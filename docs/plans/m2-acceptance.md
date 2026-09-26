# M2 验收记录（D1 走查留痕 + D 阶段缺陷修复）

> 依据 [m2-plan.md](m2-plan.md) §4.4/§7 执行并留痕。走查日期：2026-09-26。
> 走查环境：WSL2 单机，**fake g16 全链路**（`web/tests/fake_g16.py` 副本经
> 运行级设置 `g16_root` 注入，G16_FAKE 环境变量控制节奏，输入内嵌
> `! FAKE: exit=1`/`sleep=` 注释控制 per-job 行为），派发引擎真实
> （CliGateway + HQ server/worker，hq 产物 `target/release/hq` 走查前重建）。
> 真实 g16 侧金标准旁证沿用 M1 验收结论（水分子/萘体系 B3LYP 真实计算）；
> 本里程碑九条路径的执行结局（成功/失败/跳过）均需确定性注入，故按计划
> 「真 g16 + fake g16 组合」以 fake g16 承担执行侧。
> GUI 走查经 Playwright MCP + Chromium 黑盒驱动（截图留存本地
> `.playwright-mcp/shots-m2/`，不入库）。

## 1. 走查环境准备记录（与走查动作的区分）

- 隔离工作区 `/tmp/m2acc/home`（`G16WEB_HOME`），独立实例 `127.0.0.1:8399`
  （内联 uvicorn，引擎开），fake bin `/tmp/m2acc/fakebin/g16`，
  样本 `/tmp/m2acc/samples/`（水分子模板变体，内容互异防重复判定）。
  生成脚本与现场不入库、可重建（本节命令即重建口径）。
- 服务起后经设置 API 写入：`g16_root=/tmp/m2acc/fakebin`、
  `pending_seat_limit=6`（走查席位编排需要）；其余设置取默认
  （`parallel_window=1`）。
- 走查中两次实例重启（缺陷 77b474769 修复后重载后端代码；前端修复经
  `npm run build` 后整页重载）。重启期 SSE 断连重连（ERR_INCOMPLETE_CHUNKED
  → 重连成功）为 M1 已登记的预期行为。
- 「结构损坏」样本（路径 9③）按 §2.5④「历史遗留兜底」语义经文件系统注入：
  导入合法副本后直接改写 `inputs/<id>`（电荷行改为非两个整数），模拟解析
  层上线前的存量坏副本——导入侧本就拒绝 parse_errors 文件（M1 语义），
  该路径只能经存量副本触达。

## 2. C 阶段已知缺陷修复（走查前置，用户登记的两笔运行时缺陷）

C 阶段提交时未做浏览器冒烟属流程疏漏，两笔缺陷均由本次 D1 前置复验定位、
修复并浏览器实测（vue-tsc 与 vite build 均不拦截此类运行时错误）：

| # | 缺陷 | 修复 | 复验 |
|---|---|---|---|
| 1 | QueueEditorModal 在 `<script setup>` 内 `export interface MemberRow` → 模块初始化 ReferenceError，对话框 chunk 加载即崩溃、候选页组件树中断 | 导出移至普通 `<script lang="ts">` 块（c9ee77904） | 勾选 2 候选 →「+ 队列」对话框正常打开渲染，控制台零错误 |
| 2 | BlockEditor 的 taskId immediate watch 先于编辑态 ref 声明，同步回调 `exitEditLocal` 触达未初始化 ref 抛 TDZ，预览卡恒卡「读取预览 …」 | 编辑态状态与 timers 先声明、watch 后置（a62126b21） | 候选行点击后预览卡六分块完整渲染 |

## 3. D1 走查发现并修复的缺陷（随走查随修，一缺陷一提交）

以下均为 GUI 走查/复验实测暴露（单测因夹具时序或注入方式未能覆盖），
每笔修复均附回归断言或浏览器复验，并实时登记进度两文件：

