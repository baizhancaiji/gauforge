# 代码审查报告：m4 插波批次 D（crest/xtb 配套部署）独立复核

- 审查人：实现代码审查专员（独立复核，不采信实施者自述）
- 日期：2026-10-14
- 分支：g16-webui（审查起止工作区均干净，审查全程零仓库文件改动）

## 一、审查依据与范围

- 依据：`docs/plans/m4-combo-template-deploy-plan.md` §3.5 crest/xtb 部署设计、
  §2 WBS 批次 D 行（D1–D5）与批次子步骤、§4 测试矩阵 test_deploy_scripts.py 行、
  §5 提交 #11–#13（含 #14 回填与进度同步）、§6 闸门、§7 R-6/R-7/R-12/R-13、
  §8 开放事项 3、附录 B D1–D5 留痕（不采信自述，可本地复现项均已独立复跑）。
- 对象（提交）：2129e931（setup_deps.sh + 打包接线 + 沙箱测试）、47e0c071
  （deployment.md 接入节）、b5dd42f5 / 22fbd736（进度与走查回填）、4eb68e9c
  （.gitignore）。
- 对象文件：`scripts/deploy/setup_deps.sh`、`scripts/package_release.sh`、
  `docs/references/deployment.md`、`web/tests/test_deploy_scripts.py`、`.gitignore`。
- 范围证实：`git status` 起止均为 clean；`git show --stat` 逐提交核对——
  2129e931 恰含 setup_deps.sh(+174)/package_release.sh(+7)/test_deploy_scripts.py(+169/-0)，
  47e0c071 恰含 deployment.md(+50/-2)，b5dd42f5 恰含 CHANGELOG.jsonl/CHANGELOG.md/progress.json，
  22fbd736 恰含计划文档(+95)，4eb68e9c 恰含 .gitignore(+2)。测试文件为纯新增，
  既有 6 用例零改动、零削弱。
- 报告落盘：`docs/plans/m4-combo-deploy-review-D.md`（调用方指定；落盘前确认该路径无既有文件，未覆盖任何报告）。

## 二、总评与结论

**有条件通过。**

脚本本体（setup_deps.sh）设计完全符合 §3.5：幂等冒烟判据、半成品清理重装、
--xtb 可选装、代理三通道约定（与 update.sh 同款、与 install.sh 的
GAUFORGE_GH_PROXY 零混用）、布局归一对齐运行级默认值，均经沙箱用例 +
真实上游资产端到端安装独立复现；资产名/字节数/校验和口径经 GitHub API 与
实下载逐位复核，与 D4 留痕完全一致；打包接线（D5）经既有部署包 tar 断言与
包内文件逐字节 diff 证实。全部闸门独立重跑全绿（含全量 738 passed 零跳过）。

唯一实质问题是 **deployment.md §6.2 离线手动路径的两处布局说明失实**
（D-1/D-2，P1）：其描述的「crest tar 内为平铺文件」「xtb tar 顶层即
xtb-6.7.1/ 目录」与上游真实布局（ crest/crest 同名嵌套、xtb-dist/ 顶层，
即 D2 缺陷①②的实测事实与脚本归一逻辑所针对的形态）直接矛盾——用户照文档
字面操作会装出运行级找不到二进制的坏布局，离线路径不可用。该文档提交
（47e0c071）晚于 D2 修复落库（2129e931），属批次内文档口径未随缺陷事实更新。

放行条件：

1. 修正 D-1/D-2（docs 类单类变更提交，仅改 deployment.md §6.2 两条布局说明；
   脚本与测试无需动）。
2. D-3～D-6（P3）不阻断，建议下次脚本触批顺手收口。

## 三、功能完整性对照（§3.5 / §2 D / §4 / §5 逐条）

