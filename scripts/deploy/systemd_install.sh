#!/usr/bin/env bash
# GauForge systemd 用户级托管安装（可选；WSL2 需已启用 systemd）。
#
# 用法（在本部署目录执行）:
#   bash systemd_install.sh            生成用户 unit 并 enable --now
#   bash systemd_install.sh --remove   停用并删除 unit（不动工作区数据）
#
# 设计要点：
#   - ExecStart 直启 .venv/bin/python -m web.src.main（与 uv run 等效，免
#     uv 运行时依赖，SIGTERM 直达 uvicorn 优雅退出）；PATH 预置 .venv/bin
#     ——引擎经 shutil.which("hq") 定位内核（web/src/config.py）
#   - KillMode=process：停/重启只作用于 WebUI 主进程，引擎拉起的 HQ
#     server/worker 不被 cgroup 收割（development.md §8.7 停 WebUI 不杀 HQ）
#   - G16WEB_SERVICE_UNIT 写入进程环境：restart_g16web.sh / self_update.sh /
#     stop_all.sh 据此把重启/全停委托给 systemctl，避免与 Restart=on-failure
#     抢杀（直接 TERM 会被立即拉起，全停失效）
set -euo pipefail
cd "$(dirname "$0")"
DEPLOY="$(pwd)"

UNIT_NAME="gauforge.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="$UNIT_DIR/$UNIT_NAME"
SYSCTL() {
  XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" \
    systemctl --user "$@"
}

[ -x .venv/bin/python ] || {
  echo "[systemd] 未发现 .venv，请先运行 ./install.sh" >&2
  exit 1
}
command -v systemctl >/dev/null 2>&1 || {
  echo "[systemd] 未找到 systemctl：本机未启用 systemd（WSL2 需在 /etc/wsl.conf 配 [boot] systemd=true 后重启 WSL）" >&2
  exit 1
}

if [ "${1:-}" = "--remove" ]; then
  if [ -f "$UNIT_FILE" ]; then
    SYSCTL disable --now "$UNIT_NAME" 2>/dev/null || true
    rm -f "$UNIT_FILE"
    SYSCTL daemon-reload || true
    echo "[systemd] 已卸载 $UNIT_NAME（工作区数据不受影响）"
  else
    echo "[systemd] 未发现已安装的 unit：$UNIT_FILE"
  fi
  exit 0
fi

# 已托管：刷新 unit 后重启生效；未托管且端口被占：拒绝（避免与手动实例抢端口）
if SYSCTL is-active --quiet "$UNIT_NAME" 2>/dev/null; then
  REFRESH=1
else
  REFRESH=0
  PORT="$(.venv/bin/python -c "from web.src.main import resolved_listen_port; \
print(resolved_listen_port())" 2>/dev/null || echo 8300)"
  if curl -s -o /dev/null --connect-timeout 1 "http://127.0.0.1:${PORT}/"; then
    echo "[systemd] 端口 $PORT 已有服务在跑：先停旧进程再安装" >&2
    echo "  （停 WebUI 按 development.md §3；bash stop_all.sh 会一并停 HQ）" >&2
    exit 1
  fi
fi

mkdir -p "$UNIT_DIR"
{
  echo "[Unit]"
  echo "Description=GauForge G16 Web 工作台"
  echo "After=network.target"
  echo ""
  echo "[Service]"
  echo "Type=simple"
  echo "WorkingDirectory=$DEPLOY"
  echo "Environment=\"G16WEB_SERVICE_UNIT=$UNIT_NAME\""
  echo "Environment=\"PATH=$DEPLOY/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\""
  if [ -n "${G16WEB_HOME:-}" ]; then
    echo "Environment=\"G16WEB_HOME=$G16WEB_HOME\""
  fi
  echo "ExecStart=$DEPLOY/.venv/bin/python -m web.src.main"
  echo "Restart=on-failure"
  echo "RestartSec=3"
  echo "TimeoutStopSec=30"
  echo "KillMode=process"
  echo ""
  echo "[Install]"
  echo "WantedBy=default.target"
} > "$UNIT_FILE"

SYSCTL daemon-reload
if [ "$REFRESH" = "1" ]; then
  SYSCTL restart "$UNIT_NAME"
  echo "[systemd] unit 已刷新并重启（$UNIT_FILE）"
else
  SYSCTL enable --now "$UNIT_NAME"
  echo "[systemd] 已安装并启动 $UNIT_NAME（$UNIT_FILE）"
  # 开机（WSL 启动）即拉起需要 linger；失败仅提示，不影响本次启动
  if ! loginctl enable-linger "${USER:-$(id -un)}" 2>/dev/null; then
    echo "[systemd] 提示：如需免登录自启，执行 sudo loginctl enable-linger $(id -un)"
  fi
fi
echo "[systemd] 日志：journalctl --user -u $UNIT_NAME -f"
