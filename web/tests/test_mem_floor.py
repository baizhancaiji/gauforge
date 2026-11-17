"""提交链每核内存下限黄警测试（3.8.0 工具箱 B16，toolbox-plan §5
test_mem_floor）。

- 触发/不触发边界：失衡声明触发（%mem=2GB + %nprocshared=8）、默认
  设置 8GB/4 核不触发、相等值不触发（严格小于）、声明值不可解析回落
  缺省核算（%mem=2W 非法 → 记账回落设置缺省）、缺省回落核算（无
  %mem/%nproc 声明按设置缺省 8GB/4 核）；
- Warning 形状钉死：kind=mem_below_per_core_floor、keyword="%mem"、
  line = %mem 声明行绝对行号（无声明取 Link0 区首行，无 Link0 取 1——
  不出现 L0）、message 携带核算内存值/核数/下限与 freqmem 入口指引；
- fail-open 恒不阻断提交（verify_and_store 正常返回）；
- 纯算术零子进程零 g16 依赖（g16_root 空目录不影响触发——本文件默认
  摘除场景即证）；
- 组合流模板保存闸常量上移零回归（test_combo_templates 全量承载）；
- 词表同步：test_warning_messages KIND_VOCABULARY 14 + 模板用例（同批
  落地，全量闸门承载）。
"""
from __future__ import annotations

from web.src import config
from web.src.errors import ApiError
from web.src.services.candidates import import_files
from web.src.services.verify import verify_and_store
from web.src.store import settings, tasks


def _mk(text: str) -> int:
    (out,) = import_files([("a.gjf", text.encode("utf-8"))],
                          inputs_dir=config.HOME_DIR / "inputs")
    return out["id"]


def _mk_raw(text: str) -> int:
    """直写 inputs 文件（绕过导入闸——导入层先拒的形态（非法 link0 值/
    缺 route）须直达提交核验层测其黄警/阻断语义）。"""
    tid = tasks().create_candidate("a.gjf", "imported")
    ind = config.HOME_DIR / "inputs"
    ind.mkdir(parents=True, exist_ok=True)
    (ind / str(tid)).write_text(text, encoding="utf-8")
    return tid


def _floor_warnings(warnings: list[dict]) -> list[dict]:
    return [w for w in warnings if w["kind"] == "mem_below_per_core_floor"]


def test_imbalanced_declaration_triggers():
    """失衡声明触发：%mem=2GB + %nprocshared=8 → 黄警，line 取 %mem
    声明行（第 1 行）、keyword="%mem"、message 含值/核数/下限与指引。"""
    tid = _mk("%mem=2GB\n%nprocshared=8\n#p opt\n\n水\n\n0 1\nO 0 0 0\n\n")
    out = verify_and_store(tid)
    (w,) = _floor_warnings(out["warnings"])
    assert w["keyword"] == "%mem"
    assert w["line"] == 1
    assert "2GB" in w["message"] and "8 核" in w["message"]
    assert "下限 8GB" in w["message"]  # 8 × 1GB/核
    assert "freqmem" in w["message"]  # 工具箱入口指引
    assert out["normalized"] is False  # 提交核验通过（黄警不阻断）


def test_default_settings_no_trigger():
    """默认设置 8GB/4 核不触发（缺省回落核算口径：8 ≥ 4 × 1）。"""
    tid = _mk("#p opt freq b3lyp/6-31g(d)\n\n水\n\n0 1\nO 0 0 0\n\n")
    out = verify_and_store(tid)
    assert _floor_warnings(out["warnings"]) == []


def test_equal_values_no_trigger():
    """相等不触发（严格小于）：%mem=8GB + %nprocshared=8。"""
    tid = _mk("%mem=8GB\n%nprocshared=8\n#p opt\n\n水\n\n0 1\nO 0 0 0\n\n")
    out = verify_and_store(tid)
    assert _floor_warnings(out["warnings"]) == []


