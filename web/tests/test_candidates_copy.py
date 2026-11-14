"""copy_execution_input 单点直测（oldchk-duplicate-write-fix-plan §2.3 γ 收敛）。

执行副本取数为历史退回候选与队列移除分流共用的复制源单点：
- 物化明文依赖行（%oldchk=dep(-exec)?-<n>.chk，物化器私有名法）剥离——
  dep- 与 dep-exec- 两变体同剥；
- 用户明文 %oldchk= 行与 %chk= 行不受触碰（两槽不对称，§2.5）；
- 大小写敏感口径：物化器 _rewrite_line 前缀 casefold 恒产出小写 head，
  用户手写大写 dep 形态按用户槽保护不剥离；
- 无命中快路径原字节原样返回（回落分支逐字节不变，BOM/CRLF 原样）；
- 有命中时按行剥离重组，其余字节（含 CRLF）保持。
"""
from __future__ import annotations

from web.src import config
from web.src.services.candidates import copy_execution_input


def _set_home(tmp_path, monkeypatch) -> None:
    (tmp_path / "inputs").mkdir()
    (tmp_path / "run").mkdir()
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)


def test_strips_both_dep_variants_keeps_plaintext_and_chk(tmp_path,
                                                          monkeypatch):
    """dep- 与 dep-exec- 两变体剥离；用户明文 %oldchk= 行与 %chk= 行原样
    （剥离只及 %oldchk 槽的 dep 名法）。"""
    _set_home(tmp_path, monkeypatch)
    run_d = tmp_path / "run" / "7"
    run_d.mkdir(parents=True)
    (run_d / "input.gjf").write_bytes(
        b"%chk=dep-3.chk\n"
        b"%oldchk=D1_DgpC_Monomer_Opt.chk\n"
        b"%oldchk=dep-3.chk\n"
        b"%oldchk=dep-exec-42.chk\n"
        b"\n#p HF/6-31G(d)\n\n0 1\nO 0 0 0\n")
    data = copy_execution_input(7, 99)
    assert data == (b"%chk=dep-3.chk\n"
                    b"%oldchk=D1_DgpC_Monomer_Opt.chk\n"
                    b"\n#p HF/6-31G(d)\n\n0 1\nO 0 0 0\n")


def test_uppercase_dep_form_protected_as_user_slot(tmp_path, monkeypatch):
    """大小写敏感口径：大写 dep 形态非物化器产出，按用户槽保护不剥离。"""
    _set_home(tmp_path, monkeypatch)
    run_d = tmp_path / "run" / "8"
    run_d.mkdir(parents=True)
    raw = b"%oldchk=DEP-3.chk\n\n#p hf/6-31g(d)\n\n0 1\nO 0 0 0\n"
    (run_d / "input.gjf").write_bytes(raw)
    assert copy_execution_input(8, 99) == raw


def test_fallback_branch_bytes_unchanged_without_dep_lines(tmp_path,
                                                           monkeypatch):
    """回落分支（执行目录缺失）快路径逐字节不变：BOM 与 CRLF 原样。"""
    _set_home(tmp_path, monkeypatch)
    raw = (b"\xef\xbb\xbf%chk=w.chk\r\n\r\n#p HF/6-31G(d)\r\n\r\n"
           b"0 1\r\nO 0 0 0\r\n")
    (tmp_path / "inputs" / "99").write_bytes(raw)
    assert copy_execution_input(7, 99) == raw  # run/7 不存在 → 回落任务副本


def test_run_copy_dep_strip_keeps_crlf_of_surviving_lines(tmp_path,
                                                          monkeypatch):
    """有命中时按行剥离重组：存留行的 CRLF 字节原样保持。"""
    _set_home(tmp_path, monkeypatch)
    run_d = tmp_path / "run" / "9"
    run_d.mkdir(parents=True)
    (run_d / "input.gjf").write_bytes(
        b"%oldchk=dep-3.chk\r\n%chk=w.chk\r\n\r\n#p HF/6-31G(d)\r\n")
    data = copy_execution_input(9, 99)
    assert data == b"%chk=w.chk\r\n\r\n#p HF/6-31G(d)\r\n"


def test_run_copy_without_oldchk_fast_path_bytes_unchanged(tmp_path,
                                                           monkeypatch):
    """执行副本无 %oldchk 行：快路径预筛直返原字节（含非 UTF-8 字节序列
    也不因剥离解码改写）。"""
    _set_home(tmp_path, monkeypatch)
    run_d = tmp_path / "run" / "10"
    run_d.mkdir(parents=True)
    raw = b"%mem=1GB\xff\xfe\n#p hf/sto-3g\n\nt\n\n0 1\nO\n"
    (run_d / "input.gjf").write_bytes(raw)
    assert copy_execution_input(10, 99) == raw