| # | 缺陷 | 修复 | 实测与复验 |
|---|---|---|---|
| 3 | `_load_input` 以 `read_text` 读原文，Python 通用换行模式静默吞 `\r`——违反其「CRLF 不转」口径，契约「供分块编辑初始化与 CRLF 检出」依赖原始行尾：前端 CRLF 检出注记永不触发 | 改 `read_bytes().decode`，补路由级回归断言（77b474769） | 进入 crlf 样本编辑态显「检出 CRLF 行尾」注记；编辑 title 落盘后全文仍 CRLF |
| 4 | `pushToast` 的 setTimeout 闭包捕获最新 `toastSeq`：多条 toast 5 秒内交叠时早期条目永不自动消失，持续遮挡工具条（SSE 重放双 toast 后「+ 队列」按钮被遮无法点击） | 先取本条 id 再入队与定时（118366966） | 队列 D 三成员终态连发 3 条 toast 全部按期消失（DOM 计数归零） |
| 5 | 队列编辑对话框 `canSave` 在编辑态误用创建期 2–10 校验：移除至剩 1 成员（§2.2「至多移除至剩 1」、后端 PATCH 仅拒 0）时「保存」被禁用，合法编辑无法落盘 | 按模式区分：create 2–10、edit 下限 1（58353cc64） | 队列甲移除至剩 1 + 改名保存成功（PATCH 落库），未执行成员退回候选 |

文档侧发现并修复一处 roadmap 残留偏差（先改文档再改代码口径）：
M2 编辑条目仍引用已弃用的离线 HTML 字典源路径，未随修订说明五同步——
已回填 gaussian-kb MCP 口径（d0ae7b98c）。

## 4. D1 端到端走查（§7.1 九条留痕，对照 roadmap M2 验收段）

