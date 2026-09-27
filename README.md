# GauForge · Gaussian 16 管理工作台

GauForge 是以 [HyperQueue](https://github.com/It4innovations/hyperqueue)
为执行内核的 Gaussian 16 计算化学工作台，为 WSL2 单机工作流打造，
以「输入 → 计算」为完整闭环（M0–M2 即构成完整产品），
分析及以后各里程碑为功能更新。
工作分支：`g16-webui`。

```
前端 (Vite + Vue3 + 3Dmol.js)                 ← M0 起
   │ REST + SSE
服务层 (FastAPI，契约先行 OpenAPI)
领域层 (候选/队列/执行状态机 + SQLite 持久化)
   ├── 执行层：HyperQueue 内核深度融合（hq --output-mode json 起步，按需改 crates/ 源码）
   ├── 解析层：cclib（结果）+ 自写增量解析（运行中进度）
   └── 化学层：cubegen/fchk（轨道/静电势）；ASE/OpenBabel 暂缓
```

- **队列核心**：`crates/` 为 HyperQueue 内核（Rust），作为执行引擎按需修改，`cargo build --release` 构建。
- **Web 子系统**：`web/`（Python 3.10+，uv 管理环境），从零实现；原 `g16web/` 原型已整体删除。

## 快速开始

```bash
# Python 子系统
uv venv && uv pip install -r requirements.txt
uv run pytest                                  # 测试（发现 web/tests）
uv run python scripts/validate_progress.py     # 进度文件校验

# 队列核心（如需自行构建 hq）
cargo build --release
```

依赖：`~/opt/hyperqueue/hq`（HQ 二进制）、`~/g16`（Gaussian 16 安装）。工作区根默认 `~/g16web/`，路径均可经 `G16WEB_*` 环境变量覆盖，见 `web/src/config.py`。

## 里程碑

| 里程碑 | 内容 | 验收 |
|---|---|---|
| M0 | 契约与骨架 | 只看 OpenAPI 契约即知全部能力；前端 mock 五类界面 |
| M1 | 候选入口 + 队列与执行（核心闭环） | 导入 → 候选列表 → 提交 → 实时看到优化步/SCF → 历史可查且归因正确 |
| M2 | 输入工程（编辑 + 队列组建） | 分块编辑 + 队列组建 + 整队执行全部走通 |
| M3 | 结果分析 | freq 输出可见谱图并画出一条轨道 |
| M4 | 工作流 | 一键「构象搜索 + top N 精修」并汇总能量表 |
| M5 | DSH 接入 | 自然语言「帮我优化水分子并看结果」走通 |

M0–M2 合起来构成完整产品，M3 及以后为其上的功能更新；详见 [docs/specs/roadmap.md](docs/specs/roadmap.md)。

## 文档索引

- [AGENTS.md](AGENTS.md) — 仓库协作与工程约定（AI 与人共用）
- [docs/specs/roadmap.md](docs/specs/roadmap.md) — 方向规划与里程碑
- [docs/adr/](docs/adr/) — 架构决策记录
- [docs/references/conventional_commits.md](docs/references/conventional_commits.md) — 提交规范
- [docs/references/changelog-spec.md](docs/references/changelog-spec.md) — 进度管理规范
- `progress.json` — 当前状态快照（开发前必读）

## 内核来源与许可

`crates/` 改自上游 [It4innovations/hyperqueue](https://github.com/It4innovations/hyperqueue)
主干（v0.26.2 之后的未发版提交，fork 点 `21f2d2e8b`，含其调度器改进），
本项目历史已自立，上游更新改为按需手动移植（见 ADR 0002）。
HQ 自身的文档见 [上游文档站](https://it4innovations.github.io/hyperqueue/) 与仓库内
`docs/`（含 [examples](docs/examples)）；上游变更历史见 `CHANGELOG.md`（只读）。
若你在研究中使用 HyperQueue，请考虑
[引用其论文](https://github.com/It4innovations/hyperqueue#publications)。

许可双轨：根 [LICENSE](LICENSE) 适用于 GauForge 自有代码（`web/`、`frontend/`、`docs/` 等）；
[`crates/LICENSE`](crates/LICENSE) 保留上游 MIT 原文与版权行，随内核源码一并提供。
