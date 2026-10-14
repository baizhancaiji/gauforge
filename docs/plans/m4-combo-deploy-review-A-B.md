# 代码审查报告：m4 插波计划批次 A（契约 diff）与批次 B（后端迁移+repo+校验服务+端点+词典扩充）独立复核

> 审查人：实现代码审查专员（独立复核，不采信实施者自述）
> 审查日期：2026-10-14 · 分支 g16-webui · 工作区干净（审查全程只读，仅报告落盘）

## 一、审查依据与范围

- **依据**：`docs/plans/m4-combo-template-deploy-plan.md`——§0.4 定案口径、§1/§1.1 现状核查、§2 WBS 批次 A/B 行与批次内子步骤、§3.1 存储与迁移、§3.2 校验矩阵（词表三 11 项 reason 全集）、§3.3 端点、§4 测试矩阵、§5 提交 #2–#6、§6 闸门清单、§7 R-1/R-2/R-3/R-5/R-11、§8 开放事项 1/2、附录 A（API 侧断言）、附录 B（AG1/B1/B2 留痕）。
- **对象**：提交区间 `b8ba4287..1be6c461`（12 个提交：1f09471b 契约 diff、cf7ac90a 进度、f6165113+0b1e9a82 迁移+repo、07da49c0+31d81483 词典扩充、cd529130+84659b68 契约补录 is_default、e8b5d4ca+14f95421 校验服务+端点、0e963732 文档回填、1be6c461 进度登记）。
- **范围证实**：`git diff --stat b8ba4287..1be6c461` 实测 23 文件 +2004/−62，与调用方指定对象文件清单一致（另含进度同步三件套、main.py/routers/__init__.py 接线、store/__init__.py 工厂注册、kb_*.md 测试夹具，均属批次 B 预期产物）；`web/src/services/workflows.py` 在该区间**零改动**（R-5 声明证实，见四-6）。
- **报告落盘**：`docs/plans/m4-combo-deploy-review-A-B.md`（调用方指定路径，落盘前确认无同名既有报告）。

## 二、总评与结论

**结论：有条件通过。**

批次 A（契约 diff）与批次 B（迁移/repo/校验服务/端点/词典扩充）的实现与计划文档逐项对照成立：四 schema 角色定案、词表三 11 项 reason、v7 迁移幂等、§3.2 校验矩阵逐 reason（含 enforce/warn 双形态与豁免语义）、词典 387 词全小写无重复码点排序、基座 97 词零丢失、§8.1 具名清单 47 项全命中、真实 KB 再生逐字节一致、R-5 组合流提交链零改动声明、全部脚本闸门与全量测试独立重跑通过。发现 **1 项 P0**（`is_default` 缺省/false 语义违反契约明文、可致全表零默认态，API 直调即触发、UI 主路径因 radio 不可取消暂不触发）、**1 项 P2**（契约再生「零 diff」闸门因时间戳头字面不可复现）、**2 项 P3 备注与 1 项 P3 备案**。

**放行条件**：① 修复 F-1（P0）并补 API 级回归断言，复审确认后方可视为批次 B 收口；② F-2/F-3/F-4 建议随整改顺带落实，不作为放行前置。

## 三、发现清单

### F-1（P0 阻断 · 逻辑与边界/功能完整性）：`is_default` 缺省/false 保存取消默认归属，违反契约明文并破坏「恒有且仅有一行默认」不变式

- **位置**：`web/src/store/combo_templates_repo.py:34-45`（`update()` 无条件写 `1 if fields["is_default"] else 0`）；`web/src/services/combo_templates.py:181`（`"is_default": bool(data.get("is_default"))`——payload 缺省即 False）。
- **违反依据**：`docs/api/openapi.yaml:998-1001` ComboTemplateUpdate.is_default 契约明文「缺省/false **不改变现有默认归属**」；计划 §3.1「is_default 恒有且仅有一行 =1（radio 语义：默认方案不可取消、只能改选）」；§3.3「is_default=true 时本条置默认并同事务清其余行」。
- **复现命令与实测输出**（临时库，`/tmp` 下一次性脚本）：

  ```
  初始默认: [1]
  对默认行自身 is_default=False 保存后: []
  全表 is_default 合计: 0
  ```

  真实 HTTP 栈二次复现（临时工作区实例 127.0.0.1:8301）：对默认行 3 `PUT /combo-templates/3 {"name":"配置3","route":"#p hf opt"}`（不携带 is_default）返回 200 后，`GET /combo-templates` 实测「默认条目: 无——全表零默认」。
