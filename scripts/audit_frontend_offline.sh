#!/usr/bin/env bash
# 外链审计闸门（m3-plan §2.5/§4.9 C1）：扫描前端构建产物中的 http(s) 资源引用，
# 命中即非零退出——「构建产物运行时零外链」的静态保证（AGENTS.md §6.3 闸门；
# 前端改动批次与 D1 收口必跑）。
#
# 扫描对象：dist 目录全部 html/js/css 文本产物；豁免仅限「非资源引用」：
#   - 注释与 license 文本（先剥离再扫描）；
#   - 命名空间标识、错误消息文档串、用户主动外跳链接等，见 ALLOW_PREFIXES
#     逐项理由。新增豁免必须在本脚本登记理由，禁止在产物侧绕过。
# 已知包内置可选在线数据源（如 3dmol 的 RCSB/PubChem 抓取分支）若进产物，
# 属资源引用、不在豁免面——须以摇树/替换方式消除后复扫（C4 实施时核对）。
#
# 用法：scripts/audit_frontend_offline.sh [dist目录]（缺省 web/frontend/dist）

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${1:-$ROOT/web/frontend/dist}"

if [ ! -d "$DIST" ]; then
  echo "audit_frontend_offline: 构建产物不存在：$DIST（先在 web/frontend 执行 npm run build）" >&2
  exit 2
fi

# 非资源引用白名单（前缀匹配；每项须附非资源理由）
ALLOW_PREFIXES=(
  "http://www.w3.org/"                       # SVG/MathML/HTML 命名空间标识（标识符，不发请求）
  "https://vuejs.org/"                       # Vue 运行时错误消息附带的文档链接（仅控制台文案）
  "https://github.com/baizhancaiji/gauforge" # 更新卡「查看更新说明」锚链接（用户主动点击外跳，非资源加载）
  "https://v4.gh-proxy.org"                  # 更新代理默认值（用户可配数据串，非构建期资源）
  "https://github.com/ecomfe/"               # zrender/echarts 的 license 横幅文本
                                             # （/*! */ 注释随 tree-shaking 保留在 chunk 中部，
                                             #   文件头横幅剥离覆盖不到，C3 实证登记）
)

# 只豁免文件头部的 license 横幅（/*! ... */ 与 //! 行，打包器保留在产物
# 开头）；文件中部的 /* 一律不剥离——minified 代码的字符串里可能出现
# "/*" 序列，整文件块注释剥离会造成漏报（3dmol 打包探针实证）。
strip_and_extract() {
  perl -0777 -pe '
    s{\A(?:\s|/\*!.*?\*/|//![^\n]*\n?)+}{};
  ' "$1" \
    | grep -ohE 'https?://[^"'"'"'`<>()[[:space:]]+' || true
}

violations=0
while IFS= read -r -d '' file; do
  while IFS= read -r url; do
    [ -n "$url" ] || continue
    allowed=""
    for prefix in "${ALLOW_PREFIXES[@]}"; do
      case "$url" in
        "$prefix"*) allowed=1; break ;;
      esac
    done
    if [ -z "$allowed" ]; then
      if [ "$violations" -eq 0 ]; then
        echo "audit_frontend_offline: 发现外链资源引用（豁免白名单外）："
      fi
      echo "  ${file#"$DIST"/} : $url"
      violations=$((violations + 1))
    fi
  done < <(strip_and_extract "$file")
done < <(find "$DIST" -type f \( -name '*.js' -o -name '*.css' -o -name '*.html' \) -print0 | sort -z)

if [ "$violations" -gt 0 ]; then
  echo "audit_frontend_offline: 共 $violations 处外链引用 — 构建产物不满足离线约束" >&2
  exit 1
fi
echo "audit_frontend_offline: $DIST 零外链资源引用（豁免 $(( ${#ALLOW_PREFIXES[@]} )) 组白名单前缀）"
