"""chk 工具域端点测试（3.8.0 工具箱 B12，toolbox-plan §5 test_chktools）。

- verdict 三态判定（ok 健康样例 / unreadable 截断反例样例（134 + 错误行
  无锚点）/ corrupted badroute 类样例（134 + NAtoms= 锚点））—— fixtures
  真机实测输出（2026-11-17 采集），经假 chkchk 可执行回放；
- 多步成功行 job_ok 与单步并存识别；
- 对象口径分层：体检/现转需 chk 资产；有效 fchk 幂等命中不查资产、不跑
  工具；下载只查 fchk；skipped/非终态 404；
- containment 越界（绝对路径/.. 越界/symlink 逃逸）409 path_outside；
  无资产 409 cleaned/undeclared；503 工具缺失；502 超时/启动失败；
- 前置体检闸 verdict≠ok 409（details.verdict）；半成品 fchk 不误命中
  并可重转；原子落盘无 .tmp 残留（含 make_fchk 自动物化共用 helper 回归）；
- 快照复制断言（源 chk 哈希/mtime 前后一致）与 core dump 隔离断言
  （调用 cwd 为临时目录，非 run 目录）；
- fchk 下载 FileResponse + RFC 5987 中文 stem 原样 + ASCII fallback
  清洗（清洗为空回落 execution-<id>）+ 404；归档条目同口径。
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.engine import finalize
from web.src.services import chktools as chktools_svc
from web.src.services import history as history_svc
from web.src.store import executions, settings, tasks
from .conftest import assert_contract_schema, load_spec

spec = load_spec()
client = TestClient(__import__("web.src.main", fromlist=["app"]).app)

FIXTURES = Path(__file__).parent / "fixtures" / "g16tools"
F_HEALTHY = FIXTURES / "chkchk_healthy.txt"
F_UNREADABLE = FIXTURES / "chkchk_unreadable_truncated.txt"
F_CORRUPTED = FIXTURES / "chkchk_corrupted_anchored.txt"
F_MULTISTEP = FIXTURES / "chkchk_multistep_ok.txt"

# 有效 fchk 头部锚点（fake formchk 产物；锚点名与 formchk.txt 对照一致）
FCHK_GOOD = ('Gaussian, Inc.\n'
             ' Number of atoms                            I                3\n'
             ' Number of basis functions                  I               19\n'
             ' Alpha Orbital Energies                     R   N=          19\n')


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()  # 无工具：默认即摘除场景（503 断言不依赖真机）
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    settings().set("g16_root", str(tmp_path / "g16"))
    return tmp_path


def make_tool(root: Path, name: str, script: str) -> Path:
    f = root / name
    f.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    f.chmod(0o755)
    return f


def seed(*, state: str = "succeeded", filename: str = "h2o.gjf",
         with_chk: bool = True, chk_decl: str = "%chk=input.chk",
         protected: bool = False) -> int:
    """造终态执行：input.gjf（%chk= 声明）+ chk 资产（可选 protected/
    保全形态）。无 chk 声明场景传 chk_decl=""。"""
    tid = tasks().create_candidate(filename, "imported")
    eid = executions().create(
        task_id=tid, filename=filename,
        resources={"nproc": {"value": 1, "defaulted": True},
                   "mem_gb": {"value": 1.0, "defaulted": True}})
    run_d = config.HOME_DIR / "run" / str(eid)
    run_d.mkdir(parents=True, exist_ok=True)
    lines = [f"{chk_decl}\n"] if chk_decl else []
    lines.append("#p hf/sto-3g\n\n\n0 1\nO\n")
    (run_d / "input.gjf").write_text("".join(lines), encoding="utf-8")
    if with_chk:
        if protected:
            prot = run_d / "protected"
            prot.mkdir()
            (prot / "input.chk").write_bytes(b"fake-chk-bytes")
        else:
            (run_d / "input.chk").write_bytes(b"fake-chk-bytes")
    executions().finalize(execution_id=eid, state=state,
                          finished_at="2026-01-01T00:00:00+08:00")
    return eid


def put_fchk(eid: int, content: bytes) -> None:
    (config.HOME_DIR / "run" / str(eid) / "input.fchk").write_bytes(content)


def chkchk_replay(root: Path, fixture: Path, exit_code: int) -> None:
    """假 chkchk：回放真机实测输出样例（fixtures 2026-11-17 采集）。"""
    make_tool(root, "chkchk",
              f'cat "{fixture}"\nexit {exit_code}\n')


# ---------------- verdict 三态判定与锚点提取 ----------------

def test_verdict_ok_healthy_fixture(home):
    """健康样例 → verdict=ok + 最小结构提取 + raw 透传。"""
    eid = seed()
    chkchk_replay(home / "g16", F_HEALTHY, 0)
    r = client.post(f"/api/v1/history/{eid}/analysis/chkchk")
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "ok"
    rep = body["report"]
    assert rep["version"] == "ES64L-G16RevA.03"
    assert rep["natom"] == 3 and rep["icharg"] == 0 and rep["multip"] == 1
    assert rep["has_coords"] and rep["has_basis"] and rep["has_mo"]
    assert rep["job_ok"] is True
    assert "Internal force constants" in body["raw"]  # 未识别行 raw 恒透传
    assert_contract_schema(spec, "post",
                           "/history/{id}/analysis/chkchk", 200, body)


def test_verdict_unreadable_truncated_fixture(home):
    """截断反例（134 + 错误行无锚点）→ verdict=unreadable（体检恒 200）。"""
    eid = seed()
    chkchk_replay(home / "g16", F_UNREADABLE, 134)
    r = client.post(f"/api/v1/history/{eid}/analysis/chkchk")
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "unreadable"
    assert body["report"]["natom"] is None and body["report"]["job_ok"] is False
    assert "Illegal range for read" in body["raw"]


def test_verdict_corrupted_anchored_fixture(home):
    """badroute 类（134 + NAtoms= 锚点）→ verdict=corrupted（按锚点分流）。"""
    eid = seed()
    chkchk_replay(home / "g16", F_CORRUPTED, 134)
    r = client.post(f"/api/v1/history/{eid}/analysis/chkchk")
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "corrupted"
    assert body["report"]["natom"] == 0  # 合成损坏样例锚点行在 stdout
    assert "NAtoms=" in body["raw"]


def test_verdict_multistep_job_ok(home):
    """多步成功行与单步并存识别（job_ok 两形态）。"""
    eid = seed()
    chkchk_replay(home / "g16", F_MULTISTEP, 0)
    r = client.post(f"/api/v1/history/{eid}/analysis/chkchk")
    assert r.status_code == 200
    assert r.json()["report"]["job_ok"] is True
    assert "multi-step" in r.json()["raw"]


def test_anchor_marks_unit():
    """_verdict 纯函数边界：退出 0 恒 ok；非零按锚点分流。"""
    assert chktools_svc._verdict(0, "") == "ok"
    assert chktools_svc._verdict(134, "NAtoms=      3") == "corrupted"
    assert chktools_svc._verdict(1, "Version: ES64L") == "corrupted"
    assert chktools_svc._verdict(134, "Illegal range for read") == "unreadable"
    assert chktools_svc._verdict(2, "") == "unreadable"


# ---------------- 对象口径与资产闸（404/409/503/502） ----------------

def test_non_terminal_states_404(home):
    """skipped/running（非终态）/不存在一律 404（chk 工具域口径，
    不沿用 analysis 域 409）。"""
    chkchk_replay(home / "g16", F_HEALTHY, 0)
    skipped = seed(state="skipped", with_chk=False)
    assert client.post(
        f"/api/v1/history/{skipped}/analysis/chkchk").status_code == 404
    assert client.post(
        f"/api/v1/history/{skipped}/analysis/fchk").status_code == 404
    assert client.get(
        f"/api/v1/history/{skipped}/analysis/fchk").status_code == 404
    missing = 99999
    assert client.post(
        f"/api/v1/history/{missing}/analysis/chkchk").status_code == 404
    tid = tasks().create_candidate("x.gjf", "imported")
    running = executions().create(task_id=tid, filename="x.gjf",
                                  resources={"nproc": {"value": 1, "defaulted": True},
                                             "mem_gb": {"value": 1.0, "defaulted": True}})
    assert client.post(
        f"/api/v1/history/{running}/analysis/chkchk").status_code == 404


def test_chk_asset_missing_409_cleaned_vs_undeclared(home):
    """无资产 409：有 %chk= 声明 → cleaned；无声明 → undeclared。"""
    chkchk_replay(home / "g16", F_HEALTHY, 0)
    cleaned = seed(with_chk=False)  # 声明了但文件已清理
    r = client.post(f"/api/v1/history/{cleaned}/analysis/chkchk")
    assert r.status_code == 409
    body = r.json()["error"]
    assert body["code"] == "CHK_ASSET_UNAVAILABLE"
    assert body["details"]["reason"] == "cleaned"

    undeclared = seed(with_chk=False, chk_decl="")
    r = client.post(f"/api/v1/history/{undeclared}/analysis/chkchk")
    assert r.status_code == 409
    assert r.json()["error"]["details"]["reason"] == "undeclared"


def test_chk_asset_path_outside(home):
    """containment 越界三形态：绝对路径 / .. / symlink 逃逸 → 409
    path_outside，越界文件内容不读取（假 chkchk 未被调用）。"""
    marker = home / "tool-ran"
    chkchk_replay(home / "g16", F_HEALTHY, 0)
    make_tool(home / "g16", "chkchk",
              f'echo ran > "{marker}"\nexit 0\n')
    outside = home / "outside.chk"
    outside.write_bytes(b"secret")
    outside_dot = home / "run" / "outside.chk"  # `..` 相对 run/<eid> 上一级
    outside_dot.write_bytes(b"secret-dot")

    abs_eid = seed(chk_decl=f"%chk={outside}")  # 绝对路径越界
    r = client.post(f"/api/v1/history/{abs_eid}/analysis/chkchk")
    assert r.status_code == 409
    assert r.json()["error"]["details"]["reason"] == "path_outside"

    dot_eid = seed(chk_decl="%chk=../outside.chk")  # .. 越出 run/<eid>
    r = client.post(f"/api/v1/history/{dot_eid}/analysis/chkchk")
    assert r.status_code == 409
    assert r.json()["error"]["details"]["reason"] == "path_outside"

    sym_eid = seed()
    run_d = config.HOME_DIR / "run" / str(sym_eid)
    (run_d / "input.chk").unlink()
    (run_d / "link.chk").symlink_to(outside)  # symlink 逃逸
    (run_d / "input.gjf").write_text("%chk=link.chk\n#p hf/sto-3g\n\n\n0 1\nO\n",
                                     encoding="utf-8")
    r = client.post(f"/api/v1/history/{sym_eid}/analysis/chkchk")
    assert r.status_code == 409
    assert r.json()["error"]["details"]["reason"] == "path_outside"

    assert not marker.exists()  # 越界资产一律不读取（工具未被调用）


def test_tool_missing_503(home):
    """g16_root 无 chkchk/formchk（空目录摘除场景）→ 503
    G16_TOOL_UNAVAILABLE（details.tool 区分）。"""
    eid = seed()
    r = client.post(f"/api/v1/history/{eid}/analysis/chkchk")
    assert r.status_code == 503
    body = r.json()["error"]
    assert body["code"] == "G16_TOOL_UNAVAILABLE"
    assert body["details"]["tool"] == "chkchk"

    eid2 = seed()
    chkchk_replay(home / "g16", F_HEALTHY, 0)  # chkchk 在、formchk 缺
    r = client.post(f"/api/v1/history/{eid2}/analysis/fchk")
    assert r.status_code == 503
    assert r.json()["error"]["details"]["tool"] == "formchk"


def test_tool_timeout_502(home, monkeypatch):
    """chkchk 超时 → 502 G16_TOOL_FAILED（reason=timeout）。"""
    monkeypatch.setattr(chktools_svc, "CHKCHK_TIMEOUT_S", 0.2)
    eid = seed()
    make_tool(home / "g16", "chkchk", "sleep 5\n")
    r = client.post(f"/api/v1/history/{eid}/analysis/chkchk")
    assert r.status_code == 502
    body = r.json()["error"]
    assert body["code"] == "G16_TOOL_FAILED"
    assert body["details"]["tool"] == "chkchk"
    assert body["details"]["reason"] == "timeout"


def test_tool_startup_failure_502(home):
    """可执行位在但非可执行格式（exec 失败 OSError）→ 502
    （reason=startup；core dump 隔离同范式）。"""
    eid = seed()
    bad = home / "g16" / "chkchk"
    bad.write_bytes(b"\x00not-an-executable")
    bad.chmod(0o755)
    r = client.post(f"/api/v1/history/{eid}/analysis/chkchk")
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "G16_TOOL_FAILED"


def test_core_dump_cwd_isolation(home, monkeypatch):
    """损坏输入 SIGABRT + core dump 落 cwd——调用 cwd 断言为独立临时
    目录（非 run 目录/工作区根）。"""
    record = home / "cwd-record.txt"
    monkeypatch.setenv("CHK_CWD_RECORD", str(record))
    eid = seed()
    make_tool(home / "g16", "chkchk",
              'echo "$PWD" > "$CHK_CWD_RECORD"\nexit 134\n')
    client.post(f"/api/v1/history/{eid}/analysis/chkchk")
    recorded = Path(record.read_text(encoding="utf-8").strip())
    run_d = (config.HOME_DIR / "run" / str(eid)).resolve()
    assert recorded != run_d
    assert config.HOME_DIR.resolve() not in recorded.parents
    assert recorded.parent == Path(tempfile.gettempdir()).resolve()
    assert recorded.name.startswith("hq-chkchk-")  # TemporaryDirectory 形态
    # 请求结束后临时目录随清理消亡（core dump 一并带走）——目录不存在
    assert not recorded.exists()


def test_snapshot_source_untouched(home):
    """快照复制断言：调用前后源 chk 哈希与 mtime 前后一致（读清竞态
    防护——体检消费快照，不触源文件）。"""
    eid = seed()
    asset = config.HOME_DIR / "run" / str(eid) / "input.chk"
    before_hash = hashlib.sha256(asset.read_bytes()).hexdigest()
    before_mtime = asset.stat().st_mtime_ns
    chkchk_replay(home / "g16", F_HEALTHY, 0)
    client.post(f"/api/v1/history/{eid}/analysis/chkchk")
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == before_hash
    assert asset.stat().st_mtime_ns == before_mtime


def test_protected_chk_failed_entry(home):
    """failed 条目 protected/ 保全 chk 体检与转换可用。"""
    eid = seed(state="failed", protected=True)
    chkchk_replay(home / "g16", F_HEALTHY, 0)
    r = client.post(f"/api/v1/history/{eid}/analysis/chkchk")
    assert r.status_code == 200
    assert r.json()["verdict"] == "ok"

    make_tool(home / "g16", "formchk",
              f'cat > "$2" <<\'EOF\'\n{FCHK_GOOD}EOF\n')
    r = client.post(f"/api/v1/history/{eid}/analysis/fchk")
    assert r.status_code == 200
    assert r.json() == {"generated": True, "fchk": "input.fchk"}
    assert finalize.fchk_head_valid(
        config.HOME_DIR / "run" / str(eid) / "input.fchk")


def test_archived_entry_same_access(home):
    """归档条目体检/转换同口径放行（只读消费）。"""
    eid = seed()
    history_svc.archive(eid)
    chkchk_replay(home / "g16", F_HEALTHY, 0)
    assert client.post(
        f"/api/v1/history/{eid}/analysis/chkchk").status_code == 200


# ---------------- 手动转换（幂等 / 前置闸 / 原子落盘 / 下载） ----------------

def make_formchk_ok(root: Path) -> None:
    make_tool(root, "formchk",
              f'cat > "$2" <<\'EOF\'\n{FCHK_GOOD}EOF\n')


def test_convert_idempotent_hit_ignores_asset_and_tools(home):
    """有效 fchk 在场 → generated=false 幂等命中：chk 已清理仍命中、
    不跑体检不跑 formchk（无 chkchk 可执行也不 503）。"""
    eid = seed(with_chk=False)  # chk 已清理
    put_fchk(eid, FCHK_GOOD.encode())
    r = client.post(f"/api/v1/history/{eid}/analysis/fchk")
    assert r.status_code == 200
    assert r.json() == {"generated": False, "fchk": "input.fchk"}


def test_halfmade_fchk_not_hit_and_reconvertible(home):
    """半成品 fchk（非空无锚点/空文件）不判命中：健康 chk 在场可重转。"""
    eid = seed()
    put_fchk(eid, b"partial garbage without anchors")  # 超时残留形态
    chkchk_replay(home / "g16", F_HEALTHY, 0)
    make_formchk_ok(home / "g16")
    r = client.post(f"/api/v1/history/{eid}/analysis/fchk")
    assert r.status_code == 200
    assert r.json()["generated"] is True
    assert finalize.fchk_head_valid(
        config.HOME_DIR / "run" / str(eid) / "input.fchk")

    eid2 = seed()
    put_fchk(eid2, b"")  # 空文件形态
    chkchk_replay(home / "g16", F_HEALTHY, 0)
    make_formchk_ok(home / "g16")
    assert client.post(
        f"/api/v1/history/{eid2}/analysis/fchk").json()["generated"] is True


def test_convert_precheck_gate_409(home):
    """前置体检闸：verdict≠ok 409（details.verdict 区分
    corrupted/unreadable），formchk 不被调用。"""
    marker = home / "formchk-ran"
    chkchk_replay(home / "g16", F_CORRUPTED, 134)
    make_tool(home / "g16", "formchk", f'echo ran > "{marker}"\n')
    eid = seed()
    r = client.post(f"/api/v1/history/{eid}/analysis/fchk")
    assert r.status_code == 409
    body = r.json()["error"]
    assert body["code"] == "CHK_ASSET_UNAVAILABLE"
    assert body["details"]["verdict"] == "corrupted"
    assert not marker.exists()

    chkchk_replay(home / "g16", F_UNREADABLE, 134)
    eid2 = seed()
    r = client.post(f"/api/v1/history/{eid2}/analysis/fchk")
    assert r.status_code == 409
    assert r.json()["error"]["details"]["verdict"] == "unreadable"


def test_convert_formchk_failure_502_and_atomic(home):
    """formchk 非零退出 → 502 FCHK_GENERATION_FAILED（stderr 尾部）；
    原子落盘：失败/无锚点产物无 .tmp 残留、目标文件不落半成品。"""
    chkchk_replay(home / "g16", F_HEALTHY, 0)
    eid = seed()
    make_tool(home / "g16", "formchk", 'echo boom >&2\nexit 3\n')
    r = client.post(f"/api/v1/history/{eid}/analysis/fchk")
    assert r.status_code == 502
    body = r.json()["error"]
    assert body["code"] == "FCHK_GENERATION_FAILED"
    assert body["details"]["reason"] == "nonzero"
    assert "boom" in body["details"]["stderr_tail"]
    run_d = config.HOME_DIR / "run" / str(eid)
    assert not (run_d / "input.fchk").exists()
    assert not list(run_d.glob(".input.fchk.*.tmp"))  # 无半成品残留

    # 产物空 → empty；产物无锚点 → no_anchor；两条均 502 且无残留
    make_tool(home / "g16", "formchk", 'touch "$2"\n')
    eid2 = seed()
    r = client.post(f"/api/v1/history/{eid2}/analysis/fchk")
    assert r.status_code == 502
    assert r.json()["error"]["details"]["reason"] == "empty"

    make_tool(home / "g16", "formchk", 'echo garbage > "$2"\n')
    eid3 = seed()
    r = client.post(f"/api/v1/history/{eid3}/analysis/fchk")
    assert r.status_code == 502
    assert r.json()["error"]["details"]["reason"] == "no_anchor"
    assert not list((config.HOME_DIR / "run" / str(eid3)).glob(
        ".input.fchk.*.tmp"))


def test_convert_formchk_timeout_502(home, monkeypatch):
    """formchk 超时（手动 300s 预算，测试注入短超时）→ 502 且无残留。"""
    monkeypatch.setattr(chktools_svc, "FORMCHK_TIMEOUT_S", 0.2)
    chkchk_replay(home / "g16", F_HEALTHY, 0)
    eid = seed()
    make_tool(home / "g16", "formchk", "sleep 5\n")
    r = client.post(f"/api/v1/history/{eid}/analysis/fchk")
    assert r.status_code == 502
    body = r.json()["error"]
    assert body["code"] == "FCHK_GENERATION_FAILED"
    assert body["details"]["reason"] == "timeout"
    run_d = config.HOME_DIR / "run" / str(eid)
    assert not list(run_d.glob(".input.fchk.*.tmp"))


def test_fchk_download_rfc5987_and_404(home):
    """下载：RFC 5987 中文 stem 原样 + ASCII fallback 清洗（清洗为空回落
    execution-<id>）；缺失 404；流式 application/octet-stream。"""
    eid = seed(filename="水分子优化.gjf")
    put_fchk(eid, FCHK_GOOD.encode())
    r = client.get(f"/api/v1/history/{eid}/analysis/fchk")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/octet-stream")
    disp = r.headers["content-disposition"]
    assert "filename=execution-" in disp  # 中文清洗为空 → 回落
    assert "filename*=UTF-8''" in disp
    from urllib.parse import unquote
    assert unquote(disp.split("''", 1)[1]) == "水分子优化.fchk"
    assert r.content == FCHK_GOOD.encode()

    eid2 = seed(filename="h2o opt 2.gjf")  # 含空格 stem → 归并 "_"
    put_fchk(eid2, FCHK_GOOD.encode())
    disp2 = client.get(
        f"/api/v1/history/{eid2}/analysis/fchk").headers["content-disposition"]
    assert "filename=h2o_opt_2.fchk" in disp2

    eid3 = seed()
    assert client.get(
        f"/api/v1/history/{eid3}/analysis/fchk").status_code == 404


def test_convert_success_no_tmp_residue(home):
    """转换成功路径 os.replace 原子性：无 .tmp 残留、目标完整。"""
    eid = seed()
    chkchk_replay(home / "g16", F_HEALTHY, 0)
    make_formchk_ok(home / "g16")
    r = client.post(f"/api/v1/history/{eid}/analysis/fchk")
    assert r.status_code == 200
    run_d = config.HOME_DIR / "run" / str(eid)
    assert not list(run_d.glob(".input.fchk.*.tmp"))
    assert finalize.fchk_head_valid(run_d / "input.fchk")


# ---------------- 共用原子落盘 helper（make_fchk 自动物化回归） ----------------

def test_make_fchk_atomic_regression(home, tmp_path):
    """make_fchk 共用 helper 回归：成功产物头部锚点在位；失败（非零
    退出/无锚点产物）无半成品残留、返回 None（不阻断终态管线）。"""
    run_d = config.HOME_DIR / "run" / "1"
    run_d.mkdir(parents=True, exist_ok=True)
    (run_d / "input.chk").write_bytes(b"fake-chk")
    (run_d / "input.gjf").write_text("%chk=input.chk\n#p hf/sto-3g\n",
                                     encoding="utf-8")
    root = home / "g16"

    make_formchk_ok(root)
    out = finalize.make_fchk(run_d, root)
    assert out is not None and finalize.fchk_head_valid(out)
    assert not list(run_d.glob(".input.fchk.*.tmp"))

    make_tool(root, "formchk", 'exit 9\n')
    assert finalize.make_fchk(run_d, root) is None
    assert not list(run_d.glob(".input.fchk.*.tmp"))

    make_tool(root, "formchk", 'echo no-anchor > "$2"\n')
    assert finalize.make_fchk(run_d, root) is None
    assert not list(run_d.glob(".input.fchk.*.tmp"))

    assert finalize.make_fchk(config.HOME_DIR / "run" / "999", root) is None


def test_fchk_head_valid_unit(tmp_path):
    """fchk_head_valid 边界：空/缺失/无锚点非空/半锚点均不判命中。"""
    p = tmp_path / "x.fchk"
    assert not finalize.fchk_head_valid(p)  # 缺失
    p.write_bytes(b"")
    assert not finalize.fchk_head_valid(p)  # 空
    p.write_bytes(b"garbage")
    assert not finalize.fchk_head_valid(p)  # 非空无锚点
    p.write_bytes(b"Number of atoms only")
    assert not finalize.fchk_head_valid(p)  # 半锚点
    p.write_bytes(FCHK_GOOD.encode())
    assert finalize.fchk_head_valid(p)
