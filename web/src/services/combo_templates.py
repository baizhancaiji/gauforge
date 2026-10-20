r"""组合流精修模板校验与归一化（插波 3.2.0，m4-combo-template-deploy-plan §3.2）。

通用校验单点（批次 C 前端复用其结果）：保存时一次性执行、errors 全量返回
（422 VALIDATION_FAILED，details.errors[] 形态沿 {"field","line","reason",
"message"}；name/route 清空属「恢复初始值」语义，不报错）。

- 拼写校验：token 经括号/引号感知管道切分（B1 C3，与 check_route_spelling
  同管道——逗号/`!` 行内注释/`kw(opt)` 括号形/`@file`/`=` 两侧空格/引号值
  均为官方合法形态）、casefold **精确匹配** keywords.txt
  白名单（不采用近似命中判错），mode 参数 enforce/warn——3.4.0 起
  enforce 口径暂时屏蔽（输入勘误计划决策点 12：enforce/warn 分工未明且
  enforce 存在组合词值侧把关空洞——键名在典即放行，同类拼写错误裸词被
  拒、组合词仅警告），SPELLING_MODE 切为 warn：词典外 token 一律放行并
  随 notice.spelling_warnings 回传，keyword_not_in_dict 不再 422 拒绝；
  请求 ignore_spelling 字段保留但屏蔽期间不生效。恢复 enforce 须先解决
  值侧把关与缩写口径一致性（§2.8/§2.9 为恢复基线），另批裁决。
- 归一化（需求三）：route 保存时 casefold 落库、响应 notice 标注
  normalized；link0 三字段值域为数字与 proc-list（无字母词形），归一化
  仅 route 有实义。
- 温度（freq 联动，§0.4 口径 1）：route 含 freq（等值或 freq= 前缀）而
  未配置温度（temp=/temperature= 均算已配置）→ 自动补
  temperature=298.15；已配置 → 值须为单值正数（开尔文，官方仅单值语法）。
"""
from __future__ import annotations

import re

from .. import config
from ..engine.workspace import _cpu_list_count
from ..errors import validation_failed
from ..parse.keywords import (check_route_duplicates, check_route_options,
                              load_keywords, token_in_dict, tokenize_route)
from .dependencies import parse_link0_refs

# 每核内存下限 GB（§0.4 口径 3）
PER_CORE_MEM_GB_FLOOR = 1.0

# 拼写校验 mode（enforce/warn；见模块 docstring 切换纪律——3.4.0 起为
# warn，enforce 恢复另批裁决，决策点 12）
SPELLING_MODE = "warn"

# 温度值：单值正数（开尔文）；官方无列表/负值语法（KB 核验 2026-10-13）
_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")
_DEFAULT_TEMPERATURE = "temperature=298.15"


def _verr(field: str, reason: str, message: str, line: int = 1) -> dict:
    return {"field": field, "line": line, "reason": reason,
            "message": message}


