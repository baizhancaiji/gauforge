"""部署升级脚本沙箱测试（真实 bash 执行）：根脚本自动补装行为。

背景：restart_g16web.sh/stop_all.sh 为 v2.2.0 新增根脚本，从更早版本
原位升级的部署目录此前永远缺这两个文件（两条升级路径都只刷新已知
文件、不安装新增脚本）。本文件把 update.sh（CLI 兜底路径）与
self_update.sh（WebUI 接管路径）放进沙箱真实跑一遍，锁定补装语义：

- update.sh：补装部署目录缺失的根脚本；update.sh 自身与已有脚本不动；
- self_update.sh：包内全部根脚本经 *.new 原子 mv 同步（新增即补装、
  已有即刷新），update-state 置 done、载荷解压后清理。

沙箱手法：临时部署目录 + 假 .venv/bin/python（转发真解释器，供脚本
内联改写 update-state）；PATH 前置假 uv（跳过真装依赖）与假 curl
（本地文件冒充下载附件、对 127.0.0.1 探测返回拒连以立即通过端口
释放检查）；self_update.sh 经外层 bash 后台化使 PPID 立即消亡，
跳过等父循环，以 update.log 收尾行轮询判完成。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "deploy"
PKG_VERSION = "v9.9.9"
NEW_SCRIPTS = ("restart_g16web.sh", "stop_all.sh")
LEGACY_SCRIPTS = ("install.sh", "update.sh", "self_update.sh")
ALL_SCRIPTS = LEGACY_SCRIPTS + NEW_SCRIPTS

FAKE_UV = "#!/bin/sh\nexit 0\n"
# -o 后随输出路径、末参数为 URL；对 127.0.0.1 探测返回拒连（exit 7，端口
# 释放判据）、health 探活返回成功，其余按 URL 落到 FAKE_ASSET 本地文件。
FAKE_CURL = """#!/bin/bash
prev=""; out=""
for a in "$@"; do
  if [ "$prev" = "-o" ]; then out="$a"; fi
  prev="$a"
done
url="${@: -1}"
case "$url" in
  *health*) exit 0 ;;
  http://127.0.0.1*) exit 7 ;;
  *.sha256) cp "$FAKE_ASSET.sha256" "$out" ;;
  *) cp "$FAKE_ASSET" "$out" ;;
esac
"""
# 委托语义测试用：调用记录进 SYSTEMCTL_LOG；is-active 恒非活跃（走全新安装
# 分支），其余子命令一律成功。首参可能是 --user，故按参数遍历匹配子命令。
FAKE_SYSTEMCTL = """#!/bin/bash
[ -n "${SYSTEMCTL_LOG:-}" ] && printf '%s\\n' "$*" >> "$SYSTEMCTL_LOG"
for a in "$@"; do
  [ "$a" = "is-active" ] && exit 1
