# 组合流模板配置与 crest/xtb 部署 · 插波实施计划

> 状态：**待执行**——2026-10-13 起草，经八轮结构化审查修订
> 目标版本：3.1.0 后插波 → **3.2.0**（含 added → minor，changelog-spec §1.7）。
> 需求来源：用户 2026-10-13 对 M4 组合流提出的两项补充需求及当日细化；
> 2026-10-13 审查修订新增第三项需求（Link0/route 全小写统一，含既有存量修正）。

## 0. 背景与需求

### 0.1 需求一：组合流精修模板可配置（5 套，设置页管理）

M4 组合流（m4-plan §2.3，`POST /workflows/conformer-refinement`）的精修模板
route 当前为前端硬编码默认值（`ComboFlowDialog.vue:23`
`"#p B3LYP/6-31G(d) Opt Freq"`），每次打开对话框重置、不可持久化。要求：

- 设置页提供入口按钮，点击弹出配置页（类似队列编辑器模态，不铺在面板上）。
- 配置页顶部一排均匀排布 **5 个矩形框**，显式数字 1–5（对应方案唯一 id），
  点击选中（沿用既有选中态样式）并在下方展开编辑区；打开配置页自动展开
  方案 1。
- **5 套方案初始时全部存在**：配置名初始取「配置n」（n 为方案 id）；
  可配置项为 route 与 link0，均以初始值初始化，**清空则恢复为初始值**
  （route 初始值全部方案共用一个，且必须合法；link0 三字段初始值为空，
  「清空恢复初始值」对 link0 即恢复为空——见 §3.1/§3.2）。
- 支持显式指定某个方案为**默认方案**（「设为默认」复选框）。
- route 编辑框带合法性校验、拼写错误校验、热化学温度标签校验——**合法性
  校验固化为通用组件/功能**（后端单点，前端复用其结果）。
- link0 编辑框：%nprocshared、%mem、%cpu 各一个编辑框；%cpu 默认置灰，
  勾选 %nprocshared 旁「指定CPU核心」复选框后才可填。
- **保存语义**：所有校验在点击「保存」时执行；不通过则显著提示**全部**
  错误原因（一次全报，不逐个）、不保存；全部通过才落库。未点保存则保留
  原始配置，只有显式保存且校验通过才更新。

### 0.2 需求二：crest/xtb 配套部署方案

现状仅本机可用（`~/opt/crest-3.0.2` 等路径为既成事实），新部署机无安装
指引。要求提供配套部署方案。**已采纳建议口径：download-at-install**——
不随 gauforge-deploy 包分发第三方二进制（包体积/许可再分发/平台锁定三重
顾虑），提供安装脚本 + 文档，离线机走手动下载路径。

### 0.3 需求三：Link0/route 参数全小写统一

**本代码库约定：所有 Link0 与 route 参数一律全小写**（G16 大小写不敏感，
定案口径 2 的 casefold 匹配已兼容用户输入大小写；生成/序列化/入库值统一
小写，禁止 `%NProcShared` 这类混合大小写形态）：

- **规则**：生成行、序列化行、默认值、入库值、词典、错误消息与注释引用
  统一为小写形态——`%nprocshared=`、`%mem=`（GB 无空格）、`%cpu=`、
  `%oldchk=`、`%chk=`，route 如 `#p b3lyp/6-31g(d) opt freq`。
- **存量修正**：既有实现代码中的违反形态**统计并修正**（统计清单见 §1.1），
  涉及的修改纳入本计划（批次 F1 后端 / F2 前端）。
- **词典**：`keywords.txt` 统一小写（现状 97 词已全小写，扩充后仍全小写，
  `extract_keywords.py` 输出即 casefold；再生闸门增「全小写」断言，见 §4）。

### 0.4 定案口径

| # | 事项         | 定案                                                                                                                                                                                                                                |
| - | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | temptemperature 温度标签 | route 含 **freq** 即须显式带温度；已配置判定＝route 含 `temp=` 或 `temperature=`（gaussian-kb 核验 2026-10-13：两者为同一关键词两形态，官方页 slug=temp、正式名=Temperature）；已配 → 校验值合法性（非法阻止保存）；未配 → **保存时自动补** **`temperature=298.15`**（官方 route 示例唯一形态; 归一化后入库，编辑区回显归一化 route 并提示「已补齐」）。即：只要有 freq，温度恒显式存在，哪怕是默认值。                                                                               |
| 2 | route 拼写校验 | **精确白名单匹配**（casefold，gjf 来自 gv6、Link0/route 惯例小写；**不采用 difflib 近似命中判错**）；词典外 token（新词）**默认拦截**，编辑区提供「忽略拼写警告并保存」豁免按钮（豁免作用于弹窗打开期间、跨方案共享，关闭弹窗即清空，落库不记豁免态，重开重新校验——§3.4）；**词典经 gaussian-kb 扩充**（gv6 关键词名单在 gaussian-kb 中可查；词典扩充为**必须实施项**——批次 B 硬前置，见 §8 开放事项 1 与 §7 风险 R-1）。 |
| 3 | %Mem 比例校验  | 每核内存下限 **1 GB/核**（常量 `PER_CORE_MEM_GB_FLOOR = 1.0`）；有效核数 = %nprocshared ?? %cpu 核数；`mem_gb < 核数 × 1` 阻止保存。                                                                                                                       |
| 4 | 全小写统一      | 需求三（§0.3）：route/link0 生成、序列化、入库、词典、文案一律小写；保存时 casefold 归一化后入库、响应回传归一化值（notice 标注 `normalized`）；既有违反存量按 §1.1 清单逐处修正（批次 F1/F2），不改变 G16 语义。                                                              |
| 5 | nproc×cpu 匹配 | 两者同时非空时：`%cpu` 核编号总数 ≥ `%nprocshared`（相等为常规形态，如 nproc=4/cpu=1-4；不足如 1-3 阻止保存；**多于默许不拦**，如 1-5——G16 官方未定义两指令共存行为，link0 页明言 %CPU designed to replace %NProcShared）。%cpu 非必选：未配置不提示；存在即校验书写合法性（`cpu_list_invalid`）与匹配关系（`nproc_cpu_mismatch`），校验归 validate_and_normalize 单点、与既有 gjf 校验链一体；nproc 空而 cpu 非空时仅做书写合法性校验（匹配基准缺省，派发注入链不在模板校验域）。 |


## 1. 现状核查结论（实施输入，2026-10-13 实测）

| 事实                                                                                                                                                                                                                                                                         | 对本计划的影响                                                                                                                                                            |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 模板默认值硬编码于 `ComboFlowDialog.vue:23`；服务端 `save_template`/`_refine_input`（`services/workflows.py`）只消费提交载荷、不消费任何默认值                                                                               | 服务端组合流提交链**零改动**；前端把所选方案解析为既有 `template.route/link0` 载荷照常提交（批次 C）；默认值形态小写归一由批次 F2 收口                                                                                         |
| route 拼写基础设施已存在：`parse/keywords.txt`（97 词、全小写，由 `scripts/extract_keywords.py` 从 gaussian-kb 生成、可重生成）+ `parse/keywords.py::check_route_spelling`（difflib 近邻、非阻断警告，唯一消费点 `services/candidates.py::save_block`）   | 复用其加载器；判定方式按定案口径 2 改为精确白名单 + 可拦截（**组合流模板域内**新增判定函数，不改动既有 `check_route_spelling` 的非阻断语义——`save_block` 行为不变）；词典扩充 = 扩大 gaussian-kb 提取面后再生 `keywords.txt`（既有再生闸门天然覆盖，另增**全小写断言**） |
| Link0 逐行文法校验已存在：`services/candidates.py::_validate_section`（%Key=Value、nproc 正整数、`_MEM_VALUE_RE`、`_cpu_list_count` proc-list）                                                                              | 复用同款判定；新写交叉校验（mem/核数、nproc/CPU 核数）                                                                                                                                 |
| `engine/workspace.py`：`_mem_to_gb`（L34）、`_cpu_list_count`（L50）、`resolve_link0`（L69，派发时对缺失 %nprocshared/%mem 按运行级设置注入 `%NProcShared=4`/`%Mem=8GB` 形态）                                          | 模板 link0 字段空缺 → 派发补齐链路不变；交叉校验仅在两字段同时非空时启用；注入行小写归一属批次 F1（§1.1 存量 #1/#2）                                                                                                   |
| ui\_prefs 全链路先例：`routers/ui_prefs.py`（白名单整批校验、复用既有错误码不新增）+ 26 行 repo + config 白名单 + openapi schema + 契约断言测试                                                                                   | 端点/repo/测试体例照抄该先例；错误码复用 422 `VALIDATION_FAILED`，**零新增错误码**                                                                                                         |
| migrations 当前版本 **v6**（`store/migrations.py`），新表做法见 v2 先例（`IF NOT EXISTS` + `INSERT OR IGNORE` 种子幂等）；工厂注册在 `store/__init__.py`                                                                | 新表 = **migration v7**                                                                                                                                              |
| crest 探测：`engine/crest.py::crest_executable`（`<crest_root>/crest`），缺失提交即 503 `CREST_EXECUTABLE_MISSING`（details 含 crest\_root 与 expected 路径）；A5 实测定稿（m4-plan §2.3 实测记录、`engine/crest.py:14` docstring；A5 锚点见 m4-acceptance）：crest 3.0.2 静态内嵌 tblite、运行时不消费 XTB\_PATH | ...需求二的运行必需项**仅 crest 一个二进制**；xtb 为可选安装（`xtb_root` 仅为未来独立 xtb 的定位锚），文档须写明避免误装                                                                                         |
| 部署链既有约定：`scripts/deploy/update.sh` 的代理约定为**环境变量 `GAUFORGE_PROXY` + `--proxy`/`--no-proxy` 参数**（默认 `https://v4.gh-proxy.org`，选择持久化于 `.update-proxy`；注意 `GAUFORGE_GH_PROXY` 是 `install.sh` 的独立变量，两者不混用）；`scripts/package_release.sh` 根脚本清单（CLI update.sh 对新增根脚本自动补装） | 安装脚本复用 update.sh 的 `GAUFORGE_PROXY`/`--proxy`/`--no-proxy` 参数约定（同一部署目录根脚本、语义一致）；打包清单加一行即触达旧部署升级                                                                              |
| 契约再生链：openapi.yaml → `web/scripts/gen_models.py` + `npm run gen:types`；闸门 `test_openapi_ssot.py`/`test_error_codes.py`                                                                        | 批次 A 产出后两处再生产物随契约提交入库、重复再生零 diff                                                                                                                                                 |

### 1.1 全小写统一存量核查

违反形态分三类：**运行值**（生成/序列化/默认值，必须改）、**文案/注释**（错误
消息、docstring、注释引用，统一小写随行修订，受影响既有测试断言随行刷新）。

| # | 位置 | 现状形态 | 类别 | 处置（统一为） |
| - | ---- | ------ | -- | ----------- |
| 1 | `engine/workspace.py:111` | `f"%NProcShared={declared}"`（派发注入行） | 运行值 | `%nprocshared=` |
| 2 | `engine/workspace.py:115` | `f"%Mem={_fmt_gb(mem_gb)}GB"`（派发注入行） | 运行值 | `%mem=` |
| 3 | `services/resume.py:146` | `f"%OldChk=@exec:{source_eid}"`（续跑注入行） | 运行值 | `%oldchk=` |
| 4 | `services/resume.py:148` | `link0_lines: ["%OldChk=@exec:…"]`（契约响应行） | 运行值 | `%oldchk=` |
| 5 | `engine/materialize.py`（符号行值改写，前缀保留原样） | `%Chk=@task:X`→`%Chk=dep-<X>.chk`、`%OldChk=` 同 | 运行值 | 改写行前缀 casefold 归一：`%chk=`/`%oldchk=`（仅值改写逻辑不变） |
| 6 | `frontend/ComboFlowDialog.vue:23` | `DEFAULT_ROUTE = "#p B3LYP/6-31G(d) Opt Freq"` | 运行值（默认） | `#p b3lyp/6-31g(d) opt freq`，与 `COMBO_TEMPLATE_INITIAL_ROUTE` 对齐（单值来源） |
| 7 | `frontend/ComboFlowDialog.vue:145` | placeholder `%NProcShared=4` | 文案 | `%nprocshared=4` |
| 8 | `frontend/CandidatesView.vue:248/250` | 黄警文案 `%NProcShared=…`、`%Mem=… GB`（展示用，非载荷） | 文案（展示） | `%nprocshared=…`、`%mem=…GB`（去空格、与后端注入行形态一致）；**后端 missing 指令名来源已定案**：`services/candidates.py:327` 返回不带 `%` 前缀的大写指令名 `"NProcShared"`/`"Mem"`，前端黄警行构造时小写归一为 `%nprocshared=`/`%mem=`，受影响断言同步刷新 |
| 9 | 文案/注释群 | `config.py:99/103`、`models.py:361/393/663/666`、`services/candidates.py:233/236/239`（错误消息）、`services/candidates.py:285`、`services/resume.py:16/21/27`、`engine/dispatcher.py:12`、`hq/gateway.py:73`、`engine/workspace.py:4/74/76`、`parse/blocks.py:128-132`、`engine/finalize.py:5/6/77`、`services/dependencies.py:3/6`、`engine/reconcile.py:11`、`engine/materialize.py:6-11`、`frontend/contract.ts:1507` | 文案/注释 | 引用参数名一律小写（`%nprocshared`/`%mem`/`%cpu`/`%oldchk`/`%chk`）；`keywords.txt` 词典本身已全小写，不动 |

