"""CREST ensemble 最小提取器与派发参数（M4 B10，m4-plan §2.3/§4.7）。

锁 crest 3.0.2 实测格式（A5 定稿留痕 fixtures `web/tests/fixtures/crest/`），
不做通用 crest 日志解析（roadmap §4 禁正则领域解析的既定豁免范围）：

- `crest_conformers.xyz`：多构象 XYZ 堆叠——每构象 = 原子数行 + 注释行
  （该构象绝对能量，Hartree、10 位小数）+ 坐标行（元素 x y z），按能量
  升序；构象数 = 注释行条目数。
- `crest.energies`：每行「序号 相对能量」，相对列实测 kcal/mol——仅作
  提取器交叉验证（|ΔE_hartree×627.509 − rel_kcal| < 0.1 不符即锚点漂移）。
- 能量取数单一来源 = crest_conformers.xyz 注释行 Hartree；相对 kJ/mol
  由 B11 聚合层按 (E_i − E_min) × 2625.4996 直算、不经 kcal/mol 中转。

crest 3.0.2 二进制静态内嵌 tblite 引擎（XTB_PATH 不消费，A5 实测）——
派发环境无需注入 XTB_PATH，与 GAUSS_* 天然零冲突。
"""
from __future__ import annotations

from pathlib import Path

# 单位换算单点（B11「单位换算单点」同源；物理基准 1 Eh = 2625.4996 kJ/mol，
# 风险 2 换算错误直接影响能量表结论——单测断言物理基准值）
HARTREE_KJ_MOL = 2625.4996
# crest.energies 相对列单位（实测 kcal/mol）与交叉验证容差
KCAL_MOL_PER_HARTREE = 627.509
_XCHECK_TOL_KCAL = 0.1

CONFORMERS_NAME = "crest_conformers.xyz"
ENERGIES_NAME = "crest.energies"
# 终态钩子提取产物锚文件（幂等重入判据，§2.3 恢复语义：重入先查锚、
# 有则跳过提取直接续建队）
ANCHOR_NAME = "crest_ensemble.json"


class CrestExtractError(Exception):
    """crest 产物锚点缺失或格式异常（workflow 记 failed，crest 原文可查）。"""


def crest_executable(crest_root: Path) -> Path:
    """crest 可执行定位与探测（缺失由调用方提交即拒，显式不静默）。"""
    return crest_root.expanduser() / "crest"


def extract_ensemble(run_dir: Path) -> dict:
    """提取构象系综：{"n": 构象数, "conformers": [{energy_hartree, coords}]。

    coords 为该构象的坐标行原文列表（元素 x y z——Gaussian 分子说明节
    坐标行同构，模板坐标替换直接可用）。锚点缺失/格式异常抛
    CrestExtractError。
    """
    xyz = run_dir / CONFORMERS_NAME
    if not xyz.is_file():
        raise CrestExtractError(f"锚点文件缺失：{CONFORMERS_NAME}")
    lines = xyz.read_text(encoding="utf-8", errors="replace").split("\n")
    conformers: list[dict] = []
    i, n = 0, len(lines)
    while i < n:
        head = lines[i].strip()
        if not head:
            i += 1
            continue
        try:
            natom = int(head)
        except ValueError:
            raise CrestExtractError(
                f"{CONFORMERS_NAME} 原子数行无法解析（第 {i + 1} 行）")
        if i + 1 + natom > n:
            raise CrestExtractError("构象坐标块截断（锚点格式漂移）")
        comment = lines[i + 1].strip()
        try:
            energy = float(comment.split()[0])
        except (IndexError, ValueError):
            raise CrestExtractError(
                f"构象注释行无 Hartree 能量锚点（第 {i + 2} 行：{comment[:40]}）")
        coords = [lines[i + 2 + k].strip() for k in range(natom)]
        conformers.append({"energy_hartree": energy, "coords": coords})
        i += 2 + natom
    if not conformers:
        raise CrestExtractError("无构象条目")
    # crest.energies 相对列交叉验证（锚点漂移哨兵）
    _crosscheck(run_dir, conformers)
    # 升序规约（锚点格式承诺能量升序，防御性排序保证 top-N 语义）
    conformers.sort(key=lambda c: c["energy_hartree"])
    return {"n": len(conformers), "conformers": conformers}


def _crosscheck(run_dir: Path, conformers: list[dict]) -> None:
    energies = run_dir / ENERGIES_NAME
    if not energies.is_file():
        return  # 相对能量表缺失不阻断（坐标+注释行已够构队取数）
    rels: list[float] = []
    for ln in energies.read_text(encoding="utf-8",
                                  errors="replace").split("\n"):
        parts = ln.split()
        if len(parts) >= 2:
            try:
                rels.append(float(parts[1]))
            except ValueError:
                pass
    if len(rels) != len(conformers) or not rels:
        raise CrestExtractError(
            f"{ENERGIES_NAME} 行数与构象数不一致（{len(rels)} vs "
            f"{len(conformers)}）")
    emin = min(c["energy_hartree"] for c in conformers)
    for c, rel in zip(conformers, rels):
        expect = (c["energy_hartree"] - emin) * KCAL_MOL_PER_HARTREE
        if abs(expect - rel) > _XCHECK_TOL_KCAL:
            raise CrestExtractError(
                "crest 相对能量交叉验证不符（锚点漂移）："
                f"expect≈{expect:.3f} kcal/mol, got={rel}")
