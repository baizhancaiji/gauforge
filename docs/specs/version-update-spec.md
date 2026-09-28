# 版本标识与更新功能 · 需求文档（v2.1 功能更新）

> 状态：需求定稿待评审（本文档只定义需求与改动面，不含实施）。
> 来源：2026-09-28 用户需求原始陈述，经整理与现状核查后落盘。
> 版本定位：M2（2.0.0）发布后的第一个功能更新，含 `added` 条目 → **minor，目标版本 2.1.0**。
> 关联文档：[roadmap.md §2.5](../specs/roadmap.md)（配置治理）、
> [deployment.md](../references/deployment.md)（部署与升级）、
> [openapi.yaml](../api/openapi.yaml) / [sse.md](../api/sse.md)（契约 SSOT）、
> [package_release.sh](../../../scripts/package_release.sh) / [update.sh](../../../scripts/deploy/update.sh)（发行链）。

## 1. 需求总览

五件事，构成一次完整功能更新：

1. **侧栏版本标识**：品牌名下方常驻显示当前版本号，动态取自真实版本；
   导航区与版本行视觉分离。
2. **设置页顶部新增更新卡**（卡内不渲染任何卡片标题，见 §3.2 命名纪律）：
   手动检查更新、手动执行更新，附下载进度显示与代理通道切换；设置页布局
   相应调整。
3. **自动检查更新**：每日/每周/每月/从不四档周期（默认每周），检查时刻为
   凌晨 1:00，周期为设置页可设参数。
4. **异常如实反馈**：网络超时等原因如实呈现给用户，不静默失败。
5. **更新执行形态**：下载（带进度）→ 校验 → 替换 → 重启服务 → 前端强制刷新，
   全程仅在有网络时可用；任务运行期间禁止更新。

## 2. 现状与依赖（设计输入，已实地核查）

### 2.1 版本号现状——四处硬编码/漂移隐患

| 位置 | 现状 | 问题 |
|---|---|---|
| `web/src/main.py:35` | `_VERSION = "0.1.0"` 硬编码，注入 FastAPI 应用元数据（`/openapi.json` 实为回读落盘 yaml，不受它影响） | 与真实版本（2.0.0）脱节 |
| `web/src/routers/system.py:18` | `/system/health` 返回 `"version": "0.1.0"` 硬编码 | 同上 |
| `docs/api/openapi.yaml`（info.version） | `version: 0.1.0` 硬编码——`/openapi.json` 版本号的实际来源 | 同上 |
| 前端 | 无任何版本展示 | 需求 1 无从谈起 |

真实版本的既有事实来源：

- **部署环境**：部署目录 `VERSION` 文件（`package_release.sh` 打包时写入 tag，
  如 `v2.0.0`），`update.sh` 升级时随包覆盖。
- **源码环境**：git 裸 `v` 前缀 tag（`v0.1.0`/`v1.0.0`/`v2.0.0`）；
  `CHANGELOG.jsonl` 最新 `released` 行为兜底口径。

→ 因此本需求第一块基石是**版本单一事实来源**：`config` 层新增
`APP_VERSION` 解析（部署目录 `VERSION` 文件 → git tag → CHANGELOG 兜底），
`main.py`/`system.py` 硬编码退役改为引用。前端版本行与后续所有版本比较
都消费这一个来源。

### 2.2 更新通道现状——release 附件链已具备

- 发行包附件固定名 `gauforge-deploy-linux-x64.tar.gz`（+`.sha256`、`VERSION`），
  经 `https://github.com/baizhancaiji/gauforge/releases/latest/download/<附件>`
  直取最新 release，**不含版本号、免 GitHub API**。
- `update.sh` 已实现：代理选择（`--proxy` 走 `https://v4.gh-proxy.org/` /
  `--no-proxy` 直连，持久化到部署目录 `.update-proxy`）→ 下载 → sha256 校验
  → 解压覆盖（不触碰 `.venv`/`.update-proxy`）→ `uv pip` 差量刷依赖 →
  **提示手动重启**（最后一步未自动化，正是本需求补齐的缺口）。
- `update.sh --check` 即"探测最新版本"的现成口径（拉 `VERSION` 附件比对）。

