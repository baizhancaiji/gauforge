"""队列领域服务（M2 B3/B4）：PATCH 全语义、删除分级、队列 id 全库查重。

语义出处：m2-plan §2.2（状态分级矩阵/member_ids 校验/移除分流/自动成功）、
roadmap §2.1「编辑与移除边界」、§2.4 删除队列退回规则。
本层不发事件、不写 SQL（M1 模式）：返回动作清单供路由层依 sse.md §3 时序
发射（moved_in ×N → queues.changed(updated) → 自动成功 queue.status）。
"""
from __future__ import annotations

from ..errors import ApiError, err, not_found, validation_failed
from .candidates import copy_execution_input, default_inputs_dir
from ..store import executions, queues, seats, tasks

_MEMBER_FIELDS = ("name", "skip_failed", "member_ids")


def new_queue_id() -> str:
    """短随机队列 id（大写字母数字去易混字符）。

    生成时对照全库查重（roadmap §2.1/§2.6③）：queues 全表 + 任务/执行记录
    中已使用的 queue_id（含已删除队列的历史引用），命中即重试、永不复用，
    防止历史条目归属歧义。
    """
    import secrets
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    while True:
        qid = "".join(secrets.choice(alphabet) for _ in range(6))
        if (not queues().exists(qid)
                and qid not in tasks().used_queue_ids()
                and qid not in executions().used_queue_ids()):
            return qid


def _invalid_field(field: str, reason: str, message: str) -> ApiError:
    return validation_failed([{"field": field, "reason": reason,
                               "message": message}])


def _validate_member_ids(current_ids: list[int], member_ids: object) -> list[int]:
    """全量有序、原子（契约 #15）；子集校验（只减不增）、去重、下限 1。"""
    if not isinstance(member_ids, list) \
            or any(not isinstance(x, int) or isinstance(x, bool)
                   for x in member_ids):
        raise err("INVALID_REQUEST", "member_ids 须为任务 id 数组",
                  {"field": "member_ids"}, http=400)
    unique = set(member_ids)
    if len(unique) != len(member_ids):
        raise _invalid_field("member_ids", "duplicate", "成员 id 重复")
    added = sorted(unique - set(current_ids))
    if added:
        raise _invalid_field("member_ids", "member_added",
                             f"不允许新增成员（创建后只减不增）：{added}")
    if not member_ids:
        raise err("QUEUE_MEMBER_FLOOR", "队列成员不可清空（至少保留 1 个）",
                  {"current": len(current_ids), "min": 1}, http=409)
    return list(member_ids)


def _latest_execution(task_id: int) -> dict | None:
    exs = executions().list_by_task(task_id)
    return exs[-1] if exs else None


def _dispatch_removed_member(member: dict, action: dict) -> None:
    """移除分流（m2-plan §2.2）：按最近执行结局处置。"""
    tid = member["id"]
    latest = _latest_execution(tid)
    if latest is None:  # 未执行成员：退回候选（id 延续）
        tasks().return_to_candidate(tid, "returned_unrun")
        action["moved_in"].append(tid)
        return
    state = latest["state"]
    if state == "running":  # 回退后仍在跑：在途成员不可移除
        raise err("TASK_STATE_CONFLICT", "在途成员不可移除",
                  {"task_id": tid, "execution_id": latest["id"]}, http=409)
    if state == "succeeded":  # 脱离队列：历史条目与文件保留、不生成新候选
        tasks().detach_finished(tid)
        return
    if state == "failed":  # 以实际执行副本新建候选（新 id、附归因）
        new_id = tasks().create_candidate(member["filename"], "returned_failed",
                                          failure_note=latest.get("cause"))
    else:  # skipped：从未执行，回落任务输入副本，标注 returned_unrun
        new_id = tasks().create_candidate(member["filename"], "returned_unrun")
    (default_inputs_dir() / str(new_id)).write_bytes(
        copy_execution_input(latest["id"], tid))
    tasks().detach_finished(tid)


def _maybe_auto_success(queue_id: str, remaining: list[dict],
                        action: dict) -> None:
    """自动成功（roadmap §2.1）：剩余成员全部存在 succeeded 执行记录
    （最近终态即 succeeded）→ completed/success/last_failure 清 null。
    判据是「存在 succeeded 记录」而非「无失败记录」，新建队列不触发。"""
    if not remaining:
        return
    for m in remaining:
        latest = _latest_execution(m["id"])
        if latest is None or latest["state"] != "succeeded":
            return
    queues().update(queue_id, finish_reason="success", last_failure=None)
    queues().set_state(queue_id, "completed")
    action["auto_success"] = True


