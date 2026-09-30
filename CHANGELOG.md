<!-- 本文件由 scripts/gen_changelog_md.py 从 CHANGELOG.jsonl 生成，勿手工编辑；再生成：uv run python scripts/gen_changelog_md.py -->

# 变更日志

## Unreleased（未发布）

### 新增

- 【docs】新增 M3+M4 联合执行计划（m3-m4-plan.md）：结果分析（cclib 白名单解析/cubegen 轨道与静电势/cclib 入 venv 与 3Dmol 离线本地化）与工作流（chk 符号引用依赖链/断点续跑/CREST 组合流与能量表）两波 27 任务 WBS、依赖流程图、契约 diff 基线、测试矩阵、DoD 与风险预案
- 【docs】A1 Result 与分析/存储契约 diff 落库：Result 字段全集一次定死（blocks 以 ResultBlocks 独立组件避免生成撞名），新增 8 端点（分析概览/收敛/频率/轨道、cube 生成与文件流、workspace-out 只读分析、storage/usage），错误码全集 24→29，HistoryEntry.result_ref 口径改写（succeeded 且 analysis.json 落盘含 degraded 置位），SettingItem 登记 disk_usage_warn_gb（0=禁用、默认 50），mapping 增行历史详情分析区四 tab/归档分析区/.out 入口/占用面板（48 操作无孤儿），sse.md 补 M3 无新增事件断言，两侧契约生成物再生与 test_error_codes 闸门同步
- 【web】B1 cclib 引入与结果解析服务落库：requirements.txt 冻结 cclib==1.8.1 依赖链（仅 .venv、安装命令落档 development.md），parse/results.py 白名单解析→契约 JSON（异常/60s 超时/success 假三路 degraded 已得块保留、DV 垫片旧格式容错、numpy 原生化、opt_converged 三态），config.G16_SAMPLES_DIR 集中配置，金标准单测 17 例（新集 6 份逐属性+构造异常+超时注入），全量 pytest 498 通过

### 变更

- 【docs】roadmap 开放事项 5 裁决回填：自动定时清理不引入、替代为空间占用统计与阈值告警（仅警告不自动清理、手动清理沿用 M1 入口，随 M3 实施 M3.7），M3 段落与验收段补录
- 【docs】M3/M4 联合计划审查修订（用户裁决落实）：H2 新增 GET /workflows/{id} 跨容器聚合、H3 续跑改新建任务并以 @exec 符号引用与 resumed_from 建立关联、H4 新增 M3.7 存储统计告警设计，及走查路径清单 §7.3/§7.4、定稿提交表与总工量、result_ref 口径统一、依赖图表对齐、孤儿错误码场景落位等 25 项修复
- 【docs】roadmap 二轮审查回填：§8.8 事件数补注（M2 后 15 类、以 sse.md 为准）、§1 原则 2 补 crest 组合流最小提取豁免（cclib 不支持 crest 输出）、M3 工作区只读分析后缀扩为 .out/.log（g16 输出后缀两态）
- 【docs】M3/M4 联合计划二轮审查修订（修订说明二，15 项裁决落实）：重入语义定稿（含物化依赖执行禁用 HQ 内部重试、journal 重跑者对账取消后以新执行 id 重新物化派发）、A1 口径校正（8 端点/SettingItem/mapping 清单）、开工闸门 unreleased 措辞校正、B4 依赖改 A3+B2 与 B9 补 A5、workspace-out 轨道 tab 仅清单、依赖链验收扩三段 opt→freq→sp、决策点 11/12 补录、续跑探针超时 120s、storage entries 截断 50 条与千级目录 P95<2s 基准、跨文档引用显式化
- 【docs】M3/M4 联合计划三轮审查修订（修订说明三，17 项）：决策点 8 拆分关闭时点（候选清单端点有无随 A1 评审定稿、入口形态随 A3）、注入矩阵 route 判定规则定稿（含 Opt 即优化行、Opt+Freq 并存归优化，ineligible 统一四态并补图）、关键路径更正（M4 波实算最长链 A4→A5→B10→B11→C7→D3→D4、总≈19 人天，原声明漏 B9 对 A5 依赖）、组合流提交席位满员语义定稿（409 PENDING_CAPACITY_FULL 整体拒绝零副作用）、决策点 12 补三分支 contingency（HQ per-job 重试上限 a/b/c 落位，b 插 feat(hq) 批次+cargo test 闸门）、M4 schema 迁移落位（resumed_from 列与 workflow 表走 migrations 版本化）、workflow 发现路径补全（POST 响应形状+新增 GET /workflows 列表端点）、resumed_by 派生只读字段定稿（原历史条目零 schema 变更）、workspace-out 解析超时 60s 定稿、A4/B5 批次 roadmap 回填登记（M4 段物化措辞校正与 §7.2 部分关闭注记）、A1 mapping 增行补归档详情分析区、v2.1.0 附件上传悬留注记、offline 审计/RESUME_NOT_ELIGIBLE HTTP 语义/hq 在位三处口径统一、crest 能量单位列入 A5 核验
- 【docs】M3/M4 联合计划拆分为两份独立计划（m3-plan.md/m4-plan.md）：联合总工量 35 人天过大，按「两波执行、两次发布」既有结构一分为二（各 ≈17.5 人天），版本目标与波次闸门不变（M4 以 M3 收口 tag v2.2.0 为开工闸门）；章节编号重排自洽（M3 版 §2.5/§2.6=原 §2.8/§2.9，M4 版 §2.1-2.3/§3.2-3.4/§4.1-4.10=原 §2.5-2.7/§3.4-3.6/§4.14-4.23），提交表各自 15/13 项、决策点 5/7 条、风险 9/8 条拆分重编号，交叉引用经全文校验，M4 版 §0.4 前置重写为 M3 收口闸门、§0.5/§0.6 改 M4 视角（M1 遗产 protected chk/M3 产出 B1 解析），三轮修订说明以沿革注记形式保留回指（完整文本见 git 历史）；roadmap 两处引用同步改向，原 m3-m4-plan.md 删除
- 【docs】M3/M4 拆分后两计划经独立子代理二次审核并修复审核发现（9 项 P2 全部闭环，P1 零项）：两版结构完整、对照 git 历史原联合计划逐节零丢失、内部与外部引用自洽；m3-plan 修复 §2.5 外链审计 D3 残留改 D1 收口、§0.1 补空间占用治理句对齐 roadmap 现行 M3 段、§4 公共纪律 hq 口径去 M4 归因、WORKSPACE_PATH_OUTSIDE 指向 §2.3 路径守卫、§3.3 E422 节点与错误码表口径统一；m4-plan 修复决策点 7 三处拆分残留（风险 8/#4（B7）/17.5 人天）、§7.2 走查清单重排 1-9 并拆分粘连行、§4.1 步骤②赘字、§4.10 体例指针补 m3-plan 前缀、§5 真机依赖清单改 M4 口径（crest/真 g16/真机 hq）
- 【docs】A2/A3 设计定稿回填：A2 探针实证 4 份金标准 cclib 1.8.1 逐属性提取全绿，发现并定稿 G16 发行版 DV 样本版本识别缺口处置（运行时垫片，defaultdict 回落 unknown 带形状守卫，master 同缺口）、白名单实测形状（逐 SCF 迹线/mosyms 全缺→null/开壳层 αβ 双自旋/numpy 转原生）、method 摘要与 opt_converged 三态判定、fixtures 三份构造方案；A3 关闭决策点 1（ECharts 按需）/2（惰性重建）/3（cube 留存）/4（候选清单端点不纳入、.out 入口定稿）/5（阈值默认 50）；修复 §0.2 M3.7 表格列错位
- 【docs】OrbitalsResponse 契约补丁：加 spin 自旋组维度（alpha/beta、闭壳层 null，各组独立 1..n 编号；nmo 明确为 α 组轨道数即 cubegen MO=<n> 上界基）——B1 探针实证开壳层金标准 phenoxyls 双自旋后随契约 diff 补录，两侧契约生成物再生
- 【docs】M3 金标准集更换为 CVL 实测现代输出（用户裁决）：原 4 份 2007 年样例 cclib 1.8.1 解析全挂 KeyError 'DV'，CVL 探针实证 64 份 Gaussian 输出全部可解析（最大 12.5MB 耗时 2.0s）；新集 6 份落 ~/g16/tests/ 覆盖 opt+freq 旗舰/最小 freq/纯 opt/纯 sp/异常终止/强停各态（异常样例缺口由真机样本补齐），旧 4 份保留为 M1 进度解析回归样本，m3-plan §0.4/§0.6/§2.2 回填与口径统一
- 【docs】M3 金标准补样两份（本机 g16 实测生成入库 ~/g16/tests/）：h2o_optfreq_popreg（opt+freq+Pop=Reg 闭壳层，关闭 mosyms/aonames 缺口，兼作 D1 真机 freq 走查预演）与 oh_doublet_popreg（开壳层双重态 sp，homos α/β 双值与双自旋组实证）；金标准集共 8 份，m3-plan §2.2 补样记录与 §0.4 口径同步
- 【docs】M3 金标准剩余三缺口补齐（金标准集 10 份 .out + 16 份 .fchk）：线性水 freq 样本实证 -2045.3 cm⁻¹ 二重简并虚频（imaginary 路径关闭）；本机 formchk 产出现代闭壳层/开壳层小 fchk 各一（cubegen MO=1 与 Potential=SCF 冒烟通过，B4 测试资产）；c8b_qst2_error 实证 success=false 且零分析块的极端降级；澄清 Nosymm 抑制轨道对称性打印（mosyms 恒缺根因，symmetry 按 nullable 兼容）