| # | 验收项 | 结果 | 留痕 |
|---|---|---|---|
| 1 | 编辑：行预览 →「编辑」修正关键词拼写错误（字典警告）→ 自动保存显「已自动保存」→ 副本行尾未被转换；molecule 无编辑入口；新建未提交队列成员无编辑入口 | 通过 | typo.gjf 编辑 route 自动保存即报「⚠ 第 1 行「oppt」是否意为「opt」？」，修正为 Opt 后警告消隐（p1-spell-warn-autosave.png）；GET /input 与预览一致；crlf.gjf（全文 CRLF）编辑 title 后落盘逐字节核验仍全 CRLF、未编辑节字节不动（p1-crlf-note-edit.png）；编辑态 molecule 卡恒为只读四格读数；队列编辑对话框（unsubmitted 非回退）成员行无「编辑内容」入口 |
| 2 | 组建：复选框选 2 任务 →「+队列」→ 改名、拖动排序 →「保存」入列；「直接提交」进入待执行并按序列执行；入队者移出候选 | 通过 | 队列甲（XR5NKU）：拖动排序保存后队列页可见（members [1,7] 与拖后顺序一致）；队列 B 对话框「直接提交」显「已保存并提交 — 输入已自动规范化」并跳转队列页，逐个执行至 completed；候选列表仅剩未入队者（moved_out） |
| 3 | 失败中止：中段失败整队停止（未勾跳过：后续 skipped+predecessor_failed），执行序列越过队列顺延下一席位任务 | 通过 | 队列 C（J7V6YX，[qf_c, fail_mid, slow2]）：task8 succeeded → task11 failed/program_error → task10 skipped/predecessor_failed；队列回退 unsubmitted、rollback_count=1、finish=abort_on_failure；后置单任务 single_d（exec 9）在队列席位释放后执行（顺延佐证）。`last_failure.members` 仅含失败成员与 #12 e2e 断言口径一致，skipped 归因落执行记录 |
| 4 | 跳过跑完：勾选跳过开关跑完仍有失败 → 队列记失败回退可编辑（回退标记/次数/归因可见） | 通过 | 队列 D（YAYBKZ，skip_failed=true，[qf_d1, fail_mid2, qf_d2]）：14 succeeded → 12 failed → 15 继续执行 succeeded；finish=finished_with_failures、rollback_count=1；队列页「已回退 ×1」徽标 + 失败成员行 FAILED/程序错误归因（p3-queue-rollback-badge.png） |
| 5 | 哈希跳过：回退编辑失败成员重提交 → 未变成功成员跳过（无新执行记录）、已变者重跑 | 通过 | 经队列页展开区「编辑内容」（BlockEditor 内嵌，id 跨形态延续）改 12 号 route 并自动保存；重新提交后执行计数：14 仍 1 条、15 仍 1 条（哈希跳过），12 增至 2 条（重跑）；回退次数 ×2（p5-hashskip-rollback2.png） |
| 6 | 自动成功：移除全部 failed/skipped 成员后队列自动 completed | 通过 | YAYBKZ 对话框移除失败成员 012 保存（PATCH member_ids）→ 队列 completed/SUCCESS、last_failure=null、成员 [14,15]；行内「重新提交」消失仅剩删除；removed failed 成员按 §2.2 分流以执行副本新建候选（id 16，origin=returned_failed）（p6-auto-success-completed.png） |
| 7 | 队列管理：双击编辑（改名/重排/移除分流）；删除 submitted → 席位撤销 + 未执行成员退回 + 二次确认；执行中只读 | 通过 | 队列甲改：移除未执行成员 007 退回候选（origin=returned_unrun、id 延续）+ 改名保存；队列 E2（submitted、席位 14）删除二次确认文案「正在待执行 — 席位将撤销，成员退回候选列表」（p7-delete-submitted-confirm.png），确认后队列删除、席位撤销（pending 仅剩占窗慢任务席位）、成员 returned_unrun 退回；执行中队列 UUTSKK 双击显只读详情 +「前往待执行页移除成员」引导、名称/开关禁用、无保存/提交/删除（p7-executing-readonly-dialog.png） |
| 8 | 导入成队：勾选保存为队列 → 3 文件成队；11 文件 → 拒绝成队回落全部候选并提示 | 通过 | 勾选导入 3 文件夹：队列 RMJMHG「queue3a」建立（members=[38,39,40]、成员移出候选），注记「已导入 3 份 — 已保存为队列「queue3a」」（p8-import-as-queue-note.png）；11 文件夹导入回落全部候选，注记「成队未满足 — 受支持文件 11 个，超出队列成员上限 10」（p8-fallback-reason-note.png）；事件序（created ×N → moved_out ×N → queues.changed(created)）由 test_import_queue 锁定 |
| 9 | 提交核验：CRLF + 空行缺陷提交被规范化（normalized=true 驱动注记）；结构损坏提交被拒 422 且不落盘；三路径统一 | 通过 | 行内提交 crlf 样本：注记「已提交 003 — 输入已自动规范化（换行/空行）」，落盘 0 个 `\r`、link0 后多余空行按不变式移除、重解析零 parse_errors（p9-inline-normalized-note.png）；空行样本（缺文件末空行 + title 后双空行）行内提交后末尾恰补一空行、双空行坍缩；损坏副本（电荷行「0 X」）提交被拒 422 INPUT_PARSE_FAILED（对话框 alert「输入解析失败，拒绝提交」，p9-parse-failed-422.png），副本逐字节未变；队列路径以含 CRLF 成员直接提交两次复核 normalized=true |

## 5. roadmap 一致性对照核验

对照已回填的 roadmap M2 条目与验收段逐句核验：

- 编辑（拼写检查/原子保存/CRLF 不转换/提交核验时机）、组建（时间戳默认名/
  2–10 仅创建时校验/至少保留 1）、队列页（唯一删除入口/状态分级/回退标识/
  哈希重跑/自动成功/成功终态不回退）、导入成队（越界回落+提示）、错误码
  治理条目——语义与实测零冲突；
- 验收段九类路径与 §7.1 逐条对应（§4 表），无遗漏；
- 发现并修复一处残留偏差：M2 编辑条目字典抽取源未随修订说明五回填
  （d0ae7b98c，见 §3 末条）。

## 6. M2 增量 UI 设计一致性核验（沿 m0-frontend-design §8 口径）

与设计规格并排目检（截图见 shots-m2/）：

- 编辑态：分块卡描边转 `--border-strong`（A3 裁决：不冒充 running 通电态）、
  422 红描边 + `--text-sm` 错误注记、拼写警告琥珀注记（§2.1 允许清单）、
  CRLF 检出与「已自动保存」共用中性信息注记（§4.6，非琥珀）；
