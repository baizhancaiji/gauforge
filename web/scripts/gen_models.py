#!/usr/bin/env python
"""契约生成链脚本：docs/api/openapi.yaml → web/src/models/（pydantic 模型）。

- SSOT：openapi.yaml 是唯一事实来源；生成产物入库并随契约变更重生成。
- 使用 datamodel-code-generator（dev 依赖，见 m0-plan §4.2）。
- 输出路径参数化：--output 指定，默认 web/src/models/。

用法（项目根）：
    uv run python web/scripts/gen_models.py
    uv run python web/scripts/gen_models.py --output web/src/models --yaml docs/api/openapi.yaml
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# 脚本以根目录运行或 web 包不可导入时，显式把仓库根加入 sys.path。
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from web.src import config  # noqa: E402

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "src" / "models" / "models.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yaml", type=Path, default=config.CONTRACT_PATH,
                        help="openapi 契约路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="生成模型输出文件 (.py)")
    args = parser.parse_args()

    yaml_path = args.yaml.resolve()
    output = args.output.resolve()
    if not yaml_path.exists():
        print(f"契约不存在: {yaml_path}", file=sys.stderr)
        return 2
    if yaml_path.suffix.lower() == ".yaml" or yaml_path.suffix.lower() == ".yml":
        pass  # 兼容
    else:
        print(f"契约须为 yaml: {yaml_path}", file=sys.stderr)
        return 2

    output.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "datamodel_code_generator",
        "--input", str(yaml_path),
        "--input-file-type", "openapi",
        "--output", str(output),
        "--output-model-type", "pydantic_v2.BaseModel",
    ]
    print("生成命令: " + " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())