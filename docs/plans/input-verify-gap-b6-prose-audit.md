# B6 G10-b 面⑤散文提及选项三路差集全量审计留痕

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

合并去重 1435 形态 → **以现行 G8 判定链（check_route_options）重过滤**
→ 实际产生 `route_option_unknown` 的复核面 **475 形态**（唯一前缀判活、
键无选项集、斜杠粘连等假阳性已在过滤层消除，如 `freq=numer`、
`geom=connect`、`td=singlet` 判活零警告不入复核面）。

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
  维持预期警告），先行红（field 白名单 1 失败）→ 实现后全绿。
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
| `docs/plans/audit/review_flat.txt` / `review_detail.txt` | 复核输入扁平清单（475 条带 snippet/判定链细节） |
| `docs/plans/audit/review_decisions.txt` | 逐条裁决明细（475 行：形态/来源/处置/依据） |
| `docs/plans/audit/make_decisions.py` | 裁决明细生成与闭环验证脚本 |
| `docs/plans/audit/corpus_baseline_b6.json` | 语料基线复跑结果（B6 口径） |
| `scripts/extract_keywords.py` | 面⑦句式规则 + `B6_MANUAL_OPTIONS` 手工补录 |
| `web/src/parse/keywords.txt` | 词典重生成（1166→1345） |

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

gjf sha256 前缀：t1=f2b5b9ec、t2=fa2fde79、t3=5a99e5aa、t4=07b45ef1、
t5=eefe72bd、t6=ca95347a。

`prop=wrf` 删除的附带行为：`prop=wrf` 文件不再触发官方附加节识别
（该形态 G16 必然拒绝，无识别价值）；`route_option_unknown` 警告照发
（A 类口径）。COMPAT_EXTRA_KEYWORDS 常量与 §2.12 兼容项登记一并关闭。
