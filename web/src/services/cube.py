"""cubegen 集成（M3 B4，m3-plan §2.4/§4.7；3.8.0 工具箱 B13 扩展；
3.8.0 修订批 B18：批量端点与 fchk 数据段预校验）：
cube 派生物生成与幂等留存。

- kind 白名单（B13 扩至六种）：MO=<n>（1≤n≤MO 总数，上界三级源）、
  Potential=SCF、Density=SCF、Spin=SCF（M3 既有）、Alpha=SCF、Beta=SCF
  （B13——仅开壳层体系，预校验 fail-closed：闭壳层 α/β 在 cubegen 侧
  不报错、会静默产出半密度 cube（§0.5 实测 ElSum 恰为一半），不能依赖
  其失败兜底）；
- npts：40–120 整数（M3 既有语义零变更）∪ -2/-3/-4（G16 原生粗/中/细
  档位直透位置参数，B13；细档体积显著——水 22.7MB 量级）；cube_id 摘要
  含 npts 原值（-3 与 80 天然不同 id，档位幂等区分）；
- nprocs 治理域 1–6、请求文法不暴露，服务端固定取默认 1；
- 幂等：cube_id = 参数摘要 sha256，产物 run/<id>/cubes/<cube_id>.cube，
  同参数重复 POST 直接返回既有 cube_id；
- 调用 `<g16_root>/cubegen <nprocs> <kind> <fchk> <cube> <npts> h`，
  子进程 120s 超时，stderr 尾部随 502 返回（风险 4）；
- 状态门槛 POST/GET 分列（B13，§2.2）：POST = 终态 succeeded/failed 且
  fchk 在场（failed 经工具箱手动转换落盘后出 cube，缺失 502 引导先转
  换）；GET = 终态且 cube 在场，不要求 fchk（cube 已生成后 fchk 被清理
  不阻断下载）；skipped 一律 409、非终态 404——analysis 四端点共享单点
  terminal_succeeded 零改动；
- failed 条目三级源读取硬规则（§2.2）：直读 analysis.json 绕过
  load_analysis 惰性重建（禁止向 failed 执行目录补写 analysis.json），
  缺失/degraded（nmo=0/nbias=0/homos=[]/blocks.orbitals=false）判源①
  不可得降级 fchk 头锚点；succeeded 读取语义零变更（blocks.orbitals=
  false 既有 422「无 MO 表」保留）；
- MO 上界三级源（B13 自旋块总口径）：源① succeeded 闭壳取 summary.nmo
  （G16 中恒等于 nbasis）、开壳取 2×nbasis（nmo≠nbasis 以 nbasis 为
  准）；failed 缺失/degraded 判源①不可得。源② fchk 头锚点
  （Alpha Orbital Energies 段在场为前提，Alpha N + Beta N、无 Beta 段
  取 Alpha N，权威格式 ~/g16/doc/formchk.txt 核验项 6 留痕）。源③两源
  皆不可得 422 mo_upper_unknown——不再降级为仅正整数校验，不依赖
  cubegen 报错（§9 风险 5）；
- cubegen 可执行探测缺失 503 CUBE_EXECUTABLE_MISSING（显式，不静默）；
  非零退出/超时 502 CUBE_GENERATION_FAILED；fchk 取执行目录内 input.fchk
  （M1 formchk 产物，不读用户源文件）；
- fchk 数据段预校验（修订批 R4）：按 kind 必需段映射 fail-closed——
  MO=Alpha MO coefficients（开壳层另需 Beta MO coefficients；shell 不可
  判定时仅验 Alpha，不因 shell 不可判定拒绝）、Potential/Density=Total
  SCF Density、Spin=Spin SCF Density、Alpha/Beta=Total SCF Density +
  Spin SCF Density。全文行扫描（errors="replace"，行首锚点——不复用
  64KB 头窗：038 实测密度段位于 MO 系数大块之后）；单端点插在幂等命中
  之后、cubegen 之前（幂等命中即曾成功不重查；缺段由 502 裸错改 422
  data_missing 为唯一有意例外）；批量在前置全量校验阶段逐 kind 罗列
  （kind_errors[]，任一失败零生成零子进程）；
- 批量端点（修订批 R3/R5，判定链五步）：① 终态门槛（404/409 同单端点）
  → ② kinds 文法（errors[] 字段词形 422；MO 上界三级源不可得
  mo_upper_unknown 与 succeeded 无 MO 表 ANALYSIS_PARSE_FAILED 属本步
  透传）→ ③ fchk 在场闸（502；先于 shell/段校验——α/β + fchk 缺失
  同组合按 502，与单端点 shell 判定先行为有意分歧）→ ④ 前置全量校验
  （kind_errors[] 逐 kind 罗列，零生成）→ ⑤ 逐 kind 串行生成（幂等命中
  零子进程、同参数同 cube_id 不新增维度；fail-fast 502 携带 failing
  kind 与 stderr_tail，已生成类留存缓存）→ 临时 ZIP 打包
  （export-cube-* 前缀入导出临时目录，FileResponse 流式发送 +
  BackgroundTask 删包，残留由启动清扫兜底）；包名 RFC 5987 双文件名
  （沿 fchk 下载先例），条目/包名公式见契约与 §2.5；
- cube 目录不入保留期清理（决策点 3：派生物可再生，与执行目录同生命周期；
  既有清理仅作用 run/<id>/ 顶层 .chk，天然不触 cubes/）；
- GET 经 FileResponse 流式发送（B13，大 cube 不整文件入内存，§9 风险 14）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote

from .. import config
from ..engine import finalize
from ..errors import err, not_found
from ..engine.workspace import g16_env
from ..store import settings
from . import analysis as analysis_svc
from .chktools import _ASCII_KEEP  # 单源复用（fchk 下载先例同一白名单）

CUBEGEN_TIMEOUT_S = 120
DEFAULT_NPTS = 80
NPTS_MIN, NPTS_MAX = 40, 120
NPTS_PRESETS = (-2, -3, -4)  # G16 原生粗/中/细档位（B13，§0.5 实测留痕）
NPROCS = 1  # 请求文法不暴露；治理域 1–6 取下限默认（§2.4）
KINDS = ("MO", "Potential", "Density", "Spin", "Alpha", "Beta")
_SCF_KINDS = ("Potential", "Density", "Spin", "Alpha", "Beta")
_CUBE_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_GRADE_EN = {-2: "coarse", -3: "medium", -4: "fine"}  # 修订批 R5（§2.5）

# fchk 头锚点（权威格式 ~/g16/doc/formchk.txt，核验项 6 留痕；头部读取
# 窗覆盖标量锚点与两数组段名——实测锚点均在文件头段）
_FCHK_HEAD_SPAN = 65536
_F_MULT = re.compile(r"^\s*Multiplicity\s+I\s+(\d+)\s*$", re.M)
_F_ALPHA_E = re.compile(r"^\s*Number of alpha electrons\s+I\s+(\d+)\s*$",
                        re.M)
_F_BETA_E = re.compile(r"^\s*Number of beta electrons\s+I\s+(\d+)\s*$",
                       re.M)
_F_ALPHA_N = re.compile(r"^\s*Alpha Orbital Energies\s+R\s+N=\s*(\d+)\s*$",
                        re.M)
_F_BETA_N = re.compile(r"^\s*Beta Orbital Energies\s+R\s+N=\s*(\d+)\s*$",
                       re.M)

# fchk 数据段锚点（修订批 R4：全文行扫描、行首锚点沿 _F_* 形态扩；
# 不复用 64KB 头窗——038 实测密度段位于 MO 系数大块 N=25600 之后）
_SECTION_ANCHORS = {
    "Alpha MO coefficients": re.compile(r"^\s*Alpha MO coefficients\b", re.M),
    "Beta MO coefficients": re.compile(r"^\s*Beta MO coefficients\b", re.M),
    "Total SCF Density": re.compile(r"^\s*Total SCF Density\b", re.M),
    "Spin SCF Density": re.compile(r"^\s*Spin SCF Density\b", re.M),
}
# per-kind 必需段映射（fail-closed；MO 段动态——开壳层另需 Beta 段）
_REQUIRED_SECTIONS = {
    "Potential": ("Total SCF Density",),
    "Density": ("Total SCF Density",),
    "Spin": ("Spin SCF Density",),
    "Alpha": ("Total SCF Density", "Spin SCF Density"),
    "Beta": ("Total SCF Density", "Spin SCF Density"),
}


def generate(execution_id: int, kind: object, orbital: object,
             npts: object) -> dict:
    """POST /history/{id}/analysis/cube：状态门槛（404/409）→ 校验
    （含 α/β 开壳层 fail-closed 与 MO 上界三级源，422）→ fchk 在场闸
    （502 引导先转换）→ 幂等命中 → 段预校验 → 子进程生成。
    返回 {"cube_id": ...}。

    校验先于 fchk 闸沿 M3 口径（参数 422 先于对象态 502——既有用例
    「校验通过后确定走 502」语义保留）；fchk 闸先于幂等命中与工具
    执行（POST 契约=终态且 fchk 在场，跑工具前置）；段预校验插在幂等
    命中之后、cubegen 之前（修订批 R4——幂等命中即曾成功不重查）。"""
    row = analysis_svc.terminal_for_download(execution_id)  # 404/409 共享前段
    state = row["state"]
    nmo = _nmo_upper(execution_id, state) if kind == "MO" else None
    _validate(kind, orbital, npts, nmo)
    if kind in ("Alpha", "Beta"):
        _validate_shell(execution_id, state, kind)
    analysis_svc.terminal_with_fchk(execution_id)  # B13：fchk 在场（502）
    npts_v = int(npts) if npts is not None else DEFAULT_NPTS
    return _generate_one(execution_id, kind, orbital, npts_v, state=state,
                         check_sections=True, batch_mode=False)


def _generate_one(execution_id: int, kind: str, orbital: object,
                  npts_v: int, *, state: str, check_sections: bool,
                  batch_mode: bool) -> dict:
    """单 kind 生成单点（单端点与批量共用，修订批 B18）：幂等命中直接
    复用（零子进程）→ 段预校验（仅单端点插入；批量在前置全量校验已
    覆盖、生成段不重查）→ cubegen 探测（503）→ 子进程（超时/非零退出
    502 fail-fast；batch_mode 时 details 补 failing kind 归属）。"""
    run_d = analysis_svc.run_dir(execution_id)
    cube_d = run_d / "cubes"
    cube_id = _cube_id(kind, orbital, npts_v)
    out = cube_d / f"{cube_id}.cube"
    if out.is_file() and out.stat().st_size > 0:
        return {"cube_id": cube_id}  # 幂等命中（派生物可再生，直接复用）
    if check_sections:
        _ensure_cube_sections(execution_id, kind, state)

    kind_arg = f"MO={orbital}" if kind == "MO" else f"{kind}=SCF"
    fchk = run_d / "input.fchk"
    g16_root = Path(str(settings().get("g16_root"))).expanduser()
    cubegen = g16_root / "cubegen"
    if not (cubegen.is_file() and _is_executable(cubegen)):
        raise err("CUBE_EXECUTABLE_MISSING",
                  "cubegen 可执行探测失败（g16_root 配置或发行不完整）",
                  {"g16_root": str(g16_root)}, http=503)
    cube_d.mkdir(parents=True, exist_ok=True)
    cmd = [str(cubegen), str(NPROCS), kind_arg, str(fchk), str(out),
           str(npts_v), "h"]
    fail_details = ({"kind": kind, "kind_arg": kind_arg} if batch_mode
                    else {"kind": kind_arg})
    try:
        proc = subprocess.run(cmd, cwd=str(run_d),
                              env=g16_env(g16_root, run_d),
                              capture_output=True,
                              timeout=CUBEGEN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise err("CUBE_GENERATION_FAILED",
                  f"cubegen 超时（>{CUBEGEN_TIMEOUT_S}s）",
                  {"reason": "timeout", **fail_details,
                   "npts": npts_v}, http=502)
    except OSError:
        # 客户端只给中文描述；OSError 细节（errno/路径）不入 message
        raise err("CUBE_EXECUTABLE_MISSING", "cubegen 启动失败",
                  {"g16_root": str(g16_root)}, http=503)
    if proc.returncode != 0 or not (out.is_file() and out.stat().st_size > 0):
        tail = proc.stderr.decode(errors="replace").strip()[-400:]
        raise err("CUBE_GENERATION_FAILED",
                  f"cubegen 非零退出 {proc.returncode}",
                  {**fail_details, "npts": npts_v, "stderr_tail": tail},
                  http=502)
    return {"cube_id": cube_id}


def load(execution_id: int, cube_id: str) -> Path:
    """GET /history/{id}/analysis/cube/{cube_id}：cube 文件路径（路由层
    FileResponse 流式发送，大 cube 不整文件入内存——B13）。"""
    analysis_svc.terminal_for_download(execution_id)  # B13：终态即下载
    if not isinstance(cube_id, str) or not _CUBE_ID_RE.match(cube_id):
        raise not_found("cube", cube_id)  # 形态非法按不存在（防路径穿越）
    path = analysis_svc.run_dir(execution_id) / "cubes" / f"{cube_id}.cube"
    if not path.is_file():
        raise not_found("cube", cube_id)
    return path


def _validate(kind: object, orbital: object, npts: object,
              nmo: int | None) -> None:
    """请求文法校验（§2.4）：kind 白名单、MO 时 orbital 必填且 1≤n≤上界、
    npts ∈ {-2,-3,-4} ∪ [40,120]。失败 422 VALIDATION_FAILED。"""
    failures = []
    if kind not in KINDS:
        failures.append({"field": "kind", "reason": "whitelist",
                         "value": kind, "allowed": list(KINDS)})
    if kind == "MO":
        if not isinstance(orbital, int) or isinstance(orbital, bool):
            failures.append({"field": "orbital", "reason": "type",
                             "value": orbital})
        elif not 1 <= orbital <= nmo:
            failures.append({"field": "orbital", "reason": "range",
                             "value": orbital, "min": 1, "max": nmo})
    elif orbital is not None:
        failures.append({"field": "orbital", "reason": "unexpected",
                         "value": orbital})
    if npts is not None:
        if not isinstance(npts, int) or isinstance(npts, bool):
            failures.append({"field": "npts", "reason": "type",
                             "value": npts})
        elif not (npts in NPTS_PRESETS or NPTS_MIN <= npts <= NPTS_MAX):
            failures.append({"field": "npts", "reason": "range",
                             "value": npts, "min": NPTS_MIN, "max": NPTS_MAX,
                             "presets": list(NPTS_PRESETS)})
    if failures:
        raise err("VALIDATION_FAILED", "cube 参数校验失败",
                  {"errors": failures}, http=422)


# ---------------- 三级源（B13：shell 判定与 MO 上界） ----------------

def _read_analysis_direct(execution_id: int) -> dict | None:
    """failed 条目直读 analysis.json（B13 硬规则 §2.2：绕过
    load_analysis 惰性重建——禁止向 failed 执行目录补写 analysis.json，
    终态管线对 failed 仅保全不落 analysis、补写与其形成内部不一致；
    缺失/损坏返回 None 判源①不可得）。"""
    path = analysis_svc.run_dir(execution_id) / finalize.ANALYSIS_NAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _degraded(summary: dict, blocks: dict) -> bool:
    """degraded 形态（§2.2 硬规则）：nmo=0 / nbasis=0 / homos=[] /
    blocks.orbitals=false 一律判源①不可得——否则 MO 上界取 0 轨道全拒、
    homos 元素数 0 被误判闭壳层 422。"""
    return (not summary.get("nmo") or not summary.get("nbasis")
            or not summary.get("homos") or not blocks.get("orbitals"))


def _fchk_head_anchors(execution_id: int) -> dict | None:
    """源② fchk 头锚点（核验项 6 留痕）：Alpha Orbital Energies 段在场
    为可得前提（缺失即源②不可得，不得反推闭壳层）；返回 Multiplicity/
    α/β 电子数/两段 N。"""
    fchk = analysis_svc.run_dir(execution_id) / "input.fchk"
    try:
        head = fchk.read_text(encoding="utf-8",
                              errors="replace")[:_FCHK_HEAD_SPAN]
    except OSError:
        return None
    alpha_n = _F_ALPHA_N.search(head)
    if alpha_n is None:
        return None
    beta_n = _F_BETA_N.search(head)
    mult = _F_MULT.search(head)
    n_alpha = _F_ALPHA_E.search(head)
    n_beta = _F_BETA_E.search(head)
    return {"mult": int(mult.group(1)) if mult else None,
            "n_alpha": int(n_alpha.group(1)) if n_alpha else None,
            "n_beta": int(n_beta.group(1)) if n_beta else None,
            "beta_section": beta_n is not None,
            "alpha_n": int(alpha_n.group(1)),
            "beta_n": int(beta_n.group(1)) if beta_n else None}


def _shell_unknown(kind: str) -> None:
    raise err("VALIDATION_FAILED",
              "无法判定开壳层，已拒绝生成 α/β 密度",
              {"reason": "shell_unknown", "kind": kind}, http=422)


def _judge_shell(execution_id: int, state: str) -> str | None:
    """shell 判定三级源（修订批 B18 抽取共用：α/β 校验与 MO 段映射
    同源）：源① homos 元素数（≥2 开壳、1 闭壳；failed 直读、degraded
    判不可得）→ 源② fchk 头锚点（仅开壳判据成立→开壳、仅闭壳判据
    成立→闭壳、两者皆成立或皆不成立→不可判定）→ 源③ None（不可
    判定；α/β 沿既有闸 422 shell_unknown，MO 段校验仅验 Alpha 放行）。"""
    shell: str | None = None
    if state == "failed":
        payload = _read_analysis_direct(execution_id)
    else:
        payload = analysis_svc.load_analysis(execution_id)  # 既有语义
    if payload is not None:
        homos = (payload.get("result", {}).get("summary", {})
                 .get("homos"))
        if isinstance(homos, list) and homos:
            shell = "open" if len(homos) >= 2 else "closed"
    if shell is not None:
        return shell
    a = _fchk_head_anchors(execution_id)  # 源② fchk 头锚点
    if a is None:
        return None  # 两源皆不可得（源③ fail-closed 由调用方分流）
    open_judge = (a["mult"] is not None and a["mult"] >= 2) or (
        a["n_alpha"] is not None and a["n_beta"] is not None
        and a["n_alpha"] != a["n_beta"])
    closed_judge = (a["mult"] == 1 and a["n_alpha"] is not None
                    and a["n_alpha"] == a["n_beta"]
                    and not a["beta_section"])
    if open_judge == closed_judge:  # 皆成立（矛盾形态）或皆不成立
        return None
    return "open" if open_judge else "closed"


def _validate_shell(execution_id: int, state: str, kind: str) -> None:
    """α/β 开壳层预校验（fail-closed，§2.2）：判定走 _judge_shell
    三级源共用单点。闭壳层确认 422 closed_shell、不可判定 422
    shell_unknown（既有码型零变更）。"""
    shell = _judge_shell(execution_id, state)
    if shell is None:
        _shell_unknown(kind)
    if shell == "closed":
        raise err("VALIDATION_FAILED",
                  "α/β 密度要求开壳层体系（当前条目为闭壳层）",
                  {"reason": "closed_shell", "kind": kind}, http=422)


# ---------------- fchk 数据段预校验（修订批 R4） ----------------

def _required_sections(kind: str, shell: str | None) -> tuple[str, ...]:
    """per-kind 必需段映射（契约 description 同源）：MO 动态——开壳层
    另需 Beta MO coefficients；shell 不可判定/闭壳层仅验 Alpha 段（不因
    shell 不可判定拒绝，与「038 MO 可生成」口径自洽）。"""
    if kind == "MO":
        base = ("Alpha MO coefficients",)
        return base + (("Beta MO coefficients",) if shell == "open" else ())
    return _REQUIRED_SECTIONS[kind]


def _missing_section(execution_id: int, kind: str,
                     shell: str | None) -> str | None:
    """fchk 全文行扫描（errors="replace"、行首锚点正则）——返回首个
    缺失段名，齐备返回 None。不复用 64KB 头窗（038 实测密度段位于
    MO 系数大块之后；fchk 文本量级 MB，单遍扫描可接受）。"""
    fchk = analysis_svc.run_dir(execution_id) / "input.fchk"
    try:
        text = fchk.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""  # 读清竞态 fail-closed：按缺段处理（fchk 闸已过）
    for name in _required_sections(kind, shell):
        if _SECTION_ANCHORS[name].search(text) is None:
            return name
    return None


def _ensure_cube_sections(execution_id: int, kind: str, state: str) -> None:
    """单端点段预校验单点（修订批 R4）：调用时机 = 幂等命中之后、
    cubegen 之前（幂等命中即曾成功，不重查——调用方保证）。缺段 422
    VALIDATION_FAILED reason=data_missing（details.section 段名原文 +
    details.kind 归属）。MO 分支判 shell 仅用于 Beta 段增验，不可判定
    不拒绝。"""
    shell = _judge_shell(execution_id, state) if kind == "MO" else None
    missing = _missing_section(execution_id, kind, shell)
    if missing is not None:
        raise err("VALIDATION_FAILED",
                  "fchk 缺少数据段，无法生成该类型 cube",
                  {"reason": "data_missing", "kind": kind,
                   "section": missing}, http=422)


def _nmo_upper(execution_id: int, state: str) -> int:
    """MO 上界三级源（B13 自旋块总口径，§2.2）：
    - 源① succeeded：闭壳沿用 summary.nmo（既有语义零变更）、开壳
      2×nbasis（nmo≠nbasis 以 nbasis 为准）；blocks.orbitals=false 保留
      既有 422 ANALYSIS_PARSE_FAILED。failed：直读缺失/degraded 判源①
      不可得（开壳 2×nbasis、闭壳 nbasis）。
    - 源② fchk 头锚点：Alpha N + Beta N（无 Beta 段取 Alpha N）。
    - 源③ 两源皆不可得 422 mo_upper_unknown（不再降级为仅正整数校验，
      不依赖 cubegen 报错）。"""
    if state == "succeeded":
        payload = analysis_svc.load_analysis(execution_id)
        if not payload["result"]["blocks"].get("orbitals"):
            raise err("ANALYSIS_PARSE_FAILED",
                      "无 MO 表（无法确定轨道上界，建议 Pop=Reg/Full）",
                      {"block": "orbitals"}, http=422)
        summary = payload["result"]["summary"]
        homos = summary.get("homos") or []
        if len(homos) >= 2:  # 开壳层按自旋块总口径扩展
            nbasis = int(summary.get("nbasis") or 0)
            return 2 * nbasis if nbasis else int(summary.get("nmo") or 0)
        return int(summary.get("nmo") or 0)  # 闭壳层既有口径
    # failed：直读，缺失/degraded 判源①不可得
    payload = _read_analysis_direct(execution_id)
    summary = (payload or {}).get("result", {}).get("summary", {})
    blocks = (payload or {}).get("result", {}).get("blocks", {})
    if not _degraded(summary, blocks):
        homos = summary["homos"]
        return (2 * int(summary["nbasis"]) if len(homos) >= 2
                else int(summary["nbasis"]))  # nmo≠nbasis 以 nbasis 为准
    a = _fchk_head_anchors(execution_id)  # 源② fchk 头锚点
    if a is not None:
        return a["alpha_n"] + (a["beta_n"] or 0)
    raise err("VALIDATION_FAILED",
              "无法确定轨道上界（分析数据与 fchk 头锚点均不可得）",
              {"reason": "mo_upper_unknown"}, http=422)


def _cube_id(kind: str, orbital: object, npts: int) -> str:
    raw = f"{kind}|{orbital if kind == 'MO' else ''}|{npts}|{NPROCS}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_executable(path: Path) -> bool:
    return os.access(path, os.X_OK)


# ---------------- 批量端点（修订批 R3/R4/R5，判定链五步） ----------------

def generate_batch(execution_id: int, kinds: object, orbital: object,
                   npts: object) -> tuple[Path, dict[str, str]]:
    """POST /history/{id}/analysis/cube/batch：批量判定链五步（契约
    description 同源）——① 终态门槛（404/409 同单端点）→ ② kinds 文法
    （errors[] 字段词形 422）→ ③ fchk 在场闸（502；先于 shell/段校验，
    α/β + fchk 缺失同组合按 502 钉死）→ ④ 前置全量校验（kind_errors[]
    逐 kind 罗列，任一失败零生成零子进程）→ ⑤ 逐 kind 串行生成（幂等
    命中零子进程；fail-fast 502/503）→ 临时 ZIP 打包。

    返回 (zip_path, headers)——路由层 FileResponse 流式发送 +
    BackgroundTask 删包（沿 history 导出先例）。"""
    row = analysis_svc.terminal_for_download(execution_id)  # ① 404/409
    state = row["state"]
    _validate_batch_grammar(execution_id, state, kinds, orbital,
                            npts)                          # ② 文法 422
    analysis_svc.terminal_with_fchk(execution_id)          # ③ fchk 闸 502
    kinds_set = set(kinds) if isinstance(kinds, list) else set()
    selected = [k for k in KINDS if k in kinds_set]        # 规范序（§2.5）
    kind_errors = _batch_precollect(execution_id, state, selected)  # ④
    if kind_errors:
        raise err("VALIDATION_FAILED",
                  "cube 批量生成校验失败（部分类型不可生成）",
                  {"kind_errors": kind_errors}, http=422)
    npts_v = int(npts) if npts is not None else DEFAULT_NPTS
    ids: dict[str, str] = {}
    for kind in selected:                                  # ⑤ 串行生成
        res = _generate_one(execution_id, kind, orbital, npts_v,
                            state=state, check_sections=False,
                            batch_mode=True)
        ids[kind] = res["cube_id"]
    return _pack_batch_zip(execution_id, selected, ids, orbital, npts_v)


def _validate_batch_grammar(execution_id: int, state: str, kinds: object,
                            orbital: object, npts: object) -> None:
    """批量判定链②：kinds 文法校验（errors[] 字段词形，与单端点参数
    校验同形）。MO 上界三级源不可得（mo_upper_unknown）与 succeeded 无
    MO 表（ANALYSIS_PARSE_FAILED）属本步——_nmo_upper 直接抛出透传
    （details 沿单端点既有形态）。"""
    failures: list[dict] = []
    if not isinstance(kinds, list):
        failures.append({"field": "kinds", "reason": "type", "value": kinds})
    elif not kinds or len(kinds) > len(KINDS):
        failures.append({"field": "kinds", "reason": "range", "value": kinds,
                         "min": 1, "max": len(KINDS)})
    seen: set[str] = set()
    has_mo = False
    for k in (kinds if isinstance(kinds, list) else []):
        if not isinstance(k, str):
            failures.append({"field": "kinds", "reason": "type", "value": k})
        elif k not in KINDS:
            failures.append({"field": "kinds", "reason": "whitelist",
                             "value": k, "allowed": list(KINDS)})
        elif k in seen:
            failures.append({"field": "kinds", "reason": "duplicate",
                             "value": k})
        else:
            seen.add(k)
            has_mo = has_mo or k == "MO"
    if has_mo:
        nmo = _nmo_upper(execution_id, state)  # 文法步透传（两源码型）
        if not isinstance(orbital, int) or isinstance(orbital, bool):
            failures.append({"field": "orbital", "reason": "type",
                             "value": orbital})
        elif not 1 <= orbital <= nmo:
            failures.append({"field": "orbital", "reason": "range",
                             "value": orbital, "min": 1, "max": nmo})
    elif orbital is not None:
        failures.append({"field": "orbital", "reason": "unexpected",
                         "value": orbital})
    if npts is not None:
        if not isinstance(npts, int) or isinstance(npts, bool):
            failures.append({"field": "npts", "reason": "type",
                             "value": npts})
        elif not (npts in NPTS_PRESETS or NPTS_MIN <= npts <= NPTS_MAX):
            failures.append({"field": "npts", "reason": "range",
                             "value": npts, "min": NPTS_MIN,
                             "max": NPTS_MAX, "presets": list(NPTS_PRESETS)})
    if failures:
        raise err("VALIDATION_FAILED", "cube 批量参数校验失败",
                  {"errors": failures}, http=422)


def _batch_precollect(execution_id: int, state: str,
                      selected: list[str]) -> list[dict]:
    """批量判定链④：前置全量校验（先全量后生成——任一 kind 失败整批
    拒绝、零生成零子进程；与单端点幂等命中不重查为有意相反）。逐 kind
    依次 α/β 开壳层 fail-closed 与数据段预校验，kind_errors[] 逐 kind
    罗列 {kind, reason, section?}；MO 不判 shell 拒绝（仅验 Alpha，
    开壳层另验 Beta）。"""
    kind_errors: list[dict] = []
    shell_cache: str | None = None
    judged = False

    def _shell() -> str | None:
        nonlocal shell_cache, judged
        if not judged:
            shell_cache = _judge_shell(execution_id, state)
            judged = True
        return shell_cache

    for kind in selected:
        if kind in ("Alpha", "Beta"):
            s = _shell()
            if s == "closed":
                kind_errors.append({"kind": kind, "reason": "closed_shell"})
                continue  # 既有闸拦截、不进入段校验（038 口径）
            if s is None:
                kind_errors.append({"kind": kind, "reason": "shell_unknown"})
                continue
        missing = _missing_section(execution_id, kind,
                                   _shell() if kind == "MO" else None)
        if missing is not None:
            kind_errors.append({"kind": kind, "reason": "data_missing",
                                "section": missing})
    return kind_errors


def _grade_token(npts: int) -> str:
    """命名档位段（§2.5）：presets 映射英文词（coarse/medium/fine），
    40–120 自由整数用无符号数值本身（正整数域无负号）。"""
    return _GRADE_EN.get(npts, str(npts))


def _cube_entry_name(stem: str, kind: str, orbital: object,
                     npts_v: int) -> str:
    """ZIP 条目名（§2.5，与单文件前端落盘名同公式）：
    <stem>-<Kind>[-<n>]-<档位>.cube"""
    head = f"{stem}-{kind}"
    if kind == "MO":
        head = f"{head}-{orbital}"
    return f"{head}-{_grade_token(npts_v)}.cube"


def _pack_batch_zip(execution_id: int, selected: list[str],
                    ids: dict[str, str], orbital: object,
                    npts_v: int) -> tuple[Path, dict[str, str]]:
    """临时 ZIP 打包（修订批 R3/R5）：条目平铺逐 kind 命名；包名
    <stem>-<类型段>-<档位>.zip（类型段规范序罗列、六类全选 all、不含
    MO 轨道号）；Content-Disposition 恒双文件名（RFC 5987 filename* +
    白名单清洗 ASCII fallback，清洗为空回落 execution-<id>，沿 fchk
    下载先例）；临时包入导出临时目录（export-cube-* 前缀入启动清扫
    范围），失败不留半成品，发送后由 BackgroundTask 删除。"""
    from .history import get_entry  # 延迟导入（history 依赖面大，先例同）
    name = get_entry(execution_id)["filename"]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    typeseg = ("all" if len(selected) == len(KINDS)
               else "-".join(selected))
    pkg = f"{stem}-{typeseg}-{_grade_token(npts_v)}.zip"
    run_d = analysis_svc.run_dir(execution_id)
    tmp_dir = config.HOME_DIR / config.EXPORT_TMP_SUBDIR
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix="export-cube-", suffix=".zip",
                               dir=tmp_dir)
    os.close(fd)
    tmp_path = Path(raw)
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for kind in selected:
                cube_id = ids[kind]
                zf.write(run_d / "cubes" / f"{cube_id}.cube",
                         arcname=_cube_entry_name(stem, kind, orbital,
                                                  npts_v))
    except BaseException:
        tmp_path.unlink(missing_ok=True)  # 失败不留半成品（history 同口径）
        raise
    ascii_fallback = (_ASCII_KEEP.sub("_", pkg[:-len(".zip")])
                      .strip("._-") or f"execution-{execution_id}")
    headers = {"Content-Disposition":
               f"attachment; filename={ascii_fallback}.zip; "
               f"filename*=UTF-8''{quote(pkg)}"}
    return tmp_path, headers