## v2.1.0（2026-09-29T17:25+08:00 发布，minor）

### 新增

- 【docs】新增版本标识与更新功能需求文档（version-update-spec.md）：侧栏动态版本行、设置页顶部更新卡（手动检查/立即更新/下载进度/运行守卫）、每日每周每月凌晨1:00自动检查与异常如实反馈规格，含依赖核查、REST/SSE 契约草案、改动面清单与七项决策点
- 【docs】新增版本更新实施计划（docs/plans/version-update-impl-plan.md）：需求分析（五功能/边界/十项技术约束/八条验收判据）、任务拆解（A–G 七批次 17 提交，每任务含产出与完成判据）、依赖图与关键路径（A1→D1→D2→E1→G1）及 11 项风险登记、四层测试方案（单测 4 新 5 扩/进程内集成/闸门回归/手动冒烟 9 项/本地 release 模拟演练）、发布流程（含固定名附件自举边界说明）与分层回滚策略；实施侧定稿：G16WEB_UPDATE_BASE 演练通道、枚举校验失败归 type 不扩词表、openapi info.version 动态覆盖防再漂移、自动检查 30s 轮询式调度、.update-check 伴生文件跨重启恢复
- 【api】契约预告更新域四端点与五错误码（status/check/apply/proxy 与 UPDATE_* 全集 19→24，SettingItem.range 增枚举结构，info.version 同步 2.1.0），前后端契约生成物再生
- 【api】SSE 契约新增 update.progress 与 update.phase 两事件（事件全集 15 类；下载进度 ~500ms 合并窗口取最新、阶段翻转即推），推送时机表与事件命名域清单同步
- 【web】版本单一事实来源解析链落地 config（部署目录 VERSION → git describe → CHANGELOG 最新 released 兜底，bare_version 剥 v 单点、失败兜底不炸启动），并登记更新通道默认值与运行级 update_check_interval 四档参数
- 【web】health 与 openapi 元数据改用版本单一事实来源：main.py/system.py 版本硬编码退役，/openapi.json info.version 运行时动态覆盖防再漂移（ssot 测试改剔除字段严格比对+独立断言）
- 【web】支持运行级参数枚举值域校验：update_check_interval 四档周期可正常保存，非法值按类型错误随整批拒绝并回显枚举载体
- 【web】新增更新检查能力：语义化版本严格比较、远端 release 探测与连接超时/无法连接/远端异常的逐字反馈、代理通道与最近检查结果伴生文件落盘恢复
- 【web】新增更新执行流程：任务运行中/重复触发/源码形态三守卫与同步预检、带实时速度的流式下载进度、sha256 校验中止、中断重试与跨重启状态恢复、下载校验完成后自动接管重启
- 【web】新增更新域四端点：状态查询/手动检查/触发更新/代理通道设置，部署形态判定驱动前端置灰、非法代理地址拒绝，受理后经 SSE 推送进度与阶段
- 【web】新增自动检查更新：每日/每周/每月/从不四档凌晨 1:00 锚定调度、错过窗口启动后短时补查、只发现不安装、设置保存即时生效
- 【web】侧栏新增动态版本行与更新可用圆点：health 单一事实来源下发带 v 形态直接渲染、断线重连重拉校对，版本行可点击（热区含圆点）跳转设置页更新卡，发现新版本时点亮 accent 圆点
- 【web】设置页新增置顶更新卡：八态显示状态机随 SSE 相翻转、立即更新按任务运行中/源码形态/流程进行中置灰并附逐字文案、下载进度条（左版本号/右实时速度换档）、代理通道三选一切换即时生效与非法 URL 即时校验；设置页同步调整为启动级两项水平两列、运行级枚举参数四选下拉、1080p 一屏预算收敛实测零滚动
- 【web】前端更新事件消费与服务重启强刷：感知服务重启中后断线转健康检查轮询（500ms、上限 120s），恢复后按版本变化强制刷新、更新失败如实展示原因、重启超时如实提示手动处置；多标签页各自轮询自然跟随
- 【api】契约增 UI 偏好域 /ui-preferences 两端点与 QueueSortKey/UiPreferences/UiPreferencesUpdate schema（GET 读全量、PUT 合并 upsert 整批校验、不发 SSE 事件），代理通道三处口径改工作区 .update-proxy，contract.ts 与 models.py 生成物再生
- 【web】UI 偏好域落地：迁移 v2 增 ui_prefs 键值表（工作区 SQLite 持久化、跨重启/更新不回默认）、UiPrefsRepo 与 store 访问器、GET/PUT /ui-preferences 路由（键白名单与值域 all-or-nothing 校验、未知键/越域值 400 INVALID_REQUEST）、config.UI_PREF_KEYS 单一来源
- 【web】前端列表排序规则持久化：新增 useSortPref 组合式（挂载拉取回填、变更即时单键写回、失败静默降级下次重拉校对、回填期间屏蔽写回），队列页 queues.sort 与历史/归档页 history.sort/archive.sort 分立接入，同组件跨路由复用实例时键切换重拉
- 【web】增量解析新增 SCF 轮次计数 scf_round（Cycle 1 行出现即新一轮、自 1 递增，截断重扫随进度状态重建），execution.progress 载荷与快照 progress 增 scf_round 字段（sse.md/openapi.yaml/models 契约同步，contract.ts 再生）
- 【frontend】SSE 客户端无帧看门狗：连续 60s（4×默认心跳 15s）无任何帧主动断开走退避重连并以快照重建基线，消除半开连接等场景「连接看似在线、读数实已冻结」的无提示失联
- 【api】契约增历史批量导出端点 POST /history/export（ids 集合请求体 → application/zip 打包下载，新增 HistoryExportRequest schema，400/404 错误响应），mapping.md 登记多选表格套件与导出映射、端点对照 39→40（history 8→9），前后端契约生成物再生
- 【web】历史批量导出端点落地：run/<id>/input.log 打包 ZIP，条目内 <stem>.out 正规扩展命名、同任务多次执行同名冲突组全部加三位补零执行 id 前缀、无输出条目跳过并在包内 _导出说明.txt 逐条登记、选中条目全部无输出 404、ids 非空正整数数组校验 400
- 【frontend】历史页表格接入候选页同款通用多选套件（复选框列、useMultiSelect 锚点驱动 Shift 范围/Ctrl+Shift 追加、Ctrl/Cmd 单选、Ctrl+A/Esc/方向键导航与滚动定位、勾选跨页保留）与工具条勾选批量导出 .out（POST export 经 blob 下载 zip、跨页勾选整体参与、修饰点击不开详情抽屉），抽屉单条导出按钮同步改名「导出 .out」

