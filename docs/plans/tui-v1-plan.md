# TUI v1（终端客户端）· 实施计划（无限期延后）

> 状态：**无限期延后**（2026-11-12 决策：计划无限期延后，撤销目标版本
> 3.5.0 预留，原「待执行」状态作废；同日将审查修订版分叉文件
> tui-v1-plan.reviewed.md 的修订内容并入本计划后移除该文件，原制定依据
> tui-assessment/ 需求基线（tui-draft.md 2026-10-26 定稿及同目录四份基线）
> 一并清理移除，正文「tui-draft §」锚点保留为历史引用，重启实施前须重估
> 需求基线、代码事实锚点、契约基线与版本号）。
> 定位：Web 子系统的第二个客户端——「核心计算控制台」：单任务、队列编排、
> 状态监控、输入校验预览、断点续跑、组合流精修；守护进程未运行时由 TUI
> 启动引导拉起。原定目标版本 **3.5.0**（含 `added` → minor）已随延后决策
> 撤销，重启实施时另行核定版本号与 semver 口径。
> 随包分发：部署包内含 Maple Mono CN Regular 字体与 OFL 授权（原样分发，
> 不裁剪不改名；§1.3-11、C6），TUI 不自动安装字体。
> 排期口径：单人实施，任务粒度 = 一个可审查提交；规模标记 S（≤半天）/
> M（1–1.5 天）/ L（2 天+）。最低档估算约 40 人天，含 20% 缓冲按约
> 48 人天（9.6 周）排期（§3.3）。
> 代码事实锚点：提交 `1dedb9dc`；行号为该提交实际行号，批次 A 守护进程侧改动
> 会使其漂移，**以符号名为准**。契约基线 = 开工时 HEAD 的 `docs/api/`。
> 实施顺序：计划入库 → 契约文档 → 守护进程侧前置 → spike → 传输/reducer/引导/命令 →
> UI → 集成 → 人工矩阵 → 进度同步。
> 提交与发布口径：每个任务一个功能提交（实现与直接测试同属该功能变更）；
> A1 拆为 `docs(api)` 与 `test(api)`；实施期 patch 发布以显式计划路径运行
> `check_plan_status.py`，重启实施回填终态后随当次发布运行无参全量扫描。

## 1. 需求分析

### 1.1 功能范围（tui-draft §2.2/§2.5 定稿 → 实施视角）

| # | 功能 | 实施视角拆解 | 需求锚点 |
|---|---|---|---|
| F1 | 启动引导 | 地址解析（显式 `--addr`/`G16WEB_TUI_ADDR` 只探测、不自动拉起；未显式时只读工作区 SQLite `listen_port`，缺失/锁定回落 8300）→ health 探测（2s 超时，连续 3 次失败且目标不可连才判不可达）→ 不可达时依次检查 systemd 托管、`--no-launch`、TUI 引导标记（child pid）/进程扫描（`web.src.main` + 工作区匹配），任一命中只诊断不拉起 → 确认无实例才 detached 拉起守护进程（源码形态 `sys.executable -m web.src.main`；部署形态优先 `PROJECT_ROOT/.venv/bin/python -m web.src.main`；`cwd=PROJECT_ROOT`、PATH 前置 `PROJECT_ROOT/.venv/bin`、环境透传、独立会话、输出落 `<launch-workspace>/tui-daemon.log`）→ 按启动前日志偏移解析实际监听端口，1s 轮询上限 30s → 诊断（日志路径/端口冲突）；非回环地址警告并要求确认（非交互模式须显式 `--allow-remote`），非回环地址不自动拉起；systemd 托管（`G16WEB_SERVICE_UNIT` 或 `systemctl --user` unit 判定，systemctl 调用 3s 超时）或显式 `--no-launch` 不强行拉起，提示运维入口；引导锁 `<workspace>/.tui-bootstrap.lock` 用 `fcntl.flock`（记录 TUI pid、child pid、日志路径；进程退出自动释放）防双拉；退出不杀守护进程 | tui-draft §1.2 |
| F2 | 快照对齐生命周期 | 首连不带 `Last-Event-ID`；首帧 `system.snapshot` 应用（清快照外执行/停滞，并把候选/历史/队列/设置/组合流全部标脏）；看门狗 `max(60s, 2×心跳)`，随 `GET /settings` 与 `settings.updated` 重算；退避 1/2/5/10s 封顶；重连先判实例变化（daemon pid/create_time 按 §1.3-3 三路取一，变化即实例变化；health 的 version 变化、归一化 `uptime_s` 回退超过 0.5s、或无法判定同按实例变化，丢弃旧镜像与选中项）再无游标 SSE；5s 无快照视为协议异常；SIGTERM/SIGINT/SIGHUP 走同一清理路径；退出零命令 | tui-draft §1.1–§1.4 |
| F3 | 命令面（基础 10 命令） | 导入（含文件夹成队）、提交单任务、建队、成员重排、提交队列、席位重排、移除整席/成员、停止、归档；单飞 + §1.3-4 确认矩阵 + 超时=结果未知 + 基线读回核对；各命令可展示字段按端点实际响应：导入 `warnings`/`duplicate`/`queue_fallback_reason`，单任务与队列提交 `normalized`/`warnings`，续跑确认 `warnings`，候选列表 `warning_count` | tui-draft §2.2 #1–#10 |
| F4 | 输入校验预览 | 候选详情面板内嵌 `GET /candidates/{id}/preview`：解析块视图（`blocks`）、`parse_errors`、`warnings`（只读） | tui-draft §2.5、J1 |
| F5 | 断点续跑 | `POST /history/{id}/resume/preview`（面板自动拉取，ineligible 恒 200 文案呈现）+ `POST /history/{id}/resume`（`y` 二次确认，确认后只应用响应确认字段并展示 `warnings`）；ineligible 文案六态按 `(reason, probe.reason)` 选择：`reason` 五态（`no_resume_asset`/`chk_corrupted`/`probe_timeout`/`unknown_kind`/`chained_ref`）+ 归档特判（`reason` 恒 `no_resume_asset`、`probe.reason="archived"`）；入口对 failed/skipped 提供预览（归档条目在归档视图提供只读预览），succeeded/running 不提供；前置=守护进程 `resume_of` 在途拒重（批次 A4） | tui-draft §2.2 #11/#12、J6 |
| F6 | 组合流精修 | 候选页单候选 `f` 对话框（并行拉 `GET /combo-templates` + `GET /settings` 预填；模板结构化字段按 Web 同规则序列化为 Link0 行；本地校验 top_n 2–10、nproc 正整数、route 非空、`link0` 缺省或字符串数组）→ `POST /workflows/conformer-refinement`；前置=守护进程来源候选在途拒重（批次 A5）；`W` 组合流面板观测（`GET /workflows(/{id})`，含 energy_summary） | tui-draft §2.2 #13、J7 |
| F7 | 状态监控视图 | 六页（待执行/执行/候选/队列/历史/设置只读）+ 组合流面板 + 队列能量表（文本表）+ 空间占用状态栏（数据源 `GET /storage/usage`，状态栏可见时每 5 分钟刷新，超阈值即时告警）；候选/历史分页与原始输入只读视图；§1.3-6 五部件分层防 SSE 队列溢出 | tui-draft §1.5、§2.5 |
| F8 | 守护进程侧前置与 CLI 更新命令（配套） | R-H3 null 快照修复、R-H5 停止语义、R-B2 两处自然键拒重、R-B3 重启受理闩（v1.1 前置的独立加固，不参与 v1 验收）；项目 CLI 注册 `update` 子命令（经既有 REST 复用服务侧更新语义），TUI 永不纳更新 | tui-draft §7.2、§8、§9.3 |

**明确不做**（边界，防蔓延；完整清单见 tui-draft §2.5 排期表）：

- v1.1 全部端点：requeue、return-candidate、export、cleanup、候选删除、分块
  编辑、模板编辑、队列删除、设置写、ui-prefs 写、cube、workspace-out、
  重启命令（长按组件 v1 仅测试覆盖）、分析域只读五端点；
- 永不纳入：update 四端点（CLI/WebUI 专属）、`GET /ui-preferences`、
  `GET /history/{id}/output`（输出文件全文预览）、3D 渲染；
- 不做：自动重试/离线 outbox/任务状态机/补偿、乐观更新、视图态持久化、
  多客户端版本控制（并发写按服务端 400/409/422 刷新，不本地合并）、
  API 版本兼容检查（health `version` 仅用于实例变化判定，TUI 与服务端同仓发布）、
  远程形态自动拉起（仅本机 + 非回环警告）、鼠标增强、Link0 接续编排（v1.1 重议）、
  原始输入的编辑（只读查看）、队列成员增删（v1 队列编辑器仅调成员顺序，
  增删走 WebUI）、合并的「保存并提交」（保存与提交队列为两个独立命令）、
  headless 命令注入（集成测试的导入由测试进程经 REST 执行，并发写场景用
  Textual Pilot）、输入含 `@task:`/`@exec:` 的依赖预检（preview 不预检，
  submit 由服务端 422 原样展示）；
- TUI 不写 SQLite，业务层不读 SQLite；启动引导为发现既有实例可只读
  `listen_port`（单列只读豁免，不写、不迁移、不读其他键）；
- 不动 `web/frontend/`（前端零改动，前端类闸门不涉）；
- 字体自动安装/写入用户字体目录、字体子集化与改名分发、Nerd Font 图标
  字形（v1 仅随包原样分发 CN Regular 与 OFL 授权，安装由用户按指引完成）。

### 1.2 代码事实基线（锚点提交实测；TUI 决策的直接依据）

