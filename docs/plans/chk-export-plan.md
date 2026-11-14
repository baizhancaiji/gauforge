# 历史 chk 导出（split button）· 实施计划（目标 3.7.0）

> 状态：**已实施并验收（随 3.7.0 发布，验收留痕见本状态行与 progress.json
> context v3.7.0 批段，2026-11-14）**——T1–T5 四提交实施完毕（d45039fd
> 计划落盘 / f94e6e5c feat(web) 后端 scope 化 / 14adeb60 feat(frontend)
> split button / chore(progress) 本进度同步）；验收证据：全量 pytest
> 906 passed（基线 3.6.0 冻结 893）；判据 2–5 API 层矩阵由
> test_history_api.py 13 个新增用例覆盖（12 个 scope 扩展 + 1 个 purge
> 启动清扫；2026-11-14 审查整改修正计数留痕）；判据 6 浏览器实测
> （隔离实例 + playwright 直连）：三 scope split 交互与下载落盘核对全过——
> 包名 `gauforge-outputs-YYYYMMDD-HHMMSS.zip` 三 scope 同名仅时间戳区分、
> chk 条目 ZIP_STORED / .out 条目 ZIP_DEFLATED、包内平铺无子目录、
> failed 保全 chk 优先、skipped 登记文案三分口径逐字核对、临时包响应后
> 即删（隔离工作区 tmp 目录零残留）；判据 7 闸门 validate_progress /
> gen_changelog_md --check / audit_frontend_offline / check_tokens /
> check_contrast 全绿，check_plan_status 属发布前口径（本批后仅余各
> 待执行计划项，随各自批次回填）；判据 5 大文件路径经 ZipFile.write
> 按路径流式拷贝实现与 testzip 完整性双证。
> 排期口径：单人实施，任务粒度=一个可审查提交；规模标记 S（≤半天）/ M（约一天）。
> 行号锚点为计划落盘时点（HEAD=5df5e779）实际行号，实施会使其漂移，**以符号名为准**。
> 执行纪律：文档一提交 → 实现两提交（导出契约与后端、前端 split button）→
> 实测验收留痕 → 进度同步，共四提交；每提交单类变更（AGENTS §5.1）。
> 需求来源：2026-11-14 评估会话。首稿曾含「chk 到期自动清理开关」，经用户当日
> 二次裁决**收窄移除**（现状无自动清理，不新增、保持现状，见 §6 决策记录 #1）。

## 1. 需求与现状结论

### 1.1 需求（2026-11-14 用户裁决定案）

历史页工具条「导出 .out」按钮改 **split button**：主操作「导出 .out」+ 备选
「导出 .chk」「全部导出」（.out + .chk 同包）。打包为 ZIP、**包内平铺**（全部
条目同级目录、不建子文件夹），条目命名归一口径同 .out（`<stem>.<正规扩展>`），
**包名仅靠时间戳区分**（三 scope 同用 `gauforge-outputs-<时刻>.zip`），
导出限制口径与 .out 对齐处见 §2.1。

### 1.2 现状核查（HEAD=5df5e779 实测）

| 事实 | 位置 | 对本计划的意义 |
|---|---|---|
| 导出唯一入口 `POST /history/export` → `export_outputs`：全内存 BytesIO + ZIP_DEFLATED，条目 `<stem>.out` 归一命名、冲突组 `<eid:03d>-` 前缀、缺漏登记 `_导出说明.txt`、全缺 404 | `services/history.py:132-170`、`routers/history.py:50-63` | 打包分路径改造的基座；scope=out 保持现路径零回归 |
| 前端下载封装 blob + 包名写死 `gauforge-outputs-<本地时刻>.zip` | `api/client.ts:24`、`HistoryView.vue:263-271` | scope 参数化点；包名零改动满足裁决 3 |
| chk 存在性矩阵：failed/异常终止 → `run/<eid>/protected/` 保全；succeeded → 顶层 `.chk` 仅保留期内存在（`chk_rwf_retention_days` 默认 7 天，「清理 chk」expired 档/「清理所有」all 档清理后即无）；skipped → 无 | `engine/finalize.py:155-215`、`services/history.py:249-250` | 说明登记口径三分的依据（§2.1）；**chk 清理两档均为手动触发**（`POST /history/cleanup`，HistoryView 清理 split button），无自动清理、本次亦不新增 |
| chk 资产定位判据现成：`execution_chk_asset` = ① `run/<eid>/protected/` 保全（failed/异常终止）→ ② 按执行副本 `%chk=` 声明定位（resolve_chk，无声明回落 `input.chk`）；两处皆无 → None | `services/dependencies.py:95-113` | 导出取数直接复用，口径与续跑/@exec 校验同源 |
| **物化语义**：续用形态 `%chk=@task:X` 执行副本被改写为 `%chk=dep-<X>.chk` 且 G16 把本任务 chk 写入该文件（复制语义）；只读接续 `%oldchk=@task:X` 的 `dep-<X>.chk` 才是纯上游参考副本 | `engine/materialize.py:6-13,142` | **不得**对 `dep-*` 一刀切过滤：续用任务的 `dep-<X>.chk` 就是本任务自有 chk，②路径天然选中它；只读形态的 dep-* 不会被选中。按判据取数即正确，无需特判 |
| 同页清理入口已是 split button（`cleanupOpen`/`cleanupMenu` 模式） | `HistoryView.vue:372-379` | 导出 split button 直接复用该现成模式 |