> 处置原则：仅改写形态、不改语义（G16 大小写不敏感）；批次 F1/F2 以本表为
> SSOT，实施中发现表外违反处——补录本表并与修复同提交（风险 R-8）。
> 其中 `models.py:361`/`:393`/`:663`/`:666` 均为 pydantic description
> （openapi 再生面，contract.ts:1507 为其下游产物），其修订随
> 批次 A 契约 diff 一并落（一次再生，避免契约产物二次再生与同文件并行冲突）；
> F1 范围收窄为「非再生面文案/注释」，不含上述四处再生面。
>
> **R-8 补录（2026-10-14 批次 A 实施）**：`openapi.yaml` 文件头注释与
> 对象级/路径 description 中的 Link0 引用形态同属表外违反处，已随批次 A
> 同提交小写化——行号：71（错误码注 %Chk）、273/276（Task 对象级
> description）、696/697（ResumeInjection 对象级 description）、1970
> （PATCH /queues/{id} description）、2518（resume 路径 description）；
> 上述行再生后 contract.ts JSDoc（原 611/1223 等处）随产物一并归一。
> route 关键词片段引用（Opt=Restart、Guess=Read）非 Link0 指令名、不在
> §0.3 定形集内，维持原样。行号系撰写时基线口径，提交后随契约 diff
> 漂移，以形态内容为准（独立审查 F-4 实测：HEAD 全文件大写形态零残留）。
>
> **R-8 补录（2026-10-14 批次 F1 实施）**：表外违反 5 处随修复同批小写化——
> `workspace.py:5`（docstring「%Mem 已声明时」）、`:35`（「G16 %Mem 值」）、
> `:51`（「%CPU proc-list」）、`:77`（「仅 %CPU 时」）、`candidates.py:40`
> （「# %Mem 值」注释）；处置原则同上（仅改写形态、不改语义）。
> 另注：`blocks.py:134`/`candidates.py:327` 的 `"NProcShared"`/`"Mem"` 系
> missing 指令名载荷值（#8 定案前端小写归一）、非违反处，维持原样。
>
> **R-8 补录（2026-10-14 批次 F2 实施）**：前端表外违反 8 处随修复同批
> 小写化——`QueueEditorModal.vue:18-19`（docstring `%OldChk` 精确形态与
> `%Chk` 续用形态）、`:33`（removeOldChkTaskRef docstring）、`:100`
> （initTarget 注释）、`:131`（linkTitle UI title 文案）、`:201`
> （**运行值**：persistLinkChanges 生成行 `%OldChk=@task:` →
> `%oldchk=@task:`）、`:492`（成员行勾选注释）、`BlockEditor.vue:476`
> （样式注释 `%Chk=`）；解析/移除正则（:26/:36）与 loadLinkStates 初始
> 化正则（:164）均带 `i` 标志大小写不敏感，生成行切小写对存量内容安全。
> 处置原则同上（仅改写形态、不改语义）。

## 2. 任务分解（WBS）

| 批次 | 任务                 | 产出物                                                                                                                                                                              | 验收标准（可验证）                                                                                    | 依赖          | 规模  |
| -- | ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ----------- | --- |
| A  | 契约 diff（文档先行）      | openapi.yaml：`ComboTemplate`/`ComboTemplatesResponse`/`ComboTemplateUpdate` schema——**角色定案**：`ComboTemplate`＝GET 条目、`ComboTemplatesResponse`＝GET 响应整体（`initial: {route}` 内联其中）、`ComboTemplateUpdate`＝PUT 请求体（含 `ignore_spelling?`）、PUT 200 响应另立 `ComboTemplateMutationResult`（＝`ComboTemplate` 全字段 + `notice` 对象；nproc/mem_gb/cpu 为 `string|null`，值级合法性全部归校验单点给出 reason，§3.2；notice 含 `{temp_applied: bool, normalized: bool, spelling_warnings?: string[]}`，§3.3）、`GET /combo-templates`、`PUT /combo-templates/{templateId}`、文件头「词表三：组合流模板 reason 值域」（11 项全集，见 §3.2 清单；注释明确 `keyword_not_in_dict` 双信道——enforce→`errors[]`、warn→`notice.spelling_warnings`，`spelling_warnings` 元素为词典外 token 原文、非 reason）+ openapi.yaml:211（Error schema description，引用文件头词表计数的行）同步（「两张 reason 词表」→「三张」）；**§1.1 #9 再生面四处一并小写化**（models.py:361/393/663/666 pydantic description + contract.ts 下游，一次再生）           | 再生产物（`web/src/models/models.py`、`frontend/src/api/contract.ts`）随 §5 #2 提交入库、入库后重复再生零 diff；`test_openapi_ssot.py`/`test_error_codes.py` 通过（零新增错误码）；词表三条目与 §3.2 reason 清单逐项一一对应（人工 grep 核对留痕入附录 B AG1；B 批次 test\_combo\_templates.py 11 reason 断言回归闭环）；文件头无「两张」残留（grep 核对）                  | 计划评审        | S   |
| B  | 后端：迁移+repo+校验服务+端点 | migration v7（combo\_templates 表 + 5 行种子）、`store/combo_templates_repo.py`、`services/combo_templates.py::validate_and_normalize`（通用校验单点，含 enforce/warn 双 mode 实现）、`routers/combo_templates.py`、config 初始值常量（小写形态）；**词典扩充交付物**（`scripts/extract_keywords.py` 提取面扩展 + 再生 `keywords.txt`，§8.1，**必须实施项、最大化覆盖度**，#4 独立提交） | §3.2 校验矩阵逐 reason 全绿（11 项逐一断言；拼写 reason 按 mode 双形态断言，§3.2）；种子幂等；is\_default 迁移事务性（恒有且仅有一个默认）；temp 补齐与归一化（route/link0 casefold 入库、响应 notice 标注）断言；豁免语义断言（仅当次生效）；端点 200/404/422 契约断言；**B 完成形态二选一**（§8.1，**词典扩充 #4 均为必须实施项、最大化覆盖度**）：enforce 完整形态＝gaussian-kb 四项核验留痕 + 词典扩充最大化覆盖度且按达标判据完成并留痕 + #5 默认 enforce 上线；warn 降级形态＝词典扩充按 §8.1 降级语义先行（未达判据）+ #5 默认 warn 上线 + enforce 切换登记 §5 #6 条件提交、不阻塞 3.2.0 发布 | A           | M–L |
| C  | 前端：配置弹窗+入口+对话框选择器  | `ComboTemplatesModal.vue`、SettingsView 入口按钮、ComboFlowDialog 方案下拉与回填                                                                                                              | 附录 A 交互断言清单 25 条中按当前 mode 执行对应条并**逐条通过**（A1–A24，A7 拆 A7a/A7b 计 2 条；降级时 A7a 标注「不适用」，同 E 行口径；留痕入附录 B）；四闸门：`npm run build`（vue-tsc 零错误）、`scripts/audit_frontend_offline.sh`、`scripts/check_tokens.py`、`scripts/check_contrast.py` 全过                                         | B           | M–L |
| D  | crest/xtb 部署       | `scripts/deploy/setup_deps.sh`、package\_release.sh 接线（根脚本加 setup\_deps.sh **+ deployment.md 单文件纳入部署包**）、docs/references/deployment.md「CREST/xtb 接入」节                                                                                               | 真机走查（前置：附录 B 环境检查）：自定义 `--dest` 模拟新机 → 组合流 503 → 部署 → `POST /workflows/conformer-refinement` 返回 **HTTP 200 且响应含 workflow\_id** 闭环（精修实际运行不在 D 走查范围；走查后终止该走查 workflow 并留痕处置）；脚本幂等（重复执行跳过）；上游资产校验和核验留痕（§8.3，对照源口径见 §3.5，落盘附录 B）；xtb 可选安装路径与「非运行必需」说明可走查验证；**部署包内含 `docs/references/deployment.md`（D5）走查** | 无外部批次前置（内部①上游资产核验通过为②–⑤前置；部署链约定见 §1） | M   |
| F1 | Link0/route 全小写收口（后端，不含 openapi 再生面） | §1.1 清单后端部分逐处修正（运行值 5 处 #1–#5 + 文案/注释群 #9 后端部分；**不含 models.py:361/393/663/666 再生面，已随批次 A 落**）+ 受影响既有测试断言同步刷新 | §1.1 后端条目全部清零（git diff 逐处核对，留痕入附录 B FG1）；既有派发/续跑/物化链回归全绿（test\_workflow\_crest、test\_resume、test\_materialize）                             | 计划评审（与 B/C 并行） | S–M |
| F2 | Link0/route 全小写收口（前端） | §1.1 清单前端部分逐处修正（#6 默认值改引用 `COMBO_TEMPLATE_INITIAL_ROUTE`〔单值来源，常量由批次 B 提交 #3 引入〕、#7 placeholder、#8 黄警文案）+ 受影响断言同步刷新（git diff 逐处核对，留痕入附录 B FG2） | §1.1 前端条目全部清零（git diff 逐处核对）；黄警文案形态与后端注入行一致；前端四闸门过 | F1 + C + B（重入 ComboFlowDialog.vue，避免与 C 同文件并行冲突；`COMBO_TEMPLATE_INITIAL_ROUTE` 常量由 B 引入；#8 黄警文案须与 F1 改定后的后端注入行形态对齐） | S |
| E  | 验收与发布              | 走查记录回填**本文档附录 B**（含 D 闭环与附录 A 逐条留痕）；CHANGELOG.jsonl/progress.json 同步；3.2.0 冻结五步                                                                                            | §6 闸门全过；附录 C 评审清单复核通过；附录 B 预期条目（A1–A24、AG1、FG1/FG2、B1/B2/B3、D1–D5、E1–E5）逐条有实测结论、标注「待补」或标注「不适用」（A7a 降级场景），无空白条目；降级交付时冻结须复核「词典扩充 + enforce 切换」遗留项登记于 progress.json `next_steps`（§8.1 进度跟踪锚）；发布五步按 AGENTS.md §5.2 顺序执行                                                            | A–D, F1, F2（D 为条件依赖，整体失败决策出口见 R-13）      | S   |

**依赖关系**：`评审→A→B→C`；`F1` 独立（与 B/C 并行，触既有派发/续跑/物化
链、须回归）；`F2` 依赖 `F1+C+B`（重入 ComboFlowDialog.vue，避免与 C 同文件
并行冲突；提交 #3 引入的 `COMBO_TEMPLATE_INITIAL_ROUTE` 常量作为单值来源，§1.1 #6 与之对齐；
#8 黄警文案与 F1 改定后的后端注入行形态对齐）；`D` 独立
可并行（内部①上游资产核验通过为②–⑤前置）；`A–D,F1,F2→E`（B 按 §8.1 定案形态衡量：warn 降级
形态完成的 B 视为满足前置，enforce 切换〔§5 #6〕不阻塞 E）。关键路径 B→C。

