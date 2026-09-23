"""G16 Web 工作台 · 配置（两级参数全集默认值，单一集中处）。

- 启动级：经环境变量 ``G16WEB_*`` 覆盖，设置面板只读展示。
- 运行级：由 WebUI 设置面板管理（SQLite 持久化，M0 无库则用内存 mock），
  代码默认值集中于本模块（roadmap §2.5 / AGENTS §10）。

路径一律 pathlib.Path；不做硬编码绝对路径。
"""
from __future__ import annotations

import os
from pathlib import Path

# ============================ 启动级参数 ============================
# 前缀统一 G16WEB_（Rust 侧沿用 HQ_）。

BIND_ADDR = os.environ.get("G16WEB_BIND_ADDR", "127.0.0.1")
"""监听地址；只绑回环是安全边界（roadmap §5）。"""

HOME_DIR = Path(os.environ.get("G16WEB_HOME", str(Path.home() / "g16web"))).expanduser()
"""工作区根（单根体系，roadmap §2.4）。"""

PROJECT_ROOT = Path(__file__).resolve().parents[2]
"""仓库根（web/ 的上一级）。"""
CONTRACT_PATH = PROJECT_ROOT / "docs" / "api" / "openapi.yaml"
"""REST 契约唯一事实来源（SSOT）。"""
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
"""前端构建产物目录（B5 静态挂载）。"""

# ============================ 运行级参数 ============================
# 各项语义与范围对齐 roadmap §2.5；运行中由设置面板覆盖。

RUNTIME_DEFAULTS: dict[str, object] = {
    "port": 8300,                      # on_restart；保存后下次重启生效
    "seat_limit": 3,                   # immediate_retroactive；1–10，在途席位上限
    "window_size": 1,                  # immediate；1–6，并行执行数
    "chk_rwf_retention_days": 7,       # 清理保留期
    "stall_threshold_minutes": 10,     # 停滞告警阈值
    "page_size": 50,                   # 分页大小 1–200
    "sse_heartbeat_seconds": 15,       # SSE 心跳间隔
    "link0_nproc": 4,                  # Link0 缺失补齐：CPU 默认值
    "link0_mem_gb": 8,                 # Link0 缺失补齐：内存默认值（GB）
}

# 各级设置的元数据（供 /settings 数据驱动渲染；与 openapi SettingItem 对应）。
# range 为 (min, max) 或 None；value_type 限定 CSS 无关的类型。
STARTUP_SETTINGS: list[dict] = [
    {
        "key": "home_dir",
        "value_type": "string",
        "range": None,
        "editable": False,
        "effect": "immediate",
        "env_var": "G16WEB_HOME",
        "description": "工作区根目录（启动级，只读）",
    },
    {
        "key": "bind_addr",
        "value_type": "string",
        "range": None,
        "editable": False,
        "effect": "on_restart",
        "env_var": "G16WEB_BIND_ADDR",
        "description": "监听地址（启动级，只读；默认绑回环）",
    },
]

_RUNTIME_META = [
    ("port", "integer", (0, 65535), "on_restart", "监听端口（保存后下次重启生效）"),
    ("seat_limit", "integer", (1, 10), "immediate_retroactive", "在途席位上限（调小即反馈挤出）"),
    ("window_size", "integer", (1, 6), "immediate", "并行执行数（执行序列并行窗口）"),
    ("chk_rwf_retention_days", "integer", (0, 365), "immediate", "chk/rwf 文件保留期（天）"),
    ("stall_threshold_minutes", "integer", (1, 1440), "immediate", "停滞告警阈值（分钟无新进度）"),
    ("page_size", "integer", (1, 200), "immediate", "列表分页大小"),
    ("sse_heartbeat_seconds", "integer", (1, 300), "immediate", "SSE 心跳间隔（秒）"),
    ("link0_nproc", "integer", (1, 256), "immediate", "Link0 缺失 %NProcShared 补齐默认值"),
    ("link0_mem_gb", "number", (0, 1024), "immediate", "Link0 缺失 %Mem 补齐默认值（GB）"),
]

RUNTIME_SETTINGS: list[dict] = [
    {
        "key": key,
        "value_type": vtype,
        "range": {"min": rng[0], "max": rng[1]} if rng else None,
        "editable": True,
        "effect": effect,
        "env_var": None,
        "description": desc,
    }
    for key, vtype, rng, effect, desc in _RUNTIME_META
]

SETTINGS_CATALOG: dict[str, dict] = {
    item["key"]: item for item in (STARTUP_SETTINGS + RUNTIME_SETTINGS)
}
"""key -> 设置元数据，供 /settings 校验与渲染。"""


def setting_value(key: str) -> object:
    """取设置当前值（未持久化时回落运行级默认值；启动级直接取值）。"""
    if key in ("home_dir", "bind_addr"):
        return {"home_dir": str(HOME_DIR), "bind_addr": BIND_ADDR}[key]
    return RUNTIME_DEFAULTS.get(key)