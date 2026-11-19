# 服务常驻与资源校验修复计划（含分子节终止空行容错与随报 UI 补丁）· 执行计划

> 状态：**已实施并验收**（2026-11-18 实施完毕，版本锚 3.9.0 随下个 minor 冻结。
> 统一序列 P1→I1→V1→V2→V3→V4→V5→D1→D2→P2…P5 共 13 提交全部落库：P1 60303aaf、
> I1 60cce7f2、V1 d2d99308、V2 0ad5064f、V3 94303eb9、V4 95e3c501、V5 db2b9d3e、
> D1 b6b21383、D2 9fbaebf6、P2 7278fcc2、P3 0fa0dbc0、P4 909b2984、P5 306d0bab。
> 验收留痕：全量 pytest 1062 passed 0 skipped（target/release/hq 在位防 e2e
> 静默跳过），各提交三闸门全绿（validate_progress / gen_changelog_md --check /
> bash -n），前端批次另过 vue-tsc/vite build 与 check_tokens / check_contrast /
> audit_frontend_offline；前端 V4/D1/D2 经 playwright 浏览器视觉实测（亮/暗
> 两主题实测通过——截图属临时产物、按仓库纪律不落仓，实测结论即留痕），
> V5 另经隔离实例真机冒烟读回 worker clamp 值（cpus=2 / mem=4096MiB =
> min(设置值, 探测值)，真 HQ 二进制接受软限制参数）；各实现提交先红后绿
> 在提交内完成（红态实测记录见各提交闸门报告）；域 A 部署机红测以
> 2026-11-18 止血取证替代（§1.2 注记），§6.1.2 完整绿测协议待用户在部署机
> 执行回贴。变更登记见 V6（chore(progress) 汇总随 3.9.0 unreleased 行）。）

## 0. 总览与需求裁决

### 0.1 四域定位

| 域 | 主题 | 性质 | 改动面 |
|---|---|---|---|
| A | 服务常驻修复（WSL2 systemd 托管） | 部署脚本 + 文档 + 测试 | 前后端代码零改动 |
| B | 分子节终止空行：警告文案修正 + 提交自动补齐锁定 | 解析层文案 + 测试 | 极小（blocks.py 两处文案） |
| C | 声明资源校验：提交阻断 + 可用资源设置 + 编辑琥珀警告 + HQ 软限制 | feat（后端 + 前端 + 引擎） | 最大 |
| D | 随报补丁：工具箱复制提示视口遮挡 + 更新按钮文案错位（§0.4） | 前端布局/文案 | 极小（两视图各一处） |

四域相互独立、可并行实施；提交序列按 §5 统一编排（文档 → 实现（测试随实现同提交） → 进度）。

### 0.2 域 C 需求裁决（用户 2026-11-18 定案）

1. 分块编辑 link0 保存超资源 → **非阻断琥珀警告**（保存放行、提交时阻断）。
2. 阻断判据 → **任一维度超限即阻断**（核数、内存分别比较）。
3. 「可用资源」两层语义：声明大于配置总量（层 a）→ **阻断提交**；仅大于
   「总量 − 在跑占用」的剩余空闲（层 b）→ **不做操作**，交由既有队列窗口
   停等与 HQ 自身资源分配（§4.5）。
4. 设置页新增「可用资源」设置项（核数 + 内存 GB），注释文本为「为 Gaussian
   计算分配的计算资源」；可传递 HQ 则传递（软限制，§4.6），否则兜底声明；
   内置自动计算默认值 = 机器可用资源 × 75%（初始值）。

### 0.3 全局口径

- 单提交单类变更、summary 中文动词开头（AGENTS §5.1）。
- 域 B/C 落库闸门 = 全量 pytest + validate_progress + gen_changelog_md --check；
  前端改动批次（V4/D1/D2）另跑 check_tokens / check_contrast / audit_frontend_offline；
  `target/release/hq` 在位（AGENTS §6.1 第 4 条，防 e2e 静默跳过虚高）。
- 工作方式（AGENTS §8.4）：最短路径、不过度设计；层 b 不新增计算逻辑即其体现。

### 0.4 域 D · 随报补丁（3.8.0 已发布批用户回报，2026-11-18）

**D1 溶剂速查「已复制」提示视口遮挡（ToolboxView）**

- 现象：仅用溶剂速查时功能正常；用过内存估算、出现「每线程需求」「充足 —」
  结论行后，点选溶剂行的「已复制」提示被遮挡不可见。
- 根因（已核实）：提示位于溶剂表滚动容器**之后**的正常流位置
  （`ToolboxView.vue:331-334`），容器限高内滚（`.sv-table-wrap`，
  `max-height: var(--peek-max-height)` 300px + `overflow: auto`，
  `:448-454`，令牌 `tokens.css:66`）；内存估算结果块（`.fm-result`，
  `:263-287`）使卡 ① 增高，把卡 ② 底部连同提示推到视口折叠线下——提示
  1.5s 自动清除（`:180`），用户下滚前即消失，复制反馈实效丢失。
- 修复：`copied`/`copyFailed` 两行提示（`:331-334`）上移至「N / M 条」
  计数行（`:308`）之后、滚动容器之前——紧邻表顶、恒处首屏可见区，正常流
  零新增样式、零令牌变更。
- 验收：亮/暗两主题浏览器实测——先出估算结果再点溶剂行，「已复制」免滚动
  可见（截图留痕）；前端三脚本 + vue-tsc/vite build 过。

**D2 更新按钮「提交中」文案错位（UpdateCard）**

- 现象：检查到更新后点「立即更新」，按钮变「提交中 …」——更新流程无
  「提交」语义，该时段实义为启动下载。
- 根因（已核实）：`apply()` 的 `applying` 窗口覆盖 POST `/update/apply`
  同步段（守卫 + 预检，`routers/update.py:38-48` 经 `asyncio.to_thread`
  执行、代理通道下可达数秒；受理 202 后才转后台下载流水线、进度经 SSE
  推送）；按钮文案（`UpdateCard.vue:235`）误用了队列域的「提交中」措辞。
- 修复：该分支字符串「提交中 …」→「下载中 …」（与后续 phase=downloading
  进度条阶段措辞衔接）；该文案无测试与契约锁定、无他处引用，随批 grep
  自查 UpdateCard 零「提交中」残留。
- 验收：浏览器实测点按钮显「下载中 …」（环境无可用更新时以静态断言替代）；
  前端三脚本 + vue-tsc/vite build 过。

（两补丁均不触契约/后端/设计令牌；提交映射 D1/D2 见 §5.2。）

## 1. 域 A · 现象、根因与范围

### 1.1 故障现象（用户报告归纳）

| # | 现象 | 关键细节 |
|---|---|---|
| S1 | 无活跃任务时服务闲置较长时间后死亡，前端打不开/不可操作 | 电脑不物理关机；重启手段 = 运行部署目录 `systemd_install.sh` |
| S2 | 运行安装脚本后恢复正常；**关闭运行过脚本的终端窗口即死亡** | 多次复现：终端开着一切正常，终端一关就死；**在跑 G16 计算任务一并死亡** |