- **影响**：全量替换语义下对当前默认行做一次不携带 `is_default` 的保存即丢失唯一默认；`ComboFlowDialog` 打开时「默认选中 is_default 条」（附录 A A20）在该态下无选中项。UI 主路径暂不触发（「设为默认」复选框 radio 不可取消、保存恒携带 true），但 API 直调、后续前端重构或任何非浏览器客户端均会触发。
- **测试缺口**：`web/tests/test_combo_templates.py::test_is_default_exclusive_migration`（:91-98）仅覆盖 `is_default=True` 迁移断言，未覆盖「对默认行自身缺省/false 保存」分支，缺陷因此未被测试锁定。
- **修复建议**：在 `validate_and_normalize`（或 `repo.update`）将 `is_default` 语义改为 `bool(data.get("is_default")) or 原行 is_default`（缺省/false 时保持该行原默认归属，true 时迁移并清其余——与契约「不改变现有默认归属」逐字对齐）；补 API 级断言：对默认行不带 `is_default` 保存后 `GET` 仍恰有一条默认且即该行。

### F-2（P2 建议 · 测试有效性/可维护性）：契约再生「零 diff」闸门因 datamodel-codegen 时间戳头字面不可复现

- **位置**：`web/scripts/gen_models.py`（未固定时间戳）；`web/src/models/models.py:3`。
- **复现命令**：`uv run python web/scripts/gen_models.py && cd web/frontend && npm run gen:types && git diff --stat`（任意时刻执行）。
- **实测输出**：`contract.ts` 零 diff；`models.py` 非——唯一差异为生成头注释行 `#   timestamp: 2026-10-13T17:02:32+00:00` → `2026-10-14T01:02:45+00:00`（1 insertion, 1 deletion）。契约内容实质零漂移，但 `git diff` 非空，验收标准「入库后重复再生零 diff」在任意非同步时刻字面不成立，须人工 `git checkout --` 还原。
- **修复建议**：`gen_models.py` 传入 datamodel-code-generator 的 `--output-timestamp` 固定值（或在生成后归一头注释），使再生严格字节幂等；闸门口径文档同步改为可判定表述。

### F-3（P3 备注 · 留痕精度）：附录 B AG1「md5 一致」表述与实测口径偏差

- AG1 留痕「models.py／contract.ts 重复再生零 diff（md5 一致）」——实测不同时刻再生 `models.py` 的 timestamp 头必变、md5 必不同；推测留痕时两步再生恰落于同一秒。契约实质一致性成立（本报告四-4 实测），留痕表述不精确；F-2 整改后该表述自然成立。

### F-4（P3 备注 · 留痕精度）：计划 §1.1 R-8 补录行号系基线口径、与提交后行号漂移

- R-8 补录「行号：71、273/276、696/697、1970、2518」经比对与**基线 `b8ba4287`** 的大写原文位置吻合（基线 273/276/696/697/1970 行均为 `%Chk`/`%OldChk` 形态），提交 1f09471b 后漂移至 71/283/286/706-707/2116/2664 等处。**实质完成已独立证实**：HEAD 全文件 `grep -n "%Chk\b\|%OldChk\|%NProcShared\|%Mem=\|%CPU" docs/api/openapi.yaml` 零命中（退出码 1）。建议留痕行号标注「改前行号」口径。

### F-5（P3 备案 · 安全面归因，不要求整改）：v7 迁移种子 SQL 直拼

- `web/src/store/migrations.py:168-173`：`executescript` 无法参数化，种子值（配置名/route/时间戳）均为编译期仓库常量、无用户输入注入面，`:167` 注释已归因，与 v2 先例一致；repo 层全部 SQL 参数化（`?` 占位）。仅登记备案。

## 四、闸门实测记录（全部独立重跑，不引用实施者输出）

