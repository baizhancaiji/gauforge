# 版本标识与更新功能 · 实施计划（v2.1.0）

> 状态：实施计划定稿（依据 [version-update-spec.md](../specs/version-update-spec.md)
> 需求文档 v 定稿版，D1–D7 决策全部锁定）。
> 定位：M2（2.0.0）后第一个功能更新，含 `added` → **minor，目标版本 2.1.0**。
> 排期口径：单人实施，任务粒度=一个可审查提交；规模标记 S（≤半天）/ M（1 天）/ L（2 天+）。
> 实施顺序遵需求 §9：文档 → 测试 → 后端 → 脚本 → 前端 → 冒烟验收 → 进度同步，
> 每提交单类变更、可构建可回滚（AGENTS §5.1）。

## 1. 需求分析

### 1.1 功能范围（需求 §1 五件事 → 实施视角）

| # | 功能 | 实施视角拆解 | 需求锚点 |
|---|---|---|---|
| F1 | 侧栏版本标识 | 版本单一事实来源 `APP_VERSION`（后端）→ health 下发 → 前端品牌区版本行 + D5 圆点 + 点击跳转 | §3.1 |
| F2 | 设置页更新卡 | 新组件 UpdateCard（八态显示状态机 + 进度条 + 代理切换）+ 设置页布局调整（启动级两列、一屏预算） | §3.2/§3.7 |
| F3 | 自动检查 | 运行级参数 `update_check_interval` 四档枚举 + 凌晨 1:00 锚定调度 + 错过补查 + 只发现不安装 | §3.6 |
| F4 | 异常如实反馈 | 七类场景结构化错误与逐字文案；全角标点 | §3.5 |
| F5 | 更新执行 | 检查→流式下载（SSE 进度）→sha256→detached `self_update.sh` 替换/刷依赖/重启→前端轮询强刷；三守卫；`update-state`/`.update-check` 落盘恢复 | §3.3/§3.4 |

**明确不做**（边界，防蔓延）：

- 不做全局公告/toast 类新版本提示（D5 仅侧栏圆点，可后续裁撤）；
- 不做更新说明正文拉取与渲染（只拼 release tag 链接，D2）；
- 不做 staged 任务拦截（D7：仅 running）、不做多语言文案；
- 不动 `update.sh` 既有行为（CLI 兜底路径，§6.3"保留不回归"）；
- 不新增 Python/npm 依赖（httpx 0.28.1 / packaging 26.3 已在 requirements.txt，实测确认）。

### 1.2 技术要求与关键约束

1. **版本 SSOT 解析链**（F1 基石）：`config.APP_VERSION` 三级解析——部署目录
   `VERSION` 文件 → `git describe --tags`（源码形态）→ `CHANGELOG.jsonl` 最新
   `released` 行兜底。解析在进程启动时一次完成（模块级常量，不做运行时探测）。
   `main.py:35` `_VERSION`、`routers/system.py:18` 硬编码退役改引用。**对外
   形态定稿**：`APP_VERSION` 带 `v` 前缀（与部署 VERSION 文件、git tag 同
   形态，如 `v2.1.0`），health/侧栏/更新卡直接渲染；版本比较与 `info.version`
   派生一律用剥离 `v` 后的裸版本（如 `2.1.0`），剥离集中在
   `resolve_version()` 单点，消费方不得各自再剥。
2. **防再漂移**：`main.py` `_openapi_override` 回读 yaml 后动态覆盖
   `info.version`（= `APP_VERSION` 剥离 `v` 的裸版本；yaml 静态值保留为
   离线参考，不再是对外版本来源）；`docs/api/openapi.yaml` 的 `info.version`
   本次手工同步改 `2.1.0`。`test_openapi_ssot.py` 豁免方案定稿为：**剔除
   `info.version` 字段后其余字段严格比对（零豁免）** + 独立断言
   「`/openapi.json` 的 `info.version` == `APP_VERSION` 剥 `v` 裸版本」，
   两段各自守护。不得采用「两侧剥离 `v` 后比对」——源码形态 `git describe`
   输出带 `-N-g<hash>` 后缀，与 yaml 静态值必然不等、pytest 必红。
   不回退"发布流程手工同步"（R7 同步收口）。
3. **契约先行**（roadmap §1 原则 3）：REST 四端点 + 5 新错误码（19→24）+
   SSE 两事件（13→15）+ `SettingItem.range` 增 `enum` 结构（string 数组、
   nullable，枚举型参数载体——现契约 range 仅 min/max，缺口见 §1.2-4）
   先落 openapi.yaml / sse.md 文档 diff，前后端同吃契约；前端
   `npm run gen:types` 再生 contract.ts（`web/frontend/package.json`
   gen:types 生成链已确认）。
4. **机制缺口补齐**：`store/settings_repo.py` `_value_error` 现仅支持
   integer/number 的 min/max（实测确认 string range=None 直通）。补枚举校验：
   `range` 扩展 `{"enum": [...]}` 形态并**在 enum 分支先于 min/max 判断**
   （string 值不得落入 `float(value)` 转换），枚举不命中归 **`type`** reason
   （不扩契约词表二 `unknown_setting/readonly/range/type`，值域不符语义归
   类型错，前端既有提示文案直接复用）；契约侧 `SettingItem.range` 同步增
   `enum` 结构（A1，见 §1.2-3），前端由生成类型渲染四选下拉。
5. **调度实现形态**：自动检查不搞定时器重排——后台协程每 30s 醒来读最新
   设置值、计算下次触发点（本地时间 01:00 锚定：daily=每天 / weekly=周一 /
   monthly=每月 1 日 / never=不排程），到点触发。设置保存即时生效天然满足
   （下次醒来即见新值，**验收口径=30s 内生效**，与需求「重排定时器」的
   表述差异已收敛）；凌晨精度要求低，轮询粒度足够。
