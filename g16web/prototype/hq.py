"""hq CLI 封装：进程管理、JSON 查询、任务提交。全部通过 ~/opt/hyperqueue/hq 操作。"""
import json
import os
import re
import subprocess
import time

HQ = os.environ.get("HQ_BIN", os.path.expanduser("~/opt/hyperqueue/hq"))
HOME = os.path.expanduser("~")
SERVER_LOG = os.path.join(HOME, ".hq-server.log")
WORKER_LOG = os.path.join(HOME, ".hq-worker.log")

_G16_ENV = ('export g16root=$HOME GAUSS_SCRDIR=$HOME/scratch '
            'PATH="$HOME/g16:$PATH"\n'
            # g16.profile 负责设置 GAUSS_EXEDIR 等，任务必须自己补齐，
            # 不能依赖 worker 进程恰好从登录 shell 启动
            '. "$HOME/g16/bsd/g16.profile" >/dev/null 2>&1')
_G16_RUN = _G16_ENV + '\ng16 < "$1" > "${1%.*}.log" 2>&1'


class HqError(Exception):
    pass


def _run(args, timeout=60):
    try:
        p = subprocess.run([HQ, *args], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise HqError(f"找不到 hq 可执行文件: {HQ}")
    if p.returncode != 0 and "json" not in args:
        raise HqError(p.stderr.strip() or f"hq {' '.join(args)} 失败")
    return p


def run_json(args, timeout=60):
    p = _run(["--output-mode", "json", *args], timeout)
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        raise HqError(f"hq {' '.join(args)} 返回了非 JSON 输出: {p.stdout[:200]}")


def server_ok() -> bool:
    return _run(["server", "info"]).returncode == 0


def ensure_server(wait=10):
    if server_ok():
        return True
    with open(SERVER_LOG, "a") as log:
        subprocess.Popen([HQ, "server", "start"], stdout=log, stderr=log,
                         start_new_session=True)
    deadline = time.time() + wait
    while time.time() < deadline:
        if server_ok():
            return True
        time.sleep(0.4)
    return False


def workers() -> list:
    return run_json(["worker", "list"])


def online_workers() -> list:
    # worker list JSON 没有 state 字段：ended 为 null 表示在线
    return [w for w in workers() if w.get("ended") is None]


def ensure_worker(slots: int, wait=10):
    if online_workers():
        return True
    with open(WORKER_LOG, "a") as log:
        subprocess.Popen([HQ, "worker", "start", "--cpus", str(slots),
                          "--idle-timeout", "30m"],
                         stdout=log, stderr=log, start_new_session=True)
    deadline = time.time() + wait
    while time.time() < deadline:
        if online_workers():
            return True
        time.sleep(0.4)
    return False


def job_list() -> list:
    return run_json(["job", "list", "--all"])


def job_info(job_id: int) -> dict:
    infos = run_json(["job", "info", str(job_id)])
    if not infos:
        raise HqError(f"任务 {job_id} 不存在")
    return infos[0]


def cancel_job(job_id: int):
    _run(["job", "cancel", str(job_id)])


def submit(cwd: str, input_filename: str, name: str) -> int:
    p = _run(["submit", "--name", name, "--cwd", cwd,
              "--", "bash", "-c", _G16_RUN, "g16job", input_filename])
    m = re.search(r"job ID:\s*(\d+)", p.stdout)
    if not m:
        raise HqError(f"提交失败: {p.stdout.strip()} {p.stderr.strip()}")
    return int(m.group(1))


def job_paths(info: dict) -> dict:
    """从 job info JSON 里还原 cwd / 输入文件 / log 路径。"""
    submits = info.get("submits") or []
    if not submits:
        return {}
    prog = (submits[-1].get("array") or {}).get("program", {})
    cwd = prog.get("cwd", "")
    args = prog.get("args", [])
    input_name = args[-1] if len(args) >= 5 else None
    if not cwd or not input_name:
        return {"cwd": cwd}
    stem = os.path.splitext(input_name)[0]
    return {"cwd": cwd, "input": os.path.join(cwd, input_name),
            "log": os.path.join(cwd, stem + ".log")}


def job_state(job: dict) -> str:
    ts = job.get("task_stats", {})
    if ts.get("running"):
        return "RUNNING"
    if ts.get("waiting"):
        return "WAITING"
    if ts.get("failed"):
        return "FAILED"
    if ts.get("canceled") or job.get("cancel_reason"):
        return "CANCELED"
    if ts.get("aborted"):
        return "ABORTED"
    if job.get("task_count") and ts.get("finished") == job["task_count"]:
        return "FINISHED"
    return "PENDING"


def status() -> dict:
    server = server_ok()
    data = {"server": server, "workers": [], "hq": HQ}
    if server:
        for w in workers():
            if w.get("ended") is not None:
                continue
            res = (w.get("configuration", {}).get("resources", {}).get("resources", []))
            cpus = next((r.get("end", 0) - r.get("start", 0) + 1
                         for r in res if r.get("name") == "cpus"), None)
            data["workers"].append({"id": w.get("id"), "online": True,
                                    "hostname": w.get("configuration", {}).get("hostname"),
                                    "cpus": cpus})
    return data
