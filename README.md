# GauForge · Gaussian 16 管理工作台

GauForge 是以 [HyperQueue](https://github.com/It4innovations/hyperqueue)为执行内核的 Gaussian 16 计算化学工作台，为 WSL2 单机工作流打造，以「输入 → 计算」为完整闭环。
当前版本 **v2.2.0**：M0–M2（契约骨架、候选入口与队列执行、输入工程）已全部完成，构成完整产品；结果分析（M3）及以后为后续功能更新。完整发布历史见 [CHANGELOG.md](CHANGELOG.md)，后续发布见 [Releases](https://github.com/baizhancaiji/gauforge/releases)。
工作分支：`g16-webui`。

```
前端 (Vite + Vue3 + 3Dmol.js)
   │ REST + SSE
服务层 (FastAPI，契约先行 OpenAPI)
领域层 (候选/队列/执行状态机 + SQLite 持久化)
   ├── 执行层：HyperQueue 内核深度融合（进程内 HTTP/SSE 桥接）
   ├── 解析层：cclib（结果）+ 自写增量解析（运行中进度）
   └── 化学层：cubegen/fchk（轨道/静电势）；ASE/OpenBabel 暂缓
```

## 核心特性

- **候选与导入** — 单文件/文件夹批量导入 `.gjf`；文件夹导入可一键「保存为队列」成队（2–10 个文件，越界明示回落原因）；候选列表回退候选置顶、创建时间倒序，支持筛选与排序。
- **输入工程** — BlockEditor 分块编辑（link0/route/title/charge_mult/additional），失焦或 800ms 防抖自动保存；route 关键词拼写检查、CRLF 中性检出；三条提交路径建席前统一核验，解析失败与多步任务 422 拒绝且不落盘，规范化结果带注记。
- **队列组建与编辑** — 多选组建队列（复选框、Shift 范围选择、Ctrl 追加、方向键导航、Ctrl+A/Esc）；队列编辑对话框按状态分级（未提交全量编辑、已提交仅成员、执行中/已完成只读）；指针跟手的拖拽排序。
- **队列生命周期** — 提交/重新提交/删除二次确认按状态分级；失败自动补位、失败成员回退归因（failed/skipped 标记）、回退候选可编辑后重新排队，整队执行自动成功终结。
- **实时进度** — SSE 推送任务与队列事件，运行中任务增量解析优化步/SCF 进度；侧栏电源灯指示连接态（在线/重连/断线）。
- **历史与归因** — 任务历史可查且归因正确（状态、结束原因中文显示），支持历史任务重新提交与重新排队。
- **界面工程** — 视口固定布局、列表局部滚动、粘性表头、标准分页套件；设计令牌体系（令牌一致性/对比度双闸门），明暗双主题。

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

## 文档索引

- [AGENTS.md](AGENTS.md) — 仓库协作与工程约定（AI 与人共用）
- [docs/specs/roadmap.md](docs/specs/roadmap.md) — 方向规划与里程碑
- [docs/adr/](docs/adr/) — 架构决策记录
- [docs/references/conventional_commits.md](docs/references/conventional_commits.md) — 提交规范
- [docs/references/changelog-spec.md](docs/references/changelog-spec.md) — 进度管理规范
- [docs/references/deployment.md](docs/references/deployment.md) — 部署与升级（干净发行包，含国内代理说明）
- `progress.json` — 当前状态快照（开发前必读）

## 内核来源

`crates/` 改自上游 [It4innovations/hyperqueue](https://github.com/It4innovations/hyperqueue)主干（v0.26.2 之后的未发版提交，fork 点 `21f2d2e8b`，含其调度器改进），本项目历史已自立，上游更新改为按需手动移植（见 ADR 0002）。
若你在研究中使用 HyperQueue，请考虑
[引用其论文](https://github.com/It4innovations/hyperqueue#publications)。

## AI 使用声明

本项目开发过程中大量使用 AI 编码代理协作完成代码与文档的编写、测试与走查；需求定义、方案决策与验收把关由作者完成。

## 许可

分层许可（详见 [LICENSE](LICENSE)）：

- **自有代码**（除 `crates/` 外的全部内容）：PolyForm Noncommercial License 1.0.0——可自由使用、修改与再分发，但仅限非商业目的；商业使用需另行获得授权。
- **内核 `crates/`**：上游 HyperQueue 的 MIT 许可完整保留  ([`crates/LICENSE`](crates/LICENSE))，不受上述限制。
- 其余第三方依赖各依其原始许可证。

v1.0.0（含）之前的发布版本按 MIT 授权存续。