### 2.3 其他依赖事实

- **Python 依赖零新增**：`httpx==0.28.1`（流式下载/超时控制）、
  `packaging==26.3`（版本比较）已在 `requirements.txt`。
- **运行中任务判定**：`store.executions_repo.list_by_state("running")`
  为现有接口（`services/snapshot.py` 同口径消费），守卫判断直接复用。
- **SSE 基础设施**：broker/心跳/Last-Event-ID 重放/服务端重启后
  `system.snapshot(server_restarted=true)` 全量重建均已就绪（sse.md §4/§5/§6），
  下载进度推送与新事件注册有现成模式可循。
- **前端视口纪律**：`app-frame` 100vh 锁定、body 无全局滚动条（1.x 验收
  修正已定稿）；设置页表单型限宽 880px。更新卡加入后须继续遵守
  （§3.7 布局预算）。
- **设置参数机制**：运行级参数白名单、range 校验、`settings.updated`
  多标签页同步均已就绪；但现有校验只支持 `integer/number` 的 min/max，
  **枚举型 string 校验是机制缺口**（`update_check_interval` 需要，见 §6.1）。
- **重启语义**：`lifespan` 关停不杀 HQ 进程，重启对账机制已有（roadmap §5）；
  g16web 自身重启后待执行席位从盘恢复，派发自动续跑——因此**更新守卫只需
  拦截 running 任务**（见 §3.4 口径）。

## 3. 行为规格

### 3.1 版本标识（侧栏）

- 品牌区「Gaussian 16 / 管理工作台」两行下方新增版本行：`v2.0.0` 形态
  （mono、`--text-faint` 弱化色，装饰从简），版本号来自 §2.1 单一事实来源
  （经后端接口下发，前端不自行探测 git/文件）。
- 导航区整体下移，与版本行拉开间距（加大间距或细分隔线，取其一，
  实施时按视觉定稿），保证版本行不与「候选」等导航项视觉粘连。
- 版本数据入口：复用 `/system/health` 的 `version` 字段（改为真实版本后，
  避免新增只读端点）。
- 版本行尾 accent 小圆点（D5）：`phase=available`（发现新版本）时点亮，
  更新完成（`done`）或下次检查无更新（`up_to_date`）时熄灭；与品牌区现有
  HQ 连接状态点（`brand-dot`）以位置与尺寸区分，不新增颜色语义。
- **版本行本身可点击**：点击（热区含小圆点）跳转至设置页更新卡，无论是否
  发现新版本均可跳转，构成 `available` 时的引导路径；交互暗示以 hover
  微反馈与 `focus-visible` 焦点样式为限，**不得呈现导航项形态**（无选中态、
  不与导航项共享样式，与上方"导航区视觉分离"原则并行不悖）。

### 3.2 更新卡（设置页顶部）

**命名纪律**：卡片在本文档内部称"更新卡"，**UI 上不渲染任何卡片标题**——
不出现"更新卡"/"更新"三字标题，卡片身份由内容自明。

**布局**：

- 与下方设置卡同宽（880px 容器内等宽），高度自适应；
- 左侧为内容显示区，右侧按钮区右对齐，「检查更新」「立即更新」两按钮同行；
- 卡内含代理通道切换（直连 / 默认代理 / 自定义 URL），读写部署目录
  `.update-proxy`（与 `update.sh` 同一份配置），保存即时生效（见 §3.4）；
- 下载中显示条形进度条：进度条**左侧显示新版本号、右侧显示实时下载速度**；
- 下载完成后校验/替换/重启阶段**静默进行**，不展示中间步骤细节，
  内容区显示阶段性状态（如"服务重启中 …"）即可。

**显示状态机**（左内容区随状态切换）：

