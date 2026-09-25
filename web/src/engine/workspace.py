"""执行工作区：run/<id>/ 物化、Link0 补齐换算、g16 子进程环境（m1-plan §4.3 B6）。

- 物化：输入副本（含补齐行）写入 run/<执行id>/input.gjf，哈希对拷贝内容计算；
- Link0：解析 %NProcShared/%Mem，缺失项按运行级设置缺省注入（value+defaulted
  记入执行记录，roadmap §2.6）；%Mem 已声明时按 G16 单位（KB/MB/GB/TB、
  W/MW/QW，1024 进制、word=8B）换算为 GB 供资源记账；
- g16 环境：按 roadmap §2.5 实测结论等价构造（GAUSS_EXEDIR/GAUSS_BSDDIR/
  G16BASIS/GAUSS_ARCHDIR/GAUSS_LEXEDIR + 库与可执行搜索路径），不 source
  profile 文件；每次执行强制 GAUSS_SCRDIR=run/<执行id>/。
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def run_dir(root: Path, execution_id: int) -> Path:
    return root / str(execution_id)


def content_hash(text: str) -> str:
    """执行内容哈希（契约格式 sha256:<hex>，对补齐后实际执行副本计算）。"""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------- Link0 解析与补齐 ----------------

_MEM_TO_GB = {"kb": 1 / 1024 / 1024, "mb": 1 / 1024, "gb": 1.0, "tb": 1024.0,
              "w": 8 / 1024**3, "mw": 8 * 1024 / 1024**3,
              "qw": 8 * 1024**2 / 1024**3}


def _mem_to_gb(raw: str) -> float | None:
    """G16 %Mem 值 → GB 浮点；无法识别返回 None。"""
    tok = raw.strip().upper()
    for unit in ("QW", "MW", "KW", "TB", "GB", "MB", "KB", "W"):
        if tok.endswith(unit):
            try:
                return float(tok[: -len(unit)]) * _MEM_TO_GB[unit.lower()]
            except ValueError:
                return None
    return None


def _fmt_gb(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def _cpu_list_count(raw: str) -> int | None:
    """%CPU proc-list → 核数：单项 3、列表 0,2,4、区间 0-5 及混合均可
    （gaussian.com/run，绑定具体逻辑处理器）；无法识别返回 None。"""
    total = 0
    for tok in raw.replace(" ", "").split(","):
        if not tok:
            return None
        lo, sep, hi = tok.partition("-")
        try:
            a = int(lo)
            b = int(hi) if sep else a
        except ValueError:
            return None
        if b < a:
            return None
        total += b - a + 1
    return total or None


def resolve_link0(text: str, nproc_default: int,
                  mem_gb_default: float) -> dict:
    """解析 Link0 区 → 声明资源 + 补齐后的实际执行文本。

    返回 {"completed_text", "nproc": {value, defaulted}, "mem_gb": {…}}；
    缺失/不可识别的 %NProcShared/%Mem 按运行级设置缺省值注入（defaulted=True）。
    核资源两类声明并行不混同：%nproc 系给分配核数（%nproc 前缀超集，判定依据
    见 parse/blocks.py），%CPU 给具体逻辑处理器（不注入 %NProcShared，会与
    核位绑定冲突）；记账核数优先取 %nproc，仅 %CPU 时取 proc-list 推导值。
    """
    lines = text.replace("\r\n", "\n").split("\n")
    # Link 0 = 前导空行/注释后的连续 % 行（与 parse/blocks 同规则，其后无空行要求）
    i, n = 0, len(lines)
    while i < n and (not lines[i].strip() or lines[i].lstrip().startswith("!")):
        i += 1
    start = i
    while i < n and lines[i].lstrip().startswith("%"):
        i += 1
    end = i  # [start, end) 为 Link0 行区间

    nproc: int | None = None
    cpu_count: int | None = None
    mem_gb: float | None = None
    for ln in lines[start:end]:
        body = ln.strip().lstrip("%")
        key, _, val = body.partition("=")
        k = key.strip().casefold()
        if k.startswith("nproc"):
            try:
                nproc = int(val.strip())
            except ValueError:
                pass
        elif k == "cpu":
            cpu_count = _cpu_list_count(val)
        elif k == "mem":
            mem_gb = _mem_to_gb(val)

    declared = nproc if nproc is not None else cpu_count
    inject: list[str] = []
    nproc_defaulted = declared is None
    if nproc_defaulted:
        declared = int(nproc_default)
        inject.append(f"%NProcShared={declared}")
    mem_defaulted = mem_gb is None
    if mem_defaulted:
        mem_gb = float(mem_gb_default)
        inject.append(f"%Mem={_fmt_gb(mem_gb)}GB")

    completed = "\n".join(lines[:end] + inject + lines[end:])
    return {"completed_text": completed,
            "nproc": {"value": declared, "defaulted": nproc_defaulted},
            "mem_gb": {"value": mem_gb, "defaulted": mem_defaulted}}


# ---------------- 物化与环境 ----------------

def materialize(root: Path, execution_id: int, completed_text: str,
                g16_root: Path, *, env_base: dict | None = None) -> tuple[Path, dict]:
    """物化 run/<id>/：input.gjf（补齐后实际执行副本）+ g16 子进程环境。

    返回 (run_dir, env)；GAUSS_SCRDIR 强制指向 run/<id>/。
    """
    d = run_dir(root, execution_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "input.gjf").write_text(completed_text, encoding="utf-8")
    return d, g16_env(g16_root, d, base=env_base)


def g16_env(g16_root: Path, scratch: Path,
            base: dict | None = None) -> dict:
    """等价 source <g16_root>/bsd/g16.profile 的子进程环境（roadmap §2.5）。

    g16root 布局：<root>=…/g16，主程序 <root>/g16、formchk 同目录。
    """
    env = dict(base if base is not None else os.environ)
    root = str(g16_root)
    env["GAUSS_EXEDIR"] = ":".join([f"{root}/bsd", f"{root}/private/bsd", root])
    env["GAUSS_BSDDIR"] = f"{root}/bsd"
    env["G16BASIS"] = f"{root}/basis"
    env["GAUSS_ARCHDIR"] = f"{root}/arch"
    env["GAUSS_LEXEDIR"] = f"{root}/lexus"
    env["GAUSS_SCRDIR"] = str(scratch)  # 每次执行强制，不沿用全局 scratch
    env["PATH"] = f"{root}/bsd:{root}:" + env.get("PATH", "")
    env["LD_LIBRARY_PATH"] = f"{root}/bsd:" + env.get("LD_LIBRARY_PATH", "")
    return env