### 变更

- 【docs】版本更新需求文档评审修订（18 项口径对齐）：代理通道定稿上设置页（D4，更新卡内切换、读写 .update-proxy 不进 SQLite）、检查周期四档含从不（never）、update.phase 枚举增 available 并与显示状态机逐行对齐、新增部署目录 update-state 落盘标记写入/恢复/清理规则、self_update.sh 重启编排定稿（后端自退、脚本等待端口释放不杀进程）、登记第四处版本硬编码（openapi.yaml info.version）、package_release.sh 入包清单需追加 self_update.sh、SSE 断开时点/版本号形态/文案全角标点/错误码 19→24 等表述统一
- 【docs】版本更新需求文档补口径：版本行本身可点击、点击（热区含小圆点）跳转至设置页更新卡，hover 微反馈不占导航项形态，联动 §3.1/§6.2/§7.1
- 【docs】版本更新实施计划与需求文档按全面审查报告逐项修正：闸门级两项（test_error_codes 错误码全集 19→24 同步、openapi ssot 豁免改「剔除 info.version 严格比对+独立断言」防 pytest 必红）、契约补全（status 字段全集增 supported/proxy、SettingItem.range 增 enum 结构、apply 同步预检 502 回登需求）、验收补全（.update-check 伴生文件与「服务重启超时」文案回登需求、F2 按钮可用性矩阵、F3 强刷三分支与圆点全相映射、mapping 端点对照 33→37）、实现细化（下载重试策略与 httpx read 30s、update-state JSON 仅改 phase、self_update env 继承与端口判据、默认代理落盘无尾换行、1080p 预算含新增参数行）、偏差登记与一致性（30s 生效口径/根脚本自更新行为差异/版本来源措辞/测试先行差异登记、提交数 13→17、R5 下拉四选、需求 §3.7 引用与 §6.4 补登）
- 【docs】更新功能文档链补齐：mapping 增更新卡四行与侧栏版本行映射（端点对照 33→37）、roadmap 登记update_check_interval 与 G16WEB_UPDATE_BASE 及功能更新定位、deployment 升级章节改 WebUI 主/CLI 兜底并补伴生文件排障
- 【build】install.sh 安装链路镜像化：uv 自动安装器与托管 Python 解释器下载源改经 v4.gh-proxy.org 代理（GitHub 直连不再依赖），代理前缀可用 GAUFORGE_GH_PROXY 覆盖；两链路经本地实测验证
- 【docs】视图偏好域与代理通道工作区口径文档同步：mapping 端点对照 37→39（队列/历史/归档排序挂 ui-preferences）、version-update-spec 六处 .update-proxy 改工作区、deployment 升级章节注明部署目录旧位置自动搬迁、roadmap §2.5 增视图偏好条目
- 【web】更新代理配置迁工作区：proxy_path 改 G16WEB_HOME/.update-proxy（更新/重装部署目录不丢）、启动时一次性搬迁部署目录旧位置遗留（幂等、工作区已有则以工作区为准）、write_proxy 补目录创建；迁移三分支测试与既有 proxy 用例随改
- 【build】update.sh 代理配置改读工作区 ${G16WEB_HOME:-$HOME/g16web}/.update-proxy 与 WebUI 更新卡共用同一份（落盘前 mkdir -p，默认值与后端一致），覆盖范围注释同步
- 【frontend】执行中页 REST 基线轮询 8s→3s 并对账撤卡：REST 运行列表之外的卡与停滞告警一律移除（仅成功响应时执行，服务不可达窗口保持现状），SSE 事件丢失场景幽灵卡 ≤3s 自愈
- 【docs】设计令牌 --drawer-width 380px→520px 规格登记与样板同步（m0-frontend-design §2.3、m0-ui-preview.html）：历史详情抽屉单行键值行须同行容纳「提交/启动/结束」三时间戳，与候选页预览列 --preview-width 语义分立

### 修复

