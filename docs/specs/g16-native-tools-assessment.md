# G16 原生工具集成评估（WebUI 工具箱）

> 状态：已实施，计划见 [toolbox-plan.md](../plans/toolbox-plan.md)（随 3.8.0
> 冻结发布，2026-11-18 重冻结；验收留痕见
> [toolbox-acceptance.md](../plans/toolbox-acceptance.md) 与
> [toolbox-revision-acceptance.md](../plans/toolbox-revision-acceptance.md)）。
> 本文档是需求与工具评估，不是实施计划；以本文档为需求输入的实施计划已落
> `docs/plans/`。

## 1. 背景与需求定位

用户需求：把 G16 发行版自带的命令行工具（utilities）做进 WebUI，使「chk / out 产物
→ 各类数据转换导出」可在浏览器内完成，导出物供其他专业分析软件（PyMOL、Chemcraft、
VMD、自编程序等）进一步处理。

核心价值链（本次评估确立）：

```text
chk ──(chkchk 体检 → formchk 转换)──▶ fchk ──(cubegen)──▶ cube
chk/out ──(cclib 已有链路)──▶ 结构化数据
```

G16 原生工具只负责 cclib 覆盖不到的部分：cube 生成、chk 体检与转换、route 校验、
内存估算、溶剂名数据源。数据解析导出主体仍由 cclib 承担，分工见 §5。

## 2. 决策结论

采纳 G16 原生工具 **5 项**，形成 4 条工具链 + 1 个静态数据源：

| # | 工具链 | 组成 | 一句话定位 |
|---|---|---|---|
| 1 | chk 体检与转换 | `chkchk` → `formchk` | 主要工具：先体检后转换，体检失败则明示 chk 损坏 |
| 2 | cube 生成 | `cubegen` | 主要工具：fchk → cube（密度/自旋/静电势/MO） |
| 3 | route 校验 | `testrt` | 融入输入文件格式校验：route 语法检查 + 报错回显 |
| 4 | 内存估算 | `freqmem` | 融入输入校验（freq 任务内存提示），亦可单独小工具 |
| — | 溶剂名数据源 | `solname` | 启动时缓存为静态 JSON，作 SCRF 溶剂下拉菜单数据源 |

明确不纳入清单及理由见 §7。

## 3. 实测环境与溯源方法

- 实测日期：2026-11-14；实测机器：WSL2（本机开发环境）。
- G16 安装目录：`~/g16`（对应 WebUI 设置项 `g16_root`），版本号
  `ES64L-G16RevC.01`（3-Jul-2019）——由 `testrt` 输出首行自报。
- 溯源方法三种，本文档证据均来自此，可复现：
  1. **`.hlp` 帮助文件**：G16 发行时自带，位于 `~/g16/<tool>.hlp`，是各工具
     命令行语法的权威文档；
  2. **`ghelp` 内置帮助系统**：`~/g16/ghelp <topic>`，部分工具（如 mm）只有
     此处有文档；
  3. **实地运行**：无参运行探测 usage 提示；用真实数据（`~/g16/tests/` 金标准
     fchk、`~/g16web/run/1/h2o_opt2.chk` 任务产物）跑通完整转换链路。
- 补充参考：`~/g16/doc/formchk.txt`（fchk 文件格式的官方权威描述）。

## 4. 保留工具详述

### 4.1 chkchk — chk 体检

- **作用**：读取二进制 chk 文件，打印其元信息与内容清单，可直接判断 chk
  是否值得转换（即 formchk 能否成功）。
- **用法**：`chkchk [-p,-nofc] file.chk`（无参运行自报 usage，实测）。
  无 `.hlp` 文件；证据为实地运行。
- **实测输出**（`chkchk h2o_opt2.chk`）：
  ```text
  Title:  water opt
  Route:  #p opt b3lyp/6-31g(d)
  Version:  ES64L-G16RevA.03
  NAtoms=      3 ICharg=     0 Multip=     1
  Atomic coordinates present.
  AO basis is present.
  MO coefficients present.
  This checkpoint is from a job which completed successfully.
  ```
  `-p` 额外打印原子坐标（Å）与基组明细。