### 1.2 根因诊断（已闭合的证据链）

服务是**用户级 systemd 单元**（`systemctl --user`，`~/.config/systemd/user/
gauforge.service`，`WantedBy=default.target`，`KillMode=process`，
`Restart=on-failure`，v2.3.0 起 afa15364 引入；v3.6.0 部署包脚本与 HEAD 逐字节
一致，已 `git show v3.6.0` diff 验证）。其生命周期悬在**两层宿主**上，两层都
没有被当前部署链路钉住：

**层 1 · WSL distro 空闲断电（S1/S2 主因）**
WSL 只认 `wsl.exe` 会话引用，**systemd 服务在跑不算存活依据**；最后一个终端
会话关闭后，distro 按 `.wslconfig` `[general] instanceIdleTimeout`（官方默认
**15000ms**，learn.microsoft.com wsl-config，2026-10 版）自动关机，整机
poweroff——journal 留痕 `Reached target poweroff.target`（WSL 2.7.14 实证，
Stack Overflow TIL；本机实测 WSL 2.7.3 / Win10 19045 同族）。**终端开着 = 会话
在 = distro 活 = 服务活**，与 S2 的复现规律逐字吻合；S1 即同机制在「离开电脑时
终端已关/会话已散」场景的滞后体现。distro 断电杀全树，`KillMode=process` 与
`Restart=on-failure` 均无从施展。

**层 2 · 用户管理器随会话终止（S2 次因；未 linger 且实际生效的
`UserStopDelaySec` 非 infinity 时独 lethal，版本域见下）**
systemd 语义：未 linger 时最后一个会话关闭 → logind 在 `UserStopDelaySec`
宽限到期后停止 `user@.service` → 用户管理器退出（先按各单元 KillMode 停单元
——gauforge 仅 SIGTERM 主进程 uvicorn；随后 system 级停 `user@1000.service`
按 **control-group** KillMode 收割**整个用户 cgroup 树**——HQ server/worker
与在跑 G16 任务全部被杀）。宽限默认值的版本域：**上游 v240–249 默认
infinity（用户管理器不随会话终止，层 2 不发生），v250 起默认 10s（层 2
成立）**——logind.conf(5) 明示该参数 240 引入、现行默认 10s，v250 NEWS 记载
默认值由 infinity 改 10s；发行版可另行改默认（开发端 Ubuntu 22.04 systemd
249 的 logind.conf 已示 `#UserStopDelaySec=10`），故**层 2 在具体机器是否
lethal 以该机取证为准、不得按上游默认值推断**。这解释了「KillMode=process
为什么没能保护任务」：它只挡**单元级**停/重启，挡不住宿主用户管理器的整树
收割。`systemd_install.sh` 对 `loginctl
enable-linger` 的尝试失败仅打印提示（stderr 被 `2>/dev/null` 吞掉）；
[deployment.md](../references/deployment.md) §2.1 也只把 linger 记作「免登录
自启」需要，**未记载不开 linger 关终端会杀服务与任务的后果**——知识缺口即
事故面。本机 polkit 策略 `set-self-linger` 默认 `allow_any=yes`（非 root 应可
直接开）；部署机 polkit 在位与否由 enable-linger 实操结果隐含验证（下注已
实操成功），后续未修复部署机按 §6.1 探针取证。
**部署机实测注记（2026-11-18）**：keepalive（层 1 修复）落位后关全部终端
1 分钟服务实测存活。该机「user manager 不随会话关闭终止」当时未经 linger 与
版本域证实：按上游 ≥250 默认 10s（发行版可 backport）推断，无 linger 应约
10 秒后停止，实测存活须另有成因（实际生效 `UserStopDelaySec=infinity` 的
backport/drop-in，或其余持有机制）——归因以部署机取证为准（`systemctl
--version` 与 logind 配置/drop-in 核对，探针见 §6.1），层 2 是否曾参与症状
留待该取证定案。层 2 已于 2026-11-18 钉死：部署机执行 enable-linger 后
`Linger=yes` 读回确认——linger 使用户管理器不随会话终止在所有版本域均
成立，两层止血闭环。

**排除项**：应用层无闲置自杀逻辑（`web/src/main.py` lifespan 关停仅摘引擎
单例不杀 HQ 进程，`engine/startup.py::shutdown_engine` 注释明示 roadmap §8.7
红线）；
任务死亡非 uvicorn 优雅退出所致，而是 cgroup 整树收割或 distro 断电。

### 1.3 目标

1. 关闭全部终端窗口、长期闲置（电脑开机不关）时，WebUI 与 HQ/在跑任务
   **持续存活**（S1/S2 消除）。
2. Windows 登录后**不开终端**即可浏览器直访（distro 随登录自动拉起，服务随
   linger 自启，免人工跑安装脚本）。
3. 修复可随发布包分发（脚本与文档进仓），部署机按 §6 协议验收：该机红测
   以 2026-11-18 取证替代、绿测实测（§6.1 注记），完整红测协议适用于后续
   未修复部署机。

### 1.4 不做（非目标，域 A）

- **不改**用户级单元为系统级单元：WebUI 重启按钮/更新自重启/`stop_all.sh`
  的免密委托依赖 `systemctl --user`（进程环境 `G16WEB_SERVICE_UNIT` 判定），
  系统级需 sudo + polkit 授权改造，改动面与部署体验双输（§8 决策 2）。
- **不动** `KillMode=process` / `Restart=on-failure` / `WantedBy=default.target`
  单元语义（§1.2 已证它们不是缺陷源）。
- **不写** `.wslconfig`（`instanceIdleTimeout=-1` 虽为官方禁用开关，但属用户
  全局配置、需 `wsl --shutdown` 才生效、旧版 WSL 静默忽略不可依赖——keepalive
  计划任务版本无关更稳，§2.1；如用户自愿可另行启用，文档仅提示）。
- **不承诺** Windows 物理关机/休眠断电后的任务存活（超 WSL 能力域；重启后由
  既有引擎对账接管，deployment.md 口径不变）。
- **不做** WSL2 localhost 转发断链的程序化自愈（既有 `start_gauforge.ps1`
  已按「WSL 内 200 而 Windows 不通 = 转发断链」给出 `wsl --shutdown` 排障口径，
  维持现状）。
- 域 A 前端/后端代码零改动（纯部署脚本 + 文档 + 测试；域 B/C 改动见 §3/§4）。

### 1.5 前置条件

1. 部署机可执行 §6 绿测与取证探针回贴（其红测判据已随 2026-11-18 止血落位
   不可复现，以既有取证替代，§6.1 注记）；任一未修复的 systemd 已启用
   WSL2 Ubuntu 可完整执行红测协议；本机（开发端）启用 systemd 需重启 WSL，
   按用户指示**暂搁置**，不阻塞本批实施（域 A 实施与单测全部可离线完成）。
2. 落库闸门见 §0.3。
3. 开工登记：progress.json `in_progress` 写入「服务常驻与资源校验修复（含
   终止空行容错）」；`in_progress` 为单槽字段，当前为工具箱批在办——开工登记
   以 toolbox-revision 批收口为前置。