6. **跨重启状态恢复**：部署目录两份伴生文件——`update-state`（apply 流程
   标记：JSON，`{target_version, phase, started_at}`，phase 翻转重写；需求
   §3.4 定稿规则）+ `.update-check`（最近检查结果
   `{latest_version, checked_at, had_update}`，供 `GET /update/status` 跨重启
   恢复与自动检查补查判定；**每次检查结束覆盖写 `checked_at`，成功时同时
   更新 `latest_version`/`had_update`、失败保留上一份成功值**，规则已回登
   需求 §3.4）。**补查按需求字面窗口判定**：`checked_at` 落在当前周期窗口
   起点（本地时间：daily=今日 01:00 / weekly=本周一 01:00 / monthly=本月
   1 日 01:00）之后即"本窗口已查过"，启动后不补查；否则启动后 ≤5min 补查
   一次；`never` 档不排程不补查。窗口起点以标准库 `datetime` 计算，月初/
   周一跨日边界进单测（见 R9）。
7. **自我重启编排**（D6 定稿）：后端 apply 只负责下载+校验+写
   `update-state(phase=installing)`+detached 拉起 `self_update.sh`
   （`subprocess.Popen` 列表参数、`start_new_session=True`、stdout/stderr
   追加重定向部署目录 `update.log`）+ 发 `update.phase(restarting)` +
   `os.kill(os.getpid(), SIGTERM)` 优雅自退（lifespan 收尾不杀 HQ，既有语义）。
   脚本固化原启动上下文：cwd=部署目录、命令 `uv run python -m web.src.main`、
   env 经 `Popen` 继承原进程环境（脚本内直接沿用、不猜测默认值，`G16WEB_HOME`
   等启动级变量随之保持）、端口经 SQLite `resolved_listen_port()` 读取 →
   等待父进程退出（主判据 `kill -0 $PPID`）与端口释放（辅助探测，上限 60s；
   探测端口取 SQLite 现值，「设置改端口未重启」边界以父进程退出判据兜底且
   脚本内注明）（**不杀进程**）→ 复用 update.sh 的覆盖/差量刷依赖逻辑（含
   根脚本自更新，见批次 E1）→ `update-state` 置 `phase=done`（JSON，脚本经
   `.venv/bin/python -c` 改写、**仅改 `phase` 字段、保留
   `target_version`/`started_at`**，不依赖 jq）→ 按原上下文重启（nohup 形态，
   同 install.sh 提示的启动命令）。
8. **演练通道**：新增启动级环境变量 `G16WEB_UPDATE_BASE`（默认
   `https://github.com/baizhancaiji/gauforge`），检查/下载的 base URL 从
   config 读——既是端到端演练口（指向本地 http server 伪装 release），也让
   测试不触真实网络。代理拼接规则与 update.sh 一致：`{proxy%/}/{base}/…`。
9. **前端视口纪律**：`app-frame` 100vh 锁定不变；设置页更新卡后 1080p 一屏
   完整可见（无滚动条），极小视口局部滚动兜底；间距用 `--space-*` 令牌，
   新增颜色/令牌须过 `check_tokens.py` / `check_contrast.py`。
10. **跨平台纪律**：路径 `pathlib`、子进程列表参数无 shell、文本读写
    `encoding="utf-8"`、`.sh` LF（AGENTS §十，全程适用）。

### 1.3 验收标准（需求 §7 细化为可执行判据）

| # | 判据 | 验证方式 |
|---|---|---|
| A1 | 侧栏版本号 === `GET /system/health` `version` === 部署 `VERSION` 文件（`v` 前缀保留形态 `v2.1.0`）；点击版本行（热区含圆点）路由跳转设置页 | e2e 演练 + 手动冒烟 |
| A2 | 检查三分支文案逐字符合 §3.2/§3.5（全角标点）；"更新说明"链接=`releases/tag/v<x.y.z>` 新标签页 | 单测逐字断言 + 冒烟 |
| A3 | apply 三守卫：running→409 `UPDATE_BLOCKED_RUNNING`+指定文案；进行中→409 `UPDATE_IN_PROGRESS`；源码形态→409 `UPDATE_UNSUPPORTED`+按钮置灰 | 守卫矩阵单测 + 冒烟 |
| A4 | 全流程：进度条实时（左版本号/右速度）、校验后静默、服务自动重启、前端强刷后显示「更新完成」且 `update-state` 已清理，全程不碰终端 | 本地演练 e2e（§4.5） |
| A5 | 自动检查：四档保存即时生效（轮询 30s 内生效）；到点触发；补查按窗口判定（窗口未查过时启动 ≤5min 补查、已查过不重复请求）；`never` 不排程不补查；只发现不安装（无 apply 动作） | 单测（时钟注入）+ 冒烟 |
| A6 | 布局：1080p 设置页一屏无滚动条；更新卡与设置卡等宽 880px、按钮右对齐、卡内无「更新」标题字样 | 截图走查 + 冒烟清单 |
| A7 | 闸门全绿：`uv run pytest`（记录通过数，hq 产物在位时）、`validate_progress.py`、`check_tokens.py`、`check_contrast.py`、`gen_changelog_md.py --check`、`npm run gen:types` 再生零 diff | 逐条跑命令留痕 |
| A8 | 异常七场景（§3.5 表）每条文案逐字断言；超时阈值 connect 15s（与 update.sh 一致）、read 30s | 单测（httpx MockTransport 注入异常） |

## 2. 任务拆解

### 2.1 批次总览与提交序列

17 个提交、7 个批次；`文档 → 测试 → 实现`在每个功能点内闭环（测试与实现
同提交保持绿，避免红提交破坏闸门"可运行"要求；与需求 §9「测试先行」的
差异在于独立测试提交会破坏「每个提交可构建可运行」闸门，测试设计仍在
实现前完成）：

```text
A 契约文档(3) → B 版本SSOT(2) → C/D 后端(6, 测试随实现) → E 脚本(2)
→ F 前端(3) → G 冒烟与进度(1+)
```

（G1 为演练任务、无代码提交，记录并入 G2；合计 17 个提交。）