- **体检价值**：输出直接给出「坐标/基组/MO 系数是否在场」「作业是否成功完成」
  「内部力常数/OT 桶是否在场」等逐项结论，可作为 formchk 前置判断依据，
  也可作为 WebUI 中 chk 详情展示的数据来源。

### 4.2 formchk — chk → fchk 转换

- **作用**：把二进制 chk 转为机器无关的文本 fchk（Formatted Checkpoint），
  供后处理程序按行解析；fchk 本身即最终导出物之一（cclib 可读，
  Chemcraft/GaussView 等可直接打开）。
- **用法**（`~/g16/formchk.hlp`，权威）：
  `formchk [-0,-c,-2,-3] [-r] [-pesirc] input[.chk] [output[.fchk]]`
  - `-3` 为默认格式（含内坐标定义与导数、全部字符数据）；
    `-0` 仅原始数据，`-2` 含 MM 参数，`-c` 允许字符数据存储；
  - `-raw` / `-mat` 输出矩阵元文件（本项目不用）；
  - `-pesirc` IRC 数据取自 PES 结构对象（默认取自 OT 文件）。
- **格式权威描述**：`~/g16/doc/formchk.txt`（含 Type/Method/Basis 文件头
  与标量/数组段落格式定义）。
- **实测**：`formchk h2o_opt2.chk` → 生成 98,149 字节 fchk，输出
  `Read checkpoint file h2o_opt2.chk type G16` / `Write formatted file
  h2o_opt2.fchk`。
- **与现状的关系**：本项目已有三处深度集成（`web/src/engine/materialize.py`
  有效性探针、任务完成自动物化、续跑消费），本工具链新增的是**手动转换入口**
  （用户自选 chk → 下载 fchk），探针的安全调用范式（临时目录 + 超时 +
  产物头部校验）可直接复用。

### 4.3 cubegen — fchk → cube 生成

- **作用**：从 fchk 生成 cube 文件（三维网格数据），供可视化软件渲染等值面。
  导出物 cube 可被 3Dmol.js（前端已用）、PyMOL、VMD、Chemcraft 等直接读取。
- **用法**（`~/g16/cubegen.hlp`，权威）：
  `cubegen nproc what fchkfile cubefile npts format`
  - `what` 取值（UI 侧做成下拉，见 §6）：`density=SCF`（总密度）、
    `spin=SCF`（自旋密度）、`alpha=SCF` / `beta=SCF`、`potential=SCF`
    （静电势）、`mo=N`（第 N 号轨道）、`fdensity`（全电子密度，非冻核）等；
  - `npts`：`0` 为默认 80³；`-2`/`-3`/`-4` 为粗/中/细网格；`-N>5` 表示
    点间距 N×0.001 Å；正整数 N 即 N³ 网格；
  - `format`：`h` 含头 / `n` 无头（本项目恒用 `h`）。
- **实测**：`cubegen 0 density=SCF h2o_optfreq_popreg.fchk h2o.cube 40 h`
  → 生成 840,092 字节 cube，头行 `Electron density from Total SCF Density`。
- **传参陷阱**：`what` 中 `density=` 后接的是**密度类型**（SCF/Total 等），
  fchk 文件名是独立参数——实测曾误写 `density=<文件名>` 导致
  `ntran open failure` 报错。封装时必须用枚举下拉而非自由文本。

### 4.4 testrt — route 语法校验

- **作用**：把标准 route 关键词展开为完整 link 序列（overlay/选项/链接）。
  在本工具箱中的用途是**输入文件格式校验**：拼错关键词、未定义选项在
  route 解析阶段即报错，可拦截在派发之前。
- **用法**（`~/g16/testrt.hlp`）：`testrt '<route 字符串>'`，或无参交互输入。
  注意它只吃 route 字符串，不吃整个 gjf——后端需先从输入文件抽出 route 行。
- **实测三种输入**：
  | 输入 | 结果 |
  |---|---|
  | `b3lyp/6-31g(d) opt freq` | 正常展开为 link 序列 |
  | `b3lypxyz/6-31g(d)`（拼错方法名） | `QPErr --- A syntax error was detected in the input line.` 并回显出错关键词与位置（`Last state= "GCL"`），**随后异常终止（SIGABRT，退出码 134，`Aborted (core dumped)`）+ core dump 落 cwd** |
  | `opt=qqq freq=www`（未定义选项） | 同上，QPErr 报错 + SIGABRT |
