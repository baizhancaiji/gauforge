# 输入文件勘误校验缺口补齐计划

> 状态：**待实施计划**（2026-10-18 立题，决策点已全部裁决）。
> 本文由两轮分析凝成：①输入文件勘误能力全面盘点（代码层面）；②gaussian-kb MCP
> 官方规则核对（规则层面）。§1 为官方规则核对结论（本计划的规则 SSOT 摘录），
> §2 为缺口登记与逐项补齐方案，§3 为实施批次，§4 为契约影响，§6 为决策记录。
> 与 roadmap 冲突时以 roadmap 为准；契约（openapi.yaml / sse.md）变更须文档先行
> （roadmap §1 设计原则「契约先行」）。文中行号以 2026-10-18 HEAD（g16-webui 分支）为准，实施时以实际代码为准。

## 0. 背景、依据与方法

### 0.1 两轮分析

- **能力盘点**（2026-10-18）：现有勘误能力=解析层（`web/src/parse/blocks.py`
  分块扫描 + `parse_errors` 标注 + 空行规约重组）、字典层
  （`web/src/parse/keywords.py` + `keywords.txt` 1164 词条）、编排层
  （`services/candidates.py` 导入与分块保存、`services/verify.py` 提交核验、
  `services/combo_templates.py` 模板校验、`services/dependencies.py` 符号引用
  DAG）。结论：结构/分隔维度扎实（容错解析 + 规约 + 双重 round-trip 自证），
  route 关键字维度「拼写层强、语义层弱」。
- **官方规则核对**（2026-10-18，gaussian-kb MCP）：对每个缺口取得 G16 官方
  手册原文依据，并额外发现 **3 处现行实现与官方规则的矛盾**（C1/C2/C3，
  见 §2.1–§2.3）。

### 0.2 规则来源

| 规则 | 来源（gaussian-kb 页面） |
|---|---|
| 输入结构五节、空行终止、title ≤5 行与禁用字符 | `input`（About Gaussian 16 Input，Syntax） |
| 自由格式、大小写不敏感、分隔符（空白/制表符/逗号/斜杠）、选项四种形态、最短唯一缩写、`@file` 包含、`!` 注释任意处 | `input`（Syntax Rules） |
| `External="…"` 引号值 | `external`（Examples） |
| `--Link1--` 前必须空行 | `input`（Multistep Jobs） |
| 逐节终止空行触发表（59 行） | `input`（Section Ordering，§1.2 完整收录） |
| route `#` 起始、多行、空行终止、裸 `#` 合法、`#N/#P/#T` | `route`（#） |
| 重复关键字的官方盲区与后果 | `testrt` |
| Link 0 可选且须在 route 之前、行长 ≤500、`%mem` 单位值域、`%cpu`/`%nprocshared` 语义、无等号指令（`%save`/`%kjob`/`%subst` 等） | `link0`、`running` |
| 电荷（有符号整数）/多重度（通常正整数）、多组电荷/自旋对（同一行）、负多重度仅 Guess=Fragment、元素标签文法（≤4 字符）、`-Bq` 鬼原子、`X` 哑原子 | `molspec`、`zmat`、`oniom`、`counterpoise` |
| `Geom=Check/Checkpoint` 仅读电荷/多重度；`Geom=AllCheck` 全部取自 chk | `geom` |

### 0.3 与现行文档的关系

- roadmap §2.7 是本仓库输入空行规则的 SSOT，本计划 §1.2 全表**不替代**它，
  实施时把例外全集（7 项）回补进 §2.7 表格（现缺 `CASSCF=SpinOrbit`、
  `Pop=NBO6Read` 两项），并给 Title 行补「`Geom=AllCheck` 除外」括注
  （现行文只在该行写「必须」，例外仅出现在分子说明行）；同时把
  「`Geom=Checkpoint` 时仅保留电荷多重度行」补全为「title 仍必须存在」。
  细节触发表落位于代码静态数据（§2.4 方案）。
- `scripts/extract_keywords.py` 的数据源（gaussian-kb 知识库数据目录）与
  §1 规则核对同源同数；字典再生成的幂等性已有闸门（`test_extract_keywords.py`
  逐字节一致 + 1164 规模断言），但**真实知识库缺失时该测试会 skip**，
  本计划 G7 同时保留非条件的规模断言，并要求批次记录 skip 状态。
- 本计划同时登记一项兼容项：现有 `_EXTRA_KEYWORDS` 含官方表未列出的
  `prop=wrf`；G4 替换触发词集时保留一版兼容触发并在 §2.12 登记，
  待 G16 冒烟确认后再决定删除。

---

## 1. 官方规则核对结论（SSOT 摘录）

### 1.1 结构与分隔

- 五节顺序：Link 0（**不**要求终止空行）→ route（要求）→ title（要求，
  **至多 5 行**，避免 `@ # ! – _ \` 与控制字符，尤其 Ctrl-G）→ 分子说明
  （要求）→ 附加输入节（**通常**要求）。
- 语法规则：自由格式、大小写不敏感；行内项目分隔符=空白/制表符/逗号/斜杠
  **任意组合**；选项四种合法形态 `kw=opt`、`kw(opt)`、`kw=(o1,o2)`、
  `kw(o1,o2)`，且 `=` 两侧**允许任意空格**，`=` 可省略；关键字可缩写至
  **全系统最短唯一前缀**（如 `Conven` 合法而 `Conv` 非法）；`@filename`
  整文件包含（可加 `/N` 抑制回显）；`!` 注释可出现在任意行任意位置。
  引号值（如 `External="RunTink Amber"`）中的空格不属于行内分隔符。
- 多步任务：`--Link1--` 行分隔各步，**其前必须有一个空行**。
- 电荷/自旋行：可包含多组 `(charge, spin)` 对，**写在同一行**；组间仍按
  上述自由格式分隔符分隔，例如 `1,2 1,2 0,1`、`0 1 0 1 0 1`。

### 1.2 Section Ordering 全表（官方原文完整收录）

> 实施缺口 G4 的直接依据。列为：节 / 触发关键字 / 末尾空行。
> 加粗为「no」例外（官方共 7 行）。2026-10-18 对 `input` 页原文逐行复核，
> 59 行与下表一致。Link 0、Route、Title、分子说明 4 行为 **core** 行
> （官方表第 3 行 Extra Overlays 按附加节谓词归入 additional）；PDB 二级
> 结构行为 **automatic**（由分子说明残基信息触发，无 route 谓词）；其余
> 54 行为可转 route 谓词的 **additional** 行。

| 节 | 触发关键字 | 末尾空行 |
|---|---|---|
| Link 0 命令 | `%` 命令 | **no** |
| Route 节 | 全部 | yes |
| Extra Overlays | ExtraOverlays | yes |
| Title 节 | 除 Geom=AllCheck 外全部 | yes |
| 分子说明 | 除 Geom=AllCheck 外全部 | yes |
| 成键说明 | Geom=Connect 或 ModConnect | yes |
| 冻结原子改动 | Geom=ReadOpt | yes |
| 坐标修改 | Opt=ModRedundant | yes |
| 第 2 套 title 与分子说明 | Opt=QST2 或 QST3 | yes（两者皆需） |
| 第 2 套成键说明 | Geom=Connect/ModConnect 且 Opt=QST2/QST3 | yes |
| 第 2 套冻结原子改动 | Geom=ReadOpt | yes |
| 第 2 套坐标修改 | Opt=QST2 或 QST3 | yes |
| 第 3 套 title 与初始 TS 结构 | Opt=QST3 | yes（两者皆需） |
| 第 3 套成键说明 | Geom=Connect/ModConnect、Opt=(ModRedun,QST3) | yes |
| 第 3 套冻结原子改动 | Geom=ReadOpt | yes |
| 第 3 套坐标修改 | Opt=(ModRedun,QST3) | yes |
| PDB 二级结构信息 | 分子说明含残基信息时自动 | yes |
| 原子质量 | ReadIsotopes | yes |
| External 外部程序 | External=(…,ReadInput) | yes |
| MM 参数 | HardFirst、SoftFirst、SoftOnly、Modify 选项 | yes |
| 目标频率 | CPHF=RdFreq 或 Freq=ROA | yes |
| 背景电荷分布 | Charge | yes |
| BOMD/ADMP 输入 | ADMP、BOMD 必读输入及 ReadVelocity、ReadMWVelocity | yes |
| PCM 输入 | SCRF=(ExternalIteration,Read)、(SCRF=ONIOMPCM=A,Read) | yes |
| IRC 表坐标 | IRC(Report=Read) | yes |
| 谐振约束 | Geom=ReadHarmonic | yes |
| 半经验参数（Gaussian 格式） | Input 选项与 Both 选项 | yes |
| 半经验参数（MOPAC 格式） | MOPACExternal 与 Both 选项 | yes |
| 基组说明 | Gen、GenECP、ExtraBasis | yes |
| 基组改动 | Massage | yes |
| 有限场系数 | Field=Read | yes |
| ECP 说明 | Pseudo=Cards、GenECP | yes |
| 密度拟合基组 | ExtraDensityBasis | yes |
| PCM 溶剂模型输入 | SCRF=Read | yes |
| DFTB 参数 | DFTB | yes |
| 初猜来源 | Guess=Input | yes |
| 对称性合并类型 | Guess=LowSymm | **no** |
| 轨道说明（α/β 分列） | Guess=Cards | yes |
| 轨道改动（α/β 分列） | Guess=Alter | yes |
| 轨道重排（α/β 分列） | Guess=Permute | yes |
| GVB 轨道数/对 | GVB | **no** |
| CAS 态平均权重 | CAS=StateAverage | yes |
| 自旋轨道耦合目标态 | CASSCF=SpinOrbit | **no** |
| 轨道冻结信息 | ReadWindow 各选项 | yes |
| EPT 精修轨道 | EPT=ReadOrbitals | yes |
| 自旋自旋耦合常数原子表 | NMR=ReadAtoms | yes |
| 替代原子半径 | Pop=ReadRadii 或 ReadAtRadii | yes |
| Antechamber 输出文件 | Pop=MK IOp(6/50=1) | yes |
| 静电性质数据 | Prop=Read 或 Opt | yes |
| NBO 输入 | Pop=NBORead 或 Pop=NBO6Read | **no** |
| 谐振正则模式选择 | Freq=SelectNormalModes | yes |
| 阻碍转子输入 | Freq=ReadHindered | yes |
| 非谐正则模式选择 | Freq=SelectAnharmonicModes | yes |
| 非谐输入 | Freq=ReadAnharmonic | yes |
| FCHT 输入 | Freq=ReadFCHT | yes |
| Pickett 文件原子表 | Output=Pickett | **no** |
| ACID 输出文件名 | NMR=CGST IOp(10/93=1) | yes |
| PROAIMS 输出文件名 | Output=WFN | **no** |
| 矩阵元文件名 | Output=MatrixElement 或 Output=Raw | yes |

### 1.3 route 文法

- `#` 为节首行第一个非空白字符；续行**可不**带 `#`；必须空行终止；
  裸 `#`（无关键字）合法（默认 HF/STO-3G 单点）。
- `#N`（默认普通输出）、`#P`（额外输出）、`#T`（精简输出）为官方替代表单。
- 官方 testrt 工具自述盲区：「testrt cannot detect keyword usage errors …
  it will not warn you that including the **MP2 keyword twice** within the
  route section will have unexpected results (running an MP4 job)」；
  且「only the first error within the route section is flagged」。

### 1.4 Link 0 规则

- 「optional and **precede the route section**」——位置约束官方明文。
- 单条 Link 0 命令**长度上限 500 字符**。
- `%mem=N`：默认单位 8 字节字；单位后缀值域 **KB/MB/GB/TB/KW/MW/GW/TW**
  （无空格）；默认 800 MB。`%rwf` 分段语法同值域。
- `%cpu=proc-list`（逗号分隔、支持区间，区间可带 `/n` 后缀表示每隔 n 个）；
  设计上取代 `%nprocshared`；`%nprocshared=N` 语义为「最多 N 核」——
  两者并行不混同。
- Link 0 指令不要求一律 `=`：`%save`、`%errorsave`/`%nosave`、
  `%kjob L502 2`、`%subst L913 dir`、`%usessh` 等为合法无等号形态；
  `%oldmatrix=(file,i4lab)`、`%gpucpu=0-3=0-1,16-17` 等含多个 `=` 的取值
  也不能按 `key=value` 简单切分。工程上要求 `%mem` 数值 >0（官方未显式
  规定零值，零内存无实际意义）。

### 1.5 分子说明文法

