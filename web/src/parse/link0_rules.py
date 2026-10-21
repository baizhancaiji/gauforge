"""Link 0 规则单点（输入勘误计划 G5，B4 下沉）：值域、指令文法、proc-list。

parse 层（parse_input 警告）与 services/engine（编辑保存阻断、记账换算）
共用同一实现，杜绝两套口径漂移（计划 §2.7 项 2——避免 parse 反向依赖
services/engine 形成循环导入，正则与解析核心下沉本模块）。

官方规则（link0/running 页，§1.4）：
- 单条 Link 0 命令长度上限 500 字符；
- %mem 值域 KB/MB/GB/TB/KW/MW/GW/TW（无空格；默认无单位=8 字节字），
  工程上要求 >0（零内存无实际意义，决策点 8）；
- 无等号指令合法：%save/%errorsave/%nosave/%kjob L<n> [m]/%subst L<n> dir/
  %usessh/%usersh；含多个 = 的取值形（%gpucpu=0-3=0-1,16-17、
  %oldmatrix=(file,i4lab)）按「首个 = 后整体为值」解析；
- 未知指令/同名重复 → 非阻断（决策点 7，历史模板可能含自定义指令）；
- %cpu proc-list 支持区间步长 /n 后缀（0-5/2 = 每隔 2 取一个，共 3 个）。
"""
from __future__ import annotations

import re

# %mem 值：数值 + 可选单位（官方值域 KB/MB/GB/TB/KW/MW/GW/TW；无单位=
# 8 字节字；W/B 单独字母形非官方值域——G5 决策点 2 收紧删除）
MEM_VALUE_RE = re.compile(r"^\d+(?:\.\d+)?(?:KB|MB|GB|TB|KW|MW|GW|TW)?$",
                          re.IGNORECASE)

# Link 0 单行长度上限（官方 link0 页明文）
LINE_LENGTH_CAP = 500

# 记账换算（GB；1024 进制、1 word = 8 字节）——与值域共用同一单位集。
# 单位语义按官方 word 口径：KW=1024 words=8KB、MW=8MB、GW=8GB、TW=8192GB
# （旧表 mw 差 1024 倍且缺 kw 键——%mem=1KW 会 KeyError，B4 一并修正；
# QW 非官方值域删除）。
MEM_TO_GB = {"kb": 1 / 1024**2, "mb": 1 / 1024, "gb": 1.0, "tb": 1024.0,
             "kw": 8 / 1024**2, "mw": 8 / 1024, "gw": 8.0, "tw": 8192.0,
             "": 8 / 1024**3}

# 已知指令集（官方 link0 页导出；值形指令取「首个 = 前头部」比对）
KNOWN_DIRECTIVES = frozenset((
    "chk", "oldchk", "schk", "rwf", "int", "d2e", "mem", "nproc",
    "nprocshared", "cpu", "nproclinda", "gpucpu", "lindaworkers",
    "debuglinda", "save", "errorsave", "nosave", "kjob", "subst",
    "usessh", "usersh", "ssh", "oldmatrix", "oldrawmatrix", "oldraw",
    # 早期同义 %nproc（手册 %cpu 条目 replaces the earlier %nprocshared
    # and %nproc）与实测可用截断形 %nprocshare——blocks 缺失判定同口径
    "nprocshare",
))

# 无等号指令（后跟空格分隔的位置参数，如 %kjob l502 2、%subst l913 dir）
_NO_EQ_DIRECTIVES = frozenset(("kjob", "subst", "usessh", "usersh"))


def directive_head(body: str) -> tuple[str, str]:
    """>% 行体（去 % 前缀）→ (指令头, 值串)。

    含 = 按「首个 = 后整体为值」切分（%gpucpu=0-3=0-1、%oldmatrix=(f,i4lab)
    的多 = 取值不二次切分）；无 = 按首空白词取指令头（%kjob l502 2、
    %subst l913 dir 等官方无等号位置参数形态，其余词为位置参数）。"""
    body = body.strip().lstrip("%").strip()
    key, sep, val = body.partition("=")
    if sep:
        return key.strip().casefold(), val.strip()
    parts = body.split(None, 1)
    if not parts:
        return "", ""
    return parts[0].casefold(), (parts[1].strip() if len(parts) > 1 else "")


