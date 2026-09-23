"""settings 域路由：两级设置读写（§2.2 / roadmap §2.5）。

B1 起运行级参数经 SQLite 持久化（store.settings_repo），mock 设置存储退役。
"""
from __future__ import annotations

from fastapi import APIRouter

from .. import config
from ..errors import VALIDATION_FAILED
from ..mock import get_state
from ..services import pending as pending_svc
from ..store import settings as settings_store

router = APIRouter(tags=["settings"])


def _item(meta: dict) -> dict:
    key = meta["key"]
    if key in ("workspace_root", "bind_address"):
        value = config.setting_value(key)
    elif key in config.RUNTIME_DEFAULTS:
        value = settings_store().get(key)
    else:  # pragma: no cover
        value = None
    return {
        "key": key,
        "value": value,
        "value_type": meta["value_type"],
        "range": meta["range"],
        "editable": meta["editable"],
        "effect": meta["effect"],
        "env_var": meta["env_var"],
        "description": meta["description"],
    }


@router.get("/settings")
def get_settings() -> dict:
    return {
        "startup": [_item(m) for m in config.STARTUP_SETTINGS],
        "runtime": [_item(m) for m in config.RUNTIME_SETTINGS],
    }


@router.put("/settings")
def update_settings(payload: dict) -> dict:
    values = payload.get("values")
    if not isinstance(values, dict):
        raise VALIDATION_FAILED([{"field": "values", "reason": "must_be_object"}])

    # 先整批校验（全有或全无，任一失败整批拒绝），再应用。
    failures = settings_store().apply_update(values)
    if failures:
        raise VALIDATION_FAILED(failures)

    get_state().emit("settings.updated", {"keys": sorted(values.keys())})

    # 席位上限调小 → 挤出（自队尾、只挤窗口未触及席位、在跑不追溯）
    if "pending_seat_limit" in values:
        out = pending_svc.apply_capacity_limit(int(values["pending_seat_limit"]))
        for action in out["removed"]:
            for tid in action["moved_in"]:
                get_state().emit("candidates.changed",
                                 {"action": "moved_in", "candidate_id": tid})
            qid = action["queue_unsubmitted"]
            if qid is not None:
                get_state().emit("queue.status",
                                 {"queue_id": qid, "from": "submitted",
                                  "to": "unsubmitted"})
        if out["removed"]:
            get_state().emit("pending.snapshot", pending_svc.snapshot())

    return {
        "startup": [_item(m) for m in config.STARTUP_SETTINGS],
        "runtime": [_item(m) for m in config.RUNTIME_SETTINGS],
    }
