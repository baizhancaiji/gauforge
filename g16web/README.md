# g16web —— G16 Web 控制台

基于 [HyperQueue](https://github.com/It4innovations/hyperqueue) 队列引擎的 Gaussian 16
Web 提交/监控面板，为 WSL2 单机工作流打造。工作分支：`g16-webui`。

功能：
- **任务队列**：实时列表（2s 刷新）、状态徽章、进度条、最新能量、耗时
- **Gaussian 专属进度**：解析 log 输出，显示优化步数 x/N、SCF 圈数、当前迭代、
  最新能量与方法、CPU 时间、正常/异常终止识别（这是 HyperQueue TUI 都不做的事）
- **导入与预览**：三种方式导入输入文件——服务器路径（含 `/mnt/c/...`）+ 目录浏览、
  文件上传、粘贴内容；预览拆解 Link0/Route/标题/电荷/几何（支持直角坐标与
  Z-矩阵），并给出格式警告（CRLF、Link0 与 Route 间缺空行、缺末尾空行、
  缺 %NProcShared 等）
- **提交**：可编辑内容后提交，写入 `~/scratch/uploads/`，经 hq 队列调度，
  自动拉起 server/worker（worker 空闲 30 分钟自动退出）
- 取消任务、查看任务 log 尾部（自动刷新）

## 快速开始

```bash
g16web            # 启动并让 Windows 浏览器打开 http://localhost:8160
g16web stop       # 停止
g16web fg         # 前台运行（调试用）
```

依赖：Python 3.10+ 标准库（零第三方依赖）、`~/opt/hyperqueue/hq`、`~/g16`。
预计算的日志解析、hq 封装可直接复用：

```python
from g16web import hq, gaussian, inputfile
gaussian.parse_log(text)          # -> {opt_step, nsteps, last_energy, ...}
inputfile.parse_input(text)       # -> {jobs, warnings, valid, ...}
```

## JSON API（亦即未来 DSH 插件的调用接口）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | `/api/status` | server/worker 状态 |
| GET  | `/api/jobs` | 全部任务 + Gaussian 进度摘要 |
| GET  | `/api/job/{id}` | 单任务 Gaussian 进度详情 |
| GET  | `/api/job/{id}/log?lines=120` | log 尾部 |
| POST | `/api/preview` | body `{path}` 或 `{content, filename}` → 预览+警告 |
| POST | `/api/submit` | body `{path}` 或 `{content, filename}` + `slots` → `{job_id}` |
| POST | `/api/job/{id}/cancel` | 取消 |
| GET  | `/api/files?path=...` | 目录浏览 |

示例：

```bash
curl -X POST http://localhost:8160/api/submit \
  -H 'Content-Type: application/json' \
  -d '{"path": "/mnt/c/Users/you/mol.gjf", "slots": 2}'
```

## 与 HyperQueue 的关系

不修改 HyperQueue 本体：通过 `hq --output-mode json` CLI 集成
（`hq.py`），任务以 `hq submit -- bash -c <g16 运行脚本>` 形式进入队列，
Gaussian 进度则独立解析任务目录下的 `同名.log`。
上游更新只需 `git pull` 并 rebase 本分支。

## DSH 集成规划（待办）

1. JSON API 即工具接口：DSH 工具直接调 `POST /api/submit`、`GET /api/jobs`、
   `GET /api/job/{id}` 即可实现"帮我提交计算/看看跑到哪了"
2. 或绕过 HTTP，把 `g16web/hq.py`、`g16web/gaussian.py` 打包为 DSH 插件直接调用
3. 可加：分子结构可视化（读 .fchk 画轨道）、批量修改 Route 重提交、
   CREST/xtb 任务支持

## 已知限制

- 单用户、监听 127.0.0.1，未做鉴权（本机工具）
- 上传内容保存到 `~/scratch/uploads/`，不覆盖已有文件（自动加 -2、-3 后缀）
- 变量式 Z-矩阵（如 `H 1 R1`）能统计原子数但不展开坐标
- 临时任务流目录 `job-N/` 留在任务目录，可手动清理
