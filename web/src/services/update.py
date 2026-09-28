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

import json
import re as _re
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx
from packaging.version import InvalidVersion, Version

from .. import config
from ..errors import err
from ..mock import get_state

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
MSG_DOWNLOAD_INTERRUPTED = "下载中断：{reason}（已下载内容丢弃，将自动重试）"
MSG_RETRY_EXHAUSTED = "下载中断：{reason}（重试已达上限，已停止更新）"


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

    @property
    def phase(self) -> str:
        with self._lock:
            return self._phase

    def transition(self, phase: str, *, message: str | None = None,
                   version: str | None = None) -> None:
        """相翻转：更新内存态并即推 update.phase（version?/message? 按需携带）。"""
        with self._lock:
            self._phase = phase
            self._message = message
            if version is not None:
                self._version = version
        payload: dict = {"phase": phase, "ts": _now_iso()}
        if version is not None:
            payload["version"] = version
        if message is not None:
            payload["message"] = message
        get_state().emit("update.phase", payload)

    def status(self) -> dict:
        """UpdateStatus 响应体（字段全集按契约 A1：六字段）。"""
        check = load_check_state()
        with self._lock:
            phase, message = self._phase, self._message
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
        return self.status()


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
