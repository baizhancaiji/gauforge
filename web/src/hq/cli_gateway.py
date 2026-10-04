"""CLI Gateway：`hq --output-mode json` 子进程封装（m1-plan B4）。

- 参数一律列表形式（禁止 shell=True）；经 --server-dir 套接字发现服务端。
- events 以轮询 `job list --all` 差分模拟（默认周期 2s，由调用方驱动节拍）。
"""
from __future__ import annotations

import json
import subprocess

from .gateway import Gateway, GatewayError, derive_job_state, worker_resources


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
               name: str | None = None, resources: dict | None = None,
               time_limit_s: int = 0,
               env: dict[str, str] | None = None) -> str:
        args = ["submit"]
        if cwd:
            args += ["--cwd", cwd]
        if name:
            args += ["--name", name]
        if resources:
            if resources.get("cpus"):
                args += ["--resource", f"cpus={resources['cpus']}"]
            if resources.get("mem_mib"):
                # HQ mem 资源值以 MiB 计（纯数字，单位语法不被 0.26 接受）
                args += ["--resource", f"mem={resources['mem_mib']}"]
        if time_limit_s:
            args += ["--time-limit", f"{time_limit_s}s"]
        for k, v in (env or {}).items():
            args += ["--env", f"{k}={v}"]
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

    def job_submitted_at(self, job_id: str) -> str | None:
        """job 提交时刻：`job info <id>` 数组元素顶层 started_at
        （= server 侧 submission_date）。详情缺失/不可达 → None。"""
        try:
            out = self._run("job", "info", str(job_id))
        except GatewayError:
            return None
        if isinstance(out, list) and out:
            return out[0].get("started_at")
        return None

    def workers(self) -> list[dict]:
        out = self._run("worker", "list", "--all") or []
        workers = []
        for w in out:
            cpus, mem_mib = worker_resources(w.get("configuration") or {})
            workers.append({
                "id": str(w["id"]),
                "online": w.get("ended") is None,
                "hostname": w.get("configuration", {}).get("hostname"),
                "cpus": cpus,
                "mem_mib": mem_mib,
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
