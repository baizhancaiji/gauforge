#!/usr/bin/env python3
"""B6 G10-b 复核裁决明细生成（输入勘误计划 §2.13 三路差集审计的逐条裁决）。

对复核面（review_candidates.json，475 条）逐条打标处置：
- admit_rule：面⑦句式规则覆盖入典（synonym/says-to/default 句式，正式
  实现见 scripts/extract_keywords.py 面⑦）；
- admit_manual：人工复核通过、规则覆盖不足，入手工补录清单
  （extract_keywords.py B6_MANUAL_OPTIONS）；
- admit_impl：判定链实现侧处置（field 值形白名单）；
- reject_a：A 类旧形态（G03 时代，现行手册已删，维持预期警告）；
- reject_noise：散文噪声（句式词/方法名/单位/键名/引文锚/跨页载体错位/
  值形参数/obsolete 页字面），维持预期警告或本不产生警告；
- reject_pos：唯一前缀判活等判定链已零警告（审计差集假阳性）。

裁决依据：docs/plans/audit/ 三路 JSON 的 snippet + keyword 页原文核验
（复核过程逐键对照手册原文，结论见
docs/plans/input-verify-gap-b6-prose-audit.md）。纯静态，幂等。
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 人工复核通过的手工补录清单（与 extract_keywords.py B6_MANUAL_OPTIONS
# 保持一致；键=选项 casefold）
MANUAL = frozenset("""
freq=readanharmonic
freq=readhindered
freq=readnm
freq=noreadnm
freq=noreadnormalmodes
freq=noselectnm
freq=noselectnormalmodes
nmr=cgst
casscf=slaterdet
casscf=spinorbit
ccsd=maxcyc
integral=superfine
integral=ultrafine
cis=ivoguess
cis=noneqsolv
cis=nonac
cis=nononadiabaticcoupling
geom=notest
geom=readfreeze
geom=rdfreeze
admp=nobandgap
admp=cholesky
bomd=microcanonical
bomd=fixed
bomd=local
bomd=gradonly
bomd=gradientonly
cas=nofulldiag
cas=nocpmcscf
stable=noopt
symmetry=noscf
guess=nofock
guess=noforceabeliansymmetry
scf=nodiis
scf=nodamp
scf=nodsymm
scf=noidsymm
scf=nofermi
scf=nofinaliteration
scf=noincfock
scf=nosave
scf=nosavekpoint
cphf=norecursivediis
cphf=nostatic
opt=noexpert
opt=nooptproduct
opt=nooptreactant
opt=noquadmacro
opt=mic103
opt=mic120
opt=scaling
sacci=cationdoublet
sacci=aniondoublet
sacci=doublet
sacci=triplet
sacci=quartet
sacci=quintet
sacci=sextet
sacci=septet
sacci=full
sacci=leveltwo
sacci=levelthree
sacci=readwindow
population=saveesp
population=savemulliken
population=savecm5
population=savenpa
population=allorbitals
population=hirshfeldee
output=rotatationalconstants
output=spinrotation
mm=oldqeq
mm=roff
pseudo=coreless
densityfit=noniterative
gfinput=coulomb
""".split())

# A 类旧形态（G03 时代官方已删，决策点 11：预期警告）
REJECT_A = frozenset("""
geom=modela
geom=coord
geom=modlargeredundant
geom=oldredundant
geom=nocrowd
geom=gicnew
opt=coord
opt=big
opt=enonly
opt=fp
opt=gdiis
opt=grad
opt=mndofc
opt=ms
opt=unitfc
opt=backqx
scf=camp-king
scf=noextrap
scf=sleazy
scf=verysleazy
scf=novaracc
scf=noincore
scf=useoao
scrf=dpcm
scrf=oldpcm
scrf=numer
scrf=cards
units=bohr
ept=d2
freq=hindrot
freq=davidson
pseudo=mmread
ccsd=fc1
transformation=conventional
transformation=new2pdm
transformation=old2pdm
stable=symm
""".split())

# 判定链实现侧处置：field 向量取值形态（Field=Z-100 等）加入值形白名单
IMPL = frozenset("""
field=xxyz-20
field=y-50
field=z+100
field=z-100
""".split())

# 唯一前缀判活等零警告（差集假阳性，不出现在判定链过滤后的复核面，
# 兜底标注）
REJECT_POS = frozenset("""
opt=modredun
opt=readopt
""".split())


def classify(form: str, sources: list[str]) -> tuple[str, str]:
    cf = form.casefold()
    if cf in MANUAL:
        return "admit_manual", "人工复核通过（手册句面/字面实锤），入 B6 手工补录清单"
    if cf in REJECT_A:
        return "reject_a", "A 类旧形态（G03 时代，现行手册已删）——预期警告，决策点 11"
    if cf in IMPL:
        return "admit_impl", "field 向量取值形态——值面非选项面，field 键入 G8 值形白名单"
    if cf in REJECT_POS:
        return "reject_pos", "判定链唯一前缀/整词已判活（审计差集假阳性）"
    if cf in RULE_COVERED:
        return "admit_rule", "面⑦句式规则提取入典（B6 G10-b，词典重生成覆盖）"
    return "reject_noise", "散文噪声（句式词/方法名/单位/键名/引文锚/跨页载体错位/值形参数）——不入典"


def main() -> int:
    cands = json.loads((HERE / "review_candidates.json").read_text("utf-8"))
    # 闭环验证：以重生成后的词典（面⑦+手工补录生效）重跑判定链，
    # 复核面中已零警告的形态即入典生效（admit_rule/admit_manual 并集）
    import sys
    sys.path.insert(0, str(HERE.parents[2]))
    from web.src.parse.keywords import load_keywords, check_route_options
    words = load_keywords(refresh=True)
    global RULE_COVERED
    RULE_COVERED = frozenset()
    rule_hits: list[str] = []
    for c in cands:
        form = f"{c['key']}={c['option']}"
        if form.casefold() not in MANUAL | REJECT_A | IMPL | REJECT_POS \
                and not check_route_options(form, dictionary=words):
            rule_hits.append(form.casefold())
    RULE_COVERED = frozenset(rule_hits)

    lines = []
    for c in cands:
        form = f"{c['key']}={c['option']}"
        verdict, why = classify(form, c["sources"])
        srcs = "+".join(s.replace("path1_literal", "P1")
                        .replace("path2_prose", "P2")
                        .replace("path3_corpus", "P3")
                        for s in c["sources"])
        lines.append(f"{form}\t{srcs}\t{verdict}\t{why}")
    (HERE / "review_decisions.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    from collections import Counter
    dist = Counter(l.split("\t")[2] for l in lines)
    print(f"{len(lines)} 条裁决 → review_decisions.txt")
    for k, v in dist.most_common():
        print(f"  {v:4d}  {k}")
    # 残余警告（reject 类中判定链仍警告的形态数——A 类预期警告 + 噪声）
    residual = [l for l in lines if l.split("\t")[2].startswith("reject")
                and check_route_options(l.split("\t")[0], dictionary=words)]
    print(f"reject 类中仍产生警告（A 类预期 + 噪声噪声面）：{len(residual)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
