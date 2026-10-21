# 输入文件勘误校验缺口补齐计划

> 状态：**已实施并验收**（B1–B9 全部收口，验收留痕 §8.1–§8.16）目标版本 3.4.0。
> 本文由两轮分析凝成：①输入文件勘误能力全面盘点（代码层面）；②gaussian-kb MCP
> 官方规则核对（规则层面）。§1 为官方规则核对结论（本计划的规则 SSOT 摘录），
> §2 为缺口登记与逐项补齐方案，§3 为实施批次，§4 为契约影响，§6 为决策记录。
> 契约（openapi.yaml / sse.md）变更须文档先行
> （roadmap §1 设计原则「契约先行」）。文中行号与各节「现状」描述以2026-10-18 HEAD（g16-webui 分支）为基线，实施时以实际代码与 §8 留痕为准。

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
  逐字节一致 + 1166 规模断言，B5 面⑥ 扩面后为三处：条件真实 KB 测试、
  非条件 loader 测试与
  `test_combo_templates.py::test_spelling_words_loaded_and_gate_ready`），
  **真实知识库缺失时条件测试会 skip**，批次记录必须注明 skip 状态，
  不得当作通过。
- 本计划同时登记一项兼容项：现有 `_EXTRA_KEYWORDS` 含官方表未列出的
  `prop=wrf`；G4 替换触发词集时先以 `COMPAT_EXTRA_KEYWORDS` 保留一版
  兼容触发（§2.12 登记），B6 经 G16 Rev. C.01 冒烟实测拒绝后删除，
  `prop=wrf` 不再触发附加节识别。

---

## 1. 官方规则核对结论（SSOT 摘录）

### 1.1 结构与分隔

- 五节顺序：Link 0（**不**要求终止空行）→ route（要求）→ title（要求，
  **至多 5 行**，避免 `@ # ! – _ \` 与控制字符，尤其 Ctrl-G）→ 分子说明
  （要求）→ 附加输入节（**通常**要求）。
- 语法规则：自由格式、大小写不敏感；行内项目分隔符=空白/制表符/逗号/斜杠
  **任意组合**；选项四种合法形态 `kw=opt`、`kw(opt)`、`kw=(o1,o2)`、
  `kw(o1,o2)`，且 `=` 两侧**允许任意空格**，`=` 可省略；关键字**与选项**
  均可缩写至**全系统最短唯一前缀**（官方原文：「All keywords **and
  options** may be shortened to their shortest unique abbreviation」；
  如 `Conven` 合法而 `Conv` 非法）；`@filename`
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
| G10 | enforce/warn 分工未明且 enforce 存在组合词值侧把关空洞（屏蔽）；面⑤散文提及选项缺口误报官方合法写法（`opt=addredundant` 等，三路互补差集近似全量审计 + 扩面）；语料判据失真（G03 旧形态误作判据） | 修订 | B6 |
| G11 | 电荷/多重度行行内 `!` 注释误拒（分词不剥离注释，官方允许 `!` 任意行任意位置，实测预览/导入/提交记 parse_errors、编辑保存 422） | 正确性 | B7 |

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
   **人工审核触发词全集**（54 行去重后的 key/option 谓词）；官方表未列出
   的 `prop=wrf` 先以 `COMPAT_EXTRA_KEYWORDS = ("prop=wrf",)` 保留一版
   兼容项（见 §2.12），B6 经 G16 Rev. C.01 冒烟实测拒绝后删除，
   触发词集最终即 54 行全集。`parse_input`/`_scan_spans` 的 `wants_extra`
   判定改查
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
  报错），`%` 行出现在 title 位置（title 节内任意位置，含标题行之后错置）
  同样按情形 2 记 `parse_errors`；文件开头的前导 `%` 行归 Link 0 收集规则
  处理，不在本检测面（与官方 Link 0 位置语义一致）。

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
   `%mem` 值域正则与 `%cpu` 列表解析核心下沉到 `web/src/parse/link0_rules.py`
   （公共名 `MEM_VALUE_RE`/`cpu_list_count`），`services/candidates.py` 与
   `engine/workspace.py` 复用；`parse_input` 只依赖该低层模块。engine
   记账换算同步对齐统一单位集：workspace 侧 `_mem_to_gb` 原含官方值域外
   的 `QW` 且缺 `GW/TW`（`%mem=2GW` 原解析失败回落缺省注入并误记
   defaulted），下沉为 `link0_rules.mem_to_gb` 薄封装后删除 `QW`、
   补 `GW/TW` 换算，记账与值域共用同一单位集。`%rwf` 分段值域不纳入校验（目录路径与 `-1`/`0`
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
   三处 1164 断言同步 1164→1166：条件真实 KB 测试、非条件 loader 测试与
   `test_combo_templates.py::test_spelling_words_loaded_and_gate_ready`；
   2026-10-20 勘误：原句「两处」漏计第三处，先行提交因此漏改，实现提交
   补齐——§8.6 口径修正 3）。
   真实 KB 缺失时该测试 skip，批次记录必须注明 skip 状态，不得把 skip
   当作通过。
2. **缩写维持精确匹配（决策点 5，词级）**：`_token_in_dict` 保持整词与
   键名精确命中，不引入词级最短唯一前缀近似；组合词缩写（`scf=conven`）
   经键名命中放行，裸词缩写（`fre`、`geo`）词典层面不识别——enforce 拒绝
   裸词缩写、warn 按拼写近邻提示；缩写误拒登记为已知限制（§2.12），
   如需支持随词典扩面另批立项。（2026-10-20 勘误：原句「`scf=conven`…在
   enforce 下被拒」与键名命中语义不符，§8.6 口径修正 2 已裁决为放行；
   enforce 口径另按决策点 12 于 B6 暂时屏蔽；G8 选项级缩写按官方原文
   唯一前缀判活，见 §2.9。）

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
- **缩写选项**：官方原文 keywords **and options** 均可缩写（§1.1）——
  选项在其键的官方选项集（词典 `键=*` 组合词条目）内按**最短唯一前缀**
  判活（如 `density=curr`、`freq=numer`、`scf=conven`）；键内歧义前缀
  （如 `scf=conv`，同时前缀于 conver/convergence/conventional）不判活、
  仍记 `route_option_unknown`，不引入选项级近邻近似——该警告系键内
  歧义判活的保守残余，不是对 G16 行为的断言：G16 Rev. C.01 实测对
  `scf=conv` 为 Normal termination 接受（B6 冒烟 t5，prose-audit §8；
  B5 原「G16 拒绝」系 opt 页 Conven/Conv 例的错误移植），而
  `freq=readanh` 的同口径歧义警告与 G16 实测拒绝一致（B6 冒烟 t6），
  警告行为维持不回退（§2.12 已知限制）；唯一性空间按键内选项集
  近似——官方口径为「全系统」最短唯一缩写（§1.1），全系统选项全集非
  现行词典可表达，登记为 §2.12 已知限制；（2026-10-20 勘误：
  原句「精确匹配口径同样适用于选项，缩写选项按未命中记
  route_option_unknown」系据 §1.1 漏录 "and options" 的错误推导，与官方
  原文相反——§8.6 口径修正 1 已裁决，原位改写）；
- **分级（决策点 6：仅 warn）**：面⑤按「噪声可控」原则提取，选项覆盖
  非全量，enforce 化必误拒；如需 enforce，先做面⑤覆盖率评估另批立项。
  G4 的触发词匹配为头部精确等值/选项集精确包含，语义与 G8 括号拆解
  不同源，**不复用**拆解辅助，各自独立实现（2026-10-20 勘误：原句
  「复用同一拆解辅助，不另写括号解析」系立项时误设——实施未复用且无
  危害，§8.7 R5，原位改写）。

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

> 新增/变更规则必须在此矩阵登记「阻断 / 警告 / 不校验」，作为通道一致性判据。矩阵登记本计划全部批次（含 B6/B7）实施完毕后的
> 目标口径：`模板` 列的 route 拼写警告以 G10-a（决策点 12，enforce
> 屏蔽）为依据，G10-a 落地前模板保存维持现行 enforce 行为。`模板`
> 指组合流模板保存。**预览列的「阻断」
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
| route 拼写 | 警告 | 警告 | 警告 | 警告 | 警告 |
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
| `prop=wrf` 非官方触发词 | 官方 Section Ordering 未列，原实现已支持 | 经 `COMPAT_EXTRA_KEYWORDS` 保留一版（冒烟节点 B6 出口，§3.1）；B6 G16 Rev. C.01 冒烟实测拒绝（QPErr syntax error），常量删除、`prop=wrf` 不触发附加节识别（`any_trigger` 判 False，测试固化） |
| 分子说明/Variables EOF 阻断 | 历史文件常以 EOF 收尾；G16 是否一律拒绝未做全量实测 | G9 仅给非阻断 warnings；若实测 G16 拒绝，再另批升级为阻断 |
| title 语义/内容质量 | 程序不解释 title | 仅校验字符与行数 |
| Link 0 未知指令阻断 | 历史模板可能含自定义 `%` 指令 | 仅 warnings（决策点 7） |
| `%rwf` 分段值域校验 | 分段含目录路径与 `-1`/`0` 特殊值语义，离线静态校验误报率高 | 不校验；G16 运行期报错 |
| 关键字与计算类型组合合法性（如 NMR 仅限 HF/DFT/MP2） | 需完整语义模型，离线静态校验不可行；G8 仅覆盖选项-关键字归属 | 交 G16/testrt，登记为已知限制 |
| `opt==calcfc` 类双等号畸形 token | 选项型键跳过词级近邻后零警告（B5 选项化前可得拼写近邻建议） | 宁漏勿误口径内；G10-b 实施时顺带评估拆解层可报性，不单独立项 |
| 选项缩写唯一前缀的判定空间 | 官方唯一性空间为「全系统」（§1.1），全系统选项全集非现行词典可表达，离线不可精确判定 | §2.9 按键内官方选项集唯一前缀判活，较官方口径宽、仅漏报方向（warn 级宁漏勿误）；登记为已知限制 |
| `#p restart` 豁免档 | 官方 Restart 语义「No other input is required」，title/电荷/分子说明均可省，强于 Geom=AllCheck；现行实现按缺节拒绝（B2 语料 6 文件，§8.2） | 接受集窄于官方的已知限制；如需支持另批立项 |
| `@file` 含路径的多级 `/N` 后缀 | §2.3 词法仅要求尾部 `/N` 吸附；`@file/2/3` 类纯数字多级后缀宽容整词（放行方向无害），`@dir/sub/file.dat/7` 含路径斜杠仍拆散（§8.1 观察项） | 计划外形态，相关语料出现再议 |
| Guess=Cards EOF 手册与实测分歧 | 官方表 terminator=yes，G16 Rev. C.01 实测 EOF 收尾容忍（语料 1/1156，§8.2） | G4 维持 parse_errors 级；同类语料增多再议降级 warnings，需用户裁决（同决策点 3 变更） |
| 键内歧义前缀警告的保守残余（`scf=conv` 类） | 词典选项集有限，键内歧义前缀无法离线判定 G16 实际接受面；`scf=conv` G16 Rev. C.01 实测接受（B6 冒烟 t5）而警告照发，同口径的 `freq=readanh` 歧义警告与 G16 实测拒绝一致（t6） | warn 级保守口径维持不回退；登记为已知限制 |
| title 禁字警告行级粒度（每行仅报首个禁字） | warn 级不影响阻断语义；行级粒度保留精确定位（B2–B4 审查 R6 裁决：不聚合），同行其余禁字对用户不可见（语料 test0380 同文件 4 条即此粒度所致） | 维持现状；如需 message 单行列出该行全部禁字，另批立项 |
| 缺省补全等价性在值域外声明上的边界（已消除，2026-10-21 用户裁决） | B9 实测登记：原实现按「值可解析与否」判定补全，值域外声明（%mem=2W/abc/空值类）被按缺失处置注入缺省行（后值覆盖前值），补全后文本新增恰一条 link0_directive_duplicate 补全伪影，「缺省补全前后 file_warnings 内容集等价」在此类上不成立（B9-review R1 担忧的实证面） | 用户裁决收窄补全口径（§8.14）：仅指令行缺失时注入；存在但值非法时不再注入，非法输入由 link0_value_invalid 警告承载、G16 运行期裁决——等价性自构造恢复，duplicate 伪影消除；实现与测试留痕 §8.14，测试边界例改写回等价断言 |