- 【web】修复 SSE fanout 重放窗口修剪后实时广播永久停摆：增量基准由「绝对已广播条数」（对固定 1024 容量列表 len 比较永假）改为事件 id——此前服务启动累计事件超 1024 条即全量静默丢失（心跳照常、连接看似正常），执行页幽灵卡与监控读数冻结的根因
- 【frontend】执行中页读数修复：execution.progress 可选字段判空渲染（scan 类任务无优化步时 OPT STEP 不再显示 NaN）、SCF 读数改「轮次-圈数」x-y 展示（标签 SCF RUN-CYCLE，旧载荷缺 scf_round 退单圈数值）
- 【frontend】历史详情抽屉紧凑化与预览可见性：全字段改单行键值行（dt 左/值右对齐，「提交/启动/结束」三时间戳以「/」分隔同行、资源 CPU/MEM 与监控峰值各并一行），抽屉 380→520px，打开输入/输出预览后自动滚入视野；最小支持视口 1280×720 下含全尺寸预览零滚动（此前字段双行堆叠，无预览即超高约 100px、预览区被裁切在视口外）
- 【web】历史单条输出导出附件名 .log 改 .out（G16 输出正规扩展；内容不变仍为 run/<id>/input.log）
- 【web】修复多结构任务提交核验压平结构交界双空行：QST2/QST3 输入经提交核验后，第二套结构电荷行前的双空行被规约为单空行，派发副本在部分发行版 G16 上被误并为单行读取而报 End of file in ZSymb；verify_and_normalize 登记多结构例外（下一附加节首行为电荷/多重度整数对时交界规约为恰双空行，其余交界仍恰一空行），同步 roadmap §2.7 规约条款并补 6 项核验测试（正反例/幂等/QST3 双交界/非多结构回归/Variables 共存/提交路径）

## v2.0.0（2026-09-28T02:06+08:00 发布，major）

### 变更

- 【repo】自有代码许可由 MIT 更换为 PolyForm Noncommercial 1.0.0（分层许可：内核 crates/ 完整保留上游 HyperQueue 的 MIT；README 新增 AI 使用声明） **（破坏性变更）**
  - 迁移指引：v1.0.0 及之前的发布按 MIT 存续；自 v2.0.0 起除 crates/ 内核（MIT）外的自有代码仅限非商业使用，商业使用需另行获得授权

## v1.0.0（2026-09-28T01:03+08:00 发布，major）

### 新增

- 【api】契约增补导入成队参数与提交响应规范化标记（queue_from_folder/folder_name、CandidateCreate.queue、SubmitResponse.normalized），mapping/sse 时机表同步
- 【api】错误码全集 19 码与两张 reason 词表落位 openapi.yaml 文件头作为 SSOT 载体（含 M1 私有码补录与实现码语义标注），ErrorBody.code 描述改指该清单
- 【core】新增关键词字典生成链（extract_keywords.py 读 gaussian-kb 结构化知识库产出 97 词条入库、parse.keywords 加载器缺失降级零警告），支撑 route 关键词拼写检查
- 【core】分块编辑保存真实化：parse/blocks 节定位与区间替换重组器（编辑不转换行尾、目标节末恰一空行规约）、services save_block 全流水（形态守卫七路径/逐节校验 422/round-trip 自证 500 拒绝落盘/原子写/全局写锁）、PUT blocks 端点消解占位节名、route 拼写检查（近邻命中才警告）
- 【core】提交前输入核验真实化：CRLF→LF 与空行规约器、三提交路径（行内/队列逐成员/历史重新排队）建席前统一核验，解析失败与多步拒绝 422 且不落盘、规范化原子写回并自证结构不变、响应携带 normalized 标记
- 【core】队列编辑全语义：PATCH 状态分级矩阵（unsubmitted 全量/submitted 仅成员/executing、completed 409）、member_ids 子集去重下限校验与移除分流四类（退回/脱离/failed、skipped 新候选同源复制）、回退编辑移除全部 failed/skipped 自动成功终结、在跑成员移除拒绝
- 【core】队列删除增强与 id 查重：DELETE 分级处置（submitted 席位撤销+退回、completed 成员只留历史、executing 409），队列 id 生成对照全库（含任务/执行记录历史引用）查重永不复用
- 【core】导入成队：POST /candidates 增 queue_from_folder/folder_name 参数与响应 queue/queue_fallback_reason 字段，受支持文件数 2–10 成队、越界回落全部候选并明示原因，成队事件序 created ×N → moved_out ×N → queues.changed(created)，前端契约生成物再生
- 【core】契约回归更新与整队生命周期 e2e：fake g16 全链路（创建/提交核验/中段失败分流/补位/回退归因/哈希跳过/重跑/自动成功）与 PUT blocks、PATCH member_ids、提交响应 normalized 的 openapi-core 零漂移校验
- 【web】预览编辑态真实化：BlockEditor 分块编辑器（link0/route/title/charge_mult/additional 双态、自动保存失焦或 800ms 防抖、422 错误描边注记不落盘、拼写警告琥珀注记、CRLF 中性注记、molecule 恒只读），行内提交与历史重新排队按响应 normalized 字段展示规范化注记
- 【web】候选页多选与队列组建：复选框列（全选/清空、已选计数）、「+ 队列」按钮（2–10 前置校验）、队列编辑对话框三模式组件（名称/成员移除与拖动排序/跳过开关、保存 primary + 直接提交 secondary 链式失败保留 unsubmitted、normalized 中性注记）与 useDragSort 公共拖拽组合式（待执行页同步切换）
- 【web】队列页真实化：手势分工（单击行首箭头展开/双击行开编辑对话框）、状态分级对话框接入（unsubmitted 全量、submitted 仅成员、executing/completed 只读附待执行页引导）、重新提交（normalized 注记/满员 409）、删除二次确认（状态分级文案、executing 不渲染）、失败成员归因列表与回退队列 failed/skipped 成员的 BlockEditor 分块编辑入口
- 【web】导入队列选项：文件夹导入「保存为队列」勾选与队列名预填（顶层目录名缺省可改），上送 queue_from_folder/folder_name，成队注记与越界回落 queue_fallback_reason 中性提示
- 【docs】M2 验收记录落盘：D1 九条路径走查留痕（fake g16 全链路 + Playwright 黑盒）、五笔运行时缺陷修复登记、设计一致性与系统级判据核对、M2.1–M2.7 不偏离核对
- 【web】标准表格底部套件 TablePager 落地候选/队列/历史三页：「共 n 项」计数右对齐统一口径（删除「n 项 — 共 n」双口径与历史页顶部重复计数）、分页控件绝对居中（首页/上一页/下一页/尾页线性 SVG 图标按钮）、页码输入框自然数过滤回车跳转 0 落首页超上限落尾页、总数小于分页大小时控件整体隐藏不占位；候选/历史接入真实页码取数修复超过分页大小直接截断且无分页样式的缺陷（筛选/排序回第 1 页、页码越界钳末页重取），队列前端切片分页，设置项 page_size 三页全局统一并随 settings.updated 即时跟随
- 【web】队列页顶部控制行（与历史页同款）：状态筛选（全部/未提交/已提交/执行中/已完成中文措辞）与排序（默认=回退置顶·创建时间新→旧；名称 A→Z/Z→A 走 zh localeCompare），/queues 全量返回前端过滤切片，筛选/排序变更回第 1 页并区分筛选空态文案
- 【web】候选页行点击接入 Shift 范围勾选（参照资源管理器范式补齐点行入口）：Shift+行点击从锚点行到目标行范围勾选（普通 Shift 替换式、Ctrl+Shift 追加式，锚点不动可反复调整）、预览选中目标行；普通行点击保持预览选中并同步锚点/焦点衔接键盘扩展，Shift 按下 mousedown 防文本选区
- 【web】候选页行点击修饰交互补全（修饰交互全在行上）：Ctrl/Cmd+行点击切换单项勾选并重置锚点（示例范式：Ctrl 点击重置锚点），与 Shift+行点击范围选择、Ctrl+Shift 追加范围、方向键导航构成完整行内多选；行点击入口不再依赖复选框