### 批次 A：契约与文档 diff（文档类提交）

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| A1 | openapi.yaml diff：新增 `update` tag 四端点（GET /update/status 字段全集 `{current_version, latest_version?, last_checked_at?, phase, message?, proxy, supported}`、POST /update/check 200/502、POST /update/apply 200/202/409/502 语义、PUT /update/proxy）；`SettingItem.range` 增 `enum`（string 数组、nullable，枚举参数载体）；错误码全集 19→24（`UPDATE_BLOCKED_RUNNING`/`UPDATE_IN_PROGRESS`/`UPDATE_UNSUPPORTED`/`UPDATE_CHECK_FAILED`/`UPDATE_DOWNLOAD_FAILED`，登记文件头注释）；`SettingsResponse` 运行级参数表 + `update_check_interval` 四值枚举；`info.version: 2.1.0` | 契约 SSOT 先行；apply 幂等分支（已最新 200+up_to_date，D3）与同步预检失败分支（探测 VERSION 失败 → 502 `UPDATE_CHECK_FAILED`；拉 `.sha256` 验下载通道失败 → 502 `UPDATE_DOWNLOAD_FAILED`，均不进异步）写进端点 description；网络类错误码（CHECK/DOWNLOAD_FAILED）HTTP 状态统一定稿 502（上游不可达语义）；status 的 `supported`（源码形态判定，前端置灰依据）与 `proxy`（读自 `.update-proxy`）写进字段说明；**同步预检与 502 状态码为需求未列的计划细化，已回登需求 §3.4/§4.1** | `docs(api): 契约预告更新域四端点五错误码与检查周期枚举参数` | M |
| A2 | sse.md diff：事件全集 13→15（`update.progress` 载荷 version/percent/speed_bps/ts、~500ms 节流；`update.phase` 九相枚举、翻转即推）；§1 事件命名规范域清单（既有域枚举）增 `update`；§3 推送时机表补行（检查完成→update.phase、下载中→update.progress、阶段翻转→update.phase） | 节流口径沿「窗口内多条推最新」先例、**窗口收紧为 500ms**（sse.md 写明，覆盖先例 1s 口径，与需求 §4.2 表格 500ms 对齐） | `docs(api): SSE 契约新增 update.progress 与 update.phase 两事件` | S |
| A3 | mapping.md 补更新卡/版本行→端点映射行 + 收官「端点覆盖对照」段 33→37（补 `update(4)`，无孤儿口径同步）；roadmap §2.5 登记 `update_check_interval`（运行级参数表）与 `G16WEB_UPDATE_BASE`（启动级清单：默认值与演练口用途见 §1.2-8，穷举清单不缺项）及功能更新定位；deployment.md 升级章节补"WebUI 为主、CLI 兜底"关系、`update-state`/`.update-check`/`update.log` 排障说明与「根脚本自更新仅 WebUI 路径（self_update.sh），CLI update.sh 不更新脚本自身」的行为差异注明 | 文档对齐类收尾 | `docs: 更新卡映射与升级链文档补齐（WebUI 主/CLI 兜底）` | S |

### 批次 B：版本单一事实来源（后端基石，F1 数据面）

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| B1 | `config.py` 增 `APP_VERSION` 三级解析（VERSION 文件 → git describe → CHANGELOG.jsonl 最新 released 兜底；模块级常量+`resolve_version()` 函数）；`RUNTIME_DEFAULTS`/`RUNTIME_SETTINGS` 增 `update_check_interval`（string，range `{"enum": [...]}`，默认 weekly，effect=immediate）；`G16WEB_UPDATE_BASE`/超时（connect 15s、read 30s，见 D1）/附件名等更新默认值；**测试**：`test_version_source.py`（新）三级解析优先级与边界（无 VERSION/git 失败/CHANGELOG 兜底）、`v` 前缀剥离与对外形态口径（带 `v` 展示 / 裸版本派生，§1.2-1） | 解析失败最终兜底 `"v0.0.0+unknown"` 并 logger.warning，不炸启动 | `feat(config): 版本单一事实来源解析链与更新检查默认值` | M |
| B2 | `main.py` `_VERSION` 退役改 `config.APP_VERSION`（含 `_fallback_info`）；`_openapi_override` 动态覆盖 `info.version`（= `APP_VERSION` 剥离 `v` 的裸版本）；`routers/system.py` health `version` 改引用；`test_openapi_ssot.py` 豁免改造（剔除 `info.version` 后其余字段严格比对 + 独立断言 info.version == 剥 `v` 裸版本，定稿方案见 §1.2-2）；**测试**：health 返回真实版本断言（带 `v` 形态） | 四处硬编码不再作为对外版本来源（§2.1 表闭环；yaml 静态值保留为离线参考，运行时动态覆盖） | `feat(web): health 与 openapi 元数据改用版本单一事实来源` | S |