---

### 2.13 G10 · enforce 口径屏蔽与 B 类词典扩面（B6，2026-10-20 立项）

**立项背景（B5 实施与独立审查后的复盘结论，§8.6–§8.8；缺口均为当前
实现真实存在的缺陷，不以登记替代修复）**：

- **enforce 与 warning 口径分工未明**：模板保存 enforce
  （`keyword_not_in_dict` 422 拒绝）与各通道 warn 的分工无产品级裁决，
  且 enforce 存在结构性把关空洞——= 形 token 键名在典即放行，值侧从不
  阻断：同类拼写错误，裸词形态（`frqu`）被拒绝、组合词形态
  （`freq=numar`）仅警告。**决策点 12：暂时屏蔽全部 enforce 口径，仅
  启用 warning**。
- **B 类词典覆盖缺口（确凿误报，当前持续发生）**：手册明文存在但面⑤未
  提取的散文提及选项被报 `route_option_unknown`，已确认两形态：
  `opt=addredundant`（6 条，opt 页明文「AddRedundant is synonymous with
  ModRedundant」）、`freq=nnroa`（4 条，freq 页 ROA 条目明文保留 G03
  数值 ROA）。面⑤按 Options 章节 `####` 规则提取，散文提及的完整缺口
  **未做全量审计**，除已确认形态外不排除更多——补审计前不存在
  「无误报」的证据。语料另有两形态经官方原文复核判归 A 类（预期警告，
  不入典）：`td=(window(13,-12)…)`/`cis=(window=(13,-12)…)` 共 7 条
  （td 宿主 4、cis 宿主 3，G03 时代 TD/CIS 选项，G16 手册 TD/CIS 页
  均无 Window）、`units=bohr` 14 条（units 页官方选项为
  Ang/AU/Deg/Rad，`bohr` 非官方选项名，仅系 AU 的散文释义）。
  **决策点 13：B 类词典扩面正式立项**。
- **语料判据失真**：官方自带测试语料（`~/g16/tests/com`）陈旧，大量
  G03 时代旧形态（`geom=modela` 265 条等）不能作为本项目的错误判据。
  **决策点 11：G16 为最大支持对象、G09 次之，G03 及更早确认不支持；
  官方测试语料降级为回归对照样本，不作为权威参考**——A 类旧形态命中
  `route_option_unknown` 为预期行为（G03 不受支持），错误判据一律以
  手册 SSOT（gaussian-kb）与 G16 实测为准。

**方案**：

1. **G10-a enforce 屏蔽（独立提交）**：模板保存词典校验降为仅警告
   （`SPELLING_MODE` enforce → warn，单点消费以实际代码为准），
   `keyword_not_in_dict` 不再 422 拒绝，拼写错误仅随 notice 携带；
   enforce 相关用例改 warn 口径断言（含 `ignore_spelling=true` 与不传
   行为一致的 warn 等价断言）；契约 description 同步（模板保存
   不再拒绝词典外词）；`ignore_spelling` 请求字段保留不删（避免契约
   破坏），description 注明 enforce 屏蔽期间不生效，前端
   `ComboTemplatesModal.vue` 的「忽略拼写警告并保存」豁免按钮随 warn
   化隐藏（隐藏后按 AGENTS §6.2 以浏览器实测验收）；
   `combo_templates.py` 模块头切换纪律 docstring 同步改写
   （warn 为现行口径，恢复条件见决策点 12）。enforce/warn 分工重新裁决
   后另批恢复，恢复时须先解决组合词值侧把关与缩写口径的一致性
   （§2.8/§2.9 现行口径为恢复基线）。
2. **G10-b 词典扩面**：面⑤散文提及选项**三路互补差集近似全量审计**
   （散文裸选项名不含键前缀、跨页引用不落在宿主页，单一路径不构成
   全量；「全量」的精确含义为三路互补的近似全量——路②限于 keyword 页
   Options 章节条目正文，Options 章节外的散文裸词提及与非 keyword 页
   散文除字面 `键=选项` 形态外不在任何一路覆盖面内）——①全分类页面
   （不限 keyword 页）字面扫描 `键=选项` 形态；
   ②keyword 页 Options 章节条目正文内按页 slug 所属关键字对散文裸选项
   名做归属推断（首字母
   大写、非既有 Options 条目、与页主题近邻，如 opt 页「AddRedundant is
   synonymous with ModRedundant」；同一散文提及归属多载体（该句并见
   opt/geom 两页）时逐条标注载体裁决）；③语料命中形态反查手册 SSOT
   （§8.6 B 类两形态即由此证实）。三路与词典组合词条目做差集，产出缺口
   清单随批留痕，清单逐条人工复核留痕后方可入典；缺口按清单补提取：
   提取规则可覆盖的走提取规则，规则
   覆盖不足处（散文提及、跨页引用等）在 `extract_keywords.py` 内以受
   版本管理的手工补录常量清单入典，与提取产物同受幂等闸门与规模断言
   约束；载体关键字一律按语义确定而非页 slug；
   重生成词典并过幂等闸门与规模断言；已确认 B 类形态零警告复测；A 类
   旧形态命中为预期行为，不因扩面消除（`td=(window(13,-12)…)` 与
   `units=bohr` 等 A 类判归形态不入典，见立项背景）；`keywords.py` 中
   涉及 window 形态判定的注释（`_PAREN_TAIL` 条）同步按 A 类口径修正
   （G16 手册 TD/CIS 页无 Window，警告为预期行为）。
3. **`opt==calcfc` 类畸形 token 静默**：已登记 §2.12，G10-b 实施时
   顺带评估拆解层可报性，不单独立项。

**预期效果**：官方合法写法不再产生内容为错的警告；模板保存零误拒；
错误判据与语料口径对齐受支持版本。

**涉及文件**：`web/src/services/combo_templates.py`（G10-a 单点）、
`scripts/extract_keywords.py`、`web/src/parse/keywords.txt`（重生成）、
`web/src/parse/keywords.py`（断言相关）、前端
`ComboTemplatesModal.vue`（豁免按钮）、
`web/src/engine/workspace.py`（模块头 docstring 旧单位口径残留顺带修正）、
相关测试与契约 description。

### 2.14 G11 · 电荷/多重度行行内 `!` 注释误拒（正确性修复，B7，2026-10-20 立项）

**现状**：`parse_charge_tokens`（`web/src/parse/blocks.py:143-149`）对
电荷/多重度行仅做 en-dash/逗号/斜杠归一后按空白切分，不剥离行内 `!`
注释；官方允许 `!` 出现在任意行任意位置（§0.2/§1.1）。实测
`0 1 ! neutral singlet` 与 `0,1 0,1 0,1 ! cp pairs` 在预览/导入/提交均记
parse_errors「电荷/多重度行无法解析」（阻断），编辑保存
`_validate_section` 经同一单点同样 422——官方合法文件被误拒，且解析
失败时 `charge_mult` 规范化输出保留含注释原文。route 通道的行内注释
已由 C3 管道处理；原子行取首字段与位置参数，行内注释不影响解析
（实测零错误）；仅电荷/多重度行受累。§2.11 矩阵「电荷/多重度格式」行
的阻断语义在该形态上与官方规则矛盾。

**官方依据**：§1.1 语法规则——注释以 `!` 起始，可出现在任意行任意
位置；独立注释行可出现在文件任意处。

**方案**：`parse_charge_tokens` 在归一化前剥离**引号外**首个 `!` 及其后
内容（与 C3 管道同规：引号内不截断），剥离后再走既有 en-dash/分隔符
归一与整数对校验；`parse_input` 与 `_validate_section` 经同一单点自动
拉齐，`charge_mult` 规范化输出不含注释文本。剥离后 token 不足或非整数
的行仍照常记 `parse_errors`（编辑保存阻断），既有判定不变。

**行为变更登记**：接受集扩大（此前被误拒的合法文件恢复放行），预览/
导入/提交/编辑保存四通道同步，CHANGELOG 登记；无 schema 与 warnings
kind 词表变更。

**涉及文件**：`web/src/parse/blocks.py`（`parse_charge_tokens` 单点）；
测试 `web/tests/test_parse_blocks.py`、`web/tests/test_block_save.py` 补
用例：单组对行内注释零错误且 `charge_mult` 无注释、多组对行内注释零
错误、引号内 `!` 不截断、剥离后 token 不足/非整数仍报错、编辑保存通道
放行。

**G16 背书**：B7 出口以真实 G16 Rev. C.01 冒烟一例（电荷行行内注释）
确认正常结束；若实测与手册分歧（G16 拒绝该形态），按 §2.12
Guess=Cards 先例登记分歧并回评处置（需用户裁决），不在分歧未决时维持
放行口径。

### 2.15 G12 · 导入/提交 warnings 前端渲染落地（B8，2026-10-21 立项）