| 状态 | 对应 phase（§4.2） | 显示内容 |
|---|---|---|
| 未检查 | `idle` | 当前版本号（如 `当前版本 v2.0.0`） |
| 检查中 | `checking` | `检查更新中 …` |
| 无更新 | `up_to_date` | `当前版本已最新！` |
| 有更新 | `available` | `发现新版本 vx.y.z！查看更新说明`（"更新说明"为超链接，指向 `https://github.com/baizhancaiji/gauforge/releases/tag/vx.y.z`，新标签页打开；链接不落在卡内正文以外任何位置） |
| 下载中 | `downloading` | 进度条（左：新版本号，右：实时速度，如 `1.2 MB/s`） |
| 校验/替换 → 重启中 | `installing` / `restarting`（同显） | `服务重启中 …`（静默等待） |
| 更新完成 | `done` | 新版本号 + `更新完成` |
| 失败 | `failed` | 如实展示原因（§3.5 文案表） |

页面刷新/重进设置页时恢复最近一次检查与更新流程状态（服务端保留状态，
见 §4 API 草案 `GET /update/status`），不强制重查；跨服务重启的恢复依赖
部署目录两份伴生文件——`update-state`（apply 流程标记）与 `.update-check`
（最近检查结果），规则均见 §3.4。

### 3.3 检查更新（手动）

- 点击「检查更新」→ 后端探测远端最新 release → 按上表回显。
- 比较口径：语义化版本逐段比较（`v` 前缀剥离），仅严格更大算"有更新"。
- 探测目标与 `update.sh --check` 同源：`releases/latest/download/VERSION`
  附件（免 GitHub API 限流、可经 gh-proxy 代理）；发布页链接按 tag 拼接。
  （API 方案为备选，见 §5 D2。）
- 超时与错误处理见 §3.5。

### 3.4 立即更新（手动执行）

**前置守卫**（不满足即拒绝，不动任何文件）：

1. **任务运行守卫**：存在 `running` 状态执行时拒绝，提示
   **「为保证运行稳定性，任务执行期间禁止更新」**。判定口径=仅 running
   （待执行席位中的 staged 任务随重启对账自然恢复，不阻止更新——
   与 roadmap §5 重启语义一致）。
2. **重复请求守卫**：更新流程进行中时拒绝重复触发。
3. **形态守卫**：仅干净部署包安装形态（部署目录存在 `VERSION` +
   `bin/hq` 布局）可用；源码开发形态提示走 git 更新，不执行。

**执行流程**（有更新时）：

```
检查最新版本 ──与当前一致──▶ 提示「当前版本已最新」（不执行，200 幂等）
      │ 有更新（同步预检：拉 `.sha256` 验下载通道，失败 502 拒绝、不进异步）
      ▼
流式下载 release 包（SSE 推送进度：版本号/百分比/实时速度）
      ▼
sha256 校验（失败即中止并如实报错，现有版本分毫未动）
      ▼
静默替换 + 差量刷依赖 + 重启服务（detached 脚本接管，见 §5 D6）
      ▼
前端自动感知版本变化，强制刷新（见下）
```

**前端强制刷新机制**：下载/安装阶段 SSE 连接保持（消费 `update.progress` /
`update.phase`）；进入 `restarting` 阶段（服务进程退出）后 SSE 断开，前端
此时转入轮询 `/system/health`（500ms 级、超时上限 120s）；服务恢复后立即
查询 `GET /update/status` 区分三分支——`version` 已变化 → `location.reload()`
强制刷新加载新前端产物；`phase=failed`（更新中断）→ 如实展示失败原因、
不误报超时；两者均非 → 继续轮询至超时。超时未恢复则如实报错提示手动重启
（文案：`服务重启超时，请手动重启后刷新`）。多标签页经同一机制自然跟随
（SSE 广播不区分订阅方）。

**更新状态落盘标记**（部署目录 `update-state` 文件，跨服务重启的流程
状态恢复依据）：

- **写入**：`apply` 进入下载时创建，内容 `{target_version, phase,
  started_at}`，phase 翻转时同步更新；`self_update.sh` 完成替换与差量刷
  依赖、重启服务前置为 `phase=done`（见 §6.3）。
- **恢复**：服务启动时 `services/update.py` 读取——标记为 `done` 且
  `target_version` 与当前 `APP_VERSION` 一致 → 对外恢复 `phase=done`
  （前端显示「更新完成」）；标记存在但版本未达 `target_version`（更新
  中断）→ 恢复 `phase=failed` 并如实提示，以 CLI `update.sh` 重跑为恢复
  路径（§8）。
