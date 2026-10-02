"""服务重启编排（用户验收反馈：设置页一键重启 + 手动运维脚本两用）。

受理即 detached 拉起重启脚本（先快照当前进程 cmdline/environ/cwd 与监听
端口），随后延迟 SIGTERM 优雅自退；脚本等进程退出与端口释放后按快照原
命令/环境/工作目录重新拉起并探活。HQ server/worker 全程不受影响（§8.7
红线：g16web 死亡不影响在跑计算，重启后启动序列对账接管）。与更新流程
互斥（复用 UPDATE_IN_PROGRESS）：更新流水线进行中拒绝重启，避免 SIGTERM
打断下载/解压编排。
"""
from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

from .. import config
from ..errors import err
from . import update as update_svc

RESTART_LOG = "restart.log"
SELF_TERMINATE_DELAY_S = 1.0  # 等 202 响应 flush 后再 SIGTERM（uvicorn 优雅关停）
MSG_ACCEPTED = "服务重启已受理，页面将短暂失联并自动恢复。"
MSG_UPDATE_IN_FLIGHT = "更新流程进行中，暂不能重启。"


def script_path() -> Path:
    """重启脚本定位：部署形态（根 restart_g16web.sh，随发布包落位）优先，
    源码形态回落 scripts/deploy/。"""
    root: Path = config.PROJECT_ROOT
    for cand in (root / "restart_g16web.sh",
                 root / "scripts" / "deploy" / "restart_g16web.sh"):
        if cand.is_file():
            return cand
    raise FileNotFoundError("重启脚本缺失（restart_g16web.sh）")


def _popen(*args: object, **kwargs: object) -> subprocess.Popen:
    return subprocess.Popen(*args, **kwargs)  # type: ignore[arg-type]


def launch_script() -> Path:
    """detached 拉起重启脚本（stdout/stderr 追加 restart.log，环境原样
    继承——G16WEB_HOME 等启动级变量随之保持）；不杀进程，脚本负责 SIGTERM
    本进程并按快照复原拉回。返回脚本路径（测试断言用）。"""
    script = script_path()
    log_path = config.PROJECT_ROOT / RESTART_LOG
    with log_path.open("ab") as log:
        _popen(["bash", str(script), "--pid", str(os.getpid()),
                "--log", str(log_path)],
               cwd=str(config.PROJECT_ROOT), stdin=subprocess.DEVNULL,
               stdout=log, stderr=log, start_new_session=True)
    return script


def self_terminate() -> None:
    """SIGTERM 本进程：uvicorn 优雅关停（lifespan 摘引擎单例，不杀 HQ）。"""
    os.kill(os.getpid(), signal.SIGTERM)


def schedule_self_terminate(delay: float = SELF_TERMINATE_DELAY_S) -> None:
    """事件循环延迟自退：先让 202 响应 flush，再 SIGTERM（响应先行）。"""
    import asyncio
    loop = asyncio.get_running_loop()
    loop.call_later(delay, self_terminate)


def guard() -> None:
    """重启守卫：更新流程进行中拒绝（UPDATE_IN_PROGRESS，复用既有码）。"""
    if update_svc.get_service().phase in update_svc.IN_FLIGHT_PHASES:
        raise err("UPDATE_IN_PROGRESS", MSG_UPDATE_IN_FLIGHT, http=409)