**立项背景**：B1–B7 全面复审（2026-10-21，报告
docs/plans/input-verify-gap-remediation-plan-B14-review.md）登记 P2 R1：
§2.0.1/§2.5/§5 明列「CandidatesView.vue 渲染导入/提交 warnings」，
后端数据面（B1 warnings 通道、B3 导入/提交接入）已交付，前端渲染跨
B1 与 B2–B4 两轮审查遗留未落地且无取舍留痕——导入（`files[].warnings`）、
单任务提交（`SubmitResponse.warnings`）、队列提交（逐条附 `task_id`）
三条链路的响应 warnings 在候选页无任何渲染点。

**方案**：
- CandidatesView.vue 导入：导入成功响应按文件聚合非空 warnings，
  工具条下方琥珀清单区（与既有 422 逐文件失败清单同构、warn 色档），
  条目形态「文件名 ⚠ 第 N 行 message」；再次发起导入即清空；
- CandidatesView.vue 单任务提交：提交成功响应 warnings 于工具条
  琥珀注记展示（与既有 submitNote 中性规范化注记同级邻位），条目
  「⚠ 提交警告 — 第 N 行 message」（BlockEditor 保存警告同款文案纪律）；重新
  打开提交确认框即清空；
- QueueEditorModal.vue「直接提交」：done 注记下方逐条渲染
  「⚠ 任务 #task_id — 第 N 行 message」；弹窗重开/再次保存即清空；
- 历史重新排队与续跑响应（HistoryView/ResumeDialog）的 warnings
  渲染不在本项（候选页之外），登记为后续按需项。
- QueueEditorModal「再次保存即清空」为必做实现动作：B8 落地为弹窗重开
  清空（`watch(open)` 重置），保存成功路径清空 `submitWarnings` 尚待
  实现，随下个前端批次承接；验收=浏览器实测「直接提交见警告→再次保存
  后警告消失」。

**视觉实测（AGENTS §6.2）**：playwright 浏览器实测四场景——导入拼错
关键字文件见琥珀清单；单任务提交后见工具条琥珀注记；队列直接提交见
task_id 归属警告；B6 视觉补测三场景（组合流模板弹窗无豁免按钮、
词典外词保存 200 琥珀警告、%mem=0 红描边 422）随同批执行并留痕 §8。

**涉及文件**：web/frontend/src/views/CandidatesView.vue、
web/frontend/src/components/QueueEditorModal.vue；无契约与后端变更
（warnings 契约形态 B3 已定，纯前端消费）。

**验收标准**：四场景浏览器实测通过；全量测试不回归；前端闸门
（audit_frontend_offline.sh、check_tokens.py、check_contrast.py）全绿。

### 2.16 G13 · 提交前核验预显、警告文案、条目堆叠与持久化复验（B9，2026-10-21 立项）

**立项背景**：B8 收口后用户裁决（2026-10-21）——①警告条目文案再修订：
行号改「L行号」紧凑形、上下文与行号以冒号相接，相关表述随同改动，
不得以「—」作统一分隔；②警告 `message` 不得为内部英文式警告，须为
中文警告语；③警告随候选持久化并在编辑后复验，仅「分块编辑修复」与
「删除候选」两条路径可消除；④警告条目大量堆叠时不得溢出、被吞、
被遮挡；⑤（同日补充裁决，B9 本意核心）核验警告必须前置到提交确认
之前——单任务提交确认框与队列编辑弹窗在动作发生前即完成全面核验并
如实警告，粒度为任务级（每个输入文件各自呈现自己的核验结果）；
提交后才首次告知核验结果不可接受；⑥（同日补充裁决）核验信息必须
永远取最新结果——Link0 缺省补全后核验（判定以补全后文本为事实
基础），用户分块编辑修正后即时复验，任何展示点不得出现「用户已
修正、警告仍滞后保留」。

**现状**（B8 交付形态）：
- 条目口径：导入琥珀清单按文件聚合、条目「文件名 ⚠ 第 N 行 message」；
  单任务提交工具条注记「⚠ 提交警告 — 第 N 行 message」；队列直接提交
  「⚠ 任务 #task_id — 第 N 行 message」；导入清单汇总行「导入警告
  N 条 — 非阻断，已入库」；
- 警告均为动作当时的一次性提示：导入/提交响应的 warnings 仅在当时的
  琥珀区渲染，再次发起动作即清空；候选列表行无警告状态，分块保存的
  warnings 仅随保存响应出现——带警告候选在动作过后无处可见，也无从
  得知是否已修复；
- `message` 产出点已以中文为主（§2.0.1 口径），但「一律中文警告语」
  未作为逐 kind 硬口径固化（无 message 模板清单与断言；kind 字样系
  机器通道标识，不得进入 message 文案）；
- 提交确认框与队列编辑弹窗在动作前不呈现任何核验警告：单任务确认框
  打开时已取回 `/candidates/{id}/preview`（其 `warnings` 为 B1 通道、
  与导入/提交/分块保存同走 `file_warnings` 全集单点）但未消费；队列
  弹窗打开时已逐成员并行取回 preview（`loadLinkStates` 依赖勾选初始
  化）但仅消费 Link 0 行、warnings 同样未消费——核验结果首次呈现时机
  为提交成功响应之后（§2.15 B8 交付形态，裁决⑤判定不可接受）。

**方案**：
1. **提交前核验预显（裁决⑤落地，本项核心）**：核验数据源一律为既有
   `GET /candidates/{id}/preview` 的 `warnings`（B1 通道，与提交核验
   同一解析管道与 `file_warnings` 全集单点，行号为全文件绝对行号；
   无后端与契约变更）。单任务：提交确认框打开时消费 `openSubmit`
   已取回的 preview warnings，确认框内新增琥珀警告区逐条渲染（条目
   按本批新文案口径「⚠ L行号 message」），零警告零渲染；用户在知情
   后确认提交，提交后工具条琥珀注记保留为提交回执。队列：编辑弹窗
   （创建态与编辑态）打开时对每个成员取 preview——复用既有
   `loadLinkStates` 的并行取数路径（现状打开时已逐成员拉取 preview
   仅消费 Link 0 行，本批扩展为同一响应并消费 warnings，不新增第二条
   请求路径；前端消费既有端点，成员规模内成本与预览通道同量级），
   逐成员在成员行下渲染该成员自己的
   warnings（任务级归属，条目「⚠ L行号 message」，限高滚动随本批
   堆叠口径）；成员 preview 取回失败该成员占位提示、不阻断其余成员。
   提交期注入/改写（如接续 chk 注入、规范化换行）不在预显口径——
   预显=当前存储文本的核验，提交响应 warnings 保留为回执（队列含
   task_id 归属，为提交后独有信息）。核验口径为补全后事实（裁决⑥）：
   Link0 缺失项在派发时经 `resolve_link0` 按运行级设置缺省注入
   （补全单点，completed_text 为 G16 实际执行文本），核验判定须以
   补全后文本为事实基础。当前缺省值经设置校验恒为合法值、缺失指令
   本身不产 warnings（仅中性「未声明 · 执行时将按默认值补齐」注记），
   故存储文本核验与补全后核验的 warnings 内容集恒等。补全为行注入
   （`resolve_link0` 将缺省行插入 Link 0 块末尾），注入 N 行时 Link 0
   块之后所有警告行号整体 +N——等价性口径为 `(kind, keyword, message,
   suggestion)` 多重集逐条一致、行号差恰为注入行数；B9 以测试断言
   固化该等价性（缺省补全前后 `file_warnings` 按上述口径比较）作为
   回归闸门；预显行号不取补全后文本，维持存储文本绝对行号（与预览/
   编辑所见一致）。若未来补全规则或缺省值校验变化破坏等价，预显链路
   改为消费 `resolve_link0` 之后的 completed_text 核验（补全单点不动）。
   （2026-10-21 追记：B9 实测发现值域外声明类的等价破例后，用户裁决
   收窄补全口径为仅指令行缺失时注入，破例自构造消除，留痕 §8.14；
   本 fallback 条款对未来变化继续有效。）
2. **文案修订**：导入琥珀清单条目改为自含形「⚠文件名: L行号 message」
   （文件名入条目，按文件分组取消；汇总行同步改为「导入警告 N 条」）；单任务提交注记条目改为「⚠ L行号 message」（去
   「提交警告」前缀，上下文由所在琥珀区承担）；队列直接提交条目改为
   「⚠ 任务 #task_id: L行号 message」；行号一律「L行号」形；警告族内
   相关表述（汇总行、详情区标题等）随同改口径，分隔一律冒号或括注；
   `message` 逐 kind 审计并固化为中文警告语（关键字名、选项名、单位
   等术语保留原文），模板清单随批留痕并以测试断言固化。
3. **条目堆叠**：全部警告展示区（导入清单、提交注记区、单任务确认框
   预显区、队列弹窗注记区与成员预显区、候选详情警告区）实施限高滚动
   （既有先例：提交确认框完整
   输入限高滚动），限高值与滚动样式自行设计、须符合既有前端风格
   （设计令牌、mono 行形）；条目再多都不得溢出容器、被裁切吞没或遮挡
   其他内容。本批前端实现的视觉样式一律复用既有设计令牌，不得私设
   令牌或在组件内硬编码字面值；既有令牌无法覆盖时，先在令牌库
   （`web/frontend/src/styles/tokens.css`，含 m0-ui-preview.html 样板
   同步，受 check_tokens 闸门约束）新增令牌再引用。
4. **持久化与复验**：核验新鲜度为硬口径（裁决⑥）——全部警告展示点
   （预显、列表徽标、候选详情、提交回执）一律现算自当前存储文本，
   禁止任何落库快照或滞后保留；用户经分块编辑修正后，保存响应即
   复验结果，对应警告在徽标、详情与再次打开的预显中即时消退，不得
   出现「用户已修正、警告仍保留」。导入警告不阻断导入（既有语义）；带警告文件入库
   后警告随候选持续显示，用户主动消除仅两条路径——分块编辑修复（保存
   后复验）或删除候选；提交规范化补空行使 EOF 类警告随复验自然消退，
   属复验机制的自然结果、不属用户主动消除路径；重复导入同一文件新建
   条目、不覆盖既有条目（既有
   语义），不构成消除手段。机制（派生即复验，不落库）：候选列表条目
   增 `warning_count`，由列表端点对分页切片后的当前页条目现算
   （`file_warnings` 全集单点，页大小内解析成本与预览通道同量级；
   不进入切片前的全量视图构建，避免成本随全量候选数增长）；候选行
   「文件名」与「标题」列之间新增无表头占位列承载琥珀「⚠ N」徽标
   （N>0 时显示并附 title/aria 语义标注，N=0 时空置占位；列宽令牌
   `--warn-col-width` 钉宽定值（max-width+overflow hidden 与内容
   解耦，I-1 续整改 §8.16），行级显隐与末徽标消失均不引起列移。
   无表头系对既有表格「列均有列名」规范的显式授权偏离）；选中候选
   的预览区各分块下方渲染该候选当前对应区块的 warnings
   详情（取预览 `warnings`，条目「⚠ L行号 message」，限高滚动）；分块
   保存响应即新 InputPreview + warnings，保存成功后详情即复验结果并
   刷新列表徽标（BlockEditor 现无对外事件，本批新增保存完成事件供
   候选页刷新徽标与详情）；提交规范化改写文本后经列表刷新同径复验。§2.15 已
   登记的 QueueEditorModal「再次保存即清空」必做实现动作随本批队列
   弹窗改造承接；HistoryView/ResumeDialog 渲染维持 §2.15 后续按需项
   登记不变。