**批次内子步骤顺序**（M 及以上批次）：
- B：① gaussian-kb 四项核验（§8.2；**2026-10-13 已完成预核验并回填定案，
  开工时复核留痕即可**）→ ② v7 迁移+种子 → ③ repo →
  ④ 词典扩充再生（**必须实施项、最大化覆盖度**；为提交 #5 enforce 模式硬前置；gaussian-kb 不可用时按 §8.1 降级语义先行、恢复后补做扩面，不阻塞 B 整体）→ ⑤ validate\_and\_normalize → ⑥ 端点 → ⑦ 测试收尾（默认 enforce，词典未达判据则 warn；②③ 合为提交 #3、④ 为提交 #4，工作顺序与落库顺序一致）。①已完成预核验（2026-10-13，§8.2），A8/A9/A10 已按定案回填（§3.2 矩阵同步
  修订），随 B 提交复核入库。
- C：① ComboTemplatesModal（5 框+编辑区+保存流）→ ② SettingsView 入口 →
  ③ ComboFlowDialog 下拉与回填。
- D：① 上游资产实测核验（§8.3）→ ② setup\_deps.sh → ③ 打包接线 →
  ④ deployment.md → ⑤ 真机走查（附录 B）。
- F1：① §1.1 后端清单逐处修正（#1–#5、#9 后端部分）→ ② 受影响测试断言刷新
  → ③ 全量回归。
- F2：① §1.1 前端清单逐处修正（#6–#8）→ ② 受影响断言刷新 → ③ 前端四闸门回归。

**外部依赖登记**：

| 外部依赖 | 关联批次 | 用途 | 可用性处置 |
| ------- | ------ | -- | -------- |
| gaussian-kb MCP 服务 | B（子步骤①④） | 词典扩面素材（四项权威核验已于 2026-10-13 完成） | 不可用 → 拼写校验降级为非阻断警告先行、词典扩面恢复后补做（风险 R-1/R-2） |
| crest/xtb 上游 Releases（crest-lab/crest、grimme-lab/xtb） | D | 资产名/URL/校验和实施时实测 | 不可达/校验不符 → 代理重试 → 直连 → 离线手动路径（风险 R-6） |
| GitHub 代理通道（update.sh `GAUFORGE_PROXY` 约定） | D | 下载加速 | 不可用 → `--no-proxy` 直连（风险 R-6） |
| 真机走查环境（WSL2 就绪 + 网络/代理 + crest 上游可达 + g16 可执行在位 + target/release/hq 在位） | D 走查 | 模拟新机闭环验证 | 附录 B 环境检查前置项，不满足即不进入走查（风险 R-7） |

总工量 ≈ **6–8 人天**（A 0.5 + B 1.25–2（含核验与词典扩充阻塞项）+ C 1.5–2 + D 1.75–2.25 + F1/F2 0.5–1 + E 0.25；各分量下界合计 5.75，取整入 6），不含评审返工与走查缺陷修复；人天仅作规模
参照、不作日历承诺（roadmap §3 里程碑按需排期）。

## 3. 关键设计

### 3.1 存储与迁移（v7）

```sql
CREATE TABLE IF NOT EXISTS combo_templates (
  template_id INTEGER PRIMARY KEY,   -- 1–5，显式方案 id，不可变
  name        TEXT NOT NULL,         -- 初始「配置n」
  route       TEXT NOT NULL,         -- 初始 COMBO_TEMPLATE_INITIAL_ROUTE（含 #，全小写）
  nproc       INTEGER,               -- %nprocshared；NULL=未配置
  mem_gb      REAL,                  -- %mem（GB）；NULL=未配置
  cpu         TEXT,                  -- %cpu proc-list；NULL=未配置
  is_default  INTEGER NOT NULL DEFAULT 0,  -- 恒有且仅有一行 =1
  updated_at  TEXT NOT NULL
);
```

- 种子 5 行 `INSERT OR IGNORE`（id 1–5、name=配置n、route=初始值、link0 全空、
  is\_default 仅 id=1）。种子落库**不走校验链**（`validate_and_normalize` 仅
  作用于用户编辑保存路径，旧词典下默认 route 亦不被拦截，§0.1「初始值必须
  合法」指初始值内容合法、非保存校验对象）。
- v7 沿 v2 先例幂等（`IF NOT EXISTS` + `INSERT OR IGNORE`），迁移执行失败或中断后重跑安全。
- `config.py` 新增 `COMBO_TEMPLATE_INITIAL_ROUTE = "#p b3lyp/6-31g(d) opt freq"`
  （**全小写**初始值单一来源，与 ComboFlowDialog 默认值经批次 F2 对齐；GET 响应
  回传 `initial.route` 供前端「清空恢复」用）。
- 契约层 nproc/mem_gb/cpu 为 `string|null`（§3.2），与存储层 INTEGER/REAL/TEXT
  的转换在 `validate_and_normalize` 单点完成；GET 响应回传规范字符串形态
  （如 nproc=`"4"`、mem_gb=`"8"`、cpu=`"1-4"`，mem_gb 为去尾零 GB 数值）。
- repo：`get_all()`（按 id 序）、`update(id, fields)`；is\_default 置 1 时
  同事务清其余行（radio 语义：**默认方案不可取消、只能改选**）。
- 豁免态不落库：`ignore_spelling` 为 PUT 请求布尔，仅当次生效。
- **归一化入库**（需求三）：route 与 link0 三字段保存时 casefold 后落库，
  响应回传归一化值（G16 大小写不敏感，不改变语义）。

### 3.2 校验矩阵（`validate_and_normalize`，批次 B 通用校验单点）

保存时一次性执行、**errors 全量返回**（422 `VALIDATION_FAILED`，
`details.errors[]` 形态沿 `{"field","line","reason","message"}`；`name`/`route`
清空属「恢复初始值」语义，不报错）：

| 校验项            | 规则                                                                                                                                                                    | reason                                               |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| name           | 空 → 恢复「配置n」（清空恢复初始值语义），不报错                                                                                                                                            | —                                                    |
| route 非空/恢复    | 空 → 恢复初始 route；不报错                                                                                                                                                    | —                                                    |
| link0 三字段    | 空 → 保持 NULL（未配置语义），不报错；「清空恢复初始值」对 link0 即恢复为空（§0.1/§3.1）                                                                                                                       | —                                                    |
| route 文法       | **单行约束**：route 为单行文本（多行 422）；以 # 开头；无空行（以 # 开头与空行两项复用 candidates.py 既有判定理由；`multi_line_route` 系本域新增 reason）                                                                                                                    | `route_must_start_with_hash` / `multi_line_route` / `blank_line_in_route` |
| route 拼写       | token 按 `[/\s#]+` 切分、casefold **精确匹配**白名单（`keywords.txt`，经 gaussian-kb 扩大提取面再生、全小写）；**键值形 token（`key=value`）以键名精确匹配白名单且值非空放行**（补录 2026-10-14 批次 B 实施：`temp=310` 等任意数值形不可能逐值入词典——§0.4 口径 1「已配置 → 校验值合法性」的隐含前提，值合法性归温度等对应值校验；未知键名的键值形仍属词典外）；校验函数带 **mode 参数（enforce/warn，由词典覆盖面定案决定，§8.1）**：enforce → 词典外 error，请求 `ignore_spelling=true` 时该批词典外 token 降级放行；warn → 200 + `notice.spelling_warnings` 警告放行（携带词典外 token 清单，对齐既有 save\_block 非阻断语义）                               | `keyword_not_in_dict`（message 含 token；warn 模式不进 `errors[]`，仅以 `notice.spelling_warnings`（词典外 token 原文清单）回传，`errors[]` 为空）               |
| 温度（Freq 联动） | route 含 freq（**定案**：token 精确等值 `freq` 或 `freq=` 前缀，casefold；freq 页全部变体均形如 `freq[=opts]`，KB 核验 2026-10-13）：不含 `temp=`/`temperature=` → **自动补** **` temperature=298.15`**（前导空格系追加拼接分隔符、入库值含之；§0.4 口径 1 定案；归一化，响应 notice，非 error）；含任一 → 值合法性＝单值正数（KB 核验 2026-10-13：官方仅单值开尔文语法，无列表形态） | `temp_value_invalid`                                 |
| nproc          | 非空时须为正整数字符串（如 `"4"`；`"0"`/`"-1"`/`"2.5"` → error；入库转 INTEGER）                                                                                                                                                | `nproc_not_positive_int`                             |
| mem\_gb        | 非空时须为数值字符串（GB；`"abc"` → error；入库转 REAL、去尾零；模板域限 GB 单一单位记账，与 `_MEM_VALUE_RE` 多单位不同——刻意简化避免换算歧义）                                                                                                                | `mem_value_invalid`                                  |
| cpu            | 非空时须为 `_cpu_list_count` 可解析字符串（`"a-b"` → error）                                                                                                                                             | `cpu_list_invalid`                                   |
| mem×核数         | mem\_gb 与有效核数（nproc ?? cpu 核数）同时非空时：mem\_gb < 核数 × 1.0 → error                                                                                                        | `mem_below_per_core_floor`                           |
| nproc×cpu      | 两者同时非空时核数匹配——**定案：cpu 核编号总数 ≥ nproc**（相等为常规形态，如 nproc=4/cpu=1-4；不足如 1-3 → error；多于如 1-5 **默许不拦**。G16 官方未定义 %CPU 与 %NProcShared 共存行为，匹配口径为产品定案 2026-10-13，§0.4 口径 5；nproc 空而 cpu 非空时仅做书写合法性校验）                                                            | `nproc_cpu_mismatch`                                 |
| 符号引用           | route/link0 含 `@task:`/`@exec:` → 拒（精修模板携带符号引用会被 `validate_queue_members` 拒，保存时前置拦截；复用 dependencies 的 `parse_link0_refs` 判定）                                          | `link0_symbol_ref_forbidden`                         |
| 全小写归一化        | 非错误项：保存时 route/link0 值 casefold 归一化后入库，响应 notice 标注 `normalized`（与 temp 补齐 `temp_applied` 并列）；回显归一化值                                                                                     | —                                                    |

**词表三 reason 值域全集（批次 A 交付范围，11 项，与 openapi 文件头一一对应）**：
`route_must_start_with_hash`、`multi_line_route`、`blank_line_in_route`、
`keyword_not_in_dict`、`temp_value_invalid`、`nproc_not_positive_int`、
`mem_value_invalid`、`cpu_list_invalid`、`mem_below_per_core_floor`、
`nproc_cpu_mismatch`、`link0_symbol_ref_forbidden`。

> nproc/mem_gb/cpu 契约为 `string|null`：`"0"`/`"-1"`/`"2.5"`/`"abc"` 等值级
> 问题全部由校验单点给出 reason（前端以文本形态提交，规避框架层兜底）；仅结构级
> 类型错误（如 nproc 提交 JSON number 而非 string）由 FastAPI 422 直接返回、不进
> `errors[]` 细分 reason（与 ui\_prefs 先例口径一致，避免校验服务与框架层两处兜底）。

### 3.3 端点

- `GET /combo-templates` → `{templates: [<ComboTemplate>×5 按 id 序],
  initial: {route}}`，无副作用（initial 不含 link0：link0 初始值为空，前端清空即恢复，
  无需来源，§3.1/§3.2）。
- `PUT /combo-templates/{templateId}`：body = name/route/nproc/mem\_gb/cpu +
  `ignore_spelling?` ＋ **`is_default?`**（nproc/mem\_gb/cpu 均 `string|null`，
  其余 boolean/string；§3.2；**补录 2026-10-14**：`is_default` 系批次 C
  「设为默认」复选框的承载字段、字段缺省/空值语义系「未携带→恢复初始值」
  的契约表达，批次 B 实施时按文档先行补契约定案——Update 字段全部可选，
  name/route 缺省或空恢复初始值、link0 三字段缺省或空置 NULL；
  is\_default=true 时本条置默认并同事务清其余行）；**PUT 为全量替换
  语义**——未携带/空值字段按 §3.2 恢复初始值（name/route）或置 NULL
  （link0 三字段），不做部分更新。校验 → 归一化（casefold + temp 补齐）→
  落库 → 200 返回
  更新后条目（notice：`{temp_applied: bool, normalized: bool,
  spelling_warnings?: string[]}`——warn 模式未豁免的词典外 token 与 enforce
  豁免放行两种情形均回传 token 清单供前端提示）；404（templateId ∉ {1..5}）；
  422 details.errors 全量（**enforce 模式下词典外 token 以
  `reason=keyword_not_in_dict` 条目回传、`message` 含 token 原文；前端据该
  reason 判定渲染「忽略拼写警告并保存」豁免按钮，豁免集＝该批该 reason 的
  token 集**）。
