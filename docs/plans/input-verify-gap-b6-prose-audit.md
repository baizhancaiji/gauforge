# B6 G10-b 面⑤散文提及选项三路互补差集近似全量审计留痕

> 批次：输入勘误缺口补齐计划 B6（§2.13 G10-b，决策点 13）。
> 审计日期：2026-10-20。知识库：gaussian-kb 结构化数据（与
> gaussian-kb MCP 同源同数）；语料：`~/g16/tests/com`（回归对照样本，
> 决策点 11 非权威）。复核产物全部落盘 `docs/plans/audit/`。

## 1. 审计方法（三路差集互补，§2.13 方案 2）

工具：`scripts/audit_prose_options.py`（入库、幂等、输出路径参数化）。

| 路 | 覆盖面 | 差集形态数 |
|---|---|---|
| ① 字面 `键=选项` | 全分类页面（不限 keyword 页），键限已知 route 关键字面，跨页链接文本保留（键归属链接载体） | 79 |
| ② 散文裸词归属推断 | keyword 页 Options 章节 #### 选项条目正文中的大写裸词（「与页主题近邻」收窄；markdown 链接剥离——链接文本多为他页选项引用，其键归属属链接载体、由路①承接） | 1306 |
| ③ 语料命中形态 | `~/g16/tests/com` route 节 `key=opt` 形态全集反查 | 96 |

合并去重 1435 形态 → 两层过滤得复核面 **475 形态**（B6 审查整改 R1 起
两层均已脚本化入库 `scripts/audit_prose_options.py`；本节按整改后口径
原位勘误——原文「以现行 G8 判定链（check_route_options）重过滤」只覆盖
warn 层，1262→475 的 review 层谓词当时未留痕，独立审查（§9）实测不可复现）：

- **warn 层**：G8 判定链复过滤 → 实际产生 `route_option_unknown` 的
  **1262 形态**（唯一前缀判活、键无选项集、值形白名单等链上判活者零
  警告消除，如 `freq=numer`、`geom=connect`、`td=singlet` 不入下游）；
- **review 层**：warn 形态中，非 P2-only（有字面「键=选项」或语料命中
  证据）直接保留；P2-only 形态宿主条目抓取上下文含选项语义词根
  （synonym / says to / default / option / keyword 五词根，snippet
  拼接 casefold 子串）者保留 → **475 形态**（= 有字面/语料证据 74 +
  散文词根锚 401）；其余 **787 形态**为纯散文普通词提及，按机械规则
  归因排除 → `audit/excluded_candidates.json`。

漏斗闭合：1435 = 1262（warn）+ 173（判定链判活零警告）；1262 = 475
（review）+ 787（归因排除）。两层谓词与 B6 历史产物的等价性由 B5 时点
worktree 复现程序证实（六份 JSON 逐字节一致，程序见 §9）。

覆盖边界（表述精确化，审查 R8）：路②收窄为 keyword 页 Options 章节
#### 条目正文（计划 §2.13「与页主题近邻」口径），Options 章节之外的
散文裸词提及与非 keyword 页散文（除字面 `键=选项` 形态外）不在任何
一路覆盖面内——「全量」的精确含义是**三路互补的近似全量**；已确认的
两 B 类形态（addredundant/nnroa）均落在 Options 条目正文内，后续如
出现该覆盖面外的误报样例再议扩面。

复核面再按句锚点分层（synonym / says-to / default 句式与「其他」），
逐条对照手册原文裁决，产出 `audit/review_decisions.txt`（475 行逐条
处置 + 依据）。复核过程中对全部 57 个宿主键逐键核对 keyword 页原文
（Options 章节条目清单、synonym/No-对/枚举句、Section Ordering 字面）。

## 2. 裁决总览