- 首行：净电荷（**有符号整数**）+ 自旋多重度（**通常为正整数**）；
  官方示例 `0 1`、`-1 2`；某些计算类型允许/要求**多组电荷-多重度对**，
  且多组对写在**同一行**（Counterpoise `1,2 1,2 0,1`、ONIOM
  `0 1 0 1 0 1`）。负多重度**仅 `Guess=Fragment` 计算**有官方语义
  （对应 fragment 的未配对轨道转为 β 自旋），其余计算类型 G16 一律
  报错；工程上拒绝 0 多重度，负多重度按宽容口径放行并经警告提示
  （§2.7 G5/G6）。
- 原子行最一般形态：
  `Element-label[–Atom-type[–Charge]][(param=value[,…])] 位置参数`；
  元素标签=化学符号或原子序数，可后接字母数字标签（C1/C2…），
  **标签总长上限 4 字符**；可带 `(Iso=13,Fragment=2)` 类参数表与冻结码。
  元素符号可后接字母标签（如 `Foo` = F + 标签 `oo`），因此未知标签判定
  只能以「找不到任何元素符号前缀」为准。
- 鬼原子：`-Bq` 作为原子类型（如 `O-Bq`），保留基组与积分格点但无核电荷，
  用于 counterpoise 计算；计入原子行数，不计入分子式。
- 哑原子：Z-matrix 允许 `X`；计入 Z-matrix 中心/原子数，但无元素、无核电荷，
  **不计入分子式**。
- 原子行与电荷行同样受自由格式分隔符约束：`C,0,0,0`、`C/0/0/0` 合法。

### 1.6 Geom 检查点语义（矛盾根源）

- `Geom=Checkpoint`（同义 `Geom=Check`）：「**Only the charge and multiplicity
  are read from the input stream**」——电荷/多重度行**必须存在**；title 按
  §1.2 表（除 AllCheck 外全部 yes）也**必须存在**；仅原子坐标可省。
- `Geom=AllCheck`：「only the route section and any input required by
  keywords within it need be specified」——title、电荷/多重度、原子坐标
  三者皆可整体省略。
- `Geom=Modify`（已弃用）要求两组输入（电荷/多重度 + 修改节），本计划不覆盖，
  登记于 §2.12。

---

## 2. 缺口登记与补齐方案

### 2.0 缺口总表

| 编号 | 缺口 | 等级 | 批次 |
|---|---|---|---|
| C1 | Geom=Checkpoint 豁免过宽（与官方矛盾） | 正确性 | B1 |
| C2 | Geom 括号形态识别失效（与官方矛盾） | 正确性 | B1 |
| C3 | enforce 拼写五类官方合法形态误拒（与官方矛盾） | 正确性 | B1 |
| G0 | 非阻断 warnings 通道缺失（实施前置） | 前置 | B1 |
| G1 | 导入/提交通道无拼写检查 | 增强 | B3 |
| G2 | 无重复关键字检测（官方自认盲区） | 增强 | B3 |
| G3 | 位置约束无校验（% 行后置静默吞并/误作 title） | 增强 | B3 |
| G4 | Section Ordering 不校验 + `_EXTRA_KEYWORDS` 严重滞后 | 增强 | B2 |
| G5 | 值域校验通道不一致（多重度 / Link0 文法与值域与行长 / title 字符 / BOM / %cpu /n / %mem=0） | 增强 | B4 |
| G6 | 分子说明原子行与多组电荷对不验证（含自由格式分隔符、鬼原子、哑原子） | 增强 | B4 |
| G7 | 字典词条缺口（t/n）；缩写维持精确匹配 | 增强 | B5 |
| G8 | 括号内子选项不校验（未对照 `kw=opt` 组合词验证归属） | 增强 | B5 |
| G9 | 核心节必需空行与分子说明缺失无显式检测（route/title EOF 吞并、归因误导、空分子说明放行；含分子说明/Variables EOF 登记） | 增强 | B2 |

### 2.0.1 G0 · 统一非阻断 warnings 通道（B1 前置）

