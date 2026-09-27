# 0002 · 项目自立更名 GauForge，切割上游 git 历史

本仓库原以 fork 方式继承上游 HyperQueue 的完整 git 历史（约 2200 个提交、59 个
tag），项目自身的 380 个提交叠在 fork 点之上。随着项目定位收敛为「以 HQ 为执行
内核的 G16 Web 工作台」，仓库身份需要与上游脱钩：本项目是主体，HQ 是内核。

**决定**：

- 项目更名 **GauForge**；根 LICENSE 改为本项目自己的 MIT 版权行，
  上游 MIT 原文随内核源码保留在 `crates/LICENSE`，README 注明内核来源与 fork 点。
- git 历史切割：以 fork 点 `main@21f2d2e8b`（v0.26.2 之后、含上游未发版调度改进）
  的树压成单个 `vendor` 根提交，本项目 380 个自有提交原样 rebase 其上；
  上游约 2200 个历史提交、全部上游 tag 与上游 remote 移除。
  切割前完整历史备份为 bundle（`~/gauforge-history-backup-20260928.bundle`）。
- 发版 tag 一律改用裸 `v<version>` 前缀（上游 tag 已随历史移除，命名空间不再冲突，
  `changelog-spec` §1.6 同步修订）；`g16-v0.1.0` 旧 tag 在新历史上重打为 `v0.1.0`。
- 本地目录名、Rust crate 名（`hyperqueue`/`tako`）、`hq` 二进制名均不改——
  名称只作用于项目身份层（README、LICENSE、ADR、发版登记），不做全局符号替换。

**后果**：

- 与上游失去共同祖先，吸纳上游更新从 merge/rebase 变为按需手动 diff 移植；
  ADR 0001 中「吸纳上游更新需自行 merge/rebase 处理冲突」的前提自此失效，以本 ADR 为准。
- `crates/` 改动为 12 文件 +1170/-69（以 vendor 根为基准，进程内 HTTP/SSE 层为
  主；更正：初版登记的「48 文件 +2611/-338」混入了上游自身 30 个未发版提交的
  调度器改动，非本项目所为），后续上游更新按场景甄别移植，
  移植成本自担（与 ADR 0001 的独立演进决策一致，方向不变、力度加深）。
- 上游 MIT 许可义务以 `crates/LICENSE` 的保留满足；GauForge 自有代码按根 LICENSE 发布。
- 旧完整历史（含上游）可经备份 bundle 找回：`git clone ~/gauforge-history-backup-20260928.bundle`。
