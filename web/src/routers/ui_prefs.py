"""ui-prefs 域路由：前端视图偏好持久化（列表排序规则等）。

存储于工作区 SQLite ui_prefs 表（store.ui_prefs_repo），跨重启、更新、
断联不回默认值。键白名单与值域见 config.UI_PREF_KEYS；整批校验
（all-or-nothing）对齐 settings 路由纪律。不发 SSE 事件：视图偏好为
单浏览器态，不做跨标签页同步。
"""
from __future__ import annotations

from fastapi import APIRouter

from .. import config
from ..errors import VALIDATION_FAILED, err
from ..store import ui_prefs

router = APIRouter(tags=["ui-prefs"])


@router.get("/ui-preferences")
def get_ui_preferences() -> dict:
    return {"prefs": ui_prefs().all()}


@router.put("/ui-preferences")
def update_ui_preferences(payload: dict) -> dict:
    prefs = payload.get("prefs")
    if not isinstance(prefs, dict):
        raise VALIDATION_FAILED([{"field": "prefs", "reason": "must_be_object"}])

    # 整批校验先于应用（all-or-nothing）：任一未知键或越域值全批不写入。
    failures: list[dict] = []
    clean: dict[str, str] = {}
    for key, value in prefs.items():
        allowed = config.UI_PREF_KEYS.get(key)
        if allowed is None:
            failures.append({"key": key, "reason": "unknown_key"})
        elif not isinstance(value, str) or value not in allowed:
            failures.append({"key": key, "reason": "enum"})
        else:
            clean[key] = value
    if failures:
        raise err("INVALID_REQUEST", "UI 偏好键未知或值不在值域内（整批拒绝）",
                  {"errors": failures}, http=400)

    for key, value in clean.items():
        ui_prefs().set(key, value)
    return {"prefs": ui_prefs().all()}
