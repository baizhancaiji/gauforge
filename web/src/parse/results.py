"""结果解析服务（M3 B1，m3-plan §2.2/§4.4）：cclib 白名单解析 → analysis.json 形状。

- 仅 succeeded 执行进入本管道（状态机判定在 finalize 接线，B2）；
- 白名单属性提取（单位随 cclib 属性表），禁领域正则（roadmap §4）；
- 解析器自身绝不抛异常：解析异常/超时/success=false 一律 degraded 落地，
  个别块属性缺失以 missing[] 登记、对应块置空（不降级）；
- 输入只读（cclib 不改写原文件）；超时 60s（finalize 与 workspace-out 同款），
  以工作线程实现——超时即放弃等待返回 degraded（不杀线程，极端大文件场景
  单机可接受）；
- cclib 1.8.1 对 G16 发行版 DV 样本（开发版头部）的版本识别缺口以运行时
  垫片处置（A2 定稿，m3-plan §2.2：defaultdict 回落 "unknown"，仅未知后缀
  行为变化，带形态守卫，cclib 升级致形态不符时告警跳过、不静默）。

analysis.json 形状（本函数返回值，B2 原子写盘、B3 分块出端点）：
    {"result": <契约 Result>,
     "convergence": <契约 ConvergenceResponse 形状，块不可得时为空形>,
     "frequencies": <契约 FrequenciesResponse 形状>,
     "orbitals": <契约 OrbitalsResponse 形状>,
     "thermochemistry": {enthalpy, entropy, freeenergy, zpve} | None}
状态语义（计划 §2.2 降级链三分支的具体化）：
    parsed   = 解析成功且 success 为真且核心迹线（scfenergies）可得；
    degraded = ① 解析异常/超时 ② metadata.success 假或缺失（含无 Normal
               termination）③ scfenergies 缺失（任何 G16 输出必有 SCF，
               缺失即解析面残缺）；
    块属性缺失（如纯 opt/sp 任务无 vibfreqs、老版输出无 mosyms）不算缺失
    事故：blocks 置 false、state 保持 parsed；missing[] 仅 degraded 时登记
    （契约口径「degraded 时的缺失属性清单」），parsed 恒空。
"""
from __future__ import annotations

import collections
import concurrent.futures
import json
import math
import sys
from pathlib import Path

# 白名单属性（块级，缺失时登记 missing[] 并置空对应块；m3-plan §2.2 属性表）
_BLOCK_ATTRS = {
    "convergence": ("scfvalues", "geovalues", "scfenergies"),
    "frequencies": ("vibfreqs",),
    "orbitals": ("moenergies", "homos"),
    "thermochemistry": ("enthalpy", "entropy", "freeenergy", "zpve"),
}

PARSE_TIMEOUT_S = 60
# 超时降级 reason 前缀（analysis 域 422 details 判定的单一来源）
TIMEOUT_PREFIX = "解析超时"

_shimmed = False


def _ensure_cclib_shim() -> None:
    """cclib 1.8.1 DV 版本识别缺口垫片（幂等；A2 定稿 m3-plan §2.2）。

    `Gaussian, Inc.,` 引用行误触发版本识别，GDV 开发版的 year_suffix（如 DV）
    不在 YEAR_SUFFIXES_TO_YEARS 表 → KeyError 使整个解析中止。包一层缺失键
    回落 "unknown" 的 defaultdict：已识别版本逐位不变。cclib 升级若改掉该类
    属性形态，跳过垫片并告警（解析可能回落 degraded，显式不静默）。
    """
    global _shimmed
    if _shimmed:
        return
    from cclib.parser import gaussianparser

    table = getattr(gaussianparser.Gaussian, "YEAR_SUFFIXES_TO_YEARS", None)
    if isinstance(table, collections.defaultdict):
        _shimmed = True
        return
    if isinstance(table, dict):
        gaussianparser.Gaussian.YEAR_SUFFIXES_TO_YEARS = collections.defaultdict(
            lambda: "unknown", table)
        _shimmed = True
        return
    print("[parse] cclib 垫片跳过：YEAR_SUFFIXES_TO_YEARS 形态不符（上游已改？）",
          file=sys.stderr)