## 2. 实现方案

### 2.1 A 部分：导出 scope 扩展（后端）

- **契约**：`HistoryExportRequest` 增 `scope: "out"|"chk"|"all"`（缺省 `"out"`
  向后兼容）；`openapi.yaml` `/history/export` 描述更新——三 scope 取数与登记
  口径、条目归一命名与冲突前缀、**包内平铺不建子目录**、包名不变、404 按 scope、
  scope 非法值 400。路由层校验 `scope ∉ {out,chk,all}` → 400 `INVALID_REQUEST`
  （同页 cleanup 先例）。`contract.ts` 随契约再生。
- **`export_outputs(ids, scope="out")`**：
  - 采集：.out 维持 `run/<eid>/input.log`；chk 经 `execution_chk_asset(eid)`；
    skipped → 登记未启动无 chk；其余 None → 登记「无 chk 资产（已清理或从未产生）」
    （与 `CHK_SOURCE_MISSING` 文案口径一致，不假装可区分清理与未产生）；
    scope=all 同执行两文件都入包、说明按执行合并登记一条。
  - 命名：条目内 `<stem>.out` / `<stem>.chk`（stem 取任务 filename 去扩展名）；
    冲突组按 **(stem, 扩展)** 分组判定（scope=all 同执行同 stem 不误判），
    冲突组全部加 `<eid:03d>-` 前缀，规则同现状。
  - **打包分路径**：scope=out 保持内存 `BytesIO`+`ZIP_DEFLATED` 原路径（零回归）；
    scope=chk/all 改**临时文件顺序写**（`tempfile` 于 `config.HOME_DIR` 下 tmp
    子目录——常量落 `config.py`（先例 `.update-proxy` 工作区持久化），启动清扫
    挂 `main.py` lifespan），条目按路径流式拷贝入包（`ZipFile.write` 分块读写，
    chk 可达数 GB，全程不得整文件载入内存——防 OOM/内存尖峰），chk 条目
    `ZIP_STORED`（二进制压缩无收益）、.out 条目 `ZIP_DEFLATED`；路由层
    `FileResponse` 分块流式发送 + BackgroundTask 删临时文件。
    不设包大小上限（导出期间磁盘峰值 ≈ chk 存量与临时包之和，chk 条目
    `ZIP_STORED` 不压缩；ZIP64 由 `zipfile` 自动启用）。
  - 404：所选 scope 采集结果全空（missing 登记随响应 details）。
- 取数判据单一天然口径：`execution_chk_asset`（含 §1.2 物化语义，**不加 dep-*
  过滤**）；归档条目放行（与 .out 现状一致）。

### 2.2 B 部分：前端 split button 与 client

- `HistoryView.vue` 工具条「导出 .out」→ split button：主操作「导出 .out」+
  备选菜单「导出 .chk」「全部导出」——复用同页清理 split button 现成模式
  （`HistoryView.vue:372-379` cleanupOpen/cleanupMenu 先例）；文案分隔用「—」
  （禁「·」，见协作文档约定）；导出中/错误注记沿用 `exportNote`。
  样式约束：复用 `base.css` 共享按钮类（`.btn`/`.btn--secondary`）与既有令牌
  变量（`--space-*`、`--z-dropdown`、`--bg-raised`、`--border-hair`、`--r-md`、
  `--shadow-pop`、`--text-sm` 同 cleanup 菜单先例），不新增硬编码色值/尺寸/
  间距/层级——`check_tokens.py` 仅校验令牌定义两处一致、`check_contrast.py`
  仅从 `tokens.css` 取色，组件内硬编码两闸门均不拦截。
- `client.ts` `exportOutputs(ids, scope = "out")` 加参透传。
- 下载包名 `gauforge-outputs-<本地时刻>.zip` 不变（裁决 3：仅时间戳区分）。

### 2.3 明确不做（边界）

- **不新增 chk 自动清理能力**（2026-11-14 二次裁决：现状清理两档均为手动触发，
  保持现状）；手动清理与存储统计零改动；
- 不做导出进度/分批下载 UI（与 .out 现状对齐，长下载无进度条）；
- 不动保全/清理管线实现；
- 不做 `input.fchk` 导出（formchk 产物属分析管道，非本需求）；
- 不做导出条目子目录分组（裁决 2 明确平铺）；
- 不给导出加归档拦截（与 .out 现状一致放行）。

## 3. 任务分解与提交序列

