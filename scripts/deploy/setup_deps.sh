#!/usr/bin/env bash
# GauForge 第三方依赖安装：crest 3.0.2（组合流运行必需）+ xtb 6.7.1（可选）。
#
# 组合流（构象搜索 + 精修）的运行必需项仅 crest 一个二进制：crest 3.0.2
# 静态内嵌 tblite，运行时不消费 XTB_PATH；xtb 为可选安装（xtb_root 仅为
# 未来独立 xtb 计算的定位锚），不装不影响组合流。本脚本不随部署包分发
# 第三方二进制（体积/许可/平台锁定），仅引导下载安装。
#
# 用法：
#   ./setup_deps.sh                    安装 crest 到 ~/opt
#   ./setup_deps.sh --dest /data/opt   自定义安装根目录（须同步改设置页 crest_root/xtb_root）
#   ./setup_deps.sh --xtb              同时安装 xtb 6.7.1（可选）
#   ./setup_deps.sh --proxy [URL]      经代理下载（默认 https://v4.gh-proxy.org，
#                                      需兼容 gh-proxy 的 URL 前缀改写约定）
#   ./setup_deps.sh --no-proxy         直连
#   ./setup_deps.sh --force            已安装（冒烟通过）也强制重装
#   环境变量 GAUFORGE_PROXY 等效 --proxy <值>（与 update.sh 同约定，两参数
#   均不持久化——本脚本无 update 通道语义）
#
# 幂等：目标二进制 --version 冒烟通过即视为已安装、跳过（仅目录存在不算）；
# 目录存在但冒烟失败视为半成品残留，清理后重装。
# 校验：xtb 下载后与上游官方 .sha256 对照；crest 上游未发布校验和文件，
# 按发布 tag 与资产字节数对照（口径见 docs/plans/m4-combo-template-deploy-plan.md
# 附录 B D4）。
# 安装后在线/离线路径与验证闭环见 docs/references/deployment.md「CREST/xtb 接入」节。
set -euo pipefail

CREST_VERSION="3.0.2"
XTB_VERSION="6.7.1"
CREST_ASSET="crest-gnu-12-ubuntu-latest.tar.xz"
XTB_ASSET="xtb-${XTB_VERSION}-linux-x86_64.tar.xz"
CREST_URL="https://github.com/crest-lab/crest/releases/download/v${CREST_VERSION}/${CREST_ASSET}"
XTB_URL="https://github.com/grimme-lab/xtb/releases/download/v${XTB_VERSION}/${XTB_ASSET}"
# 实测 2026-10-14（GitHub Release API）；上游无校验和文件，以字节数对照
CREST_SIZE_EXPECT="${GAUFORGE_CREST_SIZE:-8764012}"
DEFAULT_PROXY="https://v4.gh-proxy.org"

dest="$HOME/opt"
proxy="${GAUFORGE_PROXY:-}"
want_xtb=0
force=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dest) dest="$2"; shift 2 ;;
    --xtb) want_xtb=1; shift ;;
    --force) force=1; shift ;;
    --proxy)
      shift
      if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then proxy="$1"; shift
      else proxy="$DEFAULT_PROXY"; fi
      ;;
    --no-proxy) proxy=""; shift ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数: $1（可用 --dest DIR / --xtb / --proxy [URL] / --no-proxy / --force）" >&2; exit 2 ;;
  esac
done
dest="${dest/#\~/$HOME}"
mkdir -p "$dest"

crest_dir="$dest/crest-$CREST_VERSION"
crest_bin="$crest_dir/crest"
xtb_dir="$dest/xtb-$XTB_VERSION"
xtb_bin="$xtb_dir/bin/xtb"

fetch() { # $1=url  $2=输出路径
  curl -fSL --retry 3 --connect-timeout 15 -o "$2" "$1" || {
    echo "[setup] 下载失败：$1（当前通道：${proxy:-直连}）" >&2
    echo "[setup] 可试 --proxy 重试或 --no-proxy 直连；仍不可达走离线手动路径" >&2
    echo "[setup] （手动下载后解压布局见 docs/references/deployment.md「CREST/xtb 接入」节）" >&2
    exit 1
  }
}

rewrite() { # $1=原始 URL → 按代理约定前缀改写
  if [ -n "$proxy" ]; then echo "${proxy%/}/$1"; else echo "$1"; fi
}

# 幂等判据：--version 冒烟通过方视为已安装（仅目录存在不算）
smoke() { # $1=二进制  $2=期望输出子串
  [ -x "$1" ] && "$1" --version 2>/dev/null | grep -q "$2"
}

