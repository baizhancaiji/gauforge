#!/usr/bin/env bash
# GauForge 服务重启脚本（WebUI 一键重启与手动运维两用）。
#
# 由 POST /system/restart detached 拉起（--pid/--log 由端点传入），亦可手动：
#   bash restart_g16web.sh [--pid PID | --port PORT] [--log PATH]
#   （--port 按 SQLite 端口定位监听进程，默认 8300；--log 缺省 ./restart-g16web.log）
#
# 编排（不碰 HQ server/worker，§8.7：计算任务不受 WebUI 重启影响）：
#   1. 定位目标进程（--pid 优先；否则按 --port 经 ss 定位监听进程）
#   2. 快照 /proc/<pid> 的 cmdline/environ 原文（NUL 分隔，参数可含空格换行）
#      与 cwd、实际监听端口——SIGTERM 后 /proc 不可读，复原依据必须先取
#   3. SIGTERM 优雅停止（uv run 父进程随子进程退出；上限 30s，兜底 SIGKILL）
#   4. 等待端口释放（上限 30s）
#   5. 按快照原命令/环境/工作目录重新拉起（脱离会话，日志追加；内联 python
#      处理 NUL 分隔，免 shell 转义歧义）
#   6. 探活 /api/v1/system/health（上限 60s），成败均记日志
set -euo pipefail

PID_ARG=""
PORT_ARG=""
LOG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --pid)  PID_ARG="$2";  shift 2 ;;
    --port) PORT_ARG="$2"; shift 2 ;;
    --log)  LOG="$2";      shift 2 ;;
    *) echo "未知参数 $1" >&2; exit 2 ;;
  esac
done
LOG="${LOG:-./restart-g16web.log}"
log() { echo "[$(date '+%F %T')] [restart] $*" >> "$LOG"; }

# ---------- 1. 定位目标进程 ----------
if [ -n "$PID_ARG" ]; then
  PID="$PID_ARG"
else
  LOCATE_PORT="${PORT_ARG:-8300}"
  PID="$(ss -tlnp "sport = :$LOCATE_PORT" 2>/dev/null \
    | grep -oP 'pid=\K[0-9]+' | head -1 || true)"
  if [ -z "$PID" ]; then
    log "按端口 $LOCATE_PORT 未定位到监听进程，中止"
    echo "[restart] 按端口 $LOCATE_PORT 未定位到监听进程，中止（详见 $LOG）" >&2
    exit 1
  fi
fi
if [ ! -d "/proc/$PID" ]; then
  log "进程 $PID 不存在，中止"
  exit 1
fi

# ---------- 2. 快照（复原依据；NUL 原文不经文本转手） ----------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp "/proc/$PID/cmdline" "$TMP/cmdline"
cp "/proc/$PID/environ" "$TMP/environ"
readlink "/proc/$PID/cwd" > "$TMP/cwd"
PORT="$(ss -tlnp 2>/dev/null | grep "pid=$PID," | grep -oP ':\K[0-9]+' | head -1 || true)"
log "快照完成（pid=$PID port=${PORT:-?} cwd=$(cat "$TMP/cwd")）"

# ---------- 3. 优雅停止（端点拉起场景由本脚本负责 TERM） ----------
kill -TERM "$PID" 2>/dev/null || true
waited=0
while kill -0 "$PID" 2>/dev/null; do
  waited=$((waited + 1))
  if [ "$waited" -ge 30 ]; then
    log "SIGTERM 30s 未退出，SIGKILL 兜底"
    kill -KILL "$PID" 2>/dev/null || true
    sleep 1
    break
  fi
  sleep 1
done
log "进程已退出（等待 ${waited}s）"

# ---------- 4. 等待端口释放（连不上即视为释放） ----------
waited=0
while [ -n "$PORT" ] && [ "$waited" -lt 30 ]; do
  if ! curl -s -o /dev/null --connect-timeout 1 "http://127.0.0.1:${PORT}/"; then
    break
  fi
  waited=$((waited + 1))
  sleep 1
done
log "端口释放确认（等待 ${waited}s）"

# ---------- 5. 按快照复原拉起 ----------
RESTART_LOG="$LOG" python3 - "$TMP" <<'PYEOF'
import os
import subprocess
import sys

tmp = sys.argv[1]
cmd = (open(f"{tmp}/cmdline", "rb").read().rstrip(b"\0")
       .decode("utf-8", "surrogateescape").split("\0"))
env = {}
for item in (open(f"{tmp}/environ", "rb").read().rstrip(b"\0")
             .decode("utf-8", "surrogateescape").split("\0")):
    if "=" in item:
        key, _, val = item.partition("=")
        env[key] = val
cwd = open(f"{tmp}/cwd", encoding="utf-8").read().rstrip("\n")
with open(os.environ["RESTART_LOG"], "ab") as fh:
    subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                     stdout=fh, stderr=fh, start_new_session=True)
print(f"[restart] 已按原上下文拉起（{len(cmd)} 段命令，cwd={cwd}）", flush=True)
PYEOF
log "服务已重新拉起（cwd=$(cat "$TMP/cwd")）"

# ---------- 6. 探活 ----------
waited=0
while [ "$waited" -lt 60 ]; do
  if [ -n "$PORT" ] && curl -s -o /dev/null --connect-timeout 1 \
      "http://127.0.0.1:${PORT}/api/v1/system/health"; then
    log "探活成功（等待 ${waited}s，端口 $PORT）"
    exit 0
  fi
  waited=$((waited + 1))
  sleep 1
done
log "探活超时（60s），请人工检查服务日志"
exit 1
