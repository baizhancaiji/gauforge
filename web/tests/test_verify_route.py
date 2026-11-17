"""testrt 提交链阻断测试（3.8.0 工具箱 B14，toolbox-plan §5
test_verify_route）。

- 三支判定：QPErr → 422 ROUTE_SYNTAX_INVALID（message 以「route 语法
  错误：」起始并入报错原文首段 + details.route_errors 原文与 exit_code）；
  退出 0 通过；非零无 QPErr → 降级黄警（异常退出）；
- 合法形态零 422：! 行内注释（截断后送检）、@mols.dat / @mols.dat/3
  （包含文件写法降级且不调 testrt——哨兵断言）、引号值
  External="RunTink Amber" 原样保留、多行合并单行；
- 降级五类原因各一例（message 中文短语锚点：testrt 工具缺失 / 调用失败 /
  校验超时 / 异常退出 / 包含文件写法），黄警不阻断提交；
- 调用 cwd 临时目录隔离断言（core dump 落临时目录，非工作区）；
- 提交路径回归：受控注入（conftest _controlled_testrt）下
  test_submit_verify / test_e2e_fake_g16 / test_e2e_queue_lifecycle
  零回归（全量闸门承载），本文件断言降级黄警在三路径响应中的形状。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from web.src import config
from web.src.errors import ApiError
from web.src.services import verify as verify_svc
from web.src.services.candidates import import_files
from web.src.services.verify import verify_and_store, _strip_inline_comments

pytestmark = pytest.mark.usefixtures("home")


@pytest.fixture
def home(tmp_path, monkeypatch):
    """本文件最小隔离：工作区根指向 tmp（inputs 落 tmp/inputs）。"""
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    return tmp_path


def _mk(text: str, name: str = "a.gjf") -> int:
    (out,) = import_files([(name, text.encode("utf-8"))],
                          inputs_dir=config.HOME_DIR / "inputs")
    return out["id"]


def install_testrt(monkeypatch, script: str) -> Path:
    """用例层覆写受控缝：自造 testrt 脚本（固定 stdout/退出码）。"""
    fake = Path(tempfile.mkdtemp(prefix="hq-testrt-case-")) / "testrt"
    fake.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setattr(verify_svc, "_testrt_path", lambda: fake)
    return fake


SIMPLE_ROUTE = "%mem=1GB\n%nprocshared=4\n#p hf/sto-3g\n\n水\n\n0 1\nO 0 0 0\n"


def _wrap(route_body: str) -> str:
    return f"%mem=1GB\n%nprocshared=4\n{route_body}\n\n水\n\n0 1\nO 0 0 0\n\n"


# ---------------- 三支判定 ----------------

def test_qperr_blocks_with_422(monkeypatch):
    """QPErr 锚点 → 422 ROUTE_SYNTAX_INVALID：message 并入报错原文首段
    （「route 语法错误：」起始）+ details.route_errors 原文与 exit_code。"""
    install_testrt(monkeypatch,
                   'echo " QPErr --- A syntax error detected."\n'
                   'echo " Last state= \\"GCL\\""\nexit 134\n')
    tid = _mk(_wrap("#p b3lypxyz/6-31g(d)"))
    with pytest.raises(ApiError) as ei:
        verify_and_store(tid)
    body = ei.value.body()["error"]
    assert body["code"] == "ROUTE_SYNTAX_INVALID"
    assert body["message"].startswith("route 语法错误：")
    assert "QPErr" in body["message"]
    assert len(body["message"]) <= 300 + len("route 语法错误：")
    assert "QPErr" in body["details"]["route_errors"]
    assert body["details"]["exit_code"] == 134
    assert body["details"]["task_id"] == tid


def test_exit_zero_passes_silently(monkeypatch):
    """退出 0 → 通过（不回显 link 展开序列、零新增警告）。"""
    install_testrt(monkeypatch,
                   'echo "link sequence echo would go here"\nexit 0\n')
    tid = _mk(_wrap("#p hf/sto-3g"))
    out = verify_and_store(tid)
    assert out["normalized"] is False
    assert out["warnings"] == []


def test_nonzero_without_qperr_degrades(monkeypatch):
    """非零退出无 QPErr → 降级黄警（异常退出），提交不阻断。"""
    install_testrt(monkeypatch, 'echo "segfault-ish"\nexit 2\n')
    tid = _mk(_wrap("#p hf/sto-3g"))
    out = verify_and_store(tid)
    assert out["normalized"] is False
    (w,) = out["warnings"]
    assert w["kind"] == "route_check_skipped"
    assert w["line"] == 3  # route 节起始行号
    assert w["keyword"] == ""
    assert "route 语法校验跳过（异常退出）" in w["message"]


# ---------------- 合法形态零 422 ----------------

def test_inline_comment_stripped_before_testrt(monkeypatch):
    """! 行内注释截断后送检（原文直送实测 134 QPErr，核验项 1）——
    假 testrt 断言收到的实参已剥注释。"""
    workdir = Path(tempfile.mkdtemp(prefix="hq-testrt-args-"))
    shim = workdir / "testrt"
    shim.write_text('#!/bin/sh\nprintf "%s\\n" "$1" > "%s"\nexit 0\n'
                    % ("$1", workdir / "args.txt"), encoding="utf-8")
    shim.chmod(0o755)
    monkeypatch.setattr(verify_svc, "_testrt_path", lambda: shim)
    tid = _mk(_wrap("#p hf/sto-3g ! FAKE: exit=1"))
    assert verify_and_store(tid)["warnings"] == []
    sent = (workdir / "args.txt").read_text(encoding="utf-8").strip()
    assert sent == "#p hf/sto-3g"  # 注释已剥、多行合并单行


def test_multiline_and_quoted_value_merged(monkeypatch):
    """多行合并单行 + 引号值原样保留（External="RunTink Amber" 不拆词）。"""
    install_testrt(monkeypatch, 'exit 0\n')
    tid = _mk(_wrap('#p external="RunTink Amber"\nhf/sto-3g'))
    assert verify_and_store(tid)["warnings"] == []


def test_strip_inline_comments_unit():
    """_strip_inline_comments 纯函数边界：引号内 ! 保留、引号外截断。"""
    assert _strip_inline_comments("#p hf/sto-3g ! note") == "#p hf/sto-3g"
    assert (_strip_inline_comments('#p external="a!b" hf')
            == '#p external="a!b" hf')
    assert _strip_inline_comments("#p opt\nfreq\nscrf=(solvent=water)") == \
        "#p opt freq scrf=(solvent=water)"
    # 行内空白不归一（strip 仅去两端；合并以行内 strip 后原文连接）
    assert _strip_inline_comments("#p hf\tfreq") == "#p hf\tfreq"


# ---------------- @file 包含形态分流 ----------------

def test_include_forms_degrade_without_invoking(monkeypatch):
    """@file / @file/N → 包含文件写法降级且不调 testrt（哨兵断言）。"""
    sentinel = Path(tempfile.mkdtemp(prefix="hq-testrt-sent-")) / "ran"
    install_testrt(monkeypatch, f'echo ran > "{sentinel}"\nexit 0\n')
    for route in ("#p @mols.dat", "#p @mols.dat/3 hf/sto-3g"):
        tid = _mk(_wrap(route))
        out = verify_and_store(tid)
        (w,) = out["warnings"]
        assert w["kind"] == "route_check_skipped"
        assert "route 语法校验跳过（包含文件写法）" in w["message"]
    assert not sentinel.exists()  # 分流不调 testrt


# ---------------- 降级五类原因各一例 ----------------

def test_degrade_tool_missing(monkeypatch):
    """可执行缺失 → 降级（testrt 工具缺失），不发子进程。"""
    missing = Path(tempfile.mkdtemp(prefix="hq-testrt-none-")) / "absent"
    monkeypatch.setattr(verify_svc, "_testrt_path", lambda: missing)
    tid = _mk(_wrap("#p hf/sto-3g"))
    (w,) = verify_and_store(tid)["warnings"]
    assert "route 语法校验跳过（testrt 工具缺失）" in w["message"]


def test_degrade_startup_oserror(monkeypatch):
    """可执行位在但格式非法（exec OSError）→ 降级（调用失败）。"""
    bad = Path(tempfile.mkdtemp(prefix="hq-testrt-bad-")) / "testrt"
    bad.write_bytes(b"\x00garbage")
    bad.chmod(0o755)
    monkeypatch.setattr(verify_svc, "_testrt_path", lambda: bad)
    tid = _mk(_wrap("#p hf/sto-3g"))
    (w,) = verify_and_store(tid)["warnings"]
    assert "route 语法校验跳过（调用失败）" in w["message"]


def test_degrade_timeout(monkeypatch):
    """超时 → 降级（校验超时）；注入短超时避免真等待。"""
    install_testrt(monkeypatch, "sleep 5\n")
    monkeypatch.setattr(verify_svc, "ROUTE_CHECK_TIMEOUT_S", 0.2)
    tid = _mk(_wrap("#p hf/sto-3g"))
    (w,) = verify_and_store(tid)["warnings"]
    assert "route 语法校验跳过（校验超时）" in w["message"]


# ---------------- 调用 cwd 临时目录隔离 ----------------

def test_invocation_cwd_is_tempdir(monkeypatch):
    """core dump 隔离断言：调用 cwd 为独立临时目录（非工作区/inputs）。"""
    record = Path(tempfile.mkdtemp(prefix="hq-testrt-rec-")) / "cwd.txt"
    shim = Path(tempfile.mkdtemp(prefix="hq-testrt-cwd-")) / "testrt"
    shim.write_text('#!/bin/sh\necho "$PWD" > "%s"\nexit 0\n' % record,
                    encoding="utf-8")
    shim.chmod(0o755)
    monkeypatch.setattr(verify_svc, "_testrt_path", lambda: shim)
    tid = _mk(_wrap("#p hf/sto-3g"))
    assert verify_and_store(tid)["warnings"] == []
    cwd = Path(record.read_text(encoding="utf-8").strip())
    inputs_d = (config.HOME_DIR / "inputs").resolve()
    assert cwd != inputs_d
    assert inputs_d not in cwd.parents
    assert cwd.name.startswith("hq-testrt-")  # TemporaryDirectory 形态
    assert not cwd.exists()  # 调用结束随清理消亡（core 一并带走）


# ---------------- 提交路径降级警形状（非阻断语义） ----------------

def test_submit_path_warning_not_blocking(monkeypatch):
    """降级黄警随提交成功响应返回（行内提交路径，submit 链同源
    verify_and_store）：kind/line/keyword 形状完整、不阻断。"""
    missing = Path(tempfile.mkdtemp(prefix="hq-testrt-none2-")) / "absent"
    monkeypatch.setattr(verify_svc, "_testrt_path", lambda: missing)
    tid = _mk(_wrap("#p hf/sto-3g"))
    out = verify_and_store(tid)
    assert out["normalized"] is False  # 提交核验通过（黄警不阻断）
    (w,) = out["warnings"]
    assert set(w) >= {"line", "keyword", "kind", "message"}
    assert w["kind"] == "route_check_skipped"
    assert isinstance(w["line"], int) and w["line"] >= 1


def test_route_line_number_multiline_link0(monkeypatch):
    """line = route 节起始行号（规范化文本上：Link0 两行、route 第 3 行；
    警告行号按规范化后文本计算，与拼写警同口径）。"""
    monkeypatch.setattr(verify_svc, "_testrt_path",
                        lambda: Path("/nonexistent/testrt"))
    text = ("%mem=1GB\n%nprocshared=4\n#p @mols.dat\n\n水\n\n0 1\n"
            "O 0 0 0\n\n")
    tid = _mk(text)
    (w,) = verify_and_store(tid)["warnings"]
    assert w["line"] == 3
