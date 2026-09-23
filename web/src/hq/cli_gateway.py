"""CLI Gateway：`hq --output-mode json` 子进程封装（m1-plan B4）。

- 参数一律列表形式（禁止 shell=True）；经 --server-dir 套接字发现服务端。
- events 以轮询 `job list --all` 差分模拟（默认周期 2s，由调用方驱动节拍）。
"""
from __future__ import annotations

import json
import subprocess

from .gateway import Gateway, GatewayError, derive_job_state


class CliGateway(Gateway):
    def __init__(self, hq_path: str, server_dir: str | None = None):
        self.hq_path = hq_path
        self.server_dir = server_dir
        self._prev_states: dict[int, str] = {}

    # ---------- 内部 ----------
    def _run(self, *args: str, timeout: float = 15.0):
        cmd = [self.hq_path, "--output-mode", "json"]
        if self.server_dir:
            cmd += ["--server-dir", self.server_dir]
        cmd += list(args)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise GatewayError(f"hq 调用超时: {' '.join(args)}") from e
        except OSError as e:
            raise GatewayError(f"hq 调用失败: {e}") from e
        if proc.returncode != 0:
            raise GatewayError(
                f"hq {args[0]} 退出码 {proc.returncode}: {proc.stderr.strip()}")
        # JSON 模式下错误（如 job not found）走 stderr ERROR 日志且退出码为 0
        if "ERROR" in proc.stderr:
            raise GatewayError(
                f"hq {args[0]} 失败: {proc.stderr.strip().splitlines()[-1]}")
        try:
            return json.loads(proc.stdout) if proc.stdout.strip() else None
        except json.JSONDecodeError as e:
            raise GatewayError(f"hq 输出非 JSON: {proc.stdout[:200]}") from e

    # ---------- Gateway ----------
    def submit(self, command: list[str], cwd: str | None = None,
               name: str | None = None) -> str:
        args = ["submit"]
        if cwd:
            args += ["--cwd", cwd]
        if name:
            args += ["--name", name]
        args += ["--"] + list(command)
        out = self._run(*args)
        return str(out["id"])

    def cancel(self, job_id: str) -> None:
        self._run("job", "cancel", str(job_id))

    def jobs(self) -> list[dict]:
        out = self._run("job", "list", "--all") or []
        jobs = []
        for j in out:
            stats = j.get("task_stats") or {}
            jobs.append({
                "id": str(j["id"]),
                "name": j.get("name"),
                "state": derive_job_state(stats, j.get("cancel_reason")),
                "task_count": j.get("task_count", 0),
                "task_stats": stats,
            })
        return jobs

    def workers(self) -> list[dict]:
        out = self._run("worker", "list", "--all") or []
        workers = []
        for w in out:
            resources = (w.get("configuration", {}).get("resources") or {})
            cpus = 0
            for res in resources.get("resources", []):
                if res.get("name") == "cpus":
                    cpus = max(cpus, int(res.get("end", 0)) - int(res.get("start", 0)))
            workers.append({
                "id": str(w["id"]),
                "online": w.get("ended") is None,
                "hostname": w.get("configuration", {}).get("hostname"),
                "cpus": cpus,
            })
        return workers

    def poll_events(self) -> list[dict]:
        current = {int(j["id"]): j["state"] for j in self.jobs()}
        events = []
        for jid, state in current.items():
            prev = self._prev_states.get(jid)
            if prev != state:
                events.append({"type": "job_state", "job_id": jid,
                               "state": state, "prev_state": prev})
        self._prev_states = current
        return events
