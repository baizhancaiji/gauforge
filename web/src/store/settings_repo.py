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
        """整批校验（unknown/readonly/type/range），全部通过才写入。

        reason 词表对齐契约载体（openapi.yaml 文件头词表二）：
        unknown_setting / readonly / range / type。"""
        failures: list[dict] = []
        clean: dict[str, object] = {}
        for key, value in values.items():
            meta = config.SETTINGS_CATALOG.get(key)
            if meta is None:
                failures.append({"key": key, "reason": "unknown_setting"})
                continue
            if not meta["editable"]:  # 启动级只读项不可写（不入库）
                failures.append({"key": key, "reason": "readonly"})
                continue
            reason = self._value_error(meta, value)
            if reason:
                failures.append({"key": key, "reason": reason, "value": value})
                continue
            clean[key] = value
        if failures:
            return failures
        for key, value in clean.items():
            self.set(key, value)
        return []

    @staticmethod
    def _value_error(meta: dict, value: object) -> str | None:
        """逐项校验：类型错 → "type"，越界 → "range"，通过 → None。

        枚举值域（range.enum，string 型参数载体，如 update_check_interval）
        先于 min/max 判断——string 值不得落入 float() 转换；不命中归 "type"
        （值域不符语义归类型错，不扩 reason 词表二）。"""
        vtype = meta.get("value_type")
        type_ok = True
        if vtype == "integer":
            type_ok = isinstance(value, int) and not isinstance(value, bool)
        elif vtype == "number":
            type_ok = (not isinstance(value, bool)
                       and isinstance(value, (int, float)))
        elif vtype == "string":
            type_ok = isinstance(value, str)
        if not type_ok:
            return "type"
        rng = meta.get("range")
        if rng is None:
            return None
        enum = rng.get("enum")
        if enum is not None:
            return None if value in enum else "type"
        num = float(value)  # type: ignore[arg-type]
        lo, hi = rng["min"], rng["max"]
        if (lo is not None and num < lo) or (hi is not None and num > hi):
            return "range"
        return None
