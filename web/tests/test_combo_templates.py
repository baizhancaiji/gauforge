"""组合流精修模板测试（插波 3.2.0 批次 B，m4-combo-template-deploy-plan §4）。

提交 #3（迁移+repo+config 常量）落种子幂等/重启 roundtrip/is_default
事务性断言；#5（校验服务+端点）落 §3.2 校验矩阵逐 reason（11 项）、
enforce/warn 双形态、端点 200/404/422 契约、序列化往返与提交链零改动回归。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.main import app
from web.src.parse import keywords as kw_mod
from web.src.services import combo_templates as svc
from web.src.store import Database, run_migrations
from web.src.store.combo_templates_repo import ComboTemplatesRepo
from .conftest import assert_contract_schema, load_spec

spec = load_spec()
client = TestClient(app)

INITIAL_ROUTE = config.COMBO_TEMPLATE_INITIAL_ROUTE


def _fields(**over):
    """合法全量字段（对齐 repo.update 形参；存储层 int/float/str|None）。"""
    base = {"name": "配置1", "route": INITIAL_ROUTE,
            "nproc": None, "mem_gb": None, "cpu": None, "is_default": False}
    base.update(over)
    return base


@pytest.fixture()
def repo(tmp_path):
    d = Database(tmp_path / "ct.db")
    run_migrations(d)
    yield ComboTemplatesRepo(d)
    d.close()


def _put(template_id: int, **body):
    return client.put(f"/api/v1/combo-templates/{template_id}", json=body)


def _reasons(resp) -> list[str]:
    return [e["reason"]
            for e in resp.json()["error"]["details"]["errors"]]


# ---------------- 种子与 repo（提交 #3） ----------------

def test_seed_idempotent_rerun(tmp_path):
    """迁移重复执行不重复播种（INSERT OR IGNORE），恒 5 行。"""
    d = Database(tmp_path / "ct.db")
    run_migrations(d)
    run_migrations(d)  # 幂等重跑
    rows = ComboTemplatesRepo(d).get_all()
    assert [r["template_id"] for r in rows] == [1, 2, 3, 4, 5]
    d.close()


def test_seed_content(repo):
    """5 套方案初始全存在：name=配置n、route=初始值、link0 三字段空、
    is_default 仅 id=1。"""
    rows = repo.get_all()
    assert [r["name"] for r in rows] == [f"配置{i}" for i in range(1, 6)]
    assert all(r["route"] == INITIAL_ROUTE for r in rows)
    assert all(r["nproc"] is None and r["mem_gb"] is None and r["cpu"] is None
               for r in rows)
    assert [r["template_id"] for r in rows if r["is_default"]] == [1]


def test_restart_roundtrip(tmp_path):
    """保存后重开连接（模拟重启）读值一致。"""
    d1 = Database(tmp_path / "ct.db")
    run_migrations(d1)
    ComboTemplatesRepo(d1).update(
        2, _fields(name="自定义", route="#p hf opt", nproc=4, mem_gb=8.0))
    d1.close()

    d2 = Database(tmp_path / "ct.db")
    run_migrations(d2)
    row = ComboTemplatesRepo(d2).get(2)
    assert row["name"] == "自定义" and row["route"] == "#p hf opt"
    assert row["nproc"] == 4 and row["mem_gb"] == 8.0
    assert row["cpu"] is None and row["is_default"] == 0
    d2.close()


def test_is_default_exclusive_migration(repo):
    """is_default 迁移事务性：置 1 同事务清其余，恒有且仅有一个默认。"""
    repo.update(3, _fields(is_default=True))
    assert [r["template_id"] for r in repo.get_all() if r["is_default"]] == [3]
    repo.update(5, _fields(is_default=True))
    rows = repo.get_all()
    assert [r["template_id"] for r in rows if r["is_default"]] == [5]
    assert sum(r["is_default"] for r in rows) == 1


def test_is_default_false_preserves_row_state(repo):
    """is_default=False 保持该行现值：默认行不自摘、非默认行不自立
    （契约：缺省/false 不改变现有默认归属）。"""
    repo.update(1, _fields(is_default=False))
    assert [r["template_id"] for r in repo.get_all() if r["is_default"]] == [1]
    repo.update(2, _fields(is_default=False))
    rows = repo.get_all()
    assert [r["template_id"] for r in rows if r["is_default"]] == [1]
    assert sum(r["is_default"] for r in rows) == 1


def test_update_refreshes_updated_at(repo):
    before = repo.get(1)["updated_at"]
    row = repo.update(1, _fields(name="改名"))
    assert row["name"] == "改名"
    assert row["updated_at"] >= before  # 审计时间戳不早于更新前


def test_get_unknown_returns_none(repo):
    assert repo.get(9) is None


# ---------------- 端点契约（GET 200 / PUT 200 / 404 / 422） ----------------

def test_get_templates_contract():
    r = client.get("/api/v1/combo-templates")
    assert r.status_code == 200
    body = r.json()
    assert [t["template_id"] for t in body["templates"]] == [1, 2, 3, 4, 5]
    assert body["initial"] == {"route": INITIAL_ROUTE}
    assert_contract_schema(spec, "GET", "/combo-templates", 200, body)


def test_put_ok_contract_and_notice():
    r = _put(2, name="方案二", route=INITIAL_ROUTE, nproc="4", mem_gb="8",
             cpu="1-4", is_default=True)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "方案二" and body["nproc"] == "4"
    assert body["mem_gb"] == "8" and body["cpu"] == "1-4"
    assert body["is_default"] is True
    # 初始 route 含 freq 无温度 → freq 联动自动补
    assert body["notice"]["temp_applied"] is True
    assert body["notice"]["normalized"] is False
    assert body["route"].endswith("temperature=298.15")
    assert_contract_schema(spec, "PUT", "/combo-templates/{templateId}", 200,
                           body)


def test_put_unknown_template_404():
    r = _put(9, name="x", route=INITIAL_ROUTE)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_put_structural_type_error_framework_422():
    """nproc 提交 JSON number → 框架 422、不进 details.errors[] 细分（§3.2）。"""
    r = client.put("/api/v1/combo-templates/1",
                   json={"name": "x", "route": INITIAL_ROUTE, "nproc": 4})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["errors"] == []


def test_radio_default_via_put():
    """PUT is_default=true → 唯一默认迁移（radio 语义）。"""
    assert _put(3, name="配置3", route=INITIAL_ROUTE,
                is_default=True).status_code == 200
    got = client.get("/api/v1/combo-templates").json()["templates"]
    assert [t["template_id"] for t in got if t["is_default"]] == [3]


def test_is_default_omitted_or_false_preserves_default_owner():
    """PUT 缺省/显式 false 不改变现有默认归属（契约明文）：对默认行自身
    或非默认行保存均不清默认，恒有且仅有一个默认。"""
    for body in ({"name": "配置1", "route": "#p hf opt"},
                 {"name": "配置1", "route": "#p hf opt", "is_default": False}):
        assert _put(1, **body).status_code == 200
        got = client.get("/api/v1/combo-templates").json()["templates"]
        assert [t["template_id"] for t in got if t["is_default"]] == [1]
    # 对非默认行保存 → 默认归属不变；显式 true 才迁移（见 radio 用例）
    assert _put(2, name="配置2", route="#p hf opt").status_code == 200
    got = client.get("/api/v1/combo-templates").json()["templates"]
    assert [t["template_id"] for t in got if t["is_default"]] == [1]
    assert sum(t["is_default"] for t in got) == 1


# ---------------- §3.2 校验矩阵逐 reason（11 项） ----------------

def test_reason_route_must_start_with_hash():
    r = _put(1, route="opt freq")
    assert r.status_code == 422
    assert "route_must_start_with_hash" in _reasons(r)


def test_reason_multi_line_and_blank_line_api_direct():
    """多行/空行分支经 API 直调断言（前端 @input 单行化 UI 不可构造，A6）。"""
    r = _put(1, route="#p opt\n#p freq")
    assert r.status_code == 422
    assert "multi_line_route" in _reasons(r)
    r = _put(1, route="#p opt\n\n#p freq")
    assert r.status_code == 422
    reasons = _reasons(r)
    assert "blank_line_in_route" in reasons
    assert "multi_line_route" in reasons  # 多行与空行违规一次全报


def test_reason_keyword_not_in_dict_enforce_and_ignore():
    """enforce：词典外拦截 422；ignore_spelling=true 该批放行；
    豁免仅当次生效（不落库，重开重新校验）。"""
    route = "#p b3lyp/6-31g(d) opt freq zzzzzq"
    r = _put(1, route=route)
    assert r.status_code == 422
    reasons = _reasons(r)
    assert reasons.count("keyword_not_in_dict") == 1
    entry = r.json()["error"]["details"]["errors"][0]
    assert "zzzzzq" in entry["message"]

    r = _put(1, route=route, ignore_spelling=True)
    assert r.status_code == 200
    assert r.json()["notice"]["spelling_warnings"] == ["zzzzzq"]
    # 豁免不落库：同 route 再次不带 ignore → 重新拦截
    assert _put(1, route=route).status_code == 422


def test_validate_warn_mode_passes_with_warnings():
    """warn mode：词典外 token 200 放行 + notice.spelling_warnings（A7b）。"""
    fields, notice = svc.validate_and_normalize(
        1, {"route": "#p opt freq zzzzzq"}, mode="warn")
    assert fields["route"].startswith("#p opt freq")
    assert notice["spelling_warnings"] == ["zzzzzq"]
    assert notice["temp_applied"] is True  # freq 联动补温度照常


def test_enforce_official_forms_pass():
    """C3：官方合法词形在 enforce 不再误拒（输入勘误计划 §2.3 五类误拒
    + 无等号空格形 + 引号值 + 括号选项键名命中 + IOp 括号内斜杠）。"""
    for route in (
        "#p opt,freq",                       # 逗号作项目分隔符
        "#p b3lyp/6-31g(d,p) opt freq",      # 基组括号整词（回归基线）
        "#p opt ! note",                     # ! 行内注释
        "#p opt(modredundant)",              # 无等号括号形
        "#p @mols.dat",                      # @file 整文件包含
        "#p opt = (calcfc, ts)",             # = 两侧任意空格
        "#p opt (calcfc, ts)",               # 键名与括号间空格
        "#p opt=(calcfc,ts)",                # 括号选项形键名命中
        "#p IOp(6/50=1)",                    # IOp 括号内斜杠不切分
        '#p External="RunTink Amber"',       # 引号值内空格不切分
        "#p opt freq @mols.dat/3",           # @file/N 抑制回显后缀整词豁免（R1）
    ):
        r = _put(1, route=route)
        assert r.status_code == 200, (route, _reasons(r) if r.status_code
                                      == 422 else None)


def test_warn_mode_official_forms_no_spurious_warnings():
    """C3：warn 通道对官方合法词形不再给出错误近邻建议。"""
    for route in ("#p opt(modredundant)", "#p opt=(calcfc,ts)",
                  '#p External="RunTink Amber"'):
        fields, notice = svc.validate_and_normalize(
            1, {"route": route}, mode="warn")
        assert notice.get("spelling_warnings") in (None, []), route


def test_temp_auto_apply_bracket_form_freq():
    """R2（审查整改）：freq 括号形（无等号/空格/大小写）同样触发温度联动
    自动补——has_freq 按 token 头部判定，不漏 C3 刚放行的括号形态。"""
    for route in ("#p b3lyp/6-31g(d) freq(readanharmonic)",
                  "#p b3lyp/6-31g(d) freq (readanharmonic)",
                  "#p B3LYP/6-31G(D) FREQ(ReadFC)"):
        fields, notice = svc.validate_and_normalize(1, {"route": route})
        assert notice["temp_applied"] is True, route
        assert fields["route"].endswith("temperature=298.15"), route


def test_reason_temp_value_invalid():
    # 300,310：B1 C3 起逗号为官方分隔符，切出孤立 token 310 走词典外拦截
    # （temperature=300 本身合法单值）；单值形态仍走温度值校验
    for val, reason in (("abc", "temp_value_invalid"),
                        ("-1", "temp_value_invalid"),
                        ("300,310", "keyword_not_in_dict"),
                        ("0", "temp_value_invalid")):
        route = f"#p b3lyp/6-31g(d) opt freq temperature={val}"
        r = _put(1, route=route)
        assert r.status_code == 422, val
        assert reason in _reasons(r), val


def test_temp_auto_apply_and_no_duplicate():
    """freq 无温度 → 自动补 temperature=298.15（notice.temp_applied）；
    已配置（temp=/temperature= 两形态）→ 不重复补。"""
    r = _put(1, route="#p b3lyp/6-31g(d) opt freq")
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "#p b3lyp/6-31g(d) opt freq temperature=298.15"
    assert body["notice"]["temp_applied"] is True
    # freq= 前缀变体同判
    r = _put(2, route="#p b3lyp/6-31g(d) opt freq=vcd")
    assert r.json()["notice"]["temp_applied"] is True
    # 已配置不补（temp= 短形）
    r = _put(3, route="#p b3lyp/6-31g(d) opt freq temp=310")
    body = r.json()
    assert body["notice"]["temp_applied"] is False
    assert body["route"] == "#p b3lyp/6-31g(d) opt freq temp=310"
    # temperature= 长形
    r = _put(4, route="#p hf opt freq temperature=310")
    assert r.json()["notice"]["temp_applied"] is False


def test_reason_nproc_not_positive_int():
    for val in ("0", "-1", "2.5"):
        r = _put(1, route=INITIAL_ROUTE, nproc=val)
        assert r.status_code == 422, val
        assert "nproc_not_positive_int" in _reasons(r), val


def test_reason_mem_value_invalid():
    r = _put(1, route=INITIAL_ROUTE, mem_gb="abc")
    assert r.status_code == 422
    assert "mem_value_invalid" in _reasons(r)


def test_reason_cpu_list_invalid():
    r = _put(1, route=INITIAL_ROUTE, cpu="a-b")
    assert r.status_code == 422
    assert "cpu_list_invalid" in _reasons(r)


def test_reason_mem_below_per_core_floor():
    """mem_gb < 核数 × 1 → 拦；等于下限放行。"""
    r = _put(1, route=INITIAL_ROUTE, nproc="4", mem_gb="3.9")
    assert r.status_code == 422
    assert "mem_below_per_core_floor" in _reasons(r)
    # 有效核数回落 cpu 核数（nproc 空时）
    r = _put(1, route=INITIAL_ROUTE, cpu="0-3", mem_gb="2")
    assert "mem_below_per_core_floor" in _reasons(r)
    # 边界：mem_gb == 核数 × 1 放行
    assert _put(1, route=INITIAL_ROUTE, nproc="4", mem_gb="4").status_code == 200


def test_reason_nproc_cpu_mismatch():
    """定案：cpu 核编号总数 ≥ nproc（不足拦、多于默许）。"""
    r = _put(1, route=INITIAL_ROUTE, nproc="8", cpu="1-4")
    assert r.status_code == 422
    assert "nproc_cpu_mismatch" in _reasons(r)
    # 相等为常规形态、多于默许
    assert _put(1, route=INITIAL_ROUTE, nproc="4", cpu="1-4").status_code == 200
    assert _put(1, route=INITIAL_ROUTE, nproc="4", cpu="1-5").status_code == 200
    # nproc 空而 cpu 非空：仅书写合法性校验
    assert _put(1, route=INITIAL_ROUTE, cpu="1-4").status_code == 200


def test_reason_link0_symbol_ref_forbidden():
    r = _put(1, route="#p opt freq @task:5")
    assert r.status_code == 422
    assert "link0_symbol_ref_forbidden" in _reasons(r)
    r = _put(1, route="#p opt freq oldchk=@exec:3")
    assert r.status_code == 422
    assert "link0_symbol_ref_forbidden" in _reasons(r)


def test_errors_all_at_once():
    """errors 全量一次返回（一次全报，不逐个）。"""
    r = _put(1, route="opt freq\n\nzzzzzq", nproc="0", mem_gb="abc",
             cpu="a-b")
    assert r.status_code == 422
    reasons = _reasons(r)
    for expect in ("multi_line_route", "blank_line_in_route",
                   "route_must_start_with_hash", "keyword_not_in_dict",
                   "nproc_not_positive_int", "mem_value_invalid",
                   "cpu_list_invalid"):
        assert expect in reasons, expect


# ---------------- 清空恢复初始值 / 归一化 ----------------

def test_clear_restores_initial_name_and_route():
    assert _put(2, name="", route="").status_code == 200
    got = client.get("/api/v1/combo-templates").json()["templates"]
    row = next(t for t in got if t["template_id"] == 2)
    assert row["name"] == "配置2"
    assert row["route"].startswith("#p b3lyp")  # 恢复初始（freq 联动补温度）
    assert "temperature=298.15" in row["route"]
    # link0 三字段缺省/空 → NULL
    assert row["nproc"] is None and row["mem_gb"] is None \
        and row["cpu"] is None


def test_casefold_normalization_notice():
    r = _put(1, route="#P B3LYP/6-31G(D) OPT FREQ")
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "#p b3lyp/6-31g(d) opt freq temperature=298.15"
    assert body["notice"] == {"temp_applied": True, "normalized": True}
    # 已全小写 → normalized=false
    r = _put(1, route="#p hf opt")
    assert r.json()["notice"]["normalized"] is False


# ---------------- 序列化往返与提交链零改动（§4） ----------------

def test_serialization_roundtrip_string_forms():
    """PUT 保存后 GET 回传 link0 三字段规范字符串形态（去尾零、仅非空项）。"""
    assert _put(3, name="配置3", route="#p hf opt", nproc="4", mem_gb="8.0",
                cpu="0-3").status_code == 200
    got = client.get("/api/v1/combo-templates").json()["templates"]
    row = next(t for t in got if t["template_id"] == 3)
    assert row["nproc"] == "4" and row["mem_gb"] == "8" \
        and row["cpu"] == "0-3"
    # 小数 GB 去尾零：8.5 保持、8.0 → "8"
    assert _put(4, name="配置4", route="#p hf opt", mem_gb="8.5") \
        .status_code == 200
    got = client.get("/api/v1/combo-templates").json()["templates"]
    assert next(t for t in got if t["template_id"] == 4)["mem_gb"] == "8.5"


def test_refine_input_accepts_serialized_template():
    """提交链零改动回归：GET 值可按既有契约组装精修模板载荷并被
    _refine_input 消费（%nprocshared=4 / %mem=8GB / %cpu=1-4 行形态）。"""
    assert _put(1, name="配置1", route="#p hf opt freq temp=310", nproc="4",
                mem_gb="8", cpu="1-4").status_code == 200
    row = next(t for t in client.get("/api/v1/combo-templates")
               .json()["templates"] if t["template_id"] == 1)
    link0 = [f"%nprocshared={row['nproc']}", f"%mem={row['mem_gb']}GB",
             f"%cpu={row['cpu']}"]
    from web.src.services.workflows import _refine_input
    text = _refine_input(row["route"], link0, "0 1", ["O 0.0 0.0 0.0"], "t")
    lines = text.splitlines()
    assert lines[0:3] == ["%nprocshared=4", "%mem=8GB", "%cpu=1-4"]
    assert lines[3] == row["route"]


def test_spelling_words_loaded_and_gate_ready():
    """校验单点依赖的词典在位（1166 词=3.3 面⑤选项面 + B5 面⑥替代表单
    扩容，判据①token 全命中）。"""
    words = kw_mod.load_keywords(refresh=True)
    assert len(words) == 1166
    assert {"p", "b3lyp", "6-31g(d)", "opt", "freq"} <= words
    assert svc.SPELLING_MODE == "enforce"



# ---------------- B3 G2：模板 route 重复关键字检测 ----------------

def test_template_route_duplicate_warning():
    """warn 模式下重复关键字出 route_duplicate（非阻断）；enforce 模式
    重复不属词典外词、不新增阻断理由（重复按警告通道，§2.11 模板列）。"""
    from web.src.services import combo_templates as ct
    payload = {"route": "#p mp2 mp2/6-31g(d)", "nproc": "4",
               "mem_gb": "8", "cpu": "0-3"}
    fields, notice = ct.validate_and_normalize(1, payload, mode="warn")
    assert notice.get("route_duplicates"), "warn 模式应携带重复关键字清单"
    assert notice["route_duplicates"][0]["keyword"] == "mp2"
    # enforce 模式不因重复 422（mp2 在词典），响应 notice 同样携带
    fields2, notice2 = ct.validate_and_normalize(2, payload, mode="enforce")
    assert notice2.get("route_duplicates")


def test_template_route_duplicate_exempt_shapes():
    """容器头裸形+选项形与 IOp 并写在模板通道同样豁免。"""
    from web.src.services import combo_templates as ct
    for route in ("#p freq freq=readfcht b3lyp/6-31g(d)",
                  "#p opt opt=(calcfc,ts)",
                  "#p b3lyp/6-31g(d) iop(5/17=1) iop(6/50=1)"):
        _, notice = ct.validate_and_normalize(
            3, {"route": route, "nproc": "4", "mem_gb": "8", "cpu": "0-3"},
            mode="enforce")
        assert not notice.get("route_duplicates"), route


# ---------------- B4：模板 mem_gb>0 与 cpu /n ----------------

def test_template_mem_gb_must_be_positive():
    """%mem=0 拒绝（决策点 8：模板 mem_gb 阻断）。"""
    from web.src.services import combo_templates as ct
    from web.src.errors import ApiError
    with pytest.raises(ApiError):
        ct.validate_and_normalize(
            9, {"route": "#p opt", "nproc": "4", "mem_gb": "0"}, mode="enforce")
    fields, _ = ct.validate_and_normalize(
        9, {"route": "#p opt", "nproc": "4", "mem_gb": "8"}, mode="enforce")
    assert fields["mem_gb"] == 8.0


def test_template_cpu_slash_n_accepted():
    """%cpu=0-5/2 步长区间模板放行（计数按步长）。"""
    from web.src.services import combo_templates as ct
    fields, _ = ct.validate_and_normalize(
        10, {"route": "#p opt", "cpu": "0-5/2", "mem_gb": "8"}, mode="enforce")
    assert fields["cpu"] == "0-5/2"


# ---------------- B5：G7 面⑥替代表单 + G8 子选项归属警告 ----------------

def test_enforce_route_alternate_forms_pass():
    """G7：#N/#P/#T 官方替代表单（route 页 Alternate Forms）enforce 通过
    （B5 前缺 n/t 词条，#T/#N 模板被误拒）。"""
    for route in ("#t b3lyp/6-31g(d) opt", "#n b3lyp/6-31g(d) opt",
                  "#p b3lyp/6-31g(d) opt"):
        r = _put(1, route=route)
        assert r.status_code == 200, (route, _reasons(r))


