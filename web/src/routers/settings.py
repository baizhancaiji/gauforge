"""settings 域路由：两级设置读写（§2.2 / roadmap §2.5）。"""
from __future__ import annotations

from fastapi import APIRouter

from .. import config
from ..errors import VALIDATION_FAILED, err
from ..mock import get_state
from starlette import status

router = APIRouter(tags=["settings"])


def _item(meta: dict) -> dict:
    state = get_state()
    key = meta["key"]
    if key in ("home_dir", "bind_addr"):
        value = config.setting_value(key)
    elif key in config.RUNTIME_DEFAULTS:
        value = state.get_runtime(key)
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
    failures = get_state().update_runtime(values)
    if failures:
        raise VALIDATION_FAILED(failures)

    state = get_state()
    state.emit("settings.updated", {"keys": sorted(values.keys())})
    return {
        "startup": [_item(m) for m in config.STARTUP_SETTINGS],
        "runtime": [_item(m) for m in config.RUNTIME_SETTINGS],
    }