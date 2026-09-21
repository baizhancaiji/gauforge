"""Gaussian 输入文件解析：为 Web 预览拆解 Link0/Route/标题/电荷/几何，并给出警告。"""
import re

RE_LINK0 = re.compile(r"^%(?P<key>[A-Za-z]+)\s*=\s*(?P<value>\S+)\s*$")
RE_CHARGE = re.compile(r"^(?P<q>-?\d+)\s+(?P<m>-?\d+)$")
RE_ELEM = re.compile(r"^[A-Z][a-z]?$")
RE_INT = re.compile(r"^[+-]?\d+$")


def _new_job():
    return {"link0": [], "route": "", "title": "", "charge": None, "mult": None,
            "atoms": [], "zmat": [], "extra": []}


def parse_input(text: str) -> dict:
    """按行状态机解析 Gaussian 输入。支持 --Link1-- 多任务；Link0 与 Route 之间
    允许没有空行（GaussView 生成的文件就是这样）。"""
    jobs = []
    current = None
    phase = "link0"  # link0 -> route -> title -> chargemult -> geom -> extra

    def finish():
        if current and (current["route"] or current["atoms"] or current["extra"]):
            jobs.append(current)

    for raw in text.replace("\r\n", "\n").split("\n"):
        s = raw.strip()
        if s == "--Link1--":
            finish()
            current, phase = None, "link0"
            continue
        if s == "":
            if phase == "route":
                phase = "title"
            elif phase == "title":
                phase = "chargemult"
            elif phase == "geom":
                phase = "extra"
            continue

        if current is None:
            current = _new_job()

        m = RE_LINK0.match(s)
        if m and phase == "link0":
            current["link0"].append({"key": m.group("key").lower(),
                                     "value": m.group("value")})
            continue

        if phase == "link0":
            if s.startswith("#"):
                current["route"] = s
                phase = "route"
            else:  # 不认识的行，当作 Route 后内容兜底
                current["route"] = s
                phase = "route"
            continue

        if phase == "route":
            current["route"] += " " + s
            continue

        if phase == "title":
            current["title"] = (current["title"] + " " + s).strip()
            continue

        if phase == "chargemult":
            mc = RE_CHARGE.match(s)
            if mc:
                current["charge"], current["mult"] = int(mc.group("q")), int(mc.group("m"))
                phase = "geom"
                continue
            phase = "geom"  # 电荷行缺失，该行按几何处理

        if phase == "geom":
            parts = s.split()
            # 直角坐标: 元素 x y z [ONIOM 层...]
            if len(parts) >= 4 and not RE_INT.match(parts[1]):
                try:
                    current["atoms"].append({
                        "symbol": parts[0],
                        "xyz": [float(parts[1]), float(parts[2]), float(parts[3])],
                        "extra": parts[4:]})
                    continue
                except ValueError:
                    pass
            # Z-矩阵: 元素 [参考原子 距离 [参考原子 角度 [参考原子 二面角]]]
            # 参考原子是纯整数（变量形式的 Z-矩阵暂不支持，归入 extra）
            if RE_ELEM.match(parts[0]) and (
                    len(parts) == 1 or RE_INT.match(parts[1])):
                current["zmat"].append(s)
                continue
            current["extra"].append(s)
            continue

        if phase == "extra":
            current["extra"].append(s)

    finish()

    for j in jobs:
        j["natoms"] = len(j["atoms"]) + len(j["zmat"])
        j["format"] = "zmatrix" if j["zmat"] and not j["atoms"] else (
            "cartesian" if j["atoms"] else "empty")

    link0 = jobs[0]["link0"] if jobs else []
    l0 = {d["key"]: d["value"] for d in link0}
    warnings = []
    if "\r" in text:
        warnings.append("检测到 Windows 换行符 (CRLF)，提交时会自动转为 Unix 格式")
    if re.search(r"%[^\n]+\n+\s*#", text):
        warnings.append("Link0 (%行) 与 Route (#行) 之间缺少空行，Gaussian 会解析失败")
    _lines = text.split("\n")
    if jobs and (_lines[-1].strip() or (len(_lines) >= 2 and _lines[-2].strip())):
        warnings.append("文件末尾缺少终止空行（最后一段后需留一个空行，否则 Gaussian 读到文件尾会报错）")
    if not jobs or not jobs[0]["route"]:
        warnings.append("未找到 Route 段（# 开头的关键词行），文件可能不是 Gaussian 输入")
    if any(j["charge"] is None for j in jobs):
        warnings.append("缺少电荷/自旋多重度行")
    if any(j["natoms"] == 0 for j in jobs):
        warnings.append("几何结构为空（支持直角坐标和整数参考的 Z-矩阵，变量式 Z-矩阵暂不支持）")
    if any(j["format"] == "zmatrix" for j in jobs):
        warnings.append("检测到 Z-矩阵几何：预览只显示连接性，不显示三维坐标")
    if "nprocshared" not in l0:
        warnings.append("未指定 %NProcShared，将只使用 1 个核心")
    elif l0.get("nprocshared", "1").isdigit() and int(l0["nprocshared"]) > 8:
        warnings.append(f"%NProcShared={l0['nprocshared']} 较大，注意与其他任务错开核心")
    if l0.get("chk"):
        warnings.append(f"使用 checkpoint 文件 {l0['chk']}，将生成在任务目录下")

    return {"jobs": jobs, "njobs": len(jobs), "link0": l0, "warnings": warnings,
            "valid": bool(jobs) and all(
                j["route"] and j["natoms"] and j["charge"] is not None for j in jobs)}
