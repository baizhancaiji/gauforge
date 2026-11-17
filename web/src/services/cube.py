"""cubegen 集成（M3 B4，m3-plan §2.4/§4.7；3.8.0 工具箱 B13 扩展）：
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
from pathlib import Path

from ..engine import finalize
from ..errors import err, not_found
from ..engine.workspace import g16_env
from ..store import settings
from . import analysis as analysis_svc

CUBEGEN_TIMEOUT_S = 120
DEFAULT_NPTS = 80
NPTS_MIN, NPTS_MAX = 40, 120
NPTS_PRESETS = (-2, -3, -4)  # G16 原生粗/中/细档位（B13，§0.5 实测留痕）
NPROCS = 1  # 请求文法不暴露；治理域 1–6 取下限默认（§2.4）
KINDS = ("MO", "Potential", "Density", "Spin", "Alpha", "Beta")
_SCF_KINDS = ("Potential", "Density", "Spin", "Alpha", "Beta")
_CUBE_ID_RE = re.compile(r"^[0-9a-f]{64}$")

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


def generate(execution_id: int, kind: object, orbital: object,
             npts: object) -> dict:
    """POST /history/{id}/analysis/cube：状态门槛（404/409）→ 校验
    （含 α/β 开壳层 fail-closed 与 MO 上界三级源，422）→ fchk 在场闸
    （502 引导先转换）→ 幂等命中 → 子进程生成。返回 {"cube_id": ...}。

    校验先于 fchk 闸沿 M3 口径（参数 422 先于对象态 502——既有用例
    「校验通过后确定走 502」语义保留）；fchk 闸先于幂等命中与工具
    执行（POST 契约=终态且 fchk 在场，跑工具前置）。"""
    row = analysis_svc.terminal_for_download(execution_id)  # 404/409 共享前段
    state = row["state"]
    nmo = _nmo_upper(execution_id, state) if kind == "MO" else None
    _validate(kind, orbital, npts, nmo)
    if kind in ("Alpha", "Beta"):
        _validate_shell(execution_id, state, kind)
    analysis_svc.terminal_with_fchk(execution_id)  # B13：fchk 在场（502）
    npts_v = int(npts) if npts is not None else DEFAULT_NPTS
    run_d = analysis_svc.run_dir(execution_id)
    cube_d = run_d / "cubes"
    cube_id = _cube_id(kind, orbital, npts_v)
    out = cube_d / f"{cube_id}.cube"
    if out.is_file() and out.stat().st_size > 0:
        return {"cube_id": cube_id}  # 幂等命中（派生物可再生，直接复用）

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
    try:
        proc = subprocess.run(cmd, cwd=str(run_d),
                              env=g16_env(g16_root, run_d),
                              capture_output=True,
                              timeout=CUBEGEN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise err("CUBE_GENERATION_FAILED",
                  f"cubegen 超时（>{CUBEGEN_TIMEOUT_S}s）",
                  {"reason": "timeout", "kind": kind_arg,
                   "npts": npts_v}, http=502)
    except OSError:
        # 客户端只给中文描述；OSError 细节（errno/路径）不入 message
        raise err("CUBE_EXECUTABLE_MISSING", "cubegen 启动失败",
                  {"g16_root": str(g16_root)}, http=503)
    if proc.returncode != 0 or not (out.is_file() and out.stat().st_size > 0):
        tail = proc.stderr.decode(errors="replace").strip()[-400:]
        raise err("CUBE_GENERATION_FAILED",
                  f"cubegen 非零退出 {proc.returncode}",
                  {"kind": kind_arg, "npts": npts_v, "stderr_tail": tail},
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


def _validate_shell(execution_id: int, state: str, kind: str) -> None:
    """α/β 开壳层预校验（fail-closed，§2.2）：源① homos 元素数
    （≥2 开壳、1 闭壳；failed 直读、degraded 判不可得）→ 源② fchk 头
    锚点（仅开壳判据成立→开壳、仅闭壳判据成立→闭壳、两者皆成立或皆不
    成立→不可判定）→ 源③ 422 shell_unknown。闭壳层确认 422 closed_shell。"""
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
    if shell is None:  # 源② fchk 头锚点
        a = _fchk_head_anchors(execution_id)
        if a is None:
            _shell_unknown(kind)  # 两源皆不可得（源③ fail-closed）
        open_judge = (a["mult"] is not None and a["mult"] >= 2) or (
            a["n_alpha"] is not None and a["n_beta"] is not None
            and a["n_alpha"] != a["n_beta"])
        closed_judge = (a["mult"] == 1 and a["n_alpha"] is not None
                        and a["n_alpha"] == a["n_beta"]
                        and not a["beta_section"])
        if open_judge == closed_judge:  # 皆成立（矛盾形态）或皆不成立
            _shell_unknown(kind)
        shell = "open" if open_judge else "closed"
    if shell == "closed":
        raise err("VALIDATION_FAILED",
                  "α/β 密度要求开壳层体系（当前条目为闭壳层）",
                  {"reason": "closed_shell", "kind": kind}, http=422)


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