def _native(value: object) -> object:
    """numpy 标量/数组 → JSON 原生类型；NaN/Inf → None（json 兼容）。

    精确 type 判定：np.float64 等内建子类不放行（cclib 返回值须落成
    纯 float/int/bool，保证 analysis.json 纯原生类型），走 tolist/item 链。"""
    if value is None or type(value) in (str, bool, int, float):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    if isinstance(value, dict):
        return {k: _native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_native(v) for v in value]
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _native(tolist())
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _native(item())
        except (ValueError, TypeError):
            pass
    return str(value)


def _last_row(value: object) -> object:
    """判据阈值取末行：1D 数组（单步形态）原样返回，2D 数组取末行（cclib
    scftargets/geotargets 两态实测）。"""
    if value is None:
        return None
    shape = getattr(value, "shape", None)
    if shape is not None and len(shape) == 1:
        return value
    try:
        rows = list(value)
    except TypeError:
        return value
    return rows[-1] if rows else None


def _eV_to_hartree(value_eV: float) -> float:
    from cclib.parser.utils import convertor

    return float(convertor(value_eV, "eV", "hartree"))


def _parse_sync(path: Path) -> object:
    """同步解析单点入口（超时注入与测试桩替换点）。"""
    import cclib

    _ensure_cclib_shim()
    opener = cclib.io.ccopen(str(path))
    if opener is None:
        raise ValueError("无法识别的输出文件格式（ccopen 返回空）")
    return opener.parse()


def parse_output(path: Path, *, timeout_s: int = PARSE_TIMEOUT_S) -> dict:
    """G16 输出文件 → analysis.json 形状 dict。绝不抛出。

    path 只读；解析异常/超时/success 假均按 degraded 落地（见模块 docstring
    状态语义）。timeout_s 仅约束等待（线程不强杀）。
    """
    try:
        # 不用 with（__exit__ 会 join 线程令超时失效）；shutdown(wait=False)
        # 超时后立即返回，放弃等待（线程不强杀，极端大文件场景单机可接受）。
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(_parse_sync, path)
            data = future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            return _degraded(None, f"{TIMEOUT_PREFIX}（>{timeout_s}s）")
        except Exception as exc:  # noqa: BLE001  降级链①：解析异常落地不抛出
            return _degraded(None, f"{type(exc).__name__}: {exc}")
        finally:
            pool.shutdown(wait=False)
    except Exception as exc:  # noqa: BLE001  线程池自身故障兜底
        return _degraded(None, f"解析调度失败：{type(exc).__name__}: {exc}")

    metadata = dict(getattr(data, "metadata", None) or {})
    blocks_flag = {name: _block_available(data, attrs)
                   for name, attrs in _BLOCK_ATTRS.items()}
    success = metadata.get("success")
    no_energy = not blocks_flag["convergence"] or _no_scf_trace(data)
    if success is not True or no_energy:
        # 降级链②/③：success 假或缺失、或核心迹线残缺 → degraded（已得块保留）
        reason = ("metadata.success=%r（无 Normal termination 记录？）" % success
                  if success is not True else "scfenergies 缺失（解析面残缺）")
        result = _result_shape(data, metadata, blocks_flag,
                               _absent_attrs(data), "degraded", reason)
        return {"result": result, **_blocks_data(data, blocks_flag)}
    result = _result_shape(data, metadata, blocks_flag, [], "parsed", None)
    return {"result": result, **_blocks_data(data, blocks_flag)}


def _no_scf_trace(data: object) -> bool:
    energies = getattr(data, "scfenergies", None)
    return energies is None or len(energies) == 0


def _block_available(data: object, attrs: tuple) -> bool:
    """块可用性判定：任一属主属性可得即可用（缺谁的细账由 _absent_attrs 记）。"""
    return any(getattr(data, attr, None) is not None for attr in attrs)