4. 版本窗口依赖：CHANGELOG.jsonl 当前 unreleased 单行已装载工具箱批内容
   （progress.json unreleased 同构），本批条目进新 unreleased 行的前置 =
   toolbox-revision 批先冻结 3.8.0（或经用户裁决合并窗口、版本锚改 3.8.0，
   §5.2 统一执行顺序同步调整）。

### 1.6 依据

- 源码证据：`scripts/deploy/systemd_install.sh`（linger 尝试 + 2>/dev/null 吞错）、
  `scripts/deploy/restart_g16web.sh` / `self_update.sh` / `stop_all.sh`
  （systemctl --user 委托链）、`web/src/main.py:111`（lifespan）、
  `web/src/engine/startup.py:77`（shutdown_engine 不杀 HQ）、
  `web/src/hq/process.py`（G16/HQ spawn 于服务 cgroup 内，start_new_session
  只脱离会话不脱离 cgroup）。
- 官方语义：systemd user@.service/logind linger 生命周期与 `UserStopDelaySec`
  版本域（logind.conf(5)：240 引入、现行默认 10s；v250 NEWS：默认由 infinity
  改 10s）；polkit `org.freedesktop.login1.set-self-linger`（本机 policy 文件
  defaults 全 yes）。
- WSL 语义：learn.microsoft.com wsl-config——`instanceIdleTimeout` 默认 15000ms
  （-1 禁用）、`vmIdleTimeout` 默认 60000ms（Win11）、关全部 shell 后 ~8s 停机
  口径；WSL issue #9245（关全部终端即停机）；WSL 2.7.14 实证 TIL
  （systemd 服务不算 keep-alive、journal poweroff 判据、schtasks S4U+PT0S
  keepalive 方案）。
- 仓库留痕：deployment.md §2.1/§2.2 现状、`web/tests/test_deploy_scripts.py`
  （fake loginctl 沙箱机制，FAKE_LOGINCTL exit 1 强制走提示分支）。

## 2. 域 A · 修复设计

### 2.1 双保险架构（缺一不可）

| 保险 | 层 | 机制 | 解决 |
|---|---|---|---|
| **linger 常驻** | Linux 侧（distro 存活期间） | `loginctl enable-linger <用户>` → 用户管理器随 distro 启动自启、不随会话关闭终止 | 层 2；并使服务在 distro 启动时自动拉起（免终端） |
| **keepalive 会话** | Windows 侧（VM/distro 常驻） | 计划任务登录时后台执行 `wsl.exe -d <发行版> -u root --exec /usr/bin/sleep infinity`，恒持一个会话引用 → distro 永不满足空闲判定 | 层 1 + 免终端首启（登录即拉起 distro） |

组合语义：登录 → 计划任务拉起 distro（keepalive 会话挂住）→ systemd 自启 →
linger 用户管理器自启 → `default.target` 拉起 gauforge.service → 浏览器随时
可访；用户关终端/无终端期间服务与在跑任务不受影响。`wsl --shutdown`（人工或
排障）会杀掉 keepalive 进程，任务注册不随之消失（State 回 Ready）：重新双击
`start_gauforge.bat` 经启动器探活分支自愈复跑（§2.2 自愈 ②），或手动
`Start-ScheduledTask` 即恢复（文档注明）。

### 2.2 改动面与文件清单