**契约动作**：候选列表条目（Candidate）增 `warning_count: int`（必填；
沿 `title` 先例为响应中现算、不落库字段，schema description 同步注明
现算口径；先改
openapi.yaml；gen_models + gen:types 再生零 diff）；`Warning` schema 与
kind 词表不变（message 中文口径为文案修订，非 schema 变更）；提交前
核验预显零契约变更（消费既有 InputPreview.warnings 通道）。

**涉及文件**：`web/src/parse/keywords.py`、`web/src/parse/blocks.py`、
`web/src/parse/link0_rules.py`（message 逐 kind 审计）； 
`docs/api/openapi.yaml`；`web/src/routers/candidates.py`（列表现算）；
前端 `CandidatesView.vue`、`BlockEditor.vue`、`QueueEditorModal.vue`；
测试：逐 kind message 中文断言、列表 `warning_count` 链路用例（导入带
警告 → N；分块修复保存后 → 0；删除随行消失）、缺省补全前后
`file_warnings` 内容集等价断言（含行号平移口径）、
`test_contract_rest.py` Candidate 契约用例、堆叠限高场景用例。

**验收标准**：提交前核验预显——打开单任务确认框即见该文件全部核验
警告（拼错关键字等），零警告零渲染；打开队列弹窗（创建态与编辑态）
即见各成员自己的 warnings（任务级归属正确），成员 preview 取回失败
仅该成员占位提示、不阻断其余成员；两链路浏览器实测留痕。
核验新鲜度——分块修正保存后，徽标、详情与再次打开的预显中对应
警告即时消退（无滞后保留，浏览器实测）；缺省补全前后 `file_warnings`
内容集等价性（含行号平移口径）以测试断言固化。
三条链路条目文案逐字符合新口径（浏览器实测）；逐 kind
`message` 模板清单全中文并测试固化；多警告限高滚动无溢出/裁切/
遮挡；导入带警告 → 占位列徽标与详情出现（徽标显隐无列移），分块
修复保存后复验消退，删除候选随行消失，重复导入同文件各自带警告互
不影响；「再次保存即清空」
落地；全量测试不回归；前端三闸门（audit_frontend_offline.sh、
check_tokens.py、check_contrast.py）全绿。

---

## 3. 实施批次

| 批次 | 范围 | 验收标准 | 契约动作 |
|---|---|---|---|
| B1 正确性修复 + 前置通道 | G0+C1+C2+C3 | 既有全量测试不回归；记录实际 passed/skipped 数与 skip 原因；`warnings` 通道就位且默认空列表、含 `message`；五类误拒形态 + 无等号空格形 + 引号值 + 括号 Geom + `Geom=Check` 用例转绿；Checkpoint 缺电荷/缺 title 被拒、AllCheck 不变 | 抽共享 `Warning` schema；openapi 增 `warnings` 形态（`message` 必填、`suggestion`/`task_id` 可选）；InputPreview 增可选 `warnings`；生成物再生零 diff |
| B2 数据固化 | G4+G9 | `section_ordering.py` 表与 §1.2 逐行一致（59 = 4 core + 54 additional + 1 automatic）；`any_trigger` 只消费 additional 且普通 route 下为 False；G9 的 route/title EOF 阻断用例、分子说明/Variables EOF 警告用例与两种吞并归因用例转绿，空分子说明缺节阻断用例转绿；roadmap §2.7 回补（2 例外 + Title 行括注 + Checkpoint title 补全） | warnings kind 词表增 `molecule_unterminated`、`variables_unterminated`；附加节终止空行按决策点 3 记 parse_errors，parse_errors description 同步更新 |
| B3 新检测 | G1+G2+G3 | 导入/提交响应携带 `warnings`（导入 422 响应的 `details.errors[]` 不携带）；三个响应返回点全部取 `res["normalized"]`（candidates/queues/history）；resume 响应透传 warnings；队列提交 warnings 带 `task_id`；重复/错位用例按 §2.6 判定表与 §2.11 矩阵在各通道行为一致 | warnings kind 词表增 `route_duplicate`（Link 0 错位按决策点 3 记 parse_errors）；CandidateCreate.files、SubmitResponse、ResumeConfirmResponse 增可选 warnings（**先改 openapi.yaml**） |
| B4 值域与原子行 | G5+G6 | §2.7 用例全绿；§2.11 矩阵逐格符合；`%mem=2W` 编辑保存阻断、导入/提交警告（决策点 2 收紧；模板无单位输入，不适用）；`%mem=0` 编辑保存/模板 `mem_gb` 阻断、导入/提交警告（决策点 8）；`%cpu=0-5/2` 通过；多组电荷对、负多重度组与 `Fragment` 佐证用例、自由格式分隔符、`Foo` 不告警、`Zz` 告警、`X` 哑原子、BOM 落盘剥离全部通过 | warnings kind 词表增 `link0_value_invalid`、`link0_line_too_long`、`link0_directive_unknown`、`link0_directive_duplicate`、`title_forbidden_char`、`atom_label_unknown`、`molecule_multiple_charge_pairs` |
| B5 字典扩面 | G7+G8 | 字典重生成幂等闸门通过（1166 词条；三处断言同步；KB skip 记录）；`#t`/`#n` 模板保存通过；`scf=conven`/`scf=conv` 组合词经键名命中放行、`fre`/`geo` 裸词 enforce 拒绝（缩写不识别限于词典层面，§8.6 口径修正 2）；G8 用例（在典零警告/未知选项/嵌套取值/`opt=(readfcht)` 跨关键字/`opt=(readfc)` 零警告/`opt=(calcfc,xyzzy)` 仅报未命中选项/`opt=(calfcf)` 附 `suggestion=calcfc`/IOp 零警告/ONIOM 零警告/External 零警告）转绿（2026-10-20 勘误：原验收「两处断言」「scf=conven/conv enforce 拒绝」与实施口径不符，原位改写） | warnings kind 词表增 `route_option_unknown` |
| B6 口径修订与词典扩面 | G10-a+G10-b | 模板保存拼写错误仅警告、零 422（enforce 屏蔽，决策点 12）；warn 口径断言含 `ignore_spelling=true` 与不传行为一致；前端豁免按钮隐藏以浏览器实测验收（AGENTS §6.2）；面⑤散文提及选项审计三路差集清单落盘并逐条人工复核留痕，复核通过的缺口选项全部入典（幂等闸门 + 规模断言同步）；`opt=addredundant`/`freq=nnroa` 零警告复测通过，`td=window`/`units=bohr` 等 A 类判归形态维持预期警告不复测（决策点 11）；全量测试不回归；语料基线仅作回归对照记录（不作通过判据），扩面后复跑并逐条归因 `route_option_unknown` 增量、不得含唯一前缀歧义翻转型新增误报，A 类判归形态顺带记录 G16 实测对照（不作判据）；G16 冒烟按 §3.1 B6 清单执行（B 类复测、`prop=wrf` 一例、缩写判活正反例各一）；`keywords.py` 中 window 相关注释按 A 类口径修正；`web/src/engine/workspace.py` 模块头 docstring 旧单位口径残留顺带修正 | 模板保存端点 description 更新（enforce → 仅警告；ignore_spelling 注明不生效）+ 生成物再生零 diff；warnings 词表不变 |
| B7 正确性补修 | G11 | `parse_charge_tokens` 剥离引号外 `!` 行内注释后，`0 1 ! …` 与 `0,1 0,1 0,1 ! …` 在预览/导入/提交零错误、编辑保存放行，`charge_mult` 规范化输出不含注释文本；剥离后 token 不足/非整数仍报错；既有电荷行用例（斜杠/en-dash/多组对）不回归；全量测试不回归；G16 冒烟一例（电荷行行内注释）实测背书，实测与手册分歧按 §2.14 登记 | 无 schema 与 kind 词表变更；CHANGELOG 登记接受集扩大 |
| B8 前端渲染收口 | G12+全面复审 R2–R5、F-2 随批整改 | 四场景浏览器实测通过（导入琥珀清单/提交工具条注记/队列 task_id 警告 + B6 补测三场景）；全量测试不回归；前端三闸门全绿 | 无契约变更（纯前端消费既有 warnings 形态） |
| B9 提交前核验预显、警告文案、堆叠与持久化复验 | G13 | 单任务确认框与队列弹窗提交前即见文件级核验警告（任务级归属、零警告零渲染，浏览器实测）；分块修正保存后警告即时消退无滞后、缺省补全前后 warnings 内容集等价性（含行号平移口径）测试固化；条目文案与逐 kind 中文 message 按 §2.16 逐字落地并测试固化；导入徽标/编辑修复复验消退/删除随行消失/重复导入互不影响全链路浏览器实测；多警告限高滚动无溢出/裁切/遮挡；「再次保存即清空」落地；全量测试不回归；前端三闸门全绿 | Candidate 增 `warning_count`（必填、响应中现算不落库，openapi 先行 + 生成物零 diff）；kind 词表不变；提交前预显零契约变更（消费既有 InputPreview.warnings） |

### 3.1 批次依赖与节点

- **B1 必须先行**：C3 的 token 化管道与 G0 的 `warnings` 通道是 B2/B3/B4/B5
  的公共基座；B1 完成前不得启动其余批次的实现。
- **B2→B3→B4 串行**：三批都触及 `blocks.py` 的 `parse_input`，且 B3 要
  把 G2/G3 警告接入同一返回结构；不建议并行修改同一文件。若确需并行，
  先把 warnings 生成拆成独立模块并冻结接口，再按文件所有权拆分。
- B5 依赖 B1（G8 复用 C3 管道、G7 依赖同一 `_token_in_dict`），与 B2–B4
  无强依赖，可最后执行。