- **并发取舍**：单机单用户场景、不设并发/乐观锁控制（`updated_at` 仅审计），
  多标签页同编理论可互相覆盖，接受该取舍（如有需要后续版本引入基线比对）。
- 无 SSE 事件（对话框打开时拉取，ui\_prefs 同口径理由）。

### 3.4 前端交互规格（批次 C，验收以附录 A 断言清单为准）

- **入口**：SettingsView 运行级参数区「组合流模板」按钮 → 弹窗
  （ConfirmModal 外壳，QueueEditorModal 同款：默认插槽 + #foot）。
- **方案框**：顶部一排 5 个矩形框（`.preset/.preset--on` 选中范式放大），
  显式数字 1–5 + 配置名 + 默认徽标；点击选中（accent 描边）即展开下方编辑
  区；打开自动选中方案 1。
- **编辑区**：配置名输入框、route textarea（**单行约束，前端 @input 剥离换行符单行化**，
  粘贴多行亦不可构造）、link0 三编辑框（%nprocshared 文本框 inputmode=numeric / %mem GB
  文本框 inputmode=decimal / %cpu 文本框默认置灰，勾选 %nprocshared 旁
  「指定CPU核心」复选框启用；三者均以文本形态提交，值级校验归后端单点，§3.2）、
  「设为默认」
  复选框（radio 语义）。输入值不做实时改写，保存时后端归一化回显。
- **保存**：PUT → 422 时 errors 全量显著展示（字段级红描边 + 顶部错误
  清单——SettingsView errors 映射与 QueueEditor `q-dep-errors` 清单双
  范式）；warn 警告与 enforce 豁免放行均按 `notice.spelling_warnings` 展示
  token 清单，出现词典外 token 时提供「忽略拼写警告并保存」豁免按钮（豁免
  记忆作用域 = **弹窗打开期间 × 全局 token 集**——跨方案共享，关闭弹窗即清空；
  **保存失败不清豁免记忆，成功后本会话仍保持，重开重新校验**）；temp 自动补齐时回显归一化 route 并提示「已补齐」、
  归一化小写时提示「已归一化」。**未点保存：本地改动丢弃**，切方案/关闭
  均回已保存值。
- **ComboFlowDialog**：打开时并行拉 GET /settings + GET /combo-templates，
  新增方案下拉（5 条配置名，默认选中 is\_default 条），选择即回填 route 与
  link0（结构化字段序列化为 `%nprocshared=…`/`%mem=…GB`/`%cpu=…` 行，
  **全小写**、仅非空项）；保留手改能力；提交载荷契约不变。

### 3.5 crest/xtb 部署（批次 D）

- `scripts/deploy/setup_deps.sh`：幂等判据 = `--version` 冒烟通过方视为
  已安装（仅目录存在不算；冒烟失败视为半成品残留，清理后重装）→ 下载
  crest 3.0.2（`--xtb` 可选装 xtb 6.7.1）→ 解压 `--dest`（默认 `~/opt`）→
  chmod → `--version` 冒烟 → 打印 crest\_root/xtb\_root 设置页指引。代理复用
  update.sh 的 `GAUFORGE_PROXY`/`--proxy`/`--no-proxy` 参数约定（**非
  install.sh 的 GAUFORGE\_GH\_PROXY**，两变量不混用）；**不随部署包分发
  第三方二进制**；上游资产名/URL/校验和**实施时实测核验**（crest-lab/crest、
  grimme-lab/xtb Releases，不凭记忆写死）；**校验和对照源定案**：以上游官方
  GitHub Release 页面（或官方发布的 checksums 文件）为对照源，代理下载后与
  官方信道对照，上游未提供校验和时记录发布 tag 与资产体积并在附录 B 标注该
  口径；「crest 3.0.2 内嵌 tblite、运行时
  无需 xtb」口径写入脚本帮助与文档；install.sh 完成提示不枚举 setup\_deps.sh，
  统一由随包分发的 deployment.md「CREST/xtb 接入」节承担指引。
- `scripts/package_release.sh`：根脚本清单加 setup\_deps.sh（CLI update.sh 对新增
  根脚本自动补装，旧部署升级即得）；**并将 `docs/references/deployment.md` 纳入部署包**
  （显式单文件 copy 该文件、不整目录拷贝 docs/references，使离线机与新部署机可获得「CREST/xtb 接入」节——
  需求二核心场景，update.sh 的 `cp -a docs` 随包自动触达旧部署）。
- `deployment.md`：增「CREST/xtb 接入」节（在线/离线两路径、设置页
  crest\_root/xtb\_root 配置、验证闭环：组合流 503 → 部署 → 提交通过；
  xtb 非运行必需说明）；该文件须随部署包分发（见上条）。
- **安装布局与运行级对齐**：解压目标须与运行级 `crest_root`/`xtb_root`
  默认值（`web/src/config.py:49-50`
  `~/opt/crest-3.0.2`/`~/opt/xtb-6.7.1`）一致，使部署后零配置可用；自定义 `--dest`
  时脚本打印设置页 `crest_root`/`xtb_root` 指引，走查步骤显式含该设置环节。
- **走查环境**（附录 B 前置）：真机 WSL2、可访问上游 Releases（或代理）、
  crest 目标目录可写；`--dest` 指向自定义目录模拟新机（不污染既有 ~/opt）。

## 4. 测试矩阵（先测试后实现）

| 测试文件（拟）                    | 覆盖 | 关键用例                                                                                                                                                                                                |
| -------------------------- | -- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| test\_combo\_templates.py  | B  | 种子幂等与重启 roundtrip；is\_default 迁移事务性（置 1 清其余、恒唯一）；校验矩阵逐 reason（11 项：route 文法/单行约束/拼写双形态〔enforce：拦截 422 + 豁免放行；warn：`notice.spelling_warnings` + 200 放行〕/temp 补齐与非法值〔定案 §0.4：补 `temperature=298.15`、检测集合含 `temp=`/`temperature=`、单值正数〕/nproc `"0"`/`"-1"`/`"2.5"` 字符串形态 → `nproc_not_positive_int`、mem `"abc"` → `mem_value_invalid`、cpu `"a-b"` → `cpu_list_invalid`/nproc 提交 JSON number → FastAPI 422 不入 errors[]（§3.2 末注）/mem 下限/nproc×cpu〔定案 §0.4：cpu 核编号总数 ≥ nproc、不足拦多于默许〕/符号引用拒绝）；清空恢复初始值（name/route）；归一化断言（route/link0 casefold 入库、响应回传归一化值、notice 标注）；errors 全量一次返回断言；端点 200/404/422 + assert\_contract\_schema |
| test\_store\_sqlite.py（增补） | B  | v7 迁移版本推进、幂等重跑、表结构断言（沿 v3/v4 用例形状）                                                                                                                                                                  |
| test\_extract\_keywords.py（增补） | B  | 词典再生一致性闸门 + **新断言：词典全小写、无重复词、排序稳定**（需求三）                                                                                                                                    |
| 既有回归（F1/F2 批次刷新）              | F1/F2  | 派发注入行断言更新为 `%nprocshared=`/`%mem=…GB`（workspace 测试）；断点续跑 `%oldchk=` 行断言（resume 测试）；物化改写前缀小写断言（materialize 测试）；candidates 校验消息文案断言同步刷新；黄警文案小写形态断言（前端，附录 A A24 走查）                                                            |
| 序列化往返（test\_combo\_templates.py 增补，B 批次） | B | PUT 保存后 GET 回传 link0 三字段规范字符串形态（`%nprocshared=4`/`%mem=8GB`/`%cpu=1-4`，仅非空项、全小写、mem\_gb 去尾零）；提交载荷与既有 `POST /workflows/conformer-refinement` 契约断言一致（提交链零改动回归） |
| 序列化往返 UI 走查（附录 A A11，C 批次） | C | ComboFlowDialog 方案下拉选中后回填三行与 GET 值一一对应（A11 逐条留痕） |
| 既有回归                       | 全程 | test\_error\_codes / test\_openapi\_ssot / gen:types 零 diff / test\_workflow\_crest（组合流链零改动不回归）/ save\_block 非阻断语义回归（check\_route\_spelling 仍不进 errors\[\]；词典扩充致近似警告命中面变化属可接受行为，不作为回归断言）                                            |
| enforce 切换回归（新增，§5 #6 挂钩） | #6  | 仅切换提交执行：词典外 token → 422 拦截；`ignore_spelling=true` → 同批放行；多词典外 token 全量回传；A7a 走查补录                                                                                                                                    |
| test\_deploy\_scripts.py（增补） | D  | setup\_deps.sh 幂等重跑跳过、半成品残留（`--version` 冒烟失败）清理后重装、`--proxy`/`--no-proxy`/`GAUFORGE_PROXY` 参数约定、`--xtb` 可选装路径、安装布局与 crest\_root/xtb\_root 默认值对齐 |
| D 走查                       | D  | `--dest` 自定义目录模拟新机；503 → 部署 → HTTP 200 + workflow\_id 闭环；脚本幂等重跑；部署包含 deployment.md（D5）；留痕入附录 B                                                                                   |

## 5. 提交序列与进度同步

单类变更/提交，文档→测试→实现→进度同步（测试与实现同提交）：

| #  | 提交                                    | 内容                                 |
| -- | ------------------------------------- | ---------------------------------- |
| 1  | docs(plans): 插波计划文档                   | 本文档（评审修订后定稿）                       |
| 2  | docs(api): 组合流模板契约 diff               | schema/paths/词表三（11 项）+ 再生产物    |
| 3  | feat(web): combo\_templates 迁移与存储     | v7 + repo + config 常量 + 测试         |
| 4  | feat(parse): 词典扩充再生（必须实施项，最大化覆盖度） | extract\_keywords.py 提取面扩展 + keywords.txt 再生（§8.1 必须实施项、最大化覆盖度；gaussian-kb 不可用时按 §8.1 降级语义先行、服务恢复后补做扩面；是 #5 校验服务 enforce 模式的硬前置，独立提交） |
| 5  | feat(web): 模板校验服务与端点                  | validate\_and\_normalize + 路由 + 测试；**默认 mode=enforce**（词典已由 #4 就位）；仅当 #4 词典未达 §8.1 判据 ①②③ 时以 warn 上线（降级形态） |
| 6  | feat(web): 拼写校验切换 enforce             | **条件提交**：仅当 #4 词典未达判据、#5 以 warn 上线时执行，词典达标后切换拦截（§8.1）；**验收**：① §8.1 判据 ①②③ 逐条复核留痕（附录 B B3）；② 附录 A A7a 补走查留痕；③ §4 enforce 切换回归用例组全绿（拦截 422／豁免放行／多 token）；④ 契约闸门重跑（gen:types/gen\_models 零 diff + ssot + error\_codes）；**回填**：A7a 补走查与 B3 复核随本提交 append-only 回填附录 B |
| 7  | feat(web): Link0 全小写收口（后端，F1）           | §1.1 #1–#5/#9 后端部分 + 受影响测试刷新    |
| 8  | feat(frontend): 组合流模板配置弹窗             | Modal + 设置页入口                      |
| 9  | feat(frontend): 组合流对话框方案选择            | 下拉 + 回填                            |
| 10 | feat(frontend): 提交链全小写收口（前端，F2）          | §1.1 #6–#8 前端部分（默认值/序列化/文案）     |
| 11 | chore: 走查截图目录忽略规则                | .gitignore 增补 docs/plans/assets/m4-combo-deploy/（D 批次走查前置，独立 chore 不与 docs 提交混类） |
| 12 | feat(scripts): crest/xtb 部署脚本         | setup\_deps.sh + 打包接线（根脚本加 setup\_deps.sh + deployment.md 单文件纳入部署包） |
| 13 | docs(references): deployment.md 部署接入节 | CREST/xtb 接入                       |
| 14 | docs(plans): 走查记录回填                   | 附录 B 回填 + 随查随修 fix 一缺陷一提交另计     |
| 15 | chore(release): 3.2.0 冻结五步            | 发布属用户授权动作，届时确认；降级交付时按 §8.1 复核 next\_steps 遗留项 |

#6 为条件提交（仅 #4 词典未达判据、#5 以 warn 上线时执行）：不执行时后续编号不前移，跨节引用一律按
提交名而非编号。**批次 B 验收时点**：#3（迁移+repo+常量）仅跑迁移/repo/种子幂等断言；
#5（校验服务+端点）收口批次级验收（§3.2 校验矩阵逐 reason 全绿、双形态断言）；
#4（词典扩充）单独跑 test\_extract\_keywords.py。每项随行 chore(progress) 登记；
CHANGELOG.jsonl unreleased 与 progress.json unreleased 同步追加；开工时 in\_progress 登记本波。

