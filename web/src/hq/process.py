"""HQ 进程管理（m1-plan B4）：spawn server/worker、健康监测、自动重启。

- server 以 --journal <workspace>/hq/server.journal 启动（切 HTTP 后追加
  --http-port，H 阶段启用）；
- 进程 start_new_session 脱离父进程组：g16web 退出不杀 HQ；
- 已有 server 在跑（server-dir 可达）则复用不新起；
- watchdog 周期检查进程存活，死亡自动重启（daemon 线程）。
"""
from __future__ import annotations

import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .cli_gateway import CliGateway
from .gateway import GatewayError


class HqProcessManager:
    def __init__(self, hq_path: str, workspace: Path,
                 http_port: int | None = None):
        self.hq_path = hq_path
        self.workspace = Path(workspace)
        self.http_port = http_port
        self.server_dir = self.workspace / "hq"
        self.journal_path = self.server_dir / "server.journal"
        self._server_proc: subprocess.Popen | None = None
        self._worker_procs: list[subprocess.Popen] = []
        self._stop = threading.Event()
        self._watchdog: threading.Thread | None = None
        # 本次生命周期内 spawn server 的时刻（复用已有实例则保持 None）：
        # S3 对账判据③的依据——server 比 job 新 ⇒ journal 恢复重跑。
        self.server_spawn_ts: str | None = None

    # ---------- 存活探测 ----------
    def server_alive(self) -> bool:
        try:
            CliGateway(self.hq_path, str(self.server_dir)).jobs()
            return True
        except GatewayError:
            return False

    # ---------- 内部辅助 ----------
    def _base_cmd(self) -> list[str]:
        return [self.hq_path, "--server-dir", str(self.server_dir)]

    def _spawn(self, name: str, args: list[str]) -> subprocess.Popen:
        """spawn 后台进程（start_new_session 脱离父组：g16web 退出不杀 HQ）。

        日志句柄用 with 管理：子进程已复制 fd，父侧即刻关闭（watchdog
        反复重启不累积句柄）。
        """
        with open(self.server_dir / f"{name}.log", "ab") as log:
            return subprocess.Popen(self._base_cmd() + args, stdout=log,
                                    stderr=subprocess.STDOUT,
                                    start_new_session=True)

    def _wait_alive(self, alive, timeout: float, what: str) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if alive():
                return
            time.sleep(0.25)
        raise GatewayError(f"HQ {what} 启动超时")

    # ---------- 启动 ----------
    def start(self, wait_timeout: float = 10.0) -> bool:
        """启动 server；已有实例则复用。返回是否新起了进程。"""
        self.server_dir.mkdir(parents=True, exist_ok=True)
        if self.server_alive():  # 已有实例：复用不新起
            self._ensure_watchdog()
            return False
        if self._server_proc is None:
            args = ["server", "start", "--journal", str(self.journal_path)]
            if self.http_port is not None:
                args += ["--http-port", str(self.http_port)]
            self._server_proc = self._spawn("server", args)
            # 与 store.db.now_iso 同格式（UTC ISO，秒精度），供 S3 判据③
            # 与 executions.started_at 直接字符串比较
            self.server_spawn_ts = datetime.now(timezone.utc).isoformat(
                timespec="seconds")
        self._wait_alive(self.server_alive, wait_timeout, "server")
        self._ensure_watchdog()
        return True

    def ensure_worker(self, cpus: int | None = None,
                      wait_timeout: float = 10.0) -> int:
        """保证至少一个在线 worker，返回其 id。

        默认不传 --cpus：worker 资源取启动探测（roadmap §8.6「worker
        资源 = 启动探测 + --resource 声明」），mem 由 HQ 自动上报——
        停等记账的「worker 总资源」依赖真实探测值；cpus 参数仅供测试
        显式约束。
        """
        gw = CliGateway(self.hq_path, str(self.server_dir))
        online = [w for w in gw.workers() if w["online"]]
        if not online:
            args = ["worker", "start", "--on-server-lost", "stop",
                    "--work-dir", str(self.server_dir / "worker")]
            if cpus is not None:
                args += ["--cpus", str(cpus)]
            self._worker_procs.append(self._spawn("worker", args))
            self._wait_alive(
                lambda: any(w["online"] for w in gw.workers()),
                wait_timeout, "worker")
            online = [w for w in gw.workers() if w["online"]]
        self._ensure_watchdog()
        return int(online[0]["id"])

    # ---------- 只读快照 ----------
    def workers(self) -> list[dict]:
        return CliGateway(self.hq_path, str(self.server_dir)).workers()

    def health_check(self) -> dict:
        try:
            workers = self.workers()
        except GatewayError:
            workers = []
        return {"server": self.server_alive(),
                "workers_online": sum(1 for w in workers if w["online"])}

    # ---------- 健康监测 ----------
    def _ensure_watchdog(self) -> None:
        if self._watchdog is None or not self._watchdog.is_alive():
            self._watchdog = threading.Thread(
                target=self._watchdog_loop, name="hq-watchdog", daemon=True)
            self._watchdog.start()

    def _watchdog_loop(self, interval: float = 5.0) -> None:
        while not self._stop.wait(interval):
            try:
                if not self.server_alive():
                    self._server_proc = None
                    self.start()
                    self.ensure_worker()
            except GatewayError:
                continue  # 下个周期重试

    # ---------- 关闭（仅测试/显式运维用） ----------
    def stop(self) -> None:
        self._stop.set()
        try:
            subprocess.run(self._base_cmd() + ["server", "stop"],
                           capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
        for proc in [*self._worker_procs, self._server_proc]:
            if proc is not None and proc.poll() is None:
                proc.terminate()
        self._server_proc = None
        self._worker_procs = []
