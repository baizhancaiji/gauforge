# 队列接续 chk 物化失败修复 · 实施计划（目标 3.5.0）

> 状态：**已实施并验收（3.5.0）**
> 验收留痕：T0–T7 八提交（08539289 / c9cc62c1 / 9924de7f / 51929afb /
> 5b547db2 / 19b75bca / 35afd852 / 本进度同步提交）——T3 红集合 19 先证红
> 入库、T4 保持红证等价、T5 全数转绿全量 892 passed（committer 独立复跑）；
> T6 前端四闸门（build / audit_frontend_offline / check_tokens /
> check_contrast）全过，playwright 浏览器视觉实测九项通过（拖宽 2× 增量
> 全程居中、键盘步进、刷新保持、长名随加宽增长、收窄钳制零溢出、其余
> 模态零变化、控制台零错误，量测与截图留痕 /tmp/g16-t6-walkthrough/）；
> §4 验收判据 1–7 逐项达成。发布版本随 unreleased 冻结定为 3.5.0（含
> added 判 minor）。
> 排期口径：单人实施，任务粒度=一个可审查提交；规模标记 S（≤半天）。
> 行号锚点为计划落盘时点实际行号，实施会使其漂移，以符号名为准。
> 执行纪律：文档三提交（本计划 / m4-plan 勘误 / openapi 契约注释分提）→
> 测试先行红入库 → 实现两提交（重构与行为修复分提）→ 前端修订 → 进度同步，
> 共八提交；每提交单类变更（AGENTS §5.1）。

## 1. 缺陷分析

### 1.1 现象与失败链路

客户端症状（3.4.1，真实 G16 环境）：前置任务 succeeded → 下游成员「立即」
failed（cause=`program_error`，前端渲染「程序错误」）→ 下游
`run/<eid>/` 仅含 `input.gjf`（首行仍为 `%OldChk=@task:N` 符号形式）。

失败链路（`web/src/engine/dispatcher.py:434` 起）：

```
依赖守卫放行（上游 exs[-1]=succeeded）
→ workspace.materialize() 先写 run/<下游eid>/input.gjf（符号形式）   ← run 目录里只有它
→ materialize_chk() → resolve_upstream_chk() 定位 run/<上游eid>/input.chk
→ 真实产物名由上游输入 %chk= 行决定（如 opt.chk）→ input.chk 不存在
→ MaterializeError「chk 已被清理」→ 成员落终态 failed/program_error
→ 不提交 HQ（所以「立即失败」，无 g16 输出文件）
```

### 1.2 根因：chk 资产定位写死 `input.chk`，与真实 G16 命名规则不符

真实规则（`finalize.resolve_chk`，web/src/engine/finalize.py:76-97，M1 时期
实测定稿）：chk 文件名 = 实际执行副本 `run/<eid>/input.gjf` 中 Link0 `%chk=`
行的声明值——相对值相对 run 目录解析、无扩展名自动追加 `.chk`（g16 手册规则）、
绝对路径按原样；**无 `%chk` 行时 g16 不产任何 chk**（finalize.py:6 注释实测结论）。

三处消费点写死 `run/<eid>/input.chk`，未复用上述规则：

| # | 位置 | 现状 | 后果 |
|---|---|---|---|
| ① | `web/src/engine/materialize.py:89`（`resolve_upstream_chk`） | 溯源恒取 `input.chk` | **本次报障点**：上游 `%chk=opt.chk` → 物化必败；上游无 `%chk` 行（无产物）同样必败 |
| ② | `web/src/services/dependencies.py:105`（`execution_chk_asset` 回落） | `protected/` 之外的回落只看 `input.chk` | `@exec:` 断点续跑同缺陷：自定义名 chk 明明在保留期却判「无 chk 资产」 |
| ③ | `web/src/services/dependencies.py:266`（`validate_queue_members` ⑥） | 溯源存在性只查 `input.chk` | 提交时把「chk 在保留期但叫别的名」误拒为 `CHK_SOURCE_MISSING`（反向缺陷） |

真实环境下仅当上游显式声明 `%chk=input.chk`（或无扩展名的 `%chk=input`，
按 g16 规则自动追加 `.chk` 后指向同一文件）时链路才通——这既非链式输入的
常规写法（常规约定即用户所述：后续任务读前置任务的同名 chk，名字由前置的
`%chk=` 行决定），也无任何校验或文档提示该隐性要求。

**文档源头**：m4-plan.md §2.1「chk 溯源」把来源具体化为「X 最近一次成功
（succeeded）执行的 `run/<eid>/input.chk`」——「最近一次成功执行的 chk」
这一定稿语义正确，错在把「chk」具体化成了固定文件名。同源表述共八处：
依赖面段落（:97「成功执行保留期内的 run/<eid>/input.chk（链式物化溯源目标）」）、
物化语义条（:194「本任务自身 `%Chk` 保持默认 `input.chk`」）、§2.1「chk 溯源」
条（:196-198）、续跑探针取数（:289-291）、续跑注入矩阵（:319「本任务 chk 为
新 input.chk」）、B9 §4.6 ③ 取数路径（:720-721）、test_resume 覆盖表（:818）、
B7 §4.6 依赖链验收断言（:930「上游 run/<opt执行id>/input.chk 原件哈希前后
一致」）。本计划随实施对这八处做勘误注记：「chk 溯源」条除口径注记外另附
§2.2 声明前置的语义注记（无声明即拒、不再以「尚无成功执行属正常」无条件
放行），其余七处语义不变、落地为「按实际执行副本 `%chk` 声明定位」。

架构面澄清（**不改动**）：「复制到下游目录并改写引用」与「拷入后统一命名
`dep-<taskid>.chk`」均为正确设计——前者解耦两执行的生命周期：g16 启动会
重写 `%chk` 目标，就地引用会把下游写入带到上游原件（roadmap §8.6 教训）；
复制后上游目录清理/重跑也不波及在跑下游。后者防 `%OldChk` 原生「复制为
本 step chk」语义下的同名互覆，并让依赖文件在目录内可辨识（重入对账、
清理边界按 `dep-*`/顶层 `.chk` 区分）。坏的只是「找源」一步。

### 1.3 复现证据（2026-11-11 本地）

模拟真实 g16 产物命名的复现脚本（临时产物，不入库；随 T3 固化为红测试）：

- 上游输入 `%chk=opt.chk`、succeeded 执行目录含 `opt.chk`+`input.log`：
  下游 `state=failed, cause=program_error`，run 目录 `['input.gjf']`，
  input.gjf 首行仍为 `%OldChk=@task:1`，HQ 提交数 0，stderr 打出
  `[materialize] 执行 2 物化失败：上游任务 1 最近成功执行（#1）的 chk 已被清理…`
  ——与客户端症状逐项一致；
- 对照组：上游产物恰为 `input.chk` → 物化正常（`dep-1.chk` 拷入、输入重写
  为 `%oldchk=dep-1.chk`、正常提交 HQ）。

客户端可独立佐证（无需本地环境）：失败执行目录 `input.gjf` 首行仍为
`@task:` 符号行；服务 stderr 日志含同款 `[materialize]` 行。

### 1.4 为什么既有测试没拦住

- `web/tests/fake_g16.py` 从不产任何 chk 文件——「上游真实产出 → 下游物化」
  半段闭环在 e2e 层零覆盖；