install_crest() {
  if smoke "$crest_bin" "crest"; then
    if [ "$force" -eq 0 ]; then
      echo "[setup] crest $CREST_VERSION 已安装（冒烟通过），跳过：$crest_bin"
      return 0
    fi
    echo "[setup] --force 重装 crest $CREST_VERSION"
  elif [ -d "$crest_dir" ]; then
    echo "[setup] 发现半成品残留（$crest_dir 冒烟不通过），清理后重装"
    rm -rf "$crest_dir"
  fi
  tmp="$(mktemp -d)"
  trap 'rm -rf "${tmp:-}"' EXIT
  echo "[setup] 下载 crest $CREST_VERSION（通道：${proxy:-直连}）…"
  fetch "$(rewrite "$CREST_URL")" "$tmp/$CREST_ASSET"
  size="$(stat -c%s "$tmp/$CREST_ASSET")"
  if [ "$size" != "$CREST_SIZE_EXPECT" ]; then
    echo "[setup] crest 资产体积与发布不符（期望 $CREST_SIZE_EXPECT 字节，实际 $size）——下载不完整或上游资产变更，中止" >&2
    exit 1
  fi
  echo "[setup] 解压到 $crest_dir …"
  mkdir -p "$crest_dir"
  tar -xJf "$tmp/$CREST_ASSET" -C "$crest_dir"
  # 上游 tar 顶层为 crest/ 目录（实测 2026-10-14）：内容上移一层，布局
  # 对齐运行级 crest_root 语义（<crest_root>/crest 即二进制）；平铺形资产
  # 此分支不触发、同样兼容。先整体改名再取内容——内层二进制与顶层目录
  # 同名（crest/crest），直接 mv 会被目录自身挡路
  if [ -d "$crest_dir/crest" ]; then
    mv "$crest_dir/crest" "$crest_dir/.crest-inner"
    mv "$crest_dir/.crest-inner"/* "$crest_dir/"
    rmdir "$crest_dir/.crest-inner"
  fi
  chmod +x "$crest_dir"/* 2>/dev/null || true
  rm -rf "$tmp"
  trap - EXIT
  smoke "$crest_bin" "crest" || {
    echo "[setup] crest 安装后冒烟失败（$crest_bin --version），安装异常中止" >&2
    exit 1
  }
  echo "[setup] crest $CREST_VERSION 安装完成：$crest_bin"
}

install_xtb() {
  if smoke "$xtb_bin" "xtb version"; then
    if [ "$force" -eq 0 ]; then
      echo "[setup] xtb $XTB_VERSION 已安装（冒烟通过），跳过：$xtb_bin"
      return 0
    fi
    echo "[setup] --force 重装 xtb $XTB_VERSION"
  elif [ -d "$xtb_dir" ]; then
    echo "[setup] 发现半成品残留（$xtb_dir 冒烟不通过），清理后重装"
    rm -rf "$xtb_dir"
  fi
  tmp="$(mktemp -d)"
  trap 'rm -rf "${tmp:-}"' EXIT
  echo "[setup] 下载 xtb $XTB_VERSION（通道：${proxy:-直连}）…"
  fetch "$(rewrite "$XTB_URL")" "$tmp/$XTB_ASSET"
  fetch "$(rewrite "${XTB_URL}.sha256")" "$tmp/$XTB_ASSET.sha256"
  ( cd "$tmp" && sha256sum -c "$XTB_ASSET.sha256" >/dev/null \
      && echo "[setup] xtb 官方校验和通过" )
  mkdir -p "$tmp/unpack"
  tar -xJf "$tmp/$XTB_ASSET" -C "$tmp/unpack"
  mkdir -p "$xtb_dir"
  # 上游 tar 顶层为 xtb-dist/ 目录（实测 2026-10-14）：内容落到 xtb-6.7.1/
  # 布局，对齐运行级 xtb_root 语义（<xtb_root>/bin/xtb）；平铺形资产同兼容
  if [ -d "$tmp/unpack/xtb-dist" ]; then
    mv "$tmp/unpack/xtb-dist"/* "$xtb_dir/"
  else
    mv "$tmp/unpack"/* "$xtb_dir/"
  fi
  chmod +x "$xtb_dir"/bin/* 2>/dev/null || true
  rm -rf "$tmp"
  trap - EXIT
  smoke "$xtb_bin" "xtb version" || {
    echo "[setup] xtb 安装后冒烟失败（$xtb_bin --version），安装异常中止" >&2
    exit 1
  }
  echo "[setup] xtb $XTB_VERSION 安装完成：$xtb_bin（可选组件——crest 3.0.2 已内嵌 tblite，组合流运行无需 xtb）"
}

install_crest
[ "$want_xtb" -eq 1 ] && install_xtb

echo "[setup] —— 设置页指引 ——"
echo "[setup] crest_root = $crest_dir（组合流运行必需；默认布局 ~/opt/crest-$CREST_VERSION 零配置可用）"
if [ "$want_xtb" -eq 1 ]; then
  echo "[setup] xtb_root   = $xtb_dir（可选；默认布局 ~/opt/xtb-$XTB_VERSION 零配置可用）"
fi
if [ "$dest" != "$HOME/opt" ]; then
  echo "[setup] 自定义安装路径：请在 WebUI 设置页把运行级参数 crest_root$([ "$want_xtb" -eq 1 ] && echo '/xtb_root') 指向上述目录（保存后对新任务生效）"
fi
echo "[setup] 验证闭环（组合流 503 → 部署 → 提交通过）与离线手动路径：见 docs/references/deployment.md「CREST/xtb 接入」节"