- **清理**：`done` / `failed` 恢复状态被 `GET /update/status` 消费后删除；
  下一次成功检查时兜底清理。

**最近检查结果伴生文件**（部署目录 `.update-check`，`GET /update/status`
的 `latest_version` / `last_checked_at` 跨服务重启恢复与 §3.6 补查窗口
判定的依据）：

- **写入**：每次检查结束（成功或失败）覆盖写 `checked_at`；检查成功时
  同时更新 `latest_version` 与 `had_update`，失败时二者保留上一份成功值
  （可为 null）。
- **恢复/判定**：服务启动时 `services/update.py` 读取，供 `GET
  /update/status` 恢复与启动补查判定（§3.6）。
- **清理**：不清理（常驻最近检查快照），与 `update-state` 的消费后删除
  规则不同。

**代理通道**：检查与下载走部署目录 `.update-proxy` 的通道选择（与
`update.sh` 同一份配置）；设置页更新卡内提供通道切换（直连 / 默认代理 /
自定义 URL），保存即写回 `.update-proxy`、即时生效（D4 决策：上设置页）。
自定义值须为合法 URL，非法按既有 `INVALID_REQUEST`（400）拒绝，不新增
错误码。

### 3.5 异常反馈（如实呈现，不静默）

| 场景 | 反馈文案 |
|---|---|
| 连接超时 | `连接超时，请检查网络` |
| DNS/连接失败 | `无法连接更新服务器，请检查网络` |
| HTTP 非 200 | `更新服务器返回异常（HTTP xxx）` |
| sha256 校验失败 | `更新包校验失败，已中止（现有版本未受影响）` |
| 任务运行中 | `为保证运行稳定性，任务执行期间禁止更新` |
| 下载中断（网络断） | 如实展示中断原因，已下载内容丢弃重试 |
| 源码形态 | `当前为源码运行模式，请通过 git 更新` |

本表与 §3.2 状态文案同为逐字验收基准（§7.2），中文标点一律全角。
超时阈值与 `update.sh` 一致（连接 15s）；错误经统一错误结构返回，
错误码登记进契约错误码全集（§4）。

### 3.6 自动检查更新

- 新增**运行级参数** `update_check_interval`，枚举：`daily` / `weekly` /
  `monthly` / `never`（默认 `weekly`，D1 决策含"从不"档），设置页可改，
  保存即时生效（30s 内，实现方式不限）。
- 检查时刻锚定**本地时间凌晨 1:00**：每日=每天 01:00；每周=每周一 01:00；
  每月=每月 1 日 01:00；`never` 档不排程。
- **「从不」档**：定时器不排程、启动补查跳过，仅保留手动检查
  （「检查更新」按钮照常可用）。
- **错过补查**：单机 WSL2 场景服务未必在 01:00 存活——服务启动时若本次
  周期窗口尚未检查过（判据：`.update-check` 的 `checked_at` 落在当前周期
  窗口起点之后即视为已查过，见 §3.4），则启动后短时间内（≤5 分钟）补查
  一次，避免"从不开机到点"的周期形同虚设。
- 自动检查**只发现、不安装**：发现新版本即更新最近检查状态（更新卡回显
  "发现新版本 …"），是否执行更新永远由用户手动触发。
- 自动检查结果经 SSE 事件广播（§4），供后续全局提示扩展（见 §5 D5）。

### 3.7 设置页布局调整（配合更新卡）

- 启动级参数两项（工作区根目录、监听地址）由上下排列改为**水平一行两列**。
- 更新卡插入设置页顶部后，启动级卡与运行级卡顺延下移（自然文档流，
  无需额外位移量）；**总高度纪律**：更新卡 + 启动级卡（含标题）+
  运行级卡 + 保存按钮在目标视口（1080p）内**一屏完整可见**，不得超出
  可视高度——间距按此预算收敛；极小视口兜底：设置页内容容器允许局部滚动
  （符合全站视口纪律的"局部滚动"模式），但 1080p 下不得出现滚动条。
- 更新卡与下方卡片间距、卡片内边距沿用现有 `--space-*` 令牌，不新增装饰。