done
exit 0
"""
FAKE_LOGINCTL = "#!/bin/sh\nexit 1\n"  # 沙箱内必走 linger 提示分支，不触真机


def _write(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def _make_package(tmp: Path) -> Path:
    """最小干净部署包（结构同 package_release.sh 产物），脚本带版本标记。"""
    pkg = tmp / "gauforge"
    _write(pkg / "web" / "src" / "main.py", "# pkg web\n")
    _write(pkg / "docs" / "api" / "openapi.yaml", "openapi: 3.0.0\n")
    _write(pkg / "requirements.txt", "# pkg req\n")
    _write(pkg / "VERSION", PKG_VERSION)
    _write(pkg / "README.md", "# pkg readme\n")
    _write(pkg / "CHANGELOG.md", "# pkg changelog\n")
    _write(pkg / "LICENSE", "MIT\n")
    _write(pkg / "crates" / "LICENSE", "MIT\n")
    _write(pkg / "bin" / "hq", "#!/bin/sh\n# pkg hq\n", 0o755)
    for name in ALL_SCRIPTS:
        _write(pkg / name, f"#!/usr/bin/env bash\n# pkg:{name}\n", 0o755)
    return pkg


def _make_asset(pkg: Path, asset: Path) -> None:
    """包 → 固定名 tar.gz + 配套 .sha256（行格式同 package_release.sh）。"""
    subprocess.run(["tar", "-czf", str(asset), "-C", str(pkg.parent), "gauforge"],
                   check=True)
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    asset.with_name(asset.name + ".sha256").write_text(
        f"{digest}  {asset.name}\n", encoding="utf-8")


def _sandbox_env(tmp: Path) -> dict[str, str]:
    """假 uv / curl / systemctl / loginctl 前置 PATH；工作区与下载附件指到沙箱内。"""
    env = dict(os.environ)
    bin_dir = tmp / "fakebin"
    _write(bin_dir / "uv", FAKE_UV, 0o755)
    _write(bin_dir / "curl", FAKE_CURL, 0o755)
    _write(bin_dir / "systemctl", FAKE_SYSTEMCTL, 0o755)
    _write(bin_dir / "loginctl", FAKE_LOGINCTL, 0o755)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["G16WEB_HOME"] = str(tmp / "home")
    env["FAKE_ASSET"] = str(tmp / "gauforge-deploy-linux-x64.tar.gz")
    return env


def _seed_old_deploy(deploy: Path) -> None:
    """v2.1.0 形态旧部署目录：三根脚本旧内容、缺 v2.2.0 新增两脚本。"""
    deploy.mkdir(parents=True)
    for name in LEGACY_SCRIPTS:
        _write(deploy / name, f"#!/usr/bin/env bash\n# old:{name}\n", 0o755)
    _write(deploy / "VERSION", "v2.1.0")
    _write(deploy / "requirements.txt", "# old req\n")
    (deploy / ".venv" / "bin").mkdir(parents=True)


# ---------------- update.sh（CLI 兜底路径） ----------------

def test_update_sh_installs_missing_root_scripts(tmp_path):
    """旧目录升级：缺失根脚本补装；已有脚本与 update.sh 自身不覆盖。"""
    deploy = tmp_path / "deploy"
    _seed_old_deploy(deploy)
    shutil.copyfile(SCRIPTS_DIR / "update.sh", deploy / "update.sh")
    pkg = _make_package(tmp_path)
    asset = tmp_path / "gauforge-deploy-linux-x64.tar.gz"
    _make_asset(pkg, asset)

    env = _sandbox_env(tmp_path)
    proc = subprocess.run(["bash", str(deploy / "update.sh")], cwd=deploy,
                          env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    for name in NEW_SCRIPTS:
        expect = f"#!/usr/bin/env bash\n# pkg:{name}\n"
        assert (deploy / name).read_text(encoding="utf-8") == expect, name
    # 既有行为不回退：CLI 路径不更新脚本自身（含 update.sh），已有脚本不动
    assert (deploy / "install.sh").read_text(encoding="utf-8") == \
        "#!/usr/bin/env bash\n# old:install.sh\n"
    assert (deploy / "self_update.sh").read_text(encoding="utf-8") == \
        "#!/usr/bin/env bash\n# old:self_update.sh\n"
    assert "# pkg:update.sh" not in \
        (deploy / "update.sh").read_text(encoding="utf-8")
    assert (deploy / "VERSION").read_text(encoding="utf-8") == PKG_VERSION
    # 代理选择落 G16WEB_HOME 工作区，不污染真实目录
    assert (tmp_path / "home" / ".update-proxy").exists()


# ---------------- self_update.sh（WebUI 接管路径） ----------------

@pytest.mark.parametrize("systemd", [False, True],
                         ids=["nohup", "systemd-delegate"])
def test_self_update_syncs_all_root_scripts(tmp_path, systemd):
    """WebUI 更新：包内全部根脚本 *.new 原子 mv 同步，新增脚本即补装；
    systemd 托管下重启委托 systemctl，不再 nohup。"""
    deploy = tmp_path / "deploy"
    _seed_old_deploy(deploy)
    shutil.copyfile(SCRIPTS_DIR / "self_update.sh", deploy / "self_update.sh")
    _write(deploy / "update-state", json.dumps(
        {"target_version": PKG_VERSION, "phase": "restarting",
         "started_at": "2026-10-04T12:00:00+08:00"}))
    # 假 .venv：bin/python 转发真解释器（端口回落与 state 改写的内联调用）
    real_py = subprocess.run(["bash", "-c", "command -v python3"],
                             capture_output=True, text=True).stdout.strip()
    assert real_py, "沙箱需系统 python3 供 .venv/bin/python 转发"
    _write(deploy / ".venv" / "bin" / "python",
           f"#!/bin/sh\nexec {real_py} \"$@\"\n", 0o755)
    # 载荷：与后端 apply 移交的伴生文件同名（脚本解压覆盖后清理）
    pkg = _make_package(tmp_path)
    payload = deploy / ".update-payload.tar.gz"
    _make_asset(pkg, payload)

    env = _sandbox_env(tmp_path)
    if systemd:
        env["G16WEB_SERVICE_UNIT"] = "gauforge.service"
        env["SYSTEMCTL_LOG"] = str(tmp_path / "systemctl.log")
    # 外层 bash 后台化脚本；exec 使脚本替换列表子 shell——否则父进程是
    # 等待脚本结束的子 shell（恒存活），等父循环必然等满 60s。外层 bash
    # 随即退出且是本测试未回收的僵尸（kill -0 对僵尸为真），故轮询里
    # proc.poll() 持续收割，脚本 1~2s 内越过得父循环。
    outer = subprocess.Popen(  # noqa: S603 —— 沙箱内受控拉起
        ["bash", "-c",
         f'cd "{deploy}" && exec bash self_update.sh >> update.log 2>&1 &'],
        cwd=deploy, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log = deploy / "update.log"
    deadline = time.time() + 60
    while time.time() < deadline:
        outer.poll()  # 收割僵尸，令脚本 kill -0 $PPID 失败
        if log.exists() and "接管完成" in log.read_text(encoding="utf-8",
                                                        errors="replace"):
            break
        time.sleep(0.5)
    else:
        pytest.fail("self_update.sh 60s 未完成；update.log：\n"
                    + (log.read_text(encoding="utf-8", errors="replace")
                       if log.exists() else "<缺>"))

    for name in ALL_SCRIPTS:
        expect = f"#!/usr/bin/env bash\n# pkg:{name}\n"
        assert (deploy / name).read_text(encoding="utf-8") == expect, name
    assert not list(deploy.glob("*.new"))  # 原子 mv 无残留
    assert not payload.exists()  # 载荷解压后清理
    assert (deploy / "VERSION").read_text(encoding="utf-8") == PKG_VERSION
    state = json.loads((deploy / "update-state").read_text(encoding="utf-8"))
    assert state["phase"] == "done"
    assert state["target_version"] == PKG_VERSION  # 仅改 phase
    assert (deploy / "bin" / "hq").read_text(encoding="utf-8") == \
        "#!/bin/sh\n# pkg hq\n"
    log_text = log.read_text(encoding="utf-8", errors="replace")
    if systemd:
        calls = (tmp_path / "systemctl.log").read_text(encoding="utf-8")
        assert calls.endswith("--user restart gauforge.service\n")
        assert "已委托 systemd 重启（unit=gauforge.service）" in log_text
        assert "重启服务（uv run" not in log_text  # 不再 nohup
    else:
        assert "重启服务（uv run" in log_text
        assert "已委托 systemd" not in log_text


# ---------------- systemd_install.sh（托管安装） ----------------

def test_systemd_install_generates_unit(tmp_path):
    """安装脚本生成用户 unit：直启 .venv/bin/python、PATH 预置 .venv/bin、
    KillMode=process、G16WEB_SERVICE_UNIT 注记；enable --now 被调用。"""
    deploy = tmp_path / "deploy"
    _seed_old_deploy(deploy)
    shutil.copyfile(SCRIPTS_DIR / "systemd_install.sh", deploy / "systemd_install.sh")
    real_py = subprocess.run(["bash", "-c", "command -v python3"],
                             capture_output=True, text=True).stdout.strip()
    _write(deploy / ".venv" / "bin" / "python",
           f"#!/bin/sh\nexec {real_py} \"$@\"\n", 0o755)
    env = _sandbox_env(tmp_path)
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    env["SYSTEMCTL_LOG"] = str(tmp_path / "systemctl.log")

    proc = subprocess.run(["bash", str(deploy / "systemd_install.sh")],
                          cwd=deploy, env=env, capture_output=True,
                          text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    unit = tmp_path / "config" / "systemd" / "user" / "gauforge.service"
    text = unit.read_text(encoding="utf-8")
    assert f"WorkingDirectory={deploy}" in text
    assert f"ExecStart={deploy}/.venv/bin/python -m web.src.main" in text
    assert f"PATH={deploy}/.venv/bin" in text  # shutil.which("hq") 可发现内核
    assert "KillMode=process" in text  # 停 WebUI 不杀引擎拉起的 HQ
    assert "Restart=on-failure" in text
    assert "G16WEB_SERVICE_UNIT=gauforge.service" in text
    calls = (tmp_path / "systemctl.log").read_text(encoding="utf-8")
    assert "is-active --quiet gauforge.service" in calls
    assert "enable --now gauforge.service" in calls
    assert "daemon-reload" in calls


# ---------------- restart_g16web.sh（systemd 委托） ----------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_restart_delegates_to_systemd(tmp_path):
    """托管目标（环境含 G16WEB_SERVICE_UNIT）：委托 systemctl restart，
    脚本自身不 TERM 目标进程（生命周期归 systemd）。"""
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    shutil.copyfile(SCRIPTS_DIR / "restart_g16web.sh", deploy / "restart_g16web.sh")
    env = _sandbox_env(tmp_path)
    env["SYSTEMCTL_LOG"] = str(tmp_path / "systemctl.log")
    port = _free_port()
    dummy = subprocess.Popen(  # noqa: S603 —— 沙箱哑服务充当被接管目标
        [sys.executable, "-m", "http.server", str(port)],
        cwd=deploy, env={**env, "G16WEB_SERVICE_UNIT": "gauforge.service"},
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 10
        while time.time() < deadline:  # 等哑服务就绪（真 socket 探测）
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        proc = subprocess.run(
            ["bash", str(deploy / "restart_g16web.sh"),
             "--port", str(port), "--log", str(tmp_path / "restart.log")],
            cwd=deploy, env=env, capture_output=True, text=True, timeout=90)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert (tmp_path / "systemctl.log").read_text(
            encoding="utf-8").endswith("--user restart gauforge.service\n")
        restart_log = (tmp_path / "restart.log").read_text(encoding="utf-8")
        assert "已委托 systemd 重启（unit=gauforge.service）" in restart_log
        assert dummy.poll() is None  # 脚本未自行杀目标（托管下归 systemd）
    finally:
        dummy.terminate()
        dummy.wait(timeout=5)