def test_invalid_value_falls_back_to_default_accounting():
    """声明值不可解析回落缺省核算：%mem=2W 非法（值域外，导入闸先拒——
    直写 inputs 直达提交核验层）→ 记账回落设置缺省 8GB，8 核触发
    （核算值按缺省 8GB 呈现）；link0 值域黄警并存（非法输入不遮蔽）。"""
    tid = _mk_raw("%mem=2W\n%nprocshared=16\n#p opt\n\n水\n\n0 1\n"
                  "O 0 0 0\n\n")
    out = verify_and_store(tid)
    (w,) = _floor_warnings(out["warnings"])
    assert "8GB / 16 核" in w["message"]  # 核算值 = 回落缺省（8 < 16×1 触发）
    kinds = {x["kind"] for x in out["warnings"]}
    assert "link0_value_invalid" in kinds  # 非法声明提示并存


def test_no_mem_decl_line_takes_link0_first_line():
    """无 %mem 声明 → line 取 Link0 区首行（%nprocshared 行，第 1 行）；
    触发靠缺省回落核算（缺省 %mem 调低后）。"""
    settings().set("link0_default_mem_gb", "1")
    tid = _mk("%nprocshared=8\n#p opt\n\n水\n\n0 1\nO 0 0 0\n\n")
    out = verify_and_store(tid)
    (w,) = _floor_warnings(out["warnings"])
    assert w["line"] == 1  # Link0 区首行（非 0，前端不渲染 L0）
    assert w["keyword"] == "%mem"
    settings().set("link0_default_mem_gb", "8")  # 复位（隔离库逐用例独立，防御性）


def test_no_link0_line_takes_one():
    """无 Link0（输入直起 route）→ line 取 1；触发靠缺省 %mem 调低。"""
    settings().set("link0_default_mem_gb", "1")
    settings().set("link0_default_nproc", "8")
    tid = _mk("#p opt\n\n水\n\n0 1\nO 0 0 0\n\n")
    out = verify_and_store(tid)
    (w,) = _floor_warnings(out["warnings"])
    assert w["line"] == 1  # 无 Link0 取 1
    assert "1GB / 8 核" in w["message"]


def test_declared_mem_triggers_with_declared_nproc():
    """声明优先核算：%mem=3GB + %nprocshared=4 → 3 < 4 触发；%mem=4GB
    + %nprocshared=4 → 相等不触发。"""
    tid = _mk("%mem=3GB\n%nprocshared=4\n#p opt\n\n水\n\n0 1\nO 0 0 0\n\n")
    assert len(_floor_warnings(verify_and_store(tid)["warnings"])) == 1
    tid2 = _mk("%mem=4GB\n%nprocshared=4\n#p opt\n\n水\n\n0 1\nO 0 0 0\n\n")
    assert _floor_warnings(verify_and_store(tid2)["warnings"]) == []


def test_queue_submit_path_carries_warning():
    """队列提交路径（组合流成员派发同闸口）随成员聚合黄警（task_id
    填充，契约 warnings 通道既有聚合口径）——行内路径外的第二路径覆盖。"""
    from web.src.routers.queues import submit_queue
    from web.src.store import queues as queues_store, tasks as tasks_store
    ind = config.HOME_DIR / "inputs"
    (out,) = import_files([("m.gjf",
                            b"%mem=2GB\n%nprocshared=8\n#p opt\n\nt\n"
                            b"\n0 1\nO 0 0 0\n\n")], inputs_dir=ind)
    tid = out["id"]
    queues_store().create("qfloor", name="qfloor")  # 先建队（外键先行）
    tasks_store().enqueue(tid, "qfloor", 0)
    resp = submit_queue("qfloor")
    warnings = resp.get("warnings") or []
    floor = _floor_warnings(warnings)
    assert floor, f"队列提交响应未携带黄警：{warnings}"
    assert any(w.get("task_id") == tid for w in floor)


def test_blocking_semantics_untouched_by_floor():
    """黄警不改变阻断语义：黄警输入照常通过；解析失败仍 422
    INPUT_PARSE_FAILED（fail-open 只增警告、不移除既有阻断）。"""
    tid = _mk("%mem=2GB\n%nprocshared=8\n#p opt\n\nt\n\n0 1\nO 0 0 0\n\n")
    out = verify_and_store(tid)  # 黄警形态：正常返回
    assert _floor_warnings(out["warnings"])
    tid2 = _mk_raw("no route marker\n\n0 1\nO\n")
    try:
        verify_and_store(tid2)
        assert False, "解析失败应 422"
    except ApiError as exc:
        assert exc.body()["error"]["code"] == "INPUT_PARSE_FAILED"