| 主题 | 事实 | 证据 |
|---|---|---|
| 进程模型 | 守护进程是唯一编排与持久化宿主；引擎独立线程；TUI 关闭不影响任务 | `web/src/main.py:109-130`、`web/src/engine/startup.py:43-81`、`web/src/engine/dispatcher.py:843-874` |
| 进程模型 | 守护进程入口 `python -m web.src.main`：uvicorn 绑定 `BIND_ADDR`（默认 `127.0.0.1`）、端口取 SQLite `listen_port`（无记录回落 8300） | `web/src/main.py:155-167`、`web/src/config.py:18`、`web/src/config.py:39` |
| 进程模型 | 启动序列自动确保 HQ server/worker 存活（对账接管已存活进程）；g16web 退出不杀 HQ；hq 定位 `G16WEB_HQ_BIN` > PATH > 仓库产物 | `web/src/engine/startup.py:43-74`、`web/src/config.py:238-246`、`docs/references/development.md` §6.2 |
| 进程模型 | 服务内 asyncio 部件不止 `fanout_task`：main.py lifespan 内另有 update 自动检查调度器，`run_pending` 由 update 路由受理后 `create_task` 触发，`to_thread` 全仓多处；SSE 与后台任务生命周期不完全同步，TUI 只凭 health/连接判断 | `web/src/main.py:114-125`、`web/src/routers/update.py:44-46`、`web/src/services/update.py:508-522`、`:791-798` |
| 持久化 | SQLite 共 10 表（9 域表 + `schema_version`），DDL 权威在 `store/migrations.py`；TUI 不写库、业务层不读库，启动引导仅只读 `listen_port` 用于既有实例发现 | `web/src/store/migrations.py:10-209`、`web/src/main.py:155-161` |
| SSE | 每连接独立队列 256 条；慢消费只断开该连接 | `web/src/sse.py:29`、`:42-66` |
| SSE | 重放窗口 1024 条 / 5 分钟；无游标或超窗推 `system.snapshot` | `web/src/sse.py:30-31`、`:138-165` |
| SSE | 慢消费断开后窗口内重连仍走重放分支；差量 >256 时 `deliver` 队满退订、已入队帧不送达，可能反复空重连——v1 无游标、每次重连取快照的直接理由 | `web/src/sse.py:68-85`、`:154-159` |
| SSE | 业务事件 id 续接 `sse_seq` 持久计数；快照/心跳帧 id 取 `MockState.event_seq` 镜像、重启后到首次 emit 之间可回落 0——帧 id 不当游标的直接理由 | `web/src/mock/__init__.py:43`、`:206`、`web/src/sse.py:129`、`:164` |
| SSE | `server_restarted=true` 只表示「带游标但无法重放」或引擎对账完成，≠进程重启；实例判定用 health 的 version/uptime_s | `web/src/sse.py:162`、`web/src/engine/reconcile.py:335-338`、`web/src/routers/system.py:15-22` |
| SSE | `pending.snapshot` 载荷可为 `null`（组合流自动提交路径）——reducer 必须 null 防御（守护进程侧修复见批次 A2） | `web/src/services/workflows.py:281` |
| SSE | 通知事件载荷 `ts` 不统一：路由层 emit 多无 `ts`、引擎层才有；同名 `queue.status` 两层载荷形态不一——reducer 不依赖 `ts` 做业务键 | `web/src/routers/settings.py:68`、`:79-82`、`web/src/engine/dispatcher.py:485-487` |
| SSE | `system.snapshot` 覆盖 pending、在跑执行（含 progress）、队列摘要、hq；列表型资源（候选/历史/设置/队列详情/组合流）不入快照，按需 REST | `web/src/services/snapshot.py:9-36`、`docs/api/sse.md:117-118` |
| 契约 | 50 path / 57 operation / 非 GET 29；统一错误体 `{"error":{code,message,details}}`、35 个稳定错误码 | `docs/api/openapi.yaml`（路径统计与文件头错误码全集清单，35 码 SSOT 载体）、`web/src/main.py:68-99`（统一错误体异常处理） |
| 契约 | 默认回环、无认证/CORS/Host 校验——v1 仅本机 + 非回环警告的依据 | `web/src/config.py:18`、`docs/api/openapi.yaml:112`、`:129`；全仓无 `CORSMiddleware`/`TrustedHostMiddleware`/`add_middleware` |
| 契约 | 全仓无 `Idempotency-Key`；五个创建型 POST 重复调用双写（导入、requeue、return-candidate、续跑确认、组合流） | `web/src/services/candidates.py:130-187`、`web/src/services/resume.py:230-261`、`web/src/services/workflows.py:110-179`、`web/src/services/history.py:178-238` |
| 续跑 | 入口只放行终态 failed/skipped（succeeded/running 404）；预览无副作用恒 200（`eligible/reason/probe/task_kind/injections/input_diff`），`reason` 枚举五态（`no_resume_asset`/`chk_corrupted`/`probe_timeout`/`unknown_kind`/`chained_ref`），归档显式强制无资产、以 `reason=no_resume_asset` + `probe.reason="archived"` 表达；skipped 允许进入 preview、通常因无 chk 落为 `no_resume_asset`；确认每次新建任务与席位（`resume_of` 关联），ineligible 422、满员 409、成功 200 | `web/src/services/resume.py:50-51`、`:54-62`、`:177-180`、`:217-227`、`:230-261`、`web/src/routers/history.py:105-120`、`docs/api/openapi.yaml:705-709`、`:740-746` |
| 续跑前端入口 | Web 历史页 `canResume` 仅对 `failed && !archived` 展示续跑；`ResumeDialog` 六条中文文案含 `archived`，但模板按 `preview.reason` 取词，归档时 `reason=no_resume_asset`，`archived` 词条不可达。TUI 六态按 `(reason, probe.reason)` 选择，入口覆盖 failed/skipped（归档只读预览） | `web/frontend/src/views/HistoryView.vue:162-164`、`web/frontend/src/components/ResumeDialog.vue:62-68`、`:135` |
| 组合流 | 受理即返回（crest 任务已入待执行队列）；检查序：字段 422（payload/top_n/nproc/route/link0）→ 503（crest 缺失）→ 409（满员，零副作用）→ 422（来源候选/输入）；模板为内联 route/link0，对话框经 `GET /combo-templates` 预填 | `web/src/routers/workflows.py:24-32`、`web/src/services/workflows.py:110-179`、`web/frontend/src/components/ComboFlowDialog.vue:39-95` |
| 组合流 | 无专属 SSE 事件；状态与能量聚合经 `GET /workflows`（列表）/`GET /workflows/{id}`（单点含 energy_summary）拉取 | `web/src/routers/workflows.py:35-47` |
| 能量表 | 两端点：`GET /queues/{id}/energy-summary`（成员恒 g16——crest 不入队，Web 侧注释性不变式）与 `GET /workflows/{id}` 单点聚合（crest 行 + 精修行混排）；Web 前端两端同形渲染，workflow 能量经 `GET /workflows` 列表内嵌 `energy_summary` 取得、未调用单点 | `web/frontend/src/components/EnergyTable.vue:3`（同形渲染）、`web/frontend/src/views/QueuesView.vue:185-186`（恒 g16 注释）、`:194`（队列能量调用）、`web/frontend/src/components/WorkflowDrawer.vue:40`、`web/src/services/energy.py:127-148`（队列 `:127-134`、workflow `:137-148`） |
| 失败前副作用 | 单任务提交在容量 409 前已规范化写回；队列提交逐成员规范化先于建席；续跑确认失败可残留任务行（不入席不占容量）——失败后必须重拉、读回以席位为准 | `web/src/routers/candidates.py:201-203`、`web/src/routers/queues.py:136-148`、`web/src/services/resume.py:249-258` |
| 停止/重启 | 停止：running 且有 `hq_job_id` 才 cancel，无在途闩，二次调用可 500（修复见 A3）；重启：每次受理都 detached 拉起脚本、`guard()` 只查 update 相、无受理闩（修复见 A6） | `web/src/engine/dispatcher.py:793-808`、`web/src/hq/cli_gateway.py:21-43`、`:75-76`、`web/src/routers/system.py:25-34`、`web/src/services/restart.py:42-53`、`:68-71` |
| 前端基线 | Web 首连发送 `Last-Event-ID: 0`（快照被标 `server_restarted=true`）、看门狗硬编码 60s（客户端常量；服务端心跳默认 15s、可调 5–300s，调至 >60s 即周期性误重连）——TUI 均不复制 | `web/frontend/src/stores/events.ts:380-384`、`:184-192`、`web/src/config.py:45`、`:92-95` |
| 前端基线 | 三处排序均提交全量有序数组；门控三组——席位行锁定、席位内成员 staged-only、队列编辑器按状态分级（`submitted` 下名称/`skip_failed`/link0 只读、在跑成员禁移除，父级按 `unsubmitted`/`submitted`→可编辑、`executing`/`completed`→只读映射打开）——三组门控须在 TUI 复制 | `web/frontend/src/views/PendingView.vue:94-126`、`web/frontend/src/components/PendingSeatMembers.vue:66-99`、`web/frontend/src/components/QueueEditorModal.vue:84`、`:86`、`:124`、`:349`、`:374`、`:397`、`:477`、`:552-553`、`:594`、`web/frontend/src/views/QueuesView.vue:168-169` |
| 前端基线 | 导入过滤是客户端选择职责：文件夹模式仅 `.gjf/.com`（大小写不敏感）、跳过相对路径任一段（含文件名）以 `.` 开头的文件；Web 文件模式由 `accept=".gjf,.com"` 提示，TUI 以文件选择器按 `.gjf/.com` 过滤/提示（§1.3-8），扩展名/编码/整批原子校验在服务端；TUI 必须按原始字节上传，不本地解码/规范化 | `web/frontend/src/views/CandidatesView.vue:112-127`（文件夹过滤）、`:455`（文件模式 accept）、`:179`（原始字节上传）、`web/src/services/candidates.py:41`、`:96-104`（扩展名/编码）、`:159-162`（整批原子校验） |
| 前端基线 | 唯一长按入口是服务重启且有运行中执行才 3 秒；`ui_prefs` 仅 3 个 Web 排序键、未知键整批 400——TUI 不读不写 | `web/frontend/src/views/SettingsView.vue:366-387`、`web/src/config.py:136-142`、`web/src/routers/ui_prefs.py:30-47` |
| 输入校验 | 导入返回逐文件 `warnings` 与 `duplicate`；单任务提交与队列提交返回 `normalized` + `warnings`；续跑确认返回 `warnings`；候选列表当前页现算 `warning_count`；候选预览返回 `parse_errors` + `warnings` | `web/src/services/candidates.py:179-180`、`web/src/routers/candidates.py:207-208`、`web/src/routers/queues.py:152-154`、`web/src/services/resume.py:259-261`、`web/src/routers/candidates.py:98-102`、`:166-177`、`docs/api/openapi.yaml:277` |
| 列表 | 候选与历史均分页：候选 `page/page_size`（默认运行级 `page_size=50`）、历史 `page/page_size/sort`；原始输入只读端点 `GET /candidates/{id}/input`、`GET /history/{id}/input` | `web/src/routers/candidates.py:76-104`、`web/src/routers/history.py:24-38`、`:71-74`、`web/src/config.py:44`、`:88-91` |
| 存储用量 | 工作区磁盘用量不入快照、不在 health：独立只读端点 `GET /storage/usage`，告警阈值为运行级设置 `disk_usage_warn_gb`——TUI 空间占用状态栏数据源；端点为工作区整树单遍历，TUI 以低频拉取 | `web/src/routers/storage.py:11-13`、`web/src/services/storage.py:41-85`、`web/src/config.py:52`、`docs/api/openapi.yaml:3047` |
| 多客户端 | 队列 PATCH、席位 order 为全量覆盖，设置写按 key 覆盖；均无版本/ETag，last-write-wins；TUI 与 WebUI 并发写按服务端 400/409/422 刷新处理 | `web/src/services/queues.py:163-179`、`web/src/services/pending.py:184-189`、`web/src/store/settings_repo.py:46-70` |
| 部署形态 | systemd unit 在服务进程环境置 `G16WEB_SERVICE_UNIT` 且 PATH 预置 `.venv/bin`；更新/重启脚本托管下委托 `systemctl --user`，非托管时 self_update 回退以 `.venv/bin/python -m web.src.main` 直启、restart 脚本按 /proc 快照复原原命令拉起；self_update 以整 `web/` 覆盖更新；`listen_port` 为重启生效项，重启/更新后可能变化 | `scripts/deploy/systemd_install.sh:73-74`、`docs/references/deployment.md:39`、`scripts/deploy/self_update.sh:48`、`:106`、`:176-187`、`scripts/deploy/restart_g16web.sh:62-77`、`:106-128`、`web/src/config.py:68-71` |
| 测试链 | `web/tests/` 测试文件 57 个（`test_*.py` 54，另有 `conftest.py`/`fake_g16.py`/`__init__.py`）；e2e 用 `shutil.which("hq")` 缺失即静默 skip——TUI 集成必须 fail-not-skip 并钉 `G16WEB_HQ_BIN`；httpx 0.28.1 已在依赖 | `web/tests/test_e2e_fake_g16.py:29`、`:43`、`docs/references/development.md:124`、`:92`、`:171`、`requirements.txt:9` |

### 1.3 技术要求与关键约束

1. **客户端边界**：TUI 位于 `web/tui/`（与 `web/src/` 平级），只经 REST/SSE 消费
   契约；不 import `web.src` 运行时、不写 SQLite、业务层不读 SQLite、不管 hq
   子进程；启动引导为发现既有实例可只读工作区 SQLite 的 `listen_port`（单列
   只读豁免）；退出不发任何任务命令、不杀守护进程（含引导拉起的 detached 实例）。
   入口 `python -m web.tui`，另提供 `--headless`（跳过渲染器，只跑传输 + reducer +
   状态导出 + 命令计数器，集成测试用；不提供命令注入）。状态导出与命令计数器在
   交互与 headless 两种模式下均写。
   状态导出写 `<workspace>/tui-state.json`（临时文件 + 原子替换），字段：

   | 字段 | 类型 | 说明 |
   |---|---|---|
   | `written_at` | string | 写入时刻 ISO 8601 |
   | `connection` | string | `connecting`/`open`/`reconnecting`/`closed` |
   | `instance` | object | `{version, uptime_s, sampled_at, daemon_pid, daemon_create_time}` |
   | `pending` | object | 同 `GET /pending` 响应 |
   | `executions_running` | array | 同 `system.snapshot.executions_running` |
   | `hq` | object | `{state, workers_online}` |
   | `last_frame_at` | string | 最近一帧 `received_at` |
   | `counters` | object | 按端点 `{started, finished, timeout, result_unknown}` |
   | `drops` | object | `{progress, monitor}` 可替换读数丢弃计数 |

   命令计数器按端点 append-only 写入 `<workspace>/tui-commands.jsonl`，每行写完
   flush/fsync；行字段：

   | 字段 | 类型 | 说明 |
   |---|---|---|
   | `ts` | string | 写入时刻 ISO 8601 |
   | `event` | string | `started`/`finished`/`timeout`/`readback` |
   | `request_id` | string | 命令实例唯一 id |
   | `method` | string | HTTP 方法 |
   | `path` | string | 端点路径 |
   | `resource_key` | string | §1.3-4 资源键 |
   | `http_status` | integer/null | 响应状态 |
   | `error_code` | string/null | 契约错误码 |
   | `outcome` | string/null | `ok`/`failed`/`unknown` |

   发命令前先写 `started` 行（进程被 `kill -9` 后仍可核对意图）；收到响应或超时
   后追加 `finished`/`timeout` 行。计数器只统计命令层发起的变更命令
   （POST/PUT/PATCH/DELETE）及其读回；页面刷新、对账与只读预览不计入。状态
   文件写入频率不高于 10Hz，并在基线就绪、连接态变化、命令完成时强制写。

2. **启动引导**：地址解析与实例发现按以下顺序执行。

   1. `<workspace>` 取 `G16WEB_HOME`（默认 `~/g16web`）。
   2. 显式 `--addr`/`G16WEB_TUI_ADDR`：只探测该地址，**不自动拉起**；不可达时
      显示诊断并要求用户启动/改地址；非回环地址警告并要求确认（非交互须
      `--allow-remote`）。
   3. 未显式指定：以只读连接读取 `<workspace>/g16web.db` 的 `settings` 表
      `listen_port`（JSON 值；不写、不迁移；库缺失/锁定/读取失败回落 8300），
      目标 `http://127.0.0.1:<port>/api/v1`。
   4. health 探测（2s 超时）。连续 3 次失败但目标端口仍可连时，按端口被其他
      进程占用处理，显示诊断，不拉起；连续 3 次失败且端口不可连才判不可达。
   5. 不可达时依次检查：systemd 托管（`G16WEB_SERVICE_UNIT` 环境变量，或
      `systemctl --user is-enabled/is-active <unit>`，unit 默认
      `gauforge.service`，调用 3s 超时；超时按未命中处理）、`--no-launch`、
      引导标记（`.tui-bootstrap.lock` 内的 child pid 存活且 cmdline 含
      `-m web.src.main`）与进程扫描（`psutil` 查找 cmdline 含 `-m web.src.main`
      且 cwd 或环境 `G16WEB_HOME` 与工作区匹配的进程）。
      任一命中只诊断、等待 health（上限 30s），不拉起第二实例。
   6. 确认无实例才获取 `fcntl.flock`（再次检查标记/进程，防竞态），detached
      拉起：`PROJECT_ROOT` 取 `web/tui` 包向上两级（源码=仓库根，部署=部署
      目录）；源码形态 `sys.executable -m web.src.main`；部署形态（`PROJECT_ROOT/VERSION`
      + `bin/hq` 在位）优先 `PROJECT_ROOT/.venv/bin/python`，缺失回落
      `sys.executable`；子进程 `cwd=PROJECT_ROOT`、`start_new_session=True`、
      stdin DEVNULL、env 透传，PATH 前置 `PROJECT_ROOT/.venv/bin`；若环境未设置
      `G16WEB_HQ_BIN` 且该目录存在 `hq`，同时设
      `G16WEB_HQ_BIN=PROJECT_ROOT/.venv/bin/hq`。锁定文件记录 TUI pid、child pid、
      日志路径与启动前日志偏移。
   7. 输出追加到 `<launch-workspace>/tui-daemon.log`；只解析启动前偏移之后新增段
      中的 uvicorn 监听行，解析成功以日志端口替换目标端口连接；解析失败按目标
      端口轮询，并在诊断中给出日志路径与端口冲突提示；1s 轮询上限 30s。
   8. 连接后与 `GET /settings` 的 `workspace_root` 比对。daemon 日志固定于拉起时
      路径，TUI 不改写；TUI 自身诊断/命令计数器/状态导出在服务端目录可写时切换到
      服务端工作区，不可写则保留本地路径并显著告警，两条路径均写入诊断。
   9. 会话中断线重走引导（先探测/标记/进程扫描防双拉）；退出不杀守护进程；
      hq 状态只呈现（非 up 时状态栏提示，不阻塞）。

3. **快照对齐**：首连与每次重连均不带游标、取 `system.snapshot` 重建基线；
   5s 无快照视为协议异常；重连先解析 daemon 实例身份：优先用 pid +
   `create_time`（TUI 引导标记、进程扫描或 `systemctl --user show -p MainPID`
   （3s 超时）三路取一），pid/create_time 变化即实例变化；该身份不可得时记录
   `(sampled_at_monotonic, uptime_s)`，以
   `uptime_s < 上次 uptime_s + 经过秒数 - 0.5` 兜底判定；`version` 变化、
   health 缺 `uptime_s` 或采样时刻不可用同样按实例变化处理（丢弃旧镜像与
   选中项）；看门狗 `max(60s, 2 × sse_heartbeat_seconds)`，随 `GET /settings` 与
   `settings.updated` 重算；退避 1/2/5/10s 封顶、任意帧复位；快照到达后把候选/
   历史/队列详情/设置/组合流全部标脏，并立即刷新当前可见页。

