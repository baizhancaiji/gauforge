# 面⑧正文提及选项 R2 复扫审计留痕（B6 续）

> 批次：输入勘误缺口补齐计划 B6 续（用户裁决扩面，3.4 unreleased）。
> 触发：3.4.0 用户实测误报——真实在用输入文件
> `opt=(qst2,calcfc,noeigentest,maxstep=15)`（QST2 过渡态标准组合）中
> NoEigenTest 被报「疑似非 OPT 的官方选项」。官方 Opt 页明载
> NoEigenTest 为合法选项，属词典缺口误报。
> 审计日期：2026-10-22。知识库：gaussian-kb 结构化数据（与 gaussian-kb
> MCP 同源同数）。状态：已实施并验收（验收留痕见本文 §4；
> CHANGELOG 3.4 unreleased fixed/parse 条目）。

## 1. 根因

词典生成（scripts/extract_keywords.py）面⑤只提取 Options 章节 `####`
独立标题条目、面⑦只覆盖 synonym/says-to/default 四句式；官方手册大量
No-对选项以正文句式记载（「EigenTest requests and NoEigenTest
suppresses」），且部分选项以表格行、页首句、空格标题记载，均不达提取
面。B6 三路审计的 P2 句式锚未覆盖此类，人工裁决亦漏（B6 曾将
td=NoIVOGuess、geom=NoKeepConstants、geom=NoGIC、opt=NoMicro、
guess=NoTranslate 误判为噪声，geom=NoCrowd、scf=NoInCore、scf=NoVarAcc、
ept=D2 误判为 G03 已删的 A 类）。

## 2. 方法（scripts/audit_prose_options_r2.py，入库幂等）

- 路A：keyword 页 Options 章节 #### 条目正文全部大写词（不限句式）；
- 路B：keyword 页全文 No* 字面（含章节外，标记区分）；
- 差集基准为入库词典组合词；B6 裁决留痕作先验——reject_a 沿用（R2
  逐条复查后翻案 4 条），reject_noise 对 No* 不采信（误拒实证）。

裁决时词典 1345 词，候选 936（No* 72），逐条对照手册原文裁决；裁决
全录见 [audit/review_decisions_r2.txt](audit/review_decisions_r2.txt)，
候选全集与上下文见 audit/r2_candidates.json（修复后重跑 = 残余维持
警告面 874 条）、r2_worksheet.txt。

## 3. 处置（词典 1345 → 1419，+74）

- 面⑧新句式规则（extract_keywords.py）：成对动词 No-对句、等价句
  （X is equivalent to Y [and Z]，含主语翼）、Use-X-to 指令句、option
  指称句（正逆序）、主语并列行为句、No* 定义动词句、单主语 request
  直述句、one-of 官方枚举句；_SYN_WITH 补对象翼；停用表补 geom、
  pass0grid 两特例。
- 面⑤补强：逗号枚举标题逐段归一（`#### Raff, Raf1, Raf2, Raf3`）。
- R2 手工补录（R2_MANUAL_OPTIONS）：表格行（scrf Dis/Rep/Cav 系）、
  页首句（densityfit NoDenFit/NoDensityFit）、章节外正文（integral
  NoDKH/NonRelativistic）、无数义动词句（scf NoVarAcc、guess
  NoTranslate）、B6 翻案（ept D2）。
- 裸关键词面（R2_BARE_KEYWORDS）：tda、nosymmetry、notestmo、fopt、
  popt。
- B6 误拒翻案共 9 条：No* 类 td=NoIVOGuess、geom=NoKeepConstants、
  geom=NoGIC、opt=NoMicro、guess=NoTranslate；A 类 geom=NoCrowd、
  scf=NoInCore、scf=NoVarAcc、ept=D2；另 noise 类 output=RawMatrixElement。

维持拒绝要点（防反向误收）：freq VPT2/ReadFCHT/ReadAnharm 输入段条目
（NoFermi/NoComb/NoReorient 等非 route 选项）、%NoSave Link 0 指令、
NoSymm 等独立关键词交叉引用、嵌套值形（Recorrect=/Report=/Switch=/
UpdateMethod= 取值，容器名已在典）、Pop=Mulliken/Opt=Raman（现行手册
无此选项名，维持预期警告）。

## 4. 验收留痕

- 词典测试 14 项全绿（web/tests/test_extract_keywords.py：mini fixture
  面⑧句式断言、真实 KB 重生成逐字节一致幂等、规模 1419 断言、面⑧
  闸门样例含 L5 事故本尊 opt=noeigentest 与 B6 翻案 4 条）。
- 全量 pytest 873 项通过（含 combo_templates 规模断言同步 1419）。
- 用户文件复跑：L5 route_option_unknown 消除，仅剩 title 含「_」警告
  （与官方 input 页「should be avoided in the title section:
  @ # ! – _ \ control characters」一致，非误报）。
- 幂等：`uv run python scripts/extract_keywords.py` 重跑逐字节一致。
- mini fixture：web/tests/fixtures/kb_scf.md 扩展八类句式样本。