| 处置 | 条数 | 说明 |
|---|---|---|
| admit_rule（面⑦句式规则入典） | 89 | synonym / says-to / default 三类官方句式直述，由 `extract_keywords.py` 面⑦规则机械提取 |
| admit_manual（手工补录入典） | 65 | 复核通过、句式覆盖不足（官方枚举句、Section Ordering 字面、No-对行为句、deprecated synonyms 等），入 `extract_keywords.py` 的 `B6_MANUAL_OPTIONS` 常量清单 |
| admit_impl（判定链实现侧） | 4 | `field=z-100/y-50/z+100/xxyz-20` 场向量取值——值面非选项面，`field` 键入 `_VALUE_FORM_HEADS` 值形白名单（与 iop/oniom/external 同构，宁漏勿误） |
| reject_a（A 类旧形态） | 37 | G03 时代形态，现行手册已删（决策点 11）：`geom=modela`（193 语料文件）、`scf=novaracc/noincore`、`scrf=dpcm/oldpcm/numer`、`units=bohr`、`transformation=*`（obsolete 页字面）、`ept=d2`、`freq=hindrot/davidson`、`pseudo=mmread`、`ccsd=fc1`、`opt=fp/gdiis/ms/…`（obsolete 页）、`stable=symm` 等——维持预期警告 |
| reject_noise（散文噪声） | 280 | 句首动词（Specifies/Requests/Sets…）、方法名（DFT/MP2/CIS/SCF/UHF…）、单位（Hartree/Bohr/Angstroms）、键自身名、引文锚（Helgaker94 型）、跨页链接载体错位、值形参数（NState=Read 之 Read）、ModRedundant 语法描述词——不入典，维持 warn 级固有边界 |

立项背景两确认形态复核结论与计划一致：`opt=addredundant`（opt.md
ModRedundant 条目「AddRedundant is synonymous with ModRedundant」）、
`freq=nnroa`（freq.md ROA 条目「NNROA says to use the numerical ROA
method from Gaussian 03」）——均三路命中，面⑦ says-to/synonym 句式
提取入典，零警告复测通过。

## 3. 入典结果

- 词典规模：1166 → **1345**（+179；面⑦规则在全部 keyword 页的完整
  提取集大于复核面 475 样本，如 `scf=fsymm/vtl`、`semiempirical=chk`、
  `scrf=isodensity/readq/writeq/sc`、`freq=fc/ht`、`oniom=noembedcharge`
  等复核面外官方句式形态一并入典）。
- 常量规模口径（审查 R2 补记）：`B6_MANUAL_OPTIONS` 实际 **76 条** =
  复核面内 admit_manual 裁决 65 + 复核面外核对直入 11
  （`bomd=gradonly/local`、`cas=nocpmcscf/nofulldiag`、
  `freq=readhindered`、`population=savecm5/savenpa`、
  `sacci=quintet/sextet/septet`、`output=spinrotation`；末条在 B5 词典
  已存在、属冗余补录，无害）。
- 重生成幂等：连续两次运行逐字节一致；真实 gaussian-kb 在机、无 skip。
- 规模断言三处同步（test_extract_keywords 两处 + test_combo_templates
  `test_spelling_words_loaded_and_gate_ready`）。
- 面⑦规则防噪三道闸：Options 章节限定（两级章节名含 option）、主语
  停用词表（代词/句首动词/方法名/单位/Link 词）、特例停用（RdFreq 载体
  属 CPHF——polar 页「CPHF=RdFreq is the default」跨键载体错位；
  yes/never 为 ReCorrect 参数取值）。复核甄别剔除两例错误提取：
  `polar=rdfreq`（载体错位）、`irc=yes`（值形参数），均经原文核实。
- 甄别保留争议例：`transformation=abcd`（transformation.md「ABCD is a
  synonym for Full」官方句面实锤）、`population=no/noa/savento`（各为
  官方 synonym 句主语）、`cas=lanczos`（「Lanczos is the default when
  there are 8 or fewer」官方行为句）。

## 4. 闭环验证

- `audit/make_decisions.py` 以重生成后词典重跑判定链：admit 类 158 条
  （89+65+4）全部零警告；reject 类 317 条仍产生警告（A 类 37 为决策点
  11 预期行为，噪声 280 为 G8 warn 级固有边界——正文裸词≠官方选项，
  宁漏勿误反向的已知残余）。