4. **命令纪律**：至多一次（不自动重试、不 outbox）；每资源单飞（资源键 =
   候选 id / 队列 id / 席位 id / 执行 id / 历史条目 id / 导入批次（全局）/
   续跑源执行 id / 组合流来源候选 id）；非幂等命令超时一律「结果未知」+ 一次
   基线读回核对；404/409 仅在 GET 确认已处期望状态后才显示为「已完成」；失败后
   重拉 preview/队列不复用旧文本。超时与读回口径（续跑探针 120s、Gateway 15s
   为服务端已知硬上界；导入/队列提交的超时在 §4.1 以实测最坏耗时校准后不得
   低于该值）：

   | 命令 | 超时 | 命令前基线 | 超时后读回与判定 |
   |---|---|---|---|
   | 导入候选 / 文件夹成队 | 30s | 候选 id 集合；`queue_from_folder=true` 时另记队列 id 集合 | 普通导入：`GET /candidates` 分页遍历，成功 = 本地文件名多重集与 `id > 基线最大值` 的新候选文件名多重集一致（同名多文件按新 id 数量匹配）；`queue_from_folder=true`：候选已转 `queue_member`，改查 `GET /queues` 新队列 id，核对 `member_ids` 与成员文件名多重集；旧同名候选/队列不计入；缺失任一条目或队列为结果未知 |
   | 提交单任务 | 10s | 候选 id + pending 席位 id 集合 | `GET /candidates/{id}`（404 视为已移出）+ `GET /pending`；成功 = 候选已移出且存在 `task_id=候选 id` 的新席位；候选仍在且无新席位为失败 |
   | 创建队列 | 10s | 队列 id 集合 | `GET /queues` 只认 `id` 不在基线的新队列；成功 = 恰好一条新队列且 `member_ids` 与提交顺序一致；多条新队列交用户确认；无新队列为失败 |
   | 队列成员重排 | 10s | 队列 id + 原 `member_ids` | `GET /queues/{id}`；成功 = `member_ids` 等于提交顺序；不同为冲突，刷新后退出重排模式 |
   | 提交队列 | 10s | 队列 id + 原状态 | `GET /queues/{id}`；成功 = `submitted`/`executing`/`completed`；仍 `unsubmitted` 为失败 |
   | 待执行席位重排 | 10s | pending 席位 id 顺序 | `GET /pending`；成功 = 席位顺序等于提交顺序；不同为冲突 |
   | 移除整席/席位成员 | 10s | 目标 seat/task id | `GET /pending`；成功 = 目标已不存在 |
   | 停止执行 | 20s | execution id | `GET /executions/{id}`；成功 = 终态；仍 running 为结果未知/冲突；409 仅在读回确认终态后视为已完成 |
   | 归档历史 | 10s | history id | `GET /history/{id}`；成功 = `archived=true` |
   | 续跑预览 | 130s | — | 只读，无需读回；失败可手动重试 |
   | 续跑确认 | 130s | pending 席位 id 集合 + `resumed_by` 长度/最大值 | `GET /pending` 新增席位 diff + 源文件名匹配；有歧义时 `GET /history/{源执行 id}` 的 `resumed_by` 必须出现 `id > 基线最大值` 的新执行；仍无法判定交用户确认 |
   | 组合流精修 | 30s | workflow id 集合 | `GET /workflows` 只认 `id` 不在基线且 `source_candidate_id` 匹配的新 workflow；旧终态 workflow 不计入；多条新 workflow 交用户确认 |

   确认矩阵：

   | 命令 | 确认方式 |
   |---|---|
   | 导入候选 | 选择完成后确认框执行 |
   | 提交单任务 | `y` |
   | 创建队列 | `Enter` 保存；提交队列为独立命令 #5 |
   | 队列成员重排 | 无二次确认（`J/K` 即时；`o` 模式 `Enter` 提交） |
   | 提交队列 | `s` + `y` |
   | 待执行席位重排 | 无二次确认（`J/K` 即时；`o` 模式 `Enter` 提交） |
   | 移除整席/席位成员 | `d` + `y` |
   | 停止执行 | `y` |
   | 归档历史 | `y` |
   | 续跑预览 | 打开面板即拉取，无确认 |
   | 续跑确认 | `y` |
   | 组合流精修 | `y` |
   | 长按重启（v1.1） | 按住 `Enter` 3 秒 |

5. **纯 reducer**：`reduce(state, event)` 不发 HTTP、不读写文件、不读时钟/
   随机数、不打印；`plan_effects` 与 `reduce_ui` 分离；dirty 用集合（幂等）、
   Toast 按事件 id 去重；executions/history/seats 按主键去重；`update.phase`/
   `update.progress` 显式 no-op（测试断言 state 与 dirty 不变）；未知事件原样返回。

6. **五部件分层**（防 256 队列溢出）：`SseReader`（只读网络）/ `EventQueue`
   （有界；状态事件不丢，progress/monitor 按 execution_id 合并、队满只丢可
   替换旧读数）/ `ReducerLoop`（≤10Hz）/ `EffectRunner`（每资源单飞 + 500ms
   合并；长请求走 worker）/ `Renderer`（只读状态只画屏）。`EventQueue` 采用
   双通道：状态事件通道容量 512；progress/monitor/心跳/update 读数按
   execution_id 或全局键保留最新值，不占状态通道。状态事件：`system.snapshot`、
   `pending.snapshot`、`task.status`、`history.appended`、`queue.status`、
   `queues.changed`、`candidates.changed`、`execution.stalled`、`hq.status`、
   `settings.updated`；可替换读数：`execution.progress`、`execution.monitor`、
   `system.heartbeat`、`update.progress`、`update.phase`。状态通道满时
   `SseReader` 阻塞形成背压；背压持续超过看门狗阈值按协议异常断开重连取快照；
   丢弃计数只统计可替换读数，并在状态栏可见。上述不丢/合并/淘汰/背压策略必须
   有独立单测，覆盖 257/300 与 513/600 两档。

7. **框架**：Textual（已定稿）；批次 B spike 为实施第 0 步，★判据（CJK 宽度、
   颜色降级）硬否决才切 Ratatui。该回退不是视图层替换（tui-draft §6.1「仅重写
   视图层」的回退口径不再适用，以本条为准）：协议/reducer/命令层是 Python，
   Ratatui 是 Rust，需以 Rust 重写整个客户端，或采用「Python 核心 + Rust 前端」
   双进程桥接；C–H 批工作量与发布形态须重新评估。B1 的 go/no-go
   在 C1 与 G 开工前完成；C2–C4/D 可与 B1 并行，若否决后选择整客户端 Rust
   重写，Python 传输/命令层不再复用；若选择双进程桥接，按桥接边界重估复用面。
   `requirements.txt` 钉死 spike 实测通过的 textual 版本及其运行时传递依赖精确
   版本（过滤 dev/测试依赖，不用完整 `uv pip freeze` 清单），uv 国内镜像装于
   `.venv`。

8. **导入过滤与三处门控为 TUI 必须复制的客户端规则**：文件夹模式仅
   `.gjf/.com`（大小写不敏感）、跳过相对路径任一段（含文件名）以 `.` 开头的
   文件、按原始字节上传；读取前显示文件大小，单文件 >64 MiB 或整批
   >256 MiB 时在导入确认框提示（不阻断、不本地解码；服务端无强制大小上限，阈值为客户端提示）；文件模式
   由 TUI 文件选择器按 `.gjf/.com` 过滤并显示提示行（不提供 HTML `accept` 属性），
   文件名须可 UTF-8 编码，不可编码者跳过并在导入确认框提示、不静默改名；
   扩展名/编码/整批原子校验由服务端负责；整批 422 逐文件展示、文件夹成队 2–10
   越界回落原因原样展示。锁定席位下标不变式提交前本地校验、非 staged 成员不可
   移动、队列编辑器按 Web 状态分级（`unsubmitted` 可改名称/`skip_failed`/成员顺序；
   `submitted` 仅成员顺序可调，名称与 `skip_failed` 只读；`executing/completed`
   只读），0 请求拒绝，不依赖服务端 409；成员增删不在 v1 编辑器范围；保存与
   提交队列为两个独立动作，不提供合并的「保存并提交」。

9. **键位基线**：`1–6` 六页 / `j/k g/G Ctrl+D/U` 导航 / `Space Shift+J/K v a Esc`
   多选 / `J/K` 移动行（席位/成员单步即时提交；队列编辑器内为本地移动）、
   `o` 重排模式 / `Enter` 确认展开 / `i` 导入 / `c` 建队 / `s` 提交 /
   `x` 停止 / `d` 移除整席或席位成员（待执行页）/ `y` 确认 / `z` 归档 /
   `r` 续跑 / `f` 组合流 / `W` 组合流面板 / `q Ctrl+C` 退出（第二次强制）/
   `?` 帮助。
   B1 按键编码矩阵须覆盖本节全部组合键；不可区分时按 B1 结论调整键位并同步
   AC9 与帮助页。旅程键数基线：J1 全程 9 键（Web 8 次激活）、J2 光标就位后
   单步 1 键、J4 焦点在卡 2 键、J6/J7 确认动作 1 键；重连后权威态恢复 0 键。

10. **跨平台纪律**：路径 `pathlib`、子进程列表参数无 shell、文本读写
    `encoding="utf-8"`（AGENTS §十，全程适用）；导入上传是唯一例外，必须
    读取原始字节，不 decode、不换行转换、不本地规范化，编码/BOM/CRLF 交由
    服务端校验与处理。

11. **字体资源分发边界**：部署包随附
    `web/tui/assets/fonts/MapleMono-CN-Regular.ttf`（18,509,264 字节，
    gzip 后约 8.0 MiB）、`OFL.txt`、`SHA256SUMS` 与安装说明
    `web/tui/assets/fonts/README.md`（来源、版本、安装命令、已知限制）。
    字体按 OFL-1.1 **原样分发**：该字体声明 Reserved Font Name
    `Maple Mono`，禁止裁剪/子集化/改名后沿用原名；**TUI 进程不安装字体、
    不写 `~/.local/share/fonts`、不改终端字体设置**，安装由用户按说明执行；
    字体缺失或未安装不影响 TUI 功能（仅影响观感），启动不检测、不告警。
    v1 只分发 Regular：终端粗体依赖终端自身合成或回退，登记为已知限制；
    NF 图标字形不在 v1 范围。校验口径 = `sha256sum -c SHA256SUMS` 通过，
    且字体 name 表家族名仍为 `Maple Mono CN`（证明未改名）。

12. **终端尺寸与布局**：最小尺寸固定 80×24，六页与帮助页在该尺寸下可用；
    低于门槛（如 70×20）只渲染单屏引导提示（当前尺寸、所需最小尺寸、调整
    建议），不进入破版布局，恢复尺寸后自动回到正常界面；所有布局值由当前
    终端尺寸派生并在 resize 后重算（布局重算去抖约 50ms），无 80×24 之外
    的布局硬编码常量。
13. **语义色与终端能力降级**：语义色与符号映射表一次定稿——调色板 ≤4 色，
    每条业务语义（执行/成员/队列状态、停滞、输入警告、选中、锁定等）给出
    颜色令牌、256/16 色回退、配对符号与文字标签，亮色终端主题对比可读为
    映射表约束列；映射表随 G1 tcss 定稿，六页与状态栏/帮助页唯一引用。
    `NO_COLOR` 或 `TERM=dumb` 时以 bold/reverse
    等单色强调渲染，状态一律「符号 + 文字」双编码，不以颜色单独承载语义；
    16 色档按映射表回退保持可读；不输出转义序列垃圾。鼠标不启用，所有操作
    键盘可达。
14. **焦点与键盘可达**：任意时刻恰一个可见焦点；Tab/Shift+Tab 按页面阅读
    顺序循环；切页返回后焦点恢复离开时位置；模态打开时焦点落于首个可交互
    控件，模态内 Tab 固定、`Esc` 可退；列表刷新与快照应用后，滚动位置与
    选中集合做边界夹取，已消失的选中项移除并提示。
15. **空态、加载态与错误态**：六页与组合流面板无数据显示空态文案 + 下一
    动作键提示，不以空表头呈现；首拉/刷新在途显示含静态文字的加载指示
    （不依赖动画帧传达状态）；错误以横幅或
    状态栏呈现，保留当前位置、筛选与选中，不替换视图；过滤无匹配提示
    「Esc 清除」。
16. **粘贴与输入边界**：输入框启用括号粘贴并按数据接收，不触发动作键；
    超长粘贴可见截断提示，不阻塞渲染。
17. **CJK 与显示宽度**：中文、emoji 与组合字符（grapheme）按显示宽度
    （CJK 按 2 列）参与列宽计算与截断，超宽以 `…` 截断且不破坏对齐，
    状态栏含 CJK 不破版；宽度计算使用 Textual/Rich 内建能力，不另引宽度
    实现。
18. **文档交付**：`web/tui/README.md`（中文）九节在位；终端合同按
    Required/Enhanced/Optional/Unsupported 四行式声明；应用级 BiDi/RTL
    不支持与屏幕阅读器支持受限写入已知限制；快捷键节与键位总表同源一致。
19. **启动失败关闭**：交互模式在进入全屏前检查 stdout 为 TTY；非 TTY 时
    向 stderr 打印单行错误并以非零码退出（提示改用 `--headless`），
    `--headless` 不受影响。

### 1.4 验收标准