### 变更

- 【docs】设计文档增补表单控件与编辑态规格定稿（select/checkbox/toggle/编辑态描边裁决/自动保存触发/队列对话框布局/拖拽动效/手势分工），M2 移项销号
- 【docs】M2 计划登记修订说明五（B1 字典抽取源改用 gaussian-kb MCP 结构化知识库）并回填 A1 实地核查结论（94 页甄别剔除 8 篇文章页、词条=slug+标题变体、决策点 4/5 关闭）
- 【core】错误码治理落位：席位私有码替换为全集码（QUEUE_MEMBER_FLOOR/TASK_EXECUTED_IMMUTABLE）、导入 reason 对齐 INPUT_PARSE_FAILED、设置域 409 SETTING_READONLY / 422 SETTING_VALUE_INVALID 与 reason 词表对齐；test_error_codes 静态闸门（实现 ⊆ 契约 19 码、退役码零残留）
- 【docs】M2 计划登记修订说明六（B 阶段收尾）：决策点 7 关闭（%Mem 手册核查结论）、实施中修正的两处 M1 引擎缺陷与回退事件对齐登记
- 【api】契约登记 GET preview/input 跨形态守卫口径：id 跨形态延续（候选与失败回退队列成员可读，守卫与 PUT blocks 一致，其余形态 404），mapping 增补编辑初始化与 CRLF 检出映射行
- 【docs】roadmap M2 编辑条目字典抽取源随修订说明五回填（D1 一致性对照核验发现旧离线 HTML 路径残留，先改文档）
- 【docs】roadmap M2、m2-plan M2.2/§4.3、m0-frontend-design §4.6 回填创建态队列对话框不渲染队列 id 字段的表述（随创建态占位注记移除的人为修正同步文档）
- 【docs】m0-frontend-design §5 候选页布局行与 m2-plan C2 段增补「+ 队列」按钮右缘对齐左列列表、不落预览区右肩的布局规格（补设计文档未述锚点，计划外人为修正指定）
- 【web】前端硬编码度量与动效时长收口为设计令牌：新增复用度量 9 个、时长档 8 个、字距复位档 1 个（tokens.css 与样板 HTML 同步，check_tokens 89/89），12 文件约 50 处字面量改引令牌，BlockEditor 防抖升命名常量；值恒等替换视觉零回归
- 【docs】设计文档混排纪律 1 登记「保存为队列」12px 从属档例外（随工具条主从分级的人为修正同步）
- 【docs】设计文档回填视口固定布局纪律（100vh 锁定、body 无全局滚动条、侧栏 HQ 状态常驻、列表容器局部滚动、退场视图绝对定位离场）与标准表格底部套件规格（共 n 项右对齐、分页控件居中与显隐规则、SVG 图标、输入框交互与边界钳制），roadmap §2.5 分页大小标注三页全局统一（人为验收修正指定，修复前先行回填）
- 【web】候选页组建队列保存后留在候选页（原跳转队列页），对话框关闭、勾选清空、列表经 SSE 自动刷新（2026-09-27 验收修正）
- 【core】候选列表默认排序改为回退候选置顶+创建时间倒序（同秒批内 id 逆序，后导入在前），批内文件名自然序退役；契约 /candidates 描述与两侧生成物再生，排序测试改反例构造（导入序与时间序相反锁定排序键，并经纯 id 序退化验证失败）
- 【docs】roadmap M1 候选序表述与 M2 队列页段、m0-frontend-design §4.1 历史页措辞与 §5 候选/队列页布局行、m2-plan §4.3 C2 保存后行为，同步回填上述规格（2026-09-27 验收修正）
- 【web】候选页多选视觉补全：勾选行统一呈 accent 选中背景态（row--checked，与预览选中同源 7% 背景、hover 保持不回落灰调）——Shift 范围勾选后范围内每一行都有选中态颜色变化，不再只有鼠标点到的预览行变色；预览行左条/焦点行描边叠加以区分，明暗双主题经令牌自动适配
- 【web】品牌更名「Gaussian 16 管理工作台」：侧边栏品牌区改两行排布（首行 Gaussian 16、次行 管理工作台，电源指示灯改对齐首行），浏览器标签页标题同步同名
- 【repo】项目自立更名 GauForge：git 历史与上游 HyperQueue 切割（vendor 根提交 + 自有提交重放）、许可双轨拆分（根 LICENSE 本项目 / crates/LICENSE 上游）、tag 改裸 v 前缀，并以 1.0.0 声明首个稳定版 **（破坏性变更）**
  - 迁移指引：现有克隆需改用新仓库地址重新克隆或重设 remote；获取本项目版本改用裸 v 前缀标签（如 v1.0.0）；上游完整历史与旧 g16- 前缀 tag 见备份 bundle（~/gauforge-history-backup-20260928.bundle）

### 修复