## 4. API 与事件草案（契约变更预告，实施前须先走契约 diff）

> 按 roadmap §1 原则 3（契约先行）与 §2.6 三层规则：以下为意向草案，
> 实施第一步是 openapi.yaml / sse.md 文档 diff 定稿，前后端同吃契约。

### 4.1 REST（新增 `update` tag，4 端点）

| 端点 | 语义 | 关键响应 |
|---|---|---|
| `GET /update/status` | 最近一次检查结果 + 当前更新流程状态（页面恢复用；跨服务重启经 `update-state` / `.update-check` 标记恢复，见 §3.4） | `{current_version, latest_version?, last_checked_at?, phase, message?, proxy, supported}`；`supported`=当前形态是否支持 WebUI 更新（源码形态 false，前端按钮置灰依据），`proxy` 读自 `.update-proxy` |
| `POST /update/check` | 触发一次检查（同步返回） | 200 状态对象；网络失败 502 `UPDATE_CHECK_FAILED`（上游不可达语义），文案按 §3.5 |
| `POST /update/apply` | 触发更新（异步） | 202 受理；409 `UPDATE_BLOCKED_RUNNING`（任务运行中）/ 409 `UPDATE_IN_PROGRESS`（重复触发）/ 409 `UPDATE_UNSUPPORTED`（源码形态）；已最新返回 200 + `phase=up_to_date`（幂等，见 §5 D3）；同步预检失败 502 `UPDATE_CHECK_FAILED`（探测不到远端）/ `UPDATE_DOWNLOAD_FAILED`（拉 `.sha256` 验下载通道失败），预检失败不进异步 |
| `PUT /update/proxy` | 设置代理通道（D4：写部署目录 `.update-proxy`，即时生效；`{proxy: string \| null}`，null=直连） | 200 状态对象；自定义值非法 400 `INVALID_REQUEST`（既有码） |

新增错误码（登记 openapi.yaml 文件头错误码全集，19 码 → 24 码，SSOT
登记机制不变）：
`UPDATE_BLOCKED_RUNNING`、`UPDATE_IN_PROGRESS`、`UPDATE_UNSUPPORTED`、
`UPDATE_CHECK_FAILED`、`UPDATE_DOWNLOAD_FAILED`。

`SettingsResponse` 运行级参数表扩一项（`update_check_interval`，
string 四值枚举 `daily/weekly/monthly/never`），`config.RUNTIME_SETTINGS`
与契约逐项对齐的既有纪律不变（`RUNTIME_DEFAULTS` 同步补默认值）。
代理通道不进运行级参数表：经 `PUT /update/proxy` 走部署目录
`.update-proxy` 文件，与 `update.sh` 共用配置（D4）。

### 4.2 SSE（事件全集 13 类 → 15 类）

| 事件 | 触发 | 载荷 | 频率/节流 |
|---|---|---|---|
| `update.progress` | 更新包下载中 | `version`、`percent`、`speed_bps`、`ts` | 下载期间 ~500ms/条（合并窗口取最新） |
| `update.phase` | 更新流程阶段翻转（含自动检查发现新版本） | `phase: idle/checking/available/downloading/installing/restarting/done/failed/up_to_date`（与 §3.2 显示状态一一对应，`available` 即「有更新」）、`version?`、`message?`、`ts` | 翻转即推 |

`update.progress` 合并窗口取 **500ms**（沿用 `execution.progress`「窗口内
多条推最新」的先例，窗口收紧至 500ms）；sse.md §3 推送时机表同步补行。

## 5. 决策点