| # | 项目 | 命令 | 实测结果 |
|---|---|---|---|
| 1 | 全量测试 | `uv run pytest -q` | **736 passed**，0 failed，0 skipped，2 warnings（starlette/anyio 弃用告警，环境噪声），118.91s。`target/release/hq` 在位（17,957,408 字节，10-12 构建）→ 无 e2e 静默跳过，通过数不虚高 |
| 2 | 进度校验 | `uv run python scripts/validate_progress.py` | `OK`，退出码 0 |
| 3 | CHANGELOG 一致性 | `uv run python scripts/gen_changelog_md.py --check` | `check_changelog_md: OK — CHANGELOG.md 与 CHANGELOG.jsonl 一致` |
| 4 | 契约三闸门 | `uv run pytest web/tests/test_openapi_ssot.py web/tests/test_error_codes.py web/tests/test_extract_keywords.py -q` | **23 passed** |
| 5 | 契约再生 | `uv run python web/scripts/gen_models.py` + `cd web/frontend && npm run gen:types` | `contract.ts` 零 diff；`models.py` 仅 timestamp 头 1 行 diff（F-2；已 `git checkout --` 还原，工作区复归干净） |
| 6 | R-5 核验 | `git diff --stat b8ba4287..1be6c461 -- web/src/services/workflows.py` | 空 diff——`save_template`/`_refine_input` 全区间零改动，组合流提交链零改动声明成立 |
| 7 | 词表三对照（AG1 复跑） | 逐 reason `grep -c <reason> docs/api/openapi.yaml` | route_must_start_with_hash 1／multi_line_route 1／blank_line_in_route 1／keyword_not_in_dict 4／temp_value_invalid 1／nproc_not_positive_int 1／mem_value_invalid 1／cpu_list_invalid 1／mem_below_per_core_floor 1／nproc_cpu_mismatch 1／link0_symbol_ref_forbidden 1——11 项逐一命中，与 AG1 留痕计数**完全一致**；`grep -n 两张` 退出码 1（零残留），「三张」在 :221 |
| 8 | 词典核验 | `wc -l` + Python 全小写/去重/码点排序脚本 | 387 词；全小写 True；无重复 True；码点排序 True；基线 97 词差集为空（零丢失）；§8.1 具名清单 27 方法+20 基组逐条命中零缺失；判据① p/b3lyp/6-31g(d)/opt/freq 全 True |
| 9 | 真实 KB 再生复现 | `uv run python scripts/extract_keywords.py --out /tmp/regen_keywords.txt` 后逐字节比对 | 「词条 387 个」；与入库 `keywords.txt` **逐字节一致**（B2 留痕独立复现成立；临时产物已清理） |

## 五、端到端冒烟记录（真实 HTTP 栈）

- **方式**：`G16WEB_HOME=/tmp/g16web-review-smoke G16WEB_ENGINE=0`（运行级 `listen_port` 预置 8301——8300 被既有进程占用，未触碰）`uv run python -m web.src.main` 拉起，实测后即停（pkill），临时目录已清理，真实工作区零污染。
- **GET /api/v1/combo-templates** → 200：5 条按 template_id 升序 `[1,2,3,4,5]`；`initial.route = "#p b3lyp/6-31g(d) opt freq"`（全小写）；默认条目 `[1]`。
- **PUT /combo-templates/3**（freq 无温度、is_default=true）→ 200：route 落库 `#p b3lyp/6-31g(d) opt freq temperature=298.15`（自动补齐）、`notice {temp_applied: true, normalized: false}`、nproc/mem_gb/cpu 回传规范字符串 `"4"/"8"/"1-4"`、默认唯一迁移至 3。
- **PUT /combo-templates/9** → 404 `NOT_FOUND`（`combo_template 9 不存在`，不泄内部路径）。
- **PUT /combo-templates/1**（`route` 含词典外 token + `nproc:"0"`）→ 422 `VALIDATION_FAILED`：`details.errors[]` **全量一次**返回 2 条（`keyword_not_in_dict` message 含 token 原文 + `nproc_not_positive_int`），结构 `{"field","line","reason","message"}`。
- **F-1 缺陷真实栈复现**：对默认行 3 不带 `is_default` 保存 → 200 后全表零默认（见三-F-1）。

## 六、逐项审查结论（对照调用方审查项）