| # | 判据 | 验证方式 |
|---|---|---|
| AC1 | 启动引导：守护进程未运行时 TUI detached 拉起、health 200、基线就绪；kill 守护进程后 TUI 自动重走引导恢复；退出后守护进程仍存活；端口被占时显示诊断不挂死；按 `listen_port`/日志发现非默认端口；慢启动 daemon 不被重复拉起；远程地址与显式 `--addr` 不自动拉起；systemd 托管/`--no-launch` 不拉起第二实例 | 集成场景 B（§4.3）+ AC26 |
| AC2 | 退出零命令：`kill -9` TUI 前后命令计数器逐端点一致（stop 计数 0、started 行总数不变）；退出不发任何任务命令、不杀守护进程 | 集成场景 A 步骤 3 |
| AC3 | 重连 0 键恢复：无输入前提下 execution 集合、pending、hq 与 REST 一致；daemon pid/create_time 变化（实例身份按 §1.3-3 三路取一）、version 变化、归一化 `uptime_s` 回退超过 0.5s 或无法判定时旧镜像与选中项被丢弃；快速重启（旧 uptime 内、pid 变化）可识别；快照后可见列表已刷新 | 集成场景 A + AC26 + 假时钟单测 |
| AC4 | 首连不带 `Last-Event-ID`、入口快照帧 `server_restarted=false`（引擎对账完成会向全体订阅者广播 `server_restarted=true` 快照，不属首连断言口径；reducer 不以该标志做实例判定）；5s 无快照按协议异常断开退避 | 协议单测 + 场景 A |
| AC5 | 看门狗与退避：心跳 300s 时 60s 无帧不误断、心跳 5s 时以 60s 为下限；`settings.updated` 后阈值重算；退避 1/2/5/10s 封顶、任意帧复位 | 假时钟表驱动单测 |
| AC6 | reducer 纯函数：15 类事件表驱动、`reduce(reduce(s,e),e)==reduce(s,e)`、空值防御（无 NaN/None 污染、`workers_online` 缺省 0）、`pending.snapshot=null` 不清屏、`update.*` 不变态、未知事件原样、executions/history/seats 按主键去重；reducer import 图不导入 httpx/socket/web.src/时间/随机；`web/tui` 全包只禁止导入 `web.src` | 单测 + 静态检查 |
| AC7 | 13 命令错误矩阵（命令 #1–#13，长按重启为 v1.1 项、不参与 v1 验收）：每个命令至少覆盖其实际可产生的 400/404/409/422/503 主分支，停止另覆盖 500/502/504；非幂等命令超时显示「结果未知」并读回；组合流 503/409/422 逐一展示 | 命令层单测（MockTransport） |
| AC8 | 守护进程拒重（R-B2 落地）：同一源执行重复续跑确认 409、同一来源候选重复组合流 409；并发重复请求只产生一个任务、一个席位、一个 workflow、一个 crest 任务，无孤儿输入文件/模板，且不超出 `pending_seat_limit`；`CONTRACT_CODES` 静态闸门同步扩容（35→38） | 服务端单测 |
| AC9 | 键位旅程：J1 9 键、J2 单步 1 键（撞锁定席位 0 请求）、J4 2 键、J6/J7 确认 1 键（ineligible 时确认禁用）、移除整席/成员 `d` + `y` 2 键；重排类即时提交无二次确认 | Pilot 按键序列断言 |
| AC10 | 导入过滤与 Web 逐条一致：文件夹模式仅 `.gjf/.com`（大小写不敏感）、跳过任一路径段（含文件名）以 `.` 开头者；文件模式由 TUI 选择器按 `.gjf/.com` 过滤/提示、扩展名由服务端校验；原始字节上传、整批原子校验、文件夹成队 2–10 越界回落原因展示、单文件/整批超阈值提示、非 UTF-8 文件名跳过提示 | 与 `CandidatesView.vue:112-127`、`:455` 同规则表驱动单测 |
| AC11 | 三处门控本地拒绝：锁定席位移动、非 staged 成员移动、`executing/completed` 队列编辑均 0 请求并提示；`submitted` 队列仅成员顺序可调，名称与 `skip_failed` 只读 | 视图单测 + Pilot |
| AC12 | 闸门全绿 + 集成真跑（hq 产物在位、TUI 集成模块 skip=0、全量套件 skip 逐条登记）+ 人工矩阵（§4.5）逐项留痕；大工作区空间占用按 5 分钟低频刷新 | 命令输出留痕 |
| AC13 | 输入校验展示：导入逐文件 `warnings`/`duplicate`/`queue_fallback_reason`、单任务提交与队列提交的 `normalized`/`warnings`、续跑确认 `warnings`、候选预览 `parse_errors`/`warnings`、候选项 `warning_count` 均可见 | Pilot + 命令层单测 |
| AC14 | 快照后列表刷新：`system.snapshot` 到达后候选/历史/队列/设置/组合流全部置脏并刷新当前可见页；重连后不显示旧列表 | 集成场景 A + reducer 单测 |
| AC15 | 多客户端并发：合法全量重排为 last-write-wins；先写者收到 400/409（另一路先移除/锁定席位或提交队列）后刷新并退出重排模式；TUI 收到快照变化同样退出重排模式；不本地合并、不重复建席 | 集成场景 C |
| AC16 | 信号退出：SIGTERM/SIGINT/SIGHUP 恢复终端、不发命令、不杀守护进程；退出时有在途命令显示「结果未知」，≤2s 退出且不重发；Textual crash 路径（人为触发未捕获异常）退出后终端恢复（依 B1 对 Textual 内建 crash 处理的实测留痕，内建不足则在 G1 清理路径补 guard） | 子进程信号测试 + 人工矩阵（含 crash 路径项） |
| AC17 | 分页与只读输入：候选按 `page/page_size`、历史按 `page/page_size/sort` 翻页且选择集保持；`/candidates/{id}/input`、`/history/{id}/input` 只读查看可用 | Pilot + 契约单测 |
| AC18 | 部署与分发：`scripts/package_release.sh` 产物含 `web/tui`；解包部署目录 `.venv/bin/python -m web.tui --headless` 可达基线；守护进程 hq 状态为 up（cwd/PATH 正确）；产物含 `web/tui/assets/fonts/` 的字体、`OFL.txt`、`SHA256SUMS` 与 `README.md`，`sha256sum -c` 通过、字体家族名仍为 `Maple Mono CN`、TUI 启动不写用户字体目录 | 部署包冒烟（H2）+ `test_deploy_scripts.py` |
| AC19 | 队列编辑器：J1 建队段可用；`unsubmitted` 可改名称/`skip_failed`/成员顺序、`submitted` 仅成员顺序、`executing/completed` 只读；0 请求门控；成员增删不提供 | Pilot + 视图单测 |
| AC20 | 可观测性：`<workspace>/tui-state.json`（工作区按 §1.3-2 第 8 步解析）按 §1.3-1 字段表可读且完整；`tui-commands.jsonl` 每行按字段表完整，发命令前有 `started` 行、请求挂起中止时该行已落盘、`kill -9` 后仍可核对 | 集成场景 A + 命令层单测 |
| AC21 | 大批量导入：257/300 文件经测试进程 REST 导入；TUI 连接可断开或持续排空，最终候选列表与 REST 完整一致；TUI 命令计数不变；导入命令读回由命令层单测覆盖 | 集成场景 A + 命令层单测 |
| AC22 | 超时与读回：续跑慢探针（>30s）不误报，130s 内完成或按读回收敛；停止 20s；导入/队列提交超时按实测最坏耗时校准且不低于该值；续跑确认按新增席位 diff + `resumed_by` 新 id 规则核对 | 命令层单测 + 集成场景 A + AC25 |
| AC23 | 服务端 SSE 边界：256 队列慢消费断开、1024/5 分钟重放窗口、无游标重连快照按事实基线；TUI 不把帧 id 当游标 | 连接层单测 + 契约单测 |
| AC24 | 按键编码：B1 三环境全部组合键可区分；不可区分项调整键位并同步 AC9/帮助页 | B1 spike + 人工矩阵 |
| AC25 | 创建型命令读回基线：预置同名候选、同名队列、旧终态 workflow、旧 `resumed_by` 时，超时读回只认新实体，不误判旧实体；文件夹成队按新队列 id 与成员文件名核对（不查 `/candidates`）；多新实体交用户确认 | 命令层单测（MockTransport + 真实 store 夹具） |
| AC26 | 启动引导边界：慢启动外部 daemon 只拉起一个；非默认 `listen_port` 被发现；远程地址与显式 `--addr` 不自动拉起；systemd `systemctl` 3s 超时按未命中处理；锁残留恢复 | 引导单测 + 集成场景 B |
| AC27 | 队列编辑器保存/提交分离：`Enter` 保存不提交；`s` + `y` 提交队列；保存成功而提交失败时队列保持 `unsubmitted` 并明确提示；无合并「保存并提交」入口 | Pilot + 视图单测 |
| AC28 | 续跑入口与六态文案：failed/skipped 可打开预览，归档条目在归档视图提供只读预览，succeeded/running 无入口；六态按 `(reason, probe.reason)` 显示，归档显示归档文案，ineligible 确认禁用 | Pilot + 命令层单测 |
| AC29 | 客户端 EventQueue：状态事件通道容量 512，257/300 与 513/600 两档状态事件在连接期间不丢；progress/monitor 按 execution_id 合并；状态通道满时背压，超看门狗阈值断开重连取快照；丢弃计数只统计可替换读数 | 连接层单测 |
| AC30 | 最小尺寸与 resize：80×24 下六页与帮助页可用；低于门槛（如 70×20）渲染最小尺寸引导提示、不崩溃不乱码，恢复尺寸自动回正常界面；布局随 resize 重算（去抖约 50ms），80→120→80 无残留破版 | Pilot 尺寸断言（(80,24) 六页与帮助页、(70,20) 降级提示、(80→120→80) resize 无残留破版）+ §4.5 人工矩阵 |
| AC31 | 无色模式可读：`NO_COLOR=1` 与 `TERM=dumb` 下正常渲染与退出，状态语义以「符号 + 文字」双编码可辨（不依赖颜色），无转义序列垃圾输出；语义色与符号映射表在位且完备——每条语义均有配对符号、文字标签与 256/16 色回退，亮色主题对比可读为约束列；16 色档语义可辨由 B1 ★判据与 §4.5 复核 | Pilot 环境变量注入断言 + 映射表静态断言 + §4.5 人工矩阵 + A.0 判据矩阵 |
| AC32 | 焦点可见与可预期：任意时刻恰一个可见焦点指示；Tab/Shift+Tab 顺序 = 页面阅读顺序；切页返回后焦点恢复离开时位置；模态（确认框/组合流对话框/队列编辑器/续跑面板）打开时焦点落于首个可交互控件、内 Tab 固定、Esc 可退；列表刷新与快照应用后滚动位置与选中集合边界夹取、消失选中项移除并提示 | Pilot 焦点序列断言（可见性/Tab 顺序/切页恢复/模态初始焦点与固定/Esc 退出/刷新后滚动与选中夹取） |
| AC33 | 空态与加载态：六页与组合流面板空态显示说明文案 + 下一动作键提示（不以空表头呈现）；过滤无匹配显示「Esc 清除」提示；页面首拉/刷新在途显示含静态文字的加载指示 | Pilot 逐页空态/加载态/Esc 清除断言 |
| AC34 | CJK 与宽字符显示：中文文件名/长文本、emoji 与组合字符（grapheme）在列表、详情与能量表的列对齐不因宽字符（按 2 列计）错位；超宽以 `…` 截断不破坏对齐；状态栏含 CJK 不破版 | test_tui_ui 渲染断言（截断/补位走 Textual/Rich 内建显示宽度，不另引宽度实现） |
| AC35 | 文档交付：`web/tui/README.md`（中文）九节在位——依赖与终端要求（Required/Enhanced/Optional/Unsupported 四行式合同）、安装与启动、快速开始、配置、快捷键、终端兼容（B1 结论）、故障排查、开发、测试；BiDi/RTL 应用级不支持与屏幕阅读器支持受限写入终端兼容节；快捷键节与键位总表一致 | §4.5 文档审查（README 九节与终端合同逐项核对）+ test_tui_ui README 快捷键节与键位总表一致性断言 |
| AC36 | 状态栏键位提示：右段常显当前页键位提示，内容为帮助页键位集的子集，六页逐页与帮助页一致；提示随页面切换即时更新 | test_tui_ui 逐页状态栏提示断言（提示集 ⊆ 帮助页键位集）+ 键位总表与帮助页一致性断言 |
| AC37 | 启动失败关闭：交互模式 stdout 非 TTY 时在进入全屏前向 stderr 打印单行错误并以非零码退出（提示改用 `--headless`）；`--headless` 不受影响 | test_tui_bootstrap 子进程断言 + §4.5 人工 pty 项 |

## 2. 任务拆解

### 2.1 批次总览与提交序列

实施前先以独立 docs 提交把本计划入库（文件名 `docs/plans/tui-v1-plan.md`，
匹配发布闸门 `check_plan_status.py` 无参扫描的 `*-plan.md` 模式；不计入
30 个实施任务。原 `tui-assessment/` 四份基线已于 2026-11-12 随延后决策清理
移除，本计划为唯一文档基线）。之后 30 个实施任务、9 个批次；
批次 A（守护进程侧）与 I（CLI）独立于 TUI 主线，可先行或并行。每个任务一个
功能提交（实现与其直接测试同属该功能变更）；A1 拆为 `docs(api)` 与
`test(api)` 两个提交；文档、纯重构、进度同步与契约闸门更新单独提交：

```text
0 计划入库(docs，不计入 30 个任务)
A 守护进程侧前置(6) ──┬──> F2/F3（拒重与停止语义）──┐
B 终端spike(1) → C 骨架/传输(6) → D reducer(2) → E 引导(1) ─┴──> G UI(7) → H 集成收口(2)
                                        F 命令层(3) ──────────┘
I CLI 更新命令(2)（独立，可并行）
C6 字体分发 → C5 部署包纳入 → H2（发布门槛）
```

C2/C3/C4/D1/D2 不依赖 Textual，可与 B1 并行；C3 的 A 批新码依赖 A1；只有 C1
的依赖钉版与 G 批视图层等待 B1 结论；C6 在 C1 后、C5 前完成（字体资源先随
`web/tui/` 入库，经 C5 纳入打包脚本后随 `web/tui` 整目录复制带上）；C5 在 C1 后、H2 前完成；G7 在
C/D/F 后、H1 前完成。

### 批次 A：契约与守护进程侧前置（TUI 无关，先行落地）

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| A1 | 契约文档 diff：`openapi.yaml` 新增 3 个 409 语义错误码（续跑在途拒重 `RESUME_ALREADY_PENDING`、组合流来源在途拒重 `WORKFLOW_SOURCE_ACTIVE`、重启重复受理 `RESTART_IN_PROGRESS`，35→38）；`/history/{id}/resume`、`/workflows/conformer-refinement`、`/system/restart`、`/executions/{id}/stop` 端点 description 钉死检查序、拒重/受理闩与网关错误映射（409/502/504/500 的触发条件）；`web/tests/test_error_codes.py` `CONTRACT_CODES` 同步 38（静态闸门随实现扩，A4/A5/A6 落地时保持绿） | 契约 SSOT 先行；续跑检查序 = 入口 404 → 同源在途 409 → 资格复探 422 → 满员 409 → 建任务/入席；组合流检查序 = 字段 422 → crest 503 → 满员 409 → 来源在途 409 → 来源形态/输入 422；停止：作业不存在/全部已终态 409，连接失败 502、超时 504、解析失败 500 均用 `INTERNAL_ERROR`、以 HTTP 状态与 `details` 区分触发条件（稳定码不扩容，仍 35→38）；错误码命名以本提交定稿 | `docs(api): 增补续跑组合流拒重与重启受理闩三错误码` + `test(api): 同步 CONTRACT_CODES 至 38` | M |
| A2 | R-H3 修复：`services/workflows.py` 组合流自动提交路径 `emit("pending.snapshot", None)`（`:281`）改为复用 `dispatcher._emit_pending_snapshot()`（`web/src/engine/dispatcher.py:810-812`），必须发真实快照，不得省略；**测试**：该路径不再产生 null 载荷；Web 侧以人工清单核对 `web/frontend/src/stores/events.ts:265-266` 的 `pending.snapshot` 赋值分支（前端当前无测试运行器，列入 §4.5） | Web 与 TUI 双客户端受益；TUI null 防御仍保留（纵深） | `fix(services): 修正组合流自动提交路径的空快照` | S |
| A3 | R-H5 修复：`dispatcher.stop_execution` 每执行 cancel 在途闩（dict + 锁；闩置位/复位在锁内，`gw.cancel` 在锁外执行；成功保持到终态，任何异常/超时释放）；已终态保持幂等 409；Gateway 错误分型——新增 `GatewayNotFound`/`GatewayUnavailable`/`GatewayTimeout`/`GatewayProtocol`（CLI/HTTP 两实现共同填型）：CLI 以 `hq job list --all` 确认 id 缺席或稳定 stderr 模式判 not-found，`subprocess.TimeoutExpired` 判 timeout，`OSError` 判 unavailable，非 JSON 判 protocol；HTTP 以 404 判 not-found、连接异常/timeout/非 JSON/5xx 分别填型；「作业不存在/全部已终态」映射 409 `TASK_STATE_CONFLICT`，连接失败 502、超时 504、解析失败 500（均用 `INTERNAL_ERROR`，以 HTTP 状态与 `details` 区分，不伪装成冲突）；**测试**：在途二次调用 409、终态 409、already-finished/job-not-found 409、HQ 不可达 502/超时 504/解析失败 500、失败后闩释放可重试；CLI 假 hq 与 HTTP MockTransport 各自覆盖四类分型 | TUI 停止命令的读回兜底保留为纵深防御；禁止按全部 `GatewayError` 一律映射 409 | `fix(engine): 增加停止执行受理闩与网关异常映射` | M |
| A4 | R-B2 续跑拒重：`services/resume.py confirm` 先做只读快速查重（命中即 409），随后资格复探与满员检查；进入 `get_db().exclusive()`（`web/src/store/db.py:54-61`，进程内跨仓储互斥上下文，非 DB 事务）后重新查重、重新核对 `pending_seat_limit`，并在锁内完成「建任务 + 写注入副本 + 核验 + 入席」；判据 = 该源执行存在仍占席的续跑任务，或存在 `resumed_from` 指向该源执行且未终态的执行行（残留未入席任务行不阻塞）；核验失败回滚任务行与输入副本，回滚失败按残留处理；重复 409 `RESUME_ALREADY_PENDING`、锁内满员 409 `PENDING_CAPACITY_FULL`；锁内只含 DB 行变更与小文件写入，120s 探针在锁外；**测试**：重复确认 409、首确认 200、并发双请求只建一任务一席且不超席位上限、失败残留任务行后可再次续跑、终态后可再次续跑 | 自然键优先，不做通用幂等键；导入不加键（显式重复导入为产品语义）；查重先于资格复探；依赖单守护进程（`exclusive()` 为进程内互斥，同进程多 worker 不影响判重；多进程部署不在 v1 范围） | `feat(services): 实现断点续跑按 resume_of 在途拒重` | M |
| A5 | R-B2 组合流拒重：`services/workflows.py submit_conformer_refinement` 在既有检查序中插入「同一 `source_candidate_id` 存在非终态 workflow → 409 `WORKFLOW_SOURCE_ACTIVE`」，位置固定在满员检查之后、来源形态/输入检查之前；进入 `get_db().exclusive()` 后完成「来源在途复检 → 容量复检 → crest 任务/xyz → set_crest_binding/save_template → workflows().create → seats().append」整段，任一步失败清理已建任务/文件/模板并入原异常上抛；**测试**：重复提交 409、并发双请求只建一个 workflow 一个 crest 任务且无孤儿输入/模板、并发不超席位上限、终态 workflow 后可再建、检查序不改变非重复请求的既有 503/409/422 语义 | 同 A4 口径；扩展既有 `workflows_repo`，新增按 `source_candidate_id` 查非终态行的方法（复用既有 `workflows` 表，无迁移）；依赖单守护进程（同 A4 口径） | `feat(services): 实现组合流按来源候选在途拒重` | M |
| A6 | R-B3 受理闩：`services/restart.py guard()` 增进程内已受理标志（与 `UPDATE_IN_PROGRESS` 对称的 409 `RESTART_IN_PROGRESS`；拉起失败复位；SIGTERM 被忽略时保持闩直到进程重启，不二次拉起）；**测试**：闩内二次调用 409 且不二次拉起脚本（Popen 计数）、拉起失败复位、拉起成功但自退调度失败时闩保持并输出诊断 | v1.1 重启命令前置的独立加固，不参与 v1 验收；A1 与 A4/A5/A6 有码依赖，回滚顺序见 §5.2 | `feat(services): 增加服务重启受理闩` | S |

