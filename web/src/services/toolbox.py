"""工具箱域服务（3.8.0 工具箱 B15，toolbox-plan §2.4/§2.5）：
freqmem 内存估算校验 + 历史带入预填 + solname 溶剂速查表。

- freqmem 有效性判定只用锚点（非法参数退出码恒 0 不可作判据，§0.5
  实测）：输出含 `Minimum of N.NN megawords per thread.` → 成功；含
  `Unrecognized` / usage 行 → 422（details 携带原文错误行，防御路径与
  白名单拦截分列）；其余 → 502 进程失败。
- basis_type 白名单终值 p/d/f/g/h/i（全字母真机实测确认，s 恒被拒）；
  白名单外 422 自有中文提示、不调 freqmem（无原文可带）。
- 对照算术在后端单点完成（nproc 总量口径）：minimum 为每线程需求、
  declared 为 %mem 声明总量，sufficient = declared ≥ minimum_gb × nproc、
  delta_gb = declared − minimum_gb × nproc（负值=缺口）；缺省 nproc=1。
  minimum_gb = minimum_mw × 8 / 1024（1 MW = 2²⁰ words × 8 B = 8 MiB；
  GB 按 1024 基底，与 link0_default_mem_gb 口径一致）。
- prefill 资源值取执行记录 resources（dispatcher 落库 {value,
  defaulted}）判声明来源，不从 run/<id>/input.gjf 执行副本反推
  （materialize 写入的副本已注入缺省行，反推恒判 declared，§2.4）；
  %mem 换算语义复用 parse/link0_rules.mem_to_gb 公开单点（语义核对，
  本服务不做用户输入换算）。零值/缺失守卫不猜数：natom 0/缺失、nbasis
  0、homos 空 → 409（details 注明缺失维度）。
- solvents 懒加载 + 进程内缓存：缓存键 = g16_root expanduser().resolve()
  后 realpath（符号链接换目标同样失效）；调用失败不缓存（下次请求重
  试）；无启动时调用（g16 缺失不炸启动）。解析锚点锁真机实测格式
  （条目行 ` I= N JN= k Name=X`，JN ∈ {1,2,3,4}；未识别行忽略的前向
  兼容）；交叉核对：JN=1 行数 = 头行 NSolv 且每 id 恰一条 JN=1，任一
  不满足 502（防御解析缺陷）。
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

from ..errors import err, not_found
from ..engine.workspace import g16_env
from ..store import executions, settings
from . import analysis as analysis_svc

FREQMEM_TIMEOUT_S = 120
SOLNAME_TIMEOUT_S = 120

BASIS_TYPES = ("p", "d", "f", "g", "h", "i")
SHELLS = ("r", "u")
_NUM_LIMIT = 100000  # 防御上限（远超真实体系规模，§2.4）
_NPROC_LIMIT = 256   # 与 link0_default_nproc 设置值域同口径
_MW_TO_GB = 8 / 1024

_FREQMEM_MW_RE = re.compile(r"Minimum of\s*([0-9.]+)\s*megawords per thread\.")
_FREQMEM_ERR_MARKS = ("Unrecognized", "usage")
_SOLNAME_LINE_RE = re.compile(r"^\s*I=\s*(\d+)\s+JN=\s*(\d+)\s+Name=(\S.*)$")
_NSOLV_RE = re.compile(r"^\s*NSolv=\s*(\d+)")

# 进程内缓存（B15）：{"key": g16_root realpath, "data": 响应体}；仅成功
# 结果入缓存，键绑定 realpath（符号链接换目标同样失效，§9 风险 8）
_solvents_cache: dict | None = None


def _g16_root() -> Path:
    return Path(str(settings().get("g16_root"))).expanduser()


def _tool_or_503(tool: str) -> Path:
    path = _g16_root() / tool
    if not (path.is_file() and os.access(path, os.X_OK)):
        raise err("G16_TOOL_UNAVAILABLE",
                  f"{tool} 可执行探测失败（g16_root 配置或发行不完整）",
                  {"tool": tool, "g16_root": str(_g16_root())}, http=503)
    return path


def _run_tool(tool_path: Path, args: list[str], *,
              timeout_s: int) -> str:
    """临时目录 + g16_env + 列表参数调用（freqmem 无副作用、solname 只读
    输出；cwd 临时目录沿探针范式）。启动失败/超时 502 G16_TOOL_FAILED
    （details.tool 区分）。"""
    with tempfile.TemporaryDirectory(prefix=f"hq-{tool_path.name}-") as td:
        try:
            proc = subprocess.run([str(tool_path), *args], cwd=td,
                                  env=g16_env(_g16_root(), Path(td)),
                                  capture_output=True, timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise err("G16_TOOL_FAILED", f"{tool_path.name} 超时"
                      f"（>{timeout_s}s）",
                      {"tool": tool_path.name, "reason": "timeout"},
                      http=502) from exc
        except OSError as exc:
            raise err("G16_TOOL_FAILED", f"{tool_path.name} 启动失败",
                      {"tool": tool_path.name, "reason": "startup"},
                      http=502) from exc
        if proc.returncode != 0:
            raise err("G16_TOOL_FAILED",
                      f"{tool_path.name} 非零退出 {proc.returncode}",
                      {"tool": tool_path.name, "reason": "nonzero",
                       "stderr_tail": proc.stderr.decode(
                           errors="replace").strip()[-400:]}, http=502)
        return proc.stdout.decode(errors="replace")


# ---------------- freqmem 校验（§2.4） ----------------

def _check_payload(payload: dict) -> tuple[int, int, str, str,
                                           float | None, int | None]:
    """载荷类型与值域校验。白名单外（含 s）422 自有中文提示（先拦，
    不调 freqmem）；其余值域错误 422 逐 field details。"""
    basis = payload.get("basis_type")
    if basis not in BASIS_TYPES:  # 白名单先拦（自有中文提示，无原文可带）
        raise err("VALIDATION_FAILED",
                  "角动量字母仅支持 p/d/f/g/h/i",
                  {"errors": [{"field": "basis_type", "reason": "whitelist",
                               "value": basis,
                               "allowed": list(BASIS_TYPES)}]}, http=422)
    failures = []

    def _int_field(name: str, value: object, limit: int) -> int | None:
        if not isinstance(value, int) or isinstance(value, bool):
            failures.append({"field": name, "reason": "type", "value": value})
            return None
        if not 1 <= value <= limit:
            failures.append({"field": name, "reason": "range",
                             "value": value, "min": 1, "max": limit})
            return None
        return value

    num_atoms = _int_field("num_atoms", payload.get("num_atoms"), _NUM_LIMIT)
    num_basis = _int_field("num_basis", payload.get("num_basis"), _NUM_LIMIT)
    nproc = payload.get("nproc")
    if nproc is not None:
        nproc = _int_field("nproc", nproc, _NPROC_LIMIT)
    shell = payload.get("shell")
    if shell not in SHELLS:
        failures.append({"field": "shell", "reason": "whitelist",
                         "value": shell, "allowed": list(SHELLS)})
    compare = payload.get("compare_mem_gb")
    if compare is not None:
        if isinstance(compare, bool) or not isinstance(compare, (int, float)):
            failures.append({"field": "compare_mem_gb", "reason": "type",
                             "value": compare})
            compare = None
        elif not compare > 0:
            failures.append({"field": "compare_mem_gb", "reason": "range",
                             "value": compare, "min": 0})
            compare = None
    if failures:
        raise err("VALIDATION_FAILED", "freqmem 参数校验失败",
                  {"errors": failures}, http=422)
    return (num_atoms, num_basis, shell, basis,
            float(compare) if compare is not None else None, nproc)


def freqmem_check(payload: dict) -> dict:
    """POST /toolbox/freqmem：白名单 → 值域校验 → 调用 → 锚点判定 →
    对照算术（nproc 总量口径）。"""
    num_atoms, num_basis, shell, basis, compare, nproc = _check_payload(
        dict(payload or {}))
    freqmem = _tool_or_503("freqmem")
    out = _run_tool(freqmem, [str(num_atoms), str(num_basis), shell, basis],
                    timeout_s=FREQMEM_TIMEOUT_S)
    m = _FREQMEM_MW_RE.search(out)
    if m is None:  # 防御路径：Unrecognized / usage 行 → 422 携带原文
        err_lines = [ln.strip() for ln in out.splitlines()
                     if any(mark in ln for mark in _FREQMEM_ERR_MARKS)]
        if err_lines:
            raise err("VALIDATION_FAILED",
                      "freqmem 拒绝了该参数组合（详见错误行原文）",
                      {"reason": "freqmem_unrecognized",
                       "error_lines": err_lines[:10]}, http=422)
        raise err("G16_TOOL_FAILED",
                  "freqmem 输出无需求锚点行（解析失败）",
                  {"tool": "freqmem", "reason": "no_anchor"}, http=502)
    minimum_mw = float(m.group(1))
    minimum_gb = minimum_mw * _MW_TO_GB
    verdict = None
    if compare is not None:
        nproc_v = nproc if nproc is not None else 1  # 缺省 1 单线程口径
        verdict = {"nproc": nproc_v, "declared_mem_gb": compare,
                   "sufficient": compare >= minimum_gb * nproc_v,
                   "delta_gb": compare - minimum_gb * nproc_v}
    return {"minimum_mw": minimum_mw, "minimum_gb": minimum_gb,
            "per_thread": True, "basis_type_echo": basis,
            "verdict": verdict}


# ---------------- freqmem 历史带入预填（§2.4） ----------------

def freqmem_prefill(execution_id: int) -> dict:
    """GET /toolbox/freqmem-prefill：仅 succeeded；三源取 analysis.json
    概览，资源值取执行记录 resources（不从执行副本反推）。"""
    row = executions().get(execution_id)
    if row is None or row["state"] not in ("succeeded", "failed", "skipped"):
        raise not_found("history", execution_id)
    if row["state"] != "succeeded":
        raise err("ANALYSIS_UNAVAILABLE",
                  "仅 succeeded 条目可预填（失败/未运行条目无分析数据）",
                  {"state": row["state"]}, http=409)
    payload = analysis_svc.load_analysis(execution_id)  # 缺失重建失败 409
    summary = payload["result"]["summary"]
    missing = []
    if not summary.get("natom"):
        missing.append("natom")
    if not summary.get("nbasis"):
        missing.append("nbasis")
    homos = summary.get("homos")
    if not isinstance(homos, list) or not homos:
        missing.append("homos")
    if missing:  # 零值/缺失守卫——不猜数（§2.4）
        raise err("ANALYSIS_UNAVAILABLE",
                  "分析数据缺少预填所需维度（degraded 解析）",
                  {"execution_id": execution_id, "missing": missing},
                  http=409)
    shell = "u" if len(homos) >= 2 else "r"

    resources = row.get("resources") or {}
    mem_res = resources.get("mem_gb")
    nproc_res = resources.get("nproc")
    mem_val = _declared_value(mem_res, "link0_default_mem_gb")
    nproc_val = _declared_nproc(nproc_res)
    return {"num_atoms": int(summary["natom"]),
            "num_basis": int(summary["nbasis"]), "shell": shell,
            "suggested_compare_mem_gb": mem_val,
            "suggested_mem_source": _source_of(mem_res),
            "suggested_nproc": nproc_val,
            "suggested_nproc_source": _source_of(nproc_res)}


def _source_of(res: object) -> str:
    """声明来源：执行记录缺 resources / defaulted=true → default；
    defaulted=false → declared（不可解析回落已由 dispatcher 记账口径
    体现，原任务输入不可读时以 defaulted 字段为准，§2.4）。"""
    if not isinstance(res, dict) or res.get("defaulted"):
        return "default"
    return "declared"


def _declared_value(res: object, setting_key: str) -> float:
    """对照 %mem 预填值：执行记录 value（defaulted=false 且正值）；
    缺失/非法回落设置缺省值（存量条目缺 resources 同口径）。"""
    if isinstance(res, dict) and not res.get("defaulted"):
        val = res.get("value")
        if isinstance(val, (int, float)) and not isinstance(val, bool) \
                and val > 0:
            return float(val)
    return float(settings().get(setting_key))


def _declared_nproc(res: object) -> int:
    if isinstance(res, dict) and not res.get("defaulted"):
        val = res.get("value")
        if isinstance(val, int) and not isinstance(val, bool) and val > 0:
            return val
    return int(settings().get("link0_default_nproc"))


# ---------------- solname 溶剂速查（§2.5） ----------------

def solvents_list() -> dict:
    """GET /toolbox/solvents：懒加载 + 进程内缓存（键 = g16_root
    realpath）；解析 + NSolv/逐 id 交叉核对；失败不缓存。"""
    global _solvents_cache
    key = str(_g16_root().resolve())
    if _solvents_cache is not None and _solvents_cache.get("key") == key:
        return _solvents_cache["data"]
    solname = _tool_or_503("solname")
    out = _run_tool(solname, [], timeout_s=SOLNAME_TIMEOUT_S)
    data = _parse_solvents(out)
    _solvents_cache = {"key": key, "data": data}
    return data


def _parse_solvents(out: str) -> dict:
    """锚点解析 + 交叉核对（JN=1 行数 = NSolv 且每 id 恰一条 JN=1；
    JN 2/3/4 收别名；未识别行忽略的前向兼容）。"""
    nsolv: int | None = None
    order: list[int] = []
    by_id: dict[int, dict] = {}
    jn1_count = 0
    for ln in out.splitlines():
        m = _NSOLV_RE.match(ln)
        if m is not None and nsolv is None:
            nsolv = int(m.group(1))
            continue
        m = _SOLNAME_LINE_RE.match(ln)
        if m is None:
            continue  # 未识别行忽略（前向兼容，§9 风险 3）
        sid, jn, name = int(m.group(1)), int(m.group(2)), m.group(3).strip()
        entry = by_id.get(sid)
        if entry is None:
            entry = {"id": sid, "name": None, "aliases": []}
            by_id[sid] = entry
            order.append(sid)
        if jn == 1:
            jn1_count += 1
            if entry["name"] is not None:  # 同 id 重复 JN=1 → 防御 502
                raise err("G16_TOOL_FAILED",
                          "solname 解析核对失败（同一溶剂 id 出现多条"
                          "全名行）",
                          {"tool": "solname", "reason": "dup_jn1",
                           "solvent_id": sid}, http=502)
            entry["name"] = name
        elif jn in (2, 3, 4):
            entry["aliases"].append(name)
        # 其他 JN 值按未识别行忽略（前向兼容）
    if nsolv is None or jn1_count != nsolv or any(
            e["name"] is None for e in by_id.values()):
        raise err("G16_TOOL_FAILED",
                  "solname 解析核对失败（全名行数与头行 NSolv 不一致或"
                  "存在缺全名溶剂）",
                  {"tool": "solname", "reason": "cross_check_failed",
                   "nsolv": nsolv, "jn1_rows": jn1_count}, http=502)
    return {"count": len(by_id),
            "solvents": [by_id[i] for i in sorted(by_id)]}