- **B6（2026-10-20 立项，§2.13）**：依赖 B5（已收口）；G10-a enforce
  屏蔽独立提交、G10-b 词典扩面同批完成（实际提交序列以 prose-audit
  §9.2 R3 勘误留痕为准）；出口另加 G16 冒烟
  （`opt=addredundant`/`freq=nnroa` 及其宿主关键字各一例，确认零误报；
  `prop=wrf` 兼容触发词随同批冒烟一例确认——G16 Rev. C.01 实测拒绝
  （QPErr syntax error），`COMPAT_EXTRA_KEYWORDS` 据此删除——决策点 9）；
  缩写判活实测背书（`freq=numer` 判活零
  警告；`scf=conv` 歧义前缀报 `route_option_unknown`，G16 Rev. C.01
  实测接受、警告系键内歧义判活的保守残余；`freq=readanh` 歧义警告与
  G16 实测拒绝一致——补足 B5 未设冒烟节点的 G8 唯一前缀口径实测背书）。
- **B7（2026-10-20 立项，§2.14）**：依赖 B4 的电荷行分词单点（已收口），
  与 B6 无文件交集、无先后约束；出口 G16 冒烟一例（电荷行行内注释）
  实测背书，实测与手册分歧时按 §2.12 Guess=Cards 先例登记并回评。
- **B8（2026-10-21 立项，§2.15）**：依赖 B3 的 warnings 数据面（已收口），
  与 B7 无文件交集；出口含 B6 视觉补测三场景（B57 审查待办承接）；
  全面复审 P3（R2–R5、F-2）同轮随批处置，留痕 §8.12。
- **B9（2026-10-21 立项，§2.16）**：依赖 B8；提交前核验预显（裁决⑤
  核心）、文案修订、message 中文审计、堆叠限高与持久化复验同批完成，
  并入 3.4.0；出口为 §2.16 验收标准全场景浏览器实测留痕 + 闸门全绿。
- 每批入口 = 上一批验收全绿 + `validate_progress.py` 通过；每批出口 =
  §5 闸门全绿 + CHANGELOG/progress 当批登记（禁止集中回补）。
- 真实 G16 冒烟节点：B1 后一次（Checkpoint/AllCheck 各一例）、B2 后一次
  （`Gen`/`Pseudo=Cards` 附加节）、B4 后一次（多组电荷对/`%cpu=0-5/2`/
  自由格式分隔符各一例）、B6 后一次（G10-b 误报形态复测）、B7 后一次
  （电荷行行内注释一例）；版本固定
  G16 Rev. C.01，语料清单与哈希随批次记录。
- **版本归属**：本计划按 **3.4.0（minor：新增 warnings 通道与检测项）**
  目标版本推进（3.3.0 已于 2026-10-15 冻结发布）。若仅交付 C1–C3
  （不含 G0/warnings）才按 patch；B1 含 G0，按 minor。B6、B7（均 2026-10-20
  立项）并入 3.4.0，发布冻结时点顺延至 B6、B7 验收全绿后。

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
- **`ignore_spelling` 屏蔽期口径**：B6 G10-a 起 enforce 屏蔽，该请求
  字段保留不删、description 注明不生效；模板保存响应
  `notice.spelling_warnings` 仍随 warn 放行携带词典外 token 清单。
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
- **警告噪声基线**：以 `~/g16/tests/com` 官方测试语料为**回归对照样本**
  （决策点 11：非权威参考），记录改动前后逐文件 warnings 数量；基线
  harness 口径固定为「不拒文件」——语料逐文件解码后 `parse_input`，对
  route 全集运行 `file_warnings`，统计各 kind 条数与命中文件数（含将被
  导入拒绝的文件；与导入/提交「先拒后警告」的闸门口径不同，两者不得
  混用）；批次
  入口冻结阈值（新增警告涉及文件 ≤5%，同一文件同一 kind ≤3 条）仅作
  **复审触发器**——超阈逐条归因，归因以手册 SSOT（gaussian-kb）与
  支持版本口径（G16/G09；G03 不支持）为准，语料命中本身不构成错误
  判据（AGENTS §6.1 可量化指标要求）。
- **官方语料回归（非权威）**：`~/g16/tests/com` 官方自带测试语料陈旧、
  含大量 G03 时代旧形态，其命中不作为错误判据（决策点 11），仅作回归
  对照与归因输入。回归样本集：现有语料 + 新增
  （Checkpoint 缺电荷行/缺 title、`Geom=Check`、括号 Geom、`#T`/`#N` 模板、
  `opt,freq` 逗号分隔、行内 `!` 注释、`opt = (calcfc, ts)`、
  `opt (calcfc, ts)`、`IOp(6/50=1)`、`External="RunTink Amber"`、`O-Bq`、
`X` 哑原子、`C-CT--0.06`、`C,0,0,0`、`C/0/0/0`、多组电荷对、负多重度组、
电荷行行内 `!` 注释（单组/多组对）、空分子说明、BOM、
`%cpu=0-5/2`、`%mem=0`、`%save`/`%kjob l502 2`）。语料版本与
  文件清单/哈希随批次记录，避免「本机可复现、他机不可复现」；语料缺失时
  记录 skip，不得默认通过。
- **端到端**：B1/B2/B4/B7 后各以真实 G16（Rev. C.01）冒烟一次
  （`Geom=(Checkpoint,ModRedundant)`、`Gen`/`Pseudo=Cards` 附加节、
  多组电荷对/`%cpu=0-5/2`/自由格式分隔符、电荷行行内注释各一例），确认
  零误报/零漏报后再进下一批；`%mem=2W`、`%mem=0`、`Zz` 原子行等为离线
  校验用例，不作为 G16 冒烟输入。
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
9. **`prop=wrf` 兼容触发词**：以 `COMPAT_EXTRA_KEYWORDS` 保留一版避免
   既有行为回退；B6 出口冒烟 G16 Rev. C.01 实测拒绝，裁决删除，
   冒烟节点在 B6 出口（§3.1）。
10. **发布窗口与批次工期**：3.4.0 为目标版本；不设日历承诺，排程由批次
    闸门驱动（每批入口 = 上一批验收全绿 + `validate_progress.py` 通过），
    发布冻结时点在批次验收全绿后的发布流程中确定（B6 立项后顺延至 B6
    验收全绿后，见 §3.1）。
11. **支持版本口径与语料判据（2026-10-20）**：G16 为最大支持对象，G09
    次之，G03 及更早版本确认不支持；官方自带测试语料
    （`~/g16/tests/com`）陈旧，降级为回归对照样本，不作为权威参考与
    错误判据——错误判据一律以手册 SSOT（gaussian-kb）与 G16 实测为准；
    G03 旧形态（`geom=modela` 等）命中 `route_option_unknown` 为预期
    行为，不作为误报归因。
12. **enforce 口径暂时屏蔽（2026-10-20）**：enforce 与 warning 的分工
    作用未明，且 enforce 存在组合词值侧把关空洞（键名在典即放行）——
    暂时屏蔽全部 enforce 口径，仅启用 warning（G10-a/B6）；分工重新
    裁决后另批恢复，恢复时须先解决值侧把关与缩写口径一致性。
13. **B 类词典扩面正式立项（2026-10-20）**：面⑤散文提及选项三路互补
    近似全量审计 + 缺口清单补提取，B6 批次交付（§2.13 G10-b）。

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
| enforce/warn 分工未明，组合词值侧把关空洞（键名在典即放行，同类错误裸词被拒、组合词仅警告） | 决策点 12：暂时屏蔽全部 enforce 口径，仅 warning（G10-a/B6）；恢复另批裁决 |
| 面⑤散文提及选项缺口未全量审计，官方合法选项误报 unknown（已确认 `opt=addredundant`/`freq=nnroa` 两形态） | 决策点 13：B6 三路互补差集近似全量审计 + 补提取（G10-b）；warn 级不阻断 |
| 官方测试语料陈旧（G03 旧形态），误作错误判据导致口径失真 | 决策点 11：语料降级为回归对照样本；错误判据以手册 SSOT + G16 实测为准 |
| G03 旧形态大范围警告造成警告疲劳 | G03 不支持口径下为预期行为；B6 评估警告 message 是否附「受支持版本」提示，评估结论（采纳与否及归因）随批留痕登记 |
| 电荷行注释剥离回归（多组对误判、剥后 token 不足漏报） | 与 C3 管道同规仅剥引号外注释；单组/多组对/剥后不足仍报错用例先行（测试先行批次）；B7 出口 G16 实测背书 |

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
  对照（目录 1161 条目，.com 语料 1156 文件）：新增警告 0 文件（阈值 ≤58）；
  「附加节未以空行终止」
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
  进度同步，共 7 提交（bbbdc390 开工、0ec1e484 契约、af0cf810 测试、
  57b34225 实现、5473f537 进度、本条留痕、374247a2 断言修正补登）。
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
     **44.03% 文件误报**（509/1156，B5 审查独立复核口径：判定链同最终
     实现、仅去掉唯一前缀判活分支，实施期初版统计 45.7% 复刻细节不可考
     已废弃；density=curr、freq=numer、guess=lowsym 等官方
     合法缩写被报为非官方选项）。修正为：在该键官方选项集（词典 `键=*`
     组合词）内唯一前缀判活（`scf=conven` 官方正面例合法、`scf=conv`
     键内歧义前缀仍报——G16 Rev. C.01 实测接受（B6 冒烟 t5），警告系
     键内歧义判活的保守残余）；词级拼写通道（决策点 5）不变。
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
    43、`scf=noincore` 20、`units=bohr` 14（units 页官方选项为
    Ang/AU/Deg/Rad，`bohr` 非官方选项名，仅系 AU 的散文释义）、
    `cphf=ultrafine` 14、`td=(window(13,-12)…)`/`cis=(window=(13,-12)…)`
    共 7 条（G03 时代 TD/CIS 选项，G16 手册 TD/CIS 页均无 Window）等；
    手册 SSOT 无据，报「官方选项集中无此项」与 G8 立题（对照官方手册）
    一致，属词典口径固有边界而非误报；warn 级不改变任何阻断语义。
  - **B 类（少量）：面⑤覆盖缺口**——手册明文存在但面⑤按 Options 章节
    `####` 规则未提取的散文提及选项：`opt=addredundant` 6 条（opt 页
    明文「AddRedundant is synonymous with ModRedundant」）、`freq=nnroa`
    4 条（freq 页 ROA 条目明文保留 G03 数值 ROA）等，
    另批词典扩面解决（§2.12 缩写限制同款处置）。
  - 单文件同 kind ≤3 维度：6 文件超（最大 5 条 test0386），沿用 R6
    裁决（行级粒度保留精确定位，不聚合）。