| 编号 | 计划条目 | 实现位置 | 结论 |
|---|---|---|---|
| R1 | 幂等判据＝`--version` 冒烟通过方视为已安装，仅目录存在不算 | setup_deps.sh:79-93（smoke() + install_crest 分支）、:126-135（xtb 同构）；test_deploy_scripts.py:462-472 | 已落地（必失败 curl 重跑实测零下载跳过） |
| R2 | 目录在但冒烟失败＝半成品残留，清理后重装 | setup_deps.sh:90-92、:132-134；test:475-487 | 已落地（沙箱断言「半成品残留」+ 重装后冒烟通过） |
| R3 | `--xtb` 可选装 xtb 6.7.1，不带时零 xtb 下载 | setup_deps.sh:163-164；test:524-528（curl 日志零 xtb URL 断言） | 已落地 |
| R4 | `--dest` 默认 `~/opt` | setup_deps.sh:38、:57 | 已落地 |
| R5 | chmod 与安装后冒烟 | setup_deps.sh:115/:153、:118-121/:156-159 | 已落地（LICENSE 附带执行位见 D-5） |
| R6 | 打印 crest_root/xtb_root 设置页指引；自定义 --dest 时显式提示 | setup_deps.sh:166-173 | 已落地（真资产实跑输出核实） |
| R7 | 代理复用 update.sh 的 `GAUFORGE_PROXY`/`--proxy`/`--no-proxy`，非 install.sh 的 GAUFORGE_GH_PROXY，两变量不混用 | setup_deps.sh:17-18、:36、:39、:47-52、:74-76；对照 update.sh:5-9/18-29/40、install.sh:3-4/11 | 已落地（逐行核对：前缀改写 `${proxy%/}/` 同款、选择不持久化且头注明示与 update.sh 的差异语义；GAUFORGE_GH_PROXY 全脚本零出现）；test:490-515 锁定三通道 |
| R8 | 不随部署包分发第三方二进制 | package_release.sh 全文无第三方二进制拷贝；D5 部署包清单实测仅仓库自产文件 | 已落地 |
| R9 | 「crest 3.0.2 内嵌 tblite、运行无需 xtb」口径入脚本帮助与文档 | setup_deps.sh:4-7（--help 继承）、:160；deployment.md:106-108 | 已落地（三处一致，D3 口径复核成立） |
| R10 | 上游资产名/URL/校验和实施时实测核验，crest 无校验和→tag+体积口径 | setup_deps.sh:28-35（URL/资产名/体积 8764012）、:97-102、:140-142；附录 B D4 | 已落地且本审查独立复核一致（见五-3） |
| R11 | 安装布局与运行级 crest_root/xtb_root 默认值对齐（crest 顶层 crest/ 嵌套同名上移；xtb-dist/ → xtb-6.7.1/ 归一） | setup_deps.sh:60-63、:106-114、:146-152；web/src/config.py（crest_root=`~/opt/crest-3.0.2`、xtb_root=`~/opt/xtb-6.7.1`）；test:399-435（假资产按真实布局构造） | 已落地（真实资产端到端验证装出 `<dest>/crest-3.0.2/crest` 与 `<dest>/xtb-6.7.1/bin/xtb`，真二进制 --version 通过） |
| R12 | deployment.md「CREST/xtb 接入」节：在线/离线两路径、设置页配置、验证闭环、xtb 非运行必需 | deployment.md:104-149（§6.1/§6.2/§6.3） | **部分落地**：在线路径、设置页、验证闭环、xtb 说明均落地；离线路径布局说明失实（D-1/D-2，P1） |
| R13 | install.sh 完成提示不枚举 setup_deps.sh | install.sh:42-49（完成提示仅 g16_root 指引） | 已落地 |
| R14 | package_release.sh 根脚本清单加 setup_deps.sh；deployment.md 显式单文件纳入部署包 | package_release.sh:55-58、:59-62（install 单文件、未整目录拷 docs/references） | 已落地（既有部署包 tar 断言+包内 diff 证实，见五-4） |
| R15 | §4 测试矩阵 D 行五用例（幂等跳过/半成品重装/代理约定/--xtb 可选/布局对齐） | test_deploy_scripts.py:445-539 | 已落地（5 用例与矩阵条目一一对应，无恒真断言，见五-5） |
| R16 | §7 R-6/R-7/R-12/R-13 | R-6：脚本失败分支提示代理重试/直连/离线路径（:67-69）+ 半成品清理重装；R-7/R-12：附录 B D1/D4 留痕；R-13：D 已交付不触发 | 已落地 |
| R17 | §8 开放事项 3（上游资产与许可实测核验落附录 B） | 附录 B D4 | 已完成（本审查独立复核逐位一致） |
| R18 | §5 提交 #11–#13 单类变更与顺序 | 4eb68e9c → 2129e931 → 47e0c071 → b5dd42f5 → 22fbd736（git log --reverse 实测） | 符合 |