**现状**：`parse_input` 只返回 `{"blocks", "parse_errors", "multistep"}`
（[blocks.py#L227](file:///home/keepoux/workspaces/projects/hyperqueue/web/src/parse/blocks.py#L227)），
没有 warnings 通道；而 `parse_errors` 在导入（`_validate_one`，任何一条即
逐文件报错并整体 422）与提交（`verify_and_store` 直接 422 INPUT_PARSE_FAILED）
**都是阻断**。因此 G6 未知元素标签、G9 的保守分支（分子说明/Variables EOF）所承诺的
「非阻断警告」当前无处落地；G1/G2/G8 也需要同一通道承载拼写、重复、子选项
提示。**G0 为必需**（G1/G2/G8 的 warning 不涉及
结构错误，不应阻断）。

**方案**：
- `parse_input` 返回值新增 `warnings: list[dict]`，条目形态为
  `{line, keyword, kind, message, suggestion?, task_id?}`：
  - `line`：**全文件 1 起**，与 `parse_errors` 相同；
  - `keyword`：该警告对应的关键字/指令名/选项/原子标签/字符；无单一载体时
    为空串；
  - `kind`：取值见 §4；
  - `message`：可直接展示的中文说明（非拼写警告必需；拼写警告也统一携带，
    避免前端按 kind 维护第二套文案）；
  - `suggestion`：可选，仅拼写/选项近邻类警告提供；
  - `task_id`：可选，仅队列/多任务提交聚合时填充。
- `parse_errors` 语义保持不变（阻断）；导入/提交/预览/分块保存统一消费
  `warnings`。**预览端点契约同步增加可选 `warnings`**（见 §4）。
- 分块保存的 `warnings` 行号改为全文件绝对行号：`check_route_spelling`
  增加 `line_offset` 参数，`save_block` 传入 route 起始行号；导入/提交
  由 `parse_input` 直接生成绝对行号。
- 命名统一：导入/提交/预览/分块保存一律 `warnings`；组合流模板既有
  `notice.spelling_warnings` 保持不变（不在本计划改名，避免破坏 3.2.0 契约）。

**涉及文件**：`web/src/parse/blocks.py`（返回值）、`services/candidates.py`、
`services/verify.py`、`routers/candidates.py`、`docs/api/openapi.yaml`；
前端 `BlockEditor.vue`、`CandidatesView.vue`；测试
`test_parse_blocks.py`、`test_block_save.py`、`test_contract_rest.py`。

**测试**：`test_parse_blocks.py` 断言 `warnings` 键存在且默认空列表；
`test_block_save.py` 断言 route 不在文件首行时警告行号为绝对行号；
`test_contract_rest.py` 覆盖 preview/提交响应 schema。

### 2.1 C1 · Geom=Checkpoint 豁免过宽（正确性修复）

**现状**：`parse/blocks.py:151-152` 以裸子串判定
`geom_checkpoint = "geom=allcheck" in route_cf or "geom=checkpoint" in route_cf`，
`:166` 豁免 title 缺失、`:183` 豁免电荷/多重度缺失——两者对 checkpoint
**同时豁免**（实测 `#p b3lyp/6-31g(d) geom=checkpoint` + title、无电荷行
→ `parse_errors=[]`）。全文件 `grep geom` 仅命中 151-152、166、183 三处，
**`_scan_spans` 与 `verify_and_normalize` 不含任何 geom 判定**，无需同步修改。

**官方依据**：§1.6。Checkpoint 仅豁免原子坐标；title 与电荷/多重度均必须
存在。AllCheck 才可整体省略。

**方案**：豁免集拆分为两档，判定收敛为 `parse_input` 单一私有函数
`_geom_exemption_tier(route_text) -> "allcheck" | "checkpoint" | None`——
- 识别 `geom=allcheck`、`geom=(allcheck,…)` 括号形、`geom = allcheck`、
  `geom (allcheck)` 及其大小写变体；
- checkpoint 档识别 `checkpoint` 与同义 `check`，含括号/空格形式；
- `allcheck`：豁免 title 缺失、电荷/多重度缺失、原子坐标缺失（现状不变）；
- `checkpoint`：仅表示「原子坐标可省」；title 与电荷/多重度缺失照常记
  `parse_errors`（错误文案改为精确表述：title 仅 AllCheck 豁免）。
  `parse_input` 目前对空坐标块本就不报错，故 checkpoint 档的实际改动是
  **取消** title/电荷豁免，而不是新增坐标报错路径。

**触发条件**：`parse_input` 解析含 route 的文本即生效（预览/导入/提交三通道
同时收严）。分块保存 route 不新增阻断，保持既有语义；若保存后产生
`parse_errors`，响应如实返回，提交时拒绝（矩阵登记为「不适用」）。
**预期效果**：`Geom=Checkpoint` 且缺电荷行/缺 title 的文件在导入与提交时被拒；
导入侧表现为 `files[].reason=INPUT_PARSE_FAILED`（外层错误码
`VALIDATION_FAILED`），提交侧为 422 `INPUT_PARSE_FAILED`。

**行为变更登记**：接受集收窄（此前可通过的 Checkpoint 文件开始被拒），
属兼容性收窄而非契约形态变更，须在 CHANGELOG 标注。

**涉及文件**：`web/src/parse/blocks.py`（仅 `parse_input`）；
`web/tests/test_parse_blocks.py`（`test_geometric_allcheck_missing_sections_allowed`
拆分为 allcheck/checkpoint/check 三态断言）。

### 2.2 C2 · Geom 括号形态识别失效（正确性修复）

**现状**：裸子串匹配无法识别 `Geom=(AllCheck,ModRedundant)`、
`Geom=(AllCheck,…)`（`(` 隔在 `=` 与值之间）——实测
`#p b3lyp/6-31g(d) geom=(allcheck,modredundant)` 仅含 route 时被误报
「缺少 title 节」+「缺少电荷/多重度行」，而裸 `geom=allcheck` 无报错。
`Geom=(Checkpoint,ModRedundant)` 省略坐标是合法的，但 title/电荷仍必须存在，
因此它**不是**本缺口的合法输入示例；本项只影响 AllCheck 括号形。

**官方依据**：§1.1 选项四种合法形态；§1.6 AllCheck 语义。

**方案**：route token 化后按「头部=取值集合」判定 geom 检查点语义：
token 切分复用 C3 的括号感知管道；形如 `geom(...)`/`geom=(...)` 的 token
取括号内选项集合（casefold、strip），含 `allcheck` → allcheck 档，
仅含 `checkpoint`/`check` → checkpoint 档。判定实现为 `parse_input` 内
单一私有函数（与 C1 合并），**不改动 `_scan_spans`/`verify_and_normalize`**——
两处均无 geom 逻辑，强行同步会引入无意义改动。

**预期效果**：括号形态与裸形态判定结果一致；消除 AllCheck 合法文件的误报。

**涉及文件**：`web/src/parse/blocks.py`（C1/C2 共用私有辅助函数）；
`web/tests/test_parse_blocks.py` 增括号形态、空格、`check` 同义与逗号后空格用例。

### 2.3 C3 · enforce 拼写误拒官方合法形态（正确性修复）

**现状**：`services/combo_templates.py` 拼写校验（`_TOKEN_SPLIT` 切分 +
`_token_in_dict` 精确匹配）对以下官方合法形态产生 `keyword_not_in_dict`
误拒：
1. **逗号分隔**：`opt,freq` 被视为单 token（[keywords.py#L19](file:///home/keepoux/workspaces/projects/hyperqueue/web/src/parse/keywords.py#L19)
   切分集 `[/\s#]+` 不含逗号；官方允许逗号作项目分隔符）；
2. **`!` 行内注释**：`#p opt ! note` 的 `note`/`!` 进入 token 流；
3. **`kw(option)` 无等号括号形**：`opt(modredundant)` 整 token 查典失败
   （`_token_in_dict` 只处理 `key=value` 形）；
4. **`@filename` 包含**：`@` 开头 token 被当词典外词；
5. **等号两侧空格**：`#p opt = (calcfc, ts)` 产生独立 `=` token 与带括号
   碎片，enforce 下同样被拒（实测）。
   另有 **无等号且关键字与括号之间有空格** 的合法形 `opt (calcfc, ts)`，
   以及 **引号值** `External="RunTink Amber"`，当前分词同样会误拒。

**官方依据**：§1.1 语法规则（逗号/空格/斜杠分隔、注释任意处、括号选项形、
`@file` 包含、`=` 两侧可空格、引号值）。

**方案**（`keywords.py` 与 `combo_templates.py` 共用同一 token 化管道，
杜绝两套口径漂移）：
- `keywords.py` 新增「route token 化」公共函数：
  - **括号感知**：括号深度为 0 处的空白/逗号/斜杠/`#` 为分隔符；深度 >0 时
    空白/逗号/斜杠/`#` 全部保留（保住 `6-31g(d,p)`、`IOp(6/50=1)` 整词）；
  - **引号感知**：双引号内的空白不切分（保住 `External="RunTink Amber"`）；
  - 切分前截断每个物理行的首个**引号外** `!` 及其后内容；
  - `@` 开头 token 直接豁免（含 `/N` 后缀）。
- **独立 `=` token 处理**：切分后丢弃裸 `=`，并把相邻的 `key`、`=`、`value`
  合并为 `key=value`；**另增 `key` + `(…)` 合并**（覆盖 `opt (calcfc, ts)`）。
- `_token_in_dict` 从 `combo_templates.py` 迁入 `keywords.py`（或共享模块），
  扩展命中规则：整词命中 ∨ `key=value`/`kw(opt)` 键名命中且值非空；
  `iop(6/50=1)` 这类含 `=` 的括号值按 `(` 前头部取键。
- `check_route_spelling` 同步换用新 token 化函数，并**先走 `_token_in_dict`**
  （整词与键名精确命中，不做缩写近似——决策点 5）再进入近邻；
  命中则不警告。
- 该公共函数同时是 G4 触发词匹配与 G8 子选项查典的拆解基座——三处共用
  一个括号/引号解析实现，杜绝口径漂移。

**预期效果**：上述形态在 enforce 模式不再误拒；warn 模式不再对官方合法
词形产生错误近邻建议。**回归风险**：括号感知切分必须以 `6-31g(d,p)`、
`opt=(calcfc,ts)`、`IOp(6/50=1)`、`External="RunTink Amber"` 等既有/新增
整词回归（`test_block_save.py` 拼写用例 + 新增用例）。

**涉及文件**：`web/src/parse/keywords.py`、`web/src/services/combo_templates.py`；
测试 `web/tests/test_block_save.py`、`web/tests/test_combo_templates.py`。

### 2.4 G4 · Section Ordering 固化（数据 + 校验 + 触发词扩容）

**现状**：`blocks.py:11-13` `_EXTRA_KEYWORDS` 仅 6 条（gen/modredundant/
guess=alter/scrf=read/pop=nbo/prop=wrf），官方触发表 59 行；附加节
`terminator_blank` **只记录不校验**（[blocks.py#L224-L225](file:///home/keepoux/workspaces/projects/hyperqueue/web/src/parse/blocks.py#L224-L225)
记录后无任何校验消费方；`verify.py:19-24` 的结构自证掩码与
`candidates.py:344` 会将其无条件置 True，不代表校验）；
`wants_extra=False` 时附加节识别退回隐式变量区启发式
（`_looks_like_variables`）兜底：伪变量形态的附加节理论上可被误判为
变量区（真实 Gen 基组节/ECP 节因后续行不满足启发式，实测不复现；
`gen` 本在 `_EXTRA_KEYWORDS` 内不受影响），`Pseudo=Cards` 等未收录
触发词的附加节因此依赖启发式而非官方口径；`Guess=Cards`（首行
`(4E20.8)`）、`ReadIsotopes`（首行 `300.0 1.0`）、`Charge`/`Field=Read`
（数字行）、`Freq=ReadFCHT`（`Final=Source=Chk`）不属于该风险面。

**官方依据**：§1.2 全表（`input` 页 Section Ordering，2018-02-19,
G16 Rev. C.01 快照）。

**方案**（三件事，同一数据源驱动）：
1. **静态表落码**：在 `web/src/parse/` 新增 `section_ordering.py`，把 §1.2
   全表固化为**显式有序映射表**，每行字段：
   `{section_id, kind, predicate, terminator}`。
   - `kind` ∈ `core`（Link 0、Route、Title、分子说明 4 行）/ `additional`
     （54 行 route 谓词）/ `automatic`
     （PDB 二级结构；无 route 谓词，不进入 `any_trigger`）；
   - 触发词条件只使用可判定的 token 谓词（`key` 存在 / `key=option` 包含）；
   - 特殊散文行由人工转换为谓词，并在表中单列：`semi_empirical_input`、
     `semi_empirical_both`、`mopac_external`、`mm_parameters`、
     `external_readinput`、`admp_bomd`、`pcm_input`、`irc_report_read`、
     `pop_mk_iop`、`nmr_cgst_iop`、`read_window`；其余行按 key/option 精确匹配；
   - **不按附加节首行猜节名**——附加节在解析器里没有名称，只有首行数据，
     无法用 `section_head` 反查概念节。
2. **`_EXTRA_KEYWORDS` 替换**：改为由该表 `kind=additional` 导出的
   **人工审核触发词全集**（54 行去重后的 key/option 谓词），并保留
   `COMPAT_EXTRA_KEYWORDS = ("prop=wrf",)` 一版兼容项（官方表未列出，
   见 §2.12）。`parse_input`/`_scan_spans` 的 `wants_extra` 判定改查
   `section_ordering.any_trigger(route_tokens)`——附加节识别与隐式变量区
   抑制同步获得官方口径。**禁止把 `core` 行的 `Route Section | all` 导入
   `any_trigger`**，否则恒为真。
3. **terminator 校验接入**：附加节由空行切分，因此「非 EOF 位置缺空行」
   在结构上不可观测（缺空行会与下一节合并为同一 region）。本项只检测
   **最后一个附加节以 EOF 收尾**（`terminator_blank=False`）。判定规则：
   - 计算当前 route 命中的 `kind=additional` 行集合；
   - 集合为空 → 不报；
   - 集合内所有行 `terminator=yes` → 记 `parse_errors`
     （section=`additional`，message=「附加输入节未以空行终止」；
     决策点 3）；
   - 集合内所有行 `terminator=no` → 不报；
   - **混合（既有 yes 又有 no）→ 保守不报**，仅 debug 日志；避免多触发词
     （如 `Gen` + `Pop=NBORead`）时把 no 节误报为 yes。
   - `kind=automatic`（PDB）不参与本判定；登记为已知限制。
   **`verify_and_normalize` 不置 `terminator_blank`**：它对每节统一插一个
   空行（QST2/QST3 的下一结构交界为两个空行，
   [blocks.py#L385-L395](file:///home/keepoux/workspaces/projects/hyperqueue/web/src/parse/blocks.py#L385-L395)），
   no 例外节位于文件末尾时追加空行不改变 G16 读取语义，故无需为 no 例外
   改规范化，只在校验侧豁免。

**范围声明**：本项固化「触发识别 + 终止空行」，**不校验附加节出现顺序**
（解析器无节名，顺序校验不可行）；该限制登记于 §2.12。

**触发条件**：预览 / 导入 / 提交核验全通道。**预期效果**：附加节归类与
终止空行判定获得官方 SSOT；`Gen`、`Pseudo=Cards` 等触发词改由官方表
驱动识别，附加节不再依赖隐式变量区启发式兜底（数量以
`section_ordering.py` 落码清单为准，
评审时登记准确数：59 行 = 4 core + 54 additional route 谓词 + 1 automatic）。

**涉及文件**：新增 `web/src/parse/section_ordering.py`；
`web/src/parse/blocks.py`（消费方）；`docs/specs/roadmap.md` §2.7（例外
全集回补 2 项 + Title 行 AllCheck 括注 + Checkpoint title 补全）；
`web/tests/test_parse_blocks.py` 增表驱动用例（逐行断言 `kind`/`terminator`/
`any_trigger`，并断言普通 route 下 `any_trigger=False`）。

### 2.5 G1 · 拼写检查接入导入与提交通道

**现状**：`check_route_spelling` 在每次 `save_block` 后触发
（`services/candidates.py:405`，不限于 route 节保存）；导入（`_validate_one`）
与提交核验（`verify_and_store`）均不做拼写检查——拼错关键字的文件可一路走到
G16 运行期才报错。近邻策略只对「有近邻的拼写」给提示，无近邻的新词
不会警告；「拼错即见提示」指「有近邻的拼错即见提示」。

**官方依据**：§1.3 testrt 盲区佐证「拼写层校验有价值」；语法规则确认
大小写不敏感（现行 casefold 正确）。

**方案**：导入与提交核验各追加**非阻断**拼写检查（C3 的新 token 化管道 +
G0 的 `warnings` 通道）：
- 导入：`_validate_one` 现通过时返回 `None`，改为始终返回
  `{"error": dict | None, "warnings": list}`；`import_files` 把 `warnings`
  写入 `files[]` 条目（通过文件携带空列表或非空列表），不阻断入库；
  整批 422 时 `details.errors[]` 保持既有逐文件错误形态、不新增
  `warnings` 字段，警告仅随导入成功的 `files[]` 返回；
- 提交核验：`verify_and_store` 返回值由 `bool` 改为
  `{"normalized": bool, "warnings": list}`。全部 **6 处**调用点同步：
  `routers/candidates.py:184`、`routers/queues.py:135`、
  `services/history.py:201`、`services/resume.py:256`、
  `services/workflows.py:254`、`services/workflows.py:276`。
  - **三个响应返回点**必须取 `res["normalized"]`：`routers/candidates.py:184`
    （直接返回 `normalized` 字段）、`routers/queues.py:135`（`if` 取值，
    dict 恒真）、`services/history.py:201`（直接返回 `normalized` 字段）；
  - `services/resume.py:256` 的响应 `ResumeConfirmResponse` 增加可选
    `warnings` 并透传；
  - `services/workflows.py:254/276` 为程序化输入，返回值可忽略，但需在
    测试中确认不因 dict 返回值改变控制流；
- 队列提交聚合：`warnings` 条目增加可选 `task_id`，`routers/queues.py`
  逐成员收集并填入；单任务提交不填；
- 命名统一为 `warnings`（与分块保存同形），不使用第三个名字
  `spelling_warnings`（组合流模板的 `notice.spelling_warnings` 保持不变）；
- **不引入 enforce**（决策点 1：导入/提交仅 warn）：导入通道面对历史文件
  与外部来源，近邻策略存在误报残余（cutoff=0.80），阻断会拒合法文件。

**预期效果**：有近邻的拼错关键字在导入/提交时即见琥珀提示；不改变任何
阻断语义。

**涉及文件**：`web/src/services/candidates.py`、`services/verify.py`、
`routers/candidates.py`、`routers/queues.py`、`services/history.py`、
`services/resume.py`、`services/workflows.py`（调用点透传）；
前端 `BlockEditor.vue`/`CandidatesView.vue`/提交确认框；
`docs/api/openapi.yaml`（先改契约，见 §4）；测试
`test_submit_verify.py`、`test_candidates_import.py`、`test_contract_rest.py`。

### 2.6 G2 · route 重复关键字检测 + G3 · 位置约束校验（B3 同批）

**G2 现状**：无任何重复检测；官方 testrt 页明文承认这是其自身盲区且后果
真实（重复 MP2 跑成 MP4）。

**G2 方案**：token 化（C3 管道）后取每 token 的关键字头部（`/`、`(`、`=`、
`[` 前，casefold），按头部聚合；出现 ≥2 次时按下表判定（可测试、无待定项）：

| 形态 | 判定 |
|---|---|
| `mp2 mp2`（同头部、均裸） | 警告 `route_duplicate` |
| `freq freq=readfcht`（容器头裸形 + 选项形） | 豁免（官方允许的追加取值；B3 用 G16/testrt 冒烟确认） |
| `opt opt=(calcfc,ts)` | 豁免（同上） |
| `freq=readfc freq=readfcht`（两个非空选项集） | 警告 |
| `opt=(calcfc,ts) opt=(qst3)` | 警告 |
| `scf=tight scf=xqc` | 警告 |
| `iop(5/17=1) iop(6/50=1)`（两个 IOp 取值 token） | 豁免（IOp 文法为多条目取值列表、并列取值语义；多 token 合并官方未明文，随 B3 冒烟确认） |
| `#p opt freq` | 无 |

容器头白名单固定为：`opt/freq/scrf/geom/guess/pop/irc/td/nmr/prop/cas/cphf/
ept/output/charge/iop`；白名单外的头部只要重复即警告。裸形+选项形豁免
（第 2/3 行）与 `iop` 并写豁免均为待冒烟确认口径：B3 以 G16/testrt 冒烟
裁决，若证实裸形被拒、选项形不叠加或多 token 不合并，对应豁免行回退为
警告，并在当批 CHANGELOG 登记判定口径与归因。**触发**：分块保存 /
导入 / 提交 / 组合流模板保存（模板 route 为单行，规则同样适用）；
`kind=route_duplicate`，`suggestion` 可缺省，`message` 指明重复头部。

**G3 现状**：`%` 行出现在 route 之后有两种表现，均静默：
1. route 后**无空行**直接跟 `%chk=…` → 被 route 收集循环吞入 route 文本
   （实测 `parse_errors=[]`，G16 会把 `%` 行当 route 内容而报错）；
2. route 后**有空行**再跟 `%chk=…` → 被 title 收集循环当成 title 首行
   （实测 `title="%chk=a.chk"`）。若 `%chk` 后还有一个空行，电荷行可正常
   解析；若 `%chk` 后直接跟其他内容，title 会吞并多行。
`_validate_section` 的 route 分支
（[candidates.py#L240-L246](file:///home/keepoux/workspaces/projects/hyperqueue/web/src/services/candidates.py#L240-L246)）
只查 `#` 首行与空行，**没有任何 `%` 校验**。

**G3 方案**（按两种表现分级）：
- 情形 1（`%` 行进入 route 文本）→ `parse_errors`
  （`section="route"`，message=「Link 0 命令必须位于 route 节之前」）；
  导入/提交阻断（G16 必然误读），分块保存补逐行
  `route_line_link0_forbidden` 阻断；
- 情形 2（`%` 行成为 title 首行）→ `parse_errors`
  （section=`title`，message=「疑似 Link 0 命令错置于 title 节」；
  决策点 3），导入/提交阻断（title 形态本身合法，但几乎必为用户错误），
  分块保存 title 节校验同步阻断（reason 按分块保存端点词表登记）；
- 检测范围限定在「route 起点至 title 结束」之间，不扫描后续附加节/分子说明，
  避免把自由文本中以 `%` 开头的行误报；route 节缺失时（缺 `#` 行已另有
  报错），`%` 行出现在 title 位置同样按情形 2 记 `parse_errors`。

**涉及文件**：`web/src/parse/blocks.py`、`services/candidates.py`、
`services/combo_templates.py`（模板重复检测）；
测试补 `%chk=` 后置（有/无空行两态，断言真实 title/charge 结果）、
缺 route 时 `%chk=` 位于 title 位置（记 `parse_errors`）、
`#p opt opt`、`opt=(calcfc,ts) opt=(qst3)` 等重复用例；
`freq,readfcht` 逗号分隔（C3 回归）、`freq freq=readfcht` 与
`iop(5/17=1) iop(6/50=1)`（G2 豁免）各一条。

### 2.7 G5+G6 · 值域拉齐与原子行校验（B4 同批）

**G5 项**（完整通道矩阵见 §2.11）：
1. **多重度正整数与多组电荷对**：`blocks.py:176-178` 仅 `int()` 转换，
   0/负多重度在导入/提交通道放行（编辑保存通道 `_validate_section:269`
   已查 `> 0`）。方案：
   - 电荷行按自由格式分词（空白/制表符/逗号/斜杠），得到偶数个整数；
   - 第一组 `(charge, mult)`：电荷有符号整数、mult ≥ 1；
   - 后续组为 fragment 层：mult 不得为 0；负值官方仅 `Guess=Fragment`
     计算合法（§1.5），其余场景按宽容口径放行，并经 G6 的
     `molecule_multiple_charge_pairs` 信息级警告提示；
   - `blocks["charge_mult"]` 保留**全部组**的规范化字符串（如
     `"1 2 1 2 0 1"`），不再截断为前两个；
   - 同步 `_validate_section` 与 `_expected_blocks` 的多组对口径；
   - 失败记 `parse_errors`——三通道口径拉齐（官方：「signed integer」+
     「usually a positive integer」+ 多组对示例）。
2. **Link 0 值域统一**：`candidates.py:42` `_MEM_VALUE_RE` 现额外放行
   `W`、`B`，官方值域仅 `KB/MB/GB/TB/KW/MW/GW/TW`。方案：删除 `W|B`，
   对齐官方值域（决策点 2：收紧，不保留宽松偏差；默认无单位=8 字节字
   的官方语义不受影响）。`%mem` 数值须 **>0**（`%mem=0` 拒绝）。**同源校验
   `parse_input`**：`%mem`/`%nproc`/`%cpu` 值在导入/提交/预览通道按同一
   正则与语义记 `warnings`（`kind=link0_value_invalid`），编辑保存保持
   阻断；组合流模板 `mem_gb` 同步要求 >0（模板无单位输入）。为避免
   `parse` 层反向依赖 `services`/`engine`（会形成循环导入），把
   `_MEM_VALUE_RE` 与 `%cpu` 解析核心下沉到 `web/src/parse/link0_rules.py`，
   `services/candidates.py` 与 `engine/workspace.py` 复用；`parse_input`
   只依赖该低层模块。engine 记账换算同步对齐统一单位集：`_mem_to_gb`
   现含官方值域外的 `QW` 且缺 `GW/TW`（`%mem=2GW` 现解析失败回落缺省
   注入并误记 defaulted），下沉时删除 `QW`、补 `GW/TW` 换算，记账与
   值域共用同一单位集。`%rwf` 分段值域不纳入校验（目录路径与 `-1`/`0`
   特殊值语义复杂，离线静态校验误报率高），登记 §2.12。
3. **Link 0 行长上限**：`parse_input` 与 `_validate_section` 均补单行
   ≤500 字符；编辑保存阻断（reason=`link0_line_too_long`），
   导入/提交记 `warnings`（`kind=link0_line_too_long`），避免拒历史文件。
4. **Link 0 指令文法与重复**：按官方 link0 页定义文法——
   - 允许无等号指令：`%save`、`%errorsave`/`%nosave`、`%kjob L<n> [m]`、
     `%subst L<n> dir`、`%usessh`、`%usersh`、`%ssh=cmd`；
   - 已知指令集从官方页面导出，至少含 chk/oldchk/schk/rwf/int/d2e/mem/
     nproc/nprocshared/cpu/nproclinda/gpucpu/lindaworkers/debuglinda/save/
     errorsave/nosave/kjob/subst/usessh/usersh/ssh/oldmatrix/oldrawmatrix/
     oldraw；
   - 同名指令重复、未知指令 → `warnings`
     （`kind=link0_directive_unknown` / `link0_directive_duplicate`）；
     不阻断（决策点 7）；
   - 含多个 `=` 的指令（`%gpucpu=0-3=0-1,16-17`、
     `%oldmatrix=(file,i4lab)`）按「首个 `=` 后整体为值」解析，不按普通
     key=value 再做二次切分。
5. **title 禁用字符通道拉齐**：`_validate_section` title 分支已查
   `@ # ! – _ \` 与控制字符，但 `parse_input` 不查，导入可带非法字符入库。
   方案：`parse_input` 对 title 记 `warnings`（`kind=title_forbidden_char`，
   `message` 指明字符与行）；编辑保存保持阻断；模板无 title 字段，不适用。
6. **UTF-8 BOM**：导入解码后若首字符为 `\ufeff` 会导致 `#` 识别失败。
   方案：`_validate_one` 解码用 `utf-8-sig`；**若检测到 BOM，落盘前剥离
   BOM 字节**（其余字节/CRLF 原样保留；剥离后的字节用于哈希与落盘）；
   `verify_and_store`、`save_block`、`resolve_title` 等所有读取路径统一
   `utf-8-sig`；`parse_input` 入口防御性剥离；剥离为静默行为，导入/预览
   响应不设专门提示字段（随 B4 写入 openapi 导入接口 description）；
   补“磁盘副本无 BOM、提交/派发无 BOM”用例。
7. **`%cpu` `/n` 后缀**：官方区间支持 `0-5/2`。`_cpu_list_count` 增加
   `/n` 解析（按步长计数），合法 `/n` 形态全通道放行；非法形态在编辑保存/
   模板阻断、导入/提交记 `warnings`。

**G6 原子行校验**：`blocks.py:50-60` `_atom_symbol` 对任意字母 token 直接
放行（实测含 H 行与 `Foo 0 0 0` 行的两原子文件计入 atom_count=2、
formula=`H1Foo1`）。官方文法：
元素符号或原子序数、标签总长 ≤4 字符、可带 `–Atom-type–Charge` 与
`(param=value)` 参数表。方案：
- **先按自由格式分词**（空白/制表符/逗号/斜杠，括号/引号感知）取首个
  字段；`C,0,0,0`、`C/0/0/0` 均取 `C`；
- 先剥离尾部 `(…)` 参数表（括号平衡）；
- **鬼原子判定先于元素识别**：剥离后按 `–`/`-` 分段，分段含 `Bq` 原子
  类型（如 `O-Bq`）判定为鬼原子——计入 atom_count（占一行）、不计入
  分子式（无核电荷），不再做元素识别；在测试中显式断言；
- 其余取**第一个 `–`/`-` 之前**的片段作为 Element-label（覆盖
  `C-CT--0.06` 类 MM/ONIOM 行）；
- Element-label ≤4 字符；元素识别采用**最长元素符号前缀**（不区分大小写，
  `Cl1` 取 Cl、`C1` 取 C、`Foo` 取 F + 标签 `oo`——官方允许字母标签，
  因此 `Foo` 不告警）；剩余部分须为字母数字；找不到任何元素符号前缀
  （如 `Zz`）才返回 None；
- `X` 或 `X<数字>` 识别为哑原子：计入原子行数、不计入分子式、不告警；
- 原子序数形态维持现有界内映射（1..118）；
- 调用方（`parse_input` 内部原子循环）对 None 行记 `warnings`
  （`kind=atom_label_unknown`，决策点 4：仅 warnings 不阻断——ONIOM/MM
  类型等复杂文法首 token 未必是元素）；
- **多组电荷/自旋对**：按 G5 第 1 项在同一电荷行解析，**不再**按“非首行
  两 token”猜测；原子行循环内顺带提取 `(Fragment=n)` 参数作为判定输入；
  若电荷行含多组对而 route 未含 `Counterpoise`/`ONIOM` 且分子说明无
  `Fragment` 参数，或含负多重度组而 route 未含 `Guess=Fragment`，记
  信息级 `warnings`（`kind=molecule_multiple_charge_pairs`），不阻断。

**涉及文件**：`web/src/parse/blocks.py`、`services/candidates.py`、
新增 `web/src/parse/link0_rules.py`（Link0 正则与 `%cpu` 解析核心）、
`web/src/engine/workspace.py`（`_cpu_list_count` 薄封装）；测试：
`-1 2` 电荷行、`0 0` 多重度、多组电荷对、负多重度组（无
`Guess=Fragment` 警告／有则零警告）、含 `Fragment` 参数的多组对零警告、
`%mem=2W`、`%mem=0`、
`%cpu=0-5/2`、501 字符 `%` 行、`%save`/`%kjob l502 2`、
`O-Bq`、`X` 哑原子、`C(Iso=13,Fragment=2)`、`Zz 0 0 0` 警告、
`Foo 0 0 0` 不告警、`C-CT--0.06`、`C,0,0,0`、`C/0/0/0`、BOM 文件。

### 2.8 G7 · 字典扩面与缩写精确匹配口径（B5）

**现状**：`keywords.txt`（1164 词条）缺 `#N/#T` 替代表单的 `n`、`t`
（`route` 页 Alternate Forms 官方合法，实测 `grep -x` 仅 `p` 在典；
`p` 来自**面②** gv6 单字母白名单 `_SINGLE_OK={"p"}`
（[extract_keywords.py#L71](file:///home/keepoux/workspaces/projects/hyperqueue/scripts/extract_keywords.py#L71)），
面① slug 没有长度过滤，标题变体才要求 len≥2）——enforce 模式会拒绝合法
`#T b3lyp/6-31g(d)` 模板（实测拒绝）。

**方案**：
1. `scripts/extract_keywords.py` 增「面⑥ route 替代表单」：从知识库
   `route` 页 Alternate Forms 提取 `n/p/t`（p 已由面② 覆盖，去重）；
   重生成字典并经 `test_extract_keywords.py` 一致性闸门（逐字节幂等；
   两处 1164 断言同步 1164→1166：条件真实 KB 测试与非条件 loader 测试）。
   真实 KB 缺失时该测试 skip，批次记录必须注明 skip 状态，不得把 skip
   当作通过。
2. **缩写维持精确匹配（决策点 5）**：`_token_in_dict` 保持整词与键名精确
   命中，不引入最短唯一前缀近似；`scf=conven`、`fre`、`geo` 类官方合法
   缩写在 enforce 下被拒、warn 下按拼写近邻提示，误拒缩写登记为已知
   限制（§2.12），如需支持随词典扩面另批立项。

**涉及文件**：`scripts/extract_keywords.py`、`web/src/parse/keywords.txt`
（重生成）、`web/src/parse/keywords.py`、`web/tests/test_extract_keywords.py`；
测试补 `#t`/`#n` 模板、`scf=conven`/`scf=conv`/`fre`/`geo` 精确匹配查典
失败（enforce 拒绝；warn 通道 `fre`/`geo` 近邻提示 `freq`/`geom`）。

### 2.9 G8 · 括号内子选项与左侧关键字归属校验（B5）

**现状**：字典已含 `kw=opt` 组合词条目（面⑤产物，实勘：`opt=` 61 条、
`freq=` 48 条、`scrf=` 34 条、`geom=` 38 条、`guess=` 33 条、`pop=` 25 条等），
但两条拼写路径均不校验括号内容：
- `combo_templates.py:53-60` `_token_in_dict` 对 `kw=(o1,o2)` 取键名查典
  即放行，选项集不查；`scrf=(solvent=water,read)` 等嵌套取值形同理；
- `check_route_spelling` 对 `opt=(calcfc,ts)` 整 token 近邻查询——
  **现状是误报而非静默**：实测返回
  `{kind: keyword_spell, suggestion: opt=calcfc}`（difflib 比值 0.80 命中
  cutoff），而 `geom=(allcheck,xyzzy)` 无近邻、静默通过。`opt=(readfc)`
  是合法 Opt 选项（`opt=readfc` 在典），不构成跨关键字错误；跨关键字示例
  使用 `opt=(readfcht)`（ReadFCHT 是 Freq 选项，`opt=readfcht` 不在典）。

**官方依据**：语法规则 `keyword=(option1, option2, …)`——括号内容是该
关键字的选项列表；testrt 页「ModRedundant is a valid option, **but not for
CCSD**」佐证「选项-关键字归属」是官方自身的校验维度。

**方案**：
- 复用 C3 的括号/引号感知 token 化管道，从含选项 token 拆出
  `(键, 选项序列)`；选项按逗号切分并 strip/casefold；
- 每个选项归一化后按组合词查典：
  纯选项 `o` 查 `键=o`；带值选项 `o=v` 剥离值后查 `键=o`；嵌套一层取值
  （`solvent=water`）同理只取 `键=o`——与面⑤「页 slug=选项」入典口径一致；
- **值形关键字白名单**（新）：`iop/oniom/external` 等括号内容为数值/评分/
  模型化学字符串的关键字，不做选项查典：
  - `IOp(6/50=1)` 的 `6/50=1` 是值，不是选项名；
  - `ONIOM(B3LYP/6-31G(d):AM1:UFF)` 是模型化学组合；
  - `External="RunTink Amber"` 是命令/文件名；
  `GFInput`/`GFPrint` 的括号内容确实是选项名（字典有
  `gfinput=aonormalization` 等），**不得**加入白名单，仍按选项校验；
- **逐选项判定**：键名在典且不在值形白名单时，每个选项独立查典，未命中者
  各记一条 `warnings` `kind=route_option_unknown`；部分命中部分未命中只报
  未命中选项（`opt=(calcfc,xyzzy)` 仅报 `xyzzy`，不因 `calcfc` 命中而整体
  放行）。条目 `keyword` 装出错选项 token 原文（与 `keyword_spell` 的出错
  token 同规），`message` 同时给出选项与左侧关键字：「xx 疑似非 KEYWORD
  的官方选项」；
- **选项级拼写建议**：未命中选项在该键的选项集合内做近邻查询（与
  `check_route_spelling` 同 cutoff），命中唯一近邻则随条目附 `suggestion`
  （`opt=(calfcf)` 的 `calfcf` 附建议 `calcfc`）；无近邻仅 unknown 警告、
  无 `suggestion`；
- **缩写选项**：精确匹配口径同样适用于选项（决策点 5），缩写选项按未
  命中记 `route_option_unknown`，不引入选项级前缀近似；
- **分级（决策点 6：仅 warn）**：面⑤按「噪声可控」原则提取，选项覆盖
  非全量，enforce 化必误拒；如需 enforce，先做面⑤覆盖率评估另批立项。
  G4 的触发词「选项集」匹配复用同一拆解辅助，不另写括号解析。

**触发条件**：分块保存 / 导入 / 提交 / 组合流模板保存，初始仅
warnings。**预期效果**：跨关键字选项误置与子选项拼写错误在保存/导入时即
有提示；合法 `opt=(calcfc,ts)` 不再产生错误近邻建议；enforce 化路径须先
过面⑤覆盖率评估，另批立项。

**涉及文件**：`web/src/parse/keywords.py`（拆解、查典辅助与
`check_route_spelling` 选项化）、`web/src/services/combo_templates.py`、
`web/src/services/candidates.py`；
测试：`opt=(calcfc,ts)` 零警告、`geom=(allcheck,xyzzy)` 警告、
`scrf=(solvent=water,read)` 嵌套取值零警告、`opt=(readfcht)` 跨关键字警告、
`opt=(readfc)` 零警告、`opt=(calcfc,xyzzy)` 仅 `xyzzy` 一条警告、
`opt=(calfcf)` 警告且 `suggestion=calcfc`、`IOp(6/50=1)` 零警告、
`ONIOM(B3LYP/6-31G(d):AM1:UFF)` 零警告、
`External="RunTink Amber"` 零警告。

### 2.10 G9 · 核心节必需空行缺失的显式检测（B2）

**现状**（与 G4 的分工：G4 管附加节 terminator，本项管 route/title/电荷行
等核心节）：
- route 收集循环 `while i < n and not blank(i)` 延展至 EOF 不报错
  （`blocks.py:143-145`）——官方 route 页明文「The route section **must**
  be terminated by a blank line」；
- route 未终止时后续内容被**静默吞并**进 route 文本，有两种表现（均实测）：
  1. 一直吞并到 EOF → title 落空，报「缺少 title 节」（归因误导：用户实际
     忘了空行，提示却指向缺节）；
  2. route 后跟 title 行、其后才有空行 → title 被填成
     `0 1\nH 0 0 0`，报「缺少电荷/多重度行」（同样归因误导）。
  `verify_and_normalize` 的结构自证掩码对此无效（吞并前后 blocks 结构一致，
  规范化不救回）；
- title 节延展至 EOF 同样无报错（`blocks.py:158-160`），以「缺少电荷/
  多重度行」间接显现；charge_mult 解析失败的文案「应为两个整数」也不提示
  「上一节可能缺终止空行」这一常见根因；
- 电荷行之后无任何原子行（分子说明整体缺失）不报任何错误（实测
  `parse_errors=[]`），坏文件放行至 G16 运行期才失败；
- 分子说明原子行、`Variables:`/`Constants:` 区延展至 EOF 也无终止检查；
  官方分子说明为 blank-terminated，roadmap §2.7 亦要求 Variables/Constants
  以空行分隔；
- `--Link1--` 前必须空行（官方 Multistep Jobs 明文）：`blocks.py:95-101`
  截断时不检查前导空行（多步文件本被整体拒绝，属提示性补强）。

**方案**（`parse_input` 小改，`_scan_spans` 的同构循环不承担报错职责、
无需改动）：
1. route 收集以 EOF 告终 → `parse_errors` 记
   `{section: "route", message: "route 节未以空行终止"}`；若 title 同时
   落空，「缺少 title 节」的 message 追加根因提示「（route 未以空行终止时
   其后内容会并入 route）」；
2. title 收集以 EOF 告终 → 记 `{section: "title", message: "title 节未以
   空行终止"}`（Geom=AllCheck 豁免集内不报）；
3. charge_mult 解析失败文案追加「（若上一节未以空行收尾，本行可能是误并
   内容）」；
4. 电荷行之后分子说明为空（无原子行）且无 Geom 检查点豁免 →
   `parse_errors` 记 `{section: "molecule", message: "缺少分子说明节
   （原子定义行）"}`——与「缺少 title/电荷」同类缺节阻断，不随决策点 3
   变级；checkpoint/allcheck 档不报；
5. 分子说明原子行以 EOF 告终 → `warnings`
   `kind=molecule_unterminated`（仅原子行非空且无 Geom 坐标豁免时；非阻断，
   避免大量历史文件误拒）；
6. `Variables:`/`Constants:` 区以 EOF 告终 → `warnings`
   `kind=variables_unterminated`（非阻断）；
7. `--Link1--` 截断时检查前一行，非空则在既有 link1 错误 message 附注
   「--Link1-- 前缺少空行（官方要求）」（多步文件在导入/提交通道已被
   整体拒绝，该附注仅预览通道可见）。

**阻断级别（决策点 3）**：1/2 进 `parse_errors`（导入 422 阻断——G16
对未终止节必然误读或 EOF 报错）；第 4 项为固定 `parse_errors`；
5/6 为 warnings（避免拒历史文件）。
提交通道因 `verify_and_store` 先规范化再解析：**纯 EOF（route 后无其他
内容）** 会被追加空行兜住；若 route 已吞并 title/电荷，规范化无法拆分，
仍会报缺节——两通道行为差异如实写入 openapi description。

**涉及文件**：`web/src/parse/blocks.py`、`docs/api/openapi.yaml`
（parse_errors/warnings description 行为口径）、`web/src/services/workflows.py`
（`_extract_molecule_block` 与 parse_input 的节扫描规则同步，或抽共享函数）；
测试：route 直连 title 无空行（报未终止 + 根因提示）、title 直连电荷行
无空行、charge_mult 误并文案断言、电荷行后无原子行（空分子说明报缺节，
checkpoint/allcheck 档不报）、`--Link1--` 紧跟原子行附注断言、
`Geom=AllCheck` 仍要求 route 终止空行（仅豁免 title/电荷，不豁免 route）、
分子说明/Variables EOF 警告、工作流取电荷/坐标同步回归。

### 2.11 规则 × 通道覆盖矩阵

> 新增/变更规则必须在此矩阵登记「阻断 / 警告 / 不校验」，作为通道一致性判据。`模板` 指组合流模板保存。**预览列的「阻断」
> 指产生 `parse_errors` 并在预览中标记错误，不阻断预览接口返回**（预览
> 本身保持尽力而为）；其余列的「阻断」指该操作 422 拒绝。模板无对应字段
> 的规则登记为「不适用」，不得虚报「阻断」。

| 规则 | 预览 | 导入 | 提交 | 分块保存 | 模板 |
|---|---|---|---|---|---|
| route 以 `#` 起始 | 阻断 | 阻断 | 阻断 | 阻断 | 阻断 |
| route/title 以空行终止（G9） | 阻断 | 阻断 | 阻断（纯 EOF 的「未终止」经规范化消除；缺节/吞并仍拒） | 不适用 | 不适用 |
| 分子说明/Variables EOF（G9） | 警告 | 警告 | 警告 | 警告 | 不适用 |
| Geom 豁免边界（C1/C2） | 阻断 | 阻断 | 阻断 | 不适用（保存不阻断，响应可见） | 不适用 |
| title ≤5 行 | 阻断 | 阻断 | 阻断 | 阻断 | 不适用（无 title 字段） |
| title 禁用字符 | 警告 | 警告 | 警告 | 阻断 | 不适用 |
| 电荷/多重度格式 + 首组多重度 >0 + 多组对合法性 | 阻断 | 阻断 | 阻断 | 阻断 | 不适用 |
| 分子说明节非空（G9，Geom 检查点豁免集内不报） | 阻断 | 阻断 | 阻断 | 不适用 | 不适用 |
| 分子说明自由格式分隔符（G5/G6） | 阻断（无法解析时） | 阻断（无法解析时） | 阻断（无法解析时） | 阻断（charge_mult 无法解析时） | 不适用 |
| 多组电荷对无 Counterpoise/ONIOM/Fragment 佐证，或负多重度组无 Guess=Fragment | 警告 | 警告 | 警告 | 警告 | 不适用 |
| `%mem` 单位值域与 >0 | 警告 | 警告 | 警告 | 阻断 | 阻断（mem_gb ≤0；无单位输入） |
| `%nproc` 正整数 | 警告 | 警告 | 警告 | 阻断 | 阻断 |
| `%cpu` 列表（含 `/n`） | 警告 | 警告 | 警告 | 阻断 | 阻断 |
| Link 0 单行 ≤500 | 警告 | 警告 | 警告 | 阻断 | 不适用（生成行远短于上限） |
| Link 0 位于 route 前（G3） | 阻断 | 阻断 | 阻断 | 阻断 | 不适用 |
| Link 0 指令文法/指令名/重复 | 警告 | 警告 | 警告 | 阻断（文法非法）/警告（未知/重复） | 不适用 |
| route 拼写 | 警告 | 警告 | 警告 | 警告 | 阻断（enforce） |
| route 重复关键字（G2） | 警告 | 警告 | 警告 | 警告 | 警告 |
| route 子选项归属（G8） | 警告 | 警告 | 警告 | 警告 | 警告 |
| 原子标签文法/哑原子/鬼原子（G6） | 警告 | 警告 | 警告 | 警告 | 不适用 |
| 附加节终止空行（G4） | 阻断 | 阻断 | 阻断 | 不适用 | 不适用 |
| `@file` 存在性/可读性 | 不校验 | 不校验 | 不校验 | 不校验 | 不校验 |

「不适用」表示该操作不新增该规则的阻断级校验；分块保存统一消费
`parse_input` 的 warnings，因此全文件 warning 仍可能在保存响应中出现，
前端按 warning 展示。模板列仅登记其真实字段
（nproc/mem_gb/cpu/route）。

### 2.12 已识别但不纳入本计划的风险（登记备案）

| 风险 | 不纳入理由 | 处置 |
|---|---|---|
| 附加节出现顺序校验 | 解析器不识别节名，只按空行切分 region，无法判定「第 2 套 title」等序号 | 本计划只做触发识别与终止空行；顺序交 G16/testrt，登记为已知限制 |
| PDB 二级结构自动触发 | 无 route 谓词，解析器不解析残基信息 | `kind=automatic`，不进入 `any_trigger`；terminator 不检测 |
| 坐标数值合法性 / Z-matrix 变量与引用 | 自由格式与变量定义复杂，离线静态校验误报率高 | 不校验；G16 运行期报错 |
| `@file` 是否存在、`/N` 语义 | 文件可能位于集群侧或 G16 运行目录，WebUI 无访问权 | 不校验；预览可显示「包含文件未校验」提示（可选，非本计划） |
| `Geom=Modify` 两节输入 | 官方已弃用（推荐 ModRedundant），实际使用极少 | 不覆盖；解析保持现状 |
| 全局关键字空间的最短唯一性 | 词典不是全系统关键字空间 | 维持精确匹配（决策点 5），缩写误拒为已知限制；warn 通道保留近邻提示 |
| `prop=wrf` 非官方触发词 | 官方 Section Ordering 未列，但现行实现已支持 | 保留一版 `COMPAT_EXTRA_KEYWORDS`，B2 后 G16 冒烟确认再决定删除 |
| 分子说明/Variables EOF 阻断 | 历史文件常以 EOF 收尾；G16 是否一律拒绝未做全量实测 | G9 仅给非阻断 warnings；若实测 G16 拒绝，再另批升级为阻断 |
| title 语义/内容质量 | 程序不解释 title | 仅校验字符与行数 |
| Link 0 未知指令阻断 | 历史模板可能含自定义 `%` 指令 | 仅 warnings（决策点 7） |
| `%rwf` 分段值域校验 | 分段含目录路径与 `-1`/`0` 特殊值语义，离线静态校验误报率高 | 不校验；G16 运行期报错 |
| 关键字与计算类型组合合法性（如 NMR 仅限 HF/DFT/MP2） | 需完整语义模型，离线静态校验不可行；G8 仅覆盖选项-关键字归属 | 交 G16/testrt，登记为已知限制 |

---

## 3. 实施批次与验收标准

| 批次 | 范围 | 验收标准 | 契约动作 |
|---|---|---|---|
| B1 正确性修复 + 前置通道 | G0+C1+C2+C3 | 既有全量测试不回归；记录实际 passed/skipped 数与 skip 原因；`warnings` 通道就位且默认空列表、含 `message`；五类误拒形态 + 无等号空格形 + 引号值 + 括号 Geom + `Geom=Check` 用例转绿；Checkpoint 缺电荷/缺 title 被拒、AllCheck 不变 | 抽共享 `Warning` schema；openapi 增 `warnings` 形态（`message` 必填、`suggestion`/`task_id` 可选）；InputPreview 增可选 `warnings`；生成物再生零 diff |
| B2 数据固化 | G4+G9 | `section_ordering.py` 表与 §1.2 逐行一致（59 = 4 core + 54 additional + 1 automatic）；`any_trigger` 只消费 additional 且普通 route 下为 False；G9 的 route/title EOF 阻断用例、分子说明/Variables EOF 警告用例与两种吞并归因用例转绿，空分子说明缺节阻断用例转绿；roadmap §2.7 回补（2 例外 + Title 行括注 + Checkpoint title 补全） | warnings kind 词表增 `molecule_unterminated`、`variables_unterminated`；附加节终止空行按决策点 3 记 parse_errors，parse_errors description 同步更新 |
| B3 新检测 | G1+G2+G3 | 导入/提交响应携带 `warnings`（导入 422 响应的 `details.errors[]` 不携带）；三个响应返回点全部取 `res["normalized"]`（candidates/queues/history）；resume 响应透传 warnings；队列提交 warnings 带 `task_id`；重复/错位用例按 §2.6 判定表与 §2.11 矩阵在各通道行为一致 | warnings kind 词表增 `route_duplicate`（Link 0 错位按决策点 3 记 parse_errors）；CandidateCreate.files、SubmitResponse、ResumeConfirmResponse 增可选 warnings（**先改 openapi.yaml**） |
| B4 值域与原子行 | G5+G6 | §2.7 用例全绿；§2.11 矩阵逐格符合；`%mem=2W` 编辑保存阻断、导入/提交警告（决策点 2 收紧；模板无单位输入，不适用）；`%mem=0` 编辑保存/模板 `mem_gb` 阻断、导入/提交警告（决策点 8）；`%cpu=0-5/2` 通过；多组电荷对、负多重度组与 `Fragment` 佐证用例、自由格式分隔符、`Foo` 不告警、`Zz` 告警、`X` 哑原子、BOM 落盘剥离全部通过 | warnings kind 词表增 `link0_value_invalid`、`link0_line_too_long`、`link0_directive_unknown`、`link0_directive_duplicate`、`title_forbidden_char`、`atom_label_unknown`、`molecule_multiple_charge_pairs` |
| B5 字典扩面 | G7+G8 | 字典重生成幂等闸门通过（1166 词条；两处断言同步；KB skip 记录）；`#t`/`#n` 模板 enforce 通过；`scf=conven`/`scf=conv`/`fre`/`geo` 精确匹配拒绝（缩写不识别）；G8 用例（在典零警告/未知选项/嵌套取值/`opt=(readfcht)` 跨关键字/`opt=(readfc)` 零警告/`opt=(calcfc,xyzzy)` 仅报未命中选项/`opt=(calfcf)` 附 `suggestion=calcfc`/IOp 零警告/ONIOM 零警告/External 零警告）转绿 | warnings kind 词表增 `route_option_unknown` |

### 3.1 批次依赖与节点

- **B1 必须先行**：C3 的 token 化管道与 G0 的 `warnings` 通道是 B2/B3/B4/B5
  的公共基座；B1 完成前不得启动其余批次的实现。
- **B2→B3→B4 串行**：三批都触及 `blocks.py` 的 `parse_input`，且 B3 要
  把 G2/G3 警告接入同一返回结构；不建议并行修改同一文件。若确需并行，
  先把 warnings 生成拆成独立模块并冻结接口，再按文件所有权拆分。
- B5 依赖 B1（G8 复用 C3 管道、G7 依赖同一 `_token_in_dict`），与 B2–B4
  无强依赖，可最后执行。
- 每批入口 = 上一批验收全绿 + `validate_progress.py` 通过；每批出口 =
  §5 闸门全绿 + CHANGELOG/progress 当批登记（禁止集中回补）。
- 真实 G16 冒烟节点：B1 后一次（Checkpoint/AllCheck 各一例）、B2 后一次
  （`Gen`/`Pseudo=Cards` 附加节）、B4 后一次（多组电荷对/`%cpu=0-5/2`/
  自由格式分隔符各一例）；版本固定 G16 Rev. C.01，语料清单与哈希随批次记录。
- **版本归属**：本计划按 **3.4.0（minor：新增 warnings 通道与检测项）**
  目标版本推进（3.3.0 已于 2026-10-15 冻结发布）。若仅交付 C1–C3
  （不含 G0/warnings）才按 patch；B1 含 G0，按 minor。

每批次独立成提交序列（文档 → 测试 → 实现 → 进度同步），单次提交只做
一类变更。开发前先把本任务写入 `progress.json.in_progress`。

## 4. 契约影响与先行文档变更

- **不新增错误码**：全部复用 `VALIDATION_FAILED`（details.errors[]）、
  `INPUT_PARSE_FAILED` 与 warnings 非阻断通道。**词表分离**：
  - 导入 per-file reason：沿用词表一 5 项，不新增；
  - 分块保存 `details.errors[].reason`：`route_line_link0_forbidden`、
    `link0_misplaced`、`link0_line_too_long`、`mem_value_invalid` 等，
    按分块保存端点自行登记，不塞入词表一；
  - warnings kind：见下，独立词表；`route_duplicate` 只是 kind，不是 reason。
- **Warning 共享 schema**：
  `{line: int, keyword: str, kind: str, message: str, suggestion?: str,
  task_id?: int}`；`line` 为全文件 1 起；`message` 必填；
  `suggestion`/`task_id` 可选。新增 kind：`route_duplicate`、
  `route_option_unknown`、`atom_label_unknown`、
  `molecule_multiple_charge_pairs`、`molecule_unterminated`、
  `variables_unterminated`、`link0_value_invalid`、`link0_line_too_long`、
  `link0_directive_unknown`、`link0_directive_duplicate`、
  `title_forbidden_char`（既有 `keyword_spell` 保留）。附加节终止空行
  （G4）、Link 0 错位（G3 情形 2）与 route/title 未终止（G9）按决策点 3
  记 `parse_errors`（message 口径，不入 kind 词表）。
- **可选字段增量**：
  - `InputPreview` 增可选 `warnings`（预览通道；warnings 统一归属
    `InputPreview`，分块保存响应现有的 `allOf(InputPreview, {warnings})`
    外层包装随之移除）；
  - `CandidateCreate.files[]` 条目增可选 `warnings`（导入 422 的
    `details.errors[]` 不新增 `warnings` 字段，警告仅随成功的 `files[]`
    返回）；
  - `SubmitResponse` 增可选 `warnings`（行内/队列/历史重新排队共用）；
  - `ResumeConfirmResponse` 增可选 `warnings`；
  - 全部为纯增量、可选、默认空数组。
- **分块保存 warnings 的 `suggestion` 由必填改可选**，并增加 `message`
  （必填）与 `task_id`（可选）；`InputPreview.blocks` 形态不变。
- **G4/G3/G9 阻断项新增 parse_errors message**（不入 reason 词表），随
  B2/B3 更新 description。
- **BOM 剥离口径**：静默剥离、不设专门响应字段，随 B4 更新导入接口
  description。
- **`charge_mult` 契约描述**：字段仍为 string；多组电荷/自旋对按规范化
  空格分隔保留全部组（单对仍为 `"c x"`），description 注明该形态。
- **生成物闸门**：openapi 变更后必须重跑 `web/scripts/gen_models.py` 与
  `npm run gen:types`，`git diff` 零残留方可提交（与 3.2.0 契约闸门同规）。
- **命名**：导入/提交/预览/分块保存统一 `warnings`；组合流模板
  `notice.spelling_warnings` 保持不变（不破坏 3.2.0 契约）。
- **roadmap §2.7**：例外全集回补（2 项）、Title 行 `Geom=AllCheck` 括注、
  Checkpoint 行补「title 仍必须存在」，随 B1/B2 批次文档先行提交。

## 5. 测试方案总纲

- **既有闸门全量必跑**：`uv run pytest`、`scripts/validate_progress.py`、
  `scripts/gen_changelog_md.py --check`；契约变更批次另跑
  `gen_models.py` 与 `npm run gen:types` 零 diff；前端展示改动批次加
  `scripts/audit_frontend_offline.sh` 与设计令牌/对比度闸门。
- **测试基线**：每批入口记录 `uv run pytest -q` 的实际 passed/skipped 数
  与 skip 原因（AGENTS §6.1）；涉及提交/派发链路时确认
  `target/release/hq` 存在，缺失时 e2e 会静默 skip，不得以通过数虚高
  代替闸门通过。
- **表驱动测试**：`section_ordering.py` 以 §1.2 全表为 fixture，逐行断言
  `kind`/`terminator`/触发谓词；固定预期数量：59 = 4 core + 54 additional
  route 谓词 + 1 automatic；G4 的散文行转换需逐条人工核对。另加负向测试：
  普通 route 下 `any_trigger=False`；多触发词混合 yes/no 时不报。
- **区间重组回归**：B2 对 `_scan_spans` 的 `wants_extra` 改动逐一验证
  `reassemble` 的 `additional-<n>` 索引稳定、逐节保存 round-trip 一致。
- **通道矩阵测试**：§2.11 每一行至少一条用例，断言预览/导入/提交/分块保存/
  模板五通道的实际级别（阻断 vs 警告 vs 不校验）；模板「不适用」必须有
  对应断言，不能只写注释。
- **警告噪声基线**：以 `~/g16/tests/com` 语料为样本，记录改动前后逐文件
  warnings 数量；批次入口冻结阈值（新增警告涉及文件 ≤5%，同一文件
  同一 kind ≤3 条），超过阈值需复审（AGENTS §6.1 可量化指标要求）。
- **金标准语料回归**：`~/g16/tests/com` 现有语料 + 新增
  （Checkpoint 缺电荷行/缺 title、`Geom=Check`、括号 Geom、`#T`/`#N` 模板、
  `opt,freq` 逗号分隔、行内 `!` 注释、`opt = (calcfc, ts)`、
  `opt (calcfc, ts)`、`IOp(6/50=1)`、`External="RunTink Amber"`、`O-Bq`、
`X` 哑原子、`C-CT--0.06`、`C,0,0,0`、`C/0/0/0`、多组电荷对、负多重度组、
空分子说明、BOM、
`%cpu=0-5/2`、`%mem=0`、`%save`/`%kjob l502 2`）。语料版本与
  文件清单/哈希随批次记录，避免「本机可复现、他机不可复现」；语料缺失时
  记录 skip，不得默认通过。
- **端到端**：B1/B2/B4 后各以真实 G16（Rev. C.01）冒烟一次
  （`Geom=(Checkpoint,ModRedundant)`、`Gen`/`Pseudo=Cards` 附加节、
  多组电荷对/`%cpu=0-5/2`/自由格式分隔符各一例），确认零误报/零漏报后再
  进下一批；`%mem=2W`、`%mem=0`、`Zz` 原子行等为离线校验用例，不作为
  G16 冒烟输入。
- **返回形态改造回归**：`verify_and_store` 6 处调用点逐一断言；重点覆盖
  `routers/candidates.py`、`routers/queues.py`、`services/history.py` 的
  `normalized` 真值语义，以及 `test_submit_verify.py` 两处 `is True` 改造。
- **契约与前端**：`test_contract_rest.py` 覆盖 preview/提交/resume schema；
  前端类型再生后 `BlockEditor.vue` 兼容可选 `suggestion`/`message`，
  `CandidatesView.vue` 渲染导入/提交 warnings。

## 6. 决策记录（已裁决）

1. **G1 拼写接入强度**：导入/提交通道仅 warn，不引入 enforce——近邻策略
   存在误报残余（cutoff=0.80），阻断会拒合法历史文件；未来如需 enforce，
   须配套 `ignore_spelling` 类豁免参数另批立项。
2. **`%mem` 的 `W|B` 单位**：收紧对齐官方值域，删除 `W|B`，不保留宽松
   偏差；默认无单位=8 字节字的官方语义不受影响；导入/提交按 §2.11 记
   警告。
3. **缺空行与新增检测的通道级别**：附加节 terminator（G4）、route/title
   未终止（G9 项 1/2）、Link 0 错位（G3 情形 2）一律 `parse_errors`
   （预览标记、导入 422 阻断——手册明示空行缺失 G16 会误读或 EOF 报
   错）；分子说明/Variables EOF（G9 项 5/6）仅 `warnings`；空分子说明
   缺节固定 `parse_errors`。提交通道因先规范化，纯 EOF 的「未终止」会被
   追加空行消除，route 已吞并 title/电荷或缺节的文件仍会拒绝——两通道
   行为差异写入契约描述。
4. **G6 未知元素标签**：仅 `warnings` 非阻断。
5. **B5 缩写兜底**：维持精确匹配，不做最短唯一前缀近似；缩写误拒登记为
   已知限制（§2.12），warn 通道保留近邻提示。
6. **G8 子选项校验分级**：仅 warn；enforce 化前置面⑤覆盖率评估（组合词
   条目数 vs 各 keyword 页 Options 条目全集），另批立项。
7. **Link 0 指令名/重复检测**：仅 `warnings`，不阻断。
8. **`%mem=0`**：拒绝——编辑保存阻断、模板 `mem_gb` 阻断、导入/提交
   警告。
9. **`prop=wrf` 兼容触发词**：保留一版 `COMPAT_EXTRA_KEYWORDS`，避免既有
   行为回退；B2 后 G16 冒烟确认再决定删除。
10. **发布窗口与批次工期**：3.4.0 为目标版本；不设日历承诺，排程由批次
    闸门驱动（每批入口 = 上一批验收全绿 + `validate_progress.py` 通过），
    发布冻结时点在 B5 验收全绿后的发布流程中确定。

## 7. 风险登记

| 风险 | 缓解 |
|---|---|
| 括号/引号感知切分回归（`6-31g(d,p)`、`IOp(6/50=1)`、`External="..."` 被拆） | C3 专用回归用例先行（测试先行批次），词典整词全量比对 |
| geom 判定点遗漏（仅 `parse_input` 一处，易被误以为需同步 `_scan_spans`） | 判定收敛为单一私有函数并在 docstring 注明「`_scan_spans`/`verify_and_normalize` 无 geom 语义」；`grep -n "geom" web/src` 复核 |
| 触发词扩容误触发（`modify`、`input` 等短词面；Route 行 `all` 恒真） | 触发词匹配一律 key/选项集精确等值，禁裸子串；`any_trigger` 只消费 additional 行；负向测试 |
| G4 多触发词下 terminator 误报 | 混合 yes/no 时保守不报；单触发词才检测；补 `Gen`+`Pop=NBORead` 用例 |
| G4 散文谓词人工转换出错 | 特殊谓词逐条人工核对并登记；表驱动测试；G16 冒烟 |
| G8 面⑤组合词覆盖不全致选项漏报/误报 | 仅 warn 级起步（面⑤覆盖非全量，词典未收录的合法选项误报 unknown 也不阻断）；ONIOM/External/IOp 值形白名单；enforce 化前置覆盖率评估（决策点 6） |
| G8 对 `IOp(...)` 等值形括号误报 | 值形关键字白名单 + `IOp(6/50=1)` 零警告用例；分词器保留括号内斜杠 |
| G7 缩写在精确匹配下被误拒 | 维持精确匹配（决策点 5）；warn 通道保留近邻提示；误拒缩写登记为已知限制（§2.12） |
| G9 阻断收严影响历史在库文件 | 仅作用于后续导入/预览，不回溯改写已存文件；纯 EOF 与吞并行为差异写入契约 |
| 分子说明/Variables EOF 警告噪声 | 仅 warnings；语料逐文件基线；超阈值复审 |
| B1 收严影响既有在库候选的再提交 | 仅影响后续提交动作；不回溯改写已存文件（与 §5.3「不改写历史」纪律一致）；发布说明标注接受集收窄 |
| `verify_and_store` 返回 dict 破坏 `queues.py`/`candidates.py`/`history.py` 真值判断 | 三处显式取 `normalized`；6 处调用点逐一改造 + 回归用例 |
| 队列提交 warnings 归属不清 | warning 条目增加可选 `task_id`；单任务不填；补多成员队列用例 |
| resume 响应丢弃 warnings | `ResumeConfirmResponse` 增可选 warnings 并透传；或明确不展示并登记 |
| 导入通道值域校验缺失（只改编辑/模板正则） | §2.11 矩阵强制登记每规则五通道级别；B4 验收逐格核对 |
| Link 0 文法放宽引入新误判 | 无等号指令按官方清单精确匹配；未知/重复仅警告；行长/值域仍按原规则 |
| 多组电荷对解析改变既有 `charge_mult` 输出 | 契约描述同步；现有单对文件输出保持 `"c x"`；多对文件输出全部组；补回归 |
| BOM 剥离改变落盘字节 | 仅剥离 BOM，保留 CRLF 与其余字节；补字节级测试 |
| 共享 Warning schema 变更导致前端类型破坏 | `suggestion` 仅改可选、新增 `message`；一次改 openapi + gen_models + gen:types；前端兼容 |
| warn 噪声上涨影响可用性 | 语料逐文件警告数基线对照；新增警告逐条归因；阈值冻结（≤5% 文件数） |
| 字典重生成依赖 gaussian-kb 数据目录在机 | extract_keywords 已有缺失降级与 `--kb-dir` 参数；重生成后跑一致性闸门；skip 记录 |
| 附加节顺序/PDB 自动触发无法校验 | 已在 §2.12 登记为已知限制，交 G16/testrt；不承诺顺序检测 |
| MM/ONIOM、鬼原子、哑原子、多电荷对误报 | G6 文法边界用例先行；未知标签仅 warn；鬼原子/哑原子不入分子式；多电荷对按同一行解析 |

## 8. 实施与审查留痕

### 8.1 B1 批次（2026-10-19 实施收口）

- 实施序列：progress 开工 → 契约文档先行（含生成物）→ 测试先行（10 用例先红）→ 实现 → 进度同步，共 5 提交。
- 验收：全量 750 passed 0 skipped（入口基线 740）；真实 G16 Rev. C.01 冒烟——
  Checkpoint 缺 title/电荷被拒（l101 报 `Charge and Multiplicity card seems defective`）、
  AllCheck 全省略正常结束（语料 sha256 前缀：t1=3e00da1c、t2=3860904a）。
- 独立审查：报告见 [input-verify-gap-b1-review.md](input-verify-gap-b1-review.md)
  （AGENTS §6.2 四查 + 前端浏览器实测），结论**有条件通过**。
- 审查发现处置：
  - **R1（P1）已修**：`@file/N` 抑制回显后缀并入 @ token（`_AT_SUFFIX_N` 吸附），
    enforce/warn 通道补回归用例；
  - **R2（P2）已修**：combo 模板 `has_freq` 改按 token 头部判定
    （`partition("=")[0].split("(")[0]`），覆盖无等号括号形，补 `temp_applied`
    断言；
  - **R3（P3）已处置**：`!` 截断实现口径（括号内不截断，视为值的一部分）
    已注明于 `keywords.py` docstring 并指向本节；
  - **R4（P3）登记**：实现提交内修正两处测试断言（绝对行号 5、temperature
    逗号列表 reason 迁移）——教训：可预判的口径变化应在测试先行提交写对，
    后续批次执行；
  - **R5（P3）登记**：`services/candidates.py` 导入 `parse.blocks` 私有名
    （`_scan_spans`/`_split_lines`）属封装穿透，功能正确；B2 起 `wants_extra`
    改造触及同区域时一并提为公共 API，本批不动。
- 整改复审（同日）：**闭环，无残留问题**——R1 边界矩阵 16 例、R2 三态
  补温与不误判矩阵均独立实测通过，全量 751 passed 0 skipped，详见审查
  报告 §8。观察项两条随批留痕：`@file/2/3` 多级后缀宽容整词（放行方向
  无害）；`@dir/sub/file.dat/7` 含路径斜杠仍拆散——计划 §2.3 仅要求
  `/N` 后缀，属计划外形态，B2 起相关语料出现再议。

### 8.2 B2 批次（2026-10-19 实施收口）

- 实施序列：progress 开工 → 契约文档先行（roadmap §2.7 例外回补 + openapi
  词表/description + 生成物零 diff）→ 测试先行（G4 表驱动 + G9 用例先红）
  → 实现 → 进度同步，共 5 提交。
- 验收：全量 **772 passed 0 skipped**（入口基线 751，新增 21）；语料基线
  对照（1161 文件）：新增警告 0 文件（阈值 ≤58）；「附加节未以空行终止」
  命中 1 文件（test0162）；「缺分子说明」6 文件全为 `#p restart`——
  B2 前已被既有缺 title/电荷检查拒绝，非本批新增收窄。
- **G16 Rev. C.01 冒烟**（Gen/Pseudo=Cards 附加节，语料 sha256 前缀随批）：

  | 语料 | G16 实测 | B2 判定 | 结论 |
  |---|---|---|---|
  | test0006（Gen 带终止空行，a9cf8103） | Normal termination | 零错误 | ✓ |
  | test0021（Gen 带终止空行，bb775297） | Normal termination | 零错误 | ✓ |
  | test0006 去尾空行（Gen EOF，eac9e797） | 报 `End of file reading basis center` | 附加节未终止阻断 | ✓ 零漏报证实 |
  | test0162（Guess=Cards EOF，1ee742b3） | Normal termination（容忍） | 附加节未终止阻断 | G16 宽于手册（见下） |
  | test0356（gen+pseudo=read 多步，3f064472） | Normal ×3 | 多步拒绝（既有行为） | ✓ |
  | test0491（oniom 括号内 genecp，8f84e772） | Normal ×2 | 零错误（触发不识别） | 官方表边界（见下） |

- **观察项两条（随批登记，不改 B2 裁决）**：
  - **Guess=Cards EOF 实测容忍**：官方表该行 terminator=yes，但 G16 实测
    EOF 收尾正常结束——B2 按手册 SSOT 阻断属「宽于 G16 实际行为」的保守
    收窄（金标准语料 1/1156）。按 §2.12 对「手册 vs 实测」的既定处理原则
    （实测未拒绝不升级），G4 维持 parse_errors 级；若后续同类语料增多再议
    降级为 warnings（需用户裁决，同决策点 3 变更）。
  - **ONIOM 括号内 genecp 不识别**：`oniom(hf/genecp:pm3)` 的 genecp 是
    模型化学值的一部分，非独立 route token——按 §7「禁裸子串」纪律不在
    选项值内做子串匹配，触发词判定保守不报（该文件附加节靠启发式正确
    归类、ECP 节 terminator 不校验）；官方表 GenECP 谓词按独立 token
    口径维持。真实 GenECP 独立关键字形态（`# oniom(...) genecp`）仍可命中。
  - 另登记计划外豁免形态：`#p restart` 任务官方语义「No other input is
    required」（scan 页 Restart 选项），title/电荷/分子说明均可省——
    与 Geom=AllCheck 同类的更强豁免档，现行实现（B1 前起）按缺节拒绝；
    计划未覆盖，语料 6 文件，留痕待议（如需支持另批立项）。
- B2 出口闸门：validate_progress / gen_changelog_md --check 通过；
  B3 入口条件满足。

### 8.3 B3 批次（2026-10-19 实施收口）

- 实施序列：契约文档先行（三响应 warnings + route_duplicate 词表 + 生成物
  零 diff）→ 测试先行（21 用例先红）→ 实现 → 进度同步，共 4 提交。
- 验收：全量 **793 passed 0 skipped**（B2 收口 772 + B3 新增 21）。
- 测试基建随批整改两处（既有缺陷）：
  - `dependencies.py` 顶层循环导入（candidates ↔ engine.materialize）：
    单跑 test_candidates_import 收集失败（全量跑被加载顺序掩盖），
    inputs_path 改延迟导入；
  - `test_extract_keywords` 词典降级用例把空集写入模块级缓存且不清回：
    全量跑时其后拼写通道用例零警告，finally 内 monkeypatch.undo 后
    refresh 恢复。
- **G2 豁免口径 G16 Rev. C.01 冒烟确认**（§2.6 待裁决项，语料 sha256
  前缀随批）：`freq freq=readfcht`（b00df0bc）与
  `iop(5/17=1) iop(6/50=1)`（357d4fe7）两例均 Normal termination、
  无 duplicate/repeated 类报错——裸形+选项形追加取值与 IOp 并写豁免
  **维持豁免**，不回退为警告。
- G3 检测范围实现口径：% 行落 title 的检测覆盖 title 节内任意位置
  （route 缺失时标题行后错置同判）；文件开头前导 % 行归 Link0 收集
  规则，不在本检测面（与官方 Link0 位置语义一致）。
- B3 出口闸门：validate_progress / gen_changelog_md --check 通过；
  B4 入口条件满足。

### 8.4 B4 批次（2026-10-19 实施收口）

- 实施序列：契约文档先行（kind 词表七项 + charge_mult/BOM description +
  生成物零 diff）→ 测试先行（22 用例先红）→ 实现 → 进度同步，共 5 提交。
- 验收：全量 **815 passed 0 skipped**（B3 收口 793 + B4 新增 22）；语料
  警告基线 **17 文件/1.5%**（阈值 5%=58；复审过程：初版 113 文件超阈，
  定位为官方语料形态误报并校准——Variables:/Variable: 无空行直接跟原子
  行时以区头为边界、pbc Tv 平移向量行非原子、哑原子 XX 与同前位 `-` 标记、
  小写 x——校准后 atom_label_unknown 语料内零误报）。
- **既有缺陷随批修正**：engine 记账换算 `_mem_to_gb` mw 单位差 1024 倍
  （2MW 原记 16KB，实为 16MB）、kw 键缺失（%mem=1KW 原 KeyError）、
  `%mem=2GW` 原解析失败回落缺省注入误记 defaulted——统一下沉
  `parse/link0_rules.py` 与值域同源后一并修正。
- **G16 Rev. C.01 冒烟**（多组电荷对 / %cpu=0-5/2 / 自由格式分隔符，
  语料 sha256 前缀随批）：

  | 语料 | G16 实测 | B4 判定 | 结论 |
  |---|---|---|---|
  | test0559（counterpoise=2，841a646c） | Normal ×4 | 零警告零错误 | ✓ 零误报 |
  | g5cpu（%cpu=0-5/2，47b23a33） | Normal | /n 放行零警告 | ✓ |
  | g6ff（自由格式分隔 + O-Bq + 多组对 `0,1 0,1 0,1`，3c623fa1） | Normal | cm 全组 `0 1 0 1 0 1`、formula=H2O1（Bq 不计式）、atom_count=4、无佐证多组对信息警告（warn 级不阻断） | ✓ |

- B4 出口闸门：validate_progress / gen_changelog_md --check 通过。
  **B2–B4 三批全部收口**；下一批 B5（G7 字典扩面 + G8 子选项校验）入口
  条件满足，待用户启动。
- **语料条数阈值复审补登（B2–B4 审查 R6）**：§5 双阈值中的「同文件同
  kind ≤3」维度在上述留痕中失登。审查独立复算证实 test0380.com 的
  title_forbidden_char 共 4 条 > 3（title 3 行含 `_`、1 行含 `#`——官方
  语料 title 误并 route 续行带来的真实禁字，行级检测粒度所致，非误报）。
  复审结论：接受超阈（行级粒度保留精确定位，不改为每文件每 kind 聚合）；
  后续批次语料留痕按文件、条数两个维度分别登记。

### 8.5 B2–B4 批次审查与整改（2026-10-19）

- **独立审查**：code-reviewer 子代理按 AGENTS §6.2 四查执行（不采信实施者
  自述，全部结论独立实测复跑），报告落盘
  `docs/plans/input-verify-gap-b234-review.md`。范围
  `c6b0d6ef..0c60733a`（16 提交）。结论：**有条件通过，无 P1，6 项 P2
  （R1–R6），5 项 P3（R7–R11）**；815 passed 0 skipped、五项闸门、生成物
  零 diff、先行红 worktree 实跑、语料 17 文件/1.47% 全部独立复现吻合。
- **整改处置**（P2 全修，P3 随批；先行红 5 失败后全绿）：
  - R1（Link0 警告行号块内序号）：`check_link0_lines` 增 `line_offset`
    （块首 0 起行号），行号 = 全文件绝对（G0 口径）；duplicate 取首次
    出现行；补前导空行行号断言。
  - R2（读取路径未统一 utf-8-sig）：`verify_and_store`/`save_block`/
    `resolve_title` 三处改 utf-8-sig；补带 BOM 磁盘副本的提交/保存用例
    （写回副本无 BOM）。
  - R3（电荷行斜杠/en-dash 编辑保存误拒）：抽 `blocks.parse_charge_tokens`
    分词单点，`_validate_section`/`_expected_blocks` 对齐 parse_input；
    补 `0/3`、`0,1/0,1`、`–1 2` 编辑保存放行用例。
  - R4（模板 notice.route_duplicates 契约缺口）：openapi
    ComboTemplateMutationResult.notice 增可选 `route_duplicates`
    （Warning 数组）；顺带把分块保存端点 422 reason 词表（含 B3/B4 新增
    route_line_link0_forbidden/link0_misplaced/link0_line_too_long/
    must_be_integer_pairs）按 §4「按分块保存端点自行登记」补入
    saveBlock description；gen_models + gen:types 再生。
  - R5（预览通道缺 route 拼写/重复警告）：preview 端点改走
    `file_warnings` 全集单点（取「对齐矩阵」侧；_file_warnings 随之去
    私有名公共化，沿 B1 R5 先例）；InputPreview.warnings description 同步
    改为引用 Warning.kind 权威词表 + 通道差异（并 P3 R10 一并处置）。
  - R6：见 §8.4 末条补登。
  - P3：R7 组合场景口径在 `check_route_duplicates` docstring 登记 + 用例
    固化（1 裸形+多选项形整体豁免）；R8 属过程教训——后续批次先行测试
    提交前对不可达场景/近邻比值离线预验，实现期测试修订在 commit message
    逐条列明；R9 仓库根 fort.7 冒烟残留已删除（G16 冒烟此后统一临时
    目录运行）；R11 佐证裸子串口径注释、neg_or_frag 冗余条件删除
    （parse_ok=True 时恒可由 len>2 推出，警告发射集不变）、duplicate
    message 措辞改「请确认是否有意为之」。
- 整改出口：全量 **820 passed 0 skipped**（815 + R1/R2×2/R3/R5 新增 5；
  R7 登记口径用例随批固化现有自洽行为）；警告发射集经逻辑等价证明不变
  （R1 只改行号、R11 ②条件化简等价），语料基线无需重算。

### 8.6 B5 批次（2026-10-19 实施收口）

- 实施序列：progress 开工 → 契约文档先行（Warning.kind 词表增
  `route_option_unknown` + 模板 notice 增 `route_option_warnings` 载体 +
  gen_models/gen:types 再生零 diff）→ 测试先行（9 用例先红）→ 实现 →
  进度同步，共 6 提交（bbbdc390 开工、0ec1e484 契约、af0cf810 测试、
  57b34225 实现、5473f537 进度、本条留痕）。
- 验收：全量 **835 passed 0 skipped**（入口基线 820 + B5 新增 15）。
  字典重生成幂等闸门通过（真实 gaussian-kb 在机，重生成逐字节一致实测
  通过、**无 skip**；1166 = 1164 + n + t）；`#t`/`#n` 模板 enforce 通过；
  §2.9 G8 用例清单全绿；warnings kind 词表增 `route_option_unknown`。
  G16 冒烟：§3.1 未设 B5 节点，未执行。
- **口径修正三处（实施期依据官方原文/实现自洽裁决，随批登记）**：
  1. **官方最短唯一缩写判活（G8）**：input 页 Syntax Rules 原文为
     「**All keywords and options** may be shortened to their shortest
     unique abbreviation」——§1.1 摘录漏 "and options"，§2.9 据此推导的
     「缩写选项按未命中记 unknown」与官方原文不符；官方语料实测原口径
     **45.7% 文件误报**（density=curr、freq=numer、guess=lowsym 等官方
     合法缩写被报为非官方选项）。修正为：在该键官方选项集（词典 `键=*`
     组合词）内唯一前缀判活（`scrf=conven` 官方正面例合法、`scf=conv`
     歧义前缀 G16 拒绝仍报）；词级拼写通道（决策点 5）不变。
  2. **`scf=conven` enforce 口径（G7）**：§2.8「scf=conven/conv enforce
     拒绝」与 §2.3/决策点 5「保持整词与键名精确命中」冲突（= 形 token
     键名命中即放行，B1 起如此）——以决策点 5 原文为准：组合词
     `scf=conven`/`scf=conv` **不在典**（词典层面缩写不识别成立）但
     enforce 经键名命中放行；`fre`/`geo` 裸词 enforce 拒绝、warn 近邻
     提示 `freq`/`geom`（测试固化现有自洽行为）。
  3. **词条规模断言三处**：§2.8 登记「两处 1164 断言」实为三处
     （test_extract_keywords 两处 + test_combo_templates
     `test_spelling_words_loaded_and_gate_ready`），先行提交漏改第三处，
     实现提交补齐（R8 教训口径：commit message 逐条列明）。
- **语料基线（`~/g16/tests/com` 1156 文件，两维度）**：
  `route_option_unknown` 命中 **420 文件/36.33%（507 条、69 个去重形态）**，
  超文件数阈值（5%=58）**接受**，归因两类——
  - **A 类（主体）：G03 时代官方测试语料旧形态选项**（G16 手册已删、
    引擎向后兼容）：`geom=modela` 265 条居首（占过半），`scf=novaracc`
    43、`scf=noincore` 20、`units=bohr` 14、`cphf=ultrafine` 14 等；
    手册 SSOT 无据，报「官方选项集中无此项」与 G8 立题（对照官方手册）
    一致，属词典口径固有边界而非误报；warn 级不改变任何阻断语义。
  - **B 类（少量）：面⑤覆盖缺口**——手册明文存在但面⑤按 Options 章节
    `####` 规则未提取的散文提及选项：`opt=addredundant`（opt 页明文
    「AddRedundant is synonymous with ModRedundant」）、`freq=nnroa`
    （freq 页明文保留 G03 数值 ROA）、`units=bohr` 等，另批词典扩面
    解决（§2.12 缩写限制同款处置）。
  - 单文件同 kind ≤3 维度：6 文件超（最大 5 条 test0386），沿用 R6
    裁决（行级粒度保留精确定位，不聚合）。
- **出口闸门**：`uv run pytest` 835 passed 0 skipped、
  `validate_progress.py`、`gen_changelog_md.py --check`、
  `gen_models.py`/`npm run gen:types` 再生零 diff（契约批次）全部通过。
  **B1–B5 五批全部收口**，按 §3.1 版本归属进入 3.4.0 发布流程（冻结
  时点由用户在 B5 验收后确定）。