- **出口闸门**：`uv run pytest` 835 passed 0 skipped、
  `validate_progress.py`、`gen_changelog_md.py --check`、
  `gen_models.py`/`npm run gen:types` 再生零 diff（契约批次）全部通过。
  **B1–B5 五批全部收口**，按 §3.1 版本归属进入 3.4.0 发布流程（冻结
  时点由用户在 B5 验收后确定）。

### 8.7 B5 批次审查与整改（2026-10-20）

- 独立审查：code-reviewer 子代理按 AGENTS §6.2 四查执行，报告落盘
  docs/plans/input-verify-gap-b5-review.md，结论**通过、无 P0/P1**（8 项
  登记性发现 R1–R8）——835 passed 0 skipped 独立复现；语料基线 13 项
  指标 12 项逐位吻合（45.7% 一项不可复现，见 R2）；端到端三通道
  （导入/分块保存/模板 enforce）隔离实测通过、line 全文件绝对语义正确；
  契约再生零 diff、先行红属实、G8 十条用例无恒真断言。验收 V1–V7 全过
  （V5 为 §8.6 口径修正 2 已登记的有据偏离，裁决与实现、测试三方一致）。
- 随批整改（单提交单类变更：fix → docs → progress）：
  - **R1（P2 可维护性）**：check_route_options `return out` 之后 14 行
    不可达死代码（旧 token 判定逻辑编辑残留）删除。
  - **R3（P2 覆盖缺口样例）**：语料 window 形态列为覆盖缺口待复核样例
    （§2.13 判归 A 类）；`_PAREN_TAIL` 注释去除「已覆盖」误导。
  - **R6（P3 注释口径）**：`_VALUE_FORM_HEADS` 注释据实修正——iop 成员
    实际靠键名不在典兜底（IOp(6/50=1) 按 = 拆键得 `iop(6/50` 含括号），
    oniom/external 真正生效，iop 保留为防御。
  - **R2（P2 留痕取数口径）**：§8.6 口径修正 1 的原口径误报修正为审查
    可复现口径 **44.03%（509/1156）** 并注明判定链（实施期 45.7% 复刻
    细节不可考，废弃）。
  - **R4（P3 文档一致性）**：§8.6 提交列表补 374247a2（6→7 提交）。
- 备案不整改（审查报告 §四已登记）：
  - **R5**：§2.9「G4 触发词选项集匹配复用同一拆解辅助」未落实——G4
    触发词为头部精确等值/选项集精确包含，与 G8 括号拆解语义不同源，
    危害为零，留待下轮计划修订改写该句。
  - **R7**：畸形 `opt==calcfc`（双等号）由改动前可能得近邻建议变为零
    警告——极边缘畸形输入，warn 级宁漏勿误口径内。
  - **R8**：模板通道 keyword 为 casefold 原文，与既有
    route_duplicates/spelling_warnings 同源惯例一致，契约未约束大小写，
    如需统一留待既有惯例一并处理。
- 整改后回归：全量 pytest **835 passed 0 skipped**（与整改前一致，
  R1 删除确认无行为影响，fix 提交仅涉 keywords.py 死代码与注释）。

### 8.8 计划再修（2026-10-20）

- B5 复盘（§8.7 审查报告 + 用户裁决）确认**实现缺口与文档错误并存**，
  且 §8.6/§8.7 的后置留痕不足以对冲正文错误——本轮原位勘误，计划进入
  再修订状态（头部状态行同步）：
  - §1.1 官方原文摘录补 "and options"（keywords 与 options 均可缩写）；
  - §2.8 断言「两处→三处」、方案 2 缩写口径改写（组合词缩写键名命中
    放行 + enforce 屏蔽括注）；
  - §2.9 缩写选项改唯一前缀判活（原「按未命中记 unknown」系错误推导）、
    G4「复用拆解辅助」句原位改写为不复用；
  - §3 批次表 B5 验收行改写为实施口径（三处断言、组合词放行/裸词拒绝）；
  - §2.12 补 `opt==calcfc` 静默已知限制；§5 语料判据降级（「金标准」→
    回归对照样本，阈值仅作复审触发器）；§7 风险登记补 4 行。
- **漏洞承接与 B6 立项**：新增 §2.13 G10 与 §3 B6 批次——G10-a enforce
  口径暂时屏蔽（决策点 12，仅启用 warning）、G10-b B 类词典扩面与面⑤
  三路互补近似全量审计（决策点 13）、支持版本口径 G16 主/G09 次/G03 不支持与官方
  语料非权威（决策点 11）。错误判据自此一律以手册 SSOT 与 G16 实测为准。
- 版本归属：B6 并入 3.4.0，发布冻结时点顺延至 B6 验收全绿后（§3.1）。
- B6 实施序列：G10-a enforce 屏蔽独立提交（f6129cef）、G10-b 词典扩面
  与审计、契约 description 同步、进度同步同批完成；G10-a 实际为批次
  最后一个提交（晚于收口登记），序列勘误以
  `docs/plans/input-verify-gap-b6-prose-audit.md` §9.2 R3 为准。

### 8.9 B7 批次（2026-10-21 实施收口）

- 实施序列：先行红测试先行落盘（2ed38a76，B6 审查整改期间随批——先行红
  2 例 + 剥离后仍报错回归守卫 1 例，留痕 input-verify-gap-b6-prose-audit.md
  §9.2 R6）→ progress 开工登记（444ba1ec）→ 实现（29c71d88，单文件单点）
  → 进度同步（a4f68b71）→ 本留痕。无契约变更（无 schema 与 kind 词表
  变更），无文档先行提交；B6 收口即本批入口（与 B6 无文件交集）。
- 实现：`parse_charge_tokens` 归一化前剥离引号外首个 `!` 及其后内容——
  截断扫描引号感知（引号内 `!` 不截断、留作分隔符不入 token，与 C3
  管道同规）；电荷行为整数对自由格式、无括号取值语义，不引入括号跟踪
  （取舍对齐 B1 审查 R3 登记先例，docstring 注明）。`parse_input` 与
  `_validate_section`/`_expected_blocks` 经同一单点自动拉齐。
- 验收：全量 **847 passed 0 skipped**（入口基线 2 failed / 845 passed，
  失败即先行红两例设计使然；实现后转绿，回归守卫例实现前后均绿）。
  四通道实测（临时脚本，工作区隔离）：单组对 `0 1 ! neutral singlet` 与
  多组对 `0,1 0,1 0,1 ! cp pairs` 预览 parse_errors=[]、导入 error=None、
  提交 normalized=True 且落盘文本往返再解析零错误、编辑保存
  save_block(charge_mult 含注释原文) errors=[] 放行；`charge_mult` 字段
  规范化输出 `0 1` / `0 1 0 1 0 1` 不含注释文本。落盘电荷行保留注释
  原文属 `verify_and_normalize` 既有设计（注释行原位保留，G16 自行忽略）。
- 语料基线对照（`~/g16/tests/com` 1156 文件，新旧实现逐文件对比）：
  `charge_mult` 解析失败命中 6 文件完全同一（test0892/0894/0896/0897/
  1100/1102），差集 0；全语料 warnings 总条数 25→25 零变化。语料中无
  电荷行行内注释样本，接受集扩大在语料上零扰动（既有拒绝集与警告发射集
  均不变）。
- **G16 Rev. C.01 冒烟**（临时目录运行，sha256 前缀随批）：

  | 语料 | 输入电荷行 | G16 实测 | 结论 |
  |---|---|---|---|
  | t_comment（5b236daa） | `0 1 ! neutral singlet` | `Charge = 0 Multiplicity = 1` 正常读取，Normal termination | ✓ 与手册一致 |
  | t_cp（9e7f140a，counterpoise=2） | `0,1 0,1 0,1 ! cp pairs` | 三组电荷/多重度全部正常读取，Normal termination | ✓ 与手册一致 |

  实测与手册一致（G16 忽略行内注释），无 §2.12 分歧登记需求。
- 顺带观察（随批登记，不改裁决）：该机 G16 Rev. C.01 实测拒绝整数坐标行
  （`O 0 0 0` 报「Wanted a floating point number」，浮点坐标通过）——非
  G11 形态；坐标数值合法性属 §2.12 已登记不校验面，不影响本批裁决。
- 出口闸门：`uv run pytest` 847 passed 0 skipped、`validate_progress.py`、
  `gen_changelog_md.py --check` 全部通过；`check_plan_status.py` 随本节
  状态行回填转绿。**B1–B7 全部收口**，按 §3.1 版本归属进入 3.4.0 发布
  流程（冻结时点由用户确定）。

### 8.10 B7 批次审查与整改（2026-10-21）

- **独立审查**：报告落盘
  [input-verify-gap-remediation-plan-B7-review.md](input-verify-gap-remediation-plan-B7-review.md)
  （AGENTS §6.2 四查 + 隔离实例端到端 + G16 Rev. C.01 直跑复现），范围
  `7b5c06aa..890bb553`（5 提交）。结论：**有条件通过**——B7 核心交付全部
  独立复现成立（847 passed、语料基线逐位吻合、先行红 worktree 实证、
  G16 直跑两例 Normal termination），1 项 P1（R11 测试有效性）+ 2 项 P3。
- **整改处置**（三提交单类变更，全数修复）：
  - **P1-1（P1 测试有效性）已修**：`test_block_save.py` 补
    `test_charge_mult_inline_comment_allowed`——编辑保存通道
    `save_block(charge_mult)` 行内注释单组/多组对放行 + 规范化输出无
    注释断言 + 剥离后 token 不足仍 422 回归断言，编辑保存通道（G11 原
    422 误拒主战场）G11 行为自此有持久化回归保护。
    **偏离原因补记**：§2.14 用例清单中「编辑保存通道放行」在先行红批次
    （2ed38a76）漏列 `test_block_save.py` 文件面（仅落
    `test_parse_blocks.py` 3 例），实施期以不入库临时脚本背书该通道、
    §8.9 留痕未登记该覆盖缺口——教训：§2.14 类「测试文件 + 用例方向」
    清单在先行红提交前应逐一核对文件面齐全性（R8 教训同款，后续批次执行）。
  - **P3-1（P3 约定违例）已修**：`progress.json` `updated` 由无偏移
    `2026-10-21T00:33` 回填为带 `+0800` 偏移的 ISO 8601，与历史惯例拉齐；
    根因为进度同步脚本 `datetime.now()`（naive）的 `strftime %z` 输出
    空串，改用 `astimezone()`。
  - **P3-2（P3 可维护性）已修**：`parse_charge_tokens` docstring
    「与 C3 管道同规」限定为「注释**截断规则**同规」，注明引号内 `!`
    后续处置两通道差异（C3 引号内空白不切分、`!` 保留为 token 整体；
    本单点引号内 `!` 替换为空格作分隔符不入 token）及缘由。