## 四、发现清单

| 编号 | 级别 | 分类 | 位置 | 描述 | 整改建议 |
|---|---|---|---|---|---|
| D-1 | P1 | 功能完整性（文档口径） | docs/references/deployment.md:132-133 | §6.2 离线路径 crest 布局说明失实：「tar 内为平铺文件，二进制位于 `~/opt/crest-3.0.2/crest`」。实测上游 crest-gnu-12-ubuntu-latest.tar.xz 顶层为 `crest/` 目录、二进制嵌套同名 `crest/crest`（与 D2 缺陷①、setup_deps.sh:106-114 归一逻辑、沙箱假资产布局一致）。照文档「解压到 `~/opt/crest-3.0.2/`」字面操作得到 `~/opt/crest-3.0.2/crest/` **目录**，运行级 `<crest_root>/crest` 找不到可执行文件，组合流持续 503，离线手动路径不可用。复现：`curl -fSL -o /tmp/c.tar.xz 'https://v4.gh-proxy.org/https://github.com/crest-lab/crest/releases/download/v3.0.2/crest-gnu-12-ubuntu-latest.tar.xz' && tar -tJf /tmp/c.tar.xz`（首行 `crest/`、含 `crest/crest`） | 改写为：「tar 顶层为 `crest/` 目录且与内层二进制同名（`crest/crest`），解压后须将 `crest/` 内全部内容上移至 `~/opt/crest-3.0.2/`，使二进制位于 `~/opt/crest-3.0.2/crest` 且有执行位」 |
| D-2 | P1 | 功能完整性（文档口径） | docs/references/deployment.md:134-135 | §6.2 xtb 离线说明失实：「tar 内顶层即 `xtb-6.7.1/` 目录」。实测上游 xtb-6.7.1-linux-x86_64.tar.xz 顶层唯一目录为 `xtb-dist/`（与 D2 缺陷②、setup_deps.sh:146-152 一致）。照文档「解压到 `~/opt/`」得到 `~/opt/xtb-dist/`，与 xtb_root 默认 `~/opt/xtb-6.7.1` 不符。复现：`tar -tJf <xtb tar.xz> \| awk -F/ '{print $1}' \| sort -u`（仅 `xtb-dist`） | 改写为：「tar 顶层为 `xtb-dist/` 目录，须将其内容移入/改名为 `~/opt/xtb-6.7.1/`（二进制位于 `bin/xtb`）」 |
| D-3 | P3 | 可维护性 | scripts/deploy/setup_deps.sh:53 | `--help` 以 `sed -n '2,30p'` 截取头注，第 26–30 行代码（`set -euo pipefail`、`CREST_VERSION="3.0.2"` 等赋值）被原样打进帮助输出。复现：`bash scripts/deploy/setup_deps.sh --help \| tail -6`（输出含 `set -euo pipefail` 等代码行） | 收紧为 `sed -n '2,25p'`，或以头注结束标记行界定 |
| D-4 | P3 | 逻辑与边界 | scripts/deploy/setup_deps.sh:44 | `--dest` 缺值时触发 `set -u` 裸报 `line 44: $2: unbound variable`（exit 1）；同脚本未知参数有友好提示（exit 2）。复现：`bash scripts/deploy/setup_deps.sh --dest` | 参数解析处补 `[ $# -ge 2 ]` 校验，给用法提示并 exit 2 |
| D-5 | P3 | 可维护性 | scripts/deploy/setup_deps.sh:115 | `chmod +x "$crest_dir"/*` 连带 LICENSE、LICENSE.LESSER 加执行位（真资产沙箱安装后实测 `-rwxr-xr-x`）；xtb 侧 :153 仅 `chmod bin/*` 更精确 | chmod 收窄至 crest 二进制 |
| D-6 | P3 | 安全/健壮性（注记） | scripts/deploy/setup_deps.sh:57-58、:92、:134 | `--dest` 无合理性防护（`--dest /` 亦被接受）。rm -rf 作用域已收窄至 `<dest>/crest-3.0.2`、`<dest>/xtb-6.7.1` 与 mktemp 临时区（trap 清理带 `${tmp:-}` 保护），永不作用于 dest 本身，误删面有限，属误用场景 | 可选：拒绝 `dest=/` 等退化值 |

