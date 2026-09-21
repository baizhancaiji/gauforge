# CHANGELOG 与项目状态规范

> 本规范定义仓库的变更记录与项目状态体系：冷数据 `CHANGELOG.jsonl`（完整发布历史，append-only）与热数据 `progress.json`（当前状态快照，覆盖写）。与 Git 提交规范（见 `docs/references/conventional_commits.md`）配套使用，后者描述「怎么提交」，本规范描述「提交后如何沉淀到变更记录」。
>
> **全仓库时间戳统一约定**：所有记录时间戳（`date`、`updated` 等）使用 ISO 8601，**精确到分钟、带时区偏移**，如 `2026-09-10T14:30+08:00`。

---

## 一、CHANGELOG.jsonl（冷数据）

### 1.1 定位与 append-only 原则

- 定位：**完整发布历史**，唯一权威来源。用于查历史、发布、排查回归，仅在需要时读取，禁止每次开发全量读取。
- 体量会持续增长，不做瘦身、不覆盖写。
- **每行一个 JSON 对象**，行尾换行，UTF-8 编码。追加只发生在文件末尾。
- **禁止改写或删除已发布的行**；发现已发布版本有遗漏，作为新变更记入当前 unreleased 行（发布后则记入新追加的 unreleased 行）。
- 不写 commit hash（细节以 git 历史为准，此处只记录用户可见的行为变化）。

### 1.2 行级 schema

| 字段 | 类型 | 说明 |
|---|---|---|
| `version` | string/null | 版本号，如 `"0.1.0"`；**null 表示未发布** |
| `status` | string | `unreleased` / `released` |
| `date` | string/null | 发布日期，ISO 8601 精确到分钟并带时区偏移（如 `2026-09-10T14:30+08:00`）；未发布时可省略 |
| `semver` | string/null | `major` / `minor` / `patch`；未发布时可省略 |
| `changes[]` | array | 变更条目数组，条目字段见 1.3；未发布时可为空数组 |

未发布行只需 `version`、`status`、`changes` 三个字段；发布（冻结）时补齐 `date`、`semver`。

### 1.3 changes[] 条目字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | `added` / `changed` / `deprecated` / `removed` / `fixed` / `security` |
| `scope` | string | 影响范围，建议使用模块/目录名（与 Conventional Commits 的 scope 对齐），无明确范围可省略 |
| `summary` | string | 一句话描述，见 1.5 撰写规则 |
| `breaking` | boolean | 是否破坏性变更，默认 false |
| `migration` | string/null | 升级指引；**`breaking=true` 时必填**，否则省略或置 null |

### 1.4 type 与 Conventional Commits type 的映射

以 `docs/references/conventional_commits.md` 的 12 类提交类型为输入，映射到 6 类变更条目：

| Conventional Commits type | 是否记录 | 映射条目 type | 理由 |
|---|---|---|---|
| `feat` | 记录 | `added` | 新功能，对用户可见，是 minor 版本依据 |
| `fix` | 记录 | `fixed` | 错误修复，对用户可见 |
| `perf` | 记录 | `changed` | 性能变化属于行为变化，用户可感知；若属纯内部微调，按 `refactor` 处理可不记录 |
| `refactor` | 视情况 | `changed` 或不记录 | 无行为变化的纯内部重构不记录；改变了对外行为则记 `changed` |
| `revert` | 视情况 | `removed` 或 `fixed` | 撤销新增功能→`removed`；撤销某次修复（回归）→`fixed`；其余不记录 |
| `docs` | 不记录 | — | 纯文档，无运行行为变化 |
| `style` | 不记录 | — | 纯格式化，不影响逻辑 |
| `test` | 不记录 | — | 不改变用户可见行为 |
| `build` / `ci` | 不记录 | — | 构建系统与 CI 内部变动 |
| `chore` | 不记录 | — | 辅助工具变动 |
| `init` | 不记录 | — | 项目初始化不进入发布历史 |

补充说明：

- **安全修复**：`fix` 涉及安全漏洞时记 `security`（不再记 `fixed`）。
- **废弃（deprecated）**：以 `feat` 或 `chore` 提交的「弃用某能力」提示，记 `deprecated`，通常伴随 `breaking=true`。
- **破坏性变更**：提交中带 `!` 或 `BREAKING CHANGE:` 的，对应条目必须 `breaking=true` 并写 `migration`。

### 1.5 撰写规则

- `summary`：**动词开头、一句话、行为视角**，描述「用户能感知到什么变化」，不描述内部实现。
- 不写 commit hash；不记录纯格式化、无行为变化的内部重构。
- `breaking=true` 必须给 `migration`（写明受影响范围与升级指引），否则视为违规。

### 1.6 发布流程

