#!/usr/bin/env bash
# GauForge 全服务停止脚本（一键关闭 WebUI 与 HQ，运维场景）。
#
# 用法: bash stop_all.sh [--port PORT]   （--port 为 WebUI 监听端口，默认 8300）
#
# 警告:与 WebUI 重启/停止不同（§8.7：单独停 WebUI 不杀 HQ），本脚本会一并
# 停止 HQ server/worker——正在运行的 G16 计算任务将被中断，用于彻底停机、
# 释放资源等明确需要全停的运维场景。
#
# 编排（每步 SIGTERM 优雅等待 30s，SIGKILL 兜底，结果逐行打印到 stdout）：
#   1. 停 WebUI（按 --port 定位监听进程；uv run 父进程随之退出）
#   2. 停 HQ worker（cmdline 含 "hq worker start"；先于 server，避免重连风暴）
#   3. 停 HQ server（cmdline 含 "hq server start"；journal 随关闭落盘）
# 先停 WebUI：避免引擎对账/接管逻辑重新拉起 HQ。
set -euo pipefail

PORT="8300"
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    *) echo "未知参数 $1" >&2; exit 2 ;;
  esac
done

TERM_LIMIT=30

# stop_one PID LABEL —— TERM → 等待 → KILL 兜底，返回是否曾经存在
stop_one() {
  local pid="$1" label="$2" waited=0
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "  [$label] pid=$pid 已不存在，跳过"
    return 0
  fi
  kill -TERM "$pid" 2>/dev/null || true
  while kill -0 "$pid" 2>/dev/null; do
    waited=$((waited + 1))
    if [ "$waited" -ge "$TERM_LIMIT" ]; then
      echo "  [$label] pid=$pid SIGTERM ${TERM_LIMIT}s 未退，SIGKILL 兜底"
      kill -KILL "$pid" 2>/dev/null || true
      sleep 1
      break
    fi
    sleep 1
  done
  echo "  [$label] pid=$pid 已停止（等待 ${waited}s）"
}

# stop_pattern PATTERN LABEL —— 对 pgrep -f 命中的全部进程逐个停止
stop_pattern() {
  local pattern="$1" label="$2" pids
  pids="$(pgrep -f "$pattern" || true)"
  if [ -z "$pids" ]; then
    echo "  [$label] 未发现运行中进程"
    return 0
  fi
  local pid
  for pid in $pids; do
    stop_one "$pid" "$label"
  done
}

echo "[stop-all] 1/3 停止 WebUI（端口 $PORT）"
WEBUI_PID="$(ss -tlnp "sport = :$PORT" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1 || true)"
if [ -n "$WEBUI_PID" ]; then
  # systemd 托管进程：直接 TERM 会被 Restart=on-failure 立即拉起，须委托 stop
  UNIT="$(tr '\0' '\n' < "/proc/$WEBUI_PID/environ" 2>/dev/null \
    | sed -n 's/^G16WEB_SERVICE_UNIT=//p' | head -1)" || UNIT=""
  if [ -n "$UNIT" ] && command -v systemctl >/dev/null 2>&1 \
      && XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" \
         systemctl --user stop "$UNIT" 2>/dev/null; then
    echo "  [webui] 已委托 systemd 停止（unit=$UNIT）"
  else
    stop_one "$WEBUI_PID" "webui"
  fi
else
  echo "  [webui] 端口 $PORT 无监听进程，跳过"
fi

echo "[stop-all] 2/3 停止 HQ worker"
stop_pattern "hq worker start" "hq-worker"

echo "[stop-all] 3/3 停止 HQ server"
stop_pattern "hq server start" "hq-server"

echo "[stop-all] 完成"