### 批次 C/D：后端 update 域（测试随实现同提交）

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| C1 | `store/settings_repo.py` 枚举校验：`_value_error` 支持 `range.enum`（string 值域校验，不命中归 `type`）；**测试**：`test_settings.py` 增枚举合法/非法/类型错三态 + 既有全量回归 | 机制缺口补齐（§2.3），词表二不动 | `feat(store): 运行级设置枚举值域校验（update_check_interval）` | S |
| D1 | `services/update.py`（新）核心一：状态机（九相 idle/checking/available/up_to_date/downloading/installing/restarting/done/failed + 全局互斥锁）、版本比较（packaging.Version，v 前缀剥离，仅严格更大）、探测（httpx GET `{base}/releases/latest/download/VERSION`，connect 15s / read 30s 超时，异常→`UPDATE_CHECK_FAILED` 分类映射 §3.5 文案）、`.update-proxy` 读写（null=直连 ↔ 空内容文件、URL 原文落盘且**无尾换行**，与 update.sh `printf '%s'` 实测格式对齐）、`.update-check` 落盘/恢复（每次检查结束覆盖写 `checked_at`；成功时更新 `latest_version`/`had_update`，失败保留上一份成功值）；**测试**：`test_update_check.py`（新）——比较器边界（2.0.0 vs 2.0.1/2.1.0/3.0.0/相等/前缀）、httpx.MockTransport 四分支（正常/超时/DNS·连接失败/非 200）逐字文案断言、代理文件读写（含无尾换行与 update.sh 互认）、`.update-check` 恢复；`test_error_codes.py` `CONTRACT_CODES` **同步扩至 24 码**（新错误码落地即触发该静态闸门，须与实现同提交） | 文案表进代码常量（单一来源），单测逐字引用同一常量防漂移 | `feat(services): 更新检查服务（版本比较/探测/异常文案/代理通道）` | M |
| D2 | `services/update.py` 核心二：apply 流程——三守卫（running 判定 `executions_repo.list_by_state("running")`、互斥、形态判定=部署目录 VERSION+bin/hq 存在）、同步预检（探测 VERSION：网络失败 → 502 `UPDATE_CHECK_FAILED`；无更新 → 200 幂等；有更新 → 拉 `.sha256` 附件验下载通道，失败 → 502 `UPDATE_DOWNLOAD_FAILED`——预检失败均不进异步）、流式下载（临时目录，进度回调 → SSE `update.progress` 500ms 合并窗口；**重试策略**：网络类与 5xx 重试 ≤3 次、指数退避，4xx 不重试，重试前清临时文件并重置进度）、sha256 校验失败中止（现有文件分毫未动）、`update-state` 写入/恢复/清理（§3.4 规则逐条；JSON 格式含 `target_version`/`phase`/`started_at`，phase 翻转重写）、detached 拉起 self_update.sh + SIGTERM 自退；**测试**：`test_update_apply.py`（新）——守卫矩阵（三 409 + 幂等 200 + 预检两 502）、状态机流转全路径、进度节流（回调时间注入）、update-state 恢复三分支（done 达标/done 未达/中断→failed）、下载中断丢弃重试与重试上限 | 下载不落部署目录（mktemp）；`update.progress` 经 `MockState.emit` 走既有总线 | `feat(services): 更新执行流程（守卫/流式下载校验/落盘标记/接管拉起）` | L |
| D3 | `routers/update.py`（新）四端点，注册进 `main.py`；GET /update/status 含恢复清理语义、返回字段全集按 A1 契约（含 `proxy` 读自 `.update-proxy`、`supported` 形态判定）；POST /update/check 网络失败 502 `UPDATE_CHECK_FAILED`；PUT /update/proxy 校验自定义 URL 合法性（非法 400 INVALID_REQUEST）；**测试**：`test_contract_rest.py` 增四端点零漂移用例（含 200/202/409/400/502 状态码矩阵，覆盖预检 UPDATE_CHECK_FAILED/UPDATE_DOWNLOAD_FAILED 与 status 字段完整性） | 路由薄层，逻辑全在 service | `feat(routers): 更新域四端点接入契约` | M |
| D4 | `main.py` lifespan：自动检查调度协程（30s 轮询式，§1.2-5）+ apply 后台任务托管 + 启动时 `.update-check`/`update-state` 恢复挂载（含补查窗口判定，§1.2-6）；调度器注入时钟便于测试；**测试**：`test_auto_check.py`（新）——四档下次触发点计算（daily/weekly/monthly/never）、补查（窗口未查过才补查/已查过跳过双分支，含月初/周一跨日边界）、never 不排程不补查、到点只发现不安装（emit update.phase(available)，无 apply）、设置变更下次轮询生效 | never 档协程空转休眠（不 CPU 空转） | `feat(engine): 自动检查调度协程与启动恢复挂载` | M |
| D5 | SSE 事件登记：`update.progress`/`update.phase` 进事件注册与 `test_contract_sse.py`/`test_sse_events.py` 零漂移/触发清单（15 类全集断言） | sse.md §7 事件源清单同步 13→15 | `test(sse): 更新事件登记与零漂移断言扩容` | S |

### 批次 E：发行链脚本

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| E1 | `scripts/deploy/self_update.sh`（新，D6）：固化启动上下文——cwd=部署目录、命令 `uv run python -m web.src.main`、env 经 `Popen` 继承原进程环境（脚本内直接沿用、不猜测默认值，`G16WEB_HOME` 等启动级变量随之保持）、端口脚本内经 `.venv/bin/python -c "from web.src.main import resolved_listen_port; print(resolved_listen_port())"` 从 SQLite 取值 → 等父进程退出（主判据 `kill -0 $PPID`）+ 端口释放（辅助探测，nc/循环 curl，上限 60s；探测端口取 SQLite 现值，「设置改端口未重启」边界以父进程退出判据兜底、脚本内注明）→ tar 解压覆盖（复用 update.sh 拷贝清单，**不触碰 .venv/.update-proxy/update-state/.update-check/update.log**）→ 差量刷依赖（同 update.sh uv pip 清华镜像）→ `update-state` 置 `phase=done`（JSON，脚本经 `.venv/bin/python -c` 改写、**仅改 phase、保留 target_version/started_at**，不依赖 jq）→ 根脚本自更新（新包 `install.sh`/`update.sh`/`self_update.sh` 先拷为 `*.new`，重启前原子 `mv` 覆盖——运行中 bash 持旧 inode，不影响本次执行；脚本修复随更新触达部署目录，**仓库源文件不动、仅部署副本刷新**）→ nohup 按原上下文重启 → 追加日志 `update.log` | `--dry-run` 模式（只打印编排步骤不动文件）供演练与测试；脚本纯 bash + curl + tar，LF | `build(deploy): 新增 self_update.sh 自更新接管脚本` | M |
| E2 | `scripts/package_release.sh` 入包清单追加 `self_update.sh`（第 55 行 install 行加名）；**验证**：打本地验证包解包确认四脚本齐 | update.sh 仓库源不动（保留 CLI 兜底；部署副本由 self_update.sh 自更新，行为差异已在 A3 注明） | `build(deploy): 发行包入包清单纳入 self_update.sh` | S |

