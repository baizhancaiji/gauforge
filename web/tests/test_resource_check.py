"""声明资源校验测试（3.9.0 资源校验波 C2/C3，resident-resource-fix-plan
§4.3/§4.4）。

- 提交链阻断（C2，权威）：核数超/内存超/双超三分 422 RESOURCE_OVERCOMMIT、
  恰好等于放行（严格大于）、缺省注入超限同拦（message 加注按缺省值补齐）、
  失败不写盘（规范化写回被拦）、message 前缀任务名、details
  declared/available/exceeded、层 b 不触发（只比配置总量）；
- 四通道琥珀警告（C3，非阻断）：导入响应 / 预览 / 分块保存 / 列表徽标
  warning_count 同走 file_warnings 单点；分块保存放行（超限声明可暂存，
  提交时把关）；line 取超限维度声明行、缺省注入加注。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.src import config
from web.src.errors import ApiError
from web.src.main import app
from web.src.routers.candidates import submit_candidate
from web.src.services.candidates import import_files, save_block, warning_count
from web.src.services.verify import verify_and_store
from web.src.store import settings

client = TestClient(app)

OVER_BOTH = (  # 双超样板：4 核 8GB（沙箱可用资源收紧到 2 核 / 4 GB）
    "%mem=8GB\n"
    "%nprocshared=4\n"
    "#p opt freq b3lyp/6-31g(d)\n"
    "\n"
    "水分子示例\n"
    "\n"
    "0 1\n"
    "O 0.0 0.0 0.0\n"
    "H 0.96 0.0 0.0\n"
    "\n"
)


@pytest.fixture()
def ind(tmp_path, monkeypatch) -> Path:
    """工作区隔离（沿 test_submit_verify 先例）：HOME_DIR 指向 tmp。"""
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    d = tmp_path / "inputs"
    d.mkdir()
    return d


def _mk(ind: Path, text: str, name: str = "a.gjf") -> int:
    (out,) = import_files([(name, text.encode("utf-8"))], inputs_dir=ind)
    return out["id"]


def _tighten(cores: int = 2, mem: float = 4) -> None:
    settings().set("available_cpu_cores", cores)
    settings().set("available_mem_gb", mem)


def _resource_warnings(warnings: list[dict]) -> list[dict]:
    return [w for w in warnings if w["kind"] == "resource_over_available"]


# ---------------- 提交链阻断（C2） ----------------

def test_cores_over_blocked(ind):
    """核数超 → 422 RESOURCE_OVERCOMMIT：message 前缀任务名并含超限维度、
    details exceeded=[nproc]、输入副本未写回（失败不写盘——L9 未终止形态
    经 422 后仍无终止空行）。"""
    _tighten(cores=2, mem=64)
    text = "%nprocshared=4\n%mem=2GB\n#p opt\n\nt\n\n0 1\nO 0 0 0\nH 0 0 0.9\n"
    tid = _mk(ind, text, name="cores.gjf")
    before = (ind / str(tid)).read_bytes()
    with pytest.raises(ApiError) as ei:
        submit_candidate(tid, None)
    body = ei.value.body()["error"]
    assert body["code"] == "RESOURCE_OVERCOMMIT"
    assert body["message"].startswith("任务 cores.gjf：声明资源超过可用资源")
    assert "核数 4 > 可用 2" in body["message"]
    assert "内存" not in body["message"]  # 单维度超限只列该维
    assert body["details"]["exceeded"] == ["nproc"]
    assert body["details"]["declared"] == {"nproc": 4, "mem_gb": 2.0}
    assert body["details"]["available"] == {"cpu_cores": 2, "mem_gb": 64.0}
    assert (ind / str(tid)).read_bytes() == before  # 未写回（含未补终止空行）


def test_mem_over_blocked(ind):
    """内存超 → 422：exceeded=[mem_gb]、message 含内存维度。"""
    _tighten(cores=64, mem=4)
    tid = _mk(ind, OVER_BOTH, name="mem.gjf")
    with pytest.raises(ApiError) as ei:
        verify_and_store(tid)
    body = ei.value.body()["error"]
    assert body["code"] == "RESOURCE_OVERCOMMIT"
    assert body["details"]["exceeded"] == ["mem_gb"]
    assert "内存 8 GB > 可用 4 GB" in body["message"]
    assert "核数" not in body["message"]


def test_both_over_blocked(ind):
    """双超 → 422：exceeded 两维齐、message 以「 / 」连接两维度。"""
    _tighten(cores=2, mem=4)
    tid = _mk(ind, OVER_BOTH, name="both.gjf")
    with pytest.raises(ApiError) as ei:
        verify_and_store(tid)
    body = ei.value.body()["error"]
    assert body["details"]["exceeded"] == ["nproc", "mem_gb"]
    assert "核数 4 > 可用 2 / 内存 8 GB > 可用 4 GB" in body["message"]


def test_equal_values_pass(ind):
    """恰好等于不拦（严格大于）：可用 = 声明 → 提交放行入席，响应无
    资源琥珀警告。"""
    _tighten(cores=4, mem=8)
    tid = _mk(ind, OVER_BOTH, name="equal.gjf")
    out = submit_candidate(tid, None)
    assert out["seat_id"] >= 1
    assert _resource_warnings(out["warnings"]) == []


def test_default_injection_over_blocked_with_note(ind):
    """缺省注入超限同拦：无 %nproc/%mem 声明、可用收紧到 1 核 / 1 GB →
    缺省（4 核 / 8GB）被拦，message 加注「（按缺省值补齐）」。"""
    _tighten(cores=1, mem=1)
    tid = _mk(ind, "#p opt\n\nt\n\n0 1\nO 0 0 0\n\n", name="def.gjf")
    with pytest.raises(ApiError) as ei:
        verify_and_store(tid)
    body = ei.value.body()["error"]
    assert body["code"] == "RESOURCE_OVERCOMMIT"
    assert body["details"]["declared"] == {"nproc": 4, "mem_gb": 8.0}
    assert "（按缺省值补齐）" in body["message"]


def test_layer_b_not_triggered(ind):
    """层 b 不触发（§4.5）：声明 ≤ 配置总量即放行——不扣减在跑占用，
    「声明 ≤ 总量但 > 空闲」由队列窗口停等与 HQ 排队自持。"""
    _tighten(cores=16, mem=64)
    tid = _mk(ind, OVER_BOTH, name="idle.gjf")
    out = verify_and_store(tid)
    assert _resource_warnings(out["warnings"]) == []
    assert out["normalized"] is False


# ---------------- 四通道琥珀警告（C3，非阻断） ----------------

def test_amber_warning_four_channels(ind):
    """四通道同走 file_warnings 单点：导入响应 / 预览 / 分块保存 / 列表
    徽标 warning_count 均产出 resource_over_available；分块保存放行
    （非阻断——超限声明可暂存）。"""
    _tighten(cores=2, mem=4)
    # ① 导入通道：响应 warnings 携带琥珀警告（line = %nprocshared 声明行 2）
    (out,) = import_files([("amber.gjf", OVER_BOTH.encode("utf-8"))],
                          inputs_dir=ind)
    tid = out["id"]
    (w,) = _resource_warnings(out["warnings"])
    assert w["line"] == 2  # %nprocshared 声明行（核数维度优先；%mem 在第 1 行）
    assert w["keyword"] == "%nproc"
    # ② 预览通道
    r = client.get(f"/api/v1/candidates/{tid}/preview")
    assert r.status_code == 200
    (wp,) = _resource_warnings(r.json()["warnings"])
    assert wp["line"] == 2
    # ③ 分块保存通道：改写 link0 仍超限 → 保存成功（放行）+ 琥珀警告在位
    saved = save_block(tid, "link0",
                       ["%mem=8GB", "%nprocshared=4"], inputs_dir=ind)
    (ws,) = _resource_warnings(saved["warnings"])
    assert "提交将被拒绝" in ws["message"]
    # ④ 列表徽标通道：warning_count 现算含琥珀警告
    assert warning_count(tid) >= 1


def test_amber_mem_only_line_takes_mem_decl(ind):
    """仅内存超限时 line 取 %mem 声明行、keyword=%mem。"""
    _tighten(cores=64, mem=4)
    (out,) = import_files([("memline.gjf", OVER_BOTH.encode("utf-8"))],
                          inputs_dir=ind)
    (w,) = _resource_warnings(out["warnings"])
    assert w["line"] == 1  # %mem 声明行（首行）
    assert w["keyword"] == "%mem"


def test_amber_defaulted_note(ind):
    """缺省注入超限的琥珀警告加注「（按缺省值补齐）」，指引调设置。"""
    _tighten(cores=1, mem=1)
    (out,) = import_files([("defamber.gjf", "#p opt\n\nt\n\n0 1\nO 0 0 0\n\n"
                            .encode("utf-8"))], inputs_dir=ind)
    (w,) = _resource_warnings(out["warnings"])
    assert "（按缺省值补齐）" in w["message"]