- 回归用例：`test_parse_blocks.py` 增三用例（`test_g10b_prose_option_
  shapes_zero_warnings` B 类零警告复测、`test_g10b_field_value_form_
  whitelist` field 白名单、`test_g10b_a_class_shapes_still_warn` A 类
  维持预期警告），先行红（field 白名单 1 失败）→ 实现后全绿
  （过程性陈述，git 同提交交付不可证——审查 R4 登记，后续批次恢复
  「契约先行 → 测试先行 → 实现」独立提交粒度）。
- `keywords.py` `_PAREN_TAIL` 条注释按 A 类口径修正（td=window 系
  G03 时代选项，G16 手册 TD/CIS 页均无 Window，警告为预期行为——
  修正原「B 类面⑤覆盖缺口，登记另批扩面」的错误登记）。
- `workspace.py` 模块头 docstring 旧单位口径残留（W/MW/QW）顺带修正
  为官方单位集（KB/MB/GB/TB/KW/MW/GW/TW）。

## 5. `opt==calcfc` 畸形 token 评估（§2.13 方案 3 顺带项）

G10-b 实施时评估：双等号 token 经 tokenize_route 的裸 = 粘合后为
`opt==calcfc`，`_split_key_options` 取 `=` 首段键名得 `opt`（带尾 =）→
rstrip 后键在典；值段 `=calcfc` 剥值后基名 `=calcfc` 非官方选项——
拆解层可报，但与 `opt=(xyzzy)` 类未知选项警告相比无增量信息（键已
被拼写/选项通道覆盖、形态为罕见畸形输入）。维持 §2.12 登记不变
（宁漏勿误，不单独立项），登记关闭。

## 6. 文件清单

| 文件 | 性质 |
|---|---|
| `scripts/audit_prose_options.py` | 审计工具（入库、幂等） |
| `docs/plans/audit/path1_literal.json` / `path2_prose.json` / `path3_corpus.json` / `merged_candidates.json` / `warn_candidates.json` / `review_candidates.json` | 三路差集与复核面原始数据 |
| `docs/plans/audit/excluded_candidates.json` | review 层归因排除集（787 形态，机械归因随条目落盘；审查整改 R1 补齐） |
| `docs/plans/audit/review_flat.txt` / `review_detail.txt` | 复核输入扁平清单（475 条带 snippet/判定链细节） |
| `docs/plans/audit/review_decisions.txt` | 逐条裁决明细（475 行：形态/来源/处置/依据） |
| `docs/plans/audit/make_decisions.py` | 裁决明细生成与闭环验证脚本 |
| `docs/plans/audit/corpus_baseline_b6.json` | 语料基线复跑结果（B6 口径） |
| `scripts/extract_keywords.py` | 面⑦句式规则 + `B6_MANUAL_OPTIONS` 手工补录 |
| `web/src/parse/keywords.txt` | 词典重生成（1166→1345） |

行数口径（审查 R7 补记）：`review_flat.txt` 实测 **511 行** = 475 形态
条目行 + 22 行同形态多上下文重复 + 14 行多行 snippet 续行碎片（空串、
`##`、散文片段等解析残片，非形态）；唯一形态 489 = 复核面 475 + 14
碎片。`review_detail.txt` 475 行与复核面一一对应。

## 7. 语料基线复跑（回归对照，决策点 11 非权威）

harness 口径按 §5（不拒文件、逐文件 parse_input、route 全集
file_warnings）。B6 词典（1345）与 B5 词典（HEAD 1166）同 harness 对比：

| 指标 | B5 词典 | B6 词典 |
|---|---|---|
| route_option_unknown 命中文件 | 417（1.5%…36%） | **394** |
| 条数 | 498 | **469** |
| 键@形态 | 66 | **55** |

- 消除 12 形态：`addredund(ant)`、`nnroa`、`emass=1000/-1000`、`savenm`、
  `selectnm`、`rdopt`、`vtight`、`nostatic`、`nofulldiag`、`gradientonly`
  ——全部为 B6 入典生效。