def check_link0_lines(lines: list[str], *,
                      line_offset: int = 0) -> list[dict]:
    """Link 0 行集 → 非阻断警告（G5：值域/行长/指令文法/重复）。

    line_offset：link0 块首行之前的全文件行数（blocks.parse_input 传块首
    0 起行号）——警告 line = line_offset + 块内 1 起序号 = 全文件绝对行号
    （审查整改 R1，G0 口径；重复指令取该指令首次出现的行）。编辑保存
    通道的阻断校验（candidates._validate_section）
    不在本函数——保存按节阻断并使用端点 reason 词表；本函数产出供
    parse_input 统一消费（预览/导入/提交/分块保存响应的 warnings 通道）。"""
    warnings: list[dict] = []
    seen: dict[str, tuple[int, int]] = {}  # head -> (出现次数, 首次块内行号)
    for idx, raw in enumerate(lines, 1):
        body = raw.strip()
        line = idx + line_offset
        if len(body) > LINE_LENGTH_CAP:
            warnings.append({"line": line, "keyword": "",
                             "kind": "link0_line_too_long",
                             "message": f"Link 0 命令超长（{len(body)} 字符，"
                                        f"官方上限 {LINE_LENGTH_CAP}）"})
        head, val = directive_head(body)
        if not head:
            continue
        if head not in KNOWN_DIRECTIVES:
            warnings.append({"line": line, "keyword": head,
                             "kind": "link0_directive_unknown",
                             "message": f"未知 Link 0 指令「%{head}」"
                                        "（官方指令集外，请确认拼写）"})
            continue
        seen[head] = (seen.get(head, (0, idx))[0] + 1, seen.get(head, (0, idx))[1])
        if head == "mem":
            num = val.split(",")[0] if val else ""
            m = MEM_VALUE_RE.match(num)
            # 值域内且数值 >0（%mem=0 拒绝——决策点 8；官方值域外 W/B 等
            # 单位由正则拒绝）
            if not m or float(re.match(r"^\d+(?:\.\d+)?", num).group()) <= 0:
                warnings.append({"line": line, "keyword": "%mem",
                                 "kind": "link0_value_invalid",
                                 "message": "%mem 值须为正数（可选单位 "
                                            "KB/MB/GB/TB/KW/MW/GW/TW）"})
        elif head in ("nproc", "nprocshared", "nprocshare"):
            # 空值（%nproc= 或无值裸形）与非法值同告警（B14 复审 R3：
            # 与编辑保存 empty_value 阻断、%mem= 空值既有告警同源拉齐）
            ok = False
            if val:
                try:
                    ok = int(val) > 0
                except ValueError:
                    ok = False
            if not ok:
                warnings.append({"line": line, "keyword": f"%{head}",
                                 "kind": "link0_value_invalid",
                                 "message": "%nproc 系值须为正整数"})
        elif head == "cpu":
            # 空值同告警（R3 同根因顺带拉齐：`if val and …` 短路使 %cpu=
            # 空值静默，与矩阵「%cpu 列表：警告」不符）
            if not val or cpu_list_count(val) is None:
                warnings.append({"line": line, "keyword": "%cpu",
                                 "kind": "link0_value_invalid",
                                 "message": "%cpu 值须为处理器列表"
                                            "（如 0,1,2 / 0-5 / 0-5/2）"})
    for head, (count, first_idx) in seen.items():
        if count > 1:
            warnings.append({"line": first_idx + line_offset,
                             "keyword": f"%{head}",
                             "kind": "link0_directive_duplicate",
                             "message": f"Link 0 指令「%{head}」重复出现 "
                                        f"{count} 次（后值覆盖前值，请确认)"})
    return warnings


_CPU_RANGE_RE = re.compile(r"^(\d+)-(\d+)(?:/(\d+))?$")


def cpu_list_count(raw: str) -> int | None:
    """%cpu proc-list → 核数（官方 run 页：单项/列表/区间/混合/区间步长 /n）。

    0-5/2 = 从 0 起每隔 2 取一个（0,2,4）共 3 个。无法识别返回 None。"""
    total = 0
    for tok in raw.replace(" ", "").split(","):
        if not tok:
            return None
        m = _CPU_RANGE_RE.match(tok)
        if m:
            a, b, step = int(m[1]), int(m[2]), int(m[3] or 1)
            if b < a or step < 1:
                return None
            total += (b - a) // step + 1
            continue
        try:
            int(tok)
        except ValueError:
            return None
        total += 1
    return total or None


def mem_to_gb(raw: str) -> float | None:
    """G16 %mem 值 → GB 浮点（官方值域单位集）；无法识别返回 None。

    无单位按 8 字节字（word）换算。"""
    tok = raw.strip()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([A-Za-z]*)$", tok)
    if not m:
        return None
    unit = m[2].lower()
    if unit not in MEM_TO_GB:
        return None
    try:
        return float(m[1]) * MEM_TO_GB[unit]
    except (ValueError, OverflowError):
        return None