| 任务 | 内容 | 提交 | 规模 |
|---|---|---|---|
| T1 | 本计划落盘并提交 | `docs(plan): 登记历史 chk 导出扩展计划` | S |
| T2 | `export_outputs` scope 化 + 临时文件打包（tmp 子目录常量落 `config.py`、启动清扫挂 `main.py` lifespan） + openapi 契约与 `contract.ts` 再生 + `test_history_api.py` 用例（§4 判据 2–5 的 API 层矩阵，含 scope 非法值 400） | `feat(web): 支持历史导出 chk 与全部打包范围` | M |
| T3 | 前端 split button 三操作 + `client.ts` scope 传参 | `feat(frontend): 改历史导出按钮为三范围 split button` | S |
| T4 | 实测验收（§4 全判据，留痕落状态行）；`uv run pytest`、`validate_progress.py` 与前端三闸门照跑 | （无独立提交，证据落 T5 状态行） | M |
| T5 | CHANGELOG.jsonl unreleased（added：chk/全部导出范围）+ progress.json 同步 + 状态行回填「已实施并验收」注明留痕位置与发布版本 | `chore(progress): 同步历史 chk 导出批次进度` | S |

## 4. 验收判据

1. **scope=out 零回归**：既有导出测试全绿；同输入包内容与现状一致（内存路径未动）。
2. **chk 取数矩阵与 scope 校验**（pytest）：succeeded 保留期内 → 自有 chk 入包；failed →
   `protected/` 保全 chk 入包；skipped → 说明登记；chk 已清理 → 说明登记；
   chk scope 全缺 → 404；scope 非法值（非 out/chk/all）→ 400 `INVALID_REQUEST`
   （`test_cleanup_invalid_scope_400` 同型）。
3. **物化语义正确性**（pytest）：只读接续任务（`%oldchk=@task:X`）导出不含
   `dep-<X>.chk`；续用任务（`%chk=@task:X`）的 `dep-<X>.chk` 作为自有 chk 入包；
   只读接续任务未声明自有 `%chk` 时无自有 chk → 说明登记，scope=chk 全缺 → 404。
4. **平铺与命名**：ZIP 根目录无子目录条目；条目归一 `<stem>.chk`；同任务多执行
   冲突组 `<eid:03d>-` 前缀；scope=all 同执行两条目不加前缀。
5. **大文件路径**：scope=chk/all 走临时文件（包过 `testzip` 完整；结束后临时文件
   已删；启动清扫残留逻辑存在）；chk 条目按路径流式拷贝入包（`ZipFile.write`，
   不得整文件读入内存）；scope=out 内存路径不变。
6. **前端**：三 scope 按钮 split 交互浏览器实测（隔离实例 + playwright-core
   直连口径，导出 blob 落盘核对包内容与包名时间戳格式不变）；新增样式对照
   diff 复核仅令牌变量引用，无硬编码色值/尺寸/间距/层级。
7. 全量 `uv run pytest` 通过数不低于基线（3.6.0 冻结 893 passed，以当次全量为准）；
   闸门：`validate_progress.py`、`audit_frontend_offline.sh`、`check_tokens.py`、
   `check_contrast.py`、`gen_changelog_md.py --check`、`check_plan_status.py`
   （发布前）全绿。

## 5. 风险与边界

- **临时文件残留**：BackgroundTask 删除为主，启动清扫兜底；服务中断残留不阻塞。
- **临时写盘失败（磁盘满）**：scope=chk/all 临时包写盘 OSError 时请求按 500
  报错、响应不发出，BackgroundTask 不执行，残留交启动清扫兜底；导出期间磁盘
  峰值 ≈ chk 存量与临时包之和（chk 条目不压缩），磁盘紧张时属预期失败路径。
- **读清竞态**：导出读取与手动清理并发时 read 失败按缺登记，不阻塞、不重试
  （chk 存量属可清理数据，竞态窗口语义可接受）。
- **存储统计口径**：`storage.usage` 按 `HOME_DIR` 整树 `os.walk` 统计，导出
  临时包计入 `total_bytes`，大包导出瞬间可能触发 `disk_usage_warn_gb` 告警，
  属可接受瞬时噪声，不为导出单独排除 tmp 目录。
- **首例二进制大包**：现有导出仅文本日志，chk 为首批大二进制条目；`testzip`
  完整性与落盘核对为强制判据（判据 5–6）。

## 6. 决策记录（2026-11-14 用户裁决，无开放决策点）

| # | 裁决 | 落点 |
|---|---|---|
| 1 | **（二次裁决收窄）** 不新增 chk 自动清理功能，保持现状——首稿的 `chk_autoclean_enabled` 设置项与周期清理线程移除 | §2.3、§1.2 |
| 2 | 平铺 = ZIP 内所有条目同级、不建子文件夹 | §2.1 契约注记、判据 4 |
| 3 | 包名仅靠时间戳区分，三 scope 同名 | §2.2、判据 6 |
| 4 | 其余按推荐值：条目命名归一 `<stem>.chk`、冲突前缀复用；scope 参数扩既有端点（缺省 out）；归档条目放行；chk 条目 `ZIP_STORED` + 临时文件打包 | §2.1、§2.2 |
