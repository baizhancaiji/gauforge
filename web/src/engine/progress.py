"""增量解析（m1-plan §4.3 B8；roadmap §8.5、sse.md execution.progress）。

直接 tail `run/<id>/input.log`（g16 自写日志；§8.5 对策：g16web 与 worker
同文件系统，不引入 --stream 传输层）。两类进度行窄域匹配（4 份金标准
.out 实测行式）+ SCF 收敛附加信号：

- 优化步：` Step number   N out of a maximum of   M`（Berny 每优化步一行）；
- SCF 迭代：` Cycle   N  Pass M  IDiag D:`（每 SCF 迭代一行，新一轮 SCF
  自 Cycle 1 重启，converged 随之复位 False）；
- SCF 收敛：` SCF Done:` → converged=True（附加信号，非独立进度类型）。

位点续传：per-execution offset 内存保持，文件增长只读增量；半行缓冲待
补齐；文件缩短（异常重写）静默从头重扫。
首读快进（catch-up）：执行日志首次可见时全量消费不推事件——重启对账重扫
与派发初期的历史行不产生事件风暴。
1s 合并窗口（sse.md：每 execution 至多 1 条/s）：窗口内新进度仅更新状态，
窗口过后由下一次 step 推最新值（数据事件=最新状态语义，中间值丢失无损）。
解析失败（文件缺失/OSError）该周期缺席，下一周期恢复（sse.md §6）。
"""
from __future__ import annotations

import re
import time
from pathlib import Path

# 窄域匹配（行首锚定 + 全行形态，金标准实测；不猜其他行式）
_RE_OPT = re.compile(
    r"^\s*Step number\s+(\d+)\s+out of a maximum of\s+(\d+)\s*$")
_RE_CYCLE = re.compile(r"^\s*Cycle\s+(\d+)\s+Pass\s+(\d+)\s+IDiag\s+\d+:\s*$")
_RE_SCF_DONE = re.compile(r"^\s*SCF Done:")

_LAST_LINE_MAX = 200  # sse.md：last_line 截断 200 字符


class ProgressTracker:
    """per-execution 增量解析：offset 续传 + 合并窗口节流。

    step() 返回 execution.progress 载荷增量字段（execution_id/task_id/ts
    由调用方补齐），无新进度或被窗口节流时返回 None。
    """

    def __init__(self, *, window_s: float = 1.0,
                 clock: callable = time.monotonic) -> None:
        self._window = float(window_s)
        self._clock = clock
        self._state: dict[int, dict] = {}

    def step(self, execution_id: int, log_path: Path) -> dict | None:
        st = self._state.get(execution_id)
        if st is None:
            st = self._state[execution_id] = {
                "offset": 0, "pending": "", "catchup": True,
                "opt_step": None, "scf_cycle": None,
                "converged": None, "last_line": None, "last_emit": None}
        try:
            if log_path.stat().st_size < st["offset"]:
                # 截断（文件缩短）→ 从头静默重扫
                st["offset"] = 0
                st["pending"] = ""
                st["catchup"] = True
            with log_path.open("rb") as fh:
                fh.seek(st["offset"])
                chunk = fh.read()
        except OSError:
            return None  # 文件缺失/瞬时失败：本周期缺席（sse.md §6）
        st["offset"] += len(chunk)

        text = st["pending"] + chunk.decode("utf-8", errors="replace")
        lines = text.split("\n")
        st["pending"] = lines.pop()  # 半行（无换行）留待下次补齐
        progress = False
        for ln in lines:
            m = _RE_OPT.match(ln)
            if m:
                st["opt_step"] = int(m.group(1))
                st["last_line"] = ln[:_LAST_LINE_MAX]
                progress = True
                continue
            m = _RE_CYCLE.match(ln)
            if m:
                st["scf_cycle"] = int(m.group(1))
                if st["scf_cycle"] == 1:
                    st["converged"] = False  # 新一轮 SCF 开始
                st["last_line"] = ln[:_LAST_LINE_MAX]
                progress = True
                continue
            if _RE_SCF_DONE.match(ln):
                st["converged"] = True
                st["last_line"] = ln[:_LAST_LINE_MAX]
                progress = True

        if st["catchup"]:
            st["catchup"] = False
            return None  # 首读全量快进不推事件
        if not progress:
            return None
        now = self._clock()
        if st["last_emit"] is not None \
                and now - st["last_emit"] < self._window:
            return None  # 合并窗口内：仅更新状态，窗口后推最新值
        st["last_emit"] = now
        facts: dict = {}
        if st["opt_step"] is not None:
            facts["opt_step"] = st["opt_step"]
        if st["scf_cycle"] is not None:
            facts["scf_cycle"] = st["scf_cycle"]
        if st["converged"] is not None:
            facts["converged"] = st["converged"]
        if st["last_line"] is not None:
            facts["last_line"] = st["last_line"]
        return facts

    def forget(self, execution_id: int) -> None:
        """终态清理（offset/状态随执行结束作废）。"""
        self._state.pop(execution_id, None)