## 6. 闸门清单（每批次提交前）

`uv run pytest` 全量、`scripts/validate_progress.py`、
`scripts/gen_changelog_md.py --check`；契约批次另跑 `npm run gen:types`
零 diff + gen\_models.py 零 diff + `test_error_codes.py` +
`test_openapi_ssot.py`；前端批次另跑 `npm run build`（vue-tsc 零错误）、
`scripts/audit_frontend_offline.sh`、`scripts/check_tokens.py`、
`scripts/check_contrast.py`；批次 B 另跑 `test_extract_keywords.py`
（含词典全小写断言）；F1 触及既有派发/续跑/物化链，**必检 hq 产物**（确认
`target/release/hq` 在位——缺失时 `test_e2e_fake_g16.py` 等静默跳过，通过数
虚高≠闸门通过，AGENTS.md §6.1 第 4 条）；B 按设计不触及派发链（服务端组合流
提交链零改动，§1），若 R-5 触发批次边界调整则补检。

## 7. 风险登记

| # | 类别 | 描述 | 触发条件 | 应对预案 | 关联批次 |
| - | --- | --- | ------- | ------ | ------ |
| R-1 | 技术 | 词典覆盖不足致误拦截：实测 97 词无 b3lyp/6-31g 任何词面（hf 等部分方法词已在词典内，2026-10-13 核验），默认 route 在 enforce 下保存必被拦截 | 词典扩充未达 §8.1 达标判据即切换拦截 | 词典扩充为**必须实施项、最大化覆盖度**（#4，#5 enforce 模式硬前置）；未达标 → #5 拼写校验以**非阻断警告（warn）**上线（与既有 check\_route\_spelling 语义对齐），达标判据见 §8.1（判据 ①＝默认 route 全 token 精确匹配通过，即死锁消除底线），达标后经 §5 #6 切换拦截；**附带影响**：词典扩充同步改变既有 save\_block 的 difflib 近似警告命中面（非阻断、可接受，不视为回归——见 §4 既有回归行口径） | B |
| R-2 | 外部依赖 | gaussian-kb MCP 服务不可用，阻塞词典扩面（四项核验已于 2026-10-13 完成，§8.2） | 服务未启动/无响应 | 拼写校验按降级非阻断警告交付、词典扩面留待服务恢复补做；批次 B 开工时若服务不可用致扩面无法进行，按 §8.1 降级语义处理 | B |
| R-3 | 技术 | gaussian-kb 核验结论偏离 §3.2 暂定口径（temp 语法、Freq 变体集、nproc×cpu 语义、temperature 区分） | 核验结论与暂定口径不符 | 先修订本文档（矩阵/契约/验收）再实现——文档→测试→实现闸门，修订随核验结论同步落本文档（断言回填机制见 §2 子步骤①）；**若修订涉及 openapi.yaml（reason 值域/notice 结构变化）**：随 §5 #5（或 #6）同提交落，并重跑 §6 契约闸门（gen:types/gen\_models 零 diff + ssot + error\_codes）。**2026-10-13 已执行：四项核验完成，①③④ 项结论偏离暂定口径（①④ 被核验推翻、③ 改写系用户裁决）并已按定案修订本文档（§0.4/§3.2/§4/附录 A），reason 值域与 notice 结构不变、openapi 无涉** | B |
| R-4 | 资源/时间 | 走查缺陷修复量超预期，E 顺延 | 同一断言条目回归失败 ≥2 次，或附录 A/B 缺陷累计 ≥5 条 | 修复一缺陷一提交另计（§5 #14）；总工量不含修复；**放行判据**：阻断性缺陷（断言失败、闸门不过）清零方可过 E；非阻断缺陷（文案/样式）可附清单放行并登记；E 按实际推进并提示用户 | C/D/E |
| R-5 | 技术 | 「组合流提交链零改动」声明失效（序列化/归一化触及既有消费链） | 序列化往返或归一化与 \_refine\_input/link0 数组形态不符 | §4 序列化往返断言（test\_combo\_templates.py + A11 走查）先于实现；发现触及 → 调整批次边界 + 补 hq 产物检查（§6） | B/C/F1/F2 |
| R-6 | 外部依赖 | 上游 crest/xtb 资产下载失败或校验和漂移；下载中断残留半成品安装目录 | Releases 不可达 / sha256 不符 / 安装目录存在但 `--version` 冒烟失败 | 代理重试 → `--no-proxy` 直连 → 离线手动路径（文档两路径）；半成品残留 → 清理后重装（幂等判据见 §3.5）；资产实测核验留痕附录 B | D |
| R-7 | 资源 | 真机走查环境不满足 | 模拟新机无网络/g16、目标目录不可写 | 附录 B 环境检查前置项，不满足不进入走查，缺陷登记后顺延 | D |
| R-8 | 技术 | 既有大小写违反存量统计遗漏（表外违反处） | F1/F2 实现发现 §1.1 清单外位置 | 清单为 SSOT，补录清单与修复同提交（文档→实现） | F1/F2 |
| R-9 | 技术 | 豁免会话记忆语义漂移（保存失败/刷新后豁免态丢失被误判） | 422 后豁免 token 消失或跨会话残留 | §3.4 口径定案（失败保留、成功保持、重开重校验）+ 附录 A A18 断言 | C |
| R-10 | 时间 | B 阻塞子步骤（核验+扩充）完成时间不确定 | 服务不可用或提取面定案往返多轮 | 降级非阻断先行、B 主体不整体阻塞；扩充独立提交；E 验收时点由用户按 §8.1 降级口径确认 | B/E |
| R-11 | 技术（已接受） | 多标签页同编并发 PUT 互相覆盖（§3.3 并发取舍的登记留痕） | 同 templateId 双端并发保存 | 接受取舍（单机单用户场景）；如需收敛，后续版本引入基线比对（§3.3） | B |
| R-12 | 外部依赖/合规 | 上游 crest/xtb 许可条款核验发现限制（禁止引导下载/附加再分发义务） | §8.3 许可核对留痕不通过 | 文档改「用户自行下载」口径并移除脚本内下载引导，或经用户当次决策接受条款后放行 | D |
| R-13 | 外部依赖/时间 | crest 部署整体不可交付（R-6 三级重试穷尽且离线手动路径不可行，或 R-12 两种应对均未被用户接受），E 依赖 A–D 致 3.2.0 发布无限期阻塞 | R-6 穷尽且离线路径不可行 / R-12 应对均未被接受 | 提交用户当次决策：(a) 拆版——3.2.0 仅含 A/B/C/F1/F2/E，D 顺延 3.3.0（E 依赖收窄为 A/B/C/F1/F2，对应 D 交付物移出本次发布范围）；(b) 全波顺延；决策留痕附录 B | D/E |

## 8. 开放事项（阻塞项与实施时核验项）

1. **词典扩充（必须实施项，最大化覆盖度；为 #5 校验服务 enforce 模式的硬前置；无用户侧交付物）**：gv6 关键词名单在
   gaussian-kb 结构化知识库中可查；扩充动作 = 扩展  `scripts/extract_keywords.py` 的提取范围后**再生  `keywords.txt`**（输出 casefold，全小写）。
   **提取面定案原则：尽可能从 gaussian-kb 提取、最大化词典覆盖**——以 gaussian-kb中可规则化提取的全部关键词内容为上限（keyword category 页 slug+标题变体为基础，另纳具名方法面、具名基组面与 gv6 route 关键词对照面等，见下方素材源）；**不得仅按判据③最低清单提取**。
   具体提取面以 gaussian-kb 实际内容定案。既有「入库字典与重生成一致」闸门（test\_extract\_keywords.py）天然覆盖扩充后的词典，另增全小写/去   重断言，不引入旁路词典文件。
   **实施时须启动 gaussian-kb 服务（MCP）**——提取与第 2 项权威核验同需该服务，当前未启动属正常。
   **达标判据（可量化，enforce 切换闸门）**：① 初始 route 全部 token（`p`/`b3lyp`/`6-31g(d)`/`opt`/`freq`）在词典内精确匹配通过；② `temp`/`temperature` 与 freq 变体集在词典内（**已满足**：现行词典已含 `temp`/`temperature`〔keywords.txt
   L89/L90，slug+标题变体〕与 `freq`；freq 变体集**定案**＝`freq` 等值或
   `freq=` 前缀，KB 核验 2026-10-13 与官方形态一致）；③ 具名方法面与具名基组面在词典内——方法面：
   `hf`/`mp2`/`b3lyp`/`wb97xd`/`cam-b3lyp`/`m06` 等 **≥10**（暂定下界，
   N 以 gaussian-kb 实际内容定案后回填替换）个具名方法；基组面：
   `6-31g(d)`/`6-31+g(d,p)`/`cc-pvtz`/`def2-svp`/`lanl2dz` 等 **≥10**（暂定下界）
   个具名基组——**此数量级仅为 enforce 切换闸门的底线验证集，非提取目标**
   （提取面最大化原则见本条开头，用户裁决 2026-10-13）；具名清单在实施时由
   gaussian-kb 内容定案后回填本文档，逐条精确匹配断言。
   **具名清单定案回填（2026-10-14 批次 B 实施，逐条精确匹配断言落
   `web/tests/test_extract_keywords.py::test_gate_named_methods_and_bases_in_dictionary`，
   全部命中）**：具名方法面 27 项——`hf`/`mp2`/`b3lyp`/`wb97xd`/`cam-b3lyp`/
   `m06`/`m062x`/`m11`/`mn15`/`ccsd`/`casscf`/`am1`/`pm6`/`pbepbe`/`hseh1pbe`/
   `wb97x`/`lc-wpbe`/`b97d`/`b2plypd3`/`bhandhlyp`/`pw6b95d3`/`tpsstpss`/
   `mp4(sdtq)`/`cbs-qb3`/`w1bd`/`uff`/`amber`；具名基组面 20 项——
   `6-31g(d)`/`6-31g(d,p)`/`6-31+g(d,p)`/`6-311+g(d,p)`/`6-311++g(2d,2p)`/
   `6-31g(3df,3pd)`/`sto-3g`/`3-21g(d)`/`cc-pvtz`/`aug-cc-pvtz`/`def2svp`/
   `def2tzvp`/`lanl2dz`/`cep-121g`/`svpfit`/`dgdzvp`/`qzvp`/`epr-iii`/`midix`/
   `cbsb7`（判据示例中的 `def2-svp` 系文献连字符形，basissets 页明示 G16
   关键词形为「连字符去除」的 `def2svp`，按 KB 定案收录该形）。
   **素材源已核实（2026-10-13，按此最大化提取）**：
   ① keyword category 全部页 slug+标题变体（现行 97 词基础，不动摇）；
   ② 方法面＝`gv6-gaussian-calculation-setup-keywords-and-options` 页
   UI→route 全小写对照表（b3lyp/cam-b3lyp/wb97xd/mp2/ccsd/casscf/am1/pm3/
   pm6/uff/amber…，结构化程度最高、首选）与 `dft` 页正文泛型名（含 Truhlar
   组、PBE 组、色散表等章节）；复合方法页（gn/w1/cbs）正文方法名实施时同面
   评估；
   ③ 基组面＝`basissets` 页正文（sto-3g/3-21g/6-31g 系列及 `(d)`/`(d,p)`/
   `+`/`aug-` 形态规则；注意 route token 切分为 `[/\s#]+`，`6-31+g(d,p)` 为
   完整单 token，词典须收录该形态）与 `pseudo` 页示例（`lanl2dz`）；
   ④ 其余 structure/utility 页正文中可规则化提取的关键词形态（如
   gen/pseudo/extrabasis 页示例 route 中的 token），实施时按噪声可控原则
   同面评估。实测底线：现行 97 词无 b3lyp/6-31g 任何词面
   （2026-10-13 核验），默认 route 在 enforce 下保存必被拦截——判据 ① 即
   该死锁场景的消除底线。**降级语义**：
   词典扩充（#4）为必须实施项、最大化覆盖度；仅当 gaussian-kb 服务不可用
   致扩充无法按判据达标时，组合流模板域拼写校验以**非阻断警告（warn）**上线
   （拦截逻辑与词典内容解耦），扩充达标后经 §5 #6 切换为默认拦截——与 R-1/R-2 联动。
   **降级交付时批次 E 的替代验收口径**：附录 B 的 B1/B2 留痕允许标注「待补」，附录 C
