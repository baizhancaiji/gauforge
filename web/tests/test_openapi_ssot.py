"""契约生成链 SSOT 测试（m0-plan §4.3 test_openapi_ssot.py）。

- /openapi.json 与落盘 docs/api/openapi.yaml 等价（后端对外暴露契约原文）。
- models/ 生成产物与 yaml 重生成无 diff（防手改漂移）。生成器输出含
  时间戳注释，比较时剥离，只比对模型代码实质。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from web.src import config
from web.src.main import app

client = TestClient(app)

_TS_RE = re.compile(br"timestamp: .*\n")


def _norm(data: bytes) -> bytes:
    """剥离生成器动态时间戳，仅比实质代码。"""
    return _TS_RE.sub(b"", data)


def test_openapi_json_equals_contract_yaml():
    served = client.get("/openapi.json").json()
    with config.CONTRACT_PATH.open(encoding="utf-8") as fh:
        disk = yaml.safe_load(fh)
    assert served == disk, "/openapi.json 应回读落盘契约，不得与契约漂移"


def test_models_regenerate_no_diff(tmp_path):
    """再生产物与入库产物比对零差异（时间戳剥离）。

    生成写入 tmp_path 再比对：测试不得改写工作区，原「原地再生后自比较」
    实现会在每次 pytest 后给 models.py 留下时间戳脏差异（测试污染源）。"""
    script = Path(__file__).resolve().parents[1] / "scripts" / "gen_models.py"
    out_file = Path(__file__).resolve().parents[1] / "src" / "models" / "models.py"
    regen = tmp_path / "models.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--output", str(regen)],
        cwd=config.PROJECT_ROOT, capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"gen_models 失败:\n{proc.stderr}"
    assert _norm(regen.read_bytes()) == _norm(out_file.read_bytes()), \
        "models/ 生成产物与当前契约不一致（请重跑 gen_models.py）"