| 文件 | 动作 | 要点 |
|---|---|---|
| `scripts/deploy/systemd_install.sh` | 修改 | **linger 尝试 + 强制验证 + 失败降级告警提升为 REFRESH=0/1 两分支共用**（现状仅 REFRESH=0 全新安装分支尝试；事故机 S1 恢复手段恰是重跑本脚本——服务在跑即走 REFRESH=1，不共用则该路径永不补 linger）：enable-linger 后**强制验证**（`loginctl show-user "$USER" --property=Linger --value` 输出 `yes`，或 `/var/lib/systemd/linger/$USER` 在位）→ 失败且有 TTY 时交互式 `sudo loginctl enable-linger "$USER"` 再验 → 仍失败输出**醒目告警**（后果明示：关最后终端/WSL 闲置断电杀服务与在跑任务 + 补救命令），不阻断本次启动（退出码保持 0；REFRESH=0 照常 enable --now、REFRESH=1 照常 restart） |
| `scripts/deploy/windows/install_keepalive.ps1` | 新增 | 注册计划任务 `GauForge WSL KeepAlive`：Trigger=AtLogOn（当前用户）；Action=`wsl.exe -d <发行版> -u root --exec /usr/bin/sleep infinity`；Settings=**ExecutionTimeLimit PT0S（必设，防 schtasks 默认 72h 时限杀任务）**、S4U 免密、AllowStartIfOnBatteries/DontStopIfGoingOnBatteries、Hidden；发行版名参数化，缺省复用 start_gauforge.ps1 的探测/launcher.json 口径；幂等（同名任务存在则更新）；`-Remove` 卸载；注册后立即 Start-ScheduledTask 当次生效。**注册一律走 Principal 参数集**：`New-ScheduledTaskPrincipal -UserId <域\用户> -RunLevel Limited` + `Register-ScheduledTask -Principal`；**默认 Interactive**（普通权限即可注册，AtLogOn 触发器语义下注销即停、下次登录自动拉起，承诺域内无缺口），`-Elevated` 显式参数时管理员上下文走 S4U（注销后续跑）。部署机实测（Win10 19045.6466 / WSL 2.7.10.0，2026-11-18）三坑定此策略：① `Register-ScheduledTask` 无 `-LogonType` 参数（报 "A parameter cannot be found that matches parameter name 'LogonType'"），直接传参路径不可用；② **S4U 注册需管理员提权**（普通权限报「拒绝访问」）；③ Interactive 版普通权限注册成功、State=Running，关全部终端 1 分钟服务实测存活（层 1 钉住）。schtasks `/create /xml`（UTF-16LE BOM）保留兜底，实施时按 AGENTS.md §8.3 经 context7/官方文档核校 |
| `scripts/package_release.sh` | 修改 | 白名单追加**随包分发 windows 三件套**至部署包顶层 `windows/`（`start_gauforge.bat`、`start_gauforge.ps1`、`install_keepalive.ps1`，逐文件 install 沿用根脚本白名单口径）——自愈 ② 依赖的安装器不再要求用户手工拷贝，纯部署环境开箱可用 |
| `scripts/deploy/windows/start_gauforge.ps1` | 修改 | 自愈两步在**探活通过分支与修复流程两处接线（幂等）**——探活通过是常驻场景最高频路径（服务活着、用户双击 bat），仅挂修复流程会漏接：①linger=no → WSL 内 `loginctl enable-linger <用户>`（失败提示 sudo 命令）；②keepalive 任务**缺失 → 调用 `install_keepalive.ps1` 注册；在但 State≠Running（`wsl --shutdown` 后 State=Ready 仅进程死亡的形态）→ `Start-ScheduledTask` 复跑；Running 则跳过**；install_keepalive.ps1 查找顺序 = 启动器同目录 → 部署包顶层 `windows/`，均缺失时降级提示手工命令、不打断主流程；各步结果均写入输出（成功/降级提示） |
| `docs/references/deployment.md` | 修改 | §2.1 补记：死亡两层机制（distro 空闲断电 + 用户管理器随会话终止，含 `UserStopDelaySec` 版本域与按机取证口径）、linger 后果明示、keepalive 安装与 `wsl --shutdown` 后恢复口径、诊断判据（journalctl poweroff 留痕）；§2.2 补启动器自愈两步与 windows 三件套随包分发口径（部署包顶层 `windows/` 免手工拷贝；拷至 `%LOCALAPPDATA%\GauForge\` 的既有形态须三文件同目录）；另补记域 C 可用资源软限制语义（设置值为提交校验权威口径、worker 侧 clamp 探测值且随重建生效，§4.6；dispatcher 停等记账池随软限制由全量探测值缩为 min(设置值, 探测值)、并发吞吐行为相应变化属「为 Gaussian 分配资源」预期语义，§7） |
| `web/tests/test_deploy_scripts.py` | 修改 | 新增锁定：systemd_install.sh 含 linger 验证/降级告警分支——**fake loginctl 按 env 分档升级（exit 1 / 成功 + show-user Linger=yes）**成功/失败双路径测，另测 **REFRESH=1 分支共用 linger**（fake systemctl is-active 同样按 env 可返回活跃，沿用既有沙箱）；install_keepalive.ps1 静态闸门（ExecutionTimeLimit PT0S、sleep infinity、-Remove、幂等、**Principal 注册路径**关键词在位，与 §7 风险表锁定项一致）；start_gauforge.ps1 引用 install_keepalive 且自愈覆盖探活通过/修复两分支（沿 test_windows_launcher_static_gates 风格）；打包沙箱断言部署包顶层 `windows/` 三件套在位（用例随 P2/P3/P4 对应实现提交分批落位） |
| `CHANGELOG.jsonl` / `progress.json` | 同步 | unreleased 追加摘要（随 3.9.0 行；域 A/B/C/D 汇总登记，见 §5.2 V6） |

### 2.3 关键实现细节

1. **linger 验证以「状态」为准而非「命令退出码」**：部分环境命令成功但
   logind 未落 linger 文件（权限/挂载异常），`show-user --property=Linger`
   读回 `yes` 才算通过；`/var/lib/systemd/linger/$USER` 存在性作无 D-Bus
   环境的回落判据。
2. **keepalive 用户取 root**：不依赖发行版默认用户配置（可能未设）；sleep
   无副作用，root 会话仅作引用持有。
3. **告警不阻断**：linger 安装失败时 unit 照常启动（本次仍可用），告警文案
   必须含「在跑任务会被杀」后果与补救命令，避免重蹈「提示被忽略」覆辙；
   start_gauforge.ps1 与之闭环：自愈两步在探活通过分支与修复流程两处接线
   （幂等），探活通过但 linger=no、keepalive 进程已死任务未跑均会补齐。
4. **兼容性口径**：keepalive 方案不依赖 `instanceIdleTimeout`/`vmIdleTimeout`
   版本行为，Win10/Win11、新旧 WSL 通吃；`.wslconfig` -1 仅在文档作可选提示。
5. **幂等与卸载**：install_keepalive.ps1 重复执行更新既有任务（改参数不重复
   建号）；`-Remove` 只删本任务；systemd_install.sh `--remove` 行为不变。

## 3. 域 B · 分子节终止空行（提示修正 + 自动补齐锁定）

### 3.1 现状机制（已核实，改动极小的根由）

1. 警告产生点（非阻断 warnings 通道）：`web/src/parse/blocks.py:472`
   （文案行；`warnings.append` 起点 :470、kind 行 :471，
   `molecule_unterminated`，文案「分子说明节未以空行终止（建议补终止空行）」）、
   `blocks.py:511-512`（文案行；append 起点 :509、kind 行 :510，
   `variables_unterminated`，「变量/常数区未以空行终止
   （建议补终止空行）」）。
2. **提交时自动补终止空行的机制已存在**：`verify_and_normalize`
   （`blocks.py:651`，空行规约「除 link0 外每节末尾恰好一个空行（含文件末节
   与文件末尾）」，末节收口 `body + "\n\n"`）在 `verify_and_store`
   （`web/src/services/verify.py:228`）内执行，规范化有变化即原子写回
   `inputs/<id>`，响应 `normalized=true`（前端已有「输入已自动规范化
   （换行/空行）」注记）。
3. 全部提交路径统一过该咽喉：行内提交 `routers/candidates.py:201`、队列提交
   `routers/queues.py:137`、历史重新排队 `services/history.py:344`、断点续跑
   `services/resume.py:279`、组合流 `services/workflows.py:254/276`——
   自动补齐覆盖无死角。
4. 缺陷本体 = **文案误导**：「建议补终止空行」引导手工操作，而 molecule 节
   不可编辑（`is_editable_section` 排除，`save_block` 对 molecule 直接 400
   「molecule 节不可编辑」），提示不可落地；用户无从知晓提交时会自动补上。

### 3.2 改动设计

1. **文案修正（仅两处字符串）**：`blocks.py:472` 与 `:511-512` 两处文案行的
   「（建议补终止空行）」→「（提交时将自动补上）」——中性、可预期、不引导
   无效操作；kind 词表不变（`molecule_unterminated` / `variables_unterminated`）。
2. **测试锁定（先红后绿）**：新用例复刻用户场景形态（分子节延展至 EOF 无
   终止空行，L9 形态）断言链：导入解析警告在位（新文案锚点）→ 提交成功且
   `normalized=true` → 写回文本末节含终止空行 → 复解析零该警告。既有用例按
   kind 断言（`test_parse_blocks.py:421/433/436/438/936`），文案变更零回归；
   `test_warning_messages.py` 词表不变。

### 3.3 不做（域 B）

- **不改导入原文**：导入仍保存原始字节（「原文」语义、CRLF 检出依赖），
  规范化（含终止空行补齐）只在提交事务内发生——与用户「在提交时自动补上」
  的要求逐字对齐（§8 决策 8）。
- route/title 节未以空行终止属 `parse_errors` **阻断**（其后内容被吞并、结构
  不可自动修复），不在本域（既有行为不变）；附加输入节未终止（§blocks.py:521）
  同属结构判定，不纳入自动补齐。

## 4. 域 C · 声明资源校验与可用资源设置

### 4.1 现状机制与缺陷根因（已核实）

1. **提交链无资源维度校验**：`verify_and_store` 只做规范化/解析/多步/拼写/
   每核下限黄警/testrt 降级；资源声明只在派发时经 `resolve_link0` 记账并随
   HQ submit 传资源请求（`dispatcher.py:467-473`，`{"cpus", "mem_mib"}`）。
2. **HQ worker 自动探测全量物理资源**：`ensure_worker` 不传 `--cpus`
   （`hq/process.py:132`，mem 由 HQ 自动上报）→ 声明 32 核 128GB 的作业在
   HQ 无可分配 worker，job 恒 waiting；WebUI 无告警无自愈，只能手动移除席位
   （用户故障原样）。
3. **记账口径单点**：`resolve_link0`（`engine/workspace.py:70`）——%nproc 系
   /%cpu/%mem 声明优先、缺省注入 `link0_default_nproc`/`link0_default_mem_gb`；
   提交链已有同法先例 `_check_mem_floor`（`verify.py:211`，每核下限黄警）。
4. **HQ worker 资源上限可传**：`SharedWorkerStartOpts`（
   `crates/hyperqueue/src/client/commands/worker.rs:83`）支持
   `--cpus <定义>` 与 `--resource "<名>=sum(<数值>)"`（
   `crates/hyperqueue/src/worker/parser.rs:147` `parse_resource_sum`）；
   内建内存资源名 `mem`、单位 MiB（`worker_resources`
   解析口径 `hq/gateway.py:33`，ResourceAmount 内部整数 = MiB×10000）。

### 4.2 设置项设计（C1）

| key | value_type | range | effect | description |
|---|---|---|---|---|
| `available_cpu_cores` | integer | min 1 / max 256 | new_submissions | 为 Gaussian 计算分配的 CPU 核数 |
| `available_mem_gb` | number | min 1 / max 1024 | new_submissions | 为 Gaussian 计算分配的内存 GB |

- 条目 schema 按既有惯例六字段：`key/value_type/range/editable/effect/
  env_var`，新键补 `editable=True, env_var=None`（沿 RUNTIME_SETTINGS 既有
  条目形态）。
- 语义：**WebUI 提交校验的权威口径**（用户手动分配的计算资源）；同时作为
  worker 软限制传 HQ（§4.6，clamp 探测值，软限制声明）。
- **默认值 = 机器可用资源 × 75%**（初始值）：核数
  `floor(可用逻辑核数 × 0.75)` 且 ≥1；内存
  `floor(物理内存总量 GB × 0.75)` 且 ≥1。实现：`config.py` 新增探测单点
  `_available_resources() -> tuple[int, float]`——核数
  `len(os.sched_getaffinity(0))`（可用逻辑核，OSError 回落
  `os.cpu_count() or 1`；与 HQ worker 自动检测同口径，worker 侧 clamp
  比较成立，§4.6）、内存 `/proc/meminfo` `MemTotal`（物理内存总量；
  KiB→GB 向下取整；不可读记 0）；任一探测失败
  整体兜底保守值 `(4, 8)` 并 `logger.warning`（不炸启动）。`RUNTIME_DEFAULTS`
  两键引用 75% 计算结果（import 时定值，进程生命周期内稳定；测试经
  monkeypatch 注入探测函数）。
- 设置页**零改动**（SettingsView 数据驱动渲染运行级目录，新 key 自动出现）；
  契约核对：openapi.yaml `SettingsResponse` 描述若枚举运行级参数词表则同步
  补行（§5.2 V1 核对项）。
- 命中仓库 UI 文案纪律：description 不含内部实现概念；「可用资源」为用户
  视角命名（§0.2 裁决 4 措辞拆分到两键）。

### 4.3 提交链阻断校验（C2，权威阻断）

- **位置**：`verify_and_store` 内、解析校验 ③④ 通过后、warnings 收集与写回
  之前——结构合法才谈资源；`raise` 即不写盘（维持「失败不写盘」原则）。
- **取值**：`resolve_link0(text, nproc_default, mem_gb_default)` 返回 dict
  （`{"completed_text", "nproc": {value, defaulted}, "mem_gb": {…}}`）——
  判定取 `resolved["nproc"]["value"]` 与 `resolved["mem_gb"]["value"]`，
  缺省注入注记取 `defaulted` 标志（§4.4 加注数据源）；记账口径与派发、
  `_check_mem_floor` 完全同源（含 %cpu proc-list 推导、缺省注入、非法值
  回落缺省的既有语义）。
- **取值来源（无调用方传参）**：`verify_and_store(task_id)` 签名不变、五
  调用方只传 id，两组数值均在函数内 `settings().get(...)` 自取——link0
  缺省沿 `_check_mem_floor` 先例（`verify.py:217-219`）自取
  `link0_default_nproc/link0_default_mem_gb`，可用阈值自取
  `available_cpu_cores/available_mem_gb`；`SettingsRepo.get` 缺记录回落
  `RUNTIME_DEFAULTS`，新键默认值自然生效。
- **判定（用户裁决：任一维度）**：`nproc > available_cpu_cores` 或
  `mem_gb > available_mem_gb` → `raise err("RESOURCE_OVERCOMMIT", …, http=422)`。
  恰好等于不拦（严格大于）。
- **message**（按实际超限维度组句，单维/双超两形态；前缀补任务名（取任务
  记录 `tasks.filename`）——多成员批量提交首个超限即中止，details.task_id
  前端不透出，任务名随 message 逐条可辨，降低批量排查成本）：
  「任务 <任务名>：声明资源超过可用资源 — 核数 32 > 可用 10 /
  内存 128 GB > 可用 24 GB；请修改输入 %nprocshared/%mem 声明，或在设置页
  调整可用资源」。
- **details**：`{task_id, declared: {nproc, mem_gb},
  available: {cpu_cores, mem_gb}, exceeded: ["nproc", "mem_gb"]}`。
- **覆盖面**：§3.1 第 3 条五调用方全量自动覆盖（行内/队列/重新排队/续跑/
  组合流）——crest 等程序化任务同过此咽喉无特判（缺省注入值通常远小于可用，
  天然放行；组合流模板 nproc 超限时错误经既有 ComboFlowDialog 错误区回传）。
- **层 b 不触发**（§4.5）：校验只比配置总量，不扣减在跑占用。

### 4.4 分块编辑琥珀警告（C3，非阻断——用户裁决）

- **产出点**：`candidates.file_warnings`（四通道统一单点：导入 / 预览 /
  分块保存响应 / 列表 `warning_count` 徽标现算；提交核验 warnings 同挂
  该单点、对本 kind 结构性不可达——超限即 422、warnings 到不了响应，
  自然冗余无害）追加资源域检查 `_resource_over_warnings(...)`：
  - 以既有入参 `lines`（`split_lines` 产物）重建文本（`"\n".join`）供
    `resolve_link0`——零签名变更（换行已归一，对解析无影响）；
  - 警告 line = %nproc/%mem 声明行全文件绝对行号（`_mem_decl_line` 同法扩展
    核数行）；记账值 defaulted=true（缺省注入）时 message 加注
    「（按缺省值补齐）」，指引调设置而非改输入。
- **kind**：`resource_over_available`（Warning.kind 词表扩容——openapi.yaml
  词表描述同步；test_warning_messages.py `KIND_VOCABULARY` 14→15 并补
  CASES 模板样例，样例经 `_resource_over_warnings` 纯函数构造、沿
  `_mem_floor_warning` 先例，文件纪律「新 kind 无中文文案口径不得上线」；
  BlockEditor `KIND_SECTION` 补映射到 "link0" 块，该表注释
  明示「词表扩容须同步本表」）。
- **message**：「声明资源超过可用资源（核数 32 > 10 / 内存 128 GB > 24 GB）
  — 提交将被拒绝，请调整声明或设置页可用资源」。
- **提交前知情**：阻断时 422 为权威反馈；提交确认框预显通道
  （`submitPreviewWarnings`，读 preview warnings）已承接提交前知情。
- 分块保存放行（非阻断）：超限声明可暂存，提交时把关（§0.2 裁决 1）。

### 4.5 层 b 语义明示不做

「总量 − 在跑占用」的剩余空闲**不新增**计算与告警：既有队列窗口停等
（成员 `wait_reason=resource`「等资源」，PendingSeatMembers 已渲染）+
dispatcher 资源停滞闸 + HQ 侧 waiting 自持已覆盖；「声明 ≤ 配置总量但 >
当前空闲」的作业由 HQ 排队等资源释放，属预期行为（§0.2 裁决 3，§8 决策 7）。

### 4.6 HQ 软限制传递（C4）

- `ensure_worker`（`hq/process.py:132`）扩展：spawn worker 时追加
  `--cpus <N>` 与 `--resource "mem=sum(<MiB>)"`；数值语法与单位以
  `crates/hyperqueue/src/worker/parser.rs` 为准（`parse_resource_sum` +
  ResourceAmount MiB 域），实施时按 AGENTS §8.3 经源码/context7 复核，测试锁
  spawn args 文本形态。
- **clamp 兜底（软限制声明）**：`N = min(available_cpu_cores, 可用逻辑核数)`、
  `mem MiB = min(available_mem_gb, 物理内存总量 GB) × 1024`——HQ 对 worker
  资源声明**不校验硬件上限**（`--cpus N` 直接转逻辑核号注册，唯一资源校验
  `crates/tako/src/internal/common/resources/descriptor.rs:325-368` 仅查
  重名/空值/列表唯一/cpus 存在性，超物理声明被静默接受），不 clamp 将以
  虚报容量登记、诱发调度超卖，故取探测值封顶；clamp 只影响 worker 侧上限，
  **设置值本身仍是校验权威口径**（§4.3），两口径差异在 deployment.md 与
  本节明示「软限制」（§0.2 裁决 4）。资源探测复用 §4.2
  `_available_resources()`。
- **生效时机**：worker 重建时（服务重启 / watchdog 重起 server 后
  ensure_worker；复用在线 worker 不重启）；校验侧即时（new_submissions）。
  既有显式 `cpus` 入参（测试约束用）语义保留：显式入参优先，未传时读设置。
- 测试：spawn args 断言（含 clamp 分支）；worker 资源读回沿用既有
  `worker_resources` 解析单点不变。

### 4.7 契约与前端登记（C5）

- openapi.yaml：Warning.kind 词表 + `resource_over_available`；错误码 +
  `RESOURCE_OVERCOMMIT`（422）；运行级参数词表核对补行；前端
  `api/contract.ts` 经 openapi-typescript 再生（随 V4）。
- 测试侧契约镜像同步（测试随实现同提交，与实现落码同批）：test_error_codes.py
  `CONTRACT_CODES` 40→41——该集为 openapi 文件头错误码全集的测试侧镜像，
  `test_impl_codes_subset_of_contract` 断言实现码 ⊆ 该集，与
  `RESOURCE_OVERCOMMIT` 实现同批落位保提交点全绿；test_warning_messages.py
  `KIND_VOCABULARY` 14→15 并补 CASES 模板样例（§4.4）。
- 前端错误分支纯透传：CandidatesView `confirmSubmit` 与 QueueEditorModal
  既有错误分支 else 路径已透出服务端 `body.error.message`，本批零新增按码
  分支字面量，`RESOURCE_OVERCOMMIT` 不入 FRONTEND_CODE_BRANCHES 允许集
  （该闸门只约束前端源码按码分支字面量，纯透传无登记义务）。
- BlockEditor `KIND_SECTION` 补映射，并修正表头注释的词表计数（现写
  「12 kind 全覆盖」已陈旧，按扩容后实数 15 改写）；设置页自动渲染零改动；
  UI 文案分隔用「—」（禁「·」）、无内部语义词（仓库 UI 文案纪律）。

## 5. 统一 WBS 与提交映射

提交序列按「文档 → 实现（测试随实现同提交，先红后绿在提交内完成） → 进度
同步」，单提交单类变更（AGENTS §5.1）；summary 中文动词开头。

### 5.1 域 A 分表

| 编号 | 提交（type: summary） | 内容 | 验收要点 | 依赖 | 规模 |
|---|---|---|---|---|---|
| P1 | `docs(plans): 落盘服务常驻与资源校验修复计划` | 本文档 | 四域设计/统一 WBS/验证协议齐备；状态行「执行计划」 | — | S |
| P2 | `fix(scripts): 强 linger 验证并补安装失败告警` | systemd_install.sh §2.2 行（linger 尝试/验证/告警提升为 REFRESH=0/1 两分支共用）+ test_deploy_scripts.py 用例随批（linger 验证/降级告警/REFRESH=1 共用，fake loginctl 按 env 分档） | 提交内先红后绿；fake 成功路径零告警；exit 1 路径走降级告警不阻断；REFRESH=1 沙箱用例同样补装并验证 linger；既有 fake loginctl 沙箱不触真机；bash -n 过 | P1 | M |
| P3 | `feat(scripts): 新增 keepalive 安装器并随包分发 windows 三件套` | install_keepalive.ps1 + package_release.sh §2.2 行 + test_deploy_scripts.py 用例随批（安装器静态闸门：ExecutionTimeLimit PT0S、sleep infinity、-Remove、幂等、Principal 注册路径；打包沙箱断言） | 提交内先红后绿；§2.2 静态要点齐；幂等/-Remove 在位；打包沙箱断言部署包顶层 `windows/` 三件套在位 | P1 | M |
| P4 | `feat(scripts): 补齐启动器 linger 与 keepalive 自愈接线` | start_gauforge.ps1 §2.2 行 + test_deploy_scripts.py 用例随批（自愈覆盖探活通过/修复两分支，沿 test_windows_launcher_static_gates 风格） | 提交内先红后绿；自愈两步在探活通过与修复流程两分支均接线且幂等；任务缺失→注册、在但 State≠Running→`Start-ScheduledTask` 用例在位；探活主流程零回归 | P2, P3 | M |
| P5 | `docs(references): 补记部署指南常驻机制与诊断口径` | deployment.md §2.1/§2.2 | 两层机制（含 UserStopDelaySec 版本域口径）/linger 后果/keepalive/windows 分发口径/恢复口径/域 C 软限制语义齐 | P2–P4 | S |
| P6 | `chore(progress): 登记服务常驻修复批次` | CHANGELOG.jsonl + progress.json | validate_progress / gen_changelog_md --check 过 | P5 | S |

（P3/P4 属部署脚本批次，`audit_frontend_offline.sh` 与视觉走查不适用；
`check_plan_status.py` 随发布窗口跑。测试用例随对应实现提交同批落位、
先红后绿在提交内完成，不单列测试提交（AGENTS §5.1）。P6 与域 B/C 进度
登记合并为 V6 汇总执行，见 §5.2。）

### 5.2 域 B/C 分表与统一执行序列

| 编号 | 提交（type: summary） | 内容 | 验收要点 | 依赖 | 规模 |
|---|---|---|---|---|---|
| I1 | `fix(parse): 修正终止空行警告提示文案` | blocks.py:472 / :511-512 两处「（建议补终止空行）」→「（提交时将自动补上）」+ test_parse_blocks / test_submit_verify 用例随批：EOF 未终止分子节 → 警告在位（新文案锚点）→ 提交成功 normalized=true → 写回末节含终止空行 → 复解析零该警告 | 提交内先红后绿；既有 kind 断言零回归；route/title/附加节终止判定不涉及 | P1 | S |
| V1 | `docs(api): 扩容契约资源校验词表` | openapi.yaml：Warning.kind + `resource_over_available`、错误码 + `RESOURCE_OVERCOMMIT`（422）、运行级参数词表核对补行 | 词表三处齐；SettingsResponse 枚举核对结论留痕 | P1 | S |
| V2 | `feat(web): 新增可用资源设置项` | RUNTIME_DEFAULTS / RUNTIME_SETTINGS 两键 + `_available_resources` 探测（§4.2）+ 探测与 75% 默认用例随批（monkeypatch 注入） | 提交内先红后绿；探测失败兜底不炸启动；设置页数据驱动渲染核对 | V1 | S |
| V3 | `feat(services): 新增提交链资源超声明阻断与四通道琥珀警告` | verify_and_store 阻断（§4.3）+ file_warnings 资源域检查（§4.4）+ 契约测试镜像同步（test_error_codes.py `CONTRACT_CODES` 40→41、test_warning_messages.py `KIND_VOCABULARY` 14→15 与 CASES 纯函数样例，§4.7）+ 用例随批：超限 422 三分（核数超/内存超/双超）/恰好等于放行/缺省注入超限同拦/file_warnings 四通道（导入/预览/分块保存/徽标计数） | 提交内先红后绿；不触真 g16（纯算术 + resolve_link0 纯函数）；五调用方既有用例零回归 | V2 | M |
| V4 | `feat(frontend): 补资源超限警告渲染并核对提交错误分支透传` | contract.ts 再生、KIND_SECTION 补 `resource_over_available` 映射并修正表头注释计数（§4.7）、两视图既有错误分支透传服务端 message 核对（零新增按码分支） | vue-tsc/vite build 过；FRONTEND_CODE_BRANCHES 允许集零新增；check_tokens / check_contrast / audit_frontend_offline 过 | V3 | M |
| V5 | `feat(hq): 传入可用资源软限制至 worker 启动参数` | ensure_worker clamp + spawn args（§4.6） | spawn args 断言（含 clamp 分支，随批先红后绿）；hq 在位 e2e 不回归 | V2 | S |
| D1 | `fix(frontend): 上移溶剂速查复制提示防视口遮挡` | ToolboxView.vue copied/copyFailed 两行提示移至「N / M 条」计数行后、滚动容器前（§0.4 D1） | 亮/暗两主题浏览器实测估算结果在场时点选行提示免滚动可见（截图留痕）；vue-tsc/vite build 过；check_tokens / check_contrast / audit_frontend_offline 过 | P1 | S |
| D2 | `fix(frontend): 改更新按钮点击后提示为下载中` | UpdateCard.vue:235 applying 分支「提交中 …」→「下载中 …」（§0.4 D2） | 浏览器实测点按钮显「下载中 …」（无可用更新环境以静态断言替代）；随批 grep 零「提交中」残留；vue-tsc/vite build 过；check_tokens / check_contrast / audit_frontend_offline 过 | P1 | S |
| V6 | `chore(progress): 登记服务常驻与资源校验修复批次` | CHANGELOG.jsonl + progress.json（域 A/B/C/D 汇总，unreleased 随 3.9.0 行；吸收 P6） | validate_progress / gen_changelog_md --check 过；check_plan_status 发布窗口跑 | 全部 | S |

**统一执行顺序**：P1 → I1 → V1 → V2 → V3 → V4 → V5 → D1 → D2 → P2…P5 → V6。
域 A（P2–P5）、域 B/C（I/V）与域 D（D1/D2）相互独立、可穿插；P6 不单跑，
并入 V6 汇总登记。
版本窗口前置：toolbox-revision 批先冻结 3.8.0、开新 unreleased 行后，V6 方
以 3.9.0 行落盘（§1.5 前置 4）；若经用户裁决合并窗口，则本批条目并入该行、
版本锚与状态行同步改锚。

## 6. 验证协议

### 6.1 域 A 部署机红/绿实测（HITL）

> 本机（开发端）WSL systemd 未启用，启用需 `wsl --shutdown` 重启，按用户指示
> 搁置；以下命令由用户在**部署机**执行并回贴输出，作为域 A 验收留痕。探活
> 端口默认 8300，运行级设置改过端口的机器按设置页实际值替换。

#### 6.1.1 红测（修复前：取证 + 复现分层）

> 时间线注记：部署机已于 2026-11-18 止血落位（`Linger=yes` 读回 + keepalive
> 注册，§1.2 注记）——② 的 Linger 读回判据（红测前提为 no）与 ③ 复现红在该机
> 已永久不可执行，其红测结论以 2026-11-18 故障报告与 §1.2 注记取证替代；
> ① 的运行态实测已留痕于文，② 的版本域/logind 配置/polkit 取证探针在该机
> 仍可执行且须回贴（层 2 归因定案依据）。完整红测协议仅对后续未修复部署机
> 执行。

```powershell
# ① 版本与运行态（Windows PowerShell）——部署机已实测：WSL 2.7.10.0 /
#    内核 6.18.33.2-2 / Win10 19045.6466（属 15s 断电行为版本域）
wsl --version
wsl -l -v

