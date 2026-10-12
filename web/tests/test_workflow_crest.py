"""CREST 任务类型与组合流测试（M4 B10，m4-plan §4.7/§5 test_workflow_crest）。

覆盖：crest 任务派发适配（程序/输入物化/资源仅 cpus/不进解析管道）、
可执行缺失 503、提交席位满员 409 零副作用（无 workflow 行）、来源候选
形态校验（WORKFLOW_STATE_INVALID）、top_n∈[2,10]、构象数边界（<2 记
failed 不生成队列、2≤n<top_n 取 min）、提取器样例回归（A5 fixtures 喂入
+ 相对能量交叉验证 + 交叉验证不符拒绝）、top-N 队列生成与自动提交（含
满员保留 unsubmitted + refine_queue_pending）、crest 失败 workflow 记
failed、启动对账 workflow 重推幂等（锚判重/队列判重）。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from web.src import config
from web.src.engine import Dispatcher, FakeGateway
from web.src.engine.crest import CrestExtractError, extract_ensemble
from web.src.errors import ApiError
from web.src.services.candidates import import_files
from web.src.services import workflows as wf_svc
from web.src.store import executions, queues, seats, settings, tasks, workflows
from web.src.routers.workflows import submit_conformer_refinement

CAND = ("%chk=c.chk\n%nprocshared=2\n"
        "#p opt b3lyp/6-31g(d)\n\n乙醇\n\n0 1\n"
        "C 0.87 -0.29 -0.01\n"
        "C -0.54 0.29 0.04\n"
        "O -1.37 -0.44 -0.52\n"
        "H 1.55 0.35 -0.43\n"
        "H 1.23 -0.56 0.99\n"
        "H 0.90 -1.15 -0.65\n"
        "H -0.36 1.26 -0.34\n"
        "H -0.61 0.44 1.10\n"
        "H -2.17 0.01 -0.02\n\n")
NATOM = 9
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "crest"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    settings().set("g16_root", str(tmp_path / "g16"))
    return tmp_path


def _mk_candidate() -> int:
    (out,) = import_files([("ethanol.gjf", CAND.encode("utf-8"))],
                          inputs_dir=config.HOME_DIR / "inputs")
    return out["id"]


def _payload(candidate_id: int, **over) -> dict:
    p = {"candidate_id": candidate_id,
         "crest": {"nproc": 2, "top_n": 2},
         "template": {"route": "b3lyp/6-31g(d) opt", "link0": None}}
    p.update(over)
    return p


def _set_crest_root(tmp_path, name: str = "crest-ok") -> Path:
    root = tmp_path / f"crest-root-{name}"
    root.mkdir(exist_ok=True)
    (root / "crest").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (root / "crest").chmod(0o755)
    # 经设置目录校验路径登记（审查 P1-1/P2-6 整改）：既往 settings().set
    # 直写绕过目录白名单，crest_root 未登记曾逃逸全部闸门（真实部署
    # PUT /settings 422 unknown_setting、组合流整体不可用）
    assert settings().apply_update({"crest_root": str(root)}) == []
    return root


# ---------------- 提交前置检查 ----------------

def test_submit_rejects_missing_executable(tmp_path):
    assert settings().apply_update(
        {"crest_root": str(tmp_path / "nope")}) == []
    cid = _mk_candidate()
    with pytest.raises(ApiError) as ei:
        wf_svc.submit_conformer_refinement(_payload(cid))
    assert ei.value.code == "CREST_EXECUTABLE_MISSING"
    assert ei.value.http == 503
    assert workflows().list() == []  # 零副作用


def test_submit_rejects_when_seats_full(tmp_path):
    _set_crest_root(tmp_path)
    cid = _mk_candidate()
    settings().set("pending_seat_limit", 1)
    sid = seats().append(kind="task", task_id=tasks().create_candidate(
        "filler.gjf", "imported"))
    with pytest.raises(ApiError) as ei:
        wf_svc.submit_conformer_refinement(_payload(cid))
    assert ei.value.code == "PENDING_CAPACITY_FULL"
    assert ei.value.http == 409
    assert workflows().list() == []  # 整体拒绝零副作用（无 workflow 行）


def test_submit_rejects_non_candidate_source(tmp_path):
    _set_crest_root(tmp_path)
    cid = _mk_candidate()
    tasks().to_seat_task(cid)  # 已提交形态
    with pytest.raises(ApiError) as ei:
        wf_svc.submit_conformer_refinement(_payload(cid))
    assert ei.value.code == "WORKFLOW_STATE_INVALID"
    assert ei.value.details["form"] == "seat_task"


@pytest.mark.parametrize("top_n", [1, 11])
def test_submit_rejects_top_n_out_of_range(tmp_path, top_n):
    _set_crest_root(tmp_path)
    cid = _mk_candidate()
    with pytest.raises(ApiError) as ei:
        wf_svc.submit_conformer_refinement(_payload(cid, crest={"nproc": 2,
                                                         "top_n": top_n}))
    assert ei.value.code == "VALIDATION_FAILED"


def test_submit_creates_crest_task_and_workflow(tmp_path):
    _set_crest_root(tmp_path)
    cid = _mk_candidate()
    out = wf_svc.submit_conformer_refinement(_payload(cid))
    assert out["state"] == "crest_running"
    wf = workflows().get(out["workflow_id"])
    assert wf["source_candidate_id"] == cid
    assert wf["top_n"] == 2
    assert wf["refine_queue_pending"] is False
    task = tasks().get(out["crest_task_id"])
    assert task["kind"] == "g16" or task["kind"] == "crest"
    assert task["workflow_id"] == out["workflow_id"]
    assert task["crest_nproc"] == 2
    # crest 引导 xyz 已程序化生成
    text = (config.HOME_DIR / "inputs" / str(out["crest_task_id"])
            ).read_text(encoding="utf-8")
    assert text.split("\n")[0] == "9"


# ---------------- 派发适配 ----------------

def test_crest_dispatch_adapter(tmp_path):
    """crest 任务派发：程序=<crest_root>/crest、输入物化 crest_input.xyz、
    资源仅 cpus、环境不注 GAUSS_*。"""
    _set_crest_root(tmp_path)
    cid = _mk_candidate()
    out = wf_svc.submit_conformer_refinement(_payload(cid))
    rec: list = []
    gw = FakeGateway(cpus=8)
    disp = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    disp.advance()
    sub = gw.submitted[0]
    assert sub["command"][0].endswith("/crest")
    assert sub["command"][1:] == ["crest_input.xyz", "-T", "2"]
    assert sub["resources"] == {"cpus": 2}  # mem 不声明
    assert "env" in sub
    run_d = Path(sub["cwd"])
    assert (run_d / "crest_input.xyz").is_file()
    assert not (run_d / "input.gjf").is_file()
    eid_row = executions().list_by_task(out["crest_task_id"])[-1]
    assert eid_row["state"] == "running"
    # crest 任务终态 succeeded：不进 cclib 管道（无 analysis.json）
    (run_d / "crest_conformers.xyz").write_text(
        "1\nx\nC 0 0 0\n")  # 产物占位（构象数不足走 failed 分支）
    wf_svc.on_crest_terminal(disp, executions().get(eid_row["id"]),
                             "failed")
    wf = workflows().get(out["workflow_id"])
    assert wf["state"] == "failed"  # crest 失败：workflow 记 failed
    assert wf["refine_queue_id"] is None


# ---------------- 提取器样例回归 ----------------

def test_extractor_on_fixture():
    """A5 留存样例（乙醇 4 构象）喂入：条目数/能量锚点/升序。"""
    ens = extract_ensemble(FIXTURES)
    assert ens["n"] == 4
    energies = [c["energy_hartree"] for c in ens["conformers"]]
    assert energies == sorted(energies)
    assert len(ens["conformers"][0]["coords"]) == NATOM
    # 相对能量物理基准（交叉验证已内置；最低行 0 由 B11 聚合计算）
    from web.src.engine.crest import HARTREE_KJ_MOL
    assert abs(HARTREE_KJ_MOL - 2625.4996) < 1e-6


def test_extractor_missing_anchor(tmp_path):
    d = tmp_path / "empty-run"
    d.mkdir()
    with pytest.raises(CrestExtractError):
        extract_ensemble(d)


def test_extractor_crosscheck_mismatch(tmp_path):
    """crest.energies 相对列与坐标注释行不一致 → 锚点漂移拒绝。"""
    d = tmp_path / "run-x"
    d.mkdir()
    xyz = "9\n-11.39433939\n" + ("C 0 0 0\n" * 9)
    (d / "crest_conformers.xyz").write_text(xyz, encoding="utf-8")
    (d / "crest.energies").write_text("  1         9.999\n", encoding="utf-8")
    with pytest.raises(CrestExtractError):
        extract_ensemble(d)


# ---------------- 终态钩子链 ----------------

def _crest_done_with_ensemble(tmp_path, n_conf: int, top_n: int = 2):
    """驱动到「crest succeeded + ensemble 已落 run 目录」的现场。"""
    _set_crest_root(tmp_path)
    cid = _mk_candidate()
    out = wf_svc.submit_conformer_refinement(_payload(
        cid, crest={"nproc": 2, "top_n": top_n}))
    rec: list = []
    gw = FakeGateway(cpus=8)
    disp = Dispatcher(gw, emitter=lambda e, d: rec.append((e, d)))
    disp.advance()  # crest 派发
    row = executions().list_by_task(out["crest_task_id"])[-1]
    run_d = config.HOME_DIR / "run" / str(row["id"])
    coords = "\n".join("C 0.1 0.2 0.3" for _ in range(NATOM))
    xyz = "".join(f"{NATOM}\n{-11.39 - i * 0.001:.10f}\n{coords}\n"
                  for i in range(n_conf))
    (run_d / "crest_conformers.xyz").write_text(xyz, encoding="utf-8")
    return out, disp, gw, row, run_d


def test_hook_below_2_fails(tmp_path):
    out, disp, gw, row, run_d = _crest_done_with_ensemble(tmp_path, n_conf=1)
    wf_svc.on_crest_terminal(disp, executions().get(row["id"]), "succeeded")
    wf = workflows().get(out["workflow_id"])
    assert wf["state"] == "failed"  # 构象数 <2 记 failed
    assert wf["refine_queue_id"] is None  # 不生成精修队列


def test_hook_builds_queue_and_submits(tmp_path):
    """crest succeeded → top-N 队列自动生成并提交（N=min(top_n, n)）。"""
    out, disp, gw, row, run_d = _crest_done_with_ensemble(tmp_path, n_conf=4)
    wf_svc.on_crest_terminal(disp, executions().get(row["id"]), "succeeded")
    wf = workflows().get(out["workflow_id"])
    assert wf["state"] == "refining"
    qid = wf["refine_queue_id"]
    assert qid is not None and wf["refine_queue_pending"] is False
    members = tasks().list_queue_members(qid)
    assert len(members) == 2  # min(top_n=2, n=4)
    assert queues().get(qid)["state"] == "submitted"  # 自动提交（一个按钮语义）
    # 锚文件落盘（重入判据）
    assert (run_d / "crest_ensemble.json").is_file()
    # 成员输入含构象坐标 + 模板 route，必过核验
    m0 = (config.HOME_DIR / "inputs" / str(members[0]["id"])
          ).read_text(encoding="utf-8")
    assert "# b3lyp/6-31g(d) opt" in m0


def test_hook_partial_min_top_n(tmp_path):
    """2 ≤ n < top_n：取 min（成队数=实际构象数）。"""
    out, disp, gw, row, run_d = _crest_done_with_ensemble(tmp_path, n_conf=3,
                                                          top_n=4)
    wf_svc.on_crest_terminal(disp, executions().get(row["id"]), "succeeded")
    wf = workflows().get(out["workflow_id"])
    members = tasks().list_queue_members(wf["refine_queue_id"])
    assert len(members) == 3


def test_hook_capacity_full_keeps_unsubmitted(tmp_path):
    """自动提交满员（crest 仍占席）：队列保留 unsubmitted + refine_queue_pending。"""
    out, disp, gw, row, run_d = _crest_done_with_ensemble(tmp_path, n_conf=4)
    settings().set("pending_seat_limit", 1)  # crest 自身席位已占满
    wf_svc.on_crest_terminal(disp, executions().get(row["id"]), "succeeded")
    wf = workflows().get(out["workflow_id"])
    assert wf["state"] == "refining"
    assert wf["refine_queue_pending"] is True
    assert queues().get(wf["refine_queue_id"])["state"] == "unsubmitted"  # 保留待手动提交
    assert seats().count() == 1  # 席位未被占用（队列未入席）


def test_hook_idempotent_on_reentry(tmp_path):
    """钩子重入幂等：锚判重（不再提取）+ 队列判重（不重建不重复提交）。"""
    out, disp, gw, row, run_d = _crest_done_with_ensemble(tmp_path, n_conf=4)
    wf_svc.on_crest_terminal(disp, executions().get(row["id"]), "succeeded")
    wf1 = workflows().get(out["workflow_id"])
    n_tasks = len(tasks().list_by_workflow(out['workflow_id']))
    # 重入（模拟对账重推）：不重复建队/提交
    wf_svc.on_crest_terminal(disp, executions().get(row["id"]), "succeeded")
    wf2 = workflows().get(out["workflow_id"])
    assert wf2["refine_queue_id"] == wf1["refine_queue_id"]
    assert len(tasks().list_by_workflow(out['workflow_id'])) == n_tasks


def test_reconcile_pushes_pending_workflow(tmp_path):
    """启动对账 workflow 重推：crest_running + crest 执行已 succeeded →
    幂等钩子重推（钩子链中断恢复）。"""
    out, disp, gw, row, run_d = _crest_done_with_ensemble(tmp_path, n_conf=4)
    # 模拟钩子链中断：执行已终态 succeeded 但 workflow 仍 crest_running
    executions().finalize(execution_id=row["id"], state="succeeded",
                          finished_at="2026-10-12T12:00:00+08:00")
    assert workflows().get(out["workflow_id"])["state"] == "crest_running"
    # 清空席位现场（模拟重启后重新挂载）
    pushed = wf_svc.reconcile_workflows(disp)
    assert pushed == 1
    wf = workflows().get(out["workflow_id"])
    assert wf["state"] == "refining"
    assert wf["refine_queue_id"] is not None
    # 再跑一轮：已推进（refining）不再重推
    assert wf_svc.reconcile_workflows(disp) == 0


# ---------------- B11 能量表汇总与 workflow 查询 ----------------

TAIL = "#p HF/6-31G(d)\n\n水\n\n0 1\nO 0 0 0\nH 1 0.96\n\n"


def _mk_queue(members: list[int], skip_failed: bool = False) -> str:
    qid = "Q" + "".join(chr(65 + i) for i in range(5))
    queues().create(qid, name="t", skip_failed=skip_failed)
    for pos, tid in enumerate(members):
        tasks().enqueue(tid, qid, pos)
    seats().append(kind="queue", queue_id=qid)
    queues().set_state(qid, "submitted")
    return qid


def _mk(text: str, name: str) -> int:
    tid = tasks().create_candidate(name, "imported")
    (config.HOME_DIR / "inputs" / str(tid)).write_text(text, encoding="utf-8")
    return tid


def _succeed_with_analysis(task_id: int, hartree: float, method="b3lyp/6-31g(d)"):
    """succeeded 执行 + analysis.json（B1 落盘 SSOT 形状：result.summary
    嵌套、method 在 result 层——扁平夹具曾致缺陷③逃逸）。"""
    eid = executions().create(
        task_id=task_id, filename="x.gjf",
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}})
    run_d = config.HOME_DIR / "run" / str(eid)
    run_d.mkdir(parents=True)
    (run_d / "analysis.json").write_text(json.dumps({
        "result": {"method": method,
                   "summary": {"scf_energy_hartree": hartree,
                               "scf_energy_eV": hartree * 27.211386245988}},
    }), encoding="utf-8")
    executions().finalize(execution_id=eid, state="succeeded",
                          finished_at="2026-10-12T12:00:00+08:00")
    return eid


def test_queue_energy_summary_zero_point(tmp_path):
    """队列能量表：B1 解析取数 + 双单位同源换算 + 零点=行集最低（相对
    kJ/mol，最低行 0）。"""
    from web.src.services.energy import queue_energy_summary
    a = _mk("%chk=a.chk\n" + TAIL, "a.gjf")
    b = _mk("%chk=b.chk\n" + TAIL, "b.gjf")
    _mk_queue([a, b])
    _succeed_with_analysis(a, -231.0)
    _succeed_with_analysis(b, -230.5)
    out = queue_energy_summary(qid_of(a))
    rows = out["rows"]
    assert [r["task_id"] for r in rows] == [a, b]
    assert rows[0]["source"] == "analysis"
    assert rows[0]["energy_hartree"] == -231.0
    assert abs(rows[0]["energy_eV"] + 231.0 * 27.211386245988) < 1e-4
    assert rows[0]["relative_kJ_mol"] == 0.0  # 零点=最低
    expect = (-230.5 - -231.0) * 2625.4996
    assert abs(rows[1]["relative_kJ_mol"] - expect) < 1e-4


def qid_of(task_id: int) -> str:
    from web.src.store import tasks as t_store
    row = t_store().get(task_id)
    if row is None or not row.get("queue_id"):
        raise AssertionError(f"queue not found for task {task_id}")
    return row["queue_id"]


def test_queue_energy_partial_rows(tmp_path):
    """部分完成态：未成功成员 source=none、relative null；新增更低能量行
    时零点整体重算（接受漂移）。"""
    from web.src.services.energy import queue_energy_summary
    a = _mk("%chk=a.chk\n" + TAIL, "a.gjf")
    b = _mk("%chk=b.chk\n" + TAIL, "b.gjf")
    _mk_queue([a, b])
    _succeed_with_analysis(a, -231.0)  # b 无成功执行
    rows = queue_energy_summary(qid_of(a))["rows"]
    assert rows[0]["relative_kJ_mol"] == 0.0
    assert rows[1]["source"] == "none"
    assert rows[1]["relative_kJ_mol"] is None
    # b 新增更低能量执行 → a 的相对值随零点整体改写
    _succeed_with_analysis(b, -231.2)
    rows = queue_energy_summary(qid_of(a))["rows"]
    assert rows[1]["relative_kJ_mol"] == 0.0
    assert abs(rows[0]["relative_kJ_mol"] - 0.2 * 2625.4996) < 1e-4


def test_workflow_aggregation_mixed_rows(tmp_path):
    """workflow 跨容器聚合：crest 行（ensemble 代表）+ 精修队列 g16 行
    混排，零点跨容器；单点与列表端点同形。"""
    from web.src.routers.workflows import get_workflow, list_workflows
    out, disp, gw, row, run_d = _crest_done_with_ensemble(tmp_path, n_conf=4)
    wf_svc.on_crest_terminal(disp, executions().get(row["id"]), "succeeded")
    # 精修成员成功执行（能量高于 crest 最优构象 → crest 行为零点行）
    wf = workflows().get(out["workflow_id"])
    members = tasks().list_queue_members(wf["refine_queue_id"])
    _succeed_with_analysis(members[0]["id"], -11.39)
    _succeed_with_analysis(members[1]["id"], -11.20)
    view = get_workflow(out["workflow_id"])
    rows = view["energy_summary"]["rows"]
    kinds = [r["kind"] for r in rows]
    assert kinds.count("crest") == 1 and kinds.count("g16") == 2  # 混排
    crest_rows = [r for r in rows if r["kind"] == "crest"]
    g16_rows = [r for r in rows if r["kind"] == "g16"]
    assert len(crest_rows) == 1 and len(g16_rows) == 2
    assert crest_rows[0]["source"] == "ensemble"
    # crest ensemble 最低构象（-11.393）< 精修成员（-11.39/-11.20）→ 零点在 crest 行
    assert crest_rows[0]["relative_kJ_mol"] == 0.0
    assert view["state"] == "refining"
    assert view["refine_queue_id"] == wf["refine_queue_id"]
    # 列表端点同形
    lst = list_workflows(20)
    assert len(lst["workflows"]) == 1
    assert lst["workflows"][0]["workflow_id"] == out["workflow_id"]
    assert lst["workflows"][0]["energy_summary"]["rows"] == rows


def test_workflow_aggregation_after_queue_delete(tmp_path):
    """精修队列删除后：workflow 停留 refining、仅 crest 行可查（结果仍可查）。"""
    from web.src.routers.workflows import get_workflow
    out, disp, gw, row, run_d = _crest_done_with_ensemble(tmp_path, n_conf=4)
    wf_svc.on_crest_terminal(disp, executions().get(row["id"]), "succeeded")
    wf = workflows().get(out["workflow_id"])
    qid = wf["refine_queue_id"]
    # 删除精修队列（成员已建执行行 → detach_finished 路径）
    from web.src.services.queues import delete_queue
    delete_queue(qid)  # 分级处置：席位撤销 + 已执行成员只留历史
    view = get_workflow(out["workflow_id"])
    assert view["state"] == "refining"  # 不设放弃终态
    kinds = [r["kind"] for r in view["energy_summary"]["rows"]]
    assert kinds == ["crest"]  # 仅 crest 行，结果仍可查


# ---------------- 缺陷整改（P1/P3/P4）：completed 联动/提交响应/孤儿回收 ----------------

def _succeed_member(task_id: int) -> int:
    """成员成功执行行（无解析产物——completed 联动判定不依赖能量表）。"""
    eid = executions().create(
        task_id=task_id, filename="m.gjf",
        resources={"nproc": {"value": 1, "defaulted": False},
                   "mem_gb": {"value": 1, "defaulted": False}})
    (config.HOME_DIR / "run" / str(eid)).mkdir(parents=True)
    executions().finalize(execution_id=eid, state="succeeded",
                          finished_at="2026-10-12T12:00:00+08:00")
    return eid


def test_refine_queue_completion_completes_workflow(tmp_path):
    """P1：精修队列收束 completed → workflow 行联动 completed（§2.3
    终态判据落地——组合流 completed 经真实转移可达，非查询期派生）。"""
    out, disp, gw, row, run_d = _crest_done_with_ensemble(tmp_path, n_conf=4)
    wf_svc.on_crest_terminal(disp, executions().get(row["id"]), "succeeded")
    wid = out["workflow_id"]
    qid = workflows().get(wid)["refine_queue_id"]
    queues().set_state(qid, "executing")
    for m in tasks().list_queue_members(qid):
        _succeed_member(m["id"])
    disp._settle_queue_seat(qid)
    assert queues().get(qid)["state"] == "completed"
    assert workflows().get(wid)["state"] == "completed"


def test_reconcile_completes_refining_with_completed_queue(tmp_path):
    """P1 崩溃窗口收口：队列已 completed 而 workflow 未及推进（两写之间
    中断）→ 启动对账补记 completed。"""
    out, disp, gw, row, run_d = _crest_done_with_ensemble(tmp_path, n_conf=4)
    wf_svc.on_crest_terminal(disp, executions().get(row["id"]), "succeeded")
    wid = out["workflow_id"]
    qid = workflows().get(wid)["refine_queue_id"]
    queues().set_state(qid, "completed")  # 模拟收束后、联动写入前中断
    assert workflows().get(wid)["state"] == "refining"
    assert wf_svc.reconcile_workflows(disp) == 1
    assert workflows().get(wid)["state"] == "completed"


def test_submit_route_response_contract(tmp_path):
    """P3：提交响应 = 契约 ConformerRefinementResponse 四字段（与
    openapi/计划 §2.3 三方对齐；crest_execution_id 属 GET 单点响应）。"""
    _set_crest_root(tmp_path)
    cid = _mk_candidate()
    out = submit_conformer_refinement(_payload(cid))
    assert set(out) == {"workflow_id", "state", "crest_task_id", "seat_id"}
    assert out["state"] == "crest_running"


def test_hook_orphan_cleanup_on_validate_failure(tmp_path):
    """P4：建队中断（模板 link0 含 @task: 被成员校验拒绝）→ 半成品队列
    与成员回收、refine_queue_id 不落——对账重推不复制孤儿队列。"""
    out, disp, gw, row, run_d = _crest_done_with_ensemble(tmp_path, n_conf=4)
    wid = out["workflow_id"]
    wf_svc.save_template(wid, "b3lyp/6-31g(d) opt",
                         ["%OldChk=@task:99999"])  # 防御校验必拒的模板
    wf_svc.on_crest_terminal(disp, executions().get(row["id"]), "succeeded")
    wf = workflows().get(wid)
    assert wf["refine_queue_id"] is None
    assert wf["state"] == "crest_running"  # 钩子异常不阻断、保留重推入口
    assert queues().list() == []  # 半成品队列已回收
    # 修复模板后对账重推可干净建队（不复制孤儿）
    wf_svc.save_template(wid, "b3lyp/6-31g(d) opt", None)
    wf_svc.on_crest_terminal(disp, executions().get(row["id"]), "succeeded")
    wf2 = workflows().get(wid)
    assert wf2["refine_queue_id"] is not None
    assert len(tasks().list_queue_members(wf2["refine_queue_id"])) == 2


def test_draft_discard_tolerates_step_failure(tmp_path, monkeypatch):
    """N4：回收单步失败（如 tasks 行删除异常）仅记日志、不阻断后续回收
    ——队列行仍被删除，原异常不被回收异常替换。"""
    from web.src.store import TasksRepo
    qid = "RTEST1"
    queues().create(qid, name="t")
    tid = tasks().create_candidate("x.gjf", "imported")
    real_delete = TasksRepo.delete
    calls: list[int] = []

    def flaky_delete(self, task_id: int) -> None:
        calls.append(task_id)
        if len(calls) == 1:
            raise RuntimeError("simulated db failure")
        real_delete(self, task_id)

    monkeypatch.setattr(TasksRepo, "delete", flaky_delete)
    wf_svc._discard_refine_draft(qid, [tid, tid + 1])
    assert calls == [tid, tid + 1]  # 首步失败未阻断次步
    assert queues().get(qid) is None  # 队列行仍回收
