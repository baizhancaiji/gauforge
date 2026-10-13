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
        assert "重启服务（.venv/bin/python" not in log_text  # 不再 nohup
    else:
        assert "重启服务（.venv/bin/python" in log_text
        assert "已委托 systemd" not in log_text


def test_self_update_survives_missing_uv(tmp_path):
    """PATH 与常见安装位都无 uv：依赖刷新警告跳过，编排不死透——
    照常置 done、同步根脚本、拉回服务（2026-10-04 3.0.0 升级事故回归：
    systemd unit 环境无 uv，uv not found 中止脚本，WebUI 死透）。"""
    deploy = tmp_path / "deploy"
    _seed_old_deploy(deploy)
    shutil.copyfile(SCRIPTS_DIR / "self_update.sh", deploy / "self_update.sh")
    _write(deploy / "update-state", json.dumps(
        {"target_version": PKG_VERSION, "phase": "restarting",
         "started_at": "2026-10-04T12:00:00+08:00"}))
    real_py = subprocess.run(["bash", "-c", "command -v python3"],
                             capture_output=True, text=True).stdout.strip()
    _write(deploy / ".venv" / "bin" / "python",
           f"#!/bin/sh\nexec {real_py} \"$@\"\n", 0o755)
    pkg = _make_package(tmp_path)
    payload = deploy / ".update-payload.tar.gz"
    _make_asset(pkg, payload)

    env = _sandbox_env(tmp_path)
    # PATH 重建：摘除 fakebin 与一切含 uv 的目录（含真实 ~/.local/bin），
    # 前置无 uv 的假命令目录——假 curl 必须保留，否则第 3 步端口探测用
    # 真 curl 会撞开发机真实监听（8300 有实例时探测吃满 60s）
    no_uv_bin = tmp_path / "fakebin-no-uv"
    no_uv_bin.mkdir()
    for name in ("curl", "systemctl", "loginctl"):
        shutil.copyfile(tmp_path / "fakebin" / name, no_uv_bin / name)
        (no_uv_bin / name).chmod(0o755)
    env["PATH"] = os.pathsep.join(
        [str(no_uv_bin)]
        + [p for p in env["PATH"].split(os.pathsep)
           if p != str(tmp_path / "fakebin")
           and not (Path(p) / "uv").exists()])
    # HOME 指到沙箱空目录：脚本的常见安装位回落看 $HOME，真实 home 若装
    # 有 uv（~/.local/bin）会被命中而走真 uv
    home = tmp_path / "fakehome"
    (home / ".local" / "bin").mkdir(parents=True)
    (home / ".cargo" / "bin").mkdir(parents=True)
    env["HOME"] = str(home)

    outer = subprocess.Popen(  # noqa: S603 —— 沙箱内受控拉起
        ["bash", "-c",
         f'cd "{deploy}" && exec bash self_update.sh >> update.log 2>&1 &'],
        cwd=deploy, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log = deploy / "update.log"
    deadline = time.time() + 60
    while time.time() < deadline:
        outer.poll()
        if log.exists() and "接管完成" in log.read_text(encoding="utf-8",
                                                        errors="replace"):
            break
        time.sleep(0.5)
    else:
        pytest.fail("self_update.sh 60s 未完成；update.log：\n"
                    + (log.read_text(encoding="utf-8", errors="replace")
                       if log.exists() else "<缺>"))

    log_text = log.read_text(encoding="utf-8", errors="replace")
    assert "未找到 uv，跳过依赖刷新" in log_text
    state = json.loads((deploy / "update-state").read_text(encoding="utf-8"))
    assert state["phase"] == "done"
    for name in ALL_SCRIPTS:
        assert (deploy / name).read_text(encoding="utf-8") == \
            f"#!/usr/bin/env bash\n# pkg:{name}\n", name
    assert (deploy / "bin" / "hq").exists()


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


# ---------------- setup_deps.sh（crest/xtb 第三方依赖安装） ----------------

# 按下载 URL 落对应假资产并记录请求 URL（代理改写断言用）；未知 URL 即失败，
# 防沙箱静默走真网络。
FAKE_DEPS_CURL = """#!/bin/bash
prev=""; out=""
for a in "$@"; do
  if [ "$prev" = "-o" ]; then out="$a"; fi
  prev="$a"
done
url="${@: -1}"
[ -n "${CURL_LOG:-}" ] && printf '%s\\n' "$url" >> "$CURL_LOG"
case "$url" in
  *.tar.xz.sha256) cp "$FAKE_XTB_TAR.sha256" "$out" ;;
  *crest-gnu-12-ubuntu-latest.tar.xz) cp "$FAKE_CREST_TAR" "$out" ;;
  *xtb-6.7.1-linux-x86_64.tar.xz) cp "$FAKE_XTB_TAR" "$out" ;;
  *) echo "unexpected url: $url" >&2; exit 1 ;;
esac
"""
# 必失败版：幂等跳过用例用（若脚本仍发起下载即失败，证明判据走冒烟）
FAILING_CURL = "#!/bin/bash\nexit 18\n"
# 假 crest / xtb 二进制：--version 输出命中 smoke 判据子串
FAKE_CREST_BIN = "#!/bin/sh\necho ' crest version 3.0.2 (fake)'\n"
FAKE_XTB_BIN = "#!/bin/sh\necho 'xtb version 6.7.1'\n"


def _make_deps_fixture(tmp: Path) -> dict[str, str]:
    """假 crest/xtb 资产（真 tar.xz，布局同上游）+ 假 curl 沙箱环境。"""
    bin_dir = tmp / "fakebin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    # 上游 tar 顶层为 crest/ 目录（真机走查实测 2026-10-14，非平铺）
    crest_stage = tmp / "crest_stage" / "crest"
    crest_stage.mkdir(parents=True)
    _write(crest_stage / "crest", FAKE_CREST_BIN, 0o755)
    _write(crest_stage / "LICENSE", "LGPL\n")
    crest_tar = tmp / "crest-gnu-12-ubuntu-latest.tar.xz"
    subprocess.run(
        ["tar", "-cJf", str(crest_tar), "-C", str(crest_stage.parent), "crest"],
        check=True)

    # 上游 tar 顶层为 xtb-dist/ 目录（真机走查实测 2026-10-14，非 xtb-6.7.1/）
    xtb_stage = tmp / "xtb_stage" / "xtb-dist" / "bin"
    xtb_stage.mkdir(parents=True)
    _write(xtb_stage / "xtb", FAKE_XTB_BIN, 0o755)
    xtb_tar = tmp / "xtb-6.7.1-linux-x86_64.tar.xz"
    subprocess.run(
        ["tar", "-cJf", str(xtb_tar), "-C", str(tmp / "xtb_stage"), "xtb-dist"],
        check=True)
    digest = hashlib.sha256(xtb_tar.read_bytes()).hexdigest()
    xtb_tar.with_name(xtb_tar.name + ".sha256").write_text(
        f"{digest}  {xtb_tar.name}\n", encoding="utf-8")

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["FAKE_CREST_TAR"] = str(crest_tar)
    env["FAKE_XTB_TAR"] = str(xtb_tar)
    env["CURL_LOG"] = str(tmp / "curl.log")
    # 体积对照隔离：期望值 = 假资产实际字节数（真实值写死在脚本内）
    env["GAUFORGE_CREST_SIZE"] = str(crest_tar.stat().st_size)
    # 隔离开发者环境可能残留的代理选择
    env.pop("GAUFORGE_PROXY", None)
    return env


def _run_setup_deps(tmp: Path, dest: Path, env: dict[str, str],
                    *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPTS_DIR / "setup_deps.sh"), "--dest", str(dest), *args],
        env=env, capture_output=True, text=True, timeout=120)


