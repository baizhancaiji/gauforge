"""执行工作区：run/<id>/ 物化、Link0 补齐换算、g16 子进程环境（m1-plan §4.3 B6）。

- 物化：输入副本（含补齐行）写入 run/<执行id>/input.gjf，哈希对拷贝内容计算；
- Link0：解析 %nprocshared/%mem，缺失项按运行级设置缺省注入（value+defaulted
  记入执行记录，roadmap §2.6）；%mem 已声明时按 G16 官方单位集（KB/MB/GB/
  TB/KW/MW/GW/TW，1024 进制、word=8B，B4 与值域同源下沉 parse/link0_rules）
  换算为 GB 供资源记账；
- g16 环境：按 roadmap §2.5 实测结论等价构造（GAUSS_EXEDIR/GAUSS_BSDDIR/
  G16BASIS/GAUSS_ARCHDIR/GAUSS_LEXEDIR + 库与可执行搜索路径），不 source
  profile 文件；每次执行强制 GAUSS_SCRDIR=run/<执行id>/。
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

_CHK_RE = re.compile(r"^%chk\s*=\s*(.+)$", re.IGNORECASE)


def run_dir(root: Path, execution_id: int) -> Path:
    return root / str(execution_id)


def content_hash(text: str) -> str:
    """执行内容哈希（契约格式 sha256:<hex>，对补齐后实际执行副本计算）。"""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------- Link0 解析与补齐 ----------------

def _link0_span_lines(lines: list[str]) -> tuple[int, int]:
    """Link0 区段行区间 [start, end)（入口为 CRLF 归一后的行列表；跳过
    前导空行/`!` 注释行、收连续 `%` 行；与 parse/blocks 同规则，其后无
    空行要求）。

    resolve_link0 与 parse_chk_line(link0_only=True)、services.dependencies.
    parse_link0_refs 三处共享单一来源，防区段口径漂移；入口收行列表
    使调用方各自 split 一次即复用，不重复归一同一文本（3.5.0 审查
    修复，原文本入口薄封装随调用方全量改行层移除）。"""
    i, n = 0, len(lines)
    while i < n and (not lines[i].strip() or lines[i].lstrip().startswith("!")):
        i += 1
    start = i
    while i < n and lines[i].lstrip().startswith("%"):
        i += 1
    return start, i


def _mem_to_gb(raw: str) -> float | None:
    """G16 %mem 值 → GB 浮点；无法识别返回 None。

    单位集与值域同源（parse/link0_rules，B4：QW 删除、GW/TW 补齐）。"""
    from ..parse.link0_rules import mem_to_gb
    return mem_to_gb(raw)


def _fmt_gb(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def _cpu_list_count(raw: str) -> int | None:
    """%cpu proc-list → 核数（薄封装：解析核心下沉 parse/link0_rules，
    B4 与值域/记账同源；区间步长 /n 后缀官方合法）。"""
    from ..parse.link0_rules import cpu_list_count
    return cpu_list_count(raw)


def resolve_link0(text: str, nproc_default: int,
                  mem_gb_default: float) -> dict:
    """解析 Link0 区 → 声明资源 + 补齐后的实际执行文本。

    返回 {"completed_text", "nproc": {value, defaulted}, "mem_gb": {…}}。
    补全口径（B9 用户裁决收窄，2026-10-21）：仅指令行**缺失**时注入缺省行
    ——%nproc 系（含 %cpu）行均不存在才注入 %nprocshared、%mem 行不存在才
    注入 %mem；指令存在但值非法（值域外/空值/非数值）时**不再注入**，非法
    输入不遮蔽（此前按缺失处置注入缺省、后值覆盖前值，会掩盖用户错误），
    核验警告 link0_value_invalid 已承载提示，运行结果交 G16 裁决。
    defaulted 语义 = 是否注入了缺省行；值非法未注入时记账值回落缺省
    （消费方 dispatcher 直接 int(value)，须数值安全）。
    核资源两类声明并行不混同：%nproc 系给分配核数（%nproc 前缀超集，判定依据
    见 parse/blocks.py），%cpu 给具体逻辑处理器（不注入 %nprocshared，会与
    核位绑定冲突）；记账核数优先取 %nproc，仅 %cpu 时取 proc-list 推导值。
    """
    lines = text.replace("\r\n", "\n").split("\n")
    # Link 0 = 前导空行/注释后的连续 % 行（与 parse/blocks 同规则，其后无空行要求）
    start, end = _link0_span_lines(lines)  # [start, end) 为 Link0 行区间

    has_nproc_line = False  # %nproc 系或 %cpu 任一行存在（声明即不注入）
    has_mem_line = False
    nproc: int | None = None
    cpu_count: int | None = None
    mem_gb: float | None = None
    for ln in lines[start:end]:
        body = ln.strip().lstrip("%")
        key, _, val = body.partition("=")
        k = key.strip().casefold()
        if k.startswith("nproc"):
            has_nproc_line = True
            try:
                nproc = int(val.strip())
            except ValueError:
                pass
        elif k == "cpu":
            has_nproc_line = True
            cpu_count = _cpu_list_count(val)
        elif k == "mem":
            has_mem_line = True
            mem_gb = _mem_to_gb(val)

    inject: list[str] = []
    if not has_nproc_line:
        nproc_value: int = int(nproc_default)
        nproc_defaulted = True
        inject.append(f"%nprocshared={nproc_value}")
    else:
        declared = nproc if nproc is not None else cpu_count
        # 行存在但值全部不可解析：记账回落缺省（不注入，defaulted=False）
        nproc_value = declared if declared is not None else int(nproc_default)
        nproc_defaulted = False
    if not has_mem_line:
        mem_value: float = float(mem_gb_default)
        mem_defaulted = True
        inject.append(f"%mem={_fmt_gb(mem_value)}GB")
    else:
        mem_value = mem_gb if mem_gb is not None else float(mem_gb_default)
        mem_defaulted = False

    completed = "\n".join(lines[:end] + inject + lines[end:])
    return {"completed_text": completed,
            "nproc": {"value": nproc_value, "defaulted": nproc_defaulted},
            "mem_gb": {"value": mem_value, "defaulted": mem_defaulted}}


# ---------------- chk 声明解析（3.5.0 自 finalize 下沉，单一事实来源） ----------------

def parse_chk_line(text: str, *, link0_only: bool = False) -> Path | None:
    """输入文本 Link0 `%chk=` 行声明值（纯函数，无 IO）。

    逐行 strip 后匹配取首个命中；声明值 strip 并剥首尾引号后 Path 化
    （无扩展名追加与 run 目录拼接均不在本函数：前者由 resolve_chk 拼接
    后按现状同序执行，后者为 resolve_chk 职责）。无声明返回 None——
    等价迁移的两形态（%chk 行不存在、%chk= 空值：正则 `(.+)` 不匹配空）；
    符号值（@task:/@exec:）返回非 None 的 Path（仅作「已声明」判据与
    物化定位输入，不作为真实产物路径使用）。

    link0_only=False（默认）全文逐行匹配，供 resolve_chk 作 find-source
    超集扫描；link0_only=True 仅扫 Link0 区（经 _link0_span_lines 与
    resolve_link0 同规则），供静态校验、物化文案判定与 fake_g16 对齐
    G16 只识别 Link0 命令的行为。多步放行（link1 B4）时本函数与
    resolve_chk、静态校验须同步改为末个声明段口径（见 link1-multistep-
    plan B4 补注）。无声明三形态语义自此齐备（3.5.0）：%chk 行不存在、
    %chk= 空值（正则不匹配空）、剥引号后为空（%chk="" 判空返回 None，
    消除 Path("") 透传派生错误路径）。
    """
    if link0_only:
        lines = text.replace("\r\n", "\n").split("\n")
        start, end = _link0_span_lines(lines)
        lines = lines[start:end]
    else:
        lines = text.splitlines()
    for ln in lines:
        m = _CHK_RE.match(ln.strip())
        if m:
            raw = m.group(1).strip().strip('"').strip("'")
            if not raw:  # %chk="" 空值引号形态视同无声明（3.5.0 行为修复）
                return None
            return Path(raw)
    return None


def resolve_chk(run_dir: Path) -> Path:
    """实际执行副本 input.gjf 的 Link0 %chk → chk 路径。

    相对值相对 run/<id>/ 解析；无扩展名时 g16 自动追加 .chk
    （g16 手册规则，实测 run/<id>/ 产物旁证），此处对齐（绝对声明无
    扩展名同样追加）；无声明回落 input.chk（此时 g16 不产 chk，formchk
    将因文件缺失失败并按「记日志不阻断」处理）。3.5.0 起为 chk 资产
    定位单一事实来源（物化溯源 / 续跑取数回落 / 成队校验共用）。
    """
    try:
        text = (run_dir / "input.gjf").read_text(encoding="utf-8",
                                                 errors="replace")
    except OSError:
        return run_dir / "input.chk"
    declared = parse_chk_line(text)
    if declared is None:
        return run_dir / "input.chk"
    p = declared
    if not p.is_absolute():
        p = run_dir / p
    return p if p.suffix else p.with_name(p.name + ".chk")


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
