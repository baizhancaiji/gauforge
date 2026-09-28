#!/usr/bin/env bash
# GauForge 干净部署包安装脚本：仅需网络；uv 缺失时自动安装。
# 环境变量：GAUFORGE_PIP_INDEX（PyPI 镜像，默认清华）、GAUFORGE_PYTHON（Python 版本，默认 3.10）、
#           GAUFORGE_GH_PROXY（GitHub 代理前缀，默认 v4.gh-proxy.org；uv 安装器与托管
#           Python 解释器的下载源均替换为 {代理}/https://github.com/… 镜像链路）
set -euo pipefail
cd "$(dirname "$0")"

PIP_INDEX="${GAUFORGE_PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
PY_SPEC="${GAUFORGE_PYTHON:-3.10}"
GH_PROXY="${GAUFORGE_GH_PROXY:-https://v4.gh-proxy.org/https://github.com}"

if ! command -v curl >/dev/null 2>&1; then
  echo "[install] 缺少 curl，请先安装（sudo apt install curl）" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[install] 未检测到 uv，自动安装（下载源经 gh-proxy 镜像）…"
  curl -LsSf https://astral.sh/uv/install.sh | \
    env UV_INSTALLER_GITHUB_BASE_URL="$GH_PROXY" sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# 优先系统 Python 3.10+；没有则由 uv 获取托管解释器（下载源经 gh-proxy 镜像）
if command -v python3 >/dev/null 2>&1 && \
   python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  PY_SPEC="$(command -v python3)"
  echo "[install] 使用系统 Python：$PY_SPEC"
else
  echo "[install] 系统无 Python 3.10+，由 uv 经 gh-proxy 镜像获取 $PY_SPEC"
  export UV_PYTHON_INSTALL_MIRROR="$GH_PROXY/astral-sh/python-build-standalone/releases/download"
fi

echo "[install] 创建 .venv 并安装依赖（镜像 $PIP_INDEX）…"
uv venv --python "$PY_SPEC" .venv
uv pip install --python .venv/bin/python -r requirements.txt -i "$PIP_INDEX"

# hq 内核就位：uv run 会把 .venv/bin 置于 PATH，hq_bin() 经 PATH 命中
install -m 755 bin/hq .venv/bin/hq

cat <<'EOF'
[install] 完成。启动：
  nohup uv run python -m web.src.main >>/tmp/g16web-8300.log 2>&1 &
浏览器访问 http://127.0.0.1:8300（首次启动自动拉起 HQ server/worker）。
数据都在工作区 ~/g16web（可用 G16WEB_HOME 改），升级部署目录不影响数据。
G16：在 WebUI 设置页把 g16_root 指向实际发行目录（默认 ~/g16）。
EOF