def test_setup_deps_installs_crest_and_smokes(tmp_path):
    """首装：crest 解压到 <dest>/crest-3.0.2/crest（平铺布局同运行级默认
    ~/opt/crest-3.0.2），体积对照通过、--version 冒烟通过、打印设置页指引。"""
    dest = tmp_path / "opt"
    env = _make_deps_fixture(tmp_path)
    _write(tmp_path / "fakebin" / "curl", FAKE_DEPS_CURL, 0o755)
    proc = _run_setup_deps(tmp_path, dest, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (dest / "crest-3.0.2" / "crest").stat().st_mode & 0o111
    ver = subprocess.run([str(dest / "crest-3.0.2" / "crest"), "--version"],
                         capture_output=True, text=True)
    assert "crest" in ver.stdout
    assert "crest_root" in proc.stdout
    # 默认布局（--dest 指向的根 == 运行级默认 ~/opt 形态）无需改设置页提示
    assert "crest-3.0.2" in proc.stdout


def test_setup_deps_idempotent_smoke_skip(tmp_path):
    """幂等：已安装（冒烟通过）重跑跳过下载——假 curl 换必失败版仍成功。"""
    dest = tmp_path / "opt"
    env = _make_deps_fixture(tmp_path)
    _write(tmp_path / "fakebin" / "curl", FAKE_DEPS_CURL, 0o755)
    first = _run_setup_deps(tmp_path, dest, env)
    assert first.returncode == 0, first.stdout + first.stderr
    _write(tmp_path / "fakebin" / "curl", FAILING_CURL, 0o755)
    second = _run_setup_deps(tmp_path, dest, env)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "已安装（冒烟通过），跳过" in second.stdout


def test_setup_deps_broken_install_reinstall(tmp_path):
    """半成品残留（目录在但 --version 冒烟失败）→ 清理后重装成功。"""
    dest = tmp_path / "opt"
    env = _make_deps_fixture(tmp_path)
    _write(tmp_path / "fakebin" / "curl", FAKE_DEPS_CURL, 0o755)
    broken = dest / "crest-3.0.2"
    _write(broken / "crest", "#!/bin/sh\nexit 1\n", 0o755)
    proc = _run_setup_deps(tmp_path, dest, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "半成品残留" in proc.stdout
    ver = subprocess.run([str(dest / "crest-3.0.2" / "crest"), "--version"],
                         capture_output=True, text=True)
    assert "crest" in ver.stdout


def test_setup_deps_proxy_channel_conventions(tmp_path):
    """代理约定与 update.sh 同款：GAUFORGE_PROXY / --proxy [URL] 前缀改写、
    --no-proxy 直连原始 URL。"""
    dest = tmp_path / "opt"
    env = _make_deps_fixture(tmp_path)
    _write(tmp_path / "fakebin" / "curl", FAKE_DEPS_CURL, 0o755)
    raw = ("https://github.com/crest-lab/crest/releases/download/v3.0.2/"
           "crest-gnu-12-ubuntu-latest.tar.xz")

    log = Path(env["CURL_LOG"])
    # ① 环境变量 GAUFORGE_PROXY
    env["GAUFORGE_PROXY"] = "https://p-env.example"
    assert _run_setup_deps(tmp_path, dest, env, "--force").returncode == 0
    assert log.read_text(encoding="utf-8").strip().splitlines()[-1] == \
        f"https://p-env.example/{raw}"
    # ② --proxy 自定义 URL（参数优先于环境变量）
    assert _run_setup_deps(tmp_path, dest, env, "--force",
                           "--proxy", "https://p-arg.example").returncode == 0
    assert log.read_text(encoding="utf-8").strip().splitlines()[-1] == \
        f"https://p-arg.example/{raw}"
    # ③ --no-proxy 直连
    assert _run_setup_deps(tmp_path, dest, env, "--force",
                           "--no-proxy").returncode == 0
    assert log.read_text(encoding="utf-8").strip().splitlines()[-1] == raw
    # 代理选择不持久化到工作区（无 update 通道语义）
    assert not (tmp_path / "home" / ".update-proxy").exists()


def test_setup_deps_xtb_optional_and_checksum(tmp_path):
    """--xtb 可选装：默认不装（无下载请求）；携带时装出 xtb-6.7.1/bin/xtb
    （顶层目录布局同运行级默认 ~/opt/xtb-6.7.1）且官方 .sha256 对照通过。"""
    dest = tmp_path / "opt"
    env = _make_deps_fixture(tmp_path)
    _write(tmp_path / "fakebin" / "curl", FAKE_DEPS_CURL, 0o755)
    # ① 不带 --xtb：xtb 资产零请求
    proc = _run_setup_deps(tmp_path, dest, env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "xtb" not in Path(env["CURL_LOG"]).read_text(encoding="utf-8")
    assert not (dest / "xtb-6.7.1").exists()
    # ② 带 --xtb：解压 bin/xtb + 官方 sha256 通道被拉取
    proc = _run_setup_deps(tmp_path, dest, env, "--force", "--xtb")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (dest / "xtb-6.7.1" / "bin" / "xtb").stat().st_mode & 0o111
    assert "官方校验和通过" in proc.stdout
    assert Path(env["CURL_LOG"]).read_text(encoding="utf-8").count(".sha256") == 1
    # ③ 安装布局与运行级 crest_root/xtb_root 默认值形态对齐（config.py
    #    ~/opt/crest-3.0.2、~/opt/xtb-6.7.1；自定义 --dest 时打印改指指引）
    assert "自定义安装路径" in proc.stdout and "crest_root" in proc.stdout
    assert str(dest / "crest-3.0.2") in proc.stdout
    assert str(dest / "xtb-6.7.1") in proc.stdout
