#!/usr/bin/env bash
# GauForge 自更新接管脚本（v2.1.0 WebUI 更新链路专用，D6）。
#
# 由后端 apply 流水线 detached 拉起（start_new_session、stdout/stderr 追加
# 重定向本目录 update.log、环境经 Popen 原样继承——G16WEB_HOME 等启动级
# 变量随之保持，脚本内直接沿用、不猜测默认值）。编排：
#
#   1. 读取 update-state（apply 流程标记，缺文件即非接管场景，退出）
#   2. 等待父进程退出（主判据 kill -0 $PPID；后端已 SIGTERM 优雅自退）
#   3. 等待端口释放（辅助探测，上限 60s；「设置改端口未重启」边界下探测
#      端口取 SQLite 现值可能与实际监听不同，以父进程退出判据兜底）
#   4. 解压 .update-payload.tar.gz（后端已 sha256 校验的载荷）覆盖
#   5. 差量刷依赖（同 update.sh：uv pip，镜像可 GAUFORGE_PIP_INDEX 覆盖）
#   6. update-state 置 phase=done（仅改 phase、保留 target_version/started_at）
#   7. 根脚本全量同步：包内全部 *.sh 先落 *.new，重启前原子 mv 覆盖
#      （运行中 bash 持旧 inode，不影响本次执行；遍历而非枚举固定名单，
#      新增根脚本借此对旧部署目录自动补装；仓库源文件不动，仅部署副本刷新）
#   8. nohup 按原上下文重启服务（cwd=本目录、命令同 install.sh 提示）
#
# 全程不杀任何进程；日志一律追加 update.log。--dry-run 只打印编排步骤，
# 不动任何文件（演练与测试用）。
set -euo pipefail
cd "$(dirname "$0")"

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

PAYLOAD=".update-payload.tar.gz"
STATE_FILE="update-state"
LOG="update.log"
WAIT_LIMIT=60

log() { echo "[$(date '+%F %T')] [self-update] $*" >> "$LOG"; }

if [ "$DRY_RUN" = "1" ]; then
  echo "[self-update] dry-run 编排步骤（不执行任何动作）："
  echo "  1. 读取 $STATE_FILE（target_version/phase/started_at）"
  echo "  2. 等待父进程退出（kill -0 \$PPID，上限 ${WAIT_LIMIT}s）"
  echo "  3. 等待端口释放（curl 127.0.0.1:<SQLite 现值>，上限 ${WAIT_LIMIT}s，辅助判据）"
  echo "  4. 解压 $PAYLOAD → 覆盖 web/docs/requirements/VERSION/README/CHANGELOG/LICENSE/crates/bin"
  echo "  5. 差量刷依赖（uv pip，镜像 \${GAUFORGE_PIP_INDEX:-清华}）"
  echo "  6. $STATE_FILE 置 phase=done（仅改 phase）"
  echo "  7. 根脚本全量同步（包内全部 *.sh 经 *.new 原子 mv，新增脚本自动补装）"
  echo "  8. nohup 按原上下文重启（uv run python -m web.src.main，日志追加 $LOG）"
  exit 0
fi

# ---------- 1. 流程标记 ----------
[ -f "$STATE_FILE" ] || {
  echo "[self-update] 缺少 $STATE_FILE，非更新流程接管场景，退出" >&2
  exit 1
}

# 端口取 SQLite 现值（resolved_listen_port；失败回落 8300 仅用于辅助探测）。
PORT="$(.venv/bin/python -c "from web.src.main import resolved_listen_port; \
print(resolved_listen_port())" 2>/dev/null || echo 8300)"

log "接管开始（载荷 $PAYLOAD，SQLite 端口 $PORT）"

# ---------- 2. 等待父进程退出（主判据，不杀进程） ----------
waited=0
while kill -0 "$PPID" 2>/dev/null; do
  waited=$((waited + 1))
  if [ "$waited" -ge "$WAIT_LIMIT" ]; then
    log "等待父进程退出超时（${WAIT_LIMIT}s），继续（端口探测兜底）"
    break
  fi
  sleep 1