# ② 两层证据（loginctl/journalctl 是 WSL 内命令，经 wsl.exe 包装；单引号
#    原样透传，$USER 由 WSL 内 bash 展开。红测前提：未开 linger，读回为 no）
wsl -d <发行版> -- bash -lc 'systemctl --version | head -1'   # systemd 版本 → UserStopDelaySec 上游版本域（≤249 默认 infinity / ≥250 默认 10s）
wsl -d <发行版> -- bash -lc 'grep -i UserStopDelaySec /etc/systemd/logind.conf /etc/systemd/logind.conf.d/*.conf 2>/dev/null'   # logind 实配（发行版 backport/drop-in 覆盖以此为准，§1.2）
wsl -d <发行版> -- bash -lc 'test -f /usr/share/polkit-1/actions/org.freedesktop.login1.policy && echo policy-ok; pkaction --action-id org.freedesktop.login1.set-self-linger --verbose'   # polkit 在位 + set-self-linger 放行读回（enable-linger 失败时归因用）
wsl -d <发行版> -- bash -lc 'loginctl show-user "$USER" --property=Linger'   # no = 层 2 确认
wsl -d <发行版> -- bash -lc 'journalctl --user -u gauforge -n 50 --no-pager' # 服务死亡时间线
# poweroff 留痕在历史 boot（distro 断电后本次 wsl 调用已拉起新 boot，
# boot 计数仅在 distro 冷启动时递增）：先 list-boots，再逐 boot 回溯 grep
wsl -d <发行版> -- bash -lc 'sudo journalctl --list-boots | tail -5'
wsl -d <发行版> -- bash -lc 'sudo journalctl -b -1 --no-pager | grep -i poweroff | tail -3'
# 出现 "Reached target poweroff.target" = 层 1 确认（sudo 要密码则在 WSL 终端内执行）