- **新增 1 形态 `readanh`**：`freq=readanharmonic` 入典后与面⑤既有
  `readanharm` 并存，`readanh` 缩写在键内歧义、唯一前缀判活失效。
  **G16 Rev. C.01 实测拒绝该形态**（t6：`End of line while reading
  DiNa input`，L717）——歧义翻转警告**正确**，不构成误报（同 §2.9
  歧义前缀口径；本批验收红线「不得含唯一前缀歧义翻转型新增误报」
  经 G16 实测裁决安全）。
- 残余警告主体仍为 A 类（`geom=modela` 265、`scf=novaracc` 43、
  `scf=noincore` 20、`units=bohr` 14、`cphf=ultrafine` 14 等，决策点 11
  预期行为）。语料 sha256 清单随 git 提交（corpus_baseline_b6.json）。

## 8. G16 Rev. C.01 冒烟（B6 出口，临时目录 /tmp/g16-smoke-b6）

| 例 | route 变体 | G16 实测 | B6 判定 | 结论 |
|---|---|---|---|---|
| t1 | `opt=addredundant` | Normal termination | 零警告（面⑦ synonym 入典） | ✓ 零误报 |
| t2 | `freq=nnroa` | Normal termination | 零警告（面⑦ says-to 入典） | ✓ 零误报 |
| t3 | `prop=wrf` | **QPErr syntax error 拒绝** | A 类（官方表未列） | ✓ 决策点 9 裁决输入：**删除 COMPAT_EXTRA_KEYWORDS**（G16 自身不接受，无兼容价值） |
| t4 | `freq=numer` | Normal termination | 零警告（唯一前缀判活） | ✓ 缩写判活正例背书 |
| t5 | `scf=conv` | Normal termination（接受） | 警告（键内歧义口径） | ⚠ **推翻 B5「G16 拒绝」推断**（B5 未设冒烟节点，系 opt 页 Conven/Conv 例的错误移植）——警告为词典口径保守残余，随批修正 §2.9/测试登记，警告行为不变 |
| t6 | `freq=readanh` | L717 拒绝（DiNa input EOF） | 警告（readanharm/readanharmonic 歧义） | ✓ 歧义警告正确 |
| t7 | `units=bohr` | Normal termination（接受） | A 类预期警告 | ✓ 审查 R9 补测：警告系词典保守残余，决策点 11 口径自洽 |
| t8 | `td=window` | **QPErr syntax error 拒绝**（l1.exe Error termination） | A 类预期警告 | ✓ 审查 R9 补测：G16 自身拒绝，警告正确 |

gjf sha256 前缀：t1=f2b5b9ec、t2=fa2fde79、t3=5a99e5aa、t4=07b45ef1、
t5=eefe72bd、t6=ca95347a、t7=7849a73e、t8=8df56ee1（t7/t8 为审查整改
R9 补测，水分子 STO-3G 浮点坐标）。

`prop=wrf` 删除的附带行为：`prop=wrf` 文件不再触发官方附加节识别
（该形态 G16 必然拒绝，无识别价值）；`route_option_unknown` 警告照发
（A 类口径）。COMPAT_EXTRA_KEYWORDS 常量与 §2.12 兼容项登记一并关闭。

## 9. 独立审查与整改留痕（2026-10-20）

code-reviewer 子代理按 AGENTS §6.2 对 B6 区间（`9bc3a456..f6129cef`）
做第二层独立复核，报告落盘
`docs/plans/input-verify-gap-b6-code-review.md`，总体结论**有条件通过**
（闸门全绿、指标逐位复现、G16 冒烟独立复跑 5 例；通过条件 R1，P3
R2–R9 随批处置）。本节登记整改落点，全部结论有可复现命令背书。

### 9.1 R1（P2）：warn→review 过渡层脚本化复原并逐字节证实

- **谓词复原**（数据反推，独立审查证伪原文「判定链重过滤得 475」）：
  review 层 = 非 P2-only（字面/语料证据）∨ P2-only 宿主条目 snippet 含
  选项语义词根（synonym/says to/default/option/keyword）。对 1188 个
  P2-only 形态精确分割：保留 401/401、误排 0/787。
