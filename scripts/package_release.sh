#!/usr/bin/env bash
# 构建干净部署包（linux-x64）：预构建前端 + 预编译内核 + Python 源码 → tar.gz。
# 用户侧只需 Python 3.10+（uv 自管），无需 Rust/Node/构建工具链。
#
# 用法：scripts/package_release.sh [<tag>] [-o 输出目录] [--upload]
#   <tag>       发布 tag（如 v2.0.0）；省略时打包当前 HEAD（版本号取 git describe，
#               仅用于本地验证，不得上传）
#   -o|--out    输出目录（默认 target/deploy，gitignored）
#   --upload    用 gh CLI 创建/复用 Release 并上传全部附件
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

tag=""
out="target/deploy"
upload=0
while [ $# -gt 0 ]; do
  case "$1" in
    -o|--out) out="$2"; shift 2 ;;
    --upload) upload=1; shift ;;
    *) tag="$1"; shift ;;
  esac
done

git diff --quiet || { echo "工作区不干净，先提交再打包" >&2; exit 1; }
if [ -n "$tag" ]; then
  [ "$(git rev-parse HEAD)" = "$(git rev-parse "$tag^{commit}")" ] || {
    echo "HEAD 不是 $tag，请先 git checkout $tag 再打包" >&2
    exit 1
  }
  version="$tag"
else
  version="$(git describe --tags --always)"
  echo "[package] 未指定 tag：按当前 HEAD 打验证包（$version），不得上传"
fi

echo "[package] 前端构建…"
(cd web/frontend && npm install --silent && npm run build)
echo "[package] 内核构建…"
# highs-sys 构建需要 cmake/libclang：.envrc 指向 .venv 内工具链（见 development.md §1.2）
[ -f .envrc ] && source .envrc
cargo build --release

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
pkg="$stage/gauforge"
mkdir -p "$pkg/bin" "$pkg/web/frontend" "$pkg/docs"

cp -a web/src "$pkg/web/src"
cp -a web/frontend/dist "$pkg/web/frontend/dist"
cp -a docs/api "$pkg/docs/api"
install -m 644 requirements.txt LICENSE README.md CHANGELOG.md "$pkg/"
install -d "$pkg/crates"
install -m 644 crates/LICENSE "$pkg/crates/LICENSE"   # 保持 crates/ 路径：与根 LICENSE 基本名冲突
install -m 755 target/release/hq "$pkg/bin/hq"
install -m 755 scripts/deploy/install.sh scripts/deploy/update.sh \
  scripts/deploy/self_update.sh scripts/deploy/restart_g16web.sh \
  scripts/deploy/stop_all.sh scripts/deploy/systemd_install.sh "$pkg/"
printf '%s\n' "$version" > "$pkg/VERSION"

mkdir -p "$out"
name="gauforge-deploy-$version-linux-x64"
tar -czf "$out/$name.tar.gz" -C "$stage" gauforge
( cd "$out" && sha256sum "$name.tar.gz" > "$name.tar.gz.sha256" )

# 固定名附件：update.sh 经 releases/latest/download 直取（不含版本号）
ASSET_FIXED="gauforge-deploy-linux-x64.tar.gz"
cp "$out/$name.tar.gz" "$out/$ASSET_FIXED"
( cd "$out" && sha256sum "$ASSET_FIXED" > "$ASSET_FIXED.sha256" )
printf '%s\n' "$version" > "$out/VERSION"

if [ "$upload" = "1" ]; then
  [ -n "$tag" ] || { echo "验证包不得上传" >&2; exit 1; }
  command -v gh >/dev/null 2>&1 || { echo "未安装 gh CLI，无法上传" >&2; exit 1; }
  gh release create "$tag" \
    "$out/$name.tar.gz" "$out/$name.tar.gz.sha256" \
    "$out/$ASSET_FIXED" "$out/$ASSET_FIXED.sha256" \
    "$out/VERSION" \
    --title "GauForge $tag" --generate-notes
fi

echo "[package] 完成："
ls -lh "$out" | grep -v '^total\|^d'
echo "[package] 附件清单（--upload 已传/未传待传）：$name.tar.gz(+.sha256)、$ASSET_FIXED(+.sha256)、VERSION"
