"""HttpGateway：HQ server 内嵌 HTTP/SSE 桥接消费端（m1-plan §2.1 过渡策略、§4.3 B4 续）。

- REST：POST /jobs（提交）、GET /jobs（批量状态）、POST /jobs/{id}/cancel（取消）、
  GET /workers（worker 列表）、GET /info（可达性探测）——JSON 形状对齐
  `hq --output-mode json`（H2 双路一致由 server 侧共用实现保证）；
- 事件：GET /events SSE 流由后台线程消费（薄桥接：不缓存不重放，断线自动
  重连，缺口由 g16web 重启对账补齐，§2.1/§8.6）——HQ 事件映射为与
  CliGateway 同语义的 job_state 差分事件（Dispatcher 无感切换）；
- 映射依据 H3 定稿事件清单（m1-plan §2.1 SSE 事件名清单）：job/task 域
  足以派生单一作业状态；task_id 为 serde 结构 {"job_id", "job_task_id"}。
"""
from __future__ import annotations

import json
import threading

import httpx

from .gateway import Gateway, GatewayError, derive_job_state, worker_resources

# HQ 事件 → 作业状态（单任务数组作业；task_finished 与 job_completed 双保险，
# 差分去重保证同一状态只产出一枚事件）
_STATE_EVENTS: dict[str, str] = {
    "submit": "waiting",
    "job_open": "waiting",
    "job_idle": "waiting",
    "task_started": "running",
    "task_finished": "finished",
    "job_completed": "finished",
    "job_cancel": "canceled",
}


class HttpGateway(Gateway):
    def __init__(self, base_url: str, *, timeout: float = 15.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base, timeout=timeout,
                                    transport=transport)
        self._prev: dict[int, str] = {}
        self._events: list[dict] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._event_loop,
                                        name="hq-sse", daemon=True)
        self._thread.start()

    # ---------- REST ----------
    def _request(self, method: str, path: str, *,
                 json_body: dict | None = None) -> object:
        try:
            resp = self._client.request(method, path, json=json_body)
        except httpx.HTTPError as exc:
            raise GatewayError(f"HQ HTTP 请求失败 {method} {path}: {exc}") from exc
        if resp.status_code >= 400:
            raise GatewayError(f"HQ HTTP {resp.status_code} {path}: "
                               f"{resp.text[:200]}")
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError as exc:
            raise GatewayError(f"HQ HTTP 响应非 JSON: {resp.text[:200]}") from exc

    def info(self) -> dict:
        """GET /info（可达性探测/健康检查）。"""
        return self._request("GET", "/info")  # type: ignore[return-value]

    def submit(self, command: list[str], cwd: str | None = None,
               name: str | None = None, resources: dict | None = None,
               time_limit_s: int = 0) -> str:
        body: dict = {"args": list(command), "time_limit_s": int(time_limit_s or 0)}
        if cwd:
            body["cwd"] = cwd
        if name:
            body["name"] = name
        if resources:
            rq: dict = {}
            if resources.get("cpus"):
                rq["cpus"] = int(resources["cpus"])
            if resources.get("mem_mib"):
                # HQ mem 资源值以 MiB 计（与 CliGateway 同语义）
                rq["mem_mib"] = int(resources["mem_mib"])
            if rq:
                body["resources"] = rq
        out = self._request("POST", "/jobs", json_body=body)
        return str(out["id"])  # type: ignore[index]

    def cancel(self, job_id: str) -> None:
        self._request("POST", f"/jobs/{job_id}/cancel")

    def jobs(self) -> list[dict]:
        out = self._request("GET", "/jobs") or []
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
        out = self._request("GET", "/workers") or []
        workers = []
        for w in out:
            conf = w.get("configuration") or {}
            cpus, mem_mib = worker_resources(conf)
            workers.append({
                "id": str(w["id"]),
                "online": w.get("ended") is None,
                "hostname": conf.get("hostname"),
                "cpus": cpus,
                "mem_mib": mem_mib,
            })
        return workers

    # ---------- SSE 事件消费（后台线程 → job_state 差分事件） ----------
    @classmethod
    def _job_id_of(cls, data: dict) -> int | None:
        jid = data.get("job_id")
        if jid is not None:
            return int(jid)
        task = data.get("task_id")
        if isinstance(task, dict) and "job_id" in task:
            return int(task["job_id"])
        return None

    def _ingest(self, name: str, data: dict) -> None:
        state = _STATE_EVENTS.get(name)
        if state is None:
            return
        jid = self._job_id_of(data)
        if jid is None:
            return
        with self._lock:
            prev = self._prev.get(jid)
            if prev != state:
                self._prev[jid] = state
                self._events.append({"type": "job_state", "job_id": jid,
                                     "state": state, "prev_state": prev})

    def _event_loop(self) -> None:
        while not self._stop.is_set():
            try:
                # 心跳（axum KeepAlive 15s）维持读超时；断线即重连
                timeout = httpx.Timeout(60.0)
                with self._client.stream("GET", "/events", timeout=timeout) \
                        as resp:
                    if resp.status_code != 200:
                        raise GatewayError(f"SSE /events {resp.status_code}")
                    name: str | None = None
                    for line in resp.iter_lines():
                        if self._stop.is_set():
                            break
                        if not line or line.startswith(":"):
                            continue  # 心跳注释帧
                        if line.startswith("event:"):
                            name = line[len("event:"):].strip()
                        elif line.startswith("data:") and name:
                            self._ingest(name, json.loads(line[len("data:"):]))
                            name = None
            except Exception:  # noqa: BLE001 - 重连循环线程不得因异常死亡
                pass  # 薄桥接：缺口由 REST 对账补齐（§2.1）
            if not self._stop.is_set():
                self._stop.wait(1.0)

    def poll_events(self) -> list[dict]:
        with self._lock:
            events, self._events = self._events, []
        return events

    def close(self) -> None:
        self._stop.set()
        self._client.close()
