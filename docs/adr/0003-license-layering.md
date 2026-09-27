# 0003 · 自有代码许可改为 PolyForm Noncommercial，内核维持 MIT

GauForge v1.0.0 曾以单一 MIT 发布全仓。本项目定位为个人主导、非商业优先的
计算化学工作台，自有代码的商用授权需要保留在版权人手中，故对许可做分层调整。

**决定**：

- 自有代码（除 `crates/` 外的全部内容）自 v2.0.0 起采用 PolyForm
  Noncommercial License 1.0.0：根 `LICENSE` 为分层声明 + PolyForm 全文，
  含 `Required Notice: Copyright (c) 2026 keepoux (GauForge)`。
- 内核 `crates/` 维持上游 MIT 不变，`crates/LICENSE` 原文保留；范围规则：
  除 `crates/` 外一切内容适用根 LICENSE，`crates/` 仅适用上游 MIT。
- v1.0.0（含）之前的发布版本按 MIT 存续（grandfather）。
- README 增 AI 使用声明：开发大量使用 AI 编码代理（ZCode CLI，GLM 系列模型）
  协作完成代码与文档，需求定义、方案决策与验收把关由人类完成。

**后果**：

- 本项目不再是 OSI 意义的开源软件（source-available）：对外表述避免「开源」；
  商业使用需另行授权；conda-forge、Linux 发行版等渠道基本不可用
  （GitHub licensee 可正常识别展示 PolyForm Noncommercial）。
- 「非商业」定义存在灰区，边界争议以 PolyForm 原文为准。
- 外部贡献若被接受，默认按 NC 授权进入；日后如需改回开源许可，须征得
  届时全体贡献者同意（当前贡献者仅 keepoux 一人）。
- 上游内核更新移植不受影响（MIT 侧无任何变化）；第三方依赖侧无新增冲突。
- 换许可按仓库纪律属破坏性变更（用户权利收缩）：breaking=true → major →
  本变更随 v2.0.0 发布。
