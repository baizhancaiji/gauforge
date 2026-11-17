"""chk 工具域服务（3.8.0 工具箱 B12，toolbox-plan §2.1/§4.2）：
chkchk 体检 + 手动 formchk 转换 + fchk 下载取数。

对象口径按端点分层（§2.1，chk 资产闸只作用需要 chk 的端点）：
- 体检：终态执行（succeeded/failed）且 chk 资产可得；
- 转换：终态执行；``input.fchk`` 有效成品幂等命中（不跑体检、不查
  chk 资产、不跑 formchk），需现转时要求 chk 资产可得且体检 verdict=ok
  （前置闸——体检失败不再转换，评估工具链 1 定位）；
- 下载：终态执行且 ``input.fchk`` 在场，不查 chk 资产（顶层 chk 被
  保留期清理后 fchk 仍可下载）。

调用范式沿 materialize 探针：源 chk 先复制进独立临时目录快照（读清
竞态防护——采集→调用间源文件被保留期清理/手动清理收走；chkchk 对损坏
输入 SIGABRT + core dump 落 cwd，临时目录隔离为硬约束，§9 风险 1/2）。
containment：chk 资产 realpath 必须位于 ``run/<id>/`` 之内（含
protected/），绝对路径/``..`` 越界一律不读取，409 ``path_outside``
（风险 15）。

verdict 三态按「非零退出 + stdout 锚点行」分流，不按退出码单判
（§0.5 实测：ok=退出 0；corrupted=非零且有锚点行（badroute 类
134 + ``NAtoms=``）；unreadable=非零且无任何锚点行（截断类 134 +
``Illegal range for read`` 等错误行））。最小锚点提取锁本机实测格式，
未识别行忽略的前向兼容（§9 风险 3）；``raw`` 恒透传 stdout 全文兜底。

归档条目同口径提供（与 3.7.0 导出批一致，均为只读消费）。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

from ..errors import err, not_found
from ..engine import finalize
from ..engine.workspace import g16_env, parse_chk_line
from ..store import executions, settings
from . import analysis as analysis_svc
from .dependencies import execution_chk_asset

CHKCHK_TIMEOUT_S = 120
FORMCHK_TIMEOUT_S = 300  # 手动转换较自动物化 120s 放宽（§2.1）

_TERMINAL = ("succeeded", "failed")  # skipped 无执行目录 → 404（§2.1）

# verdict 锚点标记（stdout 全文任意位置命中其一即「有锚点」；截断类
# 实测 stdout 仅 Illegal range/NtrErr 错误行不含任何标记，§0.5）
_ANCHOR_MARKS = ("Version:", "NAtoms=", "present.", "This checkpoint is from")

# 最小结构提取（锁本机实测格式；前向兼容——未识别行忽略不炸）
_NATOMS_RE = re.compile(
    r"NAtoms=\s*(\d+)\s+ICharg=\s*(-?\d+)\s+Multip=\s*(\d+)")
_PRESENT_MARKS = (
    ("has_coords", "Atomic coordinates present."),
    ("has_basis", "AO basis is present."),
    ("has_mo", "MO coefficients present."),
)
_JOB_OK_MARKS = (
    "This checkpoint is from a job which completed successfully.",
    "This checkpoint is from a step within a multi-step job which "
    "completed successfully.",
)

_FORMCHK_MESSAGES = {
    "nonzero": "formchk 非零退出",
    "empty": "formchk 产物为空",
    "no_anchor": "formchk 产物头部锚点缺失（半成品已丢弃，可重试转换）",
    "timeout": f"formchk 超时（>{FORMCHK_TIMEOUT_S}s）",
    "startup": "formchk 启动失败",
}

# 下载 ASCII fallback 白名单清洗（§2.1：保留 [A-Za-z0-9._-]，其余归并 "_"）
_ASCII_KEEP = re.compile(r"[^A-Za-z0-9._-]+")


def _g16_root() -> Path:
    return Path(str(settings().get("g16_root"))).expanduser()


def _terminal_row(execution_id: int) -> dict:
    """chk 工具域对象口径：终态 succeeded/failed。state ∉ 终态（含
    skipped）404——不沿用 analysis 域 terminal 判定，避免 skipped 落
    409（§2.1：跳过态无执行目录，前端不展示入口）。"""
    row = executions().get(execution_id)
    if row is None or row["state"] not in _TERMINAL:
        raise not_found("history", execution_id)
    return row


def _chk_unavailable(message: str, reason: str, execution_id: int) -> None:
    raise err("CHK_ASSET_UNAVAILABLE", message,
              {"reason": reason, "execution_id": execution_id}, http=409)


def _chk_asset(execution_id: int) -> Path:
    """chk 资产定位 + containment（§2.1/§9 风险 15）。

    无资产 409：reason=undeclared（输入未声明 %chk，G16 无声明不产
    chk）/ cleaned（有声明但文件已被保留期清理或移除）；资产 realpath
    越出 run/<id>/（含 protected/）409：reason=path_outside，一律不
    读取。"""
    run_d = analysis_svc.run_dir(execution_id)
    asset = execution_chk_asset(execution_id)
    if asset is None:
        try:
            text = (run_d / "input.gjf").read_text(encoding="utf-8",
                                                   errors="replace")
        except OSError:
            text = ""
        if parse_chk_line(text) is None:
            _chk_unavailable("无 chk 资产（输入未声明 %chk，未产生检查点"
                             "文件）", "undeclared", execution_id)
        _chk_unavailable("无 chk 资产（检查点文件已被保留期清理或移除）",
                         "cleaned", execution_id)
    real_asset = asset.resolve()
    real_run = run_d.resolve()
    if real_asset != real_run and real_run not in real_asset.parents:
        _chk_unavailable("chk 资产路径越界（%chk= 声明指向执行目录之外，"
                         "已拒绝读取）", "path_outside", execution_id)
    return asset


def _tool_or_503(g16_root: Path, tool: str) -> Path:
    """G16 发行工具可执行探测（os.access(X_OK) 沿 cube 先例）；缺失
    503 G16_TOOL_UNAVAILABLE（details.tool 区分，显式不静默）。"""
    path = g16_root / tool
    if not (path.is_file() and os.access(path, os.X_OK)):
        raise err("G16_TOOL_UNAVAILABLE",
                  f"{tool} 可执行探测失败（g16_root 配置或发行不完整）",
                  {"tool": tool, "g16_root": str(g16_root)}, http=503)
    return path


def _run_tool_snapshot(tool_path: Path, args: list[str], *, cwd: Path,
                       g16_root: Path,
                       timeout_s: int) -> tuple[str, int]:
    """临时目录隔离调用（损坏输入 SIGABRT + core dump 落 cwd——调用
    cwd 恒为独立临时目录；沿 materialize 探针范式）。返回 (stdout 文本,
    退出码)；启动失败/超时 502 G16_TOOL_FAILED（details.tool 区分）。"""
    try:
        proc = subprocess.run([str(tool_path), *args], cwd=str(cwd),
                              env=g16_env(g16_root, cwd),
                              capture_output=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise err("G16_TOOL_FAILED",
                  f"{tool_path.name} 超时（>{timeout_s}s）",
                  {"tool": tool_path.name, "reason": "timeout"},
                  http=502) from exc
    except OSError as exc:
        raise err("G16_TOOL_FAILED", f"{tool_path.name} 启动失败",
                  {"tool": tool_path.name, "reason": "startup"},
                  http=502) from exc
    return proc.stdout.decode(errors="replace"), proc.returncode


def _verdict(returncode: int, stdout: str) -> str:
    """三态判定（互斥完备覆盖全部退出形态，§2.1）：ok（退出 0）/
    corrupted（非零且有锚点行）/ unreadable（非零且无锚点行）。"""
    if returncode == 0:
        return "ok"
    anchored = any(mark in stdout for mark in _ANCHOR_MARKS)
    return "corrupted" if anchored else "unreadable"


def _extract(stdout: str) -> dict:
    """最小锚点提取（缺字段以 None 呈现、前端展示「—」；job_ok 两形态
    并存识别；版本差异新行忽略不炸，§9 风险 3）。"""
    report: dict = {"version": None, "natom": None, "icharg": None,
                    "multip": None, "has_coords": None, "has_basis": None,
                    "has_mo": None, "job_ok": False}
    for line in stdout.splitlines():
        if report["version"] is None and "Version:" in line:
            report["version"] = line.split("Version:", 1)[1].strip()
            continue
        m = _NATOMS_RE.search(line)
        if m is not None and report["natom"] is None:
            report["natom"] = int(m.group(1))
            report["icharg"] = int(m.group(2))
            report["multip"] = int(m.group(3))
            continue
        for key, mark in _PRESENT_MARKS:
            if line.strip().startswith(mark):
                report[key] = True
    report["job_ok"] = any(mark in stdout for mark in _JOB_OK_MARKS)
    return report


def run_chkchk(execution_id: int) -> dict:
    """POST /history/{id}/analysis/chkchk：体检（动作恒 200——损坏是
    有效结论；进程层失败才 502/503）。"""
    _terminal_row(execution_id)
    asset = _chk_asset(execution_id)
    g16_root = _g16_root()
    chkchk = _tool_or_503(g16_root, "chkchk")
    with tempfile.TemporaryDirectory(prefix="hq-chkchk-") as td:
        snap = Path(td) / asset.name
        shutil.copyfile(asset, snap)  # 快照（读清竞态防护，§9 风险 7）
        stdout, code = _run_tool_snapshot(chkchk, [str(snap)], cwd=Path(td),
                                          g16_root=g16_root,
                                          timeout_s=CHKCHK_TIMEOUT_S)
    return {"verdict": _verdict(code, stdout), "report": _extract(stdout),
            "raw": stdout}


def ensure_fchk(execution_id: int) -> tuple[Path, bool]:
    """转换核心单点（§2.1）：幂等优先 → chk 资产闸 → 前置体检闸 →
    formchk 原子落盘。返回 (fchk_path, generated)；领域异常（ApiError）
    由路由层透传，B17 批量作业按条目捕获、不复制转换逻辑。"""
    _terminal_row(execution_id)
    run_d = analysis_svc.run_dir(execution_id)
    fchk = run_d / "input.fchk"
    if finalize.fchk_head_valid(fchk):
        return fchk, False  # 幂等命中（不查 chk 资产、不跑工具）
    asset = _chk_asset(execution_id)
    g16_root = _g16_root()
    # 前置体检闸（内部先跑体检，不依赖前端先调；verdict≠ok 拒转换）
    check = run_chkchk(execution_id)
    if check["verdict"] != "ok":
        raise err("CHK_ASSET_UNAVAILABLE",
                  "chk 损坏/不完整，不执行转换",
                  {"verdict": check["verdict"],
                   "execution_id": execution_id}, http=409)
    formchk = _tool_or_503(g16_root, "formchk")
    with tempfile.TemporaryDirectory(prefix="hq-formchk-") as td:
        snap = Path(td) / asset.name
        shutil.copyfile(asset, snap)
        try:
            finalize.formchk_atomic(snap, fchk, g16_root, Path(td),
                                    timeout_s=FORMCHK_TIMEOUT_S)
        except finalize.FormchkError as exc:
            raise err("FCHK_GENERATION_FAILED",
                      _FORMCHK_MESSAGES[exc.reason],
                      {"reason": exc.reason,
                       "stderr_tail": exc.stderr_tail}, http=502) from exc
    return fchk, True


def fchk_download(execution_id: int) -> tuple[Path, dict[str, str]]:
    """下载取数：终态且 input.fchk 在场（不查 chk 资产），缺失 404。

    返回 (fchk_path, headers)——Content-Disposition 恒双文件名：
    filename=ASCII 清洗 fallback（白名单 [A-Za-z0-9._-]，清洗为空回落
    execution-<id>.fchk）+ filename*=UTF-8''<quote(stem + ".fchk")>
    （RFC 5987，中文 stem 原样保留；沿 history 输出下载既有 quote 形态
    并恒附带 fallback，服务端无法探测客户端能力，§2.1）。"""
    _terminal_row(execution_id)
    fchk = analysis_svc.run_dir(execution_id) / "input.fchk"
    if not fchk.is_file():
        raise not_found("fchk", "input.fchk")
    from .history import get_entry  # 延迟导入（history 依赖面大）
    name = get_entry(execution_id)["filename"]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    ascii_fallback = _ASCII_KEEP.sub("_", stem).strip("._-") or \
        f"execution-{execution_id}"
    headers = {"Content-Disposition":
               f"attachment; filename={ascii_fallback}.fchk; "
               f"filename*=UTF-8''{quote(stem + '.fchk')}"}
    return fchk, headers