def test_enforce_bare_abbreviation_rejected():
    """G7 决策点 5：裸词缩写（fre/geo）词典精确匹配失败 → enforce 拒绝
    （不做最短唯一前缀近似）。"""
    r = _put(1, route="#p fre geo")
    assert r.status_code == 422
    reasons = _reasons(r)
    assert reasons.count("keyword_not_in_dict") == 2


def test_notice_route_option_warnings():
    """G8：子选项归属警告不阻断（enforce 键名命中 token 照常放行），随
    notice.route_option_warnings 回传（契约 B5 新增可选字段）。"""
    r = _put(1, route="#p opt=(readfcht) freq")
    assert r.status_code == 200, _reasons(r)
    ws = r.json()["notice"]["route_option_warnings"]
    assert len(ws) == 1
    assert ws[0]["kind"] == "route_option_unknown"
    assert ws[0]["keyword"] == "readfcht"
    assert ws[0]["line"] == 1  # 模板 route 单行


def test_notice_route_option_warnings_ambiguous_prefix():
    """G8 歧义缩写：scf=conv（Conver/Conventional 歧义，官方明文非法）
    enforce 键名命中放行，随 notice 提示；唯一前缀缩写 scf=conven 判活
    零警告（官方 Syntax Rules 正面例）。"""
    r = _put(1, route="#p scf=conv opt")
    assert r.status_code == 200
    assert [w["keyword"] for w in r.json()["notice"]["route_option_warnings"]] \
        == ["conv"]
    r = _put(1, route="#p scf=conven opt")
    assert r.status_code == 200
    assert r.json()["notice"].get("route_option_warnings") in (None, [])
