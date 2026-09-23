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

    # ---------- 存活探测 ----------
    def server_alive(self) -> bool:
        try:
            CliGateway(self.hq_path, str(self.server_dir)).jobs()
            return True
        except GatewayError:
            return False

    # ---------- 启动 ----------
    def start(self, wait_timeout: float = 10.0) -> bool:
        """启动 server；已有实例则复用。返回是否新起了进程。"""
        self.server_dir.mkdir(parents=True, exist_ok=True)
        if self.server_alive():  # 已有实例：复用不新起
            self._ensure_watchdog()
            return False
        if self._server_proc is None:
            log = open(self.server_dir / "server.log", "ab")
            cmd = [self.hq_path, "--server-dir", str(self.server_dir),
                   "server", "start", "--journal", str(self.journal_path)]
            if self.http_port is not None:
                cmd += ["--http-port", str(self.http_port)]
            self._server_proc = subprocess.Popen(
                cmd, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True)
        deadline = time.monotonic() + wait_timeout
        while time.monotonic() < deadline:
            if self.server_alive():
                self._ensure_watchdog()
                return True
            time.sleep(0.25)
        raise GatewayError("HQ server 启动超时")

    def ensure_worker(self, cpus: int = 1, wait_timeout: float = 10.0) -> int:
        """保证至少一个在线 worker，返回其 id。"""
        gw = CliGateway(self.hq_path, str(self.server_dir))
        online = [w for w in gw.workers() if w["online"]]
        if not online:
            log = open(self.server_dir / "worker.log", "ab")
            # 不禁资源检测：mem 资源请求（B6 双账第二账）依赖 worker
            # 上报 mem；--cpus 仍显式约束（cpus 闭区间上报见 cli_gateway）
            cmd = [self.hq_path, "--server-dir", str(self.server_dir),
                   "worker", "start", "--cpus", str(cpus),
                   "--on-server-lost", "stop",
                   "--work-dir", str(self.server_dir / "worker")]
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            self._worker_procs.append(proc)
            deadline = time.monotonic() + wait_timeout
            while time.monotonic() < deadline:
                online = [w for w in gw.workers() if w["online"]]
                if online:
                    break
                time.sleep(0.25)
            else:
                raise GatewayError("HQ worker 启动超时")
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
            subprocess.run(
                [self.hq_path, "--server-dir", str(self.server_dir),
                 "server", "stop"], capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
        for proc in [*self._worker_procs, self._server_proc]:
            if proc is not None and proc.poll() is None:
                proc.terminate()
        self._server_proc = None
        self._worker_procs = []