### 批次 B：终端 spike（实施第 0 步验证）

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| B1 | Textual 终端能力 spike：临时 venv（uv 国内镜像，不改 requirements）装 spike 版本，最小 app 在 Windows Terminal（WSL 会话）、tmux、SSH 三环境过判据矩阵——★CJK 宽度（中英混排表格对齐）、★颜色降级（truecolor/256/16 三档语义可辨、16 色可读）、NO_COLOR 与 TERM=dumb 降级行为实测（内建降级程度与短板留痕，非 ★）、SGR 鼠标（tmux mouse off 不误触发）、最小尺寸 80×24 与低于门槛表现（内建行为实测留痕，非 ★）、crash 后终端恢复（内建行为实测留痕，非 ★）、tmux resize/detach-attach、Ctrl+S/Ctrl+Q 流控恢复、括号粘贴、按键编码（`Shift+J/K`、`Ctrl+D/U`、`Space`、`Esc`、`1–6`、`d`、`W`、`?` 等 §1.3-9 全部组合键）；三环境须注明终端/版本/字体/宽度，SSH 目标为本机 sshd 或局域网主机；★任一硬否决 → 切 Ratatui，按「客户端整体重写或 Python 核心 + Rust 前端双进程桥接」重估 C–H 批，结论与实测记录留痕本计划附录；三环境可用性在开工前确认 | 钉死生产版本号（C1 依据）；按键编码不通过时先调整键位表；非 ★ 项不阻塞开工，内建不足在 G1 补实现；Textual 对 NO_COLOR/TERM=dumb、最小尺寸以下、crash 后终端恢复的内建行为实测结论写入 A.0，作为 G1 实现与 AC16/AC30/AC31 验证的现场依据（非 ★） | `docs(tui): 留痕终端能力 spike 判据矩阵` | M（1.5） |

### 批次 C：TUI 骨架、传输层、字体与部署包（无 UI）

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| C1 | 包骨架与依赖：`web/tui/`（`__main__.py` 入口、`--headless` 模式骨架与 `<workspace>/tui-state.json` 状态导出、连接地址 `--addr`/`G16WEB_TUI_ADDR`（默认 `http://127.0.0.1:8300/api/v1`）、非回环警告与确认、`--allow-remote`、`--no-launch`；交互模式入口在 stdout 非 TTY 时打印单行错误并退出非零（提示改用 `--headless`），先于进入全屏失败关闭，AC37）；§1.3-1 状态/计数器字段表落到导出与 append-only 记录；`requirements.txt` 增 `textual==<B1 钉死版本>` 及运行时传递依赖精确版本（过滤 dev/测试依赖）；**测试**：入口参数解析、非回环警告/确认分支、状态导出原子写与字段完整性、命令计数器 `started` 先写、stdout 非 TTY 拒绝启动（AC37）、`web/tui` 全包 import 图不导入 `web.src`（用例落在 `test_tui_bootstrap.py` 与 `test_tui_import.py`） | 依赖走评审（B1 实测版本即生产版本）；TUI 不 import `web.src`；命令计数器 append-only 落盘（每行 flush/fsync，两种模式均写） | `feat(tui): 引入 TUI 骨架与 Textual 依赖` | M |
| C2 | SSE 解析器：httpx 流式读取；覆盖 CRLF、注释帧、多行 `data:`、`id` 非数字、`event` 缺失、`data` 非法 JSON（跳过单条不断流）、心跳/快照 id 0、`pending.snapshot=null`、未知事件、`retry:` 字段忽略（服务端已核实不发，出现则忽略）、UTF-8 多字节字符跨网络块（增量解码）；**测试**：逐类喂原始字节流断言，含在汉字/emoji 中间切块的用例 | 解析层与连接层分离；解码器使用增量 UTF-8 | `feat(tui): 实现 SSE 客户端解析器` | M |
| C3 | REST 薄层：错误体统一解析（`code/message/details`；非 JSON 4xx/5xx 回退为状态码 + 截断文本）、超时=结果未知语义、请求超时与重试禁令；分支码覆盖 tui-draft §2.4 全集（`PENDING_CAPACITY_FULL`、`SEAT_WINDOW_LOCKED`、`QUEUE_STATE_CONFLICT`、`TASK_STATE_CONFLICT`、`INVALID_MEMBERS`、`DEPENDENCY_*`、`INPUT_*`、`RESUME_NOT_ELIGIBLE`、`WORKFLOW_STATE_INVALID`、`CREST_EXECUTABLE_MISSING`、`NOT_FOUND`、`INTERNAL_ERROR`、`VALIDATION_FAILED` 及 A 批新码）；超时值按 §1.3-4 表；**测试**：MockTransport 200/204/4xx/5xx/非 JSON/超时矩阵 | 只对上述分支码做分支；其余按 `code+message` 原样展示；A 批新码依赖 A1 契约 | `feat(tui): 实现 REST 客户端薄层与错误体解析` | M |
| C4 | 连接层：无游标连接、看门狗 `max(60,2×心跳)`（随设置重算）、退避 1/2/5/10 封顶复位、重连先判实例（daemon pid/create_time 按 §1.3-3 三路取一，变化即实例变化；health 的 version 变化、归一化 `uptime_s` 回退超过 0.5s 或无法判定同按实例变化）、5s 无快照协议异常；**测试**：假时钟 + 假连接表驱动（心跳 300s/5s 边界、pid/create_time 变化与快速重启归一化判定）、EventQueue 状态事件不丢/progress-monitor 合并/队满背压/丢弃计数（512 容量与 257/300、513/600 两档） | 场景 A/B 的连接原语；EventQueue 策略独立单测；背压超阈值断开重连取快照 | `feat(tui): 实现连接层看门狗与快照重连` | M |
| C5 | 部署包纳入：修改 `scripts/package_release.sh` 将 `web/tui` 纳入 `gauforge/web/tui`；`docs/references/deployment.md` 写部署目录 TUI 启动命令（`cd <deploy> && .venv/bin/python -m web.tui`）；**测试**：`test_deploy_scripts.py` 断言包内 `web/tui`，解包目录启动 `--headless` 可拉起 daemon | 与 C1 分离的构建类提交；H2 发布门槛依赖本任务；不改变 update/self_update 的整 `web/` 覆盖语义 | `build(package): 将 TUI 模块纳入部署包` | S |
| C6 | 字体资源与分发：入库 `web/tui/assets/fonts/MapleMono-CN-Regular.ttf`（18,509,264 字节，SHA256 `0fcc5139…4085`）、`OFL.txt`、`SHA256SUMS`、`README.md`（来源/版本/安装命令/已知限制）；`docs/references/deployment.md` 增字体安装段（可选步骤，不安装不影响功能）；**测试**：`test_deploy_scripts.py` 断言包内四件套、`sha256sum -c` 通过、字体家族名仍为 `Maple Mono CN`（未改名）、全包静态检查无写 `~/.local/share/fonts` 或调用字体安装命令的代码 | 原样分发（OFL 声明 Reserved Font Name `Maple Mono`，禁止裁剪/子集化/改名）；v1 仅 Regular，粗体与 NF 图标登记为已知限制；二进制入库（仓库无 LFS），gzip 后约 8.0 MiB；实施顺序先于 C5 | `build(tui): 随包分发 Maple Mono CN 字体与授权` | S |

### 批次 D：reducer 与视图态（纯函数）

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| D1 | `TuiState` + `reduce`：15 类事件处理表（`update.*` 显式 no-op、未知原样）、快照重建（清快照外执行/停滞，候选/历史/队列/设置/组合流全部置脏）、null 防御、dirty 集合、Toast 按 id 去重、executions/history/seats 按主键去重、`last_frame_at` 取 `received_at`；**测试**：表驱动 + 幂等 + 空值 + 快照重建 + 列表置脏 + import 图静态检查（AC6 判据） | 事件全集常量独立持有副本，不依赖 `web.src` | `feat(tui): 实现事件消费纯函数 reducer` | L |
| D2 | `plan_effects` + `reduce_ui`：效果规划（Refresh* 推导，不执行 I/O）；视图态纯转移（焦点夹取、跨页勾选保留、重排锁定不变式、非 staged 门控、队列编辑器按 `unsubmitted`/`submitted`/`executing`/`completed` 分级、§1.3-4 确认矩阵的单飞/确认状态）；**测试**：效果推导、视图转移、三处门控 0 请求、重排类无二次确认 | 与 D1 同为纯函数，可并行开发；快照变化时退出本地重排缓冲 | `feat(tui): 实现效果规划与视图状态纯转移` | M |

### 批次 E：启动引导

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| E1 | 引导实现：地址解析（显式 `--addr`/`G16WEB_TUI_ADDR` 只探测不拉起；未显式时只读工作区 SQLite `listen_port`，缺失/锁定回落 8300）→ health 2s×3 → systemd（3s 超时）/`--no-launch`/引导标记 child pid/进程扫描均不拉起 → `fcntl.flock` 再检查 → detached 拉起（源码 `sys.executable -m web.src.main`；部署优先 `PROJECT_ROOT/.venv/bin/python`；`cwd=PROJECT_ROOT`、PATH 前置 `.venv/bin`、`G16WEB_HQ_BIN`（未设置时补 `.venv/bin/hq`）、`start_new_session`、stdin DEVNULL、env 透传、输出 `<launch-workspace>/tui-daemon.log`）→ 日志偏移解析实际端口 / 1s 轮询上限 30s → 诊断（日志路径/端口冲突）；systemd 判定与 `--no-launch`；引导锁记录 child pid/日志/偏移；workspace 比对（daemon 日志固定，TUI 诊断/状态/计数器按服务端目录可写切换）；会话中断线重走引导（先探测/标记/进程扫描防双拉）；退出不杀；hq 状态呈现（非 up 时状态栏提示不阻塞）；**测试**：假子进程注入 + 真实轻量子进程（隔离工作区、预置 `listen_port`、非 8300 端口）双形态、PATH/cwd、日志偏移/解析失败诊断、端口被占诊断、systemd 3s 超时、慢启动外部 daemon 只拉起一个、显式 `--addr`/远程不拉起、双 TUI 并发、锁残留恢复 | 部署形态解释器/端口/workspace/systemd 约定写入 I2 文档；C5 提供部署包 | `feat(tui): 实现守护进程启动引导` | M |

### 批次 F：命令层（13 常驻命令）

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| F1 | 派发框架：每资源单飞（资源键见 §1.3-4；在途禁用不排队）、§1.3-4 确认矩阵、超时基线读回流程（按 §1.3-4 表；基线快照在命令前采集）、失败反馈（code+message、details 诊断区）、warnings/normalized/duplicate 展示原语与按命令字段矩阵；命令计数器按端点 append-only（发命令前写 `started`，完成后追加结果，每行 flush/fsync，两种模式均写）；**测试**：单飞互斥、超时分支、基线读回序列、旧实体不误判、计数器落盘、请求挂起中止时 `started` 行已落盘 | UI 无关，headless 可测 | `feat(tui): 实现命令派发框架` | M |
| F2 | 命令 #1–#10 接入（导入/提交/建队/成员重排/提交队列/席位重排/移除整席/移除成员/停止/归档）；导入过滤规则（AC10：文件夹模式扩展名/隐藏路径段含文件名、文件模式 TUI 选择器过滤/提示、原始字节、2–10 回落、257/300 大批量重连、单文件/整批超阈值提示）；锁定席位不变式、staged 门控、队列编辑器状态分级接线；展示各命令实际响应字段；**测试**：每命令覆盖其实际 400/404/409/422/503 主分支 + 超时基线读回；停止另覆盖 500/502/504 与 409/终态/失败释放（依赖 A3）；导入边界 0/1/2/10/11、257/300、隐藏文件名、非 UTF-8 文件名跳过提示、BOM/CRLF/GBK、重复文件；文件夹成队读回只认新队列 id 与成员文件名；预置同名候选/队列不误判 | `PUT /pending/order` 响应整体应用；`queue_from_folder` 回落原因原样展示；多选顺序即成员顺序 | `feat(tui): 接入基础十命令` | L |
| F3 | 命令 #11–#13 接入（续跑预览/续跑确认/组合流）：预览面板自动拉取与 ineligible 六态文案（按 `(reason, probe.reason)` 选择；归档特判 `probe.reason="archived"`）、确认后只应用响应确认字段（含 `task_kind`）并展示 `warnings`；组合流对话框模板预填（并行拉取；模板结构化字段序列化 Link0）与本地校验（top_n 2–10、nproc 正整数、route 非空、link0 缺省或字符串数组）；**测试**：422/409/503、预览入口外 404、慢探针（>30s、上限 130s）、超时基线读回（新增席位 + `resumed_by` 新 id / 新 workflow id）、重复确认 409 展示（依赖 A4/A5）、归档/skipped 文案、模板拉取失败回落、失败后重拉 preview/队列不复用旧文本 | 预览恒 200 不当错误弹窗；组合流字段 422 先于 503 | `feat(tui): 接入续跑与组合流命令` | M |