按降级口径复核放行；「切换 enforce」作为后续独立提交（§5 #6），不阻塞3.2.0 发布。
**进度跟踪锚**：warn 降级交付时，将「词典扩充 + enforce 切换」
登记入 progress.json 的 `next_steps`（跨版本遗留项的规范载体：冻结第 4 步仅
清空 unreleased、不动 next_steps，且每次发布须复核其与现状一致——changelog-spec
§2.3；不登记入 unreleased，避免与 AGENTS.md §5.2 冻结清空冲突），触发条件＝
gaussian-kb 服务恢复，完成时限绑定「下一 minor 发布前」；复核见附录 C C11
与 E 批次验收。
2. **gaussian-kb 权威核验项（✅ 2026-10-13 已完成预核验，结论已回填 §0.4/§3.2/附录 A；同
   m4-plan §0.5 先例留痕；批次 B 开工时复核本节结论即可，届时服务不可用按
   §7 R-2 处理）**。核验结论与定案：
   ① **temp 关键字拼写与值语法**：官方页 gaussian.com/temp（页面标题
   Temperature）定义为热化学分析温度（开尔文），route 示例唯一形态
   `Temperature=<值>`，默认 298.15 K，Options 仅 Default；全库检索无
   `Temp=` route 示例、无列表值语法 → 定案：自动补 **`temperature=298.15`**、
   值校验单值正数（§0.4 口径 1）。
   ② **Freq 变体检测集合**：freq 页全部变体（VCD/ROA/Anharmonic/VibRot/
   TProjected/ReadFCHT/ReadAnharm 等）均形如 `Freq[=opts]`，capabilities 页
   明确「Freq: Frequency and thermochemical analysis」→ 定案：检测＝`freq`
   等值或 `freq=` 前缀（暂定口径成立）。已知边界：`Opt=CalcAll` 优化完成自动
   附加频率分析且 route 无 freq token（登记不拦，组合流模板场景罕见）。
   ③ **nproc×cpu 共存语义**：cpu 核编号总数 ≥ nproc，
   不足拦、多于默许；%cpu 非必选、存在即校验（§0.4 口径 5）。
   ④ **temperature 与 temp 的区分**：`temp=`/`temperature=` 均视为已配置
   温度、不重复补齐。
3. **上游下载资产**：crest/xtb Releases 的确切资产名/URL/校验和实施时
   实测核验；两家许可条款一并核对留痕（落盘附录 B）。
4. **发布授权**：3.2.0 冻结与任何推送均须用户当次明确授权。

## 附录 A：交互规格走查断言清单（批次 C 验收，逐条留痕入附录 B）

| # | 断言（预期行为，可勾选） |
| - | ---------------------- |
| A1 | 打开配置页自动选中方案 1，编辑区显示「配置1」与初始 route（小写形态） |
| A2 | 顶部 5 个矩形框均存在、显式数字 1–5、初始命名「配置n」 |
| A3 | 默认徽标全页仅一处（初始方案 1），改选后唯一迁移 |
| A4 | 默认方案不可取消（radio 语义），仅可改选 |
| A5 | route 清空 → 保存 → 重新打开 GET 返回初始 route；name 清空 → 保存 → 恢复「配置n」 |
| A6 | route 文法违规（非 # 开头/多行/空行）→ 422，顶部错误清单一次全报全部 reason（断言 errors 条数 = 违规项数）；多行/空行分支经 API 直调断言（test\_combo\_templates.py 覆盖，前端 @input 单行化处理致 UI 不可构造），UI 走查仅覆盖非 # 开头分支 |
| A7a | 〔仅 enforce 模式执行，§3.2〕词典外 token → 拦截 422；点「忽略拼写警告并保存」→ 落库；重开配置页再编辑同 token → 重新拦截（豁免仅会话内记忆）；同会话切方案后编辑同 token → 不再拦截（豁免跨方案共享，§3.4） |
| A7b | 〔仅 warn 模式执行，§3.2〕词典外 token → 200 放行，`notice.spelling_warnings` 含该 token 且警告提示展示 token 清单 |
| A8 | route 含 freq（定案：`freq` 等值或 `freq=` 前缀，KB 核验 2026-10-13）且无 `temp=`/`temperature=` → 保存后 GET route 含 `temperature=298.15`、响应 notice `temp_applied=true`、编辑区回显归一化 route 并提示「已补齐」；route 已含 `temperature=310` → 保存后不重复补默认温度 |
| A9 | 温度非法值（定案：非单值正数，如 `temperature=abc`/`temperature=-1`/`temperature=300,310`〔官方仅单值语法〕）→ 422 `temp_value_invalid`（定案来源留痕附录 B） |
| A10 | mem 低于 核数×1GB → 422 `mem_below_per_core_floor`；nproc×cpu 按定案断言（cpu 核编号总数 < nproc → 422 `nproc_cpu_mismatch`，如 nproc=8/cpu=1-4；多于默许放行，如 nproc=4/cpu=1-5 → 200；定案来源留痕附录 B） |
| A11 | %nprocshared/%mem/%cpu 序列化往返：ComboFlowDialog 方案下拉选中后回填三行与 GET 值一一对应（`%nprocshared=4`/`%mem=8GB`/`%cpu=1-4` 形态、全小写、仅非空项） |
| A12 | 未点保存：切方案/关闭后重开回已保存值（本地改动丢弃） |
| A13 | route/link0 含 `@task:`/`@exec:` → 422 `link0_symbol_ref_forbidden` |
| A14 | %cpu 编辑框默认置灰，勾选「指定CPU核心」复选框后才可填 |
| A15 | nproc 输入 0 / -1 / 2.5（文本形态提交，§3.2）→ 422 `nproc_not_positive_int`，对应编辑框红描边且顶部错误清单含该 reason |
| A16 | mem 输入非数值（如 `abc`，文本形态提交，§3.2）→ 422 `mem_value_invalid`，对应编辑框红描边且顶部错误清单含该 reason |
| A17 | cpu 输入不可解析 proc-list（如 `a-b`）→ 422 `cpu_list_invalid`，对应编辑框红描边且顶部错误清单含该 reason |
| A18 | 422 后点「忽略拼写警告并保存」→ 再次保存不再拦截且落库；保存失败重试，豁免记忆不丢失（会话内） |
| A19 | SettingsView 运行级参数区存在「组合流模板」入口按钮，点击弹出配置弹窗 |
| A20 | ComboFlowDialog 打开时方案下拉含 5 条配置名、默认选中 is\_default 条 |
| A21 | 方案下拉回填后可手改 route/link0，提交载荷按改后值（与既有 `POST /workflows/conformer-refinement` 契约一致） |
| A22 | route 或 link0 输入混合大小写 → 保存后回显归一化小写值，并提示「已归一化」（响应 notice `normalized=true`） |
| A23 | link0 三字段全部清空 → 保存 → GET 返回三字段为 NULL，ComboFlowDialog 回填无 link0 行 |
| A24 | 候选提交确认框黄警文案展示小写形态：缺失 `%nprocshared`/`%mem` 时文案为 `%nprocshared=…`/`%mem=…GB`（无空格），与后端注入行形态一致（F2 #8 收口） |

## 附录 B：走查记录（批次 D/E 留痕载体，回填本文档）

格式（每条目）：

```
- 批次 / 条目：<A1..A24（A7 拆 A7a/A7b）或 AG1 或 FG1/FG2 或 B1..Bn 或 D1..Dn 或 E1..En>
- 前置：<环境检查结果>
- 步骤：<操作序列>
- 预期：<对应验收/断言>
- 实测：<通过 | 失败>
- 留痕：<截图路径 或 日志/命令输出摘录>（截图存本地不入库，默认目录 `docs/plans/assets/m4-combo-deploy/`，路径记录于此；该子目录由 §5 提交「chore: 走查截图目录忽略规则」加入 .gitignore，仅留路径不入库）
- 缺陷：<缺陷编号及处理，fix 一缺陷一提交另计>
```

**环境检查（走查前置，R-7）**：WSL2 就绪；上游 Releases 可达（或代理可用）；
`--dest` 目标目录可写且不与既有 ~/opt 冲突；`target/release/hq` 在位；
g16 可执行在位（组合流精修步骤依赖，与 R-7 触发条件对齐）。
**预期条目（编号域 A/B/D/E）**：D 批次「组合流 503 → 部署 → `POST /workflows/conformer-refinement` 返回 HTTP 200 且响应含 workflow\_id」闭环
（D1，精修实际运行不在 D 走查范围；走查后终止该 workflow 并留痕处置）；脚本幂等重跑（D2）；xtb 可选装与非运行必需说明走查（D3）；上游
资产校验和核验留痕（D4，仅记资产下载与校验和对照，对照源口径见 §3.5）；部署包内含
`docs/references/deployment.md`（D5，离线机/新部署机可获得 CREST/xtb 接入节）；
C 批次附录 A 逐条（A1–A24，A7 拆 A7a/A7b 按当前 mode 执行对应条；**降级交付时
A7a 标注「不适用（enforce 未上线），随 §5 #6 切换补录」**，E 验收认可该标注）；
B 阻塞项留痕：四项核验结论（B1，2026-10-13 预核验结论见 §8.2，开工时复核留痕）、词典扩充再生 diff
（B2，降级交付时允许标注「待补」，§8.1）、enforce 切换判据 ①②③ 复核＋切换
回归用例全绿与契约闸门重跑输出摘录（B3，仅 §5 #6 执行时登记）——B1/B2/B3 与
D4 分列不重复登记；批次级验收留痕：AG1（A 批次词表三 vs §3.2 reason 逐项
grep 对照输出，随提交 #2 回填）、FG1/FG2（F1/F2 §1.1 逐条 git diff 摘录，
分别随提交 #7/#10 回填）；E 批次 3.2.0 冻结五步
执行留痕（E1–E5，逐条对应 AGENTS.md §5.2 冻结五步）。

### 已回填条目

- 批次 / 条目：AG1（A 批次）
- 前置：openapi.yaml 契约 diff 落盘（词表三 11 项文件头清单 + Error schema
  计数行「三张」）
- 步骤：逐 reason `grep -c <reason> docs/api/openapi.yaml`；`grep -n 两张`
  查文件头残留
- 预期：11 项逐一命中（≥1 处）且与 §3.2 reason 清单一一对应；「两张」零残留
- 实测：**通过**（2026-10-14）
- 留痕：grep 计数——route_must_start_with_hash 1／multi_line_route 1／
  blank_line_in_route 1／keyword_not_in_dict 4（词表三+Update/MutationResult
  description+路径说明）／temp_value_invalid 1／nproc_not_positive_int 1／
  mem_value_invalid 1／cpu_list_invalid 1／mem_below_per_core_floor 1／
  nproc_cpu_mismatch 1／link0_symbol_ref_forbidden 1；`grep -n 两张`
  退出码 1（零残留）。契约闸门 test_openapi_ssot.py + test_error_codes.py
  12 passed；models.py／contract.ts 重复再生零 diff（md5 一致）
  ——补注（2026-10-14 独立审查 F-3）：「md5 一致」系同刻再生口径，
  datamodel-codegen 时间戳头字面必变；已随复审整改在 gen_models.py 固定
  `--disable-timestamp`，再生字节幂等自此字面成立（整改见
  m4-combo-deploy-review-A-B.md）
- 缺陷：无

- 批次 / 条目：B1（B 批次，四项核验复核）
- 前置：gaussian-kb MCP 服务可用（2026-10-14 开工复核）
- 步骤：经 MCP 检索 temp/link0/freq 页核对 §8.2 四项预核验结论
- 预期：四项结论与 §8.2 定案一致（①温度单值开尔文默认 298.15；②freq
  变体恒 `freq[=opts]` 形；③%CPU 旨在取代 %NProcShared、共存行为官方未
  定义；④temp=/temperature= 同关键词两形态均算已配置）