# ③ 复现红：关掉全部 WSL 终端 → 等 ≥30s → Windows 侧：
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8300/api/v1/system/health   # 非 200 = 红
wsl -l -v   # Stopped = distro 已断电（层 1）；Running 但 8300 不通 = 层 2
```

#### 6.1.2 绿测（修复后验收）

```bash
# ① 前置确认
loginctl show-user "$USER" --property=Linger          # 期望 yes
# Windows：Get-ScheduledTask 'GauForge WSL KeepAlive'   # 期望 Ready/Running

# ② 常驻验收：关全部终端 → 等 ≥30s → Windows 侧 curl health = 200，wsl -l -v = Running
# ③ 免终端自启：Windows 重启 → 登录后不开终端 → 浏览器直访 8300 = 200
# ④ 任务保护验收：提交长任务 → 关全部终端 → 等 ≥60s → 重开终端
#    `systemctl --user is-active gauforge` = active 且任务进度持续推进（journal 佐证）
# ⑤ 恢复口径：wsl --shutdown 后任务注册仍在（State=Ready、进程已死）→
#    双击 start_gauforge.bat → 探活分支自愈复跑
#    （Get-ScheduledTask State=Running）且服务可达
```

#### 6.1.3 域 A 开发端闸门（每提交）

`uv run pytest`（全量，hq 在位）+ `uv run python scripts/validate_progress.py`
+ `uv run python scripts/gen_changelog_md.py --check` + `bash -n`（改动 sh）；
P3/P4 附加本机 PowerShell 可用性冒烟（Win10 19045 实测注册/卸载各一次）。

### 6.2 域 B/C 开发端闸门与冒烟

**每提交闸门**：`uv run pytest`（全量；`target/release/hq` 在位防 e2e 静默
跳过虚高）+ `scripts/validate_progress.py` + `scripts/gen_changelog_md.py
--check`；V4/D1/D2 附加 `scripts/check_tokens.py`、`scripts/check_contrast.py`、
`scripts/audit_frontend_offline.sh` 与 vue-tsc/vite build。

**域 B/C/D 真机冒烟与走查（V5/D1/D2 后执行，视觉走查按 AGENTS §6.1 留痕截图）**：

```text
① 阻断红：设置页改可用资源 = 2 核 / 4 GB → 提交 4 核任务 → 422 被拦，
  文案指明超限维度与数值，且输入副本未被写回（失败不写盘）