- **整改出口**：全量 `uv run pytest` **848 passed 0 skipped**（847 +
  P1-1 新增 1）；`validate_progress.py`、`gen_changelog_md.py --check`、
  `check_plan_status.py` 复跑全绿。审查报告通过条件 1/2 全部满足。

### 8.11 计划再修收口（2026-10-21）

- 全面终审第 1 轮（报告
  docs/plans/input-verify-gap-remediation-plan-final-review-r1.md）实现层
  通过，另登记 4 处「留痕已勘误、主文档正文未回改」型文档问题
  （D-1…D-4）与 2 条 P3 观察项（I-1/I-2）。本轮原位勘误收口，正文口径
  与留痕/实测对齐：
  - D-1：§2.9 缩写选项与 §3.1 B6 节点改按 B6 冒烟实测口径——`scf=conv`
    歧义前缀 G16 实测接受（t5），警告系键内歧义判活的保守残余；
    `freq=readanh` 同口径警告与 G16 拒绝一致（t6）；§2.12 补登记该保守
    残余已知限制；
  - D-2：§2.6 G3 检测面限定补全——route 缺失时 `%` 行按情形 2 记
    parse_errors 限于 title 节内（含标题行后错置），文件开头前导 `%` 行
    归 Link 0 收集、不在检测面（§8.3 口径）；
  - D-3：§2.0 G10 行、§2.13 方案 2、决策点 13、§7 风险表与 §8.8 的
    「三路差集全量审计」统一收敛为「三路互补差集近似全量审计」，路②
    覆盖边界（keyword 页 Options 章节条目正文）随文注明（prose-audit
    §1 审查 R8 口径）；
  - D-4：§2.13 方案 1、§3.1 B6 节点与 §8.8 末段去除「先行独立提交」
    序列断言，按 prose-audit §9.2 R3 勘误口径记 G10-a 独立提交收尾；
  - I-1：title 禁字警告行级粒度（每行仅报首个禁字）登记 §2.12 已知限制
    （B2–B4 审查 R6 行级粒度裁决的延伸登记，不改实现）；
  - I-2：prose-audit §7 补「同文件同 kind ≤3」逐文件维度——按 §5
    harness 口径复算（命中 394 文件/469 条与该表逐位一致）：超阈 6 文件，
    最大 test0386 5 条（其余 test0385/0431/0442/0985/1187 各 4 条），
    沿用 R6 行级粒度裁决接受超阈。
- 状态行回填「已实施并验收」（验收留痕 final-review-r1.md，目标版本
  3.4.0）；出口闸门 validate_progress / gen_changelog_md --check /
  check_plan_status 复跑全绿。

### 8.12 B8 批次与全面复审整改（2026-10-21 实施收口）

- **全面复审**：code-reviewer 子代理按 AGENTS §6.2 四查分两批执行——
  B1–B4（报告
  [input-verify-gap-remediation-plan-B14-review.md](input-verify-gap-remediation-plan-B14-review.md)，
  区间 v3.3.0..f5387615，38 提交）与 B5–B7（报告
  [input-verify-gap-remediation-plan-B57-review.md](input-verify-gap-remediation-plan-B57-review.md)，
  区间 f5387615..04db8a4b，48 提交）。结论：**两批均通过，无 P0/P1**——
  851 基线内 848 passed 0 skipped、七闸门全绿、生成物零 diff、G16 冒烟
  与审计漏斗逐字节独立复现；问题清单合计 1 P2 + 6 P3。
- **立项与勘误**：P2 R1（CandidatesView 渲染缺口）按 §2.15 立项 G12/B8；
  F-1 键名笔误随批原位勘误（§2.9 与 §8.6 口径修正 1 的
  `scrf=conven`→`scf=conven`，词典/scrf 页/探针三重证据）。
- **实施序列**（文档→测试→实现→进度同步，6 提交）：
  - 测试先行：R3 空值警告先行红用例（实测 1 failed）+ R2 矩阵
    「不适用」格防回归断言（分块保存列 G9/G4/C1/C2、模板列触发词
    route 放行代表断言）；
  - R3：`check_link0_lines` 对 %nproc 系空值（含截断形 %nprocshare）
    与 `%cpu=` 空值记 `link0_value_invalid`（%cpu 系 R3 同根因
    `if val` 短路的顺带拉齐，属审查未登记面，随批登记）；
  - R4：`_validate_one` 死键 `bom_stripped` 删除（无消费方）；
  - R5：`pred_read_window` docstring 落空引用（§2.12 无 RW 条目）改
    自足表述；F-2：extract_keywords/audit_prose_options 三处
    「三路差集全量审计」措辞对齐 D-3 收敛口径；
  - R1（G12）：CandidatesView 导入琥珀清单（按文件聚合）+ 单任务提交
    琥珀警告区 + QueueEditorModal 队列提交 task_id 警告（弹窗重开即
    清空）；HistoryView/ResumeDialog 渲染登记为后续按需项、
    「再次保存即清空」登记为必做实现动作（均见 §2.15）。
- **浏览器实测（playwright，AGENTS §6.2）**：隔离实例
  （`G16WEB_HOME=/tmp/g16web-b8`、`G16WEB_ENGINE=0`、:8399，构建版本
  v3.3.0-94-gea7ea5c2）六场景全过——
  ①导入 `optt` 拼写文件：琥珀清单「导入警告 1 条 — 非阻断，已入库」
  按文件聚合（spell.gjf 第 5 行 keyword_spell；clean.gjf 零警告不入列）；
  ②单任务提交：工具条下方琥珀「⚠ 提交警告 — 第 4 行 …」（提交通道
  规范化后行号，全文件绝对口径）；
  ③队列直接提交：done 注记下方「⚠ 任务 #3 — 第 3 行 …」，task_id 归属
  正确；
  ④B6 视觉补测——组合流模板弹窗无「忽略拼写警告并保存」豁免按钮
  （foot 仅「关闭/保存」，G10-a 移除口径在当前构建成立）；
  ⑤词典外 token route 保存 200 放行 + 琥珀「词典外关键词（已放行）：
  zzzzzq」（freq 联动补温度照常）；
  ⑥`%mem=0` 保存 422 + %mem 输入框 `.ct-invalid` 红描边（computed
  borderColor 为 --danger）+ 顶部错误清单「%mem 须为正数（GB 数值）」。
  截图六张存 `.playwright-mcp/`（本地留证，不入库）；实测工作区/种子
  用毕清理。
- **出口闸门**：全量 `uv run pytest` **851 passed 0 skipped**（848 + B8
  新增 3）；前端构建 vue-tsc 通过、audit_frontend_offline /
  check_tokens / check_contrast 全绿；validate_progress /
  gen_changelog_md --check / check_plan_status（状态行回填后）通过。
  **B1–B8 全部收口**，按 §3.1 版本归属进入 3.4.0 发布流程（冻结时点由
  用户确定）。
- **B8 批次独立审查与 P3 处置（2026-10-21）**：code-reviewer 子代理按
  AGENTS §6.2 四查独立复核 04db8a4b..6b992ff9（报告
  [input-verify-gap-remediation-plan-B8-review.md](input-verify-gap-remediation-plan-B8-review.md)），
  主会话以 playwright 补齐六场景视觉复测（报告 §7，六场景全过），结论
  **通过**；登记 3 条 P3 文档层偏差，同日整改闭环（为本文件与 B14 报告
  的未提交修正，随下轮文档提交入库）——
  ①P3-1：§2.15 条目文案原位勘误为实际交付口径（导入「文件名 ⚠ 第 N 行
  message」、提交「⚠ 提交警告 — 第 N 行 message」、队列
  「⚠ 任务 #task_id — 第 N 行 message」）；本节浏览器实测场景②③留痕
  分隔符随勘误改为交付后「—」形（B8 时点实测为「·」，原始观察见审查
  报告 P3-1 与 git 历史）；
  ②P3-2：本节与 B14 报告三处「31 提交」改「38 提交」
  （`git rev-list --count v3.3.0..f5387615` 实测 38）；
  ③P3-3：§2.15 补「再次保存即清空」B9 承接登记，本节实施序列 R1
  bullet「均见 §2.15」回指随之成立。

### 8.13 B9 批次（2026-10-21 实施收口）

- 实施序列：progress 开工登记（4bb5d842）→ 契约先行（a228e738，Candidate 增
  必填现算字段 warning_count，openapi 先行 + gen_models/gen:types 再生零 diff）
  → 测试先行（161ed8ab，先行红 4 failed / 867 passed）→ 后端实现（703ccd4f
  三处 Candidate 视图现算 + e0dd03d5 message 标点收口，全量 871 passed 0
  failed 转绿）→ 前端实现（含实测期两处随批修正）→ 本留痕与进度同步。
- 测试先行落点：新增 test_warning_messages.py（14 样例覆盖 Warning.kind 12
  kind 全集：message 含 CJK、命中模板短语、无 kind 字样——逐 kind 中文警告语
  模板清单随批固化，词表扩容由覆盖断言强制同步）；test_parse_blocks.py 增
  缺省补全前后 file_warnings 等价三例（双注入行号平移 +2 / 齐全全等 / 值域外
  声明边界例）；test_candidates_import.py 增 warning_count 现算链路（导入
  N≥1、分块修复归 0、不可读回落 0、删除随行消失）；test_contract_rest.py 增
  Candidate 契约用例。先行红实际 4 例（预估 3 例）：POST
  /history/{id}/return-candidate 的 201 响应同为 Candidate 形态被 schema 必填
  转红波及（test_return_candidate_from_failed，预估漏列），随实现提交一并转绿。
- **等价性边界实测（§2.12 同批补录）**：「缺省补全前后 file_warnings 内容集
  等价」在值域外声明（%mem=2W 类）上不成立——resolve_link0 对不可解析声明按
  缺失处置、块末注入缺省行，补全后新增恰一条 link0_directive_duplicate（后值
  覆盖前值，G16 实际以缺省值执行），系补全伪影而非用户输入问题；预显维持存储
  文本核验口径不显示该伪影，用户可见问题由 link0_value_invalid 本身承载。测试
  按实测钉死边界（差异恰为一条 duplicate + 平移口径不变），B9-review R1 的
  担忧在「值域外声明」类上实证落地。
