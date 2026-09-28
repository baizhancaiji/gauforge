# 部署与升级指南

> 面向**使用者**：在新 WSL2 机器上以干净部署包运行 GauForge，只运行、不改源码。
> 包内自带预编译内核与预构建前端，无需 Rust/Node/任何构建工具链。
> 想参与开发请看 [development.md](development.md)。
>
> 前提：WSL2（linux-x64，Ubuntu 22.04+）、[Gaussian 16](#g16-接入) 已安装。

## 1. 安装

从仓库 [Releases](https://github.com/baizhancaiji/gauforge/releases) 下载
`gauforge-deploy-linux-x64.tar.gz`（版本号见附件所在 Release 标题），然后：

```bash
tar xzf gauforge-deploy-linux-x64.tar.gz && cd gauforge
./install.sh
```

`install.sh` 做四件事：装 uv（未检测到时自动安装）→ 建 `.venv`（优先用系统Python 3.10+，缺失时由 uv 自动获取）→ 安装依赖（默认走清华 PyPI 镜像，可用环境变量 `GAUFORGE_PIP_INDEX` 覆盖）→ 把预编译 `bin/hq` 就位到 `.venv/bin/`。

## 2. 启动

```bash
nohup uv run python -m web.src.main >>/tmp/g16web-8300.log 2>&1 &
```

浏览器访问 `http://127.0.0.1:8300`（Windows 宿主浏览器经 WSL2 localhost转发直接可用）。首次启动自动拉起 HQ server/worker；数据（SQLite、journal、任务产物）都在工作区 `~/g16web`，与部署目录分离。

## 3. 工作区与 G16 接入

### 3.1 工作区目录结构

所有数据都在工作区（`G16WEB_HOME`，默认 `~/g16web`），与部署目录完全分离：

```text
~/g16web/
├── g16web.db          # SQLite：候选/队列/执行记录/运行级设置
├── hq/                # 内核 HQ 的 server-dir：server.journal 与进程日志
├── inputs/            # 导入的候选 .gjf 原件
└── run/<执行id>/      # 每次执行的运行目录：物化+Link0 补齐后的 input.gjf、
                       #   input.log 及 chk/scratch 等全部执行产物
```

升级/重装部署目录不触碰该目录；`chk/rwf 保留天数` 运行级参数只对其后新任务生效，用于清理 `run/` 下的对应产物。

### 3.2 G16 安装位置

不做自动探测：运行级设置 `g16_root`（默认 `~/g16`）即 G16 发行目录，要求 **g16root 布局**——`<g16_root>/g16` 为主程序，同目录树含 `bsd/`、`basis/`、`arch/`、`lexus/` 等。设置页修改仅对其后新任务生效。

执行时不 source `g16.profile`：由 Python 侧按等价方式构造 `GAUSS_*`环境全集（GAUSS_EXEDIR/GAUSS_BSDDIR、G16BASIS、GAUSS_ARCHDIR/GAUSS_LEXEDIR与 PATH/LD_LIBRARY_PATH 前置），实现见 `web/src/engine/workspace.py`（roadmap §2.5 实测口径）。

### 3.3 scratch 接管

每次执行**强制** `GAUSS_SCRDIR=run/<执行id>/`——scratch 即该执行的运行目录本身：临时读写与 `.log`/`.chk` 产物天然同目录、互不串扰，随执行目录统一归档；系统级 Gaussian scratch 配置对本项目无效，也无需预先创建任何全局 scratch 目录。

## 4. 升级

```bash
./update.sh            # 直连 GitHub 拉最新包
./update.sh --proxy    # 走默认镜像代理 https://v4.gh-proxy.org/
./update.sh --proxy https://你的代理地址/   # 自定义代理（需兼容 gh-proxy 前缀改写约定）
./update.sh --no-proxy # 显式直连（覆盖已持久化的代理选择）
./update.sh --check    # 只查询远端最新版本，不下载
```

- 代理选择会持久化到部署目录的 `.update-proxy`，之后不带参数沿用上次选择；环境变量 `GAUFORGE_PROXY` 等效于 `--proxy <值>`。
- 升级只覆盖代码、前端产物与内核二进制，`.venv` 与 `.update-proxy` 不受影响；依赖有变化时脚本会用同一 PyPI 镜像差量重装，完成后**重启服务生效**（先按 development.md §3 停旧进程）。
- 数据安全：升级不触碰工作区 `G16WEB_HOME`；大版本升级前建议整体备份该目录。

## 5. 回退

到 Releases 下载旧版本的 `gauforge-deploy-vX.Y.Z-linux-x64.tar.gz`（带版本号的附件），解压覆盖后重跑 `./install.sh` 即可；数据仍在工作区不受影响。

## 6. 许可提示

包按分层许可分发：自有代码为 PolyForm Noncommercial 1.0.0（**仅限非商业使用**，商用需另行授权）；内核 `bin/hq` 及其随附的 `crates/LICENSE` 为上游HyperQueue 的 MIT。详见包内 `LICENSE`。

## 7. 发版侧（开发者）

每次发版（tag 冻结后）在本机执行：

```bash
scripts/package_release.sh v2.0.0 [--upload]   # 构建 dist+内核 → 打 tar.gz + sha256（--upload 经 gh CLI 上传 Release 附件）
```

附件命名约定：`gauforge-deploy-linux-x64.tar.gz` 为**固定名**（供`update.sh` 的 `releases/latest/download` 直取，配套 `.sha256` 与 `VERSION`两个附件），另附带版本号的同名包供人工下载与回退。