done
log "父进程已退出（等待 ${waited}s）"

# ---------- 3. 等待端口释放（辅助探测；连不上即视为释放） ----------
waited=0
while [ "$waited" -lt "$WAIT_LIMIT" ]; do
  if ! curl -s -o /dev/null --connect-timeout 1 "http://127.0.0.1:${PORT}/"; then
    break
  fi
  waited=$((waited + 1))
  sleep 1
done
if [ "$waited" -ge "$WAIT_LIMIT" ]; then
  log "端口 $PORT 探测超时（父进程已退出，按兜底判据继续）"
fi
log "端口释放确认（等待 ${waited}s）"

# ---------- 4. 解压覆盖（载荷后端已校验；不触碰 .venv/伴生文件） ----------
if [ ! -f "$PAYLOAD" ]; then
  log "缺少更新载荷 $PAYLOAD（后端未移交），中止"
  echo "[self-update] 缺少 $PAYLOAD，中止（详见 $LOG）" >&2
  exit 1
fi
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
tar -xzf "$PAYLOAD" -C "$tmp"
src="$tmp/gauforge"
if [ ! -d "$src/web/src" ]; then
  log "包结构异常（缺 web/src），中止"
  exit 1
fi
rm -f "$PAYLOAD"

cp -a "$src/web" "$src/docs" .
install -m 644 "$src/requirements.txt" "$src/VERSION" "$src/README.md" \
  "$src/CHANGELOG.md" "$src/LICENSE" .
install -d crates
install -m 644 "$src/crates/LICENSE" crates/LICENSE   # 保持 crates/ 路径：与根 LICENSE 基本名冲突
install -d bin
install -m 755 "$src/bin/hq" bin/hq
log "解压覆盖完成（版本 $(cat VERSION)）"

# 根脚本同步第一步：包内全部 *.sh 先落 *.new（此刻仍在临时目录生命周期内）。
# 清单记入 SCRIPT_LIST，供第 7 步在临时目录删除后回放；统一走 *.new 避免
# 直接覆盖并发运行中的脚本，新增根脚本对旧部署目录即补装。
SCRIPT_LIST=""
for f in "$src"/*.sh; do
  if [ -f "$f" ]; then
    name="$(basename "$f")"
    install -m 755 "$f" "./$name.new"
    SCRIPT_LIST="$SCRIPT_LIST $name"
  fi
done
rm -rf "$tmp"

# ---------- 5. 差量刷依赖 ----------
if [ ! -d .venv ]; then
  log "未发现 .venv，请先运行 ./install.sh"
  exit 1
fi
log "差量刷新依赖…"
uv pip install --python .venv/bin/python -r requirements.txt \
  -i "${GAUFORGE_PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
install -m 755 bin/hq .venv/bin/hq

# ---------- 6. update-state 置 done（仅改 phase，保留其余字段） ----------
TARGET="$(.venv/bin/python -c "
import json
with open('$STATE_FILE', encoding='utf-8') as fh:
    st = json.load(fh)
st['phase'] = 'done'
with open('$STATE_FILE', 'w', encoding='utf-8') as fh:
    json.dump(st, fh, ensure_ascii=False)
print(st['target_version'])
")"
log "update-state 置 phase=done（目标 $TARGET）"

# ---------- 7. 重启前原子覆盖根脚本（含补装的新增脚本） ----------
for f in $SCRIPT_LIST; do
  if [ -f "./$f.new" ]; then
    mv -f "./$f.new" "./$f"
  fi
done

# ---------- 8. 按原上下文重启（env 已继承沿用，cwd=本目录） ----------
log "重启服务（uv run python -m web.src.main）"
nohup uv run python -m web.src.main >> "$LOG" 2>&1 &
log "接管完成"