- **校验能力边界**：只校验 **route 语法**（关键词拼写、选项存在性），
  不校验语义矛盾；`opt` 与 `freq` 组合本身合法，它不会拦。

### 4.5 freqmem — 频率计算内存估算

- **作用**：按体系规模估算 freq 计算所需内存，融入输入文件校验：
  对 freq 任务按原子数/基函数数给出内存提示，防派发后因内存不足失败。
- **用法**（无参运行自报 usage，实测）：
  `freqmem num-atoms num-basis r/u s/p/d/f/g/...`
  四个位置参数：原子数、基函数数、r/u（闭/开壳层）、基组角动量层级。
  无 `.hlp` 文件；纯命令行，无交互、无副作用，零风险。

### 4.6 solname — SCRF 溶剂名数据源

- **作用**：列出 G16 支持的全部 SCRF 溶剂（实测头行 `NSolv= 184`，头行
  + 214 条目行共 215 行输出）。每溶剂恒有一条全名行（JN=1），23 个溶剂
  另有别名/缩写行（JN=2/3/4 合计 30 条，如 `Water/H2O`、
  `Acetonitrile/CH3CN`；Acetone/DMSO 各有两条别名）——并非每项都有
  缩写。
- **用法**（实测）：`solname` 直接输出，无参数、无交互。
- **预期使用**：WebUI 后端启动时（或安装时）运行一次，解析为静态 JSON
  缓存，作输入表单中 SCRF 溶剂下拉菜单的数据源；避免用户手写溶剂名拼写
  错误。无需常驻调用。

## 5. 工具链与预期使用方式

### 工具链 1：chk 体检与转换（主要工具）

```text
用户选择任务 → chkchk 体检（元信息 + 内容清单 + 作业完成状态）
           → 体检通过 → formchk 转换 → fchk 下载
           → 体检失败 → 明示「chk 损坏/不完整」，不再转换
```

- 消费对象：`~/g16web/run/<执行id>/*.chk`（任务产物已留存）。
- 与现有物化链路的关系：手动入口是自动物化（任务完成后已自动 formchk）的
  补充——覆盖 chk 存在但 fchk 缺失/丢失、或用户只想体检不想转换的场景。

### 工具链 2：cube 生成（主要工具）

```text
用户选择任务（需已有 fchk；无则先走工具链 1）
  → 选 what（枚举下拉：density/spin/alpha/beta/potential/mo=N）
  → 选网格档位（粗/中/细，对应 -2/-3/-4，禁自由数值）
  → cubegen 生成 cube → 前端 3Dmol 预览 + 下载
```

- roadmap 已有定位呼应：`docs/specs/roadmap.md` §143（化学层 cubegen/fchk）、
  §496（fchk → cubegen → cube 供可视化）。

### 工具链 3：route 校验（融入输入文件校验）

```text
用户提交/编辑输入文件 → 后端抽出 route 行 → testrt
  → 展开成功 → 校验通过（可选回显 link 序列）
  → QPErr 报错 → 提取报错行与出错位置回显前端
```

### 工具链 4：内存估算（融入输入校验，或单独小工具）

freq 任务派发前用 `freqmem` 估算内存并提示；独立入口为小表单
（原子数/基函数数/壳层类型/角动量）→ 结果回显。

### 数据源：溶剂名静态 JSON

安装/启动时 `solname` 一次 → 解析缓存 → SCRF 下拉菜单。

### 与 cclib 的分工

| 数据需求 | 承担方 |
|---|---|
| out/fchk → 能量/几何/频率/热化学等结构化数据 | cclib（已有链路） |
| chk 体检、chk → fchk 文件转换 | G16 工具链 1 |
| cube 生成（轨道/密度/静电势渲染数据） | G16 工具链 2 |
| route 语法校验、freq 内存估算、溶剂名 | G16 工具链 3/4 + 数据源 |

## 6. 注意事项（集成风险清单）