### 批次 G：UI（Textual）

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| G1 | 布局骨架：六页导航（`1–6`）、状态栏（连接态/版本/hq/丢弃计数；空间占用经 `GET /storage/usage` 获取、状态栏可见时每 5 分钟刷新、超 `disk_usage_warn_gb` 阈值告警；右段常显当前页键位提示，内容为帮助页键位集的子集；分段省略优先级——空间占用最先省略、连接态与键位提示最后截断，分段超宽按显示宽度截断且边界完整）、帮助页（`?`）、退出确认与二次强制、SIGTERM/SIGINT/SIGHUP 清理路径、退出时有在途命令的结果未知提示（≤2s、不重发、不写 outbox）；最小尺寸门槛与降级（固定 80×24：低于门槛渲染单屏引导提示——列当前尺寸/所需最小尺寸/调整建议，不进入破版布局，恢复尺寸自动回到正常界面；尺寸存于状态、布局值全部由当前尺寸派生并在 resize 后重算（去抖约 50ms），无 80×24 之外的布局硬编码常量）；焦点基线（任意时刻恰一个可见焦点指示，Tab/Shift+Tab 按页面阅读顺序循环，切页返回后焦点恢复离开时位置，模态打开时焦点落于首个可交互控件、内 Tab 固定且 Esc 可退，列表刷新与快照应用后滚动位置与选中集合边界夹取）；空态与加载态基线（各页无数据显示空态文案 + 下一动作键提示、不以空表头呈现；首拉/刷新在途显示含静态文字的加载指示；过滤无匹配显示「Esc 清除」提示）；无色模式基线（`NO_COLOR`/`TERM=dumb` 下以 bold/reverse 渲染，状态一律「符号 + 文字」双编码，不依赖色相传达信息，语义色按 §1.3-13 映射表逐档回退）；输入与显示边界（输入框启用括号粘贴、按数据接收不触发动作键，超长粘贴可见截断提示；中文/emoji/组合字符按显示宽度参与列宽与截断，走 Textual/Rich 内建能力，状态栏含 CJK 不破版）；样式约定随 tcss 一次定稿并在六页复用（bold=标题/选中、dim=次要信息/时间戳、符号表意；语义色与符号映射表随本任务按 §1.3-13 定稿；Toast 同时上限 3 条、停留约 5 秒自动消退、不遮挡焦点与状态栏；边框从简，以间距与对齐分组为主；间距/边框/强调令牌统一，不做每页各写一套）；**测试**：Pilot 导航与退出路径、子进程信号测试、(80,24) 六页与帮助页断言、(70,20) 低于门槛提示与恢复、(80→120→80) resize 无残留破版、焦点序列断言（含 Esc 退出模态、模态初始焦点、刷新后滚动与选中夹取）、逐页空态/加载态与「Esc 清除」断言、状态栏当前页键位提示与帮助页子集断言、无色模式环境注入断言、语义色映射表静态断言、括号粘贴与超长粘贴截断断言、CJK/emoji/组合字符文件名截断与列对齐及状态栏 CJK 不破版断言 | `run_test(size=(120,40))` + `run_test(size=(80,24))` + `run_test(size=(70,20))` | `feat(tui): 实现布局骨架与状态栏` | L |
| G2 | 候选页：文件树导入（`i`，过滤规则 UI 侧过滤、按字节读；文件模式选择器按 `.gjf/.com` 过滤/提示）、锚点+范围多选（`Space/Shift+J/K/v/a`）、详情面板含校验预览（F4）、原始输入只读视图、组合流入口（`f`）与对话框（模板/参数/确认）、列表分页与 `warning_count`；**测试**：Pilot J1 全程 9 键、J7 确认 1 键、过滤交互、分页/选择集保持、257/300 批量导入交互 | 多选跨页保留勾选；选候顺序即队列成员顺序 | `feat(tui): 实现候选页导入多选校验预览与组合流入口` | L |
| G3 | 待执行页：席位/成员树、`Enter` 展开、`J/K` 单步即时提交、`o` 重排模式（Enter 提交/Esc 取消）、`d` + `y` 移除整席或席位成员、锁定席位/staged 两处门控（0 请求拒绝）、待执行页可见时每 30s 或快照后拉 `GET /pending`、冲突或快照变化后刷新并退出重排模式；**测试**：Pilot J2（单步 1 键、撞锁定 0 请求、跨多位 3 键）、J3、移除 2 键 | 门控提示文案与 Web 对齐；队列编辑器门控由 G7 承载；重排类无二次确认 | `feat(tui): 实现待执行页席位排序成员门控与重排模式` | L |
| G4 | 执行页 + 历史页：执行卡（progress/monitor 合并显示、`x` 停止 `y` 确认、可见时 3s 拉 `GET /executions?state=running`）、历史列表/详情（`resumed_from/resumed_by` 只读、`z` 归档、脏时刷新）、历史分页与排序、原始输入只读视图、续跑面板（`r`，failed/skipped 可开，归档只读预览，六态按 `(reason, probe.reason)`，`y` 确认）；**测试**：Pilot J4 2 键、J6 2 键、ineligible 确认禁用、分页/排序、归档/skipped 入口 | 可见页对账接线（执行页 3s、历史脏时） | `feat(tui): 实现执行页历史页监控停止归档与续跑` | L |
| G5 | 队列页 + 设置只读页 + 组合流面板（`W`：列表/详情/能量聚合文本表；列表默认 20、limit 上限 100）；**测试**：Pilot 页面切换与只读断言（无写入口） | 能量表两端点文本化（§1.2 事实）；队列编辑器由 G7 承载 | `feat(tui): 实现队列页设置只读页与组合流面板能量表` | L |
| G6 | 长按组件（3 秒进度/松手取消/无运行即时确认，仅测试覆盖，v1.1 重启接线）、按键总表全量接线核对、状态栏当前页键位提示接入、快捷键帮助、信号路径与键位一致性、`web/tui/README.md` 交付（中文，九节：依赖与终端要求——Required「UTF-8 终端、80×24 最小」/Enhanced「truecolor、括号粘贴」/Optional「同步输出、OSC 8 超链接，缺失自动降级」/Unsupported「应用级 BiDi/RTL，由终端决定」四行式合同、安装与启动（源码/部署两形态）、快速开始、配置（环境变量）、快捷键（与键位总表同源）、终端兼容（B1 结论矩阵）、故障排查（引导诊断/`tui-daemon.log`/常见问题）、开发（模块分层）、测试（headless/集成闸门）；屏幕阅读器支持受限以 headless 状态导出为结构化替代并写入文档）；**测试**：长按假计时器、按键总表与帮助页一致性断言、状态栏当前页键位提示与帮助页一致性断言、README 快捷键节与键位总表一致性断言 | 长按为模式基线（tui-draft J5） | `feat(tui): 实现长按组件帮助与按键总表收口` | M |
| G7 | 队列编辑器：创建态（名称、已选候选成员 2–10）、`unsubmitted` 可改名称/`skip_failed`/成员顺序、`submitted` 仅成员顺序（名称/`skip_failed` 只读）、`executing/completed` 只读；成员顺序本地移动；`Enter` 保存、`s` + `y` 提交队列为独立动作，不提供合并「保存并提交」；成员增删不提供；锁定/staged/只读本地校验与 0 请求门控；**测试**：Pilot J1 建队段、submitted 成员重排、executing/completed 只读 0 请求、创建态 2–10 校验、保存成功提交失败保持 `unsubmitted` | 状态分级与 Web 对齐；成员增删不在 v1 编辑器范围 | `feat(tui): 实现队列编辑器与成员顺序门控` | M |

### 批次 H：集成测试与收口

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| H1 | 集成场景 A/B/C（§4.3）：`test_tui_integration.py`；fail-not-skip fixture（收集/会话阶段断言 `target/release/hq` 存在并 `pytest.fail`；钉 `G16WEB_HQ_BIN=<repo>/target/release/hq`、PATH 前置）；场景 A 客户端透明性（headless → 读 `tui-state.json` → kill -9 → 命令计数器逐行 → 重启 0 键恢复 → 列表刷新 → 终态推进 → 257/300 文件由测试进程经 REST 批量导入，TUI 断开/重连后列表完整、命令计数不变）；场景 B 启动引导（PATH/cwd、非默认端口、日志偏移、慢启动外部 daemon、拉起/恢复/退出不杀/端口冲突/显式 `--addr` 与远程不拉起/systemd 真实判定/启动中 daemon/双 TUI 并发/锁残留）；场景 C 多客户端并发（TUI 侧用 Textual Pilot 连接真实 daemon，另一路 REST 并发；合法重排 last-write-wins + 移除/锁定/提交冲突产生 400/409）；信号与在途命令退出；fake g16 复制为临时 bin、`G16_FAKE="sleep=1;steps=10"`；结束断言 TUI 集成模块 skip=0 | 隔离工作区 + 场景 A 内联 uvicorn 指定端口；场景 B 由 TUI 拉起（预置 `listen_port`）；全量套件 skip 逐条登记 | `test(tui): 覆盖集成场景客户端透明性启动引导与并发` | L（3.5） |
| H2 | 全量闸门 + 部署包冒烟（§4.4）+ 人工矩阵（§4.5）留痕 + CHANGELOG.jsonl unreleased 汇总核对 + progress.json 收口；附录回填验收记录与 AC1–AC37 勾验 | 闸门命令输出留痕；核对实际执行数不只看 passed；部署包解包含 `web/tui` 且可启动 | `docs: 回填 TUI v1 验收记录并同步进度` | L（2） |

### 批次 I：CLI 更新命令（独立交付，可先行/并行）

| ID | 任务 | 产出 / 关键点 | 提交 | 规模 |
|---|---|---|---|---|
| I1 | 项目 CLI：`web/src/cli.py`（`python -m web.src.cli`）注册 `update check/apply/proxy` 子命令；经既有 REST 端点（`GET /update/status`、`POST /update/check`、`POST /update/apply`、`PUT /update/proxy`）复用服务侧同守卫/同文案，**不直接运行 `UpdateService.run_pending()`、不在 CLI 进程执行自退/覆盖部署目录**；服务定位 `--addr` > `--home`（默认 `G16WEB_HOME`）> 只读 SQLite `listen_port`；服务未运行时 `check/apply/proxy` 均以退出码 3 报「服务未运行」并提示 `update.sh` 兜底；apply 后轮询 `/update/status` 与 `/system/health`，报告完整阶段与失败原因；端口变化时重读 SQLite `listen_port`，库缺失/锁定回落 `--addr`；退出码：0 成功、1 业务失败、2 参数错误、3 服务不可达、4 超时；**测试**：子命令矩阵（服务运行/未运行、守卫 409 文案、check 三分支、proxy 落盘形态、apply 阶段与端口变化、SQLite 读取回退、`--home` 与 systemd 环境不一致） | CLI 进程独立于服务存活；不新增 REST 契约；`apply` 的编排权在服务进程；更新执行口径以本条为准——CLI 经 REST 复用服务侧更新语义，tui-draft §8「CLI 直接复用 `services/update.py` 的 UpdateService」不再适用 | `feat(cli): 注册项目 CLI 更新命令` | L |
| I2 | 文档：`docs/references/deployment.md` 补 CLI 更新入口（与 WebUI 更新卡、`update.sh` 兜底的关系）、systemd/地址约定（`G16WEB_SERVICE_UNIT`、`--no-launch`、`G16WEB_TUI_ADDR`）；TUI 部署目录启动命令由 C5 承载，本任务只引用；roadmap 功能清单登记 | TUI 永不纳更新的渠道分工写明；I2 在 I1 接口定稿后落地 | `docs: 补充部署文档的 CLI 更新入口与 TUI 启动` | S |

## 3. 依赖关系与风险预判

### 3.1 依赖图与关键路径

```text
0 文档入库 ──> A1 ──> A4/A5/A6 ──> F3（拒重）/F2（停止语义 A3）
                A3 ─────────────────> F2
B1 ──> C1 ──> C6 ──> C5 ──> H2
B1 ──> C1 ──> G1..G7
C2/C3/C4/D1/D2（不依赖 B1，可与 B1 并行；C3 依赖 A1 新码）──> E1/F1
C+D+E+F ──> G1..G7 ──> H1 ──> H2
I1 ──> I2（仅依赖既有 update 域）
```

**关键路径**：`max(A, B1, C2–C4/D) → C1/F → G → H`；G 批是最大单批（最低档
12 人天）。C2/C3/C4/D1/D2 在 B1 期间即可开工，B1 只阻塞 C1 的依赖钉版与 G 批
视图层；若 ★ 否决并选择整客户端 Rust 重写，Python 传输/命令层不再复用；若
选择双进程桥接，按桥接边界重估复用面。

**阻塞点**：

- C1 依赖 B1（版本钉死与 go/no-go）；G 批依赖 C/D/F 全部；G7 依赖 D2 的视图
  态与 F2 的命令层；
- C6 依赖 C1、先于 C5（字体资源须先入 `web/tui/`）；C5 依赖 C1，先于 H2
  （否则发布包不含 TUI 与字体）；
- F2/F3 依赖 A3/A4/A5 合入（服务端语义先行，TUI 只做展示与读回）；
- C3 的 A 批新码依赖 A1 契约定稿；
- H1 依赖 `cargo build --release` 产物在位（fail-not-skip，不静默跳过）与
  场景 B 的端口/引导 fixture；B1 依赖 Windows Terminal（WSL）、tmux、SSH
  环境可用；E1/H1 另需 systemd 环境可用；
- I2 依赖 I1 的接口定稿；A6 不构成 v1 阻塞（v1.1 前置的独立加固）。

### 3.2 风险登记表