- 单测 `_succeed_with_chk`（`web/tests/test_materialize.py:53-66`）与
  哈希跳过溯源用例的资产构造（`web/tests/test_dispatch_deps.py:63-73`
  的 `_succeed`，:70 手工放置）均把 chk 资产**手工放置**为 `input.chk`，
  resume 用例资产走 `protected/` 保全路径、
  源执行输入声明 `%chk=own.chk`——固定名假设从未被质疑（m4-acceptance.md
  验收断言同样以 `input.chk` 为源）。

### 1.5 与近期发布的关系（非回归核查结论）

3.4.1 仅含 parse 词典扩面；3.2.0–3.4.0 间物化链路相关变更逐一核查：
`67a9f883`（Link0 补全收窄，3.4.0）只影响 `resolve_link0` 注入判定与
input_hash 匹配，不匹配时安全回落最近成功执行，不影响物化成败；
`b953de99`（注入行小写形态，3.2.0）仅改注入行文本。**本缺陷为 3.1.0
功能上线时的固有缺陷**，真实 G16 环境首次使用即暴露，与 3.4.1 部署无因果。

## 2. 修复方案

### 2.1 chk 资产定位统一到 `workspace.resolve_chk`（单一事实来源）

**步骤一（T4）：下沉并拆纯函数（`web/src/engine/workspace.py`）**

1. 模块头新增 `import re`（现仅 hashlib/os/Path——顶层零项目依赖，无循环
   导入风险）；新增模块级正则 `_CHK_RE = re.compile(r"^%chk\s*=\s*(.+)$",
   re.IGNORECASE)`，自 `finalize.py:30` 原样迁移。
2. 新增纯函数 `parse_chk_line(text: str, *, link0_only: bool = False)
   -> Path | None`：实现取现 `finalize.py:89-96` 逐行匹配段等价迁移——
   逐行 strip 后匹配 `_CHK_RE`，取首个命中；声明值 strip 并剥首尾引号、
   `Path` 化（无扩展名追加与 run 目录拼接均不在本函数：前者由
   `resolve_chk` 拼接后按现状同序执行，后者为 `resolve_chk` 职责）。
   无声明返回 None——T4 落与现状等价的两形态（`%chk` 行不存在、
   `%chk=` 空值：正则 `(.+)` 不匹配空）；剥引号后为空的显式判空
   （`%chk=""` → None，消除 `Path("")` 透传）为 T5 行为修复内容
   （第 3 条、步骤三第 5 条），T4 该形态透传 `Path("")`、经
   `resolve_chk` 维持现状 `<执行id>.chk` 派生路径。符号值
   （`@task:`/`@exec:`）返回非 None 的 Path（仅作「已声明」判据与
   物化定位输入，不作为真实产物路径使用）。
   `link0_only=False`（默认）全文逐行匹配，与迁移前口径一致，供
   `resolve_chk` 作 find-source 超集扫描；`link0_only=True` 仅扫 Link0 区，
   范围判定与 `resolve_link0` 同规则（经第 4 条共享扫描函数，防口径
   漂移），供 §2.2 校验、物化文案判定与 fake_g16 对齐 G16 只识别
   Link0 命令的行为。单步输入下取首个命中即 finalize 现行口径；多步
   放行（link1 B4）时 `resolve_chk` 改按末个声明 `%chk` 的段定位，
   本函数与 §2.2 校验须同步改为末个声明段口径——任一段含声明即视为
   已声明、按最后一个声明段取值，全部段未声明才回落 `input.chk`
   （与 link1 B12「末段未声明回落前一个声明段」统一表述，T1 link1
   补注同此口径）。
3. `resolve_chk(run_dir)` 改写为薄封装，对外签名不变，T4 全量行为
   等价（含空值引号形态）：读 `run_dir/"input.gjf"`（utf-8、
   errors=replace）→ 读取 OSError 或 `parse_chk_line` 为 None → 回落
   `run_dir/"input.chk"`；否则与现状同序——非绝对声明拼 `run_dir` 后
   无扩展名追加 `.chk`（绝对声明无扩展名同样追加，g16 手册规则）。
   `%chk=""` 空值引号形态现状经 `Path("")` 派生出 run 目录旁
   `<执行id>.chk` 的错误路径（非真实产物，实测核验），T5 随
   `parse_chk_line` 判空增补改判无声明回落 `input.chk`——属行为修复，
   随 T5 提交（`fix(web)`）并在提交说明注明，不混入 T4 等价迁移
   （AGENTS §5.1 重构与功能分提）；裸 `%chk=` 现状正则不匹配、已按
   无声明回落，行为不变。
4. 提取共享 Link0 区段扫描 `_link0_span(text: str) -> tuple[int, int]`
   （返回 `[start, end)` 行区间；CRLF 归一后跳过前导空行/`!` 注释行、
   收连续 `%` 行——workspace.py `resolve_link0` 既有内联扫描原样迁移）：
   `resolve_link0` 与 `parse_chk_line(link0_only=True)` 改用之；
   `services/dependencies.parse_link0_refs`（dependencies.py:52-57 内联
   扫描，同规则第三拷贝）函数体内延迟导入改用之（防环先例同步骤三
   第 2 条）——三处 Link0 区段扫描口径收敛单一来源。纯等价迁移，
   不改任何判定行为。
5. 等价性验收锚点：`test_finalize_pipeline.py` 的 resolve_chk 四用例
   （相对 run 目录与大小写 :60、绝对路径与引号 :66、无声明回落 :74、
   无扩展名追加 :82）于 T4 提交时全绿；另补 `parse_chk_line` 的
   `%chk=` 空值返回 None、`link0_only=True` 忽略附加节 `%chk` 声明
   （同一文本默认模式仍返回该声明）的单测，`_link0_span` 提取以
   `resolve_link0` 与 `parse_link0_refs` 既有用例全绿为等价锚点，
   随 T4 同提交；`%chk=""` 两断言（`parse_chk_line` 返回 None、
   `resolve_chk` 回落 `input.chk`——现状为 `Path("")` 派生的
   `<执行id>.chk` 错误路径）随 T5 修复提交补入并转绿。

**步骤二（T4）：finalize.py 别名保留**

1. 删除 `finalize.py:30` `_CHK_RE` 与 :76-97 `resolve_chk` 定义，模块头
   改 `from .workspace import resolve_chk`（模块级名字保留）；`import re`
   （:22）随之移除——全文件仅 `_CHK_RE` 一处 re 使用（grep 已核实）。
2. 既有调用方清单（T4 提交全绿基线；不含经 dispatcher 终态钩子的
   间接调用面，后者由全量 pytest 覆盖）：生产 1 处——`make_fchk`
   （finalize.py:106）；`test_finalize_pipeline.py` 显式调用
   `resolve_chk` 四用例（:60/:66/:74/:82）、经 `make_fchk` 直接依赖
   三用例（:95/:106/:115）、经 dispatcher 成功终态间接依赖两用例
   （:282/:316；:297 为 failed 分支，只走 `protect_transient`，不调用
   `make_fchk`/`resolve_chk`）；`test_dispatch_deps.py` 的成功终态用例
   （如 :188 经 `_on_terminal`）同样间接触达，不单列。

**步骤三（T5）：三处接线**