def _absent_attrs(data: object) -> list[str]:
    """degraded 时的缺失属性清单：白名单块属主属性逐一点名（mosyms 等
    展示注记级属性不在此列，契约 nullable 承载）。"""
    return sorted({attr for attrs in _BLOCK_ATTRS.values() for attr in attrs
                   if getattr(data, attr, None) is None})


def _degraded(data: object | None, reason: str) -> dict:
    """降级链①：无 ccdata 可言（异常/超时），全部块置空形。"""
    empty_flag = {name: False for name in _BLOCK_ATTRS}
    result = {
        "state": "degraded", "parse_error": reason,
        "parser": _parser_meta(), "package": None, "method": None,
        "summary": {"natom": 0, "nmo": 0, "nbasis": 0,
                    "scf_energy_eV": None, "scf_energy_hartree": None,
                    "opt_converged": None, "freq_count": None,
                    "imaginary_freq_count": None, "homos": []},
        "blocks": empty_flag, "missing": [],
    }
    return {"result": result, **_empty_blocks()}


def _parser_meta() -> dict:
    import cclib

    return {"name": "cclib", "version": _native(cclib.__version__)}


def _result_shape(data: object, metadata: dict, blocks_flag: dict,
                  missing: list[str], state: str, parse_error: str | None) -> dict:
    energies = getattr(data, "scfenergies", None)
    energy_eV = float(energies[-1]) if energies is not None and len(energies) else None
    vibfreqs = getattr(data, "vibfreqs", None)
    homos = getattr(data, "homos", None)
    optdone = getattr(data, "optdone", None)
    optstatus = getattr(data, "optstatus", None)
    if optdone is not None:
        opt_converged = bool(optdone)
    elif optstatus is not None:
        opt_converged = False  # 有优化状态而无收敛记录 = 未收敛（实测 anisoles1）
    else:
        opt_converged = None    # 非优化任务
    return {
        "state": state, "parse_error": parse_error,
        "parser": _parser_meta(),
        "package": _package_meta(metadata),
        "method": _method_meta(metadata),
        "summary": {
            "natom": _natom(data), "nmo": _int_or_zero(getattr(data, "nmo", None)),
            "nbasis": _int_or_zero(getattr(data, "nbasis", None)),
            "scf_energy_eV": _native(energy_eV),
            "scf_energy_hartree": (_native(_eV_to_hartree(energy_eV))
                                   if energy_eV is not None else None),
            "opt_converged": opt_converged,
            "freq_count": _native(len(vibfreqs)) if vibfreqs is not None else None,
            "imaginary_freq_count": (_native(sum(1 for f in vibfreqs if f < 0))
                                     if vibfreqs is not None else None),
            "homos": _native([float(h) for h in homos]) if homos is not None else [],
        },
        "blocks": blocks_flag,
        "missing": sorted(set(missing)),
    }


def _natom(data: object) -> int:
    atomnos = getattr(data, "atomnos", None)
    if atomnos is not None:
        return int(len(atomnos))
    return _int_or_zero(getattr(data, "natom", None))


def _int_or_zero(value: object) -> int:
    """计数字段契约为必填 integer；degraded 无值时以 0 表「未知」（残缺故事
    由 parse_error/missing 承载）。"""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _package_meta(metadata: dict) -> dict | None:
    name = metadata.get("package")
    version = metadata.get("package_version")
    if name is None and version is None:
        return None
    return {"name": _native(name), "version": _native(version)}


def _method_meta(metadata: dict) -> str | None:
    """方法摘要：functional+basis_set 优先（实测 "B+HF-LYP/TZVP"），缺失回落
    methods 去重连接（"DFT"）。"""
    functional = metadata.get("functional")
    basis = metadata.get("basis_set")
    if functional and basis:
        return f"{functional}/{basis}"
    methods = sorted({str(m) for m in (metadata.get("methods") or [])})
    return "/".join(methods) if methods else None


def _blocks_data(data: object, blocks_flag: dict) -> dict:
    """各数据块（契约形状；不可得块为空形，可见性由 result.blocks 驱动）。"""
    return {"convergence": _convergence_block(data, blocks_flag["convergence"]),
            "frequencies": _frequencies_block(data),
            "orbitals": _orbitals_block(data),
            "thermochemistry": _thermo_block(data)}