1. **testrt 报错即异常终止（SIGABRT，退出码 134）+ core dump**（实测）：
   调用必须落在临时目录（core 文件落地隔离）、进程超时兜底、按非零退出码
   + stdout QPErr 段判定失败。其余工具链同理套用现有 `materialize.py`
   探针范式（临时目录 + `subprocess` 列表参数 + 超时）。
2. **freqchk 空 stdin 会 segfault**（实测）——虽未纳入工具箱，但若未来
   纳入同位素重算场景，须受控 stdin + 超时保护。
3. **cubegen 传参陷阱**（实测）：`density=` 后是密度类型而非文件名；
   what 与 npts 必须枚举化封装，禁自由文本。
4. **cube 体积**：默认 80³ 网格可达数 MB；UI 默认粗/中档网格，产物走
   下载或前端按需加载，不内联进页面数据。
5. **交互式工具一律不纳入**（freqchk/copychk/cubman/mm 等 stdin 问答驱动，
   自动化脆弱）；本次 5 项均实测为非交互或纯命令行，可安全 `subprocess` 调用。
6. **版本差异**：实测基于 `ES64L-G16RevC.01`；chkchk 报告 chk 内嵌创建版本
   （如 G16RevA.03），说明 chk 元信息与当前工具版本可能不同代——体检输出
   应原样透传版本号，不做兼容性断言。
7. **并发与工作目录**：工具调用一律使用独立临时目录，产物按目标路径落盘后
   清理，避免多任务并发互踩（沿用派发链路既有约定）。
8. **环境变量**：工具均依赖 G16 运行环境（`g16root`/`GAUSS_EXEDIR` 等），
   调用时须复用派发链路既有的环境构造（`roadmap.md` §226 有完整环境等价
   说明），勿裸调。

## 7. 明确不纳入清单

| 工具 | 理由（溯源见本文档 §3 方法） |
|---|---|
| `unfchk` | fchk → chk 逆向转换很少用（用户取舍）；实测可用但无 GUI 场景 |
| `copychk` | 复制 chk 不如系统 `cp`（用户取舍）；实测为 stdin 交互两问 |
| `freqchk` | 频率表与热化学数据已被 cclib 覆盖（任务完成后 out+fchk 均在）；独特价值仅剩同位素替换重算热化学与从残缺 out 重建频率，场景再现时再评估。实测注意：空 stdin segfault |
| `cubman` | cube 加减/缩放/差分用 cclib 读入 + numpy 即可数行实现；前端 3Dmol.js 原生渲染 cube |
| `newzmat` | 几何格式互转（chk/xyz/pdb/mopac ↔ gjf）暂无场景，观察 |
| `rdmat`/`wrmat` | 矩阵元文件读写，配合 `Output=Matrix` 使用，属第三方开发者工具（证据：`~/g16/doc/rdmat1.F` 为官方示例解析源码）；cclib 可直接从 fchk 取 MO 系数等 |
| `mm` | 独立分子力学程序（UFF/Dreiding/Amber 力场，`ghelp mm` 有完整文档）；用户可走 `Opt=MM`，未来可由 ASE/OpenBabel 替代（roadmap §6 已列暂缓） |
| `gauopt` | 内部参数优化工具，无 ghelp/hlp 文档，风险高 |
| `gautraj`/`trajgen`/`gdrgen` | IRC/反应路径动画几何生成，无文档（实测均提示读 fchk/chk）；若 3.6.0 做 IRC 分析确需动画几何，届时再评估（cclib 亦可从 out 提取 IRC 路径点） |
| `l*.exe`、`g16`、`gau-cpp`/`gau-fsplit`/`gau-machine`、`ghelp`、`ham506`/`grate`/`demofc`/`c8616`/`pluck` | 内部执行组件/构建辅助/帮助器/特殊用途，非用户工具 |

## 8. 后续

实施计划立项后落 `docs/plans/`，以本文档为需求输入；计划应覆盖：
API 契约（`docs/api/openapi.yaml`）、前端入口（工具箱面板）、
后端工具调用层（复用探针范式）、测试（含金标准数据与损坏 chk 反例）、
`check_tokens`/`check_contrast` 等闸门适用性声明。