1. `materialize.resolve_upstream_chk`（`web/src/engine/materialize.py:72-95`）：
   同包导入扩展（`from .workspace import` 增 `parse_chk_line, resolve_chk`）；
   chosen 定位逻辑不变（当前输入哈希匹配优先、无匹配回落最近成功执行）；
   取 `run_d = execution_run_dir(chosen["id"])` 后按序判定：

   ```python
   run_d = execution_run_dir(chosen["id"])
   try:
       copy_text = (run_d / "input.gjf").read_text(
           encoding="utf-8", errors="replace")
       declared = parse_chk_line(copy_text, link0_only=True)
   except OSError:
       declared = None  # 执行副本缺失视同无声明（生产链路恒在）
   if declared is None:
       raise MaterializeError(
           f"上游任务 {task_id} 最近成功执行（#{chosen['id']}）未声明 "
           "%chk（G16 不产出检查点文件），请为上游补写 %chk 声明",
           {"upstream_task_id": task_id, "execution_id": chosen["id"]})
   resolved = resolve_chk(run_d)
   if not resolved.is_file():
       raise MaterializeError(  # 文案与 details 维持现状
           f"上游任务 {task_id} 最近成功执行（#{chosen['id']}）的 chk "
           "已被清理，物化必然失败（重跑上游恢复 chk 来源）",
           {"upstream_task_id": task_id, "execution_id": chosen["id"]})
   return resolved
   ```
   执行副本缺失（OSError）视同无声明为有意从严的防御分支：生产链路执行
   副本恒在（派发物化先于 g16 运行写盘）；该形态下即使 `resolve_chk`
   回落的 `input.chk` 存在（盘面手工放置）亦报「未声明」，与 §2.2 校验
   （读任务输入副本）、⑥ 存在性判定（`resolve_chk` 回落）的口径差异仅
   出现在手工盘面形态，不为该形态放宽。`declared` 取 Link0 口径
   （`link0_only=True`），`resolved` 保留 `resolve_chk` 全文扫描作
   find-source 兼容；附加节 `%chk` 不构成声明，故先于 `resolved` 判空。

2. `dependencies.execution_chk_asset`（`web/src/services/dependencies.py:92-106`）：
   函数体内延迟导入 `from ..engine.workspace import resolve_chk`——防环
   （`engine/__init__.py` 导入 dispatcher → materialize → 本模块；
   module-level 导入会在全新 import services.dependencies 时触发部分
   初始化 ImportError；先例 `inputs_path` 延迟导入 `services.candidates`，
   :39）；`protected/` 优先逻辑不变，顶层回落 `top = d / "input.chk"`
   （:105）→ `top = resolve_chk(d)`（`@exec:` 与 resume 消费自动跟随）。
3. `dependencies.validate_queue_members` 两处改动：新增 §2.2 第 1 条校验块
   （插入位置 ⑦ 方向校验 :248-258 之后、⑥ 之前，函数体内延迟导入
   `parse_chk_line, resolve_chk`——module 级导入会触发 engine 包部分
   初始化的循环依赖）；既有 ⑥ 溯源存在性块的定位表达式改写——
   `(run_dir(src["id"]) / "input.chk").is_file() is False` →
   `resolve_chk(run_dir(src["id"]))` 存在性判定（message 与 details
   原样保留，消除「chk 在保留期但叫别的名」的反向误拒）；函数 docstring
   头部时点枚举由「创建 / PATCH / 提交」补为「创建 / 导入成队 / PATCH /
   提交」，校验项枚举同步——⑥ 条目扩为声明完整性与存在性两形态（上游
   输入未声明 %chk → 拒绝并引导补写；已有成功执行但 chk 已清理 → 同码
   拒绝），①-⑦ 编号保持不变。
4. **注释同步**（随本提交，防实现与注释漂移），各处 `input.chk` 具体名
   表述统一按 resolve_chk 口径改写（「实际执行副本 `%chk=` 声明决定，
   无声明回落 input.chk」）：`dependencies.py:83`（`latest_succeeded`
   docstring「chk 来源 = … run/<eid>/input.chk」）、`dependencies.py:95-96`
   （`execution_chk_asset` docstring ②「正常执行 chk：run/<eid>/input.chk」）、
   `dependencies.py:259-260`（⑥ 溯源块行内注释「上游无成功执行=依赖满足
   时必然有产出」——改写为「上游已声明 %chk，依赖满足时有产出；已有成功
   执行但文件不在则拒绝」）、`resume.py:10`（模块头注释）、
   `resume.py:191`（探针取数行内注释「protected 保全 → 保留期
   input.chk」）、`materialize.py:12` 与
   `materialize.py:121`（模块 docstring 与 materialize_chk 行内注释的
   「protected 保全优先，回落保留期内 input.chk」）、`materialize.py:76`
   （`resolve_upstream_chk` docstring）随本函数改写一并修订；
   `resume.py:8`（模块头「与物化器同源，engine.materialize.execution_chk_asset」）
   改注为「与物化器同源：定义处 `services.dependencies.execution_chk_asset`，
   经 `engine.materialize` 再导出」——与 resume.py:37 既有导入
   （`from ..engine.materialize import …` 再导出路径）一致，导入不动；
   `materialize.py:10`（模块 docstring「本任务自身 `%chk` 保持默认
   `input.chk`」与 finalize.py:6「无 %chk 不产 chk」实测口径相抵）改为
   「本任务自身 chk 目标由自身 `%chk` 声明决定，无声明 g16 不产 chk」。
5. `%chk=""` 空值引号形态修复（自 T4 移入的唯一行为变更，T5
   `fix(web)` 提交的组成部分）：`parse_chk_line` 增补剥引号后判空返回
   None（无声明三形态语义自此齐备，§2.1 步骤一第 2 条）；`resolve_chk`
   该形态随之改判回落 `input.chk`（消除 `Path("")` 派生的 run 目录旁
   `<执行id>.chk` 错误路径）；步骤一第 5 条预约的两断言随本提交补入
   并转绿。

行为对照（修复后）：

| 上游/源执行形态 | 现状 | 修复后 |
|---|---|---|
| `%chk=opt.chk`（产物 `opt.chk` 在保留期） | 物化必败（报障）| 物化成功，拷 `opt.chk` → `dep-<X>.chk` |
| 无 `%chk` 行（无产物） | 物化必败，文案误导「已被清理」 | 提交时 422 拒绝并引导补写（§2.2）；漏网到物化则文案如实「未声明 %chk」（§2.2） |
| `%chk=/abs/path.chk`（产物在绝对路径） | 必败 | 该文件存在即拷入，不存在按无源报错 |
| 续用形态上游（`%chk=@task:X` 改写后产物为 `dep-X.chk`） | 必败 | 按改写后实际执行副本定位，正确 |
| `@exec:` 自定义名产物在保留期 | 判「无 chk 资产」 | 正常取数 |
| 提交时上游已成功且自定义名 chk 在 | 误拒 `CHK_SOURCE_MISSING` | 正确放行 |

### 2.2 静态校验补缺：被 `@task:` 引用的成员须声明 `%chk`（裁决 A，2026-11-11）

现状缺口：上游输入无 `%chk` 行时 g16 不产 chk、下游物化必败，但提交时
静态校验放行（「依赖满足时必然有产出」假设不成立），运行时才失败且文案
误导（「已被清理，重跑上游恢复」——无声明时重跑也不会有）。落地：

