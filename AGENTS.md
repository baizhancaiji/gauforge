# AGENTS.md — 仓库协作与工程约定

> 本仓库是 **GauForge**——以 HyperQueue 为执行内核的 G16 计算化学工作台：
> Rust 核心（`crates/`，上游 HyperQueue 队列引擎，按需修改）+ Python 子系统
> （`web/`，Web 工作台）。
> 项目根 = 仓库根。方向与里程碑见 [docs/specs/roadmap.md](docs/specs/roadmap.md)。

## 一、项目定位

- 面向 WSL2 单机的计算化学工作台，以「输入 → 计算」为完整闭环（M0–M2 即完整产品），
  分析及以后为功能更新；队列只是执行器。
- `web/` 为从零实现的 Python 子系统；原 `g16web/` 下的一次性原型（含 `prototype/`）已整体删除，
  仅其踩坑记录作为设计输入待补。
- 上游 HyperQueue 代码已视为本项目组成部分，可按需修改（ADR 0001）；git 历史已与上游
  切割、项目自立更名 GauForge（ADR 0002），吸纳上游更新改为按需手动移植，不再 merge/rebase。

## 二、目录结构

```text
crates/               Rust 源码：HyperQueue 队列核心（上游代码为主）
web/                  Python 子系统：G16 Web 工作台
├── src/              业务模块（配置集中在 config.py）
├── frontend/         前端（Vite + Vue3 + 3Dmol.js）
└── tests/            与被测模块同名对应的测试
docs/
├── specs/            方向与需求文档（roadmap.md）
├── adr/              架构决策记录
├── plans/            专项实施计划（含设计样板 assets/）
├── api/              契约 SSOT（openapi.yaml / sse.md）
└── references/       规范单一事实来源（提交规范、进度管理规范）
scripts/              构建、运维、校验脚本（本项目闸门与冒烟）
CHANGELOG.jsonl       冷数据：本项目完整发布历史（append-only）
progress.json         热数据：当前状态快照（覆盖写）
```

## 三、技术栈

| 层 | 技术 |
|---|---|
| 队列核心 | Rust（`crates/`，cargo 构建，产物 `/target/hq`） |
| 后端 | Python 3.10+（uv 管理虚拟环境；M0 起引入 FastAPI） |
| 持久化 | SQLite（任务历史/元数据，路径见 `web/src/config.py`） |
| 执行集成 | `hq --output-mode json` CLI 起步，深度融合、可按需改 `crates/` 源码（ADR 0001） |
| 解析 | cclib（结果）+ 自写增量解析（仅运行中进度） |
| 前端 | Vite + Vue3 + 3Dmol.js（已定稿；M0 起引入 `web/frontend/`） |

## 四、命令入口

```bash
uv venv && uv pip install -r requirements.txt    # 初始化 Python 环境（仓库根 .venv/）
uv run pytest                                     # 本项目测试（默认发现 web/tests）
uv run python scripts/validate_progress.py        # 进度管理两文件校验（提交前闸门）
cargo build --release                             # 构建 hq（Rust 核心）
```

g16web 服务的拉起/关闭、前端开发链路与隔离冒烟见
[docs/references/development.md](docs/references/development.md)。

## 五、仓库纪律

### 5.1 提交

- 遵守 [conventional_commits.md](docs/references/conventional_commits.md)：12 类 type、`<type>[(scope)]: <summary>`、中文动词开头 summary。
- **单次提交只做一类变更**；文档与代码、重构与功能、格式化与逻辑必须分开提交。
- 每个提交应可构建、可运行、可回滚。
- 大改动拆成多个可审查的小提交，按「文档 → 测试 → 实现 → 进度同步」的自然顺序排列。
- 正文用 `- ` 列表分条陈述动机与影响，一条一句，不写成整段散文。
- 提交前先整理改动，不混入无关格式化或临时调试代码。

### 5.2 发布

按 [changelog-spec.md](docs/references/changelog-spec.md) §1.6 执行，顺序固定：

