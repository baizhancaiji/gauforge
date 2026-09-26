"""集中默认值（B1）：两级参数单一来源。

- 启动级：环境变量覆盖（G16WEB_ 前缀），WebUI 只读展示。
- 运行级：SQLite 持久化（M1 起），WebUI 可编辑；key/effect/range
  与契约 m0-plan §2.2、docs/api/openapi.yaml 逐项对齐。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

# ---------- 启动级（环境变量覆盖；WebUI 只读） ----------
HOME_DIR = Path(os.environ.get("G16WEB_HOME", "~/g16web")).expanduser()
BIND_ADDR = os.environ.get("G16WEB_BIND_ADDR", "127.0.0.1")
# 派发引擎开关（启动级）：G16WEB_ENGINE=0 关闭（契约测试与 M0 演示模式）
ENGINE_ENABLED = os.environ.get("G16WEB_ENGINE", "1") != "0"
# HQ HTTP 桥端口（启动级，G16WEB_HQ_HTTP_PORT）：0 = 关闭（默认，HQ 行为零变化）；
# >0 时 server 侧追加 --http-port 并由 Gateway 工厂优先选择 HttpGateway
HQ_HTTP_PORT = int(os.environ.get("G16WEB_HQ_HTTP_PORT", "0") or 0)
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
CONTRACT_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "api" / "openapi.yaml"

# ---------- 运行级默认值（契约 §2.2 运行级参数表） ----------
RUNTIME_DEFAULTS: dict[str, object] = {
    "listen_port": 8300,
    "pending_seat_limit": 3,
    "parallel_window": 1,
    "chk_rwf_retention_days": 7,
    "stall_threshold_minutes": 10,
    "page_size": 50,
    "sse_heartbeat_seconds": 15,
    "link0_default_nproc": 4,
    "link0_default_mem_gb": 8,
    "g16_root": "~/g16",
}

# ---------- 设置目录（数据驱动渲染元数据） ----------
STARTUP_SETTINGS: list[dict] = [
    {"key": "workspace_root", "value_type": "string", "range": None,
     "editable": False, "effect": "on_restart", "env_var": "G16WEB_HOME",
     "description": "工作区根目录（任务/结果/归档布局）"},
    {"key": "bind_address", "value_type": "string", "range": None,
     "editable": False, "effect": "on_restart", "env_var": "G16WEB_BIND_ADDR",
     "description": "监听地址"},
]

RUNTIME_SETTINGS: list[dict] = [
    {"key": "listen_port", "value_type": "integer",
     "range": {"min": 1, "max": 65535},
     "editable": True, "effect": "on_restart", "env_var": None,
     "description": "监听端口（保存后重启生效）"},
    {"key": "pending_seat_limit", "value_type": "integer",
     "range": {"min": 1, "max": 10},
     "editable": True, "effect": "immediate_retroactive", "env_var": None,
     "description": "待执行席位数上限（对已有席位追溯生效）"},
    {"key": "parallel_window", "value_type": "integer",
     "range": {"min": 1, "max": 6},
     "editable": True, "effect": "new_submissions", "env_var": None,
     "description": "并行执行窗口（在跑不追溯，窗口按新值收敛）"},
    {"key": "chk_rwf_retention_days", "value_type": "integer",
     "range": {"min": 1, "max": 365},
     "editable": True, "effect": "new_submissions", "env_var": None,
     "description": "chk/rwf 保留天数（仅对其后新任务生效）"},
    {"key": "stall_threshold_minutes", "value_type": "integer",
     "range": {"min": 1, "max": 1440},
     "editable": True, "effect": "new_submissions", "env_var": None,
     "description": "停滞告警阈值分钟数（仅对其后新任务生效）"},
    {"key": "page_size", "value_type": "integer",
     "range": {"min": 1, "max": 200},
     "editable": True, "effect": "immediate", "env_var": None,
     "description": "列表分页大小（候选/队列/历史页统一）"},
    {"key": "sse_heartbeat_seconds", "value_type": "integer",
     "range": {"min": 5, "max": 300},
     "editable": True, "effect": "immediate", "env_var": None,
     "description": "SSE 心跳间隔秒数"},
    {"key": "link0_default_nproc", "value_type": "integer",
     "range": {"min": 1, "max": 256},
     "editable": True, "effect": "new_submissions", "env_var": None,
     "description": "Link0 %NProcShared 缺省值（仅对其后新任务生效）"},
    {"key": "link0_default_mem_gb", "value_type": "number",
     "range": {"min": 1, "max": 1024},
     "editable": True, "effect": "new_submissions", "env_var": None,
     "description": "Link0 %Mem 缺省值 GB（仅对其后新任务生效）"},
    {"key": "g16_root", "value_type": "string", "range": None,
     "editable": True, "effect": "new_submissions", "env_var": None,
     "description": "G16 发行目录（g16root 布局；仅对其后新任务生效）"},
]

# 未知 key 拒改：白名单 = 目录全部 key（PUT 校验用）。
SETTINGS_CATALOG: dict[str, dict] = {
    m["key"]: m for m in [*STARTUP_SETTINGS, *RUNTIME_SETTINGS]
}

# 仓库根（SSOT 测试等以仓库根为工作目录跑生成命令）。
PROJECT_ROOT = CONTRACT_PATH.parent.parent


def setting_value(key: str) -> object:
    """启动级参数当前值（环境变量已解析）。"""
    return {"workspace_root": str(HOME_DIR),
            "bind_address": BIND_ADDR}.get(key)


def hq_bin() -> str:
    """HQ 可执行定位（启动序列用）：环境变量 > PATH > 仓库构建产物。"""
    env = os.environ.get("G16WEB_HQ_BIN")
    if env:
        return env
    found = shutil.which("hq")
    if found:
        return found
    return str(PROJECT_ROOT / "target" / "release" / "hq")