1. **校验判定**（`validate_queue_members` 新增块，置于 ⑦ 方向校验与
   ⑥ 溯源存在性之间——既有错误码优先级不变；创建 / 导入成队 / PATCH /
   提交四时点经同一函数自动生效，无新增端点）：被 `@task:` 引用的成员，
   其任务输入副本（`inputs/<tid>`）须在 Link0 区含 `%chk=` 声明。
   判定五要点：
   - 判定用 `workspace.parse_chk_line(..., link0_only=True)`（仅扫 Link0
     区，范围判定经共享 `_link0_span` 与 `resolve_link0` 同规则，§2.1
     步骤一同口径），对任意非空声明值返回非 None、**不按形态特判**：
     符号续用形态 `%chk=@task:X` 亦算声明——物化改写后 g16 产出
     `dep-X.chk`；`%chk=@exec:<eid>` 形态不进入本判定——队列成员携带
     `@exec:` 在 ② 载体校验先拒（dependencies.py:204-208），该形态仅属
     单任务续跑链路，由物化器/续跑探针自行取数、同样按「非空即声明」
     处理；G16 只识别 Link0 命令（Link 0
     命令须位于 route 之前，`resolve_link0` 的区段判定即据此实现），附加节
     `%chk` 不构成声明（route/标题节错置由 `parse/blocks.py` 既有
     Link 0 错位检测以 parse_errors 拒绝；落到其他附加节的 `%chk` 解析
     放行但本校验按未声明 422 引导补写到 Link0）；`resolve_chk` 保留
     全文扫描作 find-source 兼容，不参与声明判定；
   - `%chk=`（空值，含仅引号形态 `%chk=""`）视同无声明；
   - 输入副本读取失败（文件缺失等 OSError）视同无声明；
   - 无声明 → 422 `CHK_SOURCE_MISSING`（复用现有码，不新增），message
     定稿：「上游任务 {tid} 的输入未声明 %chk（G16 无声明不产出检查点
     文件，下游接续必然失败），请在上游任务输入的 Link0 节补写 %chk」；
   - details 携带 `task_id`（引用者）、`line`、`ref`（符号原文）、
     `upstream_task_id`，**无 `execution_id`**（上游未必已有执行）；前端
     经 `details.task_id` 通用路径渲染（QueueEditorModal.vue:261-262、
     `test_error_codes.py:180` 既有注释口径），白名单零改动。

   判定逻辑（`err`/`inputs_path`/`refs_by` 均为该函数既有可用名）：

   ```python
   for tid in member_ids:
       for ref in refs_by[tid]:
           if ref["kind"] != "task":
               continue
           try:
               up_text = inputs_path(ref["target"]).read_text(
                   encoding="utf-8", errors="replace")
               declared = parse_chk_line(up_text, link0_only=True)
           except OSError:
               declared = None  # 输入副本缺失视同无声明
           if declared is None:
               raise err(
                   "CHK_SOURCE_MISSING",
                   f"上游任务 {ref['target']} 的输入未声明 %chk（G16 无声明"
                   "不产出检查点文件，下游接续必然失败），请在上游任务输入"
                   "的 Link0 节补写 %chk",
                   {"task_id": tid, "line": ref["line"], "ref": ref["raw"],
                    "upstream_task_id": ref["target"]}, http=422)
   ```
   校验调用面（四时点同一函数，无新增端点）：创建 `routers/queues.py:57`、
   导入成队 `services/queues.py:105`（`create_queue_from_candidates`，
   由 `services/candidates.py:203-205` 的 `queue_from_folder=true` 调用）、
   提交 `routers/queues.py:144`、PATCH 仅在 `member_ids` 变更时
   `services/queues.py:167-170`。导入成队此前直接建队，绕过包括本计划
   新增校验在内的全部 DAG 校验——T5 在 `create_queue_from_candidates`
   建队前补 `validate_queue_members(member_ids)`，失败由
   `import_folder_as_queue` 捕获 `ApiError` 并回落为「已导入候选、未成队」，
   `queue_fallback_reason` 如实给出原因（与 2–10 越界回落同通道），
   函数 docstring 的回落口径同步为「越界或依赖校验未通过」，不产生
   半成品队列。
   「输入副本缺失视同无声明」分支在创建/PATCH/导入成队时点可达——提交
   时点 `verify_and_store`（queues.py:137）先于本校验，副本缺失以
   404 NOT_FOUND 先拒（verify.py:37-43），DAG 校验不可达；组合流精修
   队列的防御调用 `workflows.py:256` 不触发本校验——精修模板保存时已
   前置拒绝符号引用（`combo_templates.py:174-186`），生成成员互不引用，
   该链路零影响。
   升级兼容性：3.5.0 前已创建、尚未提交的队列不做回溯改写；其上游成员
   输入若无 `%chk` 声明，升级后提交会被新校验 422 拒绝，需在上游输入的
   Link0 节补写 `%chk` 后重新提交（PATCH 变更成员集同样触发）。该收紧
   行为随 T7 记入 CHANGELOG。

2. **物化文案区分**（落点即 §2.1 步骤三第 1 条 `resolve_upstream_chk`
   改造；判定读上游溯源执行副本 `run/<eid>/input.gjf` 的 Link0 区，非
   任务输入副本）：上游执行副本无声明 → 文案改「未声明 %chk（G16 不产出
   检查点文件），请为上游补写 %chk 声明」；已声明但文件不在 → 维持
   「chk 已被清理，物化必然失败（重跑上游恢复 chk 来源）」。
   `@exec:` 载体引用无声明执行经 §2.1 步骤三第 2 条落既有文案「无 chk
   资产（已清理或从未产生）」，语义已如实、不改。
   残余路径口径（已知、不在静态校验覆盖范围）：静态校验读任务输入副本
   `inputs/<tid>`，物化读所选成功执行的执行副本——当前输入哈希不匹配、
   回落更早成功执行且该执行副本无声明时，静态校验放行而物化报「未声明」；
   该形态由本条运行期文案兜底，不为它对 `latest_succeeded` 的执行副本
   追加同口径声明检查（保留哈希回落语义）。