| # | 风险 | 影响 | 概率 | 缓解 / 兜底 |
|---|---|---|---|---|
| R1 | spike ★判据否决（CJK 宽度错位/16 色不可读） | 客户端整体返工 | 低 | 预注册判据（B1）；切 Ratatui 按「整客户端重写或 Python 核心 + Rust 前端双进程桥接」重估 C–H 批与发布形态；B1 go/no-go 在 C1/G 开工前完成，C2–C4/D 可与 B1 并行（否决则重估复用面） |
| R2 | textual 版本/传递依赖升级破坏 API/行为 | 回归 | 中 | requirements 钉死 B1 实测版本及运行时传递依赖；升级单独提交全量回归 |
| R3 | 拒重「在途」判定竞态（终态瞬到/事务窗口） | 误拒或漏拒/双写 | 中 | A4/A5 用 `get_db().exclusive()` 包住「查重 + 建行 + 入席/建 workflow」；并发双请求与残留任务行专测；锁内只含 DB 行变更与小文件写入，120s 探针在锁外；单守护进程前提写入计划 |
| R4 | 启动引导双实例/端口冲突/拉起失败/systemd 误拉/环境缺失/锁残留 | 服务起不来或误拉 | 中 | 只读 `listen_port` 发现目标端口；引导标记 child pid + 进程扫描识别启动中/外部实例；显式 `--addr`/远程不自动拉起；systemctl 3s 超时；`flock` 双检；场景 B 覆盖慢启动、非默认端口、端口占用、双 TUI 并发、锁残留 |
| R5 | SSE 突发（批量导入 >256、monitor 高频）断开 | 视图闪断 | 中 | §1.3-6 五部件分层 + 状态通道 512 + progress/monitor 合并 + 背压；EventQueue 不丢/淘汰/背压单测；257/300 与 513/600 用例；单文件/整批超阈值提示；「导入大批后断线重连一次」为可接受路径，最终状态以 REST/快照一致为准 |
| R6 | 续跑确认失败残留任务行（失败前副作用） | 用户困惑/误判拒重 | 低 | A4 判据排除未入席残留行；核验失败优先回滚任务行/输入副本，回滚失败按残留处理；面板文案注明「失败可能残留未入席任务，以席位为准」；读回以 `GET /pending` 新增席位 + `resumed_by` 新 id 为准 |
| R7 | 组合流 crest 环境缺失（503）在开发环境必现 | 联调受阻 | 中 | 503 分支单测 mock；联调用 `crest_root` 指向 fake crest bin（镜像 fake g16 做法） |
| R8 | e2e 集成静默跳过（hq 缺失）虚高 | 闸门失真 | 高 | fail-not-skip fixture + `G16WEB_HQ_BIN` 钉死 + TUI 集成模块 skip=0；全量套件 skip 逐条登记 |
| R9 | Pilot 快照测试脆弱（动态 id/时间戳） | 测试维护负担 | 中 | 快照断言前剥离动态字段；布局断言用结构选择器而非像素 |
| R10 | 人工矩阵项遗漏（tmux/SSH/按键编码差异） | 上线后体验问题 | 中 | §4.5 清单逐项留痕；B1 按键编码矩阵；AC 项未过按缺陷修复，观察项未过登记为已知限制，不伪装成通过 |
| R11 | A 批改动波及既有测试（resume/workflow/restart/stop 链）与 Web 行为 | 回归 | 中 | 每提交全量 pytest；行为收紧（拒重/409）语义在契约 diff 中先定，`CONTRACT_CODES` 与实现同批；Web 重复续跑/组合流/停止/重启用例列入人工清单 |
| R12 | 快照不覆盖列表，重连后长期显示旧列表（R-H2） | 视图陈旧 | 中 | D1 快照置脏全部列表；AC14/场景 A 断言可见页刷新 |
| R13 | TUI 与 WebUI 并发写同一资源 last-write-wins（R-H6） | 覆盖他人修改 | 中 | 写面限制（不写设置、队列只重排成员）；合法重排按 last-write-wins，冲突（移除/锁定/提交）后刷新并退出重排模式；场景 C 分别验证；已知限制写入文档 |
| R14 | 输入校验 warnings/normalized/duplicate 未展示 | 用户无感地接受被改写/带警告的输入 | 中 | AC13；F2/F3 按命令字段矩阵展示；导入逐文件、提交/队列提交/续跑确认逐条展示 |
| R15 | 信号退出/端口变化/在途命令退出处理不当 | 终端残留、误发命令、失联 | 中 | G1 信号清理与 2s 退出上限；E1 只读 `listen_port`/日志端口与 `--addr`；AC1/AC16 与人工矩阵验证 |
| R16 | 部署包不含 `web/tui` 或拉起环境缺 cwd/PATH/hq 定位 | 目标版本无法交付 TUI | 高 | C5 纳入打包；E1 设 cwd/PATH/`G16WEB_HQ_BIN`；H2 解包/启动冒烟；AC18 |
| R17 | 续跑/停止/导入客户端超时早于服务端最坏耗时 | 误报结果未知/重复操作 | 高 | 续跑 130s（探针 120s）、停止 20s（Gateway 15s）；导入/队列提交按 §4.1 实测最坏耗时校准；慢探针/慢 cancel 用例；AC22 |
| R18 | headless 无可观测状态导出/计数器未落盘 | H1 断言失真 | 中 | `tui-state.json` 原子导出；计数器 `started` 先写、每行 flush/fsync；AC20 |
| R19 | 队列编辑器无归属任务/状态分级错误/保存提交耦合 | J1 无法闭环或部分成功状态不清 | 高 | G7 独立任务；Web 状态分级对齐；保存与提交分离；AC19/AC27 |
| R20 | EventQueue 状态事件溢出策略缺失 | 丢状态或无限增长 | 中 | 状态通道 512 + 背压；超阈值重连取快照；257/300、513/600 单测；AC29 |
| R21 | 按键编码不可区分/UTF-8 多字节跨块 | 键位返工/CJK 乱码 | 中 | B1 按键矩阵；C2 增量解码测试；AC24 |
| R22 | I 批独立交付却阻塞目标版本冻结 | 发布耦合 | 低 | I 批独立发布；I1 不阻塞目标版本冻结；I2 随 I1；关键路径不包含 I |
| R23 | 创建型命令超时读回误判旧实体 | 假成功/重复操作 | 高 | §1.3-4 命令前基线 + 新实体 id 判据；AC25 预置同名候选/队列/旧 workflow/旧 `resumed_by` 用例 |
| R24 | 在途计划阻塞发布闸门 | patch 发布失败 | 中 | 实施期 patch 以显式计划路径运行 `check_plan_status.py`；目标版本冻结前回填本计划终态后跑无参全量；§5.1 固定该口径 |
| R25 | 大工作区 `storage/usage` 全树遍历拖慢服务 | 状态栏/I/O 抖动 | 中 | 状态栏 5 分钟低频刷新；按需手动刷新；大工作区人工/性能用例 |
| R26 | 续跑入口与 Web 历史页不一致导致行为预期偏差 | 用户误解/测试口径漂移 | 中 | F5/AC28 明确 TUI 入口为 failed/skipped（归档只读预览），文案按 `(reason, probe.reason)`；人工矩阵核对 |
| R27 | 字体分发：包体增大、OFL 授权/保留字体名不合规、用户终端未采用字体、粗体缺失 | 包体积膨胀/合规风险/观感不一致 | 中 | 只随包原样分发 Regular（18.5 MB，gzip 约 8.0 MiB）；`OFL.txt`/`SHA256SUMS` 同目录，禁止裁剪/子集化/改名；安装为用户可选步骤并在部署文档注明；粗体与 NF 图标登记为已知限制 |
| R28 | Textual 内建行为与验收预期不符（NO_COLOR/TERM=dumb 降级程度、最小尺寸以下表现、crash 后终端恢复、焦点循环细节） | UI 验收返工 | 中 | B1 对上述行为做非 ★ 实测并留痕 A.0；G1 按 §1.3-12～§1.3-14 实现，以 Pilot 尺寸、焦点与环境注入断言收口（AC16/AC30/AC31/AC32）；内建不足处在 G1 补实现（清理路径 guard/样式），不以已知限制替代验收 |
| R29 | 长 CJK 文件名/长错误文本/emoji 与组合字符撑破列宽与状态栏（宽字符按 2 列计的截断缺失） | 对齐错乱/信息误读 | 中 | AC34 渲染断言；截断与补位统一走 Textual/Rich 内建显示宽度（不另引宽度实现，遵守框架既定依赖）；状态栏内容精简、CJK/emoji 场景纳入 §4.5 观感项 |

### 3.3 排期与里程碑

| 阶段 | 内容 | 最低人天 | 完成闸门 |
|---|---|---|---|
| 0 | 计划入库 | 0.5 | docs 提交 |
| A | 守护进程侧前置 | 5 | pytest 全绿；A3/A4/A5 合入（F2/F3 开工前置） |
| B | spike | 1.5 | ★ 判据结论；按键编码结论；C1 版本钉死 |
| C | 骨架/传输/字体/打包 | 5 | C1–C6 单测；C5 包内含 `web/tui` 与字体资源 |
| D | reducer/视图态 | 3 | D1–D2 单测 |
| E | 引导 | 1 | E1 单测 + 场景 B 预演 |
| F | 命令层 | 4 | F1–F3 单测 |
| G | UI | 12 | G1–G7 Pilot |
| H | 集成收口 | 5.5 | 场景 A/B/C + 部署包冒烟 + 人工矩阵 + AC1–AC37 |
| I | CLI 更新 | 2.5 | 子命令矩阵（独立发布，不阻塞目标版本） |
| 小计 | 最低档 | 40 | — |
| 缓冲 | 约 20% | 8.0 | — |
| **合计** | **单人（含缓冲）** | **约 48** | 9.6 周 |

**里程碑**：M0 文档入库 → M1 A 批合入（F2/F3 前置）→ M2 B1 go/no-go（C1/G
前置）→ M3 C/D/E/F 完成（含 C6 字体与 C5 打包）→ M4 G 完成（含 G7 队列编辑器）→
M5 H 验收（AC1–AC37）→ M6 目标版本冻结。I 批独立交付，可与目标版本同版或在其后
单独发布，不参与 M5/M6 冻结判定。C2/C3/C4 与 D1/D2 在 B1 期间并行，实际工期
以 B1 结论和 L 任务上浮修正。

## 4. 测试与验证方案

### 4.1 单元测试（新增 11 文件 + 扩 6 文件，全部离线，本地进程不触外网）

| 文件 | 覆盖 | 手法 |
|---|---|---|
| `test_tui_sse_parse.py`（新） | C2 解析器逐类（CRLF/注释/多行 data/非法 JSON/id 0/null pending/retry 忽略/未知事件/UTF-8 多字节跨块） | 原始字节流喂入 |
| `test_tui_rest.py`（新） | C3 错误体解析、非 JSON 回退、超时=结果未知、tui-draft §2.4 分支码全集、超时表 | httpx.MockTransport |
| `test_tui_conn.py`（新） | C4 看门狗边界（心跳 300s/5s）、退避序列与复位、重连判实例（pid/create_time 三路取一变化与归一化 uptime 快速重启）、5s 无快照、EventQueue 512 容量/不丢/合并/背压/丢弃计数（257/300、513/600） | 假时钟 + 假连接 |
| `test_tui_reduce.py`（新） | D1 全量：表驱动/幂等/空值/快照重建/列表置脏/null 防御/update.* 不变态/未知事件/主键去重/reducer import 图静态检查 | 固定 `received_at` |
| `test_tui_view.py`（新） | D2 效果推导、视图转移、锁定席位/staged/队列编辑器状态分级三处门控 0 请求、确认矩阵、快照变化退出重排 | 纯函数断言 |
| `test_tui_bootstrap.py`（新） | C1 入口参数、`--addr`/`G16WEB_TUI_ADDR` 优先级、非回环警告/确认、状态导出字段与原子写、计数器 `started` 先写、stdout 非 TTY 拒绝启动（单行报错退出非零，AC37）、`web/tui` import 图；E1 探测→拉起→日志偏移解析端口→轮询→诊断、cwd/PATH/`G16WEB_HQ_BIN`、只读 `listen_port`、端口被占诊断、显式 `--addr`/远程不拉起、systemd 3s 超时/`--no-launch`、慢启动外部 daemon、启动中 daemon、双 TUI 引导锁、锁残留恢复、workspace 比对 | 假子进程 + 真实轻量子进程 |
| `test_tui_commands.py`（新） | F1–F3 单飞/确认矩阵/超时基线读回、13 命令错误矩阵（#1–#13，长按重启除外；每命令实际 400/404/409/422/503 主分支，停止含 500/502/504）、各命令字段、导入边界 0/1/2/10/11、257/300、组合流本地校验（含 link0）、续跑六态、慢探针、停止 20s、续跑确认 diff+`resumed_by` 新 id、超时读回预置同名候选/队列/旧 workflow/旧 `resumed_by` 用例、文件夹成队按新队列 id 与成员文件名读回、导入与队列提交最坏耗时基准（校准超时）、计数器 `started` 先写与挂起中止落盘 | MockTransport + 真实 store 夹具 |
| `test_tui_import.py`（新） | AC10 过滤规则（文件夹模式扩展名/隐藏路径段含文件名、文件模式 TUI 选择器过滤/提示、非 UTF-8 文件名跳过提示）、原始字节保真（BOM/CRLF/GBK）、多选顺序即成员顺序、257/300 批量、单文件/整批超阈值提示、队列成队回落原因、`web/tui` 全包不导入 `web.src` 的 import 闸门 | 表驱动 + 静态检查 |
| `test_tui_ui.py`（新） | G1–G7 Pilot：页面导航、J1–J7 键位序列、队列编辑器状态分级与保存/提交分离、长按假计时、分页/选择集、原始输入只读、信号/在途命令退出、续跑入口与归档/skipped 文案、(80,24) 六页与帮助页可用、(70,20) 低于门槛提示与恢复、80→120→80 resize 无残留破版（结构断言，不引入像素 golden 依赖）、焦点序列（可见性/Tab 顺序/切页恢复/模态初始焦点与固定/Esc 退出/刷新后滚动与选中夹取）、逐页空态/加载态与「Esc 清除」断言、状态栏当前页键位提示与帮助页子集断言、`NO_COLOR`/`TERM=dumb` 环境注入断言、语义色映射表静态断言、括号粘贴与超长粘贴截断断言、CJK/emoji/组合字符文件名截断与列对齐及状态栏 CJK 不破版、README 快捷键节与键位总表一致性断言（AC30–AC36） | Textual `run_test` + Pilot |
| `test_tui_integration.py`（新） | H1 场景 A/B/C：headless 状态导出、命令计数器、kill -9、0 键恢复、列表刷新、257/300 REST 批量导入后的断线/重连、启动引导（含慢启动/非默认端口/显式 `--addr`/远程）、systemd/锁/端口、双 TUI 状态与计数、Pilot 并发 last-write-wins 与冲突、信号/在途命令 | 真实守护进程子进程 + fake g16 + `target/release/hq` |
| `test_cli_update.py`（新） | I1 子命令矩阵：服务运行/未运行退出码 3、守卫 409 文案、check 三分支、proxy 落盘、apply 阶段与端口变化、SQLite 读取回退、`--home` 与 systemd 环境不一致 | MockTransport + 临时工作区 |
| `test_resume.py`（扩） | A4 拒重：重复 409、首确认 200、并发双请求只建一任务一席、残留任务行回滚/可再次续跑、终态后再续跑、慢探针超时 | 既有夹具 + 线程并发 |
| `test_workflow_crest.py`（扩） | A2 null 快照消失、A5 拒重/并发只建一个 workflow 一个 crest 任务/无孤儿输入与模板/检查序、终态后可再建 | 既有夹具 + 线程并发 |
| `test_system_restart.py`（扩） | A6 闩内 409、Popen 计数、拉起失败复位、自退调度失败诊断 | 既有夹具 |
| `test_dispatch_engine.py`（扩） | A3 停止在途闩/失败释放、终态 409、already-finished/job-not-found 409、HQ 不可达 502/超时 504/解析失败 500；CLI 假 hq 与 HTTP MockTransport 分别覆盖四类 Gateway 分型 | 既有夹具 + 假 Gateway + 假 hq |
| `test_error_codes.py`（扩） | `CONTRACT_CODES` 35→38、契约载体清单同步 | 既有静态闸门 |
| `test_deploy_scripts.py`（扩） | 部署包含 `web/tui`、解包启动、systemd unit 环境/PATH、TUI 启动命令；字体四件套在位、`sha256sum -c` 通过、字体家族名未变、包内无字体安装代码 | 既有脚本夹具 + 临时目录 |

### 4.2 协议与契约一致性

- 事件全集常量（15 类）独立持有副本，与 `docs/api/sse.md:35-49` 断言一致；
  契约 schema 校验复制 `conftest.py` 的 `load_spec`/`assert_contract_schema`
  写法，不 import `web.src` 内部（tui-draft §5.2 口径）。
- REST 形状断言覆盖 `warnings`/`normalized`/`duplicate`/`queue_fallback_reason`/
  `warning_count`、`parse_errors`、候选分页、历史分页与排序、原始输入端点、
  存储用量端点、38 个稳定错误码。
- `web/tui` 全包 import 图静态检查（不导入 `web.src`）作为独立测试；reducer
  另做 httpx/socket/`time`/`random` 的 import 检查，不依赖其他层。
- `tui-state.json` 与 `tui-commands.jsonl` 按 §1.3-1 字段表做 schema 断言；
  `tui-commands.jsonl` 首行必须是 `started`，完成后追加结果行。

### 4.3 集成测试（H1，真实守护进程子进程；场景 A/B 与断言见 tui-draft §5.3，场景 C 及 257/300 批量导入步骤为本计划扩展）