- 实测：**通过**（2026-10-14，与 §8.2 逐项一致）
- 留痕：① temp 页（slug=temp、标题 Temperature）正文「Specifies the
  temperature to be used for thermochemistry analysis (in Kelvin)…
  `# … Temperature=300`… The default is 298.15 K」——单值开尔文、默认
  298.15、route 示例唯一形态成立；③ link0 页（Parallel Job Directives 节）
  「%CPU=proc-list … designed to replace the earlier %NProcShared and
  %NProc directives」+ running 页「%CPU 指定具体核、%NProcShared 指定总数」
  ——产品定案（cpu 核数 ≥ nproc 不足拦多于默许）依据成立；② freq 页
  变体节（freq__055 ReadFCHT Value=*temp* 默认回溯 Temp keyword 298.15）
  恒 `Freq[=opts]` 形成立；④ temp 页即 Temperature 页，`temp=` 与
  `temperature=` 同键两形态成立
- 缺陷：无

- 批次 / 条目：B2（B 批次，词典扩充再生）
- 前置：`~/gaussian-kb/data` 结构化数据目录在位（135 页清单 + markdown
  正文，与 MCP 同源）
- 步骤：扩展 `scripts/extract_keywords.py` 提取面（面①manifest 基座 +
  面②gv6 对照表末列 route 切分与 dft 族正则/短语锚点 + 面③basissets 族
  正则与极化/弥散形态生成 + 面④gen/pseudo/extrabasis 评估后不设规则）→
  再生 keywords.txt → `test_extract_keywords.py` 全绿
- 预期：达标判据 ①②③ 全过；词典全小写、无重复、码点排序；真实 KB 重生
  与入库逐字节一致
- 实测：**通过**（2026-10-14；97 → **387** 词条）
- 留痕：再生输出「词条 387 个」；判据① p/b3lyp/6-31g(d)/opt/freq 逐条
  命中、② temp/temperature/freq 及 freq=vcd 等变体命中、③ 具名方法面
  27 项与基组面 20 项逐条精确匹配（清单见 §8.1 定案回填）；全小写/去重/
  排序断言过；`test_real_kb_inrepo_dictionary_matches_regeneration` 逐字节
  一致；基座 97 词零丢失（comm 差集为空）；噪声终查（常见英文词表与词典
  交集）仅 `name`（系面① slug，合法词条）。口径补录：键值形 token
  （temp=310 等）以键名白名单+值非空放行（§3.2 补录）；def2 系按页内
  「连字符去除」形 def2svp 收录
- 缺陷：无（原型阶段缺陷均在落库前修正：短语锚点分支缺 `\s+`、def2 正则
  `pp?$` 笔误、弥散 + 位置误置于 g 后〔应为 6-31+g〕、反序锚点句首英文词
  误捕〔加技术词守卫〕）

- 批次 / 条目：A1–A24（C 批次，2026-10-14 浏览器视觉实测，playwright MCP；
  当前 mode=enforce——A7a 执行、A7b 不适用；A24 属 F2 #8 收口范围、
  已随 FG2 走查补录通过）
- 前置：WSL2 真机；后端 v3.1.0-19-g1be6c461（uv run python -m web.src.main，
  127.0.0.1:8300）；前端本地构建（npm run build 产物经 FastAPI 托管）；
  种子候选 16 个（scripts/seed_manual_workspace.py 灌入，组合流候选
  etoh.gjf=#133）；运行级 crest_root 全程 ~/opt/crest-3.0.2（A21 期间临时
  指向不存在路径以 503 零副作用抓载荷，走查后已恢复）
- 步骤与实测（逐条）：
  A1 通过——打开配置页自动选中方案 1，编辑区「配置1」+ 初始 route 小写
  （留痕 A1-modal-layout-v3.png）；A2 通过——顶部 5 矩形框显式数字 1–5、
  初始命名「配置n」（同上截图）；A3 通过——默认徽标全页仅方案 1 一处，
  改选方案 5 保存后唯一迁移（A3-default-migrated-scheme5.png），已改回
  方案 1；A4 通过——默认「设为默认」点击不可取消、仅可改选（5→1 迁回
  实测）；A5 通过——route 清空保存 GET 恢复初始 route（叠加 §0.4 口径 1
  温度补齐形态 `#p b3lyp/6-31g(d) opt freq temperature=298.15`，恢复语义
  成立）；name 清空保存恢复「配置5」；A6 通过——UI 走查非 # 开头分支
  422 route_must_start_with_hash 一条全报；多行/空行分支按条目备注经
  API 直调断言（test_combo_templates.py B 批次全绿，前端 @input 单行化
  致 UI 不可构造）；A7a 通过——词典外 token mycustomkeyword → 422
  keyword_not_in_dict 拦截 + 豁免按钮出现（A7a-keyword-blocked-exempt-
  button.png）→ 点「忽略拼写警告并保存」落库 + notice.spelling_warnings
  展示 → 关闭重开同 token 重新拦截（豁免清空）→ 同会话切方案 4 同
  token 直接放行（跨方案共享）；A7b 不适用（enforce 已上线，无降级）；
  A8 通过——freq 无温度保存补 temperature=298.15、notice temp_applied
  提示「已补齐」、回显归一化 route；已含 temperature=310 保存不重复补；
  A9 通过——temperature=abc / -1 / 300,310 三变体均 422 temp_value_invalid；
  A10 通过——mem=0.5/nproc=1 → mem_below_per_core_floor；nproc=8/cpu=1-4
  → nproc_cpu_mismatch；nproc=4/cpu=1-5 多于默许 200 放行（相等 4/1-4
  亦放行）；A11 通过——方案下拉选 2 回填三行 %nprocshared=4 / %mem=8GB /
  %cpu=1-5 与 GET 值一一对应、全小写、仅非空项（A11-A20-A21-comboflow-
  dialog.png）；A12 通过——未保存本地改动切方案/重开均回已保存值；A13
  通过——route 含 @task: → 422 link0_symbol_ref_forbidden（补注 2026-10-14
  独立审查 C-4：link0 半支如 cpu 含 @exec: 先被 cpu_list_invalid 拦——
  拒绝语义成立、reason 与断言字面漂移，系后端文法判定先于符号子串检测
  的既定顺序，登记不修）；A14 通过——
  %cpu 默认置灰（disabled），勾选「指定CPU核心」后可填；A15/A16/A17
  通过——nproc=0 / mem=abc / cpu=a-b 三错误一次全报（422 details 三条
  reason 全展示）+ 三编辑框红描边（A15-A16-A17-final.png）；A18 通过——
  豁免后再次保存不再拦截且落库；保存失败（nproc=0）重试豁免记忆不丢失，
  修复后重试成功落库；A19 通过——运行级参数区「组合流模板」入口按钮，
  点击弹出配置弹窗（A19-settings-entry.png）；A20 通过——ComboFlowDialog
  方案下拉含 5 条配置名、默认选中 is_default 条（打开即选「1 · 配置1
  （默认）」）；A21 通过——回填后手改 route 提交，抓包 POST 载荷
  template.route 为手改值、link0 三行为回填值、契约结构与既有
  POST /workflows/conformer-refinement 一致（503 零副作用）；A22 通过——
  混合大小写 route 保存后回显归一化小写 +「已归一化」提示（A22-
  normalized-notice.png）；A23 通过——link0 三字段清空保存 GET 返回
  NULL（curl 实测方案 3），ComboFlowDialog 选 NULL 方案回填无 link0 行
  （方案 1 实测）；A24 通过（F2 批次 2026-10-14 浏览器实测补录：
  #109 CVL_orig.gjf 双缺黄警「⚠ %nprocshared、%mem 未声明 · 执行时将按
  默认值补齐（%nprocshared=4、%mem=8GB）」、#133 etoh.gjf 单缺黄警
  「⚠ %mem 未声明 · 执行时将按默认值补齐（%mem=8GB）」，DOM 逐字提取
  与后端注入行形态一致、零大写残留，详痕见 FG2 条目）
- 留痕：截图 docs/plans/assets/m4-combo-deploy/（A19-settings-entry.png、
  A1-modal-layout-v3.png、A15-A16-A17-final.png、A7a-keyword-blocked-
  exempt-button.png、A22-normalized-notice.png、A3-default-migrated-
  scheme5.png、A11-A20-A21-comboflow-dialog.png；该目录已入 .gitignore，
  仅留路径）；载荷抓包 POST /api/v1/workflows/conformer-refinement
  request-body：`{"candidate_id":133,"crest":{"nproc":4,"top_n":2},
  "template":{"route":"#p b3lyp/6-31g(d) opt freq temperature=333",
  "link0":["%nprocshared=4","%mem=8GB","%cpu=1-5"]}}`
- 缺陷：2 项，均走查中当场修复、随本批次提交落库（未产生提交后 fix）：
  ① A4 首测「设为默认」可被取消——原生 checkbox DOM 取反与受控状态脱节，
  修复 toggleDefault 显式回写 checked；② 视觉——「指定CPU核心」标签溢出
  与 %mem 标签重叠、方案框配置名被默认徽标挤压截断，修复布局（方案框改
  数字+徽标/配置名两行结构、复选框移至 %nprocshared 输入框下方、标签
  精简）。修复后复测 A1–A24 相应条目全过，前端四闸门重跑全绿

- 批次 / 条目：D1（D 批次，2026-10-14 真机走查：503 → 部署 → 200 闭环）
- 前置：附录 B 环境检查全过——WSL2 就绪；上游 Releases 可达（GitHub API
  直连实测、资产下载经 gh-proxy 代理）；`--dest` 目标 `~/opt/g16web-
  walkthrough` 可写且不与既有 ~/opt 冲突；`target/release/hq` 在位
  （17,957,408 字节，10-12 构建）；g16 可执行在位（~/g16/g16）；
  种子候选 #133 etoh.gjf（组合流候选）；后端 v3.1.0-29 本地构建运行中
- 步骤：① 运行级 crest_root 指向空目录 `~/opt/g16web-walkthrough/
  crest-3.0.2`（模拟新机未部署）→ 候选页 etoh 行「组合流」一键提交 →
  ② `./scripts/deploy/setup_deps.sh --dest ~/opt/g16web-walkthrough
  --proxy` 真实下载部署 → ③ 重新一键提交 → ④ 终止走查 workflow
- 预期：① 503 `CREST_EXECUTABLE_MISSING`；③ HTTP 200 且响应含
  workflow_id；④ 走查 workflow 终止、无残留实跑
- 实测：**通过**。① UI 报「crest 可执行不可用 — 请检查运行级设置
  crest_root 后重试」（POST 返回 503，零副作用；截图 D1-predeploy-
  503.png）；③ POST /api/v1/workflows/conformer-refinement 返回 200，
  响应 `{"workflow_id":"KB7N32","state":"crest_running",
  "crest_task_id":141,"seat_id":38}`（截图 D1-postdeploy-200.png）；
  ④ 乙醇构象搜索 ~20s 自然完成（crest_task 141 succeeded，能量
  -11.394 hartree 入 energy_summary），workflow 推进 refining 后对精修
  执行主动终止：POST /executions/52/stop → 204（执行 52=精修成员 143
  转 failed；成员 142 在停止前已自然 succeeded），队列 R6JX3Q 收敛
  unsubmitted、workflow KB7N32 停留 refining 不再推进——精修实际运行
  不在 D 走查范围，终止处置达成；crest_root 已恢复 ~/opt/crest-3.0.2
- 留痕：截图 docs/plans/assets/m4-combo-deploy/D1-predeploy-503.png、
  D1-postdeploy-200.png；响应体与 stop 返回码摘录如上
- 缺陷：无（本条目范围）

- 批次 / 条目：D2（D 批次，脚本幂等重跑）
- 前置：同 D1
- 步骤：`setup_deps.sh --dest ~/opt/g16web-walkthrough --proxy` 连续执行
  ≥2 次；另测半成品残留路径（crest 冒烟失败态重跑）与 `--force` 重装
- 预期：已安装（`--version` 冒烟通过）重跑跳过下载；半成品清理后重装；
  `--force` 重装成功
- 实测：**通过**。重跑输出「已安装（冒烟通过），跳过」且无下载请求；
  首次部署曾因 crest 资产布局缺陷冒烟失败，重跑自动清理半成品后重装
  成功（清理路径真机复现）；`--xtb --force` 重装 crest+xtb 成功
- 留痕：命令输出摘录（「[setup] crest 3.0.2 已安装（冒烟通过），跳过：
  /home/keepoux/opt/g16web-walkthrough/crest-3.0.2/crest」）