3. **契约同步**（T1/T2 文档批次，两类文件分提——AGENTS §5.1）：
   - （T1，`docs(plans)`）m4-plan.md 勘误注记八处（其中七处语义不变、
     落地口径修订；「chk 溯源」条另附语义注记）：依赖面段落 :97、
     物化语义条 :194、§2.1「chk 溯源」条 :196-198、续跑探针取数
     :289-291、续跑注入矩阵 :319、B9 §4.6 ③ 取数路径 :720-721、
     test_resume 覆盖表 :818、B7 §4.6 依赖链验收断言 :930（「上游
     run/<opt执行id>/input.chk 原件哈希前后一致」同样把 chk 固化为
     `input.chk`），各追加注记
     「勘误（3.5.0）：chk 具体名由该执行实际执行副本 Link0 `%chk=` 声明
     决定（相对值相对 run 目录、无扩展名自动追加 .chk、无声明 g16 不产
     chk——`finalize.resolve_chk` 实测口径），非固定 `input.chk`」；
     其中 §2.1「chk 溯源」条（:196-198）另追加语义注记「3.5.0 起被
     `@task:` 引用的上游须在 Link0 区声明 `%chk`：无声明时即使尚无成功
     执行也以 `CHK_SOURCE_MISSING` 422 拒绝（原文「尚无成功执行属正常、
     放行」自本版起以已声明为前提）」——§2.2 校验相对 m4 定稿的语义
     收紧，非纯口径修订；
     link1-multistep-plan.md B4 行（`| B4 |`）涉及文件列已有 resolve_chk
     迁入注记，补 `parse_chk_line` 同源迁入说明与多步口径衔接——多步
     放行后 `resolve_chk` 按末个声明 `%chk` 的段定位，任一段含声明即
     视为已声明、全部段未声明才回落 `input.chk`，`parse_chk_line` 与
     §2.2 校验须同步改为末个声明段口径（与 B12 统一表述；防待执行
     计划文件锚点漂移，其 B12 已列 workspace.py，无需改）。
   - （T2，`docs(api)`）`docs/api/openapi.yaml` 六处 description 文本
     同步：:72-73 `CHK_SOURCE_MISSING` 注释扩两形态口径（定稿文本如下）；
     PromptBlock description :1518-1524 的 `CHK_SOURCE_MISSING` 单形态
     表述扩两形态；ResumePreview description :2725-2730「取最近成功执行
     的 input.chk」改按 `%chk=` 声明定位口径；导入成队回落语义三处——
     `queue` 属性 :1731、`queue_fallback_reason` 属性 :1740 与
     POST /candidates description :2097-2100——由「越界」扩为「越界或
     依赖校验未通过」。同提交同步 `docs/api/mapping.md:12` 与
     `docs/api/sse.md:69` 的「越界回落时仅 `created` ×N」表述为「越界或
     依赖校验未通过时回落（仅 `created` ×N）」——T5 后回落原因还包括
     依赖校验未通过，不随本批修订即成不准确契约。以上均为
     description/注释文本，openapi 变更经 `web/scripts/gen_models.py` 与
     前端 `npm run gen:types` 再生成 Pydantic 模型与 `contract.ts` 随本
     提交（契约源与生成产物同批，link1 B1 先例），闸门复核生成零 diff：

     ```yaml
     #   - CHK_SOURCE_MISSING — 422：被引用上游接续源缺失（提交拒绝）——
     #     两形态：上游输入未声明 %chk（G16 无声明不产出检查点文件；
     #     details 携带 upstream_task_id、无 execution_id，引导在上游输入
     #     Link0 节补写 %chk，3.5.0）/ 上游已有成功执行但 chk 已被保留期
     #     清理（details 注明缺失的执行 id，提示重跑上游恢复 chk 来源，M4）
     ```

     不新增码、不改响应结构，`test_error_codes.py` 前端分支白名单零改动。

### 2.3 fake_g16 对齐真实行为：按 `%chk` 行产 chk

修改 `web/tests/fake_g16.py`（61 行独立脚本，仅 os/sys/time/pathlib，不
导入 web.src；现流程：读输入 `Path(sys.argv[-1])` → 写同名 `.log`（steps
循环 + note）→ 按 exit 码退出）：

1. **解析**：main() 内一次读取输入文本（utf-8、errors=replace；读取
   OSError → `text=""`，解析不出声明即不产 chk——`.log` 写出与退出码
   路径维持现状容错，不因输入缺失抛栈），内嵌
   `_CHK_RE = re.compile(r"^%chk\s*=\s*(.+)$", re.IGNORECASE)`，仅扫
   Link0 区（前导空行/`!` 注释后的连续 `%` 行，与
   `parse_chk_line(link0_only=True)` 同规则）逐行 strip 匹配取首个命中，
   声明值 strip 并剥首尾引号；脚本头注释注明「Link0 口径与
   `web/src/engine/workspace.parse_chk_line` 同步维护」（独立脚本不导入
   web.src，正则内嵌）；`import re` 新增。
2. **落盘规则**（`.log` 写完之后、退出之前——对齐 g16 退出前 chk 已在
   盘）：
   - 相对声明 → 写 `inp.parent / 声明名`（输入文件所在 run 目录）；
     无扩展名声明自动追加 `.chk`（g16 手册规则）；
   - 绝对形态声明 → **不写**：判定用 `Path(raw).anchor` 非空（覆盖
     POSIX 绝对路径与 Windows 盘符/根锚形态——`Path('/tmp/w.chk')
     .is_absolute()` 在 Windows 下为 False，`inp.parent / p` 会得到
     盘符根路径 `<drive>:/tmp/w.chk`，故不能只用 `is_absolute()`）；
     脚本头注释注明与真实 g16 的差异边界：测试触盘面已整体隔离到
     tmp_path（home 夹具口径），绝对路径落盘会外溢共享 /tmp；绝对路径
     产态由单测手工资产覆盖——§2.4；
   - 内容恒 `b"fake-chk"`（非空字节；无专项字节级断言依赖）；
   - 无 Link0 `%chk` 声明不写（对齐「无声明不产 chk」实测结论，
     finalize.py:6）。
3. **影响面核查结论**：既有用例输入或无 `%chk` 行
   （test_e2e_queue_lifecycle.py 全部），或声明为绝对路径
   `%chk=/tmp/w.chk`（test_e2e_fake_g16.py 的 SIMPLE :31 与 FAILING :185
   三用例、test_dispatch_engine.py 首链用例 `test_fake_g16_first_pipeline`
   :476，:475 为其 skipif 装饰器）——新规格下均不触发
   写盘（Windows 下根锚判定同样跳过，不外溢写盘或抛 FileNotFoundError），
   fake_g16 变更对既有用例**零行为变化**；新 e2e 红用例为首个相对声明
   输入（§2.4）。

### 2.4 测试补强

**溯源助手改置（T3）**——「手工放 `input.chk`」的助手改为「按任务输入
声明放置」，消除固定名假设的测试基建根源（§1.4）：「按名放置」= 命名
chk 与声明该名的执行副本 `input.gjf` 两者同落——缺执行副本时
`resolve_chk` 走无声明回落仍按 `input.chk` 命中，红用例无法转绿。
助手取声明时按 Link0 区口径（与 `parse_chk_line(link0_only=True)` 同
规则），避免把附加节 `%chk` 误当声明；绝对路径声明只落执行副本
`input.gjf`、不写资产文件（防写出 tmp_path 之外，绝对路径产态由
`test_absolute_chk_declared` 在 tmp_path 内手工构造）。

- `test_materialize.py::_succeed_with_chk`（:53-66，8 处调用面）：改造为
  读任务输入副本 `inputs/<task_id>` 原文 → 内嵌 Link0 区正则取 `%chk`
  声明名（与 `workspace.parse_chk_line(link0_only=True)` 同口径，注释
  注明同步维护；T3 时点该纯函数尚未迁移，助手不预依赖）→ 落执行副本
  `run/<eid>/input.gjf`（任务输入原文）+ 按声明名落 chk 字节资产；无声明
  （现调用面不存在，防御）回落现行为 `input.chk`。各调用点上游输入均
  声明 `%chk=u.chk`/`o.chk`，全部转为按名放置；
- `test_dispatch_deps.py::_succeed`（:63-73，4 处调用面 :164/:184/:200/
  :253）：同款改造（各上游输入均声明 `%chk=u.chk`）；
- 联动体改（改置涉及断言/操作目标文件名，仅改名不改语义）：
  `test_cleaned_source_raises`（:111 unlink 目标 → u.chk）、
  `test_upstream_untouched`（上游原件哈希不变断言路径 → u.chk）、
  `test_hash_skip_source_resolution`（:128 返回路径断言 → u.chk）、
  `test_dispatch_materialize_failure_terminal`（chk 删除目标 → u.chk）；
- `test_resume.py` 无需改置：资产经 `protected/` 保全优先取数（① 路径
  语义不变），源执行输入声明 `%chk=own.chk` 与资产名一致；