- **场景 A 客户端透明性**：隔离工作区以 `sys.executable -c` 内联 uvicorn 在指定空闲
  端口起守护进程（复用真实入口同一应用工厂 `build_app()`，即 `web/src/main.py:152` 的
  `app = build_app()`，保证 lifespan 与场景 B 真实拉起同构）；headless TUI 以匹配 `--addr` 启动并等待 `<workspace>/tui-state.json`
  基线；fake g16 任务 running 中 `kill -9` TUI → 读取 `<workspace>/tui-commands.jsonl`，
  确认命令计数器逐端点不变（stop 0、`started` 总数不变）→ REST 确认推进 → 重启
  TUI 无输入恢复基线（execution 集合/pending/hq 与 REST 一致，可见列表已刷新）→
  终态推进与 `history.appended` 收卡；测试进程经 REST 追加 257/300 文件导入，
  TUI 连接可断开/持续排空，断言断线重连后列表完整且命令计数不变。
- **场景 B 启动引导**：不预起守护进程；隔离工作区预置 `listen_port=<空闲端口>`，
  headless TUI 透传 `G16WEB_HOME`/`G16WEB_HQ_BIN` → TUI detached 拉起守护进程、
  按日志偏移解析端口、health 200、hq up（PATH/cwd 正确）、基线就绪 → kill 守护进程
  → 自动重走引导恢复 → 退出 TUI 后守护进程仍存活 → 端口占用反例显示诊断不挂死 →
  慢启动外部 daemon 只拉起一个 → 显式 `--addr` 与远程地址不自动拉起 →
  systemd 真实判定（隔离 unit 名/临时 unit 文件 + `systemctl --user`；`systemctl --user`
  不可用的环境降级为 unit 文件判定并在 §4.5 留痕）不拉起 →
  `--no-launch` 另测不拉起 →
  启动中 daemon 场景只拉起一个 → 双 TUI 并发引导只拉起一个，两 TUI 的
  `tui-commands.jsonl` 行完整不交织、`tui-state.json` 后写者可读 → kill -9 TUI
  后锁自动释放、重新引导成功。
- **场景 C 多客户端并发**：TUI 侧以 Textual Pilot 连接真实 daemon；① 合法重排：
  TUI 与另一路 REST 先后提交全量 `PUT /pending/order`，断言后写者胜、TUI 收到
  快照变化退出重排模式、无重复席位/成员；② 冲突：另一路先移除/锁定席位或提交
  队列，TUI 再提交旧快照，断言收到 400/409 后刷新并退出重排模式。
- **信号与在途命令**：SIGTERM/SIGHUP TUI 于任务 running 中；断言终端状态恢复、
  未发命令、守护进程存活；慢请求在途时退出显示「结果未知」并在 2s 内结束。
- 前置 fixture：会话/模块级断言 `target/release/hq` 存在否则 `pytest.fail`
  （含 `cargo build --release` 提示）；`G16WEB_HOME=tmp_path`、`G16WEB_ENGINE=1`；
  fake g16 复制为临时 bin、`G16_FAKE="sleep=1;steps=10"`；结束断言 TUI 集成模块
  实际执行数与跳过数 0，全量套件 skip 逐条登记。

### 4.4 回归与闸门（每批次收口必跑，H2 全量留痕）

```bash
cargo build --release && ls target/release/hq   # H1 前提（AGENTS §6.1-4）
uv run pytest                                     # 全量，记录实际通过数与 skip 清单
uv run pytest web/tests/test_tui_integration.py   # TUI 集成模块，skip 必须为 0
uv run python scripts/validate_progress.py
uv run python scripts/gen_changelog_md.py --check
bash scripts/package_release.sh -o <tmp>          # H2 发布门槛
tar -tzf <pkg> | grep '^gauforge/web/tui/'        # 包内含 TUI
tar -tzf <pkg> | grep '^gauforge/web/tui/assets/fonts/'   # 字体与授权随包
tar -xzf <pkg> -C <tmp> && ( cd <tmp>/gauforge/web/tui/assets/fonts && sha256sum -c SHA256SUMS )
uv run python scripts/check_plan_status.py docs/plans/m1-plan.md  # 实施期 patch 发布（显式路径示例）
uv run python scripts/check_plan_status.py        # 目标版本发布前全量（本计划已回填终态）
```

范围复核：`git diff --stat` 确认 A 批/UI/打包改动边界，未声明文件零改动。
`package_release.sh` 要求干净工作区，打包门槛在 H2 提交后执行。
前端零改动：`check_tokens.py`/`check_contrast.py`/`audit_frontend_offline.sh`
不涉。实施期 patch 发布只校验本次发布涉及的计划文档；目标版本发布前本计划状态
已回填终态，运行无参全量扫描。重点回归面：A 批波及的 resume/workflow/restart/
dispatch 链、`test_e2e_fake_g16.py`/`test_e2e_queue_lifecycle.py`（hq 在位真跑）、
SSE 全事件触发清单、Web 重复续跑/组合流/停止/重启用例人工核对。

### 4.5 人工/pty 验证矩阵（不进自动化闸门，逐项留痕）

- 终端矩阵：Windows Terminal（WSL 会话）、xterm、tmux、SSH（本机 sshd 或
  局域网主机；注明终端/版本/字体/宽度）；truecolor/256/16、80×24 下六页与
  帮助页完整可用、低于门槛（如 70×20）的最小尺寸提示与恢复、NO_COLOR 与
  TERM=dumb 降级、亮色终端主题可读性、CJK/emoji/组合字符与 ambiguous-width、
  长 CJK 文件名/长错误文本的截断与对齐观感、括号粘贴与 100KB 粘贴后的截断
  提示、Ctrl+S/Ctrl+Q、SIGSTOP/SIGCONT、tmux detach/attach 与 resize、
  人为触发 Textual crash 路径后的终端恢复；B1 按键编码矩阵逐键复核；
- pty 启动失败关闭：重定向 stdout 到非 TTY 后启动交互模式，确认进入全屏前
  向 stderr 输出单行错误、退出码非零、提示改用 `--headless`；`--headless`
  在同样条件下正常导出状态；
- 真实按键长按（组件虽仅测试覆盖，交互模式一并验证）；SSH 断线信号路径
  （终端状态恢复、未发命令）；SIGTERM/SIGHUP 退出与在途命令提示；
- 颜色语义标签 + 颜色双编码、16 色可读；状态栏右段当前页键位提示逐页核对
  （提示集为帮助页键位集子集、切页即时更新）；systemd 托管部署与
  `--no-launch` 引导路径；`listen_port` 非 8300 的连接与诊断；TUI 拉起启动中
  daemon；慢启动外部 daemon；显式 `--addr`/远程不拉起；锁残留恢复；TUI +
  WebUI 并发改席位/队列的冲突反馈；归档条目与 skipped 条目的续跑文案/入口；
  workspace 不一致时的路径告警；
- 视觉层级与间距：逐页核对首要信息所处主列表/主面板、强调仅用于状态与当前
  选中、边框与间距令牌跨页一致、暗色与亮色主题下按语义色映射表约束列复核
  对比可读；
- 队列编辑器状态分级（`unsubmitted` 名称/`skip_failed`/成员顺序、`submitted`
  仅成员顺序、`executing/completed` 只读）；保存与提交分离（保存成功提交失败
  保持 unsubmitted）；文件模式与文件夹模式导入差异；257/300 批量导入后的
  断线重连；大工作区空间占用 5 分钟刷新；部署目录 `.venv/bin/python -m web.tui`
  启动与 hq 状态；按 `web/tui/assets/fonts/README.md` 安装字体后的中文显示
  （可选步骤，不安装不影响功能；粗体观感一并记录）；
- Web 回归：组合流自动提交后待执行面板不被 null 清空（A2）；重复续跑/
  组合流/停止/重启的错误提示与读回（A3/A4/A5/A6）。
- 文档审查：逐项核对 `web/tui/README.md` 九节在位、终端合同按
  Required/Enhanced/Optional/Unsupported 四行式声明、BiDi/RTL 应用级不支持
  与屏幕阅读器支持受限写入终端兼容节、快捷键节与键位总表一致；
- 结论写入附录；AC 项未过按缺陷修复后复测，观察项未过登记为已知限制，
  不以单测通过替代人工结论。

## 5. 发布与回滚策略

### 5.1 发布（目标版本 minor，版本号重启实施时核定）

- 分批登记 CHANGELOG.jsonl unreleased（docs/feat/test 对号）。I 批（CLI 更新
  命令）独立交付，可与目标版本同版或在其后单独发布；I1 不阻塞目标版本冻结，
  I2 随 I1。
- 实施期发布约束：实施期 patch 发布前以显式计划路径运行
  `check_plan_status.py`（示例：
  `uv run python scripts/check_plan_status.py docs/plans/m1-plan.md`），只校验
  本次发布涉及的计划；目标版本冻结前回填本计划终态后运行无参全量扫描。
- 冻结前：AC1–AC37 全部勾验（A6 不参与 v1 验收）→ 部署包冒烟（包内含
  `web/tui`、字体与 OFL/`SHA256SUMS` 在位且校验通过、解包可启动）→ 本计划
  状态行回填「已实施并验收」→
  `uv run python scripts/check_plan_status.py` 通过 → 按 changelog-spec §1.6
  固定顺序冻结、打 tag `v<目标版本>`。

### 5.2 回滚（分层；本版本零 SQLite schema 迁移，回退无数据负担）

| 层级 | 场景 | 手段 |
|---|---|---|
| TUI 客户端 | TUI 缺陷影响使用 | 不启动 TUI 即回退（WebUI 全功能仍在）；或整体 revert C–H 批 |
| 守护进程侧前置 | A 批行为收紧引发问题 | A4/A5/A6 先回、A1 后回（A1 与三码有依赖，不单独回滚）；回滚 A3/A4/A5 时同步回滚或禁用 TUI 对应命令，不得只回滚服务端语义而保留依赖它的 TUI 命令；A3 可独立回，但其停止错误映射已写入 A1 的 `/executions/{id}/stop` description，回滚 A3 须同步回退该段契约描述；A2 独立可回；各步均为收紧语义，撤销即回旧行为 |
| 部署包 | 打包脚本/TUI 纳包/字体资源问题 | 单独 revert C6（字体）或 C5（纳包）并重打包；字体回退不影响 TUI 功能，仅恢复为无随包字体；update/self_update 的整 `web/` 覆盖语义不受影响 |
| CLI 更新命令 | I 批问题 | 独立 revert I1/I2；WebUI 更新卡与 `update.sh` 兜底不受影响 |
| 服务不可用 | 极端情况 | 既有 `restart_g16web.sh`/systemd/手动命令兜底（deployment.md） |

### 5.3 发布后观察项

- TUI 日常使用中 SSE 稳定性（断线频率、导入大批后的预期重连、状态事件背压）；
- 续跑/组合流拒重是否有误伤反馈（R3）；超时读回是否误判旧实体（R23）；续跑慢
  探针的实际等待与读回体验（R17）；
- 输入校验 warnings/normalized 的展示是否被用户注意（R14）；
- TUI 与 WebUI 并发写冲突的实际频率与刷新体验（R13）；
- `listen_port` 变化、systemd 部署、启动引导与信号退出的现场反馈（R4/R15）；
- 部署包启动、队列编辑器状态分级与 257/300 批量导入的现场反馈（R16/R19/R5）；
- 随包字体的安装率与中文/粗体观感反馈（R27）；
- 大工作区空间占用状态栏的刷新成本（R25）；续跑入口与 Web 历史页差异的用户
  反馈（R26）；
- Textual 内建降级与 crash 恢复在真实终端的现场反馈（R28）；长 CJK/emoji
  文件名与长错误文本的截断、对齐观感（R29）；
- CLI 更新命令实际使用率与 WebUI 更新的分工是否如预期。

## 6. 进度同步与提交纪律

- 开发前：`progress.json` `in_progress` 指向本计划，按批次推进更新 note；
  先完成「计划与基线入库」docs 提交，再进入批次 A。
- 每批次收口：CHANGELOG.jsonl unreleased 行 + progress.json `unreleased`
  同步追加摘要；逐文件 `git add` 具名（AGENTS §5.3）。
- 提交粒度：一个任务的实现与其直接测试同属该任务的功能变更，合并为一个
  `feat`/`fix` 提交；`test` 类型只用于独立测试补强（A1 的契约闸门同步、H1
  集成测试）。30 个实施任务按任务提交，A1 拆为 `docs(api)` 与 `test(api)`
  两个提交；合计 31 个实施提交（另有 1 个计划入库 docs 提交）。批次内顺序：
  契约/文档 → 功能实现（含直接测试）→ 集成 → 进度；每个提交可构建、可运行、可回滚。
- 提交信息遵守 `conventional_commits.md`：`<type>[(scope)]: <summary>`，summary
  中文、动词开头、≤50 字、不加句号；正文用 `- ` 分条陈述动机与影响。
- 本计划实施完毕：回填状态行并跑 `check_plan_status.py`；验收留痕入附录。

## 附录：spike 与验收记录

### A.0 终端 spike 判据矩阵（B1）

| 判据 | Windows Terminal（WSL） | tmux | SSH | 结论 |
|---|---|---|---|---|
| CJK 宽度 ★ | | | | |
| 颜色降级 ★ | | | | |
| NO_COLOR / TERM=dumb | | | | |
| 最小尺寸 80×24 与低于门槛表现 | | | | |
| SGR 鼠标 | | | | |
| tmux resize/detach-attach | — | | — | |
| Ctrl+S/Ctrl+Q 流控 | | | | |
| 括号粘贴 | | | | |
| 按键编码（Shift+J/K、Ctrl+D/U 等） | | | | |
| 未捕获异常后的终端恢复 | | | | |

（附：spike 实测 textual 版本号 → C1 钉死值；三环境终端/版本/字体/宽度；
★ 项任一否决的处置记录：客户端整体重写或 Python 核心 + Rust 前端双进程桥接，
C–H 批工作量与发布形态重估；按键编码不通过项登记调整后的键位。）

### A.1 验收记录（H2）

（AC1–AC37 逐条勾验、闸门命令输出、部署包冒烟、集成场景执行数/跳过数、
人工矩阵结论、演练环境说明；另附创建型命令读回基线用例、启动引导慢启动/
非默认端口/远程地址用例、EventQueue 512 容量与 513/600 背压用例的实测记录。）

### A.2 字体资源记录（C6）

| 项 | 值 |
|---|---|
| 文件 | `web/tui/assets/fonts/MapleMono-CN-Regular.ttf` |
| 家族名 / 字重 | `Maple Mono CN` / Regular（无 Bold，v1 已知限制） |
| 上游 | Maple Mono v7.9（<https://github.com/subframe7536/Maple-font>） |
| 获取来源 | npmmirror `@automann/maple-mono-cn@7.9.2` → `dist/og/MapleMono-CN-Regular.ttf`；实施时优先与官方 v7.9 release 内同名文件比对 SHA256，不一致即中止入库并报告 |
| 大小 | 18,509,264 字节（gzip 8,398,273 字节） |
| SHA256 | `0fcc5139bfd5ab14ff989bb7dfd5236d0cafc10e60b9828569e6883613ab4085` |
| 授权 | OFL-1.1，声明 Reserved Font Name `Maple Mono`；原样分发，禁止裁剪/子集化/改名 |
| 分发方式 | 随部署包分发（`scripts/package_release.sh` 经 `web/tui` 整目录纳入）；TUI 不自动安装 |