| # | 决策点 | 决策 |
|---|---|---|
| D1 | `update_check_interval` 默认值；需求仅列三档，是否需要"从不"档 | 默认 `weekly`；加"从不"档|
| D2 | 探测通道：VERSION 附件 vs GitHub API `releases/latest` | **VERSION 附件**（免 API 限流、gh-proxy 可代理、与 update.sh 同源；代价是拿不到 notes 正文——需求只要求链接，可拼接） |
| D3 | `apply` 时已是最新：200 幂等返回 vs 409 错误码 | **200 + `phase=up_to_date`**（"无更新"不是错误） |
| D4 | 代理通道是否上设置页 | **上**（更新卡内切换，读写部署目录 `.update-proxy` 与 `update.sh` 共用，不进 SQLite 运行级参数） |
| D5 | 发现新版本时设置页之外的全局提示（如侧栏版本号旁小圆点） | 版本行旁 accent 小点（低成本、可后续裁撤）|
| D6 | 替换+重启执行体：**入库脚本** `scripts/deploy/self_update.sh`（由后端 detached 调用，固化原启动命令/环境/端口） vs 后端内嵌逻辑 | **入库脚本**（符合"脚本纳入版本管理"纪律；后端只做下载/校验/状态机） |
| D7 | 运行中判定口径：仅 running（staged 不拦） vs running+staged 全拦 | **仅 running**（按需求字面"没有任何任务执行"；staged 随重启对账恢复，roadmap §5） |

## 6. 改动面清单

### 6.1 后端（web/src）

| 文件 | 改动 |
|---|---|
| `config.py` | 版本单一事实来源（`APP_VERSION`：VERSION 文件 → git → CHANGELOG 兜底）；`RUNTIME_DEFAULTS`/`RUNTIME_SETTINGS` 同步增 `update_check_interval`（默认 `weekly`）；更新超时/URL 等默认值 |
| `store/settings_repo.py` | 枚举型 string 参数校验（现有校验仅支持 `integer/number` 的 min/max，机制缺口见 §2.3） |
| `services/update.py` **（新）** | 检查/比较/流式下载（进度回调）/状态机/守卫判断；代理通道读写（`.update-proxy`）；`update-state` 与 `.update-check` 落盘标记写入/启动恢复/清理（§3.4） |
| `routers/update.py` **（新）** | §4.1 四端点 |
| `routers/system.py` | health `version` 改真实版本 |
| `main.py` | `_VERSION` 硬编码退役；注册 update 路由；lifespan 挂自动检查定时任务与 apply 后台任务 |
| `sse.py` / 事件注册处 | 新事件类型登记 |

### 6.2 前端（web/frontend/src）

| 文件 | 改动 |
|---|---|
| `App.vue` | 品牌区版本行 + 导航区下移视觉分离（+D5 小圆点）+ 版本行点击跳转设置页更新卡 |
| `views/SettingsView.vue` | 挂载更新卡于顶部；启动级参数改水平两列；高度预算收敛 |
| `components/UpdateCard.vue` **（新）** | §3.2 状态机/按钮右对齐/进度条/代理通道切换 |
| `stores/events.ts` | 新事件消费 + 服务重启后轮询 health 比对版本触发强制刷新 |
| `api/contract.ts` | 契约生成物再生（既有生成链） |

### 6.3 脚本与发行链

| 文件 | 改动 |
|---|---|
| `scripts/deploy/self_update.sh` **（新，D6）** | 固化原启动上下文（命令/env/端口）→ 等待父进程退出与端口释放（后端 apply 收尾自行退出，脚本不杀进程）→ 覆盖替换（含根脚本自更新，仓库源不动）→ 差量刷依赖 → `update-state` 置 `done`（仅改 phase、保留 target_version，§3.4）→ 按原上下文重启服务 |
| `scripts/package_release.sh` | 入包清单（`scripts/deploy/` 显式列名拷贝行）追加 `self_update.sh`；VERSION 附件/固定名附件机制无需改 |
| `scripts/deploy/update.sh` | 保留为 CLI 兜底路径，不回归 |

### 6.4 契约与文档

| 文件 | 改动 |
|---|---|
| `docs/api/openapi.yaml` | §4.1 端点/错误码/参数表 diff；`info.version` 改真实版本（§2.1 所列 `/openapi.json` 版本实际来源） |
| `docs/api/sse.md` | §4.2 两事件 + 推送时机表 |
| `docs/api/mapping.md` | 设置页/更新卡与端点映射行补齐；收官「端点覆盖对照」段 33→37（补 `update(4)`） |
| `docs/specs/roadmap.md` | §2.5 配置治理登记 `update_check_interval`（运行级）与 `G16WEB_UPDATE_BASE`（启动级，更新 base URL，兼端到端演练口）；功能更新定位表述 |
| `docs/references/deployment.md` | 升级章节补 WebUI 更新入口与 `update.sh` 的关系（WebUI 为主、CLI 兜底）、`update-state`/`.update-check`/`update.log` 排障说明与根脚本自更新（仅 WebUI 路径）行为差异注明 |
| `CHANGELOG.jsonl` / `progress.json` | unreleased 同步（文档与实现分批登记） |

