"""集中配置：默认值对齐 prototype/ 的既成事实，环境变量统一 G16WEB_ 前缀覆盖。

跨平台约定（见 AGENTS.md）：路径一律 pathlib.Path，禁止硬编码字符串路径；
环境变量只作覆盖，不要求使用者必须设置。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    hq_bin: Path
    upload_dir: Path
    data_dir: Path
    db_path: Path
    g16_root: Path
    gauss_scrdir: Path


def load(environ: dict[str, str] | None = None) -> Config:
    """按环境变量构建配置；传入 environ 便于测试注入。"""
    env = os.environ if environ is None else environ
    home = Path.home()

    def path(name: str, default: Path) -> Path:
        return Path(env.get(name, str(default)))

    host = env.get("G16WEB_HOST", "127.0.0.1")
    port = int(env.get("G16WEB_PORT", "8160"))
    hq_bin = path("G16WEB_HQ_BIN", home / "opt" / "hyperqueue" / "hq")
    upload_dir = path("G16WEB_UPLOAD_DIR", home / "scratch" / "uploads")
    data_dir = path("G16WEB_DATA_DIR", home / "scratch" / "g16web")
    g16_root = path("G16WEB_G16_ROOT", home / "g16")
    gauss_scrdir = path("G16WEB_GAUSS_SCRDIR", home / "scratch")
    return Config(
        host=host,
        port=port,
        hq_bin=hq_bin,
        upload_dir=upload_dir,
        data_dir=data_dir,
        db_path=data_dir / "g16web.db",
        g16_root=g16_root,
        gauss_scrdir=gauss_scrdir,
    )


CONFIG = load()