1. 确认当前 unreleased 行的 `changes` 已完整（无遗漏、无未批准条目）。
2. **冻结**：`status` 改为 `released`，补齐 `version`、`date`（ISO 8601 精确到分钟并带时区偏移）、`semver`。
3. 在文件末尾**追加新的空 unreleased 行**。
4. 更新 `progress.json`：清空 `unreleased`，更新 `latest_released_version`。
5. 本地打 tag：`git tag v<version>`，并提示协作者。

版本号判定见 [changelog-spec.md](docs/references/changelog-spec.md) §1.7（breaking → major；含 added → minor；仅修复 → patch）。

### 5.3 禁止事项

- 不改写已发布版本的历史记录。
- 不在变更记录中写 commit hash（细节以 git 历史为准）。
- 不手工维护 Markdown 版 CHANGELOG（与机器可读版本必然漂移），本项目变更一律记入 `CHANGELOG.jsonl`；人类可读的 `CHANGELOG.md` 只能由 `scripts/gen_changelog_md.py` 从 `CHANGELOG.jsonl` 生成（`--check` 校验一致），不得手工编辑。
- 不让 `progress.json` 无限增长（它是快照，不是流水账）。
- 不提交疑似含密钥的文件（`.env`、凭据文件）；如确需提交，先明确告知风险。
- 不使用 `git add -A` / `git add .` 批量暂存，逐文件按名添加，避免误入敏感文件与大数据。

## 六、代码审查机制

审查分三层，**逐层递进，任何一层不过则不得提交**。

### 6.1 第一层：自审（提交前）

1. 全量测试通过，记录实际通过数。
2. 治理层校验脚本全部通过（结构校验、引用校验、数据一致性校验）。
3. 若改动涉及可量化指标（性能、检索质量、体积），**跑基线对照**并记录前后数字。
4. 涉及派发/端到端链路的改动：确认 `target/release/hq` 存在（先 `cargo build --release`）——缺失时 `test_e2e_fake_g16.py` 等关键 e2e 用例会**静默跳过**，通过数虚高不等于闸门通过。

### 6.2 第二层：独立复核

审查者**不采信实施者的自述**，独立执行以下四查，每条结论都要有可复现的命令与实测输出：

| 查什么 | 怎么做 |
|---|---|
| 校验可复现 | 独立重跑全部校验脚本与测试，不引用他人输出 |
| 指标可复现 | 用当前数据重算指标，确认与实施者记录逐位一致（含逐条对照清单） |
| 范围可证实 | 用 `git diff` 证实「声称未改动的部分」确实零改动 |
| 端到端可用 | 在真实运行环境冒烟（启动服务、调用接口、观察日志），而非只跑单测 |

发现登记瑕疵（文档与事实不符、取数口径未注明等）时，修复后需再次复核，并在计划文档中留痕。

### 6.3 第三层：闸门脚本

把可自动化的判据固化为脚本，作为**零回退闸门**：

- 结构类：字段齐全性、键唯一性、引用可达性。
- 数据类：覆盖率、一致性、边界值。
- 效果类：与基线逐条对照，回退条目必须逐条归因（区分真实回退与环境噪声）。

脚本失败即退出码非零，纳入提交前检查。（本仓库当前闸门：
`scripts/validate_progress.py`、`uv run pytest`、`scripts/check_tokens.py`——
设计令牌逐变量一致性、`scripts/check_contrast.py`——WCAG 对比度全组合
≥ 4.5:1、`scripts/gen_changelog_md.py --check`——CHANGELOG.md 与 jsonl
一致性；涉及前端视觉或派发链路的改动另见 §6.1 第 4 条 hq 产物检查。）

## 七、长程脚本规范

长程脚本指预计运行超过 10 秒、涉及大量计算、网络请求或文件处理的脚本。**必须**实现：