- 既有依赖校验用例数据改置：`test_patch_remove_depended_member_rejected`
  （test_dependencies.py:170-186）中段成员 b 被 c 引用但输入仅
  `%OldChk=@task:a`、无 `%chk`——新校验会使建队即 422；为 b 输入补
  `%chk=b.chk`（不改断言语义与用例目的），随 T3 同提交；

**新增红用例（T3 先证红）**：

| 用例 | 场景与断言 | T3 红因（现状缺陷） |
|---|---|---|
| test_materialize.py::test_named_upstream_chk_materializes | 上游输入 `%chk=opt.chk`、助手按名放置；下游 `%OldChk=@task:<u>` → `materialize_chk` 拷 `dep-<u>.chk` 字节相等、改写行 `%oldchk=dep-<u>.chk`、零残留 | 定位恒取 `input.chk` → MaterializeError |
| test_materialize.py::test_symbol_chk_chain_three_level | A（`%chk=a.chk`）→ B（`%chk=@task:A`）→ C（`%OldChk=@task:B`）：B 执行副本改写后声明 `dep-A.chk`，C 溯源按改写后执行副本命中 | 同上 |
| test_materialize.py::test_absolute_chk_declared | 执行副本声明绝对路径（tmp_path 内）且资产在 → 拷入成功 | 同上 |
| test_materialize.py::test_undeclared_source_message | 源执行副本无声明且无 `input.chk` → MaterializeError 文案含「未声明 %chk」与「补写」 | 现文案误导「已被清理」 |
| test_materialize.py::test_exec_asset_named_top_level | 源执行输入声明 `%chk=o.chk`、助手按名放置顶层 `o.chk`（无 protected/）→ `execution_chk_asset` 返回 `o.chk`、`%OldChk=@exec:<eid>` 物化拷入 `dep-exec-<eid>.chk` 字节相等（resume 探针取数同源跟随） | 回落恒取 `input.chk` → 判「无 chk 资产」 |
| test_dependencies.py::test_upstream_undeclared_chk_rejected | b→a 引用、a 输入无 `%chk` → 创建 422 `CHK_SOURCE_MISSING`（message 含「未声明 %chk」「补写」；details.task_id/line/ref/upstream_task_id、无 execution_id）；提交时点另建一组：a 先声明 `%chk=point.chk` 建队成功，清空 a 的声明后提交 → 同码 422 | 无此校验、放行 |
| test_dependencies.py::test_upstream_input_missing_rejected | a 输入副本文件删除 → 创建 422 同码同口径（创建/PATCH/导入成队时点可达——导入副本刚写入除非磁盘故障、无独立用例；提交时点副本缺失经核验链 404 先拒、DAG 校验不可达，§2.2 调用面） | 同上 |
| test_dependencies.py::test_patch_revalidates_undeclared_upstream_rejected | 队列 [a, b, c] 创建成功（b 输入 `%OldChk=@task:a`、a 输入声明 `%chk=a.chk`，c 为无引用普通成员）；改写 a 的输入副本删除 `%chk` 声明后 PATCH 为 [a, b]（移除 c）→ PATCH 422 `CHK_SOURCE_MISSING`（message/details 同 §2.2 定稿），校验先于任何落库、成员集与库内顺序不变。构造走「移除触发重校验」路径：PATCH 的 `_validate_member_ids` 禁止新增成员（queues.py:49-52 只减不增），加成员形态会在校验前以 `member_added` 先拒、不可达本校验 | 无此校验、PATCH 放行 |
| test_materialize.py::test_exec_copy_missing_treated_as_undeclared | 上游 succeeded 执行副本 `input.gjf` 被删除、顶层 `input.chk` 手工存在 → `resolve_upstream_chk` 抛 MaterializeError「未声明 %chk」（不从 `input.chk` 放行） | 现状按 `input.chk` 命中并放行 |
| test_import_queue.py::test_folder_queue_dag_rejected_falls_back | 文件夹导入 2 文件、其中一件携带 `%chk=@exec:999999`（队列成员禁用 @exec）→ 全部落候选、`queue=null`、`queue_fallback_reason` 非空、零队列 | 现状直接建队、绕过全部 DAG 校验 |
| test_e2e_fake_g16.py::test_e2e_task_chain_chk_materialization | 队列两成员经真 CliGateway + 仓库构建 hq（`target/release/hq`，Windows 为 `hq.exe`）全链路：u 输入 `%chk=opt.chk`、d 输入 `%OldChk=@task:<u>`（tid 建队后回填）→ u succeeded（fake 产出 `opt.chk`）→ d succeeded、`run/<d_eid>/dep-<u>.chk` 存在且与 u 的 `opt.chk` 字节相等、d 的 input.gjf 无 `@task:`/`@exec:` 残留、队列 completed | 下游立即 failed/program_error |

**改置转红清单**（既有物化类用例，T3/T4 保持红、T5 转绿）：
`test_rewrite_oldchk_and_no_leftover`、`test_upstream_untouched`、
`test_hash_skip_source_resolution`、`test_dispatch_materializes_and_
disables_retry`（test_materialize.py）；`test_hash_skip_member_satisfies_
dependency_and_feeds_materialization`（改置后承接「哈希跳过 + 按名放置」
场景，不另设用例）、上游重跑传导用例（:178-206，
`_succeed` :184/:200 消费者）与重入②用例组（经 `_remat_setup`）
（test_dispatch_deps.py）。

**守护绿用例**（T3 即绿、T5 后须仍绿，防过杀）：

- `test_dependencies.py::test_symbol_declaration_passes`（新增）：三成员
  链 z（`%chk=z.chk`）→ a（`%chk=@task:z`）→ b（`%OldChk=@task:a`）
  创建与提交放行（符号声明不误拒）；
- 放行类由既有 `test_legal_chain_passes` / `test_backward_reference_passes`
  承接（上游均经 `_plain` 声明 `%chk=point.chk`）；
- `test_dependencies.py::test_patch_remove_depended_member_rejected`
  （:170-186）改置（中段 b 补 `%chk=b.chk`）后全程绿：新校验不误伤
  PATCH 移除被依赖成员的拒绝语义与合法移除链；
- 失败分支既有用例改置后全程绿：`test_cleaned_source_raises`（锁「已声明
  但文件不在」形态）、`test_dispatch_materialize_failure_terminal`、
  `test_exec_asset_protected_first`（protected 优先语义不变）、
  `test_missing_source_raises`（无助手调用，零改动）；
- `test_materialize.py::test_exec_asset_top_level_fallback`（新增）：无
  protected、无执行副本 `input.gjf`、顶层 `input.chk` 存在 →
  `execution_chk_asset` 返回 `input.chk`（`resolve_chk` OSError 回落的
  正向锚点）；
- `test_e2e_fake_g16.py::test_fake_g16_ignores_non_link0_chk`（新增）：
  输入在 route 之后的附加节携带 `%chk=late.chk` → fake_g16 不产 chk
  （Link0 口径守护，与校验口径同源）；直接子进程调用 fake_g16
  （`sys.executable` 传脚本与输入路径），不经导入/提交链——附加节
  `%chk` 经导入会先被 Link 0 错位检测以 parse_errors 拒绝，到不了
  fake_g16；
