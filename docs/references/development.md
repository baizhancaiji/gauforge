# 开发者指南：环境与服务管理

> 面向仓库开发者的日常操作手册：环境初始化、g16web 服务的拉起与关闭、
> 前端开发链路、测试闸门与隔离冒烟。协作与提交规范见
> [AGENTS.md](../../AGENTS.md)，方向与里程碑见
> [specs/roadmap.md](../specs/roadmap.md)。
>
> 本文所有命令默认在**仓库根**执行；服务指 FastAPI 后端
> （`web/src/main.py`，托管 `web/frontend/dist` 静态前端）。

## 1. 环境初始化

### 1.1 前置工具链（一次性）

| 工具 | 用途 | 安装 |
|---|---|---|
| uv | Python 环境与依赖 | `curl -LsSf https://astral.sh/uv/install.sh \| UV_INSTALLER_GITHUB_BASE_URL='https://v4.gh-proxy.org/https://github.com' sh`（二进制下载经 gh-proxy 镜像） |
| Rust（stable） | 编译内核 hq | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| Node.js ≥ 20 | 前端构建（`dist/` 不入库，必须本地构建） | nvm 或发行版包管理器 |

仓库 clone 路径随意（项目与仓库路径零耦合，工作区根默认 `~/g16web`）：

```bash
git clone https://github.com/baizhancaiji/gauforge.git && cd gauforge
```

私有仓库需在 GitHub 配置 SSH key 或 PAT；拉取可走 gh-proxy 加速（全局
`insteadOf` 规则）。

### 1.2 Python 环境与内核编译

```bash
uv venv && uv pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
uv pip install cmake libclang -i https://pypi.tuna.tsinghua.edu.cn/simple  # ⚠️ highs-sys 构建工具链，requirements.txt 暂未登记（2026-09-28）
source .envrc            # LIBCLANG_PATH/PATH 指向 .venv 内工具链；direnv 环境用 direnv allow
cargo build --release    # 产物 target/release/hq
```

注意：cclib 已随 M3 B1 引入并冻结进 requirements.txt（cclib==1.8.1 及
numpy/scipy/periodictable 依赖链），随上表首行命令一并装入项目 `.venv`，
**禁止全局 pip 安装**（质量标准含全局无包核查）；若需单独补装，单行命令：
`uv pip install cclib -i https://pypi.tuna.tsinghua.edu.cn/simple`
（m3-plan §2.5；镜像不可达时可换 `--default-index` 指定其他国内镜像）。

### 1.3 前端构建

```bash
cd web/frontend && npm install && npm run build && cd ../..   # 产出 web/frontend/dist
```

### 1.4 G16 与冒烟

- Gaussian 16 装好后，在工作台设置页把运行级参数 `g16_root` 指到实际发行目录
  （默认 `~/g16`，g16root 布局；仅对其后新任务生效）。
- 冒烟：`uv run pytest`（当前基准 350 passed），再按 §2 启动服务、从 UI 导入
  一个 `.gjf` 走通提交与实时进度。

## 2. 启动服务

### 2.1 前台启动

```bash
uv run python -m web.src.main
```

默认监听 `127.0.0.1:8300`，浏览器访问 `http://127.0.0.1:8300` 即工作台 UI；
API 文档在 `http://127.0.0.1:8300/docs`。

### 2.2 后台启动

```bash
nohup uv run python -m web.src.main >>/tmp/g16web-8300.log 2>&1 &
```

日志续写在 `/tmp/g16web-8300.log`，确认监听：`ss -tlnp | grep 8300`。

### 2.3 启动参数

监听端口是**运行级设置**（SQLite 持久化，WebUI 设置页可改），启动时从库读取；保存后**下次重启生效**。工作区根、监听地址等启动级参数仅经环境变量覆盖（前缀 `G16WEB_`，见 `web/src/config.py`）：

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `G16WEB_HOME` | `~/g16web` | 工作区根（SQLite、任务/结果/归档布局） |
| `G16WEB_BIND_ADDR` | `127.0.0.1` | 监听地址 |
| `G16WEB_ENGINE` | `1` | 派发引擎开关；`0` 关闭（纯演示/契约测试） |
| `G16WEB_HQ_HTTP_PORT` | `0`（关） | HQ HTTP 桥端口 |
| `G16WEB_HQ_BIN` | 按 `hq_bin()` 解析 | hq 可执行定位：环境变量 > PATH > `target/release/hq` |

引擎默认开启：启动序列会 **spawn 或接管**已存活的 HQ server/worker（对账语义，见 `web/src/engine/startup.py`）；关闭服务**不会**杀掉 HQ 进程，下次启动自动复用。

## 3. 停止服务

按监听端口定位进程后 `kill`（`uv run` 父进程会随子进程退出，若有残留一并补杀）：

```bash
PID=$(ss -ltnp | grep ':8300' | grep -oP 'pid=\K[0-9]+' | head -1)
kill "$PID"
# 若 uv run 父进程仍残留：
ps -eo pid,cmd | grep 'uv run python -m web.src.main' | grep -v grep
```

注意：停止 g16web 不影响已存活的 HQ server/worker；仅当需要重启 HQ 本身时另行处理（对账机制会在 g16web 下次启动时接管）。

## 4. 前端开发链路

- **开发模式**：`cd web/frontend && npm run dev`，Vite 起在 `http://localhost:5173`，`/api` 与 `/openapi.json` 自动代理到
  `127.0.0.1:8300` —— **需先启动后端**。
- **构建产物**：`npm run build`（vue-tsc 类型检查 + vite 构建）产出 `web/frontend/dist`，由 FastAPI 静态托管。改完前端后须重新 build，8300
  端口的页面才是最新（浏览器硬刷新避免缓存）。
- **契约类型**：openapi.yaml 变更后 `npm run gen:types` 重新生成 `src/api/contract.ts`。

## 5. 测试与提交前闸门

```bash
uv run pytest                                  # 本项目测试（默认发现 web/tests）
uv run python scripts/validate_progress.py     # 进度两文件校验
```

注意：涉及派发/端到端链路的改动，确认 `target/release/hq` 存在，否则`test_e2e_fake_g16.py` 等用例会**静默跳过**，通过数虚高（AGENTS.md §6.1）。

## 6. 隔离冒烟实例

验证改动而**不污染真实工作区**（`~/g16web`）时，用独立工作区 + 独立端口 +关引擎起临时实例：

```bash
G16WEB_HOME=/tmp/g16web-dev G16WEB_ENGINE=0 \
  uv run python -c "from web.src.main import app; import uvicorn; uvicorn.run(app, host='127.0.0.1', port=8399)"
```

端口无法用环境变量覆盖（listen_port 属运行级设置），临时实例以内联uvicorn 指定；用完 `kill` 该进程即可。临时工作区目录可随时整体删除。