1. 确认当前 `unreleased` 行的 `changes` 已完整（无遗漏、无未批准条目）。
2. **冻结**：将该行 `status` 改为 `released`，补齐 `version`（按 1.7 判定）、`date`（ISO 8601 精确到分钟并带时区偏移）、`semver`。
3. 在文件末尾**追加新的空 unreleased 行**：`{"version":null,"status":"unreleased","changes":[]}`。
4. 更新 `progress.json`：清空 `unreleased`，更新 `latest_released_version`。
5. 本地打 git tag：`git tag v<version>`，并提示协作者执行。

### 1.7 semver 判定

- 任一 `breaking=true` → `major`。
- 无 breaking 但含 `added` → `minor`。
- 仅 `fixed` / `security`（及不破坏的 `changed`）→ `patch`。
- 注意：`removed` 通常视为破坏性变更（→ `major`），除非语义上不破坏现有用户行为。

### 1.8 校验

一行命令（PowerShell 7，Windows 开发环境）：

```powershell
Get-Content CHANGELOG.jsonl | ForEach-Object { $_ | ConvertFrom-Json | Out-Null }; Get-Content -Raw progress.json | ConvertFrom-Json | Out-Null; 'OK'
```

逐行解析 `CHANGELOG.jsonl` 并校验 `progress.json` 为合法 JSON；任一行非法即报错。

### 1.9 完整示例

未发布行（真实文件中的单行 JSON）：

```
{"version":null,"status":"unreleased","changes":[{"type":"added","scope":"retriever","summary":"为混合检索新增 TTL LRU 缓存","breaking":false,"migration":null}]}
```

已发布行：

```
{"version":"0.1.0","status":"released","date":"2026-09-10T14:30+08:00","semver":"minor","changes":[{"type":"added","scope":"retriever","summary":"为混合检索新增 TTL LRU 缓存","breaking":false,"migration":null},{"type":"changed","scope":"server","summary":"API 路由改为 APIRouter 分组挂载","breaking":true,"migration":"将客户端路径前缀由 /search 迁移至 /api/search"}]}
```

---

## 二、progress.json（热数据）

### 2.1 定位

- **当前状态快照**：每次开发前必读，提供「我现在在哪、刚做了什么、接下来做什么」。
- **覆盖写**：体量恒定，必须保持精简（建议单文件不超过 200 行）。
- 不记录完整历史、不写 commit hash——历史交给 `CHANGELOG.jsonl` 与 git。

### 2.2 schema

| 字段 | 类型 | 说明 |
|---|---|---|
| `updated` | string | 最近更新时间，ISO 8601 精确到分钟并带时区偏移（如 `2026-09-10T14:30+08:00`） |
| `latest_released_version` | string/null | 最近一次发布版本，未发布过为 null |
| `unreleased` | array | 当前未发布变更的摘要数组，**条目字段与 CHANGELOG.jsonl 的 changes 对齐**（type/scope/summary/breaking/migration） |
| `in_progress` | object/null | 进行中任务，形如 `{"task":"...","note":"..."}`，无任务为 null |
| `next_steps` | array | 下一步计划（字符串数组） |
| `known_issues` | array | 已知问题（字符串数组） |
| `context` | string | 必要的短期上下文，可随开发演进更新 |

### 2.3 更新时机

- **开始一个任务**：更新 `in_progress`。
- **完成一次变更（准备提交）**：向 `unreleased` 追加摘要，同步更新 `next_steps`、`known_issues`。
- **发布**：清空 `unreleased`，更新 `latest_released_version`，`in_progress` 若无任务置 null。

### 2.4 与 CHANGELOG.jsonl 的关系

- `unreleased` 是 CHANGELOG.jsonl 当前 unreleased 行的**摘要视图**。
- 细节与完整历史以 CHANGELOG.jsonl 为准；两者必须保持一致（发布时同步清空）。

### 2.5 原则

- 覆盖写、保持精简、只写「当前需要知道的事」。
- 随项目推进及时清理过期的 `context` 与 `known_issues`，防止无限增长。

### 2.6 完整示例

```json
{
  "updated": "2026-09-10T14:30+08:00",
  "latest_released_version": "0.1.0",
  "unreleased": [
    {"type": "added", "scope": "chunker", "summary": "新增超长章节二次切分与 15% 重叠", "breaking": false, "migration": null}
  ],
  "in_progress": {"task": "实现混合检索 RRF 融合", "note": "BM25 与向量召回权重待定"},
  "next_steps": ["实现 BM25 索引构建", "接入 Chroma 持久化"],
  "known_issues": ["bge-m3 在 Windows CPU 环境首次加载较慢"],
  "context": "处于《计划》阶段 P3：chunker 已完成，进入 retriever 实现"
}
```
