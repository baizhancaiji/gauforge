"""G16 Web 工作台 · 内存 mock 状态（M0）。

REST 与 SSE 共用同一状态对象（m0-plan §3.7「剧本数据与 REST mock 数据同源」）。
B1 起运行级设置退役为 SQLite（store.settings_repo）委托读取；候选、队列、席位、执行、历史仍驻留此单例（随 M1 各域真实化逐个退役）。
"""
from __future__ import annotations

import copy
import threading
from datetime import datetime, timedelta, timezone

from .. import config
from .. import store


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


class MockState:
    """整站内存状态。属性在 __init__ 内建齐，测试可靠引用。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()

        self.started_at = datetime.now(timezone.utc)

        # 自增 id：task/candidate/execution 共用全库不可复用一个计数（roadmap §2.1）。
        self._counter = 0

        self.candidates: list[dict] = []
        self.queues: list[dict] = []
        self.seats: list[dict] = []
        self.executions: list[dict] = []   # 运行/已停止；运行视图
        self.history: list[dict] = []      # 终态冻结（HistoryEntry 超集）
        self.archive_flags: set[int] = set()  # history entry id 集合

        # SSE 全局事件序号与重放窗口（m0-plan §3.5）。
        self.event_seq = 0
        self.event_history: list[dict] = []  # {"id":int,"event":str,"data":jsonstr,"ts":str}

    # ------------------------ id 分配 ------------------------
    def next_id(self) -> int:
        with self._lock:
            self._counter += 1
            return self._counter

    # ------------------------ 设置（B1 起委托 SQLite） ------------------------
    def get_runtime(self, key: str) -> object:
        return store.settings().get(key)

    def set_runtime(self, key: str, value: object) -> None:
        """演示种子写设置（真实动作即写库）。"""
        store.settings().set(key, value)

    # ------------------------ 候选 ------------------------
    def add_candidate(self, filename: str, origin: str = "imported",
                      failure_note: str | None = None) -> dict:
        cid = self.next_id()
        cand = {
            "id": cid,
            "filename": filename,
            "origin": origin,
            "failure_note": failure_note,
            "created_at": _now(),
            "title": _fake_title(filename),
        }
        with self._lock:
            self.candidates.append(cand)
        return cand

    def get_candidate(self, cid: int) -> dict | None:
        for c in self.candidates:
            if c["id"] == cid:
                return c
        return None

    def remove_candidate(self, cid: int) -> bool:
        with self._lock:
            before = len(self.candidates)
            self.candidates = [c for c in self.candidates if c["id"] != cid]
            return len(self.candidates) != before

    # ------------------------ 队列 ------------------------
    def create_queue(self, name: str, member_ids: list[int],
                     skip_failed: bool) -> dict:
        qid = _gen_queue_id()
        q = {
            "id": qid,
            "name": name,
            "member_ids": member_ids,
            "skip_failed": skip_failed,
            "state": "unsubmitted",
            "rollback_flag": False,
            "rollback_count": 0,
            "last_failure": None,
            "finish_reason": None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        with self._lock:
            self.queues.append(q)
        return q

    def get_queue(self, qid: str) -> dict | None:
        for q in self.queues:
            if q["id"] == qid:
                return q
        return None

    def delete_queue(self, qid: str) -> bool:
        with self._lock:
            before = len(self.queues)
            self.queues = [q for q in self.queues if q["id"] != qid]
            return len(self.queues) != before

    # ------------------------ 待执行席位 ------------------------
    def pending(self) -> dict:
        """GET /pending 响应体：席位 + 容量 + 窗口。"""
        limit = int(self.get_runtime("pending_seat_limit"))
        occupied = len(self.seats)
        return {
            "seats": copy.deepcopy(self.seats),
            "capacity": {
                "limit": limit,
                "occupied": occupied,
                "available": max(0, limit - occupied),
            },
            "window_size": int(self.get_runtime("parallel_window")),
        }

    # ------------------------ 执行与历史 ------------------------
    def add_execution(self, task_id: int, filename: str,
                      queue_id: str | None, time_limit_s: int = 0) -> dict:
        eid = self.next_id()
        nproc_defaulted = "nproc" not in _fake_input(task_id)
        exc = {
            "id": eid,
            "task_id": task_id,
            "queue_id": queue_id,
            "state": "running",
            "filename": filename,
            "submitted_at": _now(),
            "started_at": _now(),
            "input_hash": f"sha256:{eid:x}",
            "resources": {
                "nproc": {"value": int(self.get_runtime("link0_default_nproc")),
                          "defaulted": nproc_defaulted},
                "mem_gb": {"value": float(self.get_runtime("link0_default_mem_gb")),
                           "defaulted": True},
            },
            "hq_job_id": 1000 + eid,
            "monitor": {"cpu_percent": 0.0, "mem_rss_mb": 0.0, "elapsed_s": 0},
            "progress": {"opt_step": None, "scf_cycle": None,
                         "converged": None, "last_line": None},
        }
        with self._lock:
            self.executions.append(exc)
        return exc

    def get_execution(self, eid: int) -> dict | None:
        for e in self.executions:
            if e["id"] == eid:
                return e
        return None

    def finish_execution(self, eid: int, state: str, cause: str | None) -> dict:
        """执行到达终态：移入历史。"""
        with self._lock:
            exc = self.get_execution(eid)
            if exc is None:
                raise KeyError(eid)
            self.executions = [e for e in self.executions if e["id"] != eid]
            exc["state"] = state
            started = datetime.fromisoformat(exc["started_at"])
            wall = (datetime.now(timezone.utc) - started).total_seconds()
            entry = {
                **exc,
                "finished_at": _now(),
                "cause": cause,
                "wall_time_s": round(wall, 2),
                "monitor_summary": None,
                "chk_snapshot": {"protected": False, "location": None},
                "archived": False,
                "result_ref": None,
            }
            self.history.append(entry)
            return entry
    # ------------------------ SSE ------------------------
    def emit(self, event: str, data: dict) -> None:
        """记录事件到重放窗口（3.5：最近 1024 条或 5 分钟。M0 按条数）。"""
        from json import dumps
        payload = {"event": event, "data": dumps(data, ensure_ascii=False),
                   "ts": _now()}
        with self._lock:
            self.event_seq += 1
            payload["id"] = self.event_seq
            self.event_history.append(payload)
            if len(self.event_history) > 1024:
                self.event_history = self.event_history[-1024:]


def _gen_queue_id() -> str:
    import random
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去 0/O/1/I
    return "".join(random.choice(alphabet) for _ in range(6))


def _fake_title(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
    return stem.capitalize()


def _fake_input(task_id: int) -> dict:
    """伪造简单输入块（仅用于 defaulted 判定；M0 不打真文件）。"""
    # 以任务 id 奇偶决定是否含 nproc，制造 defaulted 真假两种演示数据。
    return {"nproc": "4" if task_id % 2 else ""}


_STATE: MockState | None = None


def get_state() -> MockState:
    """应用级单例（lazy）；测试可替换为独立实例。"""
    global _STATE
    if _STATE is None:
        _STATE = MockState()
        _seed(_STATE)
    return _STATE


def _seed(state: MockState) -> None:
    """演示种子：候选 + 一条队列 + 在途席位堆 + 多个并行运行执行 + 一条历史。

    目视口径：并行窗口 parallel_window=4 → 执行中页 4 槽位全满；
    在途席位上限 pending_seat_limit=6 → 待执行页 6/6 满，前 4 席在途（locked）、
    后 2 席等待区；队列席位提供成员概览多样性。
    """
    for i in range(8):
        state.add_candidate(f"job{i + 1}.gjf")

    state.set_runtime("parallel_window", 4)
    state.set_runtime("pending_seat_limit", 6)

    cands = state.candidates

    # 队列入一席位（成员=前两个候选），增添席位类型多样性。
    queue_id = state.create_queue("rho-scan", [cands[0]["id"], cands[1]["id"]],
                                  False)["id"]

    # 6 个席位：前 4 个已被并行窗口触及（在途）→ locked，后 2 个在等待区。
    seat_spec: list[tuple[str, str | None, list[int], bool]] = [
        ("task", None, [0], True),
        ("task", None, [1], True),
        ("task", None, [2], True),
        ("task", None, [3], True),
        ("task", None, [4], False),
        ("queue", queue_id, [5, 6], False),
    ]
    for pos, (kind, qid, member_cids, locked) in enumerate(seat_spec):
        sid = state.next_id()
        members = [{"task_id": cands[c]["id"], "filename": cands[c]["filename"],
                    "state": "staged"} for c in member_cids]
        state.seats.append({
            "seat_id": sid, "kind": kind,
            "task_id": None if kind == "queue" else members[0]["task_id"],
            "queue_id": qid, "position": pos, "members": members,
            "locked": locked,
        })

    # 并行槽位填满：4 条运行中执行，各带独立监控/进度读数，执行页一开即现形。
    for i in range(4):
        cand = cands[i]
        exc = state.add_execution(cand["id"], cand["filename"], None, 0)
        exc["monitor"] = {
            "cpu_percent": 40 + i * 15, "mem_rss_mb": 480 + i * 120,
            "elapsed_s": 25 + i * 60,
        }
        exc["progress"] = {
            "opt_step": i + 1, "scf_cycle": 5 + i, "converged": False,
            "last_line": f" Step number {i + 1}",
        }

    # 一条已完结历史（HistoryView 落地页目视演示）。
    done = cands[7]
    dex = state.add_execution(done["id"], done["filename"], None, 0)
    state.finish_execution(dex["id"], "succeeded", None)