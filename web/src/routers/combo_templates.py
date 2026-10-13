"""组合流模板域路由（GET /combo-templates、PUT /combo-templates/{templateId}）。

体例照抄 ui_prefs 先例：值级校验归 services.combo_templates.validate_and_normalize
单点（errors 全量 422 VALIDATION_FAILED，零新增错误码）；404=templateId ∉
1–5。请求体用契约模型（ComboTemplateUpdate）承载：仅结构级类型错误（如
nproc 提交 JSON number）由框架 422 直接返回、不进 details.errors[] 细分
（§3.2 末注）。不发 SSE 事件（对话框打开时拉取，ui-preferences 同口径）。
"""
from __future__ import annotations

from fastapi import APIRouter

from .. import config
from ..errors import not_found
from ..models.models import ComboTemplateUpdate
from ..services import combo_templates as svc
from ..store import combo_templates as repo

router = APIRouter(tags=["combo-templates"])


def _serialize(row: dict) -> dict:
    """存储行 → 契约条目（nproc/mem_gb/cpu 规范字符串形态，GB 去尾零）。"""
    return {
        "template_id": row["template_id"],
        "name": row["name"],
        "route": row["route"],
        "nproc": None if row["nproc"] is None else str(row["nproc"]),
        "mem_gb": None if row["mem_gb"] is None else svc._num_txt(row["mem_gb"]),
        "cpu": row["cpu"],
        "is_default": bool(row["is_default"]),
        "updated_at": row["updated_at"],
    }


@router.get("/combo-templates")
def get_combo_templates() -> dict:
    """5 套方案按 id 升序全量 + 初始值（initial.route 供「清空恢复」）。"""
    return {"templates": [_serialize(r) for r in repo().get_all()],
            "initial": {"route": config.COMBO_TEMPLATE_INITIAL_ROUTE}}


@router.put("/combo-templates/{template_id}")
def update_combo_template(template_id: int,
                          payload: ComboTemplateUpdate) -> dict:
    """全量替换保存（校验→归一化→落库→更新后条目 + notice）。"""
    if repo().get(template_id) is None:
        raise not_found("combo_template", template_id)
    fields, notice = svc.validate_and_normalize(
        template_id, payload.model_dump())
    saved = repo().update(template_id, fields)
    return {**_serialize(saved), "notice": notice}
