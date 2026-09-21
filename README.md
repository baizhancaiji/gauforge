# HQ · G16 计算化学工作台

基于 [HyperQueue](https://github.com/It4innovations/hyperqueue) 队列引擎的 Gaussian 16
计算化学工作台，为 WSL2 单机工作流打造，覆盖「输入 → 计算 → 分析」闭环。
工作分支：`g16-webui`。

```
前端 (Vite + Vue3/React + 3Dmol.js)          ← M0 起
   │ REST + SSE
服务层 (FastAPI，契约先行 OpenAPI)
领域层 (Calculation 状态机 + SQLite 历史)
   ├── 执行适配器：HyperQueue（hq --output-mode json）
   ├── 解析层：cclib（结果）+ 自写增量解析（运行中进度）
   └── 化学层：ASE / OpenBabel（结构互转）、cubegen/fchk（轨道）
```

- **队列核心**：`crates/` 为 HyperQueue（Rust），作为执行引擎按需修改，`cargo build --release` 构建。
- **Web 子系统**：`g16web/`（Python 3.10+，uv 管理环境）。
  `g16web/prototype/` 是验证链路的已冻结原型，用法见
  [g16web/prototype/README.md](g16web/prototype/README.md)。

## 快速开始

```bash
# Python 子系统
uv venv && uv pip install -r requirements.txt
uv run pytest                                  # 测试（发现 g16web/tests）
uv run python scripts/validate_progress.py     # 进度文件校验

# 队列核心（如需自行构建 hq）
cargo build --release

# 归档原型（仅调试参考：提交/监控面板，监听 127.0.0.1:8160）
python3 g16web/prototype/server.py
```

依赖：`~/opt/hyperqueue/hq`（HQ 二进制）、`~/g16`（Gaussian 16 安装）、`~/scratch`（任务与上传目录）。路径均可经 `G16WEB_*` 环境变量覆盖，见 `g16web/src/config.py`。

## 里程碑

| 里程碑 | 内容 | 验收 |
|---|---|---|
| M0 | 契约与骨架 | 只看 OpenAPI 契约即知全部能力；前端 mock 三界面 |
| M1 | 队列与监控 | 提交 → 实时看到优化步/SCF → 历史可查 |
| M2 | 输入工程 | 从 PDB 不手写文本生成合法 opt 输入并提交 |
| M3 | 结果分析 | freq 输出可见谱图并画出一条轨道 |
| M4 | 工作流 | 一键「构象搜索 + top N 精修」并汇总能量表 |
| M5 | DSH 接入 | 自然语言「帮我优化水分子并看结果」走通 |

详见 [docs/plans/roadmap.md](docs/plans/roadmap.md)。

## 文档索引

- [AGENTS.md](AGENTS.md) — 仓库协作与工程约定（AI 与人共用）
- [docs/plans/roadmap.md](docs/plans/roadmap.md) — 方向规划与里程碑
- [docs/references/conventional_commits.md](docs/references/conventional_commits.md) — 提交规范
- [docs/references/changelog-spec.md](docs/references/changelog-spec.md) — 进度管理规范
- `progress.json` — 当前状态快照（开发前必读）

## 上游 HyperQueue

本仓库 fork 自 [It4innovations/hyperqueue](https://github.com/It4innovations/hyperqueue)。
HQ 自身的文档见 [上游文档站](https://it4innovations.github.io/hyperqueue/) 与仓库内
`docs/`（含 [examples](docs/examples)）；上游变更历史见 `CHANGELOG.md`（只读）。
若你在研究中使用 HyperQueue，请考虑
[引用其论文](https://github.com/It4innovations/hyperqueue#publications)。