- 【core】预览与原文端点对失败回退队列成员放行（读取守卫与 PUT blocks 一致，其余形态 404），补路由级断言回退成员 200、非回退成员 404
- 【web】队列对话框 MemberRow 类型导出移出 script setup（setup 内 export 引发模块初始化 ReferenceError，对话框 chunk 加载即崩溃、候选页组件树中断；浏览器实测复验通过）
- 【web】预览编辑器 taskId 的 immediate watch 移至编辑态声明之后（原声明序在 loadPreview→exitEditLocal 同步回调中触达未初始化 ref 抛 TDZ，预览卡恒卡「读取预览」；浏览器实测复验通过）
- 【core】候选原文端点保留 CRLF 行尾（_load_input 改字节读入，read_text 通用换行静默吞 \r 致前端 CRLF 检出注记永不触发，D1 走查实测暴露）并补路由级回归断言
- 【web】toast 自动消失按本条 id 而非最新序号（多条交叠时早期 toast 永不消失并遮挡工具条，D1 走查 GUI 实测暴露）
- 【web】队列编辑对话框保存校验按模式区分成员数下限（编辑态误用创建期 2–10 校验致剩 1 成员的合法编辑被禁存，D1 走查 GUI 实测暴露）
- 【web】候选页「+ 队列」按钮右缘与左列列表对齐（原被工具条 spacer 推至整页最右、落在预览区右肩，视觉归属错误；计划外人为修正）
- 【web】创建态队列编辑对话框移除「队列 ID/保存后生成」按钮样式占位注记（纯装饰不可点击、属实现注释不应上 UI；编辑/只读态真实 id 展示与后端生成逻辑不变；计划外人为修正）
- 【web】候选页双栏塌单列回归修复：令牌化重构删除页内变量 --preview-col 后 .duo 的 grid-template-columns 引用漏改，声明无效回退 none 致预览区落到表格下方；改引 --preview-width 并补全量悬空变量审计（83 引用全部有定义）
- 【web】候选页工具条导入组主从分级：「保存为队列」与两导入按钮间加竖分割线（组间距 12→25px）、复选框贴近宿主按钮（8px）并降字号至 12px 下限档，体现其对「导入文件夹」的从属（计划外人为修正）
- 【web】管理面板锁定视口高度与列表局部滚动：app-frame 100vh + overflow hidden + 网格行高 minmax(0,1fr)，长列表不再撑破面板、body 不再出现全局滚动条，侧栏 HQ 状态行常驻窗口底部；候选/队列/历史三页列表容器化（滚动包裹层吃剩余高度、粘性表头贴滚动容器顶、候选预览卡改随行高拉伸自管滚动），视图切换退场视图绝对定位离场防双视图挤压
- 【web】候选页粘性表头透明穿透修复：表格边框模型 collapse 改 separate（spacing 0）并给表头建自身层叠上下文，列表局部滚动后行内容不再画在表头背景上，明暗两主题实测穿透消失；发丝线全在单元格 border-bottom 上视觉不变
- 【web】队列页提交动作文案按回退标记分级：携带回退标记/回退次数的未提交队列（失败回退）显「重新提交」，新鲜未提交队列显「提交」，修复新鲜队列被误标重新提交的问题；整席移除回退按后端设计无回退标记视同新鲜，设计文档 §5 队列页规格同步回填
- 【web】队列编辑对话框拖拽排序动效重做：HTML5 DnD 改指针跟手画布式（usePointerSort 组合式），拿起项 transform 跟手、其余项迟滞换位让位/归位（--dur-drag 200ms 新令牌，行高/行距量测自 DOM 与令牌不硬编码），松手先滑入目标槽位、归位动画结束后才提交重排全程无跳变，成员超出限高触边自动滚屏，行内移除按钮不再被拖拽劫持；待执行页保留 HTML5 DnD，设计文档 §2.4/§4.6/§6 规格同步回填
- 【web】视觉修复三处：侧栏导航项中英上下分行、中文名 14px 升 18px 并扩命中区至 48px（新增 --nav-item-height 令牌）；展开/收起三角放大至 18px 并以弹性居中修正旋转基准，原地旋转不再绕点公转（队列页与待执行页同款）；队列页状态列/成员状态徽标/结束原因列改中文显示（queueStateLabel/taskStateLabel/finishReasonLabel 单一来源），原英文枚举保留为内部信号（chip 类名与 data-finish-reason 属性）
- 【web】修复分子说明以原子序数书写时化学式空缺（序数映射元素符号计入 Hill 式），预览卡 FORMULA 空值改显 — 占位防标签上浮错位
- 【web】候选页多选交互套件化：新增 useMultiSelect 公共组合式（锚点+焦点双状态驱动），复选框接 Shift 范围选择（Ctrl+Shift 追加、锚点不随 Shift 改动可反复调整）、上下方向键导航联动勾选与滚动定位、Ctrl+A 全选与 Esc 清空、翻页重置页内索引（勾选跨页保留），行点击预览与勾选锚点衔接；焦点行发丝描边与 Shift 按下防文本选区
- 【web】历史页状态列/详情抽屉状态徽标/状态筛选下拉改中文显示（taskStateLabel 单一来源，与队列页同纪律；筛选下拉文案 全部/成功/失败/跳过），原英文枚举保留为内部信号
- 【web】候选页多选交互修复：复选框点击不再 preventDefault——Chromium 的 checkbox 取消激活回滚发生在 Vue 渲染写入之后、覆盖 :checked 同步（实测计数已更新而复选框不亮、Shift 锚点范围选择视觉不生效），改为放行原生翻转并按 checkedIds 语义同步修正被点击项 DOM（该行 vnode 值未变时 Vue 跳过写 DOM 需自补）；Playwright 隔离实例实测锚点范围选择/范围调整/Ctrl+Shift 追加/Ctrl 切换/方向键导航/Shift+方向键扩展/Esc 清空全路径通过

## v0.1.0（2026-09-26T17:35+0800 发布，minor）

### 新增

