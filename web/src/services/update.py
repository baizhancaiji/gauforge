"""更新域服务（v2.1.0 功能更新；D1 检查通道 + D2 执行流程）。

- 版本比较：packaging.Version，剥 v 单点复用 config.bare_version，仅严格更大。
- 探测：GET {base}/releases/latest/download/VERSION（与 update.sh --check 同源），
  超时 connect 15s / read 30s；异常按 §3.5 分类映射文案常量（单一来源，
  测试逐字引用同一常量防漂移）。
- 伴生文件（部署目录 config.PROJECT_ROOT，与 update.sh 同目录）：
  - .update-proxy：与 update.sh 共用同一份配置；null=直连 ↔ 空内容文件，
    URL 原文落盘且无尾换行（update.sh printf '%s' 实测格式互认）；
  - .update-check：最近检查结果 {latest_version, checked_at, had_update}，
    每次检查结束覆盖写 checked_at；成功时同时更新 latest_version/had_update，
    失败保留上一份成功值（可为 null）。
- 状态机九相（idle/checking/available/up_to_date/downloading/installing/
  restarting/done/failed），翻转即 emit update.phase（契约 sse.md §4.2）。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re as _re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from packaging.version import InvalidVersion, Version

from .. import config
from ..errors import ApiError, err
from ..mock import get_state
from ..store import executions as executions_store

logger = logging.getLogger(__name__)

# ---------------- 文案表（§3.2/§3.5 逐字验收基准，全角标点；单一来源） ----------------
MSG_CHECKING = "检查更新中 …"
MSG_UP_TO_DATE = "当前版本已最新！"
MSG_RESTARTING = "服务重启中 …"
MSG_DONE = "更新完成"
MSG_TIMEOUT = "连接超时，请检查网络"
MSG_CONNECT_FAILED = "无法连接更新服务器，请检查网络"
MSG_SHA256_FAILED = "更新包校验失败，已中止（现有版本未受影响）"
MSG_BLOCKED_RUNNING = "为保证运行稳定性，任务执行期间禁止更新"
MSG_UNSUPPORTED = "当前为源码运行模式，请通过 git 更新"
MSG_RETRY_EXHAUSTED = "下载中断：{reason}（重试已达上限，已停止更新）"
MSG_IN_PROGRESS = "更新流程进行中，请勿重复触发"
MSG_RECOVER_FAILED = ("更新流程曾中断（目标版本 {target} 未达成），"
                      "请重新执行更新或通过 CLI update.sh 恢复")
MSG_ABORTED = "更新流程异常中止，请重试"

# 下载重试（D2）：网络类与 5xx 重试 ≤3 次、指数退避（1s/2s/4s），4xx 不重试。
DOWNLOAD_MAX_RETRY = 3
PROGRESS_WINDOW_S = 0.5  # update.progress 合并窗口（sse.md §2：~500ms/条取最新）
SHA_BLOCK = 1 << 20  # sha256 分块读大小


def _monotonic() -> float:
    """进度节流时钟（测试注入假时间）。"""
    return time.monotonic()


def _sleep(seconds: float) -> None:
    """重试退避休眠（测试注入为 no-op 记账）。"""
    time.sleep(seconds)


def msg_http_status(code: int) -> str:
    return f"更新服务器返回异常（HTTP {code}）"


def msg_current(version: str) -> str:
    return f"当前版本 {version}"


def msg_available(version: str) -> str:
    return f"发现新版本 {version}！查看更新说明"


def msg_done(version: str) -> str:
    return f"{version} 更新完成"


# 状态机九相（与契约 UpdatePhase / 更新卡显示状态机一一对应）。
PHASES = ("idle", "checking", "available", "up_to_date", "downloading",
          "installing", "restarting", "done", "failed")

# 更新流程执行中（互斥窗口；run_check 不回翻这些相）。
IN_FLIGHT_PHASES = ("downloading", "installing", "restarting")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------- 版本比较 ----------------

# 源码形态 git describe 后缀（-N-gHASH，语义上即基线 tag + N 个提交）；packaging
# 无法解析该后缀（post 段后接 -gHASH 非法），保留则一律 InvalidVersion。
_DESCRIBE_SUFFIX_RE = _re.compile(r"-\d+-g[0-9a-f]+$")


def _comparable(version: str) -> str:
    """比较口径：剥 v（config 单点）+ 剥源码形态 git describe 后缀。"""
    return _DESCRIBE_SUFFIX_RE.sub("", config.bare_version(version))


def has_update(current: str, latest: str) -> bool:
    """仅严格更大算有更新（剥 v 单点；任一侧不可解析一律视为无更新）。"""
    try:
        return Version(_comparable(latest)) > Version(_comparable(current))
    except InvalidVersion:
        return False


# ---------------- 形态判定（守卫三：部署包形态） ----------------

def deployment_supported() -> bool:
    """干净部署包安装形态 = 部署目录 VERSION + bin/hq 布局；源码形态 False。"""
    root = config.PROJECT_ROOT
    return (root / "VERSION").is_file() and (root / "bin" / "hq").is_file()


# ---------------- .update-proxy（与 update.sh 共用配置） ----------------

def proxy_path() -> Path:
    return config.PROJECT_ROOT / ".update-proxy"


def read_proxy() -> str | None:
    """读代理通道：文件缺失/空内容 → None（直连）；URL 原文（容错剥首尾空白）。"""
    try:
        text = proxy_path().read_text(encoding="utf-8")
    except OSError:
        return None
    return text.strip() or None


def write_proxy(proxy: str | None) -> None:
    """写代理通道：null → 空内容文件；URL 原文落盘且无尾换行（printf '%s' 互认）。"""
    proxy_path().write_text("" if proxy is None else proxy, encoding="utf-8")


# ---------------- .update-check（最近检查结果伴生文件） ----------------

def check_state_path() -> Path:
    return config.PROJECT_ROOT / ".update-check"


def load_check_state() -> dict:
    """{latest_version, checked_at, had_update}；缺失/损坏回落三元 null。"""
    try:
        data = json.loads(check_state_path().read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except (OSError, ValueError):
        data = {}
    return {"latest_version": data.get("latest_version"),
            "checked_at": data.get("checked_at"),
            "had_update": data.get("had_update")}


def record_check(*, success: bool, latest_version: str | None = None,
                 had_update: bool | None = None) -> None:
    """检查结束覆盖写：checked_at 必写；成功更新 latest_version/had_update，
    失败保留上一份成功值（可为 null，§3.4 定稿规则）。"""
    prev = load_check_state()
    entry = {
        "checked_at": _now_iso(),
        "latest_version": latest_version if success else prev["latest_version"],
        "had_update": had_update if success else prev["had_update"],
    }
    check_state_path().write_text(json.dumps(entry, ensure_ascii=False),
                                  encoding="utf-8")


# ---------------- update-state（apply 流程标记，§3.4 落盘规则） ----------------

def state_path() -> Path:
    return config.PROJECT_ROOT / "update-state"


def write_state(target_version: str, phase: str,
                started_at: str | None = None) -> None:
    """apply 进入下载时创建，phase 翻转重写；started_at 缺省沿用现值
    （仅 self_update.sh 收尾置 done 时由脚本侧改写 phase、保留其余字段）。"""
    started = started_at
    if started is None:
        started = load_state().get("started_at") or _now_iso()
    entry = {"target_version": target_version, "phase": phase,
             "started_at": started}
    state_path().write_text(json.dumps(entry, ensure_ascii=False),
                            encoding="utf-8")


def load_state() -> dict | None:
    """读 update-state；缺失/损坏返回 None（视为无标记）。"""
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("phase") else None


def clear_state_file() -> None:
    """删除 update-state（done/failed 消费后删除、成功检查兜底清理）。"""
    state_path().unlink(missing_ok=True)


# ---------------- 远端探测（VERSION 附件直链，与 update.sh --check 同源） ----------------

class CheckFailed(Exception):
    """探测/拉取失败；message 即 §3.5 对应场景的逐字文案。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def release_url(proxy: str | None, asset: str) -> str:
    """release 直链拼接；代理规则与 update.sh 一致：{proxy%/}/{base}/…。"""
    base = config.UPDATE_BASE
    if proxy:
        base = f"{proxy.rstrip('/')}/{base}"
    return f"{base}/releases/latest/download/{asset}"


