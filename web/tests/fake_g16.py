#!/usr/bin/env python3
"""fake g16（m1-plan §8 决策点 8）：g16 替身，独立脚本不依赖真环境。

行为配置（G16_FAKE="exit=0;sleep=0.1;steps=3" 环境变量，缺省 exit=0）：
- steps：写入进度行轮数（每轮 = 优化步一行 + SCF Cycle 一行 + SCF Done
  一行，与 4 份金标准 .out 的实测行式一致，B8 窄域匹配可识别）；
- exit：进程退出码（非零 → HQ Failed → 程序报错链路）；
- 输入内嵌 `! FAKE: exit=1` 注释行可覆盖全局配置（per-job 行为差异，
  HQ worker 环境固定的场景经输入内容传递）。

输出文件：与输入同名 .log（input.gjf → input.log，m1-plan §2.3 输出
文件名约定；B6 实施核实默认预期）。SCFDIR/GAUSS_SCRDIR 语义不模拟。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def _conf() -> dict[str, str]:
    conf = dict(kv.split("=", 1) for kv in
                os.environ.get("G16_FAKE", "").split(";") if kv.strip())
    # 输入内嵌覆盖：! FAKE: k=v; k=v
    try:
        for ln in Path(sys.argv[-1]).read_text(encoding="utf-8",
                                               errors="replace").splitlines():
            s = ln.strip()
            if s.lower().startswith("! fake:"):
                conf.update(kv.strip().split("=", 1) for kv in
                            s.split(":", 1)[1].split(";") if kv.strip())
    except OSError:
        pass
    return conf


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: fake_g16 <input.gjf>", file=sys.stderr)
        return 2
    conf = _conf()
    inp = Path(sys.argv[-1])
    out = inp.with_suffix(".log")
    steps = int(conf.get("steps", "1"))
    for i in range(1, steps + 1):
        with out.open("a", encoding="utf-8") as fh:
            fh.write(f" Step number {i} out of a maximum of {steps}\n")
            fh.write(" Cycle   1  Pass 1  IDiag  1:\n")
            fh.write(" RMSDP=1.00D-06 MaxDP=1.00D-06\n")
            fh.write(" SCF Done:  E(RB-HF-LYP) =  -1.000000000"
                     "     A.U. after    1 cycles\n")
        time.sleep(float(conf.get("sleep", "0")))
    if conf.get("note"):
        with out.open("a", encoding="utf-8") as fh:
            fh.write(conf["note"] + "\n")
    return int(conf.get("exit", "0"))


if __name__ == "__main__":
    sys.exit(main())