- 缺陷：2 项，走查实测抓出、随 #12（提交 2129e931）落库修复：
  ① 上游 crest tar 顶层为 `crest/` 目录（非平铺——既有 ~/opt 平铺布局
  系人工整理产物），且顶层目录与内层二进制同名（crest/crest）致首版
  上移逻辑 mv 被目录自身挡路；修复为「整体改名 .crest-inner 后上移」
  布局归一，对齐运行级 crest_root 语义；② 上游 xtb tar 顶层为
  `xtb-dist/` 目录（非 xtb-6.7.1/），修复为解压临时区后内容落
  `<dest>/xtb-6.7.1/`。两缺陷均有沙箱测试锁定（假资产改按真实上游布局）

- 批次 / 条目：D3（D 批次，xtb 可选装与非运行必需说明）
- 前置：同 D1
- 步骤：`setup_deps.sh --xtb --dest ~/opt/g16web-walkthrough --proxy`；
  核对脚本帮助、deployment.md §6 与设置页指引中「crest 3.0.2 内嵌
  tblite、组合流运行无需 xtb」口径
- 预期：不带 `--xtb` 时零 xtb 下载；携带时装出 `xtb-6.7.1/bin/xtb`
  （官方 .sha256 对照通过）；三处口径一致
- 实测：**通过**。默认安装 curl 请求日志零 xtb URL（沙箱用例锁定）；
  真机 `--xtb` 安装成功（xtb-6.7.1/bin/xtb --version 输出版本横幅，
  「xtb 官方校验和通过」）；脚本输出、--help、deployment.md §6 均含
  「crest 3.0.2 已内嵌 tblite，组合流运行无需 xtb」口径
- 留痕：命令输出摘录（安装完成行 + 指引行）
- 缺陷：无

- 批次 / 条目：D4（D 批次，上游资产校验和与许可核验留痕）
- 前置：GitHub Release API 可达（直连实测）
- 步骤：API 实测两项目发布资产清单 → 真机下载对照 → 许可文件核对
- 预期：资产名/URL/校验和（或对照口径）与上游一致；许可无再分发限制
  冲突（R-12）
- 实测：**通过**。**crest**：Release API 实测 tag v3.0.2（2024-08-25
  发布），资产 `crest-gnu-12-ubuntu-latest.tar.xz` 官方字节数 8,764,012，
  部署下载实测一致（体积对照通过）；**上游未发布校验和文件**——按
  §3.5 定案口径记录发布 tag 与资产体积为对照源（本条目即该口径标注）；
  附注：本机既有 `~/opt/crest-3.0.2/crest`（sha256 25b2cb66…）与本次
  部署二进制（sha256 201db794…）不同，既有安装系非 gnu-12 资产原件
  （历史人工安装），不影响官方对照口径。**xtb**：tag v6.7.1
  （2024-07-23 发布），资产 `xtb-6.7.1-linux-x86_64.tar.xz` 官方字节数
  27,128,568，部署实测上游官方 `.sha256` 对照通过（sha256sum -c 输出
  「xtb 官方校验和通过」）。**许可**（R-12 核对）：crest gnu-12 资产内
  LICENSE=GPL-3.0、另附 LICENSE.LESSER（LGPL-3.0 文本）；xtb 发布资产
  内不含许可文件、上游 repo 声明 LGPL-3.0——两项目均为 FSF 开源许可，
  本项目采 download-at-install 口径（不随包再分发二进制、仅引导用户
  自行下载使用），不构成再分发，无附加义务冲突，R-12 不触发
- 留痕：API 响应摘录（/tmp/crest_release.json、/tmp/xtb_release.json
  抓取的 tag/date/assets 清单）、sha256sum 输出、LICENSE 头部
- 缺陷：无

- 批次 / 条目：D5（D 批次，部署包内含 deployment.md）
- 前置：#12/#13 提交落库后工作区干净（package_release.sh 要求）
- 步骤：`scripts/package_release.sh`（HEAD 验证包，不上传）→ 解包断言
- 预期：部署包含根脚本 `setup_deps.sh`（update.sh 对新增根脚本自动补装，
  旧部署升级即得）与单文件 `docs/references/deployment.md`（含「CREST/
  xtb 接入」节）
- 实测：**通过**。`tar -tzf target/deploy/gauforge-deploy-linux-x64.tar.gz`
  命中 `gauforge/setup_deps.sh` 与 `gauforge/docs/references/
  deployment.md`；验证包版本 v3.1.0-29-gb5dd42f5
- 留痕：tar -tzf 输出摘录
- 缺陷：无

- 批次 / 条目：FG1（F1 批次，2026-10-14，§1.1 后端逐条 git diff 核对）
- 前置：工作区干净（d3718360 开工登记后）；F1 与 B/C 并行线无涉
- 步骤：逐条修改后 `git diff` 核对；全库 grep `%[A-Z]` 复扫
  （web/src、crates/、docs/api/openapi.yaml）
- 预期：§1.1 后端条目全部清零（#1–#5 运行值 + #9 后端文案/注释；不含
  models.py:361/393/663/666 再生面——已随批次 A 落）；既有派发/续跑/
  物化链回归全绿
- 实测：**通过**。#1 workspace.py:111 → `%nprocshared=`、#2 :115 →
  `%mem=`、#3/#4 resume.py:146/148 → `%oldchk=@exec:`、#5
  materialize._rewrite_line 前缀 casefold（改写行归一 `%chk=`/`%oldchk=`，
  无引用行前缀原样——test_materialize `%Chk=own.chk` 断言锁定）；#9
  后端：config.py:99/103、candidates.py:233/236/239/285、resume.py:16/
  21/27、dispatcher.py:12、gateway.py:73、workspace.py:4/74/76、
  blocks.py:128-132、finalize.py:5/6/77、dependencies.py:3/6、
  reconcile.py:11 全部小写归一；**R-8 表外补录 5 处**（workspace.py:5/
  35/51/77、candidates.py:40）随修复同批落库（§1.1 表后补录注）。复扫：
  web/src 仅余 strftime `%Y%m%d` 与文法占位 `%Key=` 两非违反项、crates/
  与 openapi.yaml 零命中；`blocks.py:134`/`candidates.py:327` 的
  "NProcShared"/"Mem" 系 missing 指令名载荷值（#8 定案前端小写归一）、
  维持原样。测试刷新：test_dispatch_engine（注入行 4 断言）、test_resume
  （注入行 3 断言）、test_materialize（改写行 3 断言）随行小写化，输入侧
  大写夹具保留覆盖大小写不敏感解析；全量回归 736 passed，e2e 3 例真实
  运行（hq 产物 17,957,408 字节在位，§6 必检项满足）
- 留痕：git diff 摘录（feat(web) 提交 b953de99，14 文件 +60/-59）——
  workspace.py:111 `-f"%NProcShared={declared}"` →
  `+f"%nprocshared={declared}"`、:115 `%Mem=` → `%mem=`；resume.py:146/
  148 `%OldChk=@exec:` → `%oldchk=@exec:`；materialize.py:101
  `return head + sep + dep_name` → `return head.casefold() + sep +
  dep_name`
- 缺陷：无

- 批次 / 条目：FG2（F2 批次，2026-10-14，§1.1 前端逐条 git diff 核对 +
  A24 浏览器实测）
- 前置：F1+C+B 已收口（d9504f8f）；种子候选 #109 CVL_orig.gjf
  （missing=NProcShared+Mem）与 #133 etoh.gjf（missing=Mem，计划指定
  种子）；后端运行级默认 link0_default_nproc=4 / link0_default_mem_gb=8
- 步骤：#6/#7/#8 逐处修改后 git diff 核对；grep
  `%[A-Z][A-Za-z]*[=\s（(、]` 复扫 web/frontend/src；前端四闸门
  （npm run build、scripts/audit_frontend_offline.sh、
  scripts/check_tokens.py、scripts/check_contrast.py）；浏览器实测 A24
  （127.0.0.1:8300 构建产物经 FastAPI 托管，DOM 逐字提取黄警文案）
- 预期：§1.1 前端条目全部清零；黄警文案形态与后端注入行一致；四闸门过
- 实测：**通过**。#6 ComboFlowDialog.vue：DEFAULT_ROUTE → FALLBACK_ROUTE
  小写常量 + initialRoute ref（watch 中取 GET /combo-templates 响应
  initial.route，applyTemplate 回落分支与清空恢复共用——单值来源对齐
  COMBO_TEMPLATE_INITIAL_ROUTE）；#7 模板 placeholder `%nprocshared=4`；
  #8 CandidatesView.vue submitWarnText：head 项 `%${m.toLowerCase()}`
  归一、缺省补齐行 `%nprocshared=${nproc}`/`%mem=${mem}GB` 无空格；
  R-8 表外补录 8 处（QueueEditorModal.vue 7 处含生成行 :201
  `%OldChk=@task:` → `%oldchk=@task:`、BlockEditor.vue:476）随修复同批
  落库（§1.1 表后补录注）。复扫：web/frontend/src 零大写残留（missing
  载荷值 "NProcShared"/"Mem" 为后端契约、前端归一后展示，非残留）。
  四闸门：build 零错误（vue-tsc + vite 5.04s）、audit 零外链资源引用、
  tokens 92+31 逐变量一致、contrast 全组合 ≥4.5:1。A24 实测：#109 黄警
  「⚠ %nprocshared、%mem 未声明 · 执行时将按默认值补齐（%nprocshared=4、
  %mem=8GB）」、#133 黄警「⚠ %mem 未声明 · 执行时将按默认值补齐
  （%mem=8GB）」——逐字一致、零大写残留
- 留痕：git diff 摘录（feat(frontend) 提交 d5c6ef2a，4 文件 +26/-19）——
  ComboFlowDialog.vue:26 `const FALLBACK_ROUTE = "#p b3lyp/6-31g(d) opt
  freq"`、:45 `const initialRoute = ref(FALLBACK_ROUTE)`、:89
  `initialRoute.value = tplRes.data?.initial?.route ?? FALLBACK_ROUTE`、
  :61 `route.value = initialRoute.value`；CandidatesView.vue
  submitWarnText `parts.push(\`%nprocshared=${submitDefaults.value.nproc}\`)`
  / `parts.push(\`%mem=${submitDefaults.value.mem}GB\`)` /
  `submitMissing.value.map((m) => \`%${m.toLowerCase()}\`)`；
  QueueEditorModal.vue:201 `lines.push(\`%oldchk=@task:${prevId}\`)`；
  BlockEditor.vue:476 `%Chk=` → `%chk=`
- 缺陷：无

## 附录 C：评审清单（批次闸门判据，逐条勾选方可通过评审;已通过评审,文档定稿,进入待执行态）

| # | 维度 | 判据 |
| - | ---- | ---- |
| C1 | 依赖 | WBS 各批次依赖边、批次内子步骤顺序、外部依赖登记（§2）齐备且无环 |
| C2 | 依赖 | 批次闸门「评审通过」判定可复核（本清单逐条勾选留痕） |
| C3 | 风险 | §7 风险登记覆盖技术/资源/时间/外部依赖四类，逐条含触发条件与应对预案 |
| C4 | 风险 | R-1/R-2/R-3 对应降级与修订路径与 §8 开放事项口径一致 |
| C5 | 交付物 | 各批次产出物名称、路径、内容范围明确无歧义（含词表三 11 项 reason 全集） |
| C6 | 交付物 | 走查/核验留痕载体与格式已定（附录 B） |
| C7 | 验收 | 各批次验收标准可量化、可验证，无「符合要求/正常运行/语义正确」类模糊表述 |
| C8 | 验收 | 附录 A 断言清单与 §3.2 矩阵、§3.4 规格一一对应，无遗漏或漂移 |
| C9 | 一致性 | 文档内部交叉引用无断链；§1 现状核查与实测代码位置一致（含 §1.1 存量清单） |
| C10 | 合规 | 需求三全小写统一口径贯穿设计（§3.2 归一化行）、测试（§4）、提交（§5 词典扩充再生 / F1 后端收口 / F2 前端收口） |
| C11 | 验收 | 若按 §8.1 降级口径交付：B1/B2 留痕「待补」已标注、A7a 标注「不适用」、A8/A9/A10 已按定案回填（2026-10-13 核验完成，不再属暂定项）、enforce 切换已登记为 §5 #6 条件提交、「词典扩充 + enforce 切换」遗留项已登记于 progress.json \`next\_steps\`（§8.1 进度跟踪锚），其余判据按降级口径复核放行；**若后续执行 §5 #6 切换**：须同时满足 §5 #6 验收四项（B3 复核、A7a 补走查、enforce 切换回归用例全绿、契约闸门重跑）方可；非降级交付时本条前半不适用、C1–C10 全过方可 |