1. **闸门独立重跑**：全部通过（见四；契约再生 timestamp 头归因 F-2）。
2. **批次 A 契约符合性**：通过。四 schema 角色定案与 §2 A 行一致（`openapi.yaml:902` ComboTemplate＝GET 条目、`:945` Response 含内联 `initial:{route}`、`:968` Update 含 `ignore_spelling?`、`:1009` MutationResult＝全字段+notice）；nproc/mem_gb/cpu 均 `string|null`（:925-936/:983-994）；notice `{temp_applied, normalized, spelling_warnings?}`（:1020-1035，warnings 元素注明「token 原文非 reason」）；`keyword_not_in_dict` 双信道注释在文件头 :86-90 与路径说明 :3089-3092；Error 计数行「三张」无「两张」残留；§1.1 #9 再生面四处小写化证实（models.py 基线 :361/:393/:663/:666 对应内容 HEAD 已 `%oldchk`/`%nprocshared` 小写，行号漂移至 :751/:754，`models.py`/`contract.ts` 大写形态零残留）。
3. **批次 B 实现符合性**：通过（除 F-1）。v7 表结构与 §3.1 逐列一致、`IF NOT EXISTS`+`INSERT OR IGNORE` 幂等（test_seed_idempotent_rerun）、种子 5 行内容与 `is_default` 仅 id=1、种子不走校验链（迁移层直插）；`COMBO_TEMPLATE_INITIAL_ROUTE = "#p b3lyp/6-31g(d) opt freq"` 全小写字面一致（`config.py:153`）；repo `get_all()` 按 id 序、`update()` 同事务清其余（`tx()` 内两语句）；`SPELLING_MODE="enforce"`（services :34）；§3.2 校验矩阵 11 reason 逐项对照实现成立——route 文法三 reason（:80-90，multi_line_route 本域新增）、`_TOKEN_SPLIT=[/\s#]+` 切分+casefold 精确白名单（:92-97）、键值形键名匹配+值非空放行（:53-60）、enforce/warn 双 mode+`ignore_spelling` 当次生效（:98-100）、freq 等值或 `freq=` 前缀检测（:103）、自动补前导空格 ` temperature=298.15`（:107）、`temp=`/`temperature=` 均算已配置（:104）、温度单值正数（:109-116）、nproc/mem/cpu 值级校验（:119-147）、mem≥核数×1.0 等值放行（:150-156）、cpu 核编号总数≥nproc 不足拦多于默许（:157-160）、`@task:`/`@exec:` route 子串+link0 经 `parse_link0_refs` 双信道拒绝（:165-174）；errors 全量一次返回（:176-177）；casefold 入库与响应回传（:179/:183）；GET 形态（router `_serialize` 规范字符串、mem 去尾零 `_num_txt`）；PUT 全量替换（缺省/空恢复初始值或置 NULL，test_clear_restores_initial_name_and_route）；404（templateId ∉ {1..5}，表内 id 固定无增删路径）；422 复用 `VALIDATION_FAILED` 零新增错误码（`errors.py:42-44`）。
4. **词典扩充**：通过。`extract_keywords.py` 四面提取与 §8.1 定案一一对应（面① manifest 基座 :79-94、面② gv6 对照表+_dft_words :97-183、面③ basissets 族+形态生成 :186-243、面④ 评估不设规则 docstring :21-23）；387 词/全小写/无重复/码点排序/基座零丢失/47 项具名清单/真实 KB 再生逐字节一致全部独立复现。
5. **逻辑边界与安全**：repo SQL 全参数化无注入面（F-5 备案除外）；templateId 越界 404；服务无状态、豁免态仅请求级不跨请求泄漏（`ignore_spelling` 为载荷布尔，词典缓存非豁免态）；R-11 并发取舍与实现一致（无乐观锁、`updated_at` 仅审计）；错误消息不泄内部路径（冒烟 404/422 响应体证实）。**例外：F-1。**
6. **测试有效性**：断言真实锁行为——逐 reason 精确断言、边界值断言（mem 等于下限放行 :265、cpu 多于默许 :275）、豁免不落库断言（:195-196）、契约 schema 断言（`assert_contract_schema`）、errors 全量断言（:289-299）、序列化往返断言（:329-341）、`_refine_input` 消费回归（:344-357）；无恒真断言；conftest autouse 隔离库（`_isolated_db`）端点测试零真实数据污染；test_put_structural_type_error_framework_422 断言与 `main.py:71-75` 处理器实际形态一致。**缺口：F-1 对应分支无断言。**

## 七、与附录 B 留痕的偏差对照

| 条目 | 留痕声明 | 独立复核结论 |
|---|---|---|
| AG1 grep 计数 | 11 项逐一命中、keyword_not_in_dict 4、「两张」零残留 | **一致**（四-7 逐位一致） |
| AG1「md5 一致」 | 重复再生零 diff（md5 一致） | **偏差**（F-3）：实测 timestamp 头致 md5 必变；契约实质一致成立 |
| B1 四项核验 | 经 MCP 检索复核通过 | 不可同径复现（审查会话无 gaussian-kb MCP）；其下游实现口径（temp/temperature 双形、freq= 前缀、温度补 298.15、nproc×cpu 方向）经代码与 HTTP 冒烟**独立验证成立** |
| B2 词典再生 | 97→387、判据①②③、全小写/去重/排序、逐字节一致、基座零丢失 | **全部一致**（四-8/9 独立复现） |
| B3 enforce 切换 | 仅 §5 #6 执行时登记 | 本波非降级交付、默认 enforce 上线（`SPELLING_MODE="enforce"` 实测），#6 未执行、B3 无条目——与计划条件提交语义一致 |

## 八、整改清单（供实施者执行）

1. **F-1（P0，放行前置）**：修正 `is_default` 缺省/false 语义为「保持原默认归属」，补 API 级断言（默认行不带 `is_default` 保存后恒有恰一条默认且即该行），复审确认。
2. **F-2（P2，建议）**：`gen_models.py` 固定 timestamp 使再生字节幂等，闸门口径同步修订。
3. **F-3/F-4（P3，建议）**：AG1「md5 一致」与 R-8 行号口径在计划文档随下次文档批次补注说明。
4. F-5 备案不要求整改。