## 五、闸门与实测记录（全部独立复跑，不引用实施者输出）

1. **定向测试**：`uv run pytest web/tests/test_deploy_scripts.py -q` →
   `11 passed in 2.66s`；`-v` 逐用例 11 PASSED（6 既有 + 5 新增 setup_deps
   用例：installs_crest_and_smokes / idempotent_smoke_skip /
   broken_install_reinstall / proxy_channel_conventions /
   xtb_optional_and_checksum），零跳过零失败。
2. **全量测试**：`uv run pytest -q` → `738 passed, 2 warnings in 110.48s`
   （零 skipped）。hq 产物核验：`target/release/hq` 在位、17,957,408 字节
   （与 D1 留痕一致）；定向 `uv run pytest web/tests/test_e2e_fake_g16.py -q`
   → `3 passed in 5.48s`——e2e 真实运行，无静默跳过、通过数无虚高。前端四闸门
   不适用（本批次零前端文件改动，git diff --stat 证实）。
3. **上游资产独立复核**（api.github.com 直连 exit 7，经 v4.gh-proxy.org 重试成功——
   代理通道本身即 R-6 预案的实证）：
   - crest v3.0.2：published 2024-08-25T20:33:24Z；`crest-gnu-12-ubuntu-latest.tar.xz`
     官方 8,764,012 字节；资产全集仅 2 个 tar.xz、**无任何 sha256/checksum 资产**
     ——「上游未发布校验和文件，按 tag+体积对照」口径成立。实下载字节数一致；
     tar 顶层 `crest/`（内含 crest/crest、LICENSE、LICENSE.LESSER）；LICENSE
     头部实测为 GNU GPL v3（与 D4 许可留痕一致）。
   - xtb v6.7.1：published 2024-07-23T20:37:54Z；`xtb-6.7.1-linux-x86_64.tar.xz`
     官方 27,128,568 字节 + 官方 `.sha256`（96 字节）；实下载 `sha256sum -c` →
     **OK**；tar 顶层唯一首段 `xtb-dist`、含 `xtb-dist/bin/xtb`。
4. **真资产端到端沙箱安装**（/tmp 隔离，用后已清理；真机 ~/opt 零接触）：
   `bash scripts/deploy/setup_deps.sh --dest /tmp/reviewD-sim-opt --xtb --proxy`
   → crest 体积对照通过（默认 8764012）→ 解压归一装出
   `/tmp/reviewD-sim-opt/crest-3.0.2/crest`（58,561,984 字节，--version 冒烟通过）
   → xtb「官方校验和通过」→ 装出 `xtb-6.7.1/bin/xtb` → 输出 crest_root/xtb_root
   指引与「自定义安装路径：请在 WebUI 设置页……」提示。**幂等复现**：前置必失败
   curl（exit 18）重跑 → 「已安装（冒烟通过），跳过」×2、exit 0、零网络请求——
   判据确为冒烟而非目录存在。
