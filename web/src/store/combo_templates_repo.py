"""combo_templates 表 DAL（组合流精修模板 5 套方案，GET/PUT /combo-templates）。

- 值级校验与归一化（casefold、温度补齐、拼写）在
  services.combo_templates.validate_and_normalize 单点，本层只存取
  （同 ui_prefs 分层口径：路由层组合、repo 层不写 SQL 之外的业务规则）。
- is_default radio 语义：置 1 同事务清其余行，恒有且仅有一条默认、
  不可取消只能改选；迁移种子保证初始默认为 id=1。
"""
from __future__ import annotations

from .db import Database, now_iso


class ComboTemplatesRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get_all(self) -> list[dict]:
        """全部方案（恒 5 行），按 template_id 升序。"""
        return self._db.query(
            "SELECT * FROM combo_templates ORDER BY template_id")

    def get(self, template_id: int) -> dict | None:
        return self._db.one(
            "SELECT * FROM combo_templates WHERE template_id = ?",
            (template_id,))

    def update(self, template_id: int, fields: dict) -> dict:
        """全量更新一条并返回更新后行；is_default=True 时同事务清其余行。

        fields 键：name/route/nproc(int|None)/mem_gb(float|None)/
        cpu(str|None)/is_default(bool)；值级合法性由校验服务先行保证。
        """
        with self._db.tx() as conn:
            conn.execute(
                "UPDATE combo_templates SET name = ?, route = ?, nproc = ?,"
                " mem_gb = ?, cpu = ?, is_default = ?, updated_at = ?"
                " WHERE template_id = ?",
                (fields["name"], fields["route"], fields["nproc"],
                 fields["mem_gb"], fields["cpu"],
                 1 if fields["is_default"] else 0, now_iso(), template_id))
            if fields["is_default"]:
                conn.execute(
                    "UPDATE combo_templates SET is_default = 0"
                    " WHERE template_id != ?", (template_id,))
        return self.get(template_id)