def _empty_convergence() -> dict:
    """收敛块空形（降级全空形与块不可得共用单一实现）。"""
    return {"downsampled": False, "scf_trace": [], "scf_targets": [],
            "geo_trace": [], "geo_targets": [], "energy_series": []}


def _empty_blocks() -> dict:
    return {"convergence": _empty_convergence(),
            "frequencies": {"frequencies": []},
            "orbitals": {"nmo": 0, "nbasis": 0, "homos": [], "orbitals": []},
            "thermochemistry": None}


def _convergence_block(data: object, available: bool) -> dict:
    if not available:
        return _empty_convergence()
    scfvalues = getattr(data, "scfvalues", None)
    scf_trace = [{"geometry_step": i + 1, "cycles": _native(step.tolist())}
                 for i, step in enumerate([] if scfvalues is None else scfvalues)]
    scf_targets = _native(_last_row(getattr(data, "scftargets", None))) or []
    geovalues = getattr(data, "geovalues", None)
    geo_trace: list = []
    if geovalues is not None:
        geo_trace = [{"geometry_step": i + 1, "values": _native(row)}
                     for i, row in enumerate(geovalues)]
    geo_targets = _native(_last_row(getattr(data, "geotargets", None))) or []
    energies = getattr(data, "scfenergies", None)
    energy_series = [{"geometry_step": i + 1, "energy_eV": _native(e),
                      "energy_hartree": _native(_eV_to_hartree(float(e)))}
                     for i, e in enumerate([] if energies is None else energies)]
    return {"downsampled": False, "scf_trace": scf_trace,
            "scf_targets": scf_targets, "geo_trace": geo_trace,
            "geo_targets": geo_targets, "energy_series": energy_series}


def _frequencies_block(data: object) -> dict:
    vibfreqs = getattr(data, "vibfreqs", None)
    if vibfreqs is None:
        return {"frequencies": []}
    vibirs = getattr(data, "vibirs", None)
    vibsyms = getattr(data, "vibsyms", None)
    vibrmasses = getattr(data, "vibrmasses", None)

    def _at(arr: object | None, i: int) -> object:
        if arr is None or i >= len(arr):
            return None
        return _native(arr[i])

    return {"frequencies": [
        {"index": i + 1, "frequency_cm": _native(f),
         "ir_intensity": _at(vibirs, i), "symmetry": _at(vibsyms, i),
         "reduced_mass": _at(vibrmasses, i), "imaginary": bool(f < 0)}
        for i, f in enumerate(vibfreqs)]}


def _orbitals_block(data: object) -> dict:
    moenergies = getattr(data, "moenergies", None)
    homos = getattr(data, "homos", None)
    if moenergies is None or homos is None:
        return {"nmo": 0, "nbasis": 0, "homos": [], "orbitals": []}
    mosyms = getattr(data, "mosyms", None)
    spins = (["alpha", "beta"] if len(moenergies) > 1 else [None])
    orbitals: list = []
    for spin_group, spin in enumerate(spins):
        syms = mosyms[spin_group] if mosyms is not None \
            and spin_group < len(mosyms) else None
        for i, energy in enumerate(moenergies[spin_group]):
            orbitals.append({
                "index": i + 1, "energy_eV": _native(energy),
                "symmetry": _native(syms[i]) if syms is not None
                and i < len(syms) else None,
                "spin": spin})
    return {"nmo": _int_or_zero(len(moenergies[0])),
            "nbasis": _int_or_zero(getattr(data, "nbasis", None)),
            "homos": _native([float(h) for h in homos]), "orbitals": orbitals}


def _thermo_block(data: object) -> dict | None:
    attrs = _BLOCK_ATTRS["thermochemistry"]
    values = {attr: getattr(data, attr, None) for attr in attrs}
    if any(v is None for v in values.values()):
        return None
    return {attr: _native(float(v)) for attr, v in values.items()}


def dumps_compact(payload: dict) -> str:
    """analysis.json 落盘统一序列化（ensure_ascii=False、压缩分隔符）。"""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