② 放行绿：可用资源调回默认（≥任务声明）→ 同任务提交放行入席
③ 编辑琥珀：分块编辑 link0 改 %nprocshared=64 → 保存成功（非阻断）+
  link0 块琥珀警告在位 + 列表 warning_count 徽标 +1
④ worker 软限制：重启服务后 WSL 内 `hq worker list`（与 dispatcher 停等
  记账同源字段）读回 cpus/mem = min(设置值, 机器探测值)——设置值超探测值时
  取探测值（clamp 分支实测）
⑤ 域 B 场景：导入末行无终止空行的 gjf → 列表琥珀警告文案 =「提交时将自动
  补上」→ 提交成功 + 规范化注记 → 预览复解析零该警告
⑥ 视觉：亮/暗两主题下新警告与 422 错误文案对比度走查（check_contrast 全
  组合闸门之外的人工确认）
⑦ 补丁 D1：先出内存估算结果 → 点溶剂行 → 「已复制」免滚动可见（亮/暗两
  主题截图留痕）
⑧ 补丁 D2：更新卡点「立即更新」→ 按钮显「下载中 …」（受理转下载进度条阶段
  按钮回「立即更新」置灰；环境无可用更新时以静态断言替代）
```

## 7. 风险与回退

| 风险 | 缓解 | 回退 |
|---|---|---|
| 部署机 polkit 缺失导致非 root enable-linger 失败 | 脚本交互式 sudo 兜底 + 醒目告警 + start_gauforge 自愈闭环 | 按告警手动 `sudo loginctl enable-linger` |
| schtasks 72h 默认时限杀 keepalive | ExecutionTimeLimit=PT0S 写死 + 测试锁定 | 重跑 install_keepalive.ps1 |
| PS 版本差异：Register-ScheduledTask 参数集不全（部署机实测无 -LogonType） | 实现固定走 New-ScheduledTaskPrincipal + -Principal 路径（全版本可用）；静态闸门锁定 Principal 关键词 | schtasks /create /xml 兜底 |
| S4U 注册需管理员提权（部署机实测普通权限「拒绝访问」） | 提权检测 + Interactive 降级路径（AtLogOn 语义下等效覆盖登录→注销时段）；输出明示所用类型 | 管理员窗口注册 S4U |
| `wsl --shutdown` 后 keepalive 失效被误判复发 | 文档明示恢复口径（任务注册不随 shutdown 消失，双击 bat → 探活分支自愈 `Start-ScheduledTask` 复跑） | — |
| 登录前（锁屏期）服务不可用 | S4U 注销不杀任务；boot 触发器需管理员，按需用户自选（文档提示） | 可选加 boot 触发 |
| keepalive 会话占用极轻资源（sleep） | 无副作用进程；资源占用可忽略 | `-Remove` 卸载即回现状 |
| HQ `--resource mem=sum` 单位/语法与预期不符 | 实施前按 `crates/hyperqueue/src/worker/parser.rs` 复核（AGENTS §8.3）；spawn args 测试锁定 | 移除传参恢复 worker 自动探测（行为零变化） |
| 设置值超过机器探测值造成两口径分歧 | clamp 只限 worker 侧；校验仍用设置值；文档明示软限制 | 用户自行调低设置值 |
| worker 软限制使 dispatcher 停等记账池由全量探测值缩为 min(设置值, 探测值)，并发吞吐行为变化 | 属「为 Gaussian 分配资源」的预期语义；deployment.md §2.2 补记（§2.2）；V5 既有 e2e 不回归覆盖 | 用户调高设置值即回全量口径 |
| file_warnings 增域后既有候选徽标数变化 | 口径正确（导入即示警，属修复而非回归）；V2 回归用例覆盖 | — |
| 缺省注入值超可用（用户把可用资源调得极小） | 与声明同一记账口径统一拦截，message 注明「按缺省值补齐」指引调设置 | 调高设置值 |
| 资源 422 对组合流批量提交的中断面 | workflows.py 咽喉统一，错误经既有 ComboFlowDialog 错误区逐条回传 | — |


