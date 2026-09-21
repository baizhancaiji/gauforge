"""g16web/src/config.py 的默认值与环境变量覆盖行为。"""
from pathlib import Path

from config import load


def test_defaults():
    cfg = load(environ={})
    home = Path.home()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8160
    assert cfg.hq_bin == home / "opt" / "hyperqueue" / "hq"
    assert cfg.upload_dir == home / "scratch" / "uploads"
    assert cfg.data_dir == home / "scratch" / "g16web"
    assert cfg.db_path == cfg.data_dir / "g16web.db"
    assert cfg.g16_root == home / "g16"
    assert cfg.gauss_scrdir == home / "scratch"


def test_env_override():
    cfg = load(
        environ={
            "G16WEB_HOST": "0.0.0.0",
            "G16WEB_PORT": "9000",
            "G16WEB_HQ_BIN": "/usr/local/bin/hq",
            "G16WEB_DATA_DIR": "/tmp/g16web-data",
        }
    )
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 9000
    assert cfg.hq_bin == Path("/usr/local/bin/hq")
    assert cfg.data_dir == Path("/tmp/g16web-data")
    # 未覆盖的项回落默认值
    assert cfg.upload_dir == Path.home() / "scratch" / "uploads"