- **脚本化**：`scripts/audit_prose_options.py` 增 `warn_layer` /
  `review_layer` 两函数与三份产物（warn/review/excluded_candidates.json），
  谓词常量与排除归因随条目落盘；单测
  `web/tests/test_audit_prose_options.py` 六例（先行红 → 实现后绿）。
- **复现程序**（warn 层谓词依赖判定链代码版本与词典快照对应，须在
  B5 时点代码复现历史产物）：
  ```bash
  git worktree add /tmp/b6repro 31a2cb60        # B5 判定链 + B5 词典(1166)
  cp scripts/audit_prose_options.py /tmp/b6repro/scripts/
  (cd /tmp/b6repro && .venv/bin/python scripts/audit_prose_options.py \
     --out-dir /tmp/b6out)                      # 79/1306/96/1435/1262/475/787
  cmp /tmp/b6out/<七产物> docs/plans/audit/     # 六份历史产物逐字节一致
  git worktree remove --force /tmp/b6repro
  ```
  实测：path1/2/3、merged、warn、review 六份 JSON 与入库产物**逐字节
  一致**；`make_decisions.py` 重跑裁决分布 4/65/89/37/280 不变、
  review_decisions.txt 零变化（幂等）。`excluded_candidates.json`
  （787 条归因排除）为整改新增产物入库。
- 历史复核面与复现面集合全等（475），文件顺序唯一差异（第 73/74 条
  边界）系历史生成「先证据形态、后锚点形态」两段拼接所致，已作为
  review 层输出结构固化。

### 9.2 P3 项处置

| 编号 | 处置 |
|---|---|
| R2 | §3 补记常量 76 = 复核面 65 + 复核面外 11（机械核验一致，含 1 条 B5 冗余无害） |
| R3 | 批次序列勘误：G10-a（f6129cef）实为批次最后一个提交（22:01），晚于收口登记（21:58），与开工登记「先行独立提交」序列不符——最终状态正确、同批完成，此处留痕为准 |
| R4 | §4 先行红主张标注「过程性陈述，git 不可证」；本整改批恢复测试先行独立提交 |
| R5 | 本整改批提交 summary 一律中文动词开头 |
| R6 | B7 实施者知悉：G11 三用例中先行红实为 2 例（`test_g11_charge_line_inline_comment`、`test_g11_comment_cut_quote_aware`），第三例为回归守卫（实现后应保持绿，不必期待先红） |
| R7 | §6 补记 review_flat.txt 行数口径（511 = 475 条目 + 22 多上下文 + 14 续行碎片） |
| R8 | 标题与 §1 「全量」表述收敛为「三路互补近似全量」，覆盖边界登记 |
| R9 | §8 补 t7（units=bohr 接受）/ t8（td=window QPErr 拒绝）实测行 |

### 9.3 L1：playwright 独立视觉复测（审查限制项闭合）

隔离实例（`G16WEB_HOME=/tmp/g16web-l1 G16WEB_ENGINE=0`、127.0.0.1:8399，
health 版本 `v3.3.0-65-gf6129cef` 即审查 HEAD；前端 `npm run build`
重构建后拉起；用后实例与临时工作区已清理）：

| 场景 | 操作 | 实测 |
|---|---|---|
| 豁免按钮移除 | 打开设置 → 组合流模板弹窗 | 仅「关闭」「保存」两键，**无「忽略拼写警告并保存」** |
| 拼写偏差放行 + 琥珀警告 | route 改 `#p fre geo`，保存 | PUT `/api/v1/combo-templates/1` **200**，弹窗展示琥珀警告「词典外关键词（已放行）：fre、geo」（`.ct-warn`，var(--warn)） |
| 硬错误仍阻断 | %mem 填 0，保存 | %mem 输入框**红描边** + 红色横幅「%mem 须为正数（GB 数值）」，PUT **422** |

截图留档 /tmp（未入库）；审查报告 §五.3 的静态证据（源码与重构建
dist 零残留、三道前端闸门绿）与本次视觉实测合并构成 L1 完整闭环。
