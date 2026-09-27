#!/usr/bin/env bash
# GauForge 升级脚本：从 GitHub Releases 拉最新干净部署包覆盖本目录。
#
# 代理参数（国内网络建议使用）：
#   ./update.sh --proxy                    走默认镜像代理 https://v4.gh-proxy.org/
#   ./update.sh --proxy https://自定义/     自定义代理（需兼容 gh-proxy 的 URL 前缀改写约定）
#   ./update.sh --no-proxy                 直连
#   环境变量 GAUFORGE_PROXY 等效 --proxy <值>
# 选择持久化到 .update-proxy，之后不带参数沿用上次选择；--check 只查远端版本。
set -euo pipefail
cd "$(dirname "$0")"

OWNER="baizhancaiji"
REPO="gauforge"
ASSET="gauforge-deploy-linux-x64.tar.gz"
DEFAULT_PROXY="https://v4.gh-proxy.org"
CONF=".update-proxy"

mode="apply"
proxy=""
[ -f "$CONF" ] && proxy="$(cat "$CONF")"
while [ $# -gt 0 ]; do
  case "$1" in
    --proxy)
      shift
      if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then proxy="$1"; shift
      else proxy="$DEFAULT_PROXY"; fi
      ;;
    --no-proxy) proxy=""; shift ;;
    --check) mode="check"; shift ;;
    *) echo "未知参数: $1（可用 --proxy [URL] / --no-proxy / --check）" >&2; exit 2 ;;
  esac
done
printf '%s' "$proxy" > "$CONF"

base="https://github.com/$OWNER/$REPO"
[ -n "$proxy" ] && base="${proxy%/}/$base"

fetch() {
  curl -fSL --retry 3 --connect-timeout 15 -o "$2" "$1" || {
    echo "[update] 下载失败：$1（当前通道：${proxy:-直连}；国内网络可试 --proxy）" >&2
    exit 1
  }
}

if [ "$mode" = "check" ]; then
  fetch "$base/releases/latest/download/VERSION" /tmp/gauforge-remote-VERSION
  echo "[update] 远端最新：$(cat /tmp/gauforge-remote-VERSION)；当前：$(cat VERSION 2>/dev/null || echo 未知)"
  exit 0
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "[update] 下载最新包（通道：${proxy:-直连}）…"
fetch "$base/releases/latest/download/$ASSET.sha256" "$tmp/$ASSET.sha256"
fetch "$base/releases/latest/download/$ASSET" "$tmp/$ASSET"
( cd "$tmp" && sha256sum -c "$ASSET.sha256" >/dev/null && echo "[update] 校验通过" )

mkdir -p "$tmp/unpack"
tar -xzf "$tmp/$ASSET" -C "$tmp/unpack"
src="$tmp/unpack/gauforge"
[ -d "$src/web/src" ] || { echo "[update] 包结构异常，中止" >&2; exit 1; }

# 覆盖代码与产物（包内不含 .venv / .update-proxy，本目录二者不受影响）
cp -a "$src/web" "$src/docs" .
install -m 644 "$src/requirements.txt" "$src/VERSION" "$src/README.md" "$src/CHANGELOG.md" "$src/LICENSE" .
install -d crates
install -m 644 "$src/crates/LICENSE" crates/LICENSE   # 保持 crates/ 路径：与根 LICENSE 基本名冲突
install -d bin
install -m 755 "$src/bin/hq" bin/hq

[ -d .venv ] || { echo "[update] 未发现 .venv，请先运行 ./install.sh" >&2; exit 1; }
echo "[update] 差量刷新依赖…"
uv pip install --python .venv/bin/python -r requirements.txt \
  -i "${GAUFORGE_PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
install -m 755 bin/hq .venv/bin/hq

echo "[update] 已升级到 $(cat VERSION)。重启服务生效：先停旧进程，再跑启动命令（见 docs/references/deployment.md）。"
