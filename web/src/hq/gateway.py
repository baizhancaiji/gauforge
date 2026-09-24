"""HQ Gateway 抽象接口（m1-plan B4）。

统一 CLI（CliGateway）与 HTTP（H 阶段 HttpGateway）两实现的调用面；
事件语义：CLI 侧以轮询 job list 模拟（poll_events 差分），
HTTP 侧对接 SSE 桥接（H3，22 变体映射见 roadmap §8.8）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class GatewayError(RuntimeError):
    """HQ 调用失败（非零退出码/连接不可用/解析失败）。"""


def derive_job_state(stats: dict, cancel_reason: str | None) -> str:
    """task_stats → 单一状态：canceled > failed > finished > running > waiting。"""
    if cancel_reason or stats.get("canceled", 0):
        return "canceled"
    if stats.get("failed", 0):
        return "failed"
    if stats.get("finished", 0) and stats.get("finished") == sum(stats.values()):
        return "finished"
    if stats.get("running", 0):
        return "running"
    return "waiting"


def worker_resources(configuration: dict) -> tuple[int, int]:
    """HQ worker configuration.resources → (cpus, mem_mib)（停等记账用）。

    HQ JSON 形状（crates client/output/json.rs format_resource_descriptor）：
    cpus 为 range 序列化闭区间（--cpus 4 → start=0 end=3），mem 为 sum
    资源（size 即 MiB 数）。CLI 与 HTTP 两实现共用本解析（领域规则集中）。
    """
    cpus = 0
    mem_mib = 0
    for res in (configuration.get("resources") or {}).get("resources", []):
        if res.get("name") == "cpus":
            span = int(res.get("end", 0)) - int(res.get("start", 0)) + 1
            cpus = max(cpus, span)
        elif res.get("name") == "mem":
            mem_mib = max(mem_mib, int(res.get("size") or 0))
    return cpus, mem_mib


class Gateway(ABC):
    """HQ 作业网关抽象。job_id 以字符串承载（HTTP 侧同为不透明 id）。"""

    @abstractmethod
    def submit(self, command: list[str], cwd: str | None = None,
               name: str | None = None, resources: dict | None = None,
               time_limit_s: int = 0) -> str:
        """提交作业（command 为参数列表形式），返回 HQ job id。

        resources（B6 资源双账第二账，roadmap §2.1）：{"cpus": int,
        "mem_mib": int} → HQ 资源请求（%NProcShared→cpus、%Mem GB→MiB）；
        time_limit_s≠0 时设 HQ time_limit（0=不设，默认）。"""

    @abstractmethod
    def cancel(self, job_id: str) -> None:
        """取消作业；不存在/不可取消时抛 GatewayError。"""

    @abstractmethod
    def jobs(self) -> list[dict]:
        """作业概览列表（规整化：id/name/state/task_count/task_stats）。"""

    @abstractmethod
    def workers(self) -> list[dict]:
        """worker 列表（规整化：id/online/hostname/cpus）。"""

    @abstractmethod
    def poll_events(self) -> list[dict]:
        """取自上次调用以来的作业状态变化事件。

        事件形态：{"type": "job_state", "job_id": int,
                   "state": str, "prev_state": str | None}。
        """

    def close(self) -> None:  # noqa: B027 - 可选释放
        """释放底层资源（CLI 实现无常驻资源，HTTP 实现关连接）。"""
