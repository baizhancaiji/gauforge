"""cubegen 集成（M3 B4，m3-plan §2.4/§4.7）：cube 派生物生成与幂等留存。

- kind 白名单（§2.4 治理表）：MO=<n>（1≤n≤nmo，上界取 B2 analysis.json）、
  Potential=SCF、Density=SCF、Spin=SCF；npts 40–120（默认 80，G16 默认档）；
  nprocs 治理域 1–6、请求文法不暴露，服务端固定取默认 1；
- 幂等：cube_id = 参数摘要 sha256，产物 run/<id>/cubes/<cube_id>.cube，
  同参数重复 POST 直接返回既有 cube_id；
- 调用 `<g16_root>/cubegen <nprocs> <kind> <fchk> <cube> <npts> h`，
  子进程 120s 超时，stderr 尾部随 502 返回（风险 4）；
- cubegen 可执行探测缺失 503 CUBE_EXECUTABLE_MISSING（显式，不静默）；
  非零退出/超时 502 CUBE_GENERATION_FAILED；fchk 取执行目录内 input.fchk
  （M1 formchk 产物，不读用户源文件），缺失亦 502（details 注明）；
- cube 目录不入保留期清理（决策点 3：派生物可再生，与执行目录同生命周期；
  既有清理仅作用 run/<id>/ 顶层 .chk/.rwf，天然不触 cubes/）。
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

from ..errors import err, not_found
from ..engine.workspace import g16_env
from ..store import settings
from . import analysis as analysis_svc

CUBEGEN_TIMEOUT_S = 120
DEFAULT_NPTS = 80
NPTS_MIN, NPTS_MAX = 40, 120
NPROCS = 1  # 请求文法不暴露；治理域 1–6 取下限默认（§2.4）
KINDS = ("MO", "Potential", "Density", "Spin")
_CUBE_ID_RE = re.compile(r"^[0-9a-f]{64}$")


def generate(execution_id: int, kind: object, orbital: object,
             npts: object) -> dict:
    """POST /history/{id}/analysis/cube：校验 → 幂等命中 → 子进程生成。

    返回 {"cube_id": ...}；校验顺序沿 §3.3：白名单与上界（422）→ 幂等 →
    运行（502/503）。"""
    analysis_svc.terminal_succeeded(execution_id)  # 非 succeeded 409
    nmo = _nmo_upper(execution_id) if kind == "MO" else None
    _validate(kind, orbital, npts, nmo)
    npts_v = int(npts) if npts is not None else DEFAULT_NPTS
    run_d = analysis_svc.run_dir(execution_id)
    cube_d = run_d / "cubes"
    cube_id = _cube_id(kind, orbital, npts_v)
    out = cube_d / f"{cube_id}.cube"
    if out.is_file() and out.stat().st_size > 0:
        return {"cube_id": cube_id}  # 幂等命中（派生物可再生，直接复用）

    kind_arg = f"MO={orbital}" if kind == "MO" else f"{kind}=SCF"
    fchk = run_d / "input.fchk"
    if not fchk.is_file():
        raise err("CUBE_GENERATION_FAILED",
                  "formchk 产物缺失（run/<id>/input.fchk 不存在）",
                  {"reason": "fchk_missing", "fchk": "input.fchk"}, http=502)
    g16_root = Path(str(settings().get("g16_root"))).expanduser()
    cubegen = g16_root / "cubegen"
    if not (cubegen.is_file() and os_access(cubegen)):
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
    except OSError as exc:
        raise err("CUBE_EXECUTABLE_MISSING", f"cubegen 启动失败：{exc}",
                  {"g16_root": str(g16_root)}, http=503)
    if proc.returncode != 0 or not (out.is_file() and out.stat().st_size > 0):
        tail = proc.stderr.decode(errors="replace").strip()[-400:]
        raise err("CUBE_GENERATION_FAILED",
                  f"cubegen 非零退出 {proc.returncode}",
                  {"kind": kind_arg, "npts": npts_v, "stderr_tail": tail},
                  http=502)
    return {"cube_id": cube_id}


def load(execution_id: int, cube_id: str) -> bytes:
    """GET /history/{id}/analysis/cube/{cube_id}：cube 文件流。"""
    analysis_svc.terminal_succeeded(execution_id)  # 404 语义前置（非终态 404）
    if not isinstance(cube_id, str) or not _CUBE_ID_RE.match(cube_id):
        raise not_found("cube", cube_id)  # 形态非法按不存在（防路径穿越）
    path = analysis_svc.run_dir(execution_id) / "cubes" / f"{cube_id}.cube"
    try:
        return path.read_bytes()
    except OSError:
        raise not_found("cube", cube_id)


def _validate(kind: object, orbital: object, npts: object,
              nmo: int | None) -> None:
    """请求文法校验（§2.4）：kind 白名单、MO 时 orbital 必填且 1≤n≤nmo、
    npts 40–120。失败 422 VALIDATION_FAILED。"""
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
        elif not NPTS_MIN <= npts <= NPTS_MAX:
            failures.append({"field": "npts", "reason": "range",
                             "value": npts, "min": NPTS_MIN, "max": NPTS_MAX})
    if failures:
        raise err("VALIDATION_FAILED", "cube 参数校验失败",
                  {"errors": failures}, http=422)


def _nmo_upper(execution_id: int) -> int:
    """MO 上界：取 analysis.json 概览 nmo（缺失/不可得走 409/422 语义）。"""
    payload = analysis_svc.load_analysis(execution_id)
    if not payload["result"]["blocks"].get("orbitals"):
        raise err("ANALYSIS_PARSE_FAILED",
                  "无 MO 表（无法确定轨道上界，建议 Pop=Reg/Full）",
                  {"block": "orbitals"}, http=422)
    return int(payload["result"]["summary"]["nmo"])


def _cube_id(kind: str, orbital: object, npts: int) -> str:
    raw = f"{kind}|{orbital if kind == 'MO' else ''}|{npts}|{NPROCS}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def os_access(path: Path) -> bool:
    import os
    return os.access(path, os.X_OK)
