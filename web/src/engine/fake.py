"""FakeGateway：内存可编程网关（m1-plan §4.3 B6「测试先行」、§5 测试表）。

单测不依赖真 hq：测试直接驱动 set_state/poll_events 差分编排
「提交→运行→终态」全部窗口推进路径；真实 HQ 交互由 CliGateway 承担
（test_hq_gateway），fake g16 端到端见 test_dispatch_engine 集成段。
"""
from __future__ import annotations

from ..hq.gateway import Gateway


class FakeGateway(Gateway):
    """可编程事件/状态的内存 Gateway。

    - workers 可编程（cpus/mem_mib 驱动资源停等断言）；
    - set_state 变更作业状态，poll_events 以差分产出 job_state 事件
      （与 CliGateway 同语义）；
    - submit 记录 (command, cwd, name, resources, time_limit_s) 供断言。
    """

    def __init__(self, *, cpus: int = 8, mem_mib: int = 0) -> None:
        self._next_id = 1
        self._jobs: dict[str, dict] = {}
        self._prev: dict[int, str] = {}
        self._workers = [{"id": "1", "online": True, "hostname": "fake",
                          "cpus": cpus, "mem_mib": mem_mib}]
        self.submitted: list[dict] = []
        self.canceled: list[str] = []

    # ---- 测试驱动 ----
    def set_state(self, job_id: str, state: str) -> None:
        job = self._jobs[job_id]
        job["state"] = state

    def fail_worker(self) -> None:
        """模拟 HQ 不可达（workers/jobs 抛 GatewayError → 引擎停等）。"""
        self._unreachable = True

    def _check(self) -> None:
        if getattr(self, "_unreachable", False):
            from ..hq.gateway import GatewayError
            raise GatewayError("fake unreachable")

    # ---- Gateway ----
    def submit(self, command: list[str], cwd: str | None = None,
               name: str | None = None, resources: dict | None = None,
               time_limit_s: int = 0,
               env: dict[str, str] | None = None) -> str:
        self._check()
        jid = str(self._next_id)
        self._next_id += 1
        self._jobs[jid] = {"id": int(jid), "state": "waiting",
                           "task_stats": {}, "name": name}
        self.submitted.append({"command": list(command), "cwd": cwd,
                               "name": name, "resources": resources,
                               "time_limit_s": time_limit_s, "env": env})
        return jid

    def cancel(self, job_id: str) -> None:
        self._check()
        if job_id not in self._jobs:
            from ..hq.gateway import GatewayError
            raise GatewayError(f"job {job_id} not found")
        self.canceled.append(job_id)
        self.set_state(job_id, "canceled")

    def jobs(self) -> list[dict]:
        self._check()
        return [dict(j) for j in self._jobs.values()]

    def workers(self) -> list[dict]:
        self._check()
        return [dict(w) for w in self._workers]

    def poll_events(self) -> list[dict]:
        self._check()
        current = {int(j["id"]): j["state"] for j in self._jobs.values()}
        events = []
        for jid, state in current.items():
            prev = self._prev.get(jid)
            if prev != state:
                events.append({"type": "job_state", "job_id": jid,
                               "state": state, "prev_state": prev})
        self._prev = current
        return events