- 【web】新增 G16 Web 后端骨架（config 两级参数/应用工厂/统一错误结构），可启动服务
- 【web】按 REST 契约补齐 mock 端点全表（system/settings/candidates/queues/pending/executions/history）
- 【web】新增 SSE broker 与 mock 推流（快照恢复/Last-Event-ID 重放/心跳）
- 【web】新增前端空壳工程（Vite+Vue3+TS、明暗双主题 tokens、六页视图与组件）
- 【web】新增 SSE 消费骨架与设置面板（流式解析/退避重连/Last-Event-ID/快照重建/设置读写）
- 【core】新增 SQLite 存储层（连接治理/顺序迁移/五域 DAL）与设置持久化，mock 内存设置退役
- 【core】新增输入分块解析器（§2.7 五段切块/Hill 记法/多步与坏文件容错）与文件名自然序（字母先于数字）
- 【core】新增 HQ Gateway 抽象与 CLI 实现（--output-mode json 子进程封装、轮询差分事件）及 HQ 进程管理（journal 落位/复用/看门狗重启/脱离父进程组）
- 【core】新增候选领域服务（导入逐文件校验与整批原子/inputs/<id> 副本与剔除/title 实时解析/重复导入 duplicate 提示）
- 【core】新增待执行席位领域服务（尾部追加/全量原子重排/整席移除退候选与队列回退/成员移除规则/容量满员与上限挤出/窗口锁定语义）
- 【api】候选/待执行端点真实化（multipart 导入/列表 title 注入/预览/剔除/行内提交/席位重排与移除/上限调小挤出），引入 python-multipart
- 【core】新增派发引擎（执行序列展开/并行窗口推进/哈希跳过/Link0 补齐与 GB→MiB 换算/声明资源停等不越位/run/<id>/ 物化与 g16 环境构建/终态映射与队列失败分流）及 FakeGateway、fake g16 夹具
- 【core】新增执行监控（psutil 进程树采样：cwd+启动时间双重校验定位、CPU 差值/RSS 汇总、2s 节流与峰值累计）、停滞状态机（翻转才推/冷启动宽限/时长累计，仅提示不终止）与手动停止真实化（stop→cancel→归因 manually_stopped）
- 【core】新增运行中增量解析（tail run/<id>/input.log 位点续传、优化步/SCF 迭代窄域识别、1s 合并窗口、execution.progress 事件与停滞基准喂入），fake g16 输出对齐金标准行式
- 【core】新增终态文件管线与历史端点真实化（formchk 转 fchk 失败不阻断、failed 保全快照入 protected/ 落库 chk_snapshot、手动清理仅删 succeeded 超期顶层 chk/rwf、历史列表/详情/输入输出/归档/重新排队/退回候选/清理统计）
- 【core】新增重启对账与引擎启动序列（§2.4 五场景：S1 接管与 started_at 回填、S2 终态幂等冻结、S3 重跑特征探测与 chk 保全重定向、S4 server 丢失外部中断、S5 重试不中途落历史；对账后发 system.snapshot；lifespan 挂载 HQ 进程管理与引擎线程，新增 G16WEB_ENGINE/G16WEB_HQ_BIN 启动级参数）
- 【core】SSE 事件总线真实化（事件唯一来源切领域事件总线、mock 推流剧本退役、序号 sse_seq 每事件短事务落库重启延续、fanout 按广播条数差量、system.snapshot 统一真实 store 载荷）
- 【rust】新增 HQ server 内嵌 axum HTTP 骨架（--http-port 默认关、GET /info，桥接任务复用 server 处理逻辑）
- 【rust】新增 HQ REST 端点集（jobs 提交/详情/批量/取消与 workers，复用 CLI 内部实现保证双路一致）
- 【rust】新增 GET /events SSE 事件桥接（四域事件单行 JSON 帧+15s 心跳，薄桥接不重放）
- 【core】新增 HttpGateway（HQ HTTP/SSE 桥接消费、断线重连）与 Gateway 工厂按可用性切换（G16WEB_HQ_HTTP_PORT，默认关）
- 【web】候选页真实化（文件/文件夹 multipart 导入与逐文件失败清单、自然序展示、来源徽标与归因注记、剔除二次确认；新增共享确认模态与前端自然序工具）
- 【web】只读预览真实化（分块卡按样板重排、Link0 缺失琥珀注记、parse_errors 逐条容错条、分子四格读数）
- 【web】行内提交流真实化（确认框完整输入限高滚动、Link0 缺失黄警含设置缺省值、满员 409 提示）
- 【web】待执行页真实化（拖拽重排/整席与成员移除二次确认/容量仪表超限示警/窗口边界与在途锁定态，pending.snapshot 驱动）
- 【web】执行中页真实化（通道卡 1Hz 节流读数、停滞琥珀灯行翻转与时长、停止 danger 二次确认）
- 【web】历史页真实化（输入/输出查看导出、重新排队与退回候选、独立归档页路由、清理统计回显、history.appended 驱动重拉）
- 【web】设置面板真实化（中性生效语义徽标、实际变更 on_restart 重启提示、席位上限调小挤出确认、范围提示）
- 【api】queues 端点真实化（队列创建/编辑/删除/提交切真实 queues/tasks/seats 存储与事件，整队占席走引擎派发路径，修复 mock 残留致 §7.1 第 10 条无法在真实栈成立）
- 【core】新增 HQ 连通性监控（引擎 tick 以 workers 列表探测 server 可达性，状态/在线数翻转才推 hq.status；system.snapshot 增 hq 字段供快照重建侧栏基线）
- 【web】侧栏 HQ 连接状态行真实化（hq.status 与快照 hq 字段驱动的三态 LED 与文案：已连接/未连接/未启用，替换 M0 静态占位）
- 【core】历史列表支持多排序（sort 参数：提交倒序默认/完成时间升降/文件名自然序升降），历史页工具条新增排序切换；取数端全量稳定排序后切片，跨页全局有序
- 【web】待执行页队列成员子表补全属性（队列内序号/任务 id/文件名/标题/资源声明含缺省补齐标记），契约 PendingSeat 及成员项同步扩字段（resources 提取为命名模式复用）
- 【docs】新增 M2 输入工程执行计划（WBS 四阶段/分块编辑与队列语义设计定稿/流程图三张/测试矩阵/提交序列/验收 DoD/风险预案）

### 变更

- 【web】区分待执行页容量仪表与席位行的视觉层级（仪表改内嵌读数槽、区间加分隔线）
- 【core】候选列表默认排序改为导入时间倒序（created_at 新批在上），同一秒导入的批内按文件名自然序；跨页全局有序机制不变
- 【web】历史页归档入口按钮文案「归档视图」改为「归档管理」
- 【web】设置页每个参数行布局互换：上方显示中文释义、下方小字注释显示参数名（含启动级只读参数）；范围与生效徽标保留
- 【web】调整前端字号阶梯整档上浮约 11%（2K 视口可读性：正文 13.5→15px 等七档同步），tokens/样板/设计文档三处同值，布局度量不变
- 【web】任务 id 展示全站统一三位零填充（候选/待执行/队列成员概览；padStart 只补齐不截断，≥1000 自然加宽），资源读数收敛为共享格式化函数
- 【web】提交确认框输入区读数改「完整输入」，括注实现语义（纯文本·含坐标）移回注释
- 【web】执行中页读数「WINDOW n」改「并行上限」（原英文代号随设置值变、语义歧义且与在跑/可用重复）
- 【web】执行中页按并行上限渲染槽位：在跑卡按执行 id 序占槽，空槽为虚线占位框（槽位号+横线+空闲），撤销整页空态；设计文档 §4.4/§4.5/页表同步
- 【docs】按裁决修订 M2 执行计划（新增提交前输入核验与错误码治理两项任务；编辑入口收窄为候选与失败回退队列；导入成队事件序列修正；验收与风险补强）
- 【docs】按 roadmap 一致性审查修复 M2 计划（依赖与提交归属补强、m0-plan 口径勘误登记、设计一致性补强；roadmap 回填错误码治理条目与 M1 托付项改期登记）
- 【docs】按一致性复审修复 M2 计划（提交响应规范化标记登记为第三处契约增量、C 阶段补「已自动规范化」注记承接全覆盖三条提交路径、目标段自动保存口径对齐、设计文档琥珀清单增补拼写警告注记、e2e 测试提交归属与引用勘误）

### 修复

