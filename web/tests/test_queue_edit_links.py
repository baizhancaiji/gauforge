"""C5 队列编辑模式「接续前置 chk」链路（审查 P1-2 整改）。

复现前端队列编辑框编辑既有队列时的精确调用序（HTTP 层）：GET preview
（取 Link0 基线）→ PUT blocks/link0（写 %OldChk=@task:<前驱>）→ 提交
（DAG 校验读输入放行）→ 复读 preview 断言落盘。

成员在编辑模式为 queue_member 形态：读/写守卫原仅放行候选与失败回退
队列（m2-plan §2.1 守卫矩阵），preview 404 / 保存 409 使勾选静默失效
（原生勾选视觉态、保存零落盘）——整改后 unsubmitted 队列成员可读、
link0 节可写（其余节仍锁定，守卫矩阵不回退）。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.main import app
from web.src.services.candidates import import_files

client = TestClient(app)

INPUT = ("%chk=c{n}.chk\n%nprocshared=2\n#p opt b3lyp/6-31g(d)\n\n"
         "t{n}\n\n0 1\nO 0 0 0\nH 1 0.96\n")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    (tmp_path / "g16").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    return tmp_path


def _import(n: int) -> int:
    (out,) = import_files([(f"t{n}.gjf", INPUT.format(n=n).encode("utf-8"))],
                          inputs_dir=config.HOME_DIR / "inputs")
    return out["id"]


def _mk_queue(n: int = 2) -> tuple[str, list[int]]:
    ids = [_import(i) for i in range(1, n + 1)]
    r = client.post("/api/v1/queues", json={"name": "编辑链路",
                                            "member_ids": ids,
                                            "skip_failed": False})
    assert r.status_code == 201, r.text
    return r.json()["id"], ids


def _link0_lines(tid: int) -> list[str]:
    """前端 loadLinkStates 同源取数（编辑模式成员 preview）。"""
    r = client.get(f"/api/v1/candidates/{tid}/preview")
    assert r.status_code == 200, r.text
    return r.json()["blocks"]["link0"]["lines"]


def test_edit_mode_link0_preview_readable():
    """编辑既有队列：queue_member 形态成员 preview 可读（原 404 使勾选
    available=false、静默失效）。"""
    _, ids = _mk_queue()
    assert _link0_lines(ids[1]) is not None


def test_edit_mode_oldchk_write_submit_reread():
    """编辑模式勾选→保存→复读断言：link0 写 %OldChk 落盘、队列提交放行、
    复读引用仍在（原缺陷：写路径 409/preview 404，勾选零落盘零提示）。"""
    qid, ids = _mk_queue()
    a, b = ids
    lines = _link0_lines(b)
    lines.append(f"%OldChk=@task:{a}")
    r = client.put(f"/api/v1/candidates/{b}/blocks/link0",
                   json={"lines": lines})
    assert r.status_code == 200, r.text
    # 复读断言（原缺陷：写路径守卫 409/preview 404，勾选零落盘）
    assert f"%OldChk=@task:{a}" in _link0_lines(b)
    # 提交（DAG 校验读输入：序前列引用放行；提交后成员锁定不可复读）
    r = client.post(f"/api/v1/queues/{qid}/submit")
    assert r.status_code == 200, r.text


def test_edit_mode_non_link0_section_still_locked():
    """守卫矩阵不回退：unsubmitted 队列成员仅 link0 节可写（C5 依赖行
    专用），其余节仍 QUEUE_MEMBER_LOCKED（m2-plan §2.1）。"""
    _, ids = _mk_queue()
    r = client.put(f"/api/v1/candidates/{ids[0]}/blocks/route",
                   json={"lines": ["#p hf/sto-3g"]})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "QUEUE_MEMBER_LOCKED"


def test_submitted_queue_member_locked_again():
    """提交后守卫复原：submitted 队列成员 preview 404、link0 写 409
    （勾选可编辑窗口止于 unsubmitted，与前端 linkEditable 同口径）。"""
    qid, ids = _mk_queue()
    r = client.post(f"/api/v1/queues/{qid}/submit")
    assert r.status_code == 200, r.text
    r = client.get(f"/api/v1/candidates/{ids[1]}/preview")
    assert r.status_code == 404
    r = client.put(f"/api/v1/candidates/{ids[1]}/blocks/link0",
                   json={"lines": [f"%OldChk=@task:{ids[0]}"]})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "QUEUE_MEMBER_LOCKED"
