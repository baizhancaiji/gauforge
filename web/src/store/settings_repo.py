"""运行级设置持久化（m1-plan §2.2 settings 表 + §4.3 B1）。

- 无记录回落 config.RUNTIME_DEFAULTS；启动级参数永不入库。
- 校验逻辑从 M0 mock 迁移并加固：整批校验通过才应用（all-or-nothing），
  integer/number 严格类型检查（bool 拒绝）。
"""
from __future__ import annotations

import json

from .. import config
from .db import Database


class SettingsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, key: str, default: object = None, *, use_default: bool = True) -> object:
        row = self._db.one("SELECT value FROM settings WHERE key = ?", (key,))
        if row is not None:
            return json.loads(row["value"])
        if default is not None:
            return default
        if use_default:
            return config.RUNTIME_DEFAULTS.get(key)
        return None

    def all(self) -> dict[str, object]:
        merged = dict(config.RUNTIME_DEFAULTS)
        merged.update(self._raw_all())
        return merged

    def _raw_all(self) -> dict[str, object]:
        rows = self._db.query("SELECT key, value FROM settings")
        return {r["key"]: json.loads(r["value"]) for r in rows}

    def set(self, key: str, value: object) -> None:
        self._db.run(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)))

    # ---------------- 校验与应用（settings 路由唯一入口） ----------------

    def apply_update(self, values: dict[str, object]) -> list[dict]:
        """整批校验（unknown/readonly/range/type），全部通过才写入。"""
        failures: list[dict] = []
        clean: dict[str, object] = {}
        for key, value in values.items():
            meta = config.SETTINGS_CATALOG.get(key)
            if meta is None or not meta["editable"]:
                # 启动级只读项与未知 key 同样按「不可写」拒绝（不入库）。
                failures.append({"key": key,
                                 "reason": "unknown_setting" if meta is None else "readonly"})
                continue
            if not self._valid_value(meta, value):
                failures.append({"key": key, "reason": "out_of_range", "value": value})
                continue
            clean[key] = value
        if failures:
            return failures
        for key, value in clean.items():
            self.set(key, value)
        return []

    @staticmethod
    def _valid_value(meta: dict, value: object) -> bool:
        vtype = meta.get("value_type")
        if vtype == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                return False
        elif vtype == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False
        elif vtype == "string":
            if not isinstance(value, str):
                return False
        rng = meta.get("range")
        if rng is None:
            return True
        num = float(value)  # type: ignore[arg-type]
        lo, hi = rng["min"], rng["max"]
        if lo is not None and num < lo:
            return False
        if hi is not None and num > hi:
            return False
        return True