5. **打包接线（D5）**：`tar -tzf target/deploy/gauforge-deploy-v3.1.0-29-gb5dd42f5-linux-x64.tar.gz`
   命中 `gauforge/setup_deps.sh` 与 `gauforge/docs/references/deployment.md`；
   解包后与仓库 HEAD 两文件 `diff` 逐字节一致；包内 deployment.md 含「CREST/xtb
   接入」节；包内 VERSION=v3.1.0-29-gb5dd42f5。package_release.sh:55-58 根脚本
   清单含 setup_deps.sh、:61-62 显式 `install` 单文件（未整目录拷 docs/references），
   与计划 §3.5 D5 措辞一致。update.sh:75-82 补装循环为泛化遍历 `"$src"/*.sh`
   （新根脚本随包自动补装成立）、:73 `cp -a docs` 触达旧部署。
6. **治理闸门**：`uv run python scripts/validate_progress.py` → `OK`（exit 0）；
   `uv run python scripts/gen_changelog_md.py --check` → `check_changelog_md:
   OK — CHANGELOG.md 与 CHANGELOG.jsonl 一致`（exit 0）。CHANGELOG.jsonl/
   progress.json 的 scripts 条目内容与实际交付逐项相符（含布局归一、代理约定、
   校验和对照、打包接线四要点）。
7. **真机重装类步骤**（D1 真机闭环）：按任务约定不强制重复（下载部署成本高），
   采信附录 B D1 留痕，独立佐证＝全量回归 738 passed（含 e2e 3 passed）+
   脚本逻辑审读 + 真资产端到端沙箱安装；该处置已在第六节偏差对照中如实标注。

## 六、与 D1–D5 留痕的偏差对照

| 条目 | 留痕声明 | 独立复核结果 | 偏差 |
|---|---|---|---|
| D1 | 503→部署→200 闭环；hq 17,957,408 字节 | hq 字节数实测一致；闭环本身未复跑（成本，已标注采信），以全量回归+e2e+脚本实测佐证 | 无（附采信标注） |
| D2 | 缺陷①crest 顶层 `crest/` 同名嵌套、②xtb 顶层 `xtb-dist/`；幂等跳过/半成品重装/--force | 真资产实测布局**逐项一致**；幂等跳过以必失败 curl 独立复现；半成品重装由沙箱用例（本审查独立重跑通过）锁定 | 无 |
| D3 | 默认零 xtb 下载；--xtb 官方 .sha256 通过；三处口径一致 | 沙箱断言（curl 日志零 xtb URL）+ 真资产 --xtb 安装（校验和 OK）均复现；脚本头注/安装行/deployment.md §6 口径一致 | 无 |
| D4 | crest 8,764,012 字节、无上游校验和文件、GPL-3.0+LGPL 文本；xtb 27,128,568 字节、官方 .sha256 通过、LGPL-3.0 | API 与实下载逐位一致；crest 资产全集零校验和文件属实；LICENSE 头部 GPL-3.0 实测一致；xtb sha256sum -c OK | 无 |
| D5 | 部署包含 setup_deps.sh 与 docs/references/deployment.md（v3.1.0-29-gb5dd42f5） | tar -tzf 命中 + 包内与仓库 HEAD 逐字节一致 | 无 |
| —（新增） | 附录 B 未覆盖项 | **deployment.md §6.2 离线布局两处失实（D-1/D-2）**——#13 提交晚于 D2 事实落库仍沿用旧口径，属批次内交付物自身口径矛盾，留痕与事实无偏差 | 本审查新发现 |

## 七、结论

**有条件通过**：脚本、测试、打包接线、进度登记全部合格，闸门全绿；待实施者
以单类 docs 提交修正 D-1/D-2（deployment.md §6.2 两条布局说明）后，批次 D
视为收口；D-3～D-6 为 P3，不阻断，建议随下次触批顺手整改。整改后按仓库惯例
可对本报告两条 P1 做增量复核（仅须复读 §6.2 修正段并与真资产布局比对，无需
重跑全量闸门）。