### 批次 F：前端

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| F1 | `App.vue` 品牌区版本行：两行品牌下方渲染 `{{version}}`（mono、--text-faint、不加粗；health 返回带 `v` 形态直接渲染，前端不再加前缀）；数据源 `/system/health`（启动拉取一次；`system.snapshot` 载荷不含 version，断线重连/服务重启后重拉 health 校对，随 F3 强刷机制自然对齐）；导航区下移视觉分离（间距取现有 --space 令牌，与细分隔线二选一按视觉定稿）；D5 accent 圆点（available 亮，done 或 up_to_date 灭，位置尺寸与 brand-dot 区分）；版本行可点击（热区含圆点）→ router 跳设置页，hover 微反馈 + focus-visible，**无导航项形态**；**走查**：圆点/版本行对比度过 check_contrast | 点击用 `<button>` 语义化实现（键盘可达），样式去按钮化 | `feat(frontend): 侧栏版本行与更新可用圆点跳转` | M |
| F2 | `components/UpdateCard.vue`（新）：八态显示状态机（§3.2 表逐行对齐 phase）；布局左内容右按钮（「检查更新」「立即更新」同行右对齐）；**按钮可用性矩阵**——running>0（消费 events.lamps.running）或 `supported=false`（源码形态，status 字段）或流程进行中时「立即更新」置灰并附文案（§3.5 定稿文案）；进度条（左新版本号/右实时速度，speed_bps 格式化 KB/s / MB/s）；代理通道三选一（直连/默认代理/自定义 URL，PUT /update/proxy，自定义非法前端即时提示；**默认代理落盘形态**=与 update.sh 相同的 URL 串 `https://v4.gh-proxy.org` 无尾换行）；「更新说明」链接新标签页；卡内**不渲染标题**；`views/SettingsView.vue`：更新卡置顶 + 启动级两项改水平一行两列 + 间距按 1080p 一屏预算收敛（**含新增参数行**，运行级 10→11 项）；**走查**：check_tokens（无新令牌）/check_contrast/1080p 截图 | 状态数据源 `GET /update/status`（含 supported/proxy 回显）+ SSE update.phase/progress；页面重进恢复不重查 | `feat(frontend): 设置页更新卡（八态状态机/进度/代理切换）与布局调整` | L |
| F3 | `stores/events.ts`：新两事件消费（phase→更新卡与圆点联动、progress→进度条）；**圆点全 phase 映射**：`available` 亮、`done`/`up_to_date` 灭（需求定稿三态），其余相（idle/checking/downloading/installing/restarting/failed）取默认灭、`failed` 不重亮（验收按此口径）；**强制刷新机制**：SSE 连接关闭（update 上下文中）→ 轮询 `/system/health`（500ms、上限 120s）→ 服务恢复后查 `GET /update/status` 三分支——`version` 变化 → `location.reload()`；`phase=failed` → 如实展示失败原因、不误报超时；两者均非 → 继续轮询至超时；超时如实提示「服务重启超时，请手动重启后刷新」（**新增文案，已回登需求 §3.4**）；多标签页各自轮询自然跟随；`api/contract.ts` gen:types 再生 | 轮询仅在感知 restarting 阶段后启动，常规断线不触发（避免误刷） | `feat(frontend): 更新事件消费与服务重启后强制刷新` | M |

### 批次 G：冒烟、验收与进度同步

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| G1 | 本地端到端演练（§4.5 方案）：本地 http server 伪装 release（VERSION/固定名附件/.sha256）→ 部署目录装"旧版" → `G16WEB_UPDATE_BASE` 指本地 → WebUI 检查/更新全流程 → 强刷/完成态/清理验证；**留痕**：演练记录（含截图）入本计划附录节 | A1–A6 逐条过 | （演练无代码提交，记录并入 G2） | L |
| G2 | 全量闸门 + 手动冒烟清单走查（§4.4）+ CHANGELOG.jsonl unreleased 汇总核对 + progress.json in_progress 收口 → 发布流程（§5） | 闸门命令输出留痕 | `docs: v2.1.0 验收留痕与进度同步` | S |

## 3. 依赖关系与风险预判

### 3.1 依赖图与关键路径

```text
A1 ──┬──> D3（契约四端点）──> F2/F3（前端吃契约）
A2 ──┤         └────────────> D5（SSE 登记）
B1 ──┼──> B2 ──> F1（health 版本行数据源）
    ├──> C1 ──> D4（调度读新参数）
    └──> D1 ──> D2 ──> E1（apply 拉起脚本）──> E2（入包）──> G1
                                      └────> F3（restarting 断线契约）
F1 + F2 + F3 ──> G1 ──> G2 ──> 发布
```

**关键路径**：A1 → D1 → D2 → E1 → G1（后端服务→脚本→真实演练），约占总
工作量 60%；其中 **D2+E1（自我重启编排）是全计划最高风险区**，G1 演练是其
唯一实证验收。次关键：A1 → D3 → F2（契约链，风险低但阻塞前端全部）。
B1/C1 为独立短任务，可与 A 批并行开工。

**阻塞点**：

- F2/F3 完全依赖 A1/A2 契约定稿（前端最后开工，排期上契约 diff 第一个做）；
- G1 依赖 E2（演练包须含 self_update.sh）与真实 uv/nohup 环境（WSL2 部署
  目录，不可用 pytest 替代）；
- Cargo/Node 构建链（package_release.sh 内嵌）仅在打验证包时需要，日常
  开发不被阻塞。

### 3.2 风险登记表