### 6.5 测试（web/tests）

| 文件 | 覆盖 |
|---|---|
| `test_update_check.py` **（新）** | 版本比较边界；探测 mock（正常/超时/非 200）；错误文案口径 |
| `test_update_apply.py` **（新）** | 守卫矩阵（running/重复/源码形态）；状态机流转；进度事件节流 |
| `test_settings*.py` | 新参数枚举校验与即时生效 |
| `test_contract_rest.py` / `test_contract_sse.py` | 新端点与新事件零漂移 |
| 前端 | 手动冒烟清单（仓库已决策不引入 vitest，roadmap §7.5），补更新卡走查项 |

## 7. 验收标准草案（实施前细化）

1. 侧栏版本号与 `GET /system/health` `version` 一致，随部署版本变化；
   点击版本行跳转至设置页更新卡。
2. 检查更新三分支（已最新/有新版本/无网络）文案与链接逐字符合 §3.2/§3.5。
3. 立即更新：running 存在时 409 + 指定文案；无任务时全流程走通——
   进度条实时（左版本号/右速度）、下载后静默、服务自动重启、前端自动
   强刷到新版本并恢复显示「更新完成」（`update-state` 标记消费后清理），
   全程不手工触碰终端。
4. 自动检查：四档周期设置保存即时生效；到点触发；错过启动补查
   （`never` 档不排程不补查）；只发现不安装。
5. 布局：1080p 下设置页（含更新卡与保存按钮）一屏完整可见、无滚动条；
   更新卡与设置卡等宽、按钮右对齐、卡内无"更新卡"标题字样。
6. 闸门全绿：`uv run pytest`、`validate_progress.py`、契约零漂移测试、
   `check_tokens.py` / `check_contrast.py`（涉前端视觉）、
   `gen_changelog_md.py --check`。

## 8. 风险与边界

| 风险/边界 | 处置 |
|---|---|
| 自我重启可靠性（nohup/环境变量/端口取 SQLite 设置） | 后端 apply 收尾自行退出；detached 脚本先固化原启动上下文（命令、env、端口）、再等待父进程退出与端口释放后接管（不杀进程）；重启后端口仍从 SQLite 读（`resolved_listen_port`） |
| 替换中断（断电/断网）导致部署目录半新半旧 | 下载与校验全部在临时目录完成，校验通过才动现有文件；替换窗口极短；损坏场景以 CLI `update.sh` 重跑为恢复路径（文档写明） |
| 源码开发形态误触发更新 | §3.4 形态守卫 409，按钮置灰 + 文案提示（文案即 §3.5 定稿「当前为源码运行模式，请通过 git 更新」） |
| GitHub 附件限流/网络波动 | 附件直取无 API 限流；下载带重试与 sha256 兜底；代理通道沿用 `.update-proxy` |
| 多标签页并发触发更新 | 后端 `UPDATE_IN_PROGRESS` 全局互斥；非发起页经 SSE 感知同一状态机 |
| 更新包与数据版本错配 | 工作区（`G16WEB_HOME`）与部署目录分离的既有架构天然隔离；迁移类变更由 release notes 承载、更新卡链接引导阅读 |

## 9. 实施顺序建议（概要，细化另立实施计划）

文档（契约 diff + roadmap/deployment）→ 测试（守卫矩阵/比较器/契约零漂移）
→ 后端（版本 SSOT → update 服务/路由 → 自动检查定时）→ 脚本（self_update.sh）
→ 前端（版本行 → 更新卡 → 布局调整 → 强刷机制）→ 冒烟与验收留痕 →
进度同步。每步遵守"单次提交只做一类变更"。