- 后端：services/candidates.warning_count 单点（file_warnings 全集现算、输入
  副本不可读回落 0）；列表端点对分页切片后的当前页条目逐条现算（不进切片前
  全量构建，成本不随全量候选数增长）；单条 GET 与 history 退回候选同口径；
  link0_directive_duplicate message 尾括号半角改全角（逐 kind 审计唯一不符点）、
  route_duplicate message 补「会跑成 MP4」空格（实测发现随批修正）。
- 前端：BlockEditor 逐块 warnings 详情（kind→块归属映射，词表 12 kind 全覆盖，
  词表扩容须同步映射表）+ saved 事件（保存即复验，宿主刷新徽标与详情）；
  CandidatesView 提交确认框预显区（裁决⑤，消费 openSubmit 已取 preview
  warnings）、导入清单自含条目「⚠文件名: L行号 message」与汇总行「导入警告
  N 条」、提交回执「⚠ L行号 message」、徽标占位列（文件名与标题之间，无表头
  系对「列均有列名」规范的计划授权偏离，列宽有界显隐无列移（I-1 勘误），
  N=0 空置）；
  QueueEditorModal 成员行下任务级预显（复用 loadLinkStates 并行取数路径扩展
  消费 warnings，不新增请求路径；创建态与编辑态均取数，只读/完成态不取数）
  + 直接提交回执「⚠ 任务 #task_id: L行号 message」+ 保存成功路径清空
  submitWarnings（§2.15「再次保存即清空」必做动作承接，重开清空原有 watch(open)
  延续）+ done 后成员预显清空（提交回执承载最新核验，防规范化改写后滞后保留，
  裁决⑥）；全部警告展示区限高滚动（新令牌 --warn-list-max-height: 200px，
  tokens.css 与 m0-ui-preview.html 同步，check_tokens 93/93 + 31/31 一致）。
- **浏览器实测（playwright，AGENTS §6.2；隔离实例 G16WEB_HOME=/tmp/g16web-b9、
  G16WEB_ENGINE=0、:8399，构建版本 v3.3.0-104）九场景全过**：
  ①导入四文件：琥珀清单汇总行「导入警告 14 条」、自含条目「⚠multi.gjf: L1 …」
  逐条渲染，限高滚动（scrollHeight 416 / clientHeight 198，滚动可达末条无
  吞没）；②徽标列：multi ⚠13、spell ⚠1、clean/broken 空置占位，aria 语义
  到位，列宽有界显隐无列移（I-1 勘误）；③单任务确认框预显（裁决⑤）：spell 打开即见
  「⚠ L1 「optt」疑似拼写错误…」（动作发生前），clean 零警告零渲染；④队列
  创建态与编辑态弹窗：multi 13 条 / spell 1 条各归其位（任务级归属），broken
  预览 404 仅该成员占位「成员输入预览不可用 — 无法核验」、其余成员不阻断
  （console 仅预期 404）；⑤直接提交回执：「⚠ 任务 #4/#7: L行号 …」task_id
  归属正确，回执区限高滚动（515/200），done 后成员区无占位；⑥复验链（裁决⑥）：
  分块修复 route（optt→opt）保存后详情警告即时消退、列表徽标即时消失、再次
  打开提交框预显零渲染；提交规范化补空行使 multi 的 EOF 类警告 13→12 自然
  消退（§2.16④ 复验机制活例）；⑦删除带徽标候选随行消失；⑧重复导入同文件
  各自带警告互不影响、输入副本不可读徽标回落空置；⑨队列弹窗重开回执清空、
  submitted（memberOnly）成员占位符合端点守卫语义（preview 对 submitted 成员
  本就 404）、保存链路无回归。截图存 .playwright-mcp/（本地留证，不入库）；
  实测工作区/种子用毕清理。
  - 实测期发现并随批修正两处：done 态成员区误显「预览不可用」占位（占位
    条件补 !done，重建后复测通过）；route_duplicate message 缺空格（后端
    message，重启后生效、pytest 模板断言同步复绿）。
- 出口闸门：全量 uv run pytest **871 passed 0 skipped**（入口基线 851 + B9
  新增 20）；前端构建 vue-tsc 通过、audit_frontend_offline / check_tokens /
  check_contrast 全绿；validate_progress / gen_changelog_md --check /
  check_plan_status（状态行回填后）通过。**B1–B9 全部收口**，并入 3.4.0
  （发布冻结时点由用户确定）。

### 8.14 B9 批次后裁决：Link0 缺省补全收窄（2026-10-21，用户裁决）

- 裁决背景：§8.13 登记的等价性边界（值域外声明类补全伪影）经用户复核，
  裁决收窄补全口径——**仅在 %mem/%nproc 系指令行缺失时注入缺省行；指令
  存在但值非法（值域外/空值/非数值）时不再注入**。非法输入不遮蔽（原实现
  按缺失处置注入缺省、后值覆盖前值静默执行，掩盖用户错误），由既有核验
  警告 link0_value_invalid 承载提示，运行结果交 G16 裁决（§2.12「坐标数值
  等同类交 G16 运行期报错」同口径）。
- 实现（`workspace.resolve_link0` 单点，docstring 同步改写）：缺失判定从
  「值可解析与否」改为「按行存在性」——%nproc 系与 %cpu 任一行存在即视为
  已声明核资源、不注入 %nprocshared；%mem 行存在即不注入 %mem。
  `defaulted` 语义改为「是否注入了缺省行」；值非法未注入时记账值回落
  缺省（消费方 dispatcher 直接 `int(value)`，须数值安全）。行为变更随
  CHANGELOG migration 登记：此前 %mem=2W 类文件提交后按缺省值静默执行，
  现以原行进入 G16（运行期大概率报错）——需修正取值或删除非法行。
- 测试：test_dispatch_engine.py 增 test_link0_invalid_value_not_injected
  （%mem=2W/abc/空值、%nprocshared=zz、%cpu=x-y 五态无注入 + 记账回落
  断言）并改写 test_link0_cpu_list_semantics 末段（%CPU=x 行存在即不
  注入）；test_parse_blocks.py 等价边界例改写回等价断言（duplicate 伪影
  随收窄消除：内容多重集一致 + 行号平移口径 + 无 duplicate）。
- §2.12「缺省补全等价性在值域外声明上的边界」条目改写为已消除；§2.16 的
  fallback 条款对未来补全规则变化继续有效。
- 出口：全量 uv run pytest **872 passed 0 skipped**（871 + 收窄断言 1）；
  闸门 validate_progress / gen_changelog_md --check 通过。

### 8.15 B9 实现审查与整改（2026-10-21）

- **实现审查**：code-reviewer 子代理按 AGENTS §6.2 四查独立复核 B9 批次
  （区间 78bef9fa..334ea301，13 提交；报告
  [input-verify-gap-remediation-plan-B9-impl-review.md](input-verify-gap-remediation-plan-B9-impl-review.md)）。
  结论：**通过，无 P0/P1/P2**——872 passed 0 skipped 与 §8.14 逐位复现、
  先行红 4 failed/基线 851 归一复现、七闸门全绿、生成物再生零 diff、
  warning_count 三路径 API 冒烟与 playwright 九场景浏览器实测通过；
  4 项 P3（I-1..I-4）。
- **整改（I-1 遵用户裁决：组件禁硬编码度量，一律令牌库注册并引用）**：
  - I-1：候选列表徽标占位列宽硬编码消除——新令牌 `--warn-col-width: 56px`
    （tokens.css 页面度量段与 m0-ui-preview.html 样板同步登记，
    check_tokens 逐变量闸门覆盖），`.warn-col` 改引令牌；纯令牌化不改
    布局行为，auto 布局下限与整表末徽标消失再分布维持审查实测口径，
    §2.16 与 §8.13「列宽固定」措辞随本节勘误为「列宽有界（下限）」。
  - I-2：头部状态行留痕区间「§8.1–§8.13」→「§8.1–§8.15」（补 §8.14
    Link0 收窄与本节）。
  - I-3：openapi `warning_count` description `>-` 折叠标量改单行双引号
    长句，消除 YAML 折行词间空格伪影（「响应中 现算」「现算
    （file_warnings」），gen_models + gen:types 再生入库。
  - I-4：submitted 态逐成员「无法核验」占位维持备案观察不改（§8.13 ⑨
    预期行为；memberOnly 汇总句式留待后续需要时立项）。
- 出口：全量 uv run pytest **872 passed 0 skipped**（令牌化与 description
  源修正零行为变更）；闸门 check_tokens（94+31 逐变量含新令牌）/
  check_contrast / audit_frontend_offline（重建 dist 后零外链）/
  validate_progress / gen_changelog_md --check / check_plan_status 全绿。

### 8.16 B9 审查 I-1 续整改：徽标占位列钉宽（2026-10-21，用户裁决）

- **裁决**：N 至多两位数，数字变化不得影响该列宽度，不得因列宽变化
  引起右列抖动偏移——§8.15 的纯令牌化未改变 auto 表格布局「内容参与
  列宽」行为（实现审查实测：徽标在场 60–67px、末徽标消失 −4~−11px
  再分布），本节钉死。
- **实现**（`.warn-col`，CandidatesView.vue）：
  - 钉宽三件套：`max-width` 与 `width`/`min-width` 同取令牌值 +
    `overflow: hidden`——auto 表格布局下 td/th 的 max-width 仅在
    overflow 非 visible 时生效，列宽自此与内容解耦（数字变化、徽标
    显隐均不参与列宽计算）；
  - `--warn-col-width` 56→64px，`.warn-col` 水平内边距 `--space-3`
    收窄至 `--space-2`：两位数最坏徽标「⚠ 99」隔离实测 42.02px +
    内边距 16px = 58.02 ≤ 64（原 56px 预算下连一位数 33.02+24=57.02
    都容不下，钉宽即裁切）；~6px 余量覆盖 Windows 回退字体 ⚠ 字形
    差异；样板 m0-ui-preview.html 同步。
- **浏览器实测**（playwright，隔离实例 :8399）：
  - 钉宽：徽标 ⚠1/⚠2 在场与注入「⚠ 99」列宽均恰 64.00px，⚠99 零裁切；
  - 末徽标消失：真实数据路径（分块修复 route 拼写警告 ⚠1→0，经列表
    刷新徽标移除）前后全 8 列 x/width 零差；DOM 级移除同验全列零位移。
- **出口**：全量 uv run pytest **872 passed 0 skipped**；闸门
  check_tokens（94+31 逐变量）/ check_contrast / audit_frontend_offline
  （重建 dist）/ validate_progress 全绿；§2.16 徽标列口径随本节更新为
  钉宽定值。