- 【api】修正契约可空字段写法使 null 响应合法（finish_reason/cause 由 $ref+nullable 同级改为内联枚举含 null）
- 【web】对齐设置项契约命名与生效语义（10 项运行级 key/effect/range 修正并补 g16_root）
- 【web】修复 SSE 重放窗口下界与投递队满处理（超窗走快照重建、队满断连走恢复语义）
- 【web】补齐 mock 六页联演剧本（队列状态全流转、席位增减、派发、停滞告警置位/解除）
- 【web】修复前端快照重建残留与 Toast 命名规则（重建先清空旧态、队列成员取所属队列名并 15 字截断、消费 queue.status）
- 【web】移除历史抽屉遮罩硬编码色值（新增 --backdrop-dim 令牌并引用）
- 【docs】对齐设计文档与实现（--text-faint 实际色值、待执行页「在途」标记、SSE 剧本组织说明）
- 【web】修正演示种子污染真实设置库（get_state 不再自动写入 demo 参数，种子仅进引擎关闭的演示模式分支）
- 【rust】修复 HTTP 桥提交/取消后未 flush journal 致 kill -9 恢复丢任务（对齐 RPC 提交路径，消除 journal_flush_period 窗口丢失）
- 【core】修复重启对账 S3 判据：journal 恢复后 job 回退 waiting 即判重跑，不再误按 S1 接管
- 【core】补齐队列手动停止失败分流：未执行成员 skipped(queue_manually_stopped) 并整队回退
- 【web】对齐前端设计令牌与基础样式至 v2 设计规范（令牌值修正与补全、页面度量与缓动/字距令牌、基础接管清单、StateChip 两档响度、Noto Sans SC 自托管）
- 【web】修正 Link0 缺失指令名匹配与展示（后端 missing 为不带 % 前缀指令名，提交黄警缺省值回显此前永不命中）
- 【core】修正引擎启动序列 Gateway 工厂模块路径（误用同级相对导入致引擎开启即启动失败，补 select_gateway 两分支回归测试）
- 【core】修正 worker 资源记账单位与启动探测语义（sum mem 的 ResourceAmount 内部整数误当 MiB 致内存虚高一万倍、--cpus 1 违背启动探测语义致默认任务永久停等）
- 【web】提交确认框按文本读取 text/plain 完整输入（openapi-fetch 默认 JSON 解析抛错致确认框卡读取中、Link0 黄警不出现）
- 【core】兼容 worker cpus 自动探测的 list 序列化形状（原 range 闭区间解析误算 1 核，自动探测 worker 仍永久停等）
- 【core】修正 formchk 前置 chk 路径解析（对齐 g16 无扩展名 %Chk 自动追加 .chk 语义，此前 succeeded 任务 .fchk 一律缺失）
- 【core】修正执行监控双重校验基准（改取派发时刻，此前按轮询 started_at 过滤误杀真实 g16 进程树致监控读数与峰值恒零）
- 【core】S3 重跑判据补 server 重 spawn 确定性证据③（waiting 相位与进程证据可被启动对账时点错过致重跑误按接管、续跑资产无保全）
- 【core】g16 自洽环境随作业提交下发（GAUSS_* 全集经 Gateway env 传参贯通 CLI/HTTP 两实现，GAUSS_SCRDIR 强制 run/<执行id>/ 不再落到全局 scratch）
- 【web】SSE 解析器兼容 CRLF 行尾（此前前端从未真正处理过任何事件，读数/快照/Toast 全哑，页面仅靠 REST 轮询兜底）
- 【web】REST 基线轮询改合并语义（原整体覆盖卡片致 SSE 实时读数被周期性抹除）
- 【web】历史输入/输出查看按文本读取（text/plain 误按 JSON 解析致面板卡读取中）、停止模态重开清空残留错误
- 【core】席位重排放行锁定原位的等待区调整（原实现存在锁定席位即全量 409，窗口非空时等待区拖拽永不生效）
- 【core】S1 接管后监视器锚定改取 submitted_at（原以轮询 started_at 重锚致接管后进程树定位失败、读数全哑），locate 容差放宽至 30s
- 【docs】字号阶梯补 --text-2xs 档位并对齐可视化样板（纯拉丁微标签 10px 下限成 token，承载中文一律 --text-sm）
- 【web】六页硬编码字号收编 tokens 并修正中文微标签字号越限（4 处中文标签 10px 升 --text-sm，新增 --text-2xs 档承载纯拉丁微标签与刻度符号）
- 【web】声明空 favicon 消除控制台 404 噪声
- 【web】亮色主题 failed 徽标对比度达标（#c23a31 调至 #bd352b，新增 WCAG 对比度实测闸门）
- 【core】通道卡「已运行」恢复真实计时（elapsed_s 改取 now-started_at，此前硬编码 0 恒 0s）
- 【web】文件夹导入前端过滤受支持输入文件（.gjf/.com、跳过隐藏目录，过滤后为空提示且不发请求）
- 【web】待执行页等待区重排在窗口非空时生效（前端门控对齐后端锁定原位放行语义）
- 【api】候选导入响应契约补登 duplicate 字段并同步两侧生成物（前端去强转改走契约类型）
- 【web】中文微标签字号与字距全量整改（承载中文升 --text-sm、去 letter-spacing，StateChip/读数标签拆中文/拉丁两档）
- 【web】队列/历史/设置页视觉规范对齐（移除响应式残留、刷新改扫描线两态、行高对齐 40px、扫描线动效统一引用共用实现）
- 【web】挤出确认模态席位数改按实际可挤数计算（min(超限幅度, 未锁定席位数)，零挤出明示暂不挤出），替换按新旧上限差的虚高文案
- 【core】进度读数随快照恢复（executions_running 并入引擎已掌握的 progress）并在 S1 接管快进后补发一条 execution.progress，读数恢复不再受限于日志下一匹配行；截断重扫重置进度状态防陈值
- 【web】执行中页断连窗口读数降档并提示延迟（SSE 非 open 时 45% 降档+琥珀注记），快照重建改差量合并消除重建瞬间读数清空闪烁
- 【core】候选列表改为后端全局自然序排序后分页（切片前按 natural_key 稳定排序，跨页全局有序、并列保持 id 逆序）；前端废止页内排序并删除 naturalsort.ts 双实现
- 【web】修复设置保存后不实时生效：PUT /settings 触及待执行快照字段（席位上限/并行窗口）时无条件补发 pending.snapshot（原仅挤出席位场景发送），执行中页 WINDOW、待执行页 OCCUPIED 上限与侧栏灯排即时刷新，无需刷新页面
- 【web】前端消费 settings.updated 通知（脏计数驱动设置页重拉，多标签页同步；有未保存编辑时不覆盖输入）
- 【core】停滞告警阈值改为派发 tick 实时跟随设置（新任务生效，在跑不追溯；原引擎构造时固化、重启才生效）
- 【web】历史页废除 page_size=100 硬编码，省略参数由后端回落设置值（列表分页大小设置即时生效，与候选页同模式）
- 【web】修复 Link0 核数检测对 %nproc 早期同义形式与 %nprocshare 截断形式的误报（blocks 缺失判定与执行前缺省注入两处；检测取 %nproc 前缀超集，避免缺省注入与用户声明并存）
- 【web】Link0 核资源检测纳入 %CPU=proc-list（0,1,2 / 0-5 / 混合，绑定逻辑处理器语义）：视为已声明且不注入缺省 %NProcShared，记账核数 %nproc 优先、仅 %CPU 时按列表推导
- 【web】待执行页队列席位行去冗余（QUEUE 徽标旁不再重复 queue 字样），补展示队列名、成员数与提交时刻
- 【web】修复 GET /queues 回归契约（补 member_ids 聚合、last_failure 反序列化、SQLite 整数布尔还原），队列页真实数据下成员数列渲染崩溃
- 【web】修复测试运行污染工作区：SSOT models 再生比对改写临时目录（原原地再生自比较，每次 pytest 后 models.py 残留时间戳脏差异）
- 【web】修正候选页行内提交黄警文案与设计样板（「提交时」→「执行时」按默认值补齐，与派发/物化时补齐的实现时机一致）
