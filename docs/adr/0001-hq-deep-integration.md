# 0001 · HyperQueue 作为执行内核深度融合，而非外部依赖

本仓库 fork 自上游 HyperQueue，`crates/` 是队列引擎源码。集成方式有两条路：
把 HQ 当外部依赖、仅经 `hq --output-mode json` CLI 适配（可随时换调度器，但
能力受 CLI 输出限制）；或把 HQ 视为项目自身的执行内核，直接修改 `crates/`
源码补齐需求。

**决定**：HQ 是本项目的执行内核而非外部依赖——`crates/` 源码可按需修改，
完全独立于上游仓库演进；不为「换调度器」过度留缝，g16web 与其深度融合，
不做外挂式补丁。

**后果**：吸纳上游更新需自行 merge/rebase 处理冲突；上游 CLI JSON 结构变化
不再是本项目的风险（结构自己掌控，CLI JSON 契约测试兜底）。首个改造场景：
server 进程内 HTTP/JSON 层与 SSE 事件桥接（M1 实施，见 roadmap §8.8）；进程级
资源监控改由 Python 侧 psutil 采 g16 进程树实现、不改 HQ（2026-09-22 修订，
见 roadmap §8.4）。