1. **分批落盘** —— 处理结果按批写入磁盘，不全部驻留内存。
2. **断点续传** —— 重启时能识别已完成部分并跳过；进度锚文件与结果文件配套使用。
3. **定期进度打印** —— 周期性输出已完成/总数/耗时，便于判断卡死与预估剩余。
4. **幂等与可重跑** —— 重复执行不产生重复数据；标注「结果文件须与数据版本匹配」，数据更新后清理对应旧记录，防止新旧混算。

## 八、协作偏好

### 8.1 语言与文档
- 对话与文档正文一律使用简体中文。
- 规范类主文档用中文；引用的外部资料可保留原语言。

### 8.2 终端与环境
- 默认终端视环境而定,若为Windwos,则为 PowerShell 7：**不支持 heredoc**，改用 here-string 语法;若为Linux/WSL,使用默认bash。
- 安装依赖时默认使用UV在项目根目录创建虚拟环境，命令与参数压缩为单行，不使用多行命令(尤其在Windows)。

### 8.3 工具优先级

| 场景 | 首选 |
|---|---|
| 定位函数、变量、调用链、影响面 | 代码知识图谱（codegraph）的 MCP 或 CLI(如若可用) |
| 引入新依赖、查询库/框架用法 | context7 MCP 查最新参考文档，**不可仅凭记忆写代码**(MCP不可用必须报告用户提醒其配置) |
| 简单定向查找 | Grep / Glob |
| 大范围探索 | 探索型子代理 |
|安装依赖,包括但不限于pip,npm,cargo,rust等 | 使用UV在项目根目录创建虚拟环境,使用国内镜像源 |

### 8.4 工作方式（仓库铁律）
- **实事求是**：回答关于代码/架构的问题前，先回读相关文件的关键段落再作答；禁止凭印象、猜测、杜撰。
- **最短路径**：能直连就不引入中继/代理；能改一处就不动三处。
- **不过度设计**：只做被要求的改动；不提前抽象、不加用不到的配置项与兼容层。
- **脚本纳入版本管理**：运维与转发类脚本放项目目录并提交 git，不散落在仓库外。
- **输出路径参数化**：脚本接受输出路径参数，优先使用用户指定目录，默认回落到项目内约定目录。

## 九、进度管理约定

- schema 与流程的单一事实来源：[changelog-spec.md](docs/references/changelog-spec.md)，此处不复制正文。
- 提交规范单一事实来源：[conventional_commits.md](docs/references/conventional_commits.md)。

| 时机 | 动作 |
|---|---|
| 开发前 | 读 `progress.json`，把当前任务写入 `in_progress` |
| 提交前 | 按 `conventional_commits.md` 组织提交（单次提交只做一类变更），并跑 `scripts/validate_progress.py` |
| 完成一次变更 | 向 `CHANGELOG.jsonl` 的 unreleased 行与 `progress.json` 的 `unreleased` 同步追加摘要 |
| 发布时 | 冻结 CHANGELOG 行 → 追加新的空 unreleased 行 → 清空 `progress.json` 的 `unreleased` → 本地打 tag |
| 排查回归 | 按需读 `CHANGELOG.jsonl`，不要每次全量读取 |

## 十、跨平台工程约定（WSL2 + Windows 场景强制）

- 路径统一 `pathlib.Path`，拼接用 `/` 运算符；禁止 `os.path.join`、硬编码绝对路径。
- 子进程参数一律列表形式，禁止 `shell=True` 与 `os.system()`；调用 Python 用 `sys.executable`。
- 文本读写显式 `encoding="utf-8"`；`.sh` 与 systemd 单元必须 LF。
- 配置分两级：启动级参数（工作区根、监听地址）通过环境变量覆盖，统一前缀 `G16WEB_`（Rust 侧沿用 `HQ_`）；运行级参数（含监听端口，保存后重启生效）由 WebUI 设置面板管理（SQLite 持久化，生效规则见 [roadmap.md §2.5](docs/specs/roadmap.md)）；默认值集中在 `web/src/config.py`。
