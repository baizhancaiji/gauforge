"""集中默认值（B1）：两级参数单一来源。

- 启动级：环境变量覆盖（G16WEB_ 前缀），WebUI 只读展示。
- 运行级：SQLite 持久化（M1 起），WebUI 可编辑；key/effect/range
  与契约 m0-plan §2.2、docs/api/openapi.yaml 逐项对齐。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
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

# ---------- 更新通道默认值（启动级；v2.1.0 功能更新） ----------
# G16WEB_UPDATE_BASE 兼端到端演练口：指向本地 http server 伪装的 release 目录
# 即可离线演练检查/下载链路（测试与演练不触真实网络）。
UPDATE_BASE = os.environ.get(
    "G16WEB_UPDATE_BASE", "https://github.com/baizhancaiji/gauforge")
UPDATE_ASSET = "gauforge-deploy-linux-x64.tar.gz"  # 固定名附件（与 update.sh 同源）
UPDATE_DEFAULT_PROXY = "https://v4.gh-proxy.org"  # 与 update.sh DEFAULT_PROXY 一致
UPDATE_CONNECT_TIMEOUT_S = 15  # 连接超时（与 update.sh --connect-timeout 一致）
UPDATE_READ_TIMEOUT_S = 30  # 读超时

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
    "update_check_interval": "weekly",
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
    {"key": "update_check_interval", "value_type": "string",
     "range": {"enum": ["daily", "weekly", "monthly", "never"]},
     "editable": True, "effect": "immediate", "env_var": None,
     "description": "自动检查更新周期（凌晨 1:00 锚定、错过窗口启动补查；只发现不安装）"},
]

# 未知 key 拒改：白名单 = 目录全部 key（PUT 校验用）。
SETTINGS_CATALOG: dict[str, dict] = {
    m["key"]: m for m in [*STARTUP_SETTINGS, *RUNTIME_SETTINGS]
}

# ---------- UI 偏好（前端视图态持久化键值域；工作区 SQLite ui_prefs 表） ----------
# 键白名单 + 值域单一来源（GET/PUT /ui-preferences 整批校验用），与契约
# UiPreferencesUpdate 描述对齐；未知键/越域值整批拒绝（INVALID_REQUEST）。
_HISTORY_SORTS = frozenset({"submitted_desc", "finished_desc", "finished_asc",
                            "filename_asc", "filename_desc"})
UI_PREF_KEYS: dict[str, frozenset[str]] = {
    "queues.sort": frozenset({"default", "name_asc", "name_desc"}),
    "history.sort": _HISTORY_SORTS,
    "archive.sort": _HISTORY_SORTS,  # 归档页与历史页同组件、键分立各自记忆
}

# 仓库根（部署形态=部署目录；伴生文件/形态判定/hq 定位的基准）。
# 注意三层 parent：CONTRACT_PATH=<仓库根>/docs/api/openapi.yaml。
PROJECT_ROOT = CONTRACT_PATH.parent.parent.parent


# ---------- 版本单一事实来源（v2.1.0 功能更新，version-update-impl-plan B1） ----------
# 三级解析链：部署目录 VERSION 文件 → git describe --tags（源码形态）→
# CHANGELOG.jsonl 最新 released 行兜底；进程启动时一次完成（模块级常量，不做
# 运行时探测）。对外形态带 v 前缀（与部署 VERSION 文件、git tag 同形态）；
# 版本比较与 openapi info.version 派生一律经 bare_version() 取裸版本，
# 消费方不得各自剥离。

logger = logging.getLogger(__name__)

_VERSION_FALLBACK = "v0.0.0+unknown"


def _version_from_file(root: Path) -> str | None:
    """① 部署目录 VERSION 文件（package_release.sh 打包时写入，如 v2.0.0）。"""
    try:
        text = (root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _version_from_git(root: Path) -> str | None:
    """② git describe --tags（源码形态；非 git 仓库或无 tag 时失败）。"""
    try:
        proc = subprocess.run(
            ["git", "describe", "--tags"], cwd=root,
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    out = proc.stdout.strip()
    if proc.returncode != 0 or not out:
        return None
    return out


def _version_from_changelog(root: Path) -> str | None:
    """③ CHANGELOG.jsonl 最新 released 行兜底（append-only 时序，末个 released 即最新）。"""
    latest: str | None = None
    try:
        with (root / "CHANGELOG.jsonl").open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (row.get("status") == "released"
                        and isinstance(row.get("version"), str)):
                    latest = row["version"]
    except OSError:
        return None
    return latest


def resolve_version(root: Path | None = None) -> str:
    """版本三级解析；全链失败兜底 v0.0.0+unknown 并告警，不炸启动。"""
    base = PROJECT_ROOT if root is None else root
    found = (_version_from_file(base) or _version_from_git(base)
             or _version_from_changelog(base))
    if not found:
        logger.warning("版本解析链全部失败（VERSION 文件/git/CHANGELOG 均不可得）")
        return _VERSION_FALLBACK
    found = found.strip()
    return found if found.startswith("v") else f"v{found}"


def bare_version(version: str | None = None) -> str:
    """剥 v 前缀的裸版本：版本比较与 openapi info.version 派生的单点入口。"""
    raw = APP_VERSION if version is None else version
    return raw[1:] if raw.startswith("v") else raw


APP_VERSION = resolve_version()


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
