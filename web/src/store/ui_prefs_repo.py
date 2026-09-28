"""ui_prefs 表 DAL（前端视图偏好键值，GET/PUT /ui-preferences）。

- 键值域白名单与校验在 config.UI_PREF_KEYS（路由层整批校验），本层只存取。
- value 与 settings 表同模式 JSON 序列化，防未来值类型扩展时歧义。
"""
from __future__ import annotations

import json

from .db import Database


class UiPrefsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def all(self) -> dict[str, str]:
        """全部已持久化键值（无记录键不在结果中，前端各自回落默认值）。"""
        rows = self._db.query("SELECT key, value FROM ui_prefs")
        return {r["key"]: json.loads(r["value"]) for r in rows}

    def set(self, key: str, value: str) -> None:
        self._db.run(
            "INSERT INTO ui_prefs (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)))
