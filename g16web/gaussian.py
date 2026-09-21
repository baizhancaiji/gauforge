"""Gaussian 输出日志解析：从 .log 文本中提取任务进度。"""
import re

RE_OPT_STEP = re.compile(r"Step number\s+(\d+)")
RE_NSTEPS = re.compile(r"NSteps\s*=\s*(\d+)")
RE_ENERGY = re.compile(r"SCF Done:\s+E\(([^)]+)\)\s*=\s*([-+]?\d+\.\d+(?:[EeDd][-+]?\d+)?)")
RE_SCF_ITER = re.compile(r"^\s*Iteration\s+(\d+)\s", re.MULTILINE)
RE_NORMAL_END = re.compile(r"Normal termination of Gaussian")
RE_ERROR_END = re.compile(r"Error termination via Lnk1e")
RE_ERROR_MSG = re.compile(r"^\s*(?:Error termination|.*error.*).*$", re.IGNORECASE)
RE_CPU_TIME = re.compile(r"Job cpu time:\s+(.+)")
RE_OPT_COMPLETED = re.compile(r"Optimization completed")
RE_OPT_EXCEEDED = re.compile(r"Number of steps exceeded")
RE_ROUTE = re.compile(r"^\s*(#.*)$", re.MULTILINE)
RE_GRAD_BLOCK = re.compile(r"^ GradGradGrad", re.MULTILINE)


def parse_log(text: str) -> dict:
    """解析 Gaussian log，返回进度摘要（永远不抛异常，坏日志返回尽力而为的结果）。"""
    energies = [
        {"method": m.group(1), "energy": float(m.group(2).replace("D", "E").replace("d", "e"))}
        for m in RE_ENERGY.finditer(text)
    ]
    steps = [int(m.group(1)) for m in RE_OPT_STEP.finditer(text)]
    iters = [int(m.group(1)) for m in RE_SCF_ITER.finditer(text)]
    error_lines = [ln.strip() for ln in text.splitlines() if RE_ERROR_END.search(ln)]

    route_m = RE_ROUTE.search(text)
    nsteps = [int(m.group(1)) for m in RE_NSTEPS.finditer(text)]
    normal = bool(RE_NORMAL_END.search(text))
    errored = bool(RE_ERROR_END.search(text))

    return {
        "normal_termination": normal,
        "error_termination": errored,
        "error_message": error_lines[-1] if error_lines else None,
        "route": route_m.group(1).strip() if route_m else None,
        "opt_step": steps[-1] if steps else None,
        "nsteps": nsteps[-1] if nsteps else None,
        "scf_cycles": len(energies),
        "current_scf_iter": iters[-1] if iters else None,
        "last_energy": energies[-1]["energy"] if energies else None,
        "energy_method": energies[-1]["method"] if energies else None,
        "optimization_completed": bool(RE_OPT_COMPLETED.search(text)),
        "steps_exceeded": bool(RE_OPT_EXCEEDED.search(text)),
        "cpu_time": (m.group(1).strip() if (m := RE_CPU_TIME.search(text)) else None),
        "size": len(text),
    }


def parse_file(path: str) -> dict:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return parse_log(f.read())
    except OSError:
        return {"missing": True}


def progress_summary(progress: dict) -> str:
    """给队列列表用的一句话进度。"""
    if progress.get("missing"):
        return "无日志"
    if progress["normal_termination"]:
        return "正常结束"
    if progress["error_termination"]:
        return "异常终止"
    if progress["opt_step"]:
        n = progress.get("nsteps")
        return f"优化第 {progress['opt_step']} 步" + (f"/{n}" if n else "")
    if progress["current_scf_iter"]:
        return f"SCF 第 {progress['current_scf_iter']} 圈"
    return "读取日志中"
