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

chk 产出（3.5.0 起，对齐真实 g16「按 %chk 行声明命名产物」实测规则）：
仅扫 Link0 区取 `%chk=` 首个声明（Link0 口径与
web/src/engine/workspace.parse_chk_line 同步维护——独立脚本不导入
web.src，正则内嵌），.log 写完之后、退出之前落盘（对齐 g16 退出前 chk
已在盘）：相对声明写输入所在目录（无扩展名自动追加 .chk，g16 手册规则），
内容恒 b"fake-chk"；无声明不写（g16 无 %chk 不产 chk 实测结论）。
与真实 g16 差异边界：绝对路径声明不写盘（测试触盘面已整体隔离到
tmp_path，绝对路径落盘会外溢共享 /tmp；绝对路径产态由单测手工资产覆盖）。
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

_CHK_RE = re.compile(r"^%chk\s*=\s*(.+)$", re.IGNORECASE)


def _conf() -> dict[str, str]:
    conf = dict(kv.strip().split("=", 1) for kv in
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


def _declared_chk(text: str) -> Path | None:
    """输入 Link0 区首个 %chk 声明值（剥引号，空值视同无声明）。

    仅扫 Link0 区（前导空行/! 注释行后的连续 % 行，G16 只识别 Link0
    命令），与 parse_chk_line(link0_only=True) 同规则。"""
    lines = text.replace("\r\n", "\n").split("\n")
    i, n = 0, len(lines)
    while i < n and (not lines[i].strip() or lines[i].lstrip().startswith("!")):
        i += 1
    while i < n and lines[i].lstrip().startswith("%"):
        m = _CHK_RE.match(lines[i].strip())
        if m:
            raw = m.group(1).strip().strip('"').strip("'")
            if raw:
                return Path(raw)
        i += 1
    return None


def _write_chk(inp: Path, text: str) -> None:
    """按声明落 chk（相对声明才写；OSError 容错与 .log 同口径不抛栈）。"""
    declared = _declared_chk(text)
    if declared is None or declared.anchor:
        return  # 无声明不产 chk；绝对路径声明不写（差异边界见模块头）
    target = inp.parent / declared
    if not target.suffix:
        target = target.with_name(target.name + ".chk")
    try:
        target.write_bytes(b"fake-chk")
    except OSError:
        pass


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: fake_g16 <input.gjf>", file=sys.stderr)
        return 2
    conf = _conf()
    inp = Path(sys.argv[-1])
    out = inp.with_suffix(".log")
    try:
        text = inp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""  # 解析不出声明即不产 chk，.log 写出与退出码路径维持现状容错
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
    _write_chk(inp, text)  # .log 写完之后、退出之前（g16 退出前 chk 已在盘）
    return int(conf.get("exit", "0"))


if __name__ == "__main__":
    sys.exit(main())