- 队列编辑对话框：复用弹层基础（backdrop 压暗/焦点圈定/Esc）、顶部名+id、
  中部成员（⋮⋮ 拖源、剩 1 禁用「-」）、toggle 开关、底部「保存」primary +
  「直接提交」secondary、只读态禁用并注明原因；
- 队列页手势分工：行首箭头单击展开、双击行开对话框（A3 定稿）；
- 导入队列选项：勾选 + 队列名预填（顶层目录名，可改）、回落原因中性注记；
- 闸门：`check_tokens`（逐变量 diff 为空）与 `check_contrast`（全组合
  ≥ 4.5:1）通过；`npm run build` + vue-tsc 零错误。

## 7. 系统级判据核对（§7.2）

| 判据 | 结果 |
|---|---|
| `uv run pytest` 全绿（M0+M1+M2 全量含契约回归） | 通过：349 passed（D1 收尾实测值；基线 348 + 新增 input 端点 CRLF 回归断言） |
| hq 产物前置检查（派发链路 e2e 前） | 通过：`target/release/hq` 走查前 `cargo build --release` 重建（与 crates 最新提交一致）；走查全程派发链路真实运行（HQ server/worker + fake g16 共 20+ 执行） |
| `npm run build` + vue-tsc 零错误 | 通过（走查期间多次重建均零错误） |
| `test_error_codes.py`（实现 ⊆ 契约 19 码、退役码零残留） | 通过（含于 349） |
| 双闸门 `validate_progress.py` | 通过（每次提交前逐次执行） |
| 不偏离核对（M2.1–M2.7 逐项） | 见 §8 |
| roadmap 一致性核对 | 见 §5 |

## 8. 不偏离核对（M2.1–M2.7 逐项）

| 工作项 | 状态 | 说明 |
|---|---|---|
| M2.1 编辑 | 完成 | 分块编辑自动保存（失焦/800ms 防抖）、逐节校验 422、拼写近邻警告、molecule 不可编辑、守卫矩阵七路径 |
| M2.2 +队列 | 完成 | 复选框多选、对话框（创建/编辑共用）、拖动排序（useDragSort 与待执行页共用）、2–10 创建期校验、直接提交链式失败保留 unsubmitted |
| M2.3 队列页 | 完成 | 双击编辑、状态分级、唯一删除入口（二次确认、状态分级文案）、回退标识/次数/归因、分块改内容哈希重跑、自动成功 |
| M2.4 导入成队 | 完成 | queue_from_folder/folder_name、2–10 成队、越界回落 + 原因注记、事件序符合 sse.md §3 |
| M2.5 整队端到端 | 完成 | roadmap M1 验收段括注随本记录 §4 第 3–6 条销号 |
| M2.6 提交前核验 | 完成 | 三路径统一 CRLF→LF + 空行规约 + 解析/多步拒绝、normalized 契约字段、失败不落盘、规范化致哈希变化的单次重跑实测（§4 第 5/9 条） |
| M2.7 错误码治理 | 完成 | 全集 19 码载体落 openapi.yaml 文件头、私有码退役、test_error_codes 静态闸门 |

## 9. 替代方案与已知限制声明

- 执行侧以 fake g16 承担（确定性失败/节奏注入所需），真 g16 旁证沿用 M1
  验收的真实计算结论；导入、解析、核验、队列与历史语义均不依赖执行器差异。
- 路径 9③ 结构损坏副本经文件系统注入（§2.5④ 历史遗留兜底语义），导入侧
  本就拒绝坏文件，无 GUI 建坏路径。
- Playwright 目录上传可携带 webkitRelativePath（真实浏览器行为），
  队列名预填链路实测生效；若浏览器/自动化环境缺失该属性，队列名输入框
  可手工填写（契约 folder_name 的显式来源），语义等价。
- 「保存为队列」勾选为一次性标志：导入完成后自动复位，连续成队导入需重新
  勾选（实测确认，属 C4 交互口径，不构成缺陷）。