| # | 风险 | 影响 | 概率 | 缓解 / 兜底 |
|---|---|---|---|---|
| R1 | 自我重启编排失败（端口未释放即重启/uv 环境变量丢失/nohup 工作目录错） | 服务起不来，需手动介入 | 中 | E1 脚本 `--dry-run` 先演练；等待端口释放上限 60s 才重启；日志全部落 `update.log`；`update-state` 恢复 failed 如实提示；CLI `update.sh` + deployment.md 手动命令为最终兜底 |
| R2 | 替换中断（断电/断网）致部署目录半新半旧 | 服务不可用 | 低 | 下载/校验全在 mktemp 临时目录，通过后才覆盖；覆盖窗口极短；恢复路径=CLI `update.sh` 重跑（文档写明） |
| R3 | detached 脚本继承的 stdout/环境异常或随会话被杀 | 更新静默中断 | 中 | `start_new_session=True` 脱离进程组；stdio 重定向 update.log 不依赖终端；G1 演练必测"关掉浏览器/SSH 断开"场景 |
| R4 | WSL2 网络波动/gh-proxy 不稳 | 检查/下载失败 | 高 | 异常如实反馈（F4 本身就是缓解）；下载带重试（网络类与 5xx ≤3 次、指数退避，落点见 D2）；代理通道可切换；下载中断丢弃重试不残留 |
| R5 | 枚举校验改动波及既有 settings 测试/前端表单渲染 | 回归 | 低 | C1 独立小提交全量跑 pytest；前端设置页表单按 value_type 分支渲染需确认 string+enum 的控件形态（**下拉四选**：daily/weekly/monthly/never） |
| R6 | SSE 断开时点与前端轮询衔接错位（restarting 前断线误判） | 误强刷/漏强刷 | 中 | 前端仅在**已感知 restarting**（收到 update.phase(restarting) 或 apply 受理后）才进入轮询；常规断线走既有重连不触发刷新；120s 超时如实报错 |
| R7 | openapi info.version 动态覆盖破坏 ssot 零漂移测试 | 闸门红 | 低 | 已定稿豁免（§1.2-2）：**剔除 `info.version` 后其余字段严格比对（零豁免）+ 独立断言 info.version == 剥 `v` 裸版本**；不得用「两侧剥离 v 后比对」（源码形态 git describe 带 `-N-g<hash>` 后缀必红） |
| R8 | 多标签页并发 apply / 检查与更新并发 | 状态机错乱 | 低 | 全局互斥（UPDATE_IN_PROGRESS）；check 与 apply 共用锁序（check 不阻塞、apply 持锁） |
| R9 | 补查窗口判定边界（跨日/周一/月初时刻） | 判定误差致漏查或多查 | 低 | 窗口起点以标准库 datetime 计算，单测覆盖月初/周一跨日边界；按窗口判定后频繁重启不再重复请求远端（§1.2-6）；固定名附件无 API 限流，偶发多查无害 |
| R10 | 1080p 一屏预算超限（更新卡+两卡+按钮） | 布局验收失败 | 中 | F2 间距预算先行（更新卡目标高度 ≤160px），**运行级 10→11 项新增一行高度计入预算**；冒烟用 1080p 截图核对；兜底=局部滚动（需求允许，1080p 不得出现） |
| R11 | 源码开发形态误触发更新（本仓库日常即源码形态） | 开发目录被覆盖 | 低 | 形态守卫（部署目录 VERSION+bin/hq 判定）409 + 按钮置灰；单测覆盖判定边界（有 VERSION 无 bin/hq 等） |

## 4. 测试与验证方案

### 4.1 单元测试（新增 4 文件 + 扩 5 文件，全部离线）

| 文件 | 覆盖 | 手法 |
|---|---|---|
| `test_version_source.py`（新） | 三级解析优先级/兜底/边界 | tmp_path 伪造 VERSION/git monkeypatch/CHANGELOG 片段 |
| `test_update_check.py`（新） | 比较器边界；探测四分支（正常/超时/DNS·连接失败/非 200）；§3.5 七场景文案逐字；代理读写（无尾换行与 update.sh 互认）；`.update-check` 恢复 | httpx.MockTransport 注入 200/超时/ConnectError/非 200 |
| `test_update_apply.py`（新） | 守卫矩阵；状态机全流转；进度节流；update-state 三分支；sha256 失败不动现有文件；下载中断重试与重试上限 | MockTransport 流式 chunk；时钟注入；fake executions repo |
| `test_auto_check.py`（新） | 四档触发点计算；补查（窗口未查补查/已查跳过双分支）；never；只发现不安装；设置即时生效（30s 窗口） | 调度器时钟注入（不真 sleep） |
| `test_settings.py`（扩） | 枚举三态（合法/不命中归 type/类型错）；既有参数回归 | 既有夹具 |
| `test_error_codes.py`（扩） | `CONTRACT_CODES` 19→24 同步（D1 提交内落地，防静态闸门红） | 既有静态闸门（契约文件头比对） |
| `test_contract_rest.py` / `test_contract_sse.py` / `test_sse_events.py`（扩） | 四端点/两事件零漂移；15 类事件触发清单（update 两事件由真实动作触发，D5） | 既有契约夹具 |

文案断言口径：§3.2/§3.5 文案表进 `services/update.py` 模块常量，测试逐字
引用常量比对（防止文案双写漂移），中文全角标点含在断言内。

### 4.2 集成测试（进程内 ASGI + fake 链路）

- apply 全流程进程内联测：fake http server（本地 loopback 起静态文件服务，
  非真实 GitHub）+ `G16WEB_UPDATE_BASE` 指向 → TestClient 触发 check/apply →
  断言 SSE 事件序列（update.phase×N + update.progress 节流条数）与
  update-state 生命周期（写入→done→GET status 后清理）。**self_update.sh
  的真实执行不进 pytest**（涉及杀进程/重启，见 4.5 演练），进程内以
  monkeypatch 替换 Popen 断言调用参数（列表参数/start_new_session/脚本路径）。
- 守卫与并发：running 席位在场（fake_g16 既有夹具）apply 409；并发第二发
  UPDATE_IN_PROGRESS。

### 4.3 回归与闸门（每批次收口必跑，G2 全量留痕）

```bash
cargo build --release && ls target/release/hq   # e2e 前提（AGENTS §6.1-4）
uv run pytest                                     # 全量，记录实际通过数
uv run python scripts/validate_progress.py
uv run python scripts/check_tokens.py             # F 批后必跑
uv run python scripts/check_contrast.py           # F 批后必跑
uv run python scripts/gen_changelog_md.py --check
cd web/frontend && npm run gen:types && git diff --exit-code -- src/api/contract.ts
```

重点回归面：设置域（枚举校验波及）、SSE 全事件（15 类触发清单）、
错误码全集（19→24，`test_error_codes.py`）、openapi ssot（info.version
方案落点）、startup/reconcile（lifespan 新增协程不破坏既有启动序列）、
test_e2e_fake_g16 / test_e2e_queue_lifecycle（hq 产物在位前提下真跑，
确认派发链路零影响）。

### 4.4 手动冒烟清单（前端无 vitest，仓库既定决策）