def _text(value: object) -> str | None:
    """string|null 载荷 → 去壳文本（缺省/空 → None=未配置语义）。"""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def validate_and_normalize(template_id: int, data: dict, *,
                           mode: str = SPELLING_MODE) -> tuple[dict, dict]:
    """校验并归一化一次模板保存载荷（PUT 全量替换语义）。

    返回 (fields, notice)：fields = {name, route, nproc(int|None),
    mem_gb(float|None), cpu(str|None), is_default(bool)}（存储层形态；
    is_default 仅表达「本请求置默认」，False 时 repo 保持现有归属——契约：
    缺省/false 不改变默认）；
    notice = {temp_applied, normalized, spelling_warnings?}（词典外 token
    清单，warn 口径一律携带——3.4.0 起 enforce 屏蔽）。任一校验失败 →
    validation_failed(errors)（全量一次返回）。
    """
    errors: list[dict] = []

    # ---- name：缺省/空 → 恢复「配置n」（清空恢复初始值语义，不报错） ----
    name = _text(data.get("name")) or f"配置{template_id}"

    # ---- route：缺省/空 → 恢复初始；文法（单行/# 开头/无空行） ----
    route = _text(data.get("route")) or config.COMBO_TEMPLATE_INITIAL_ROUTE
    lines = route.split("\n")
    if len(lines) > 1:
        errors.append(_verr("route", "multi_line_route",
                            "route 须为单行文本"))
    for k, ln in enumerate(lines, 1):
        if not ln.strip():
            errors.append(_verr("route", "blank_line_in_route",
                                "route 内不得出现空行", k))
    if not lines[0].lstrip().startswith("#"):
        errors.append(_verr("route", "route_must_start_with_hash",
                            "route 须以 # 开头"))

    route_cf = route.casefold()
    # C3 token 化：括号/引号感知（与 check_route_spelling 同管道），模板
    # route 为单行，token 行号恒 1
    tokens = [t for _, t in tokenize_route(route_cf)]

    # ---- 拼写（精确白名单；3.4.0 起 enforce 屏蔽仅 warn——SPELLING_MODE
    # 为单一切换点，mode="enforce" 分支仅恢复后可达，决策点 12） ----
    words = load_keywords()
    oov = [t for t in tokens if not token_in_dict(t, words)]
    if mode == "enforce" and oov and not bool(data.get("ignore_spelling")):
        errors.extend(_verr("route", "keyword_not_in_dict",
                            f"词典外关键词：{t}") for t in oov)

    # ---- 重复关键字（B3 G2：非阻断，enforce/warn 均随 notice 携带；
    # 裸形+选项形追加取值与 IOp 并写豁免与 check_route_duplicates 同源） ----
    duplicates = check_route_duplicates(route_cf)

    # ---- 子选项归属（B5 G8：非阻断，随 notice.route_option_warnings 携带；
    # 仅 warn——面⑤选项覆盖非全量，决策点 6） ----
    option_warnings = check_route_options(route_cf)

    # ---- 温度（freq 联动；token 头部判定覆盖 freq / freq=x / freq(…) /
    # freq (…) 全形态——R2 审查整改，不漏 C3 放行的无等号括号形） ----
    has_freq = any(
        t.partition("=")[0].split("(", 1)[0] == "freq" for t in tokens)
    has_temp = "temp=" in route_cf or "temperature=" in route_cf
    temp_applied = False
    if has_freq and not has_temp:
        route_cf = f"{route_cf} {_DEFAULT_TEMPERATURE}"
        temp_applied = True
    if has_temp:
        for t in tokens:
            key, _, val = t.partition("=")
            if key in ("temp", "temperature"):
                if not val or not _NUM_RE.match(val) or float(val) <= 0:
                    errors.append(_verr(
                        "route", "temp_value_invalid",
                        f"温度须为单值正数（开尔文）：{t or '空值'}"))

    # ---- link0 三字段（值级，string|null 文本形态） ----
    nproc_txt = _text(data.get("nproc"))
    mem_txt = _text(data.get("mem_gb"))
    cpu_txt = _text(data.get("cpu"))

    nproc: int | None = None
    if nproc_txt:
        if nproc_txt.isdigit() and int(nproc_txt) > 0:
            nproc = int(nproc_txt)
        else:
            errors.append(_verr("nproc", "nproc_not_positive_int",
                                "%nprocshared 须为正整数"))

    mem_gb: float | None = None
    if mem_txt:
        if _NUM_RE.match(mem_txt) and float(mem_txt) > 0:
            mem_gb = float(mem_txt)  # 模板域限 GB 单一单位记账（刻意简化）
        else:
            # %mem=0 拒绝（决策点 8：模板 mem_gb 阻断）
            errors.append(_verr("mem_gb", "mem_value_invalid",
                                "%mem 须为正数（GB 数值）"))

    cpu: str | None = None
    cpu_count: int | None = None
    if cpu_txt:
        cpu_count = _cpu_list_count(cpu_txt)
        if cpu_count is None:
            errors.append(_verr("cpu", "cpu_list_invalid",
                                "%cpu 须为处理器列表（如 0,1,2 / 0-5）"))
        else:
            cpu = cpu_txt

    # ---- 交叉校验：mem×核数、nproc×cpu（§0.4 口径 3/5） ----
    effective_cores = nproc if nproc is not None else cpu_count
    if mem_gb is not None and effective_cores is not None \
            and mem_gb < effective_cores * PER_CORE_MEM_GB_FLOOR:
        errors.append(_verr(
            "mem_gb", "mem_below_per_core_floor",
            f"每核内存低于下限：{mem_txt}GB / {effective_cores} 核"
            f"（下限 {effective_cores * PER_CORE_MEM_GB_FLOOR:g}GB）"))
    if nproc is not None and cpu_count is not None and cpu_count < nproc:
        errors.append(_verr(
            "cpu", "nproc_cpu_mismatch",
            f"%cpu 核编号总数（{cpu_count}）须 ≥ %nprocshared（{nproc}）"))

    # ---- 符号引用拒绝（精修模板会被 validate_queue_members 拒，保存前置拦截；
    # link0 形文本复用 dependencies.parse_link0_refs 判定，route 无 % 行文法
    # 以 @task:/@exec: 子串同判） ----
    if "@task:" in route_cf or "@exec:" in route_cf:
        errors.append(_verr("route", "link0_symbol_ref_forbidden",
                            "精修模板不得携带符号引用（@task:/@exec:）"))
    link0_lines = [ln for ln in (
        f"%nprocshared={nproc}" if nproc is not None else "",
        f"%mem={_num_txt(mem_gb)}GB" if mem_gb is not None else "",
        f"%cpu={cpu}" if cpu is not None else "") if ln]
    if parse_link0_refs("\n".join(link0_lines)):
        errors.append(_verr("link0", "link0_symbol_ref_forbidden",
                            "精修模板不得携带符号引用（@task:/@exec:）"))

    if errors:
        raise validation_failed(errors)

    fields = {"name": name, "route": route_cf, "nproc": nproc,
              "mem_gb": mem_gb, "cpu": cpu,
              "is_default": bool(data.get("is_default"))}
    notice: dict = {"temp_applied": temp_applied,
                    "normalized": route.casefold() != route}
    if oov:
        notice["spelling_warnings"] = oov
    if duplicates:
        notice["route_duplicates"] = duplicates
    if option_warnings:
        notice["route_option_warnings"] = option_warnings
    return fields, notice


def _num_txt(v: float) -> str:
    """GB 数值去尾零（契约规范字符串形态，与 engine.workspace._fmt_gb 同规）。"""
    return str(int(v)) if float(v).is_integer() else f"{v:g}"