- 既有 ⑥ 提交拒绝锚 `test_chk_source_missing_rejected`
  （test_dependencies.py:191-208）改置后全程绿：该用例不落执行副本
  `input.gjf`、以手工放置/删除 `input.chk` 构造「已声明但已清理」形态，
  `resolve_chk` 经 OSError 回落仍按 `input.chk` 定位（创建时在、提交时
  被删 → 判缺失拒绝）——回落语义为 §2.1 步骤一第 3 条等价性锚点，
  不得随本计划改动；
- 既有绝对路径声明用例零影响恒绿：`test_fake_g16_first_pipeline`、
  `test_e2e_fake_g16.py` 三用例（§2.3 影响面核查结论）。

**e2e 新用例夹具**：沿 `test_e2e_queue_skip_failed_continues` 同款机制
（fakebin 拷贝 fake_g16.py、`G16_FAKE` 注入 sleep、`queues().create` +
`tasks().enqueue` + `set_state("submitted")` + 席位 append、仓库构建 hq
缺失时 skip——产物定位兼容 `target/release/hq` 与
`target/release/hq.exe`，避免 Windows 下静默跳过），等待循环以队列终态
（completed）收敛为退出条件。

### 2.5 队列编辑弹窗宽度可调与任务名自适应截断（前端修订，来源二）

现状锚点：弹窗宽度取设计令牌 `--modal-width: 560px`（tokens.css:60），经
共享外壳 ConfirmModal.vue:99 `width: min(var(--modal-width),
calc(100vw - 48px))` 生效；成员行任务名 `.m-file` 固定 `max-width: 150px`
单行溢出省略（QueueEditorModal.vue:762-769）。系列任务命名同前缀时可视
段为相同前缀，成员间无法区分——加宽弹窗也无法缓解（任务名列宽度不随
弹窗变化）。

改造四点（改动收敛于 ConfirmModal.vue 与 QueueEditorModal.vue 两文件）：

1. **宽度覆盖通道与手柄落点**（ConfirmModal.vue）：新增可选宽度透传
   （prop 或作用域 CSS 变量覆写），未传入时外壳行为逐字节不变——其余
   共享 ConfirmModal 的模态（ComboTemplatesModal / ResumeDialog /
   ComboFlowDialog、QueuesView / ExecutionsView / PendingView /
   HistoryView / SettingsView / CandidatesView 的确认弹窗）零视觉变化。
   外壳两处配套改动（同样零视觉变化）：`.modal` 增加
   `position: relative`（仅建立定位上下文，不改布局与外观）；`.modal`
   末尾新增具名插槽 `<slot name="resize-handle" />`——未传入插槽的
   模态渲染不变。落点约束：拖拽手柄必须经该具名插槽渲染为 `.modal`
   直接子元素，不得经默认插槽置于 `.body` 内——`.body` 是
   `overflow-y: auto` 的滚动容器（ConfirmModal.vue:115-119）且其内无
   定位祖先，slot 内容绝对定位会以滚动容器/视口为参照并被裁剪，
   无法贴住面板右缘。两条显式约束（2026-11-12
   用户裁决）：
   - **居中不偏移**：面板居中由覆盖层承载（`.scrim` 为 flex 双轴居中，
     ConfirmModal.vue:94-96），宽度透传不得改用 margin/transform 偏移等
     破坏居中的形态——任意宽度下弹窗保持窗口水平居中、两侧边距对称
     等分；
   - **不溢出视口**：宽度表达式必须保持 `min(<宽度>, calc(100vw - 48px))`
     形态（覆写 `--modal-width` 变量、不覆写 width 属性，ConfirmModal.vue:99）
     ——持久化宽度超过当前视口时自动钳制（两侧各留 ≥24px），窗口 resize
     后由该表达式在 CSS 层自动重钳，任何状态下零溢出。
2. **拖拽调宽**（QueueEditorModal.vue 经改造点 1 具名插槽提供手柄）：
   弹窗右缘拖拽手柄连续调节宽度
   （pointer 事件，组件内既有 usePointerSort 指针拖拽同栈）；居中面板
   两侧对称扩展，宽度增量 = 2 × 指针水平位移（右缘拖 1px 面板宽 2px），
   否则拖拽与视觉增长不同步；钳位区间 [560px（现默认档，默认宽度不变）,
   视口宽 − 48px]；视口宽 < 608px 时上限低于下限，内部取值取
   max(560, 视口宽 − 48px) 兜底，实际渲染宽度由 `min()` 表达式钳制为
   视口宽 − 48px（如 600px 视口渲染 552px），拖拽不改变可见宽度、零
   溢出；拖拽全程与持久化恢复时弹窗保持窗口水平居中（改造点 1 居中
   约束），持久化宽度超出当前视口时由 min() 表达式自动钳制（窗口
   收窄/resize 后同样生效）；宽度只改横向尺寸、成员行保持单行省略
   形态——画布行高前缀和量测（`loadLinkStates` 后 `sort.measure()`，
   QueueEditorModal.vue:193）不受影响。手柄为可聚焦控件：
   `role="separator"`、`aria-orientation="vertical"`、
   `aria-label="调整弹窗宽度"`、`aria-valuenow`（实际渲染宽度 =
   min(内部值, 视口宽 − 48px)，与渲染一致）、`aria-valuemin="560"`/
   `aria-valuemax`（实际渲染上限 = 视口宽 − 48px，与 `min()` 钳制一致；
   不取内部钳位值 max(560, 视口宽 − 48px)——视口宽 < 608px 时该值
   大于渲染上限，此时 max < min 为如实暴露的退化区间）、`tabindex="0"`、
   `cursor: col-resize`；键盘 ←/→
   以 16px 步长调节，与拖拽共用同一钳位与持久化路径，焦点态可见。
   手柄在只读/完成态同样显示且可操作（宽度属本地视图偏好而非数据
   编辑能力，与队列状态无关），拖宽照常生效并持久化。
3. **任务名截断动态化**（QueueEditorModal.vue `.m-file`）：去除固定
   `max-width: 150px`，改可伸缩占位（`flex: 1 1 auto`，基准为内容宽、
   可增长可收缩）+ `min-width: 0` 防溢出撑破，与 `.m-title`（既有
   `flex: 1; min-width: 40px`）按 flex 比例分配行内剩余宽度；单行省略
   兜底保留（仍超宽时省略号截断）；全名悬浮提示沿用既有 `title` 属性
   （QueueEditorModal.vue:522，本项不新增）；拖宽后长任务名显示宽度随
   弹窗增长。
4. **持久化**：localStorage（ThemeToggle 主题持久化同通道，键名对齐
   `g16web-theme` 既有前缀，如 `g16web-queue-editor-width`）——不上
   ui-prefs：其键为枚举白名单、值须在
   枚举值域内（`config.UI_PREF_KEYS`，config.py:138-142；PUT
   /ui-preferences 整批 all-or-nothing enum 校验），连续像素值不在该域
   模型内，且宽度属设备视口相关的本地视图偏好；后端零改动。

闸门与验证（前端改动批次，AGENTS §6.3）：`npm run build`（vue-tsc +
vite build）通过；`scripts/audit_frontend_offline.sh` 通过；不新增设计
令牌与配色（宽度值为组件级像素写法，`.m-file` 150px 即既有先例），
`check_tokens.py` / `check_contrast.py` 跑闸门确认零 diff。项目无组件
测试基建（frontend package.json 无 test 脚本），交互项以人工冒烟逐项
走查并留痕（development.md §6 口径）：拖宽生效且全程居中、键盘 ←/→
调节生效、刷新保持、长名随加宽显示、窗口收窄后不溢出（自动钳制）、
其余模态宽度不变；走查证据随 T6 进度记录保留。