def _client() -> httpx.Client:
    # curl -fSL 对齐：跟随 releases 直链 302；超时 connect 15s / read 30s。
    return httpx.Client(
        timeout=httpx.Timeout(config.UPDATE_READ_TIMEOUT_S,
                              connect=config.UPDATE_CONNECT_TIMEOUT_S),
        follow_redirects=True)


def _classify_http_error(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return MSG_TIMEOUT
    return MSG_CONNECT_FAILED  # DNS 解析失败/连接被拒/读通道异常同归连接失败


def fetch_remote_version(proxy: str | None,
                         client: httpx.Client | None = None) -> str:
    """探测远端最新版本（四分支：正常/超时/DNS·连接失败/非 200 → §3.5 文案）。"""
    try:
        resp = _request(release_url(proxy, "VERSION"), client)
    except httpx.HTTPError as exc:
        raise CheckFailed(_classify_http_error(exc)) from exc
    if resp.status_code != 200:
        raise CheckFailed(msg_http_status(resp.status_code))
    text = resp.text.strip()
    try:
        Version(config.bare_version(text))
    except InvalidVersion:
        # 内容不可解析（空/非版本串）同归「远端返回异常」文案。
        raise CheckFailed(msg_http_status(resp.status_code)) from None
    return text


def _request(url: str, client: httpx.Client | None) -> httpx.Response:
    """单次 GET；client 未注入时按默认超时自建自收（测试经 MockTransport 注入）。"""
    if client is not None:
        return client.get(url)
    with _client() as hc:
        return hc.get(url)


def fetch_asset_bytes(proxy: str | None, asset: str,
                      client: httpx.Client | None = None) -> bytes:
    """拉取小附件（如 .sha256）；失败分类同探测（§3.5 文案，含非 200）。

    apply 同步预检与下载流水线共用：预检失败转 UPDATE_DOWNLOAD_FAILED（不进
    异步），流水线中段失败转 phase=failed 如实反馈（不经该码）。"""
    try:
        resp = _request(release_url(proxy, asset), client)
    except httpx.HTTPError as exc:
        raise CheckFailed(_classify_http_error(exc)) from exc
    if resp.status_code != 200:
        raise CheckFailed(msg_http_status(resp.status_code))
    return resp.content


# ---------------- 状态机（单例） ----------------

class UpdateService:
    """更新域状态机。

    - ``_lock``：内存相翻转保护（check/apply 共用，临界区轻量）；
    - ``_apply_mutex``：apply 全局互斥（D2，UPDATE_IN_PROGRESS 判据；
      check 不持此锁，避免检查被下载阻塞，R8）。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._apply_mutex = threading.Lock()
        self._phase = "idle"
        self._message: str | None = None
        self._version: str | None = None  # available 目标版本 / done 达成版本
        # apply 执行上下文（D2）：受理后至流水线结束期间非空，transition
        # 据此重写 update-state（phase 翻转落盘，§3.4）。
        self._active_target: str | None = None
        self._started_at: str | None = None
        self._pending: dict | None = None  # 受理上下文（路由调度 run_pending）
        self._recovered = False  # 启动恢复态待 GET /update/status 消费

    @property
    def phase(self) -> str:
        with self._lock:
            return self._phase

    @property
    def pending(self) -> dict | None:
        """受理上下文（路由受理后据此调度 run_pending 后台流水线）。"""
        with self._lock:
            return self._pending

    def transition(self, phase: str, *, message: str | None = None,
                   version: str | None = None) -> None:
        """相翻转：更新内存态、翻转重写 update-state（apply 执行中）并即推
        update.phase（version?/message? 按需携带）。"""
        with self._lock:
            self._phase = phase
            self._message = message
            if version is not None:
                self._version = version
            active, started = self._active_target, self._started_at
        if active is not None:
            write_state(active, phase, started_at=started)
        payload: dict = {"phase": phase, "ts": _now_iso()}
        if version is not None:
            payload["version"] = version
        if message is not None:
            payload["message"] = message
        get_state().emit("update.phase", payload)

    def status(self) -> dict:
        """UpdateStatus 响应体（字段全集按契约 A1：六字段）。

        启动恢复的 done/failed 相被本方法首次消费即删除 update-state 文件
        （§3.4：消费后删除），内存相保持至下次检查/更新。"""
        check = load_check_state()
        with self._lock:
            phase, message = self._phase, self._message
            recovered = self._recovered
            self._recovered = False
        if recovered and phase in ("done", "failed"):
            clear_state_file()
        if message is None and phase == "idle":
            message = msg_current(config.APP_VERSION)
        return {
            "current_version": config.APP_VERSION,
            "latest_version": check["latest_version"],
            "last_checked_at": check["checked_at"],
            "phase": phase,
            "message": message,
            "proxy": read_proxy(),
            "supported": deployment_supported(),
        }

    def run_check(self, client: httpx.Client | None = None) -> dict:
        """检查更新（手动/自动共用入口；只发现不安装）。

        - 流程执行中（downloading/installing/restarting）不回翻状态机，
          直接返回当前状态（check 端点无 409，不并发探测）；
        - 检查结束必写 .update-check（成功更新 latest_version/had_update，
          失败仅刷新 checked_at、保留上一份成功值）；
        - 探测失败抛 ApiError(UPDATE_CHECK_FAILED, 502)；自动检查调用方须
          自行捕获（D4），手动检查经路由直出。
        """
        if self.phase in IN_FLIGHT_PHASES:
            return self.status()
        self.transition("checking", message=MSG_CHECKING)
        proxy = read_proxy()
        try:
            remote = fetch_remote_version(proxy, client)
        except CheckFailed as exc:
            record_check(success=False)
            self.transition("failed", message=exc.message)
            raise err("UPDATE_CHECK_FAILED", exc.message, http=502)
        had_update = has_update(config.APP_VERSION, remote)
        record_check(success=True, latest_version=remote, had_update=had_update)
        if had_update:
            self.transition("available", message=msg_available(remote),
                            version=remote)
        else:
            self.transition("up_to_date", message=MSG_UP_TO_DATE)
        clear_state_file()  # 成功检查兜底清理 update-state 残留（§3.4）
        return self.status()

    # ---------------- apply（D2：守卫/同步预检/流式下载/接管拉起） ----------------

    def apply(self, client: httpx.Client | None = None,
              chunk_size: int = 65536) -> dict:
        """apply 同步段：三守卫 → 同步预检 → 受理（翻 downloading）。

        chunk_size 为流式下载分块（测试注入小块驱动进度窗口）。

        返回 status dict（202 受理 / 200 幂等 up_to_date）；守卫与预检失败
        抛 ApiError，均不动任何文件、不进异步。受理后由路由调度 run_pending()。
        """
        if not deployment_supported():
            raise err("UPDATE_UNSUPPORTED", MSG_UNSUPPORTED, http=409)
        if not self._apply_mutex.acquire(blocking=False):
            raise err("UPDATE_IN_PROGRESS", MSG_IN_PROGRESS, http=409)
        accepted = False
        try:
            if executions_store().list_by_state("running"):
                raise err("UPDATE_BLOCKED_RUNNING", MSG_BLOCKED_RUNNING,
                          http=409)
            proxy = read_proxy()
            # 同步预检①：探测 VERSION（失败 → 502 UPDATE_CHECK_FAILED）
            try:
                remote = fetch_remote_version(proxy, client)
            except CheckFailed as exc:
                record_check(success=False)
                self.transition("failed", message=exc.message)
                raise err("UPDATE_CHECK_FAILED", exc.message, http=502)
            had_update = has_update(config.APP_VERSION, remote)
            record_check(success=True, latest_version=remote,
                         had_update=had_update)
            if not had_update:
                clear_state_file()
                self.transition("up_to_date", message=MSG_UP_TO_DATE)
                return self.status()  # 已最新：200 幂等，无更新不是错误（D3）
            # 同步预检②：拉 .sha256 验下载通道（失败 → 502 UPDATE_DOWNLOAD_FAILED）
            try:
                fetch_asset_bytes(proxy, config.UPDATE_ASSET + ".sha256",
                                  client)
            except CheckFailed as exc:
                self.transition("failed", message=exc.message)
                raise err("UPDATE_DOWNLOAD_FAILED", exc.message, http=502)
            # 受理：进入下载（update-state 随 transition 落盘），转后台流水线
            with self._lock:
                self._active_target = remote
                self._started_at = _now_iso()
                self._pending = {"target": remote, "client": client,
                                 "proxy": proxy, "chunk_size": chunk_size}
            self.transition("downloading", version=remote)
            accepted = True
            return self.status()
        finally:
            if not accepted:
                self._apply_mutex.release()

    async def run_pending(self) -> None:
        """后台执行受理的下载/校验/拉起/自退（路由受理后调度）。

        结束时释放 apply 互斥；自退路径（SIGTERM）下本协程收尾与 uvicorn
        优雅关停并行，锁释放先于进程退出完成。"""
        with self._lock:
            pending = self._pending
            self._pending = None
        try:
            if pending is not None:
                await asyncio.to_thread(self._pipeline, pending["target"],
                                        pending["client"], pending["proxy"],
                                        pending["chunk_size"])
        finally:
            self._apply_mutex.release()

    def _pipeline(self, target: str, client: httpx.Client | None,
                  proxy: str | None, chunk_size: int = 65536) -> None:
        """下载（mktemp，不落部署目录）→ sha256 校验 → 拉起脚本 + 自退。"""
        tmp_dir = Path(tempfile.mkdtemp(prefix="g16web-update-"))
        try:
            sha_bytes = fetch_asset_bytes(
                proxy, config.UPDATE_ASSET + ".sha256", client)
            tar_path = self._download_with_retry(target, proxy, client,
                                                 tmp_dir, chunk_size)
            self._verify_sha256(sha_bytes, tar_path)
        except CheckFailed as exc:
            self.transition("failed", message=exc.message)
            return
        except Exception:  # 未预期异常同样如实入 failed，不静默死
            logger.exception("apply 流水线未预期异常")
            self.transition("failed", message=MSG_ABORTED)
            return
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        self.transition("installing")
        self._launch_script()

    def _download_with_retry(self, target: str, proxy: str | None,
                             client: httpx.Client | None,
                             tmp_dir: Path,
                             chunk_size: int = 65536) -> Path:
        """流式下载 release 包；网络类与 5xx 重试 ≤3 次（指数退避），4xx 不重试；
        重试前清临时文件并重置进度（部分下载丢弃）。"""
        url = release_url(proxy, config.UPDATE_ASSET)
        tar_path = tmp_dir / config.UPDATE_ASSET
        attempt = 0
        while True:
            tar_path.unlink(missing_ok=True)  # 重试前清临时文件、进度归零
            try:
                self._stream_once(url, tar_path, target, client, chunk_size)
                return tar_path
            except _RetryableDownload as exc:
                attempt += 1
                if attempt > DOWNLOAD_MAX_RETRY:
                    raise CheckFailed(
                        MSG_RETRY_EXHAUSTED.format(reason=exc.reason)) from exc
                logger.info("下载中断（第 %d 次重试）：%s", attempt, exc.reason)
                _sleep(2 ** (attempt - 1))

    def _stream_once(self, url: str, tar_path: Path, target: str,
                     client: httpx.Client | None, chunk_size: int) -> None:
        """单次流式下载；进度经 update.progress 推送（500ms 合并窗口取最新）。"""
        try:
            if client is not None:
                with client.stream("GET", url) as resp:
                    self._consume_stream(resp, tar_path, target, chunk_size)
            else:
                with _client() as hc, hc.stream("GET", url) as resp:
                    self._consume_stream(resp, tar_path, target, chunk_size)
        except httpx.HTTPError as exc:
            raise _RetryableDownload(_classify_http_error(exc)) from exc

    def _consume_stream(self, resp: httpx.Response, tar_path: Path,
                        target: str, chunk_size: int) -> None:
        if resp.status_code != 200:
            reason = msg_http_status(resp.status_code)
            if 500 <= resp.status_code < 600:
                raise _RetryableDownload(reason)  # 上游 5xx 可重试
            raise CheckFailed(reason)  # 4xx 不重试
        total_header = resp.headers.get("content-length")
        total = (int(total_header)
                 if total_header and total_header.isdigit() else None)
        started_at = _monotonic()
        last_emit = 0.0
        last_bytes = 0
        downloaded = 0
        with tar_path.open("wb") as fh:
            for chunk in resp.iter_bytes(chunk_size=chunk_size):
                fh.write(chunk)
                downloaded += len(chunk)
                now = _monotonic()
                if now - last_emit >= PROGRESS_WINDOW_S:
                    self._emit_progress(target, downloaded, total, now,
                                        started_at, last_emit, last_bytes)
                    last_emit, last_bytes = now, downloaded
        # 完成终值必推一条（100% / 窗口未满也补齐），前端进度条收口。
        self._emit_progress(target, downloaded, total, _monotonic(),
                            started_at, last_emit, last_bytes)

    def _emit_progress(self, target: str, downloaded: int,
                       total: int | None, now: float, started_at: float,
                       last_emit: float, last_bytes: float) -> None:
        span = (now - last_emit) if last_emit > 0 else (now - started_at)
        speed = (downloaded - last_bytes) / span if span > 0 else 0.0
        percent = round(downloaded * 100 / total, 1) if total else 0
        get_state().emit("update.progress", {
            "version": target, "percent": percent,
            "speed_bps": round(max(speed, 0.0), 1), "ts": _now_iso()})

    @staticmethod
    def _verify_sha256(sha_bytes: bytes, tar_path: Path) -> None:
        """sha256 校验（sha256sum -c 格式首列）；失败中止、现有文件分毫未动。"""
        expected = sha_bytes.decode("utf-8", errors="replace").split()[0].lower()
        digest = hashlib.sha256()
        with tar_path.open("rb") as fh:
            for block in iter(lambda: fh.read(SHA_BLOCK), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise CheckFailed(MSG_SHA256_FAILED)

    def _launch_script(self) -> None:
        """detached 拉起 self_update.sh + SIGTERM 优雅自退（D6 编排）。

        - 先推 update.phase(restarting)（SSE 断开前最后一条，前端转轮询）；
        - Popen 列表参数、start_new_session 脱离进程组、stdout/stderr 追加
          重定向部署目录 update.log，env 经继承沿用原进程环境；
        - 不杀进程：脚本自行等待父进程退出与端口释放后接管。"""
        self.transition("restarting")
        script = config.PROJECT_ROOT / "scripts" / "deploy" / "self_update.sh"
        log_path = config.PROJECT_ROOT / "update.log"
        with log_path.open("ab") as log:
            self._popen(["bash", str(script)], cwd=str(config.PROJECT_ROOT),
                        stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                        start_new_session=True)
        self._self_terminate()

    @staticmethod
    def _popen(*args: object, **kwargs: object) -> subprocess.Popen:
        return subprocess.Popen(*args, **kwargs)  # type: ignore[arg-type]

    @staticmethod
    def _self_terminate() -> None:
        os.kill(os.getpid(), signal.SIGTERM)  # uvicorn 优雅关停（不杀 HQ）

    def recover_from_disk(self) -> None:
        """启动恢复（§3.4；D4 挂载 lifespan）：update-state 三分支。

        - done 且 target_version == 当前 APP_VERSION → 恢复 done（更新完成）；
        - done 但版本未达 / 执行相中断（downloading/installing/restarting/failed）
          → 恢复 failed 如实提示（恢复路径=CLI update.sh 重跑）；
        - 无标记不动作。恢复态被 GET /update/status 首次消费后删除文件。"""
        st = load_state()
        if st is None:
            return
        target = st.get("target_version")
        with self._lock:
            self._recovered = True
        if st.get("phase") == "done" and target == config.APP_VERSION:
            self.transition("done", message=msg_done(target), version=target)
            return
        self.transition("failed", message=MSG_RECOVER_FAILED.format(
            target=target or "未知"))


class _RetryableDownload(Exception):
    """下载可重试失败（网络类/上游 5xx）；reason 为 §3.5 分类文案。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


_service: UpdateService | None = None


def get_service() -> UpdateService:
    """应用级单例（lazy；测试可经 reset_service 换新）。"""
    global _service
    if _service is None:
        _service = UpdateService()
    return _service


def reset_service() -> None:
    """测试清理：丢弃单例（内存相归零，伴生文件由测试自管）。"""
    global _service
    _service = None


# ---------------- 自动检查调度（D4：30s 轮询式，§1.2-5） ----------------

AUTO_CHECK_POLL_S = 30.0  # 轮询粒度（验收口径：设置变更 30s 内生效）


def window_start(interval: str, now: datetime) -> datetime | None:
    """当前周期窗口起点（本地时间锚定凌晨 01:00；never 不排程 → None）。

    daily=今日 01:00；weekly=本周一 01:00；monthly=本月 1 日 01:00。"""
    anchor = now.replace(hour=1, minute=0, second=0, microsecond=0)
    if interval == "daily":
        return anchor
    if interval == "weekly":
        return anchor - timedelta(days=now.weekday())
    if interval == "monthly":
        return anchor.replace(day=1)
    return None


def checked_within_window(checked_at: str | None, start: datetime) -> bool:
    """.update-check 的 checked_at 是否落在当前窗口起点之后
    （=本窗口已查过；解析失败按未查过处理，触发补查）。"""
    if not checked_at:
        return False
    try:
        dt = datetime.fromisoformat(checked_at)
    except ValueError:
        return False
    return dt >= start


class AutoCheckScheduler:
    """自动检查调度（30s 轮询式）。

    - 每轮醒来读最新设置值（保存即时生效，验收=30s 内生效，§1.2-5）；
    - 窗口已开始且本窗口未查过（.update-check 判定，§1.2-6）→ 触发一次
      检查：到点触发与启动补查同一口径，服务启动 ≤5min 补查由首轮醒来满足；
    - never 空转休眠（不排程不补查）；只发现不安装（run_check 无 apply）。
    """

    def __init__(self, service: UpdateService | None = None,
                 poll_seconds: float = AUTO_CHECK_POLL_S,
                 clock=None, sleeper=None, settings_reader=None) -> None:
        self._service = service or get_service()
        self._poll = poll_seconds
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._sleep = sleeper or asyncio.sleep
        self._settings = settings_reader or self._read_interval
        self._stopped = False

    @staticmethod
    def _read_interval() -> str:
        from ..store import settings as settings_store
        return str(settings_store().get("update_check_interval"))

    def should_run_now(self) -> bool:
        """本时刻是否应触发检查（窗口已开始且本窗口未查过）。"""
        now = self._clock()
        start = window_start(self._settings(), now)
        if start is None or now < start:
            return False
        return not checked_within_window(load_check_state()["checked_at"],
                                         start)

    async def step(self) -> None:
        """单次轮询步（测试入口；生产由 run() 循环调用）。

        探测在工作线程执行（httpx 同步栈不阻塞事件循环）；失败仅记日志
        （失败文案已随 phase=failed 入状态机，如实反馈）。"""
        if not self.should_run_now():
            return
        try:
            await asyncio.to_thread(self._service.run_check)
        except ApiError:
            logger.info("自动检查失败（失败文案已随 failed 相入状态机）")

    async def run(self) -> None:
        """调度主循环（挂 lifespan 后台任务；stop 后退出）。"""
        while not self._stopped:
            await self.step()
            await self._sleep(self._poll)

    def stop(self) -> None:
        self._stopped = True