1. 侧栏版本号与 health 一致；圆点 available 点亮/done 熄灭；点击跳设置页；键盘 Tab 可达。
2. 检查三分支文案与链接逐字/逐目标核对（本地伪装服务触发各分支）。
3. 更新中进度条：版本号在左、速度实时跳动（KB/s→MB/s 换档）。
4. 任务在跑时「立即更新」置灰 + 409 文案；源码形态按钮置灰 + 文案。
5. 代理三选一切换后，检查请求确实走选定通道（本地服务看 access log）。
6. 更新完成强刷后：版本行新号、更新卡「更新完成」、update-state 已清理。
7. 1080p 设置页一屏无滚动条；更新卡无标题字样；极小视口局部滚动。
8. 多标签页：A 页触发更新，B 页同步看到进度与最终强刷。
9. 拔网线/断本地服务：检查失败如实文案；下载中断重试提示。

### 4.5 端到端演练方案（G1，本地完整链路实证）

1. `scripts/package_release.sh`（无 tag）打验证包 ×2：一份 VERSION 改
   `v2.0.9` 装"旧版"部署目录 A；一份 VERSION 改 `v2.1.1` 作为"新版本"。
2. 本地静态服务（`python -m http.server` 目录含：VERSION(v2.1.1)、
   `gauforge-deploy-linux-x64.tar.gz`(+.sha256)）模拟 release 直链目录
   结构 `releases/latest/download/`。
3. 部署目录 A 以 `G16WEB_UPDATE_BASE=http://127.0.0.1:<port>` 启动 →
   WebUI 检查（发现 v2.1.1）→ 立即更新 → 观察进度条 → 服务自动重启 →
   前端强刷 → 「更新完成」+ 版本行 v2.1.1。
4. 反例演练：running 任务在场触发（409）；sha256 篡改（校验失败中止、旧版
   未动）；更新中关浏览器（detached 脚本继续完成）；断电模拟（kill -9
   服务后重启，update-state 恢复 failed 提示）。
5. 演练记录（步骤/输出/截图）回填本计划附录，A1–A6 逐条勾验。

## 5. 发布与回滚策略

### 5.1 发布流程（v2.1.0）

按 changelog-spec §1.6 固定顺序，叠加本功能特有步骤：

1. G2 闸门全绿留痕 → CHANGELOG unreleased 行核对完整（文档/后端/脚本/前端
   分批登记的汇总）。
2. 冻结：unreleased → `released`，补 `version: 2.1.0`、`date`（ISO 8601
   带时区）、`semver: minor`；末尾追加空 unreleased 行。
3. `progress.json` 清空 unreleased、`latest_released_version: 2.1.0`。
4. 本地 `git tag v2.1.0`（不打 tag 无法打包上传，package_release.sh
   校验 HEAD=tag）。
5. `scripts/package_release.sh v2.1.0 --upload`：gh release create +
   上传五附件（带版本名 tar.gz(+.sha256)、**固定名** tar.gz(+.sha256)、
   VERSION）——固定名附件覆盖后即成为 WebUI 更新通道的 latest 目标。
6. 发布后验证：另一部署目录装 v2.1.0 → `G16WEB_UPDATE_BASE` 还原默认
   （真实 GitHub，走配置的代理）→ 手动检查更新连通性冒烟（此刻 latest
   即自身 v2.1.0，应显示「已最新」）——首次真实通道验证；**WebUI 全流程
   自更新（v2.1.0→未来版本）留待下个发布自然验收**（自举边界：v2.0.0
   无更新端点，无法作为更新起点，已在 §4.5 用本地演练等效覆盖）。
7. 提示协作者；推送/上传等外发动作逐次取用户当次授权（AGENTS §5.4）。

### 5.2 回滚策略（分层）

| 层级 | 场景 | 手段 |
|---|---|---|
| 流程内自愈 | 下载失败/sha256 失败/守卫拒绝 | 需求内置：不动现有文件，phase=failed 如实提示，用户可直接重试 |
| 流程内中断 | 替换/重启阶段进程死亡（断电、kill） | 服务重启后 update-state 恢复 failed + 提示；恢复路径=CLI `scripts/deploy/update.sh` 重跑（幂等覆盖，docs 已写明） |
| 版本回退 | v2.1.x 需退回旧版 | release 页下载**带版本名**附件（`gauforge-deploy-v2.1.0-linux-x64.tar.gz` 等，历史版本永久在）手动解压覆盖 + 重启；数据零迁移（见下）无兼容负担 |
| 数据隔离 | 任务/SQLite/journal | `G16WEB_HOME` 工作区与部署目录分离的既有架构天然隔离；本版本**无 SQLite schema 迁移**（migrations.py 零改动，回退不涉数据） |
| 服务起不来 | self_update 后异常 | `update.log` + `/tmp/g16web-*.log` 排障；deployment.md 手动启动命令兜底；最坏 `install.sh` 重装（数据不受影响） |
| 发布回退 | release 附件有误 | gh release delete + 重建（tag 本地可删重打）；固定名附件未大规模消费前窗口极短 |

### 5.3 发布后观察项

- 首日：自动检查（凌晨 01:00 档）是否如期触发；`.update-check` 文件正常落盘。
- 代理场景用户：gh-proxy 通道下载成功率（凭 update.log 反馈）。
- 下个版本发布时：v2.1.0 部署上 WebUI 自更新全流程的真实首次验收。

## 6. 进度同步与提交纪律

- 开发前：`progress.json` in_progress 指向本计划，按批次推进时更新 note。
- 每批次收口：CHANGELOG.jsonl unreleased 行 + progress.json `unreleased`
  同步追加摘要（文档/后端/脚本/前端分批登记，type 对号：docs/feat/build）。
- 提交纪律对照：17 个提交均为单类变更；文档（A）→ 测试+实现成对（B–D）
  → 脚本（E）→ 前端（F）→ 进度（G）；逐文件 `git add` 具名，不用 `-A`。
- 本计划自身的落地与后续修订记录于 progress.json，不另开流水。

## 附录（G1 演练留痕，2026-09-29 回填）

### 环境与布置