def queue_view(row: dict) -> dict:
    """契约 Queue 视图：聚合 member_ids（position 序）+ last_failure 反序列化
    （库行存 JSON 文本）+ SQLite 整数布尔还原。"""
    row = dict(row)
    row["member_ids"] = [m["id"] for m in tasks().list_queue_members(row["id"])]
    row["skip_failed"] = bool(row.get("skip_failed"))
    row["rollback_flag"] = bool(row.get("rollback_flag"))
    lf = row.get("last_failure")
    if isinstance(lf, str):
        import json
        row["last_failure"] = json.loads(lf)
    return row


def patch_queue(queue_id: str, payload: dict) -> dict:
    """PATCH /queues/{id} 全语义（m2-plan §2.2 状态分级矩阵）。

    返回 {"queue": 契约视图, "moved_in": [task_id…], "auto_success": bool,
    "members_changed": bool}；事件由路由层依 sse.md §3 时序发射。
    """
    q = queues().get(queue_id)
    if q is None:
        raise not_found("queue", queue_id)
    state = q["state"]
    if state not in ("unsubmitted", "submitted"):
        raise err("QUEUE_STATE_CONFLICT", "队列当前状态不可编辑",
                  {"state": state}, http=409)
    fields = {k: payload[k] for k in _MEMBER_FIELDS
              if isinstance(payload, dict) and k in payload}
    if state == "submitted" and any(k in fields for k in ("name", "skip_failed")):
        # 执行语义对已在待执行者不追溯（m2-plan §8 决策点 9）：改名/开关 409
        raise err("QUEUE_STATE_CONFLICT", "已提交队列仅可调整成员（重排/移除）",
                  {"state": state}, http=409)

    action: dict = {"queue": None, "moved_in": [], "auto_success": False,
                    "members_changed": False}
    members = tasks().list_queue_members(queue_id)
    current_ids = [m["id"] for m in members]
    if "name" in fields:
        if not fields["name"] or not str(fields["name"]).strip():
            raise _invalid_field("name", "required", "队列名不可为空")
        queues().update(queue_id, name=str(fields["name"]))
    if "skip_failed" in fields:
        queues().update(queue_id, skip_failed=bool(fields["skip_failed"]))
    if "member_ids" in fields:
        new_ids = _validate_member_ids(current_ids, fields["member_ids"])
        by_id = {m["id"]: m for m in members}
        for tid in current_ids:
            if tid not in set(new_ids):
                _dispatch_removed_member(by_id[tid], action)
        for pos, tid in enumerate(new_ids):  # 顺序即新 position（全量重写）
            tasks().enqueue(tid, queue_id, pos)
        action["members_changed"] = True
        _maybe_auto_success(queue_id,
                            [by_id[tid] for tid in new_ids], action)
    action["queue"] = queue_view(queues().get(queue_id))
    return action


def delete_queue(queue_id: str) -> dict:
    """DELETE /queues/{id} 分级处置（m2-plan §2.2、roadmap §2.4）。

    - unsubmitted：未执行成员退回候选（returned_unrun）→ 删行；
    - submitted：席位撤销（pending.snapshot 由路由层补发）→ 成员退回 → 删行；
    - executing：409（执行中不可删除）；
    - completed：全成员已执行 → detach_finished（只留历史，经历史页触达）→ 删行。

    返回 {"moved_in": [task_id…], "seat_removed": bool} 供路由层发事件。
    """
    q = queues().get(queue_id)
    if q is None:
        raise not_found("queue", queue_id)
    state = q["state"]
    if state == "executing":
        raise err("QUEUE_STATE_CONFLICT", "执行中队列不可删除",
                  {"state": state}, http=409)
    action: dict = {"moved_in": [], "seat_removed": False}
    if state == "completed":
        for m in tasks().list_queue_members(queue_id):
            tasks().detach_finished(m["id"])
    else:  # unsubmitted / submitted
        for m in tasks().list_queue_members(queue_id):
            tasks().return_to_candidate(m["id"], "returned_unrun")
            action["moved_in"].append(m["id"])
    if state == "submitted":
        seat = next((s for s in seats().list_by_position()
                     if s["kind"] == "queue" and s["queue_id"] == queue_id),
                    None)
        if seat is not None:
            seats().remove(seat["seat_id"])
            action["seat_removed"] = True
    queues().delete(queue_id)
    return action
