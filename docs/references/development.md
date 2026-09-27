# 开发者指南：环境与服务管理

> 面向本仓库开发者的日常操作手册：环境初始化、g16web 服务的拉起与关闭、
> 前端开发链路、测试闸门与隔离冒烟。协作与提交规范见
> [AGENTS.md](../../AGENTS.md)，方向与里程碑见
> [specs/roadmap.md](../specs/roadmap.md)。
>
> 本文所有命令默认在**仓库根**执行；服务指 FastAPI 后端
> （`web/src/main.py`，托管 `web/frontend/dist` 静态前端）。

## 1. 环境初始化

```bash
uv venv && uv pip install -r requirements.txt        # 后端（仓库根 .venv/）
cd web/frontend && npm install                        # 前端依赖
cargo build --release                                 # hq 可执行（派发链路需要，产物 target/release/hq）
```

## 2. 启动服务

### 2.1 前台启动

```bash
uv run python -m web.src.main
```

默认监听 `127.0.0.1:8300`，浏览器访问 `http://127.0.0.1:8300` 即工作台 UI；
API 文档在 `http://127.0.0.1:8300/docs`。

### 2.2 后台启动（日常推荐）

```bash
nohup uv run python -m web.src.main >>/tmp/g16web-8300.log 2>&1 &
```

日志续写在 `/tmp/g16web-8300.log`，确认监听：`ss -tlnp | grep 8300`。

### 2.3 启动参数

监听端口是**运行级设置**（SQLite 持久化，WebUI 设置页可改），启动时从库读
取；保存后**下次重启生效**。工作区根、监听地址等启动级参数仅经环境变量
覆盖（前缀 `G16WEB_`，见 `web/src/config.py`）：

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `G16WEB_HOME` | `~/g16web` | 工作区根（SQLite、任务/结果/归档布局） |
| `G16WEB_BIND_ADDR` | `127.0.0.1` | 监听地址 |
| `G16WEB_ENGINE` | `1` | 派发引擎开关；`0` 关闭（纯演示/契约测试） |
| `G16WEB_HQ_HTTP_PORT` | `0`（关） | HQ HTTP 桥端口 |
| `G16WEB_HQ_BIN` | 按 `hq_bin()` 解析 | hq 可执行定位：环境变量 > PATH > `target/release/hq` |

引擎默认开启：启动序列会 **spawn 或接管**已存活的 HQ server/worker（对账
语义，见 `web/src/engine/startup.py`）；关闭服务**不会**杀掉 HQ 进程，
下次启动自动复用。

## 3. 停止服务

按监听端口定位进程后 `kill`（`uv run` 父进程会随子进程退出，若有残留一并
补杀）：

```bash
PID=$(ss -ltnp | grep ':8300' | grep -oP 'pid=\K[0-9]+' | head -1)
kill "$PID"
# 若 uv run 父进程仍残留：
ps -eo pid,cmd | grep 'uv run python -m web.src.main' | grep -v grep
```

注意：停止 g16web 不影响已存活的 HQ server/worker；仅当需要重启 HQ 本身
时另行处理（对账机制会在 g16web 下次启动时接管）。

## 4. 前端开发链路

- **开发模式**：`cd web/frontend && npm run dev`，Vite 起在
  `http://localhost:5173`，`/api` 与 `/openapi.json` 自动代理到
  `127.0.0.1:8300` —— **需先启动后端**。
- **构建产物**：`npm run build`（vue-tsc 类型检查 + vite 构建）产出
  `web/frontend/dist`，由 FastAPI 静态托管。改完前端后须重新 build，8300
  端口的页面才是最新（浏览器硬刷新避免缓存）。
- **契约类型**：openapi.yaml 变更后 `npm run gen:types` 重新生成
  `src/api/contract.ts`。

## 5. 测试与提交前闸门

```bash
uv run pytest                                  # 本项目测试（默认发现 web/tests）
uv run python scripts/validate_progress.py     # 进度两文件校验
```

注意：涉及派发/端到端链路的改动，确认 `target/release/hq` 存在，否则
`test_e2e_fake_g16.py` 等用例会**静默跳过**，通过数虚高（AGENTS.md §6.1）。

## 6. 隔离冒烟实例

验证改动而**不污染真实工作区**（`~/g16web`）时，用独立工作区 + 独立端口 +
关引擎起临时实例：

```bash
G16WEB_HOME=/tmp/g16web-dev G16WEB_ENGINE=0 \
  uv run python -c "from web.src.main import app; import uvicorn; uvicorn.run(app, host='127.0.0.1', port=8399)"
```

端口无法用环境变量覆盖（listen_port 属运行级设置），临时实例以内联
uvicorn 指定；用完 `kill` 该进程即可。临时工作区目录可随时整体删除。