- 仓库 HEAD `v2.0.0-35-g23f937f0`（含批次 F 前端）打验证包
  `gauforge-deploy-v2.0.0-35-g23f937f0-linux-x64.tar.gz`（无 tag 验证包不入库）。
- 部署目录 A `/tmp/g16web-drill/deploy-a`：解包验证包、`VERSION` 改 `v2.0.9`、
  `install.sh` 建 .venv；工作区 `G16WEB_HOME=/tmp/g16web-drill/home-a`；
  SQLite `listen_port=8401`（首启内联 uvicorn 写入后按标准命令正式启动）；
  `G16WEB_UPDATE_BASE=http://127.0.0.1:8402`。
- 伪装 release：`python -m http.server 8402`，目录
  `release-root/releases/latest/download/{VERSION, gauforge-deploy-linux-x64.tar.gz(+.sha256)}`，
  内容为验证包改版本 v2.1.1 重打包（**顶层目录须为 `gauforge/`，与
  package_release.sh 布局一致**——首演因布置成 `./` 顶层被 self_update.sh
  结构校验拦截，属演练布置错误、脚本行为正确，见反例 d 项）。

### 主流程（v2.0.9 → v2.1.1，全程 WebUI 操作）

1. 侧栏版本行 `v2.0.9` === health `version` === 部署 VERSION 文件；
   从候选页点击版本行（热区含圆点）跳转设置页（语义化 button 键盘可达）。
2. 「检查更新」→ 逐字文案 `发现新版本 v2.1.1！查看更新说明`，链接
   `https://github.com/baizhancaiji/gauforge/releases/tag/v2.1.1` 新标签页
   （截图 `drill-1-available.png`，圆点随 available 点亮）。
3. 「立即更新」→ 202 受理 → downloading（本地回环 18MB 瞬时，进度条
   500ms 窗口一闪即过）→ `服务重启中 …`（installing/restarting 显示态、
   双按钮置灰，截图 `drill-2-downloading.png`）→ 后端 SIGTERM 自退。
4. detached `self_update.sh` 编排（update.log 留痕）：接管（SQLite 端口
   8401）→ 等父退出 0s → 端口释放确认 0s → 解压覆盖 v2.1.1 → 差量刷依赖
   → update-state 置 done → 按原上下文重启 → 接管完成。
5. 前端感知 restarting 后 SSE 断开转轮询 health（500ms），服务恢复后
   version 变化 → `location.reload()` 强刷（新进程 access log 实证：
   `GET /` + assets 重载 + events 重连 + update/status 恢复，全程无人干预）。
6. 强刷后：侧栏 `v2.1.1`、更新卡 `v2.1.1 更新完成`、`update-state` 已清理
   （截图 `drill-3-done.png`）。

### 反例四项

| # | 场景 | 结果 |
|---|---|---|
| a | running 在场触发（fake_g16.py 置 g16_root、输入内嵌 `! FAKE: sleep=30`、行内提交至 running） | HTTP 409 `UPDATE_BLOCKED_RUNNING`，逐字文案「为保证运行稳定性，任务执行期间禁止更新」 |
| b | sha256 篡改（远端 v2.1.2 + 全零 hash） | 202 受理（预检只验通道）→ 下载后校验失败 → phase=failed 逐字「更新包校验失败，已中止（现有版本未受影响）」，部署 VERSION 仍 v2.1.1 分毫未动 |
| c | 更新中关浏览器（v2.1.2 正常包 WebUI 触发后关闭页面） | detached 脚本独立完成全编排（update.log：接管→解压 v2.1.2→刷依赖→置 done→重启→接管完成），服务恢复 v2.1.2 |
| d | 断电等效（脚本中止后服务死亡 → 重启） | update-state 停 installing → 恢复 phase=failed 逐字「更新流程曾中断（目标版本 v2.1.1 未达成），请重新执行更新或通过 CLI update.sh 恢复」，标记被 GET /update/status 消费后删除，旧版未损 |

### 自动检查与代理通道观察

- 启动补查：首启（weekly 窗口未查过）≤5min 补查触发，`.update-check` 落
  `latest_version=v2.1.1`，只发现不安装（phase 不进 downloading）；重启后
  窗口已查过不再重复请求远端（phase 保持 idle、latest_version 经伴生文件恢复）。
- 代理通道：自定义 URL 落盘 `.update-proxy` 无尾换行；检查请求经本地迷你
  透传代理（8403）实证拼接规则 `{proxy}/{base}/…`（access log：
  `GET /http://127.0.0.1:8402/releases/latest/download/VERSION`）；null=直连
  ↔ 空内容文件与 update.sh 互认。默认代理（真实 gh-proxy）无法代理本地
  base 属外网代理语义（拼接逻辑由单测覆盖）。
- up_to_date 分支：部署 v2.1.2 vs 远端 v2.1.2 → 逐字「当前版本已最新！」。
- 失败文案：源码实例探测不可达远端 → 逐字「连接超时，请检查网络」。

### A1–A6 勾验

| 判据 | 结果 |
|---|---|
| A1 侧栏=health=VERSION、点击跳设置页 | ✓（主流程 1） |
| A2 检查三分支逐字文案与链接 | ✓（available/up_to_date/failed 超时三分支均实证） |
| A3 三守卫矩阵 | ✓（running 409 反例 a、源码形态置灰 8399 走查、单测覆盖守卫矩阵与幂等/502 分支） |
| A4 全流程强刷与清理 | ✓（主流程 3–6） |
| A5 自动检查 | ✓（补查窗口双分支与只发现不安装实证；四档到点触发/30s 生效由单测时钟注入覆盖） |
| A6 1080p 一屏布局 | ✓（F2 收口实测：内容区零滚动、savebar 底 1041/1080；更新卡无标题、与设置卡等宽 880px） |

### 演练产物索引

- 截图：`docs/plans/assets/version-update-drill/drill-1-available.png`、
  `drill-2-downloading.png`、`drill-3-done.png`。
- 日志：部署 A `update.log`（self_update 编排逐行）、伪装服务 access log
  （代理拼接与强刷请求序列）。
- 演练环境（/tmp/g16web-drill）为一次性目录，演练后整体清理不入库。