## 3. 任务分解与提交序列

| # | 内容 | 提交类型 | 规模 |
|---|---|---|---|
| T0 | 本计划文档落盘（本提交） | `docs(plans)` | S |
| T1 | m4-plan 八处勘误注记（「chk 溯源」条另附 §2.2 声明前置语义注记）+ link1 B4 parse_chk_line/末个声明段口径补注（§2.2 第 3 条） | `docs(plans)` | S |
| T2 | openapi 六处 description 同步（CHK_SOURCE_MISSING 两形态、ResumePreview/PromptBlock、导入成队回落三处）+ mapping.md/sse.md 回落表述同步 + gen_models.py / gen:types 再生成（§2.2 第 3 条） | `docs(api)` | S |
| T3 | 测试先行：fake_g16 产 chk（§2.3）+ 溯源助手按名改置与既有依赖用例数据改置（§2.4）+ e2e 接续闭环红用例 + 单测定位分支红用例 + 校验红用例与守护绿用例（§2.4） | `test(web)` | S |
| T4 | 实现（结构迁移）：resolve_chk 下沉 workspace（拆 parse_chk_line 纯函数 + 共享 Link0 区段扫描 `_link0_span`）+ finalize 别名保留（§2.1 步骤一/二），全量行为等价（含 `%chk=""` 现状派生路径），提交时除 T3 红集合（§2.4）外全量 pytest 全绿 | `refactor(web)` | S |
| T5 | 实现（行为修复）：三处接线（§2.1 步骤三）+ `%chk=""` 空值引号形态修复及其断言（§2.1 步骤一第 3 条、步骤三第 5 条）+ 注释同步清单（§2.1 步骤三第 4 条）+ 校验与物化文案两形态 + 导入成队校验接线（§2.2），T3 红集合全数转绿 | `fix(web)` | S |
| T6 | 前端修订：队列编辑弹窗宽度可调与任务名自适应截断（§2.5），闸门 `npm run build` + `scripts/audit_frontend_offline.sh` + `check_tokens.py` + `check_contrast.py` 全通过 | `feat(frontend)` | S |
| T7 | 进度同步：CHANGELOG unreleased（fixed/web——条目注明「创建/导入成队/PATCH/提交四时点生效：上游输入未声明 %chk 由放行收紧为 422 CHK_SOURCE_MISSING；导入成队校验失败回落候选、不成队；升级后既有队列的未声明上游须在上游输入 Link0 节补写 %chk 后方可提交」的升级行为；added/frontend——§2.5 前端修订；changed/plans——本计划定稿与 m4-plan 八处勘误/语义注记，changelog-spec `docs` 类豁免第 2 条口径）+ `CHANGELOG.md` 经 `scripts/gen_changelog_md.py` 再生成并通过 `--check` + progress.json + 本计划状态回填「已实施并验收（3.5.0）」；目标版本 3.5.0（unreleased 已含 added 条目（Windows 启动器与本批前端修订）随同批发布，按 changelog-spec §1.7 判 minor） | `chore(progress)` | S |

T3 红用例先行红入库（先例 `cf59112f`），红集合 = §2.4 新增红用例 + 改置
转红清单所列既有用例；该提交闸门口径为「除红集合外全量 pytest 全绿」，
T4 维持同一口径，T5 红集合全数转绿后全量全绿。既有依赖用例数据改置
（§2.4 末条：`test_patch_remove_depended_member_rejected` 中段补
`%chk=b.chk`）同随 T3，避免 T5 新校验上线后该用例误红。红集合入库与先证红走查
前置：确认仓库构建 hq 在位（`target/release/hq`，Windows 为
`target/release/hq.exe`；缺失先 `cargo build --release`，防红 e2e 静默
skip 造成虚假通过数，AGENTS §6.1 第 4 条）。先证红（e2e 物化
断言失败于 T3 时点现状）再证绿的走查在 T3→T5 间完成，转绿走查须确认定位
分支资产含执行副本 `input.gjf`（§2.4）与既有绝对路径声明用例恒绿（§2.3）。
进度同步口径：本计划按「整批一次变更」收口——T1–T6 不逐提交追加
CHANGELOG/progress，T7 统一收口属批次正常收尾而非补填（先例：启动器
批次 docs→feat→test 后由 chore(progress) 单提交同步）；条目范围按
changelog-spec 记录映射取用户可见变更（fix→fixed、feat→added，计划
定稿与勘误属 `docs` 类豁免第 2 条协作可见口径回填记 changed）。

## 4. 验收判据

1. `uv run pytest` 全量通过（含新 e2e；确认仓库构建 hq 在位——
   `target/release/hq`，Windows 为 `target/release/hq.exe`，e2e 不静默
   跳过，通过数如实记录）；
2. 新 e2e：上游 `%chk=opt.chk` 接续链全绿（物化拷贝 + 零符号残留 + 下游
   succeeded）；
3. 校验行为：上游无 `%chk` 声明的组队提交被 422 拒绝、文案引导补写；
   创建/PATCH/导入成队/提交四时点同源生效（导入成队校验失败回落候选、
   不建队列）；输入副本缺失视同无声明拒绝（提交时点副本缺失经核验链
   404 先拒）；符号续用形态放行；附加节 `%chk` 不算声明；既有合法
   PATCH 移除与重排链路（含被引用中段成员）不受新校验影响；
4. 前端修订（§2.5）：队列编辑弹窗拖宽生效且全程保持窗口水平居中、两侧
   边距对称，刷新后宽度保持；手柄可聚焦、aria 属性齐全，键盘 ←/→
   可调节且与拖拽同钳位；窗口收窄/resize 后不溢出（自动钳制至视口宽 −
   48px）；长任务名显示宽度随加宽增长、仍超宽时单行省略 + title 全名
   提示；其余共享 ConfirmModal 模态宽度零变化；人工走查逐项留痕；
   `npm run build`、`scripts/audit_frontend_offline.sh`、
   `check_tokens.py`、`check_contrast.py` 全通过；
5. `uv run python scripts/validate_progress.py` 通过；
6. `uv run python scripts/gen_changelog_md.py --check` 通过（CHANGELOG.md
   与 jsonl 一致）；
7. `uv run python scripts/check_plan_status.py
   docs/plans/chk-materialize-fix-plan.md` 通过（AGENTS §5.2 第 2 步计划
   状态校验，本次发布涉及计划定点口径）；
8. 人工冒烟（可选）：客户端重放原失败队列（上游补 `%chk=` 或原名重跑），
   下游正常接续。

## 5. 明确不做（边界）

- 不改复制语义、`dep-<taskid>.chk` 命名、物化/重入/HQ 提交参数
  （`crash_limit=0` 等）——架构面见 §1.2 澄清，均正确；
- 不改 `reconcile.has_chk`（重定向判据按「目录任意顶层 .chk」，与具体名
  无关，不受影响）；
- 不引入「下游直接跨目录读上游文件」形态（生命周期耦合：上游清理/重跑
  波及在跑下游，g16 启动重写 `%chk` 亦会波及上游原件——roadmap §8.6）；
- 不动清理边界与保留期逻辑；
- chk 修复主体前端零改动（失败归因、文案渲染既有链路不变）；前端改动仅
  §2.5 队列编辑弹窗一处，不触碰 DAG 校验交互与错误渲染链路。
