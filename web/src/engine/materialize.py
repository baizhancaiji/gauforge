"""chk 物化器与 formchk 探针（M4 B7，m4-plan §2.1/§2.2/§4.4）。

派发前物化钩子（「自我续跑同源」的工程落点）：把 Link0 符号引用重写为
实际路径——

- `%chk=@task:X`（续用形态）：复制 X 溯源 chk 至本执行目录 `dep-<X>.chk`
  并改写 `%chk=dep-<X>.chk`——G16 运行会重写 %chk 目标文件，复制语义
  保护上游原件（roadmap §8.6 教训）；
- `%oldchk=@task:X`（只读接续）：复制至 `dep-<X>.chk`、改写 `%oldchk=`，
  本任务自身 `%chk` 保持默认 `input.chk`；
- `%oldchk=@exec:<eid>`（断点续跑）：复制该执行的 chk 资产（protected/
  保全优先，回落保留期内 input.chk）至 `dep-exec-<eid>.chk`。

物化完成后输入文件内**零符号残留**；输入哈希按物化前的符号形式计算
（派发器 advance 已完成，物化不改哈希语义，重跑判定稳定）。
物化失败 = 成员 failed（归因沿用 program_error，details 注明
chk_materialization，§8 决策点 3）。

重入①（§2.1）：凡输入含物化依赖（@task:/@exec: 任一形态）的执行，提交
HQ 时禁用内部重试（crash_limit）——worker 失联即终态 failed、显式重跑经
本物化器重新物化（派发器接线，FakeGateway 提交参数断言见测试）。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ..services.dependencies import (
    execution_chk_asset,
    inputs_path,
    parse_link0_refs,
    run_dir as execution_run_dir,
)
from ..store import executions
from .workspace import content_hash, g16_env, resolve_link0

PROBE_TIMEOUT_S = 120  # 与 finalize.make_fchk 同款兜底上限（§2.2）


class MaterializeError(Exception):
    """物化失败（成员 failed(program_error) 的归因来源）。

    details 携带定位信息（上游任务/执行 id、源路径），调用方落
    stderr 日志与终态管线。
    """

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


def needs_materialization(text: str) -> bool:
    """输入是否含物化依赖（@task:/@exec: 任一形态）。"""
    return bool(parse_link0_refs(text))


def _task_current_hash(task_id: int, nproc_default: int,
                       mem_gb_default: float) -> str | None:
    """任务当前输入的补齐后内容哈希（哈希跳过沿用判据同源）。"""
    try:
        text = inputs_path(task_id).read_text(encoding="utf-8",
                                               errors="replace")
    except OSError:
        return None
    resolved = resolve_link0(text, nproc_default, mem_gb_default)
    return content_hash(resolved["completed_text"])


def resolve_upstream_chk(task_id: int, *, nproc_default: int = 1,
                         mem_gb_default: float = 1.0) -> Path:
    """@task:X 的 chk 溯源（§2.1）：优先 X 当前输入哈希匹配的成功执行
    （哈希跳过被沿用的那次），无匹配回落最近成功执行；取其
    run/<eid>/input.chk。缺源抛 MaterializeError。"""
    exs = [e for e in executions().list_by_task(task_id)
           if e["state"] == "succeeded"]
    if not exs:
        raise MaterializeError(
            f"上游任务 {task_id} 无成功执行，chk 来源不存在",
            {"upstream_task_id": task_id})
    chosen = None
    current = _task_current_hash(task_id, nproc_default, mem_gb_default)
    if current is not None:
        chosen = next((e for e in exs if e.get("input_hash") == current),
                      None)
    chosen = chosen or exs[-1]
    chk = execution_run_dir(chosen["id"]) / "input.chk"
    if not chk.is_file():
        raise MaterializeError(
            f"上游任务 {task_id} 最近成功执行（#{chosen['id']}）的 chk "
            "已被清理，物化必然失败（重跑上游恢复 chk 来源）",
            {"upstream_task_id": task_id, "execution_id": chosen["id"]})
    return chk


def _rewrite_line(line: str, dep_name: str) -> str:
    """符号行值替换（前缀 casefold 归一小写形态，仅取值改写）。"""
    head, sep, _ = line.partition("=")
    return head.casefold() + sep + dep_name


def materialize_chk(run_dir: Path, text: str, *, nproc_default: int = 1,
                    mem_gb_default: float = 1.0) -> str:
    """物化钩子主体：复制上游 chk → 重写符号行 → 零残留校验。

    run_dir 为本执行目录（dep-*.chk 落位处）；text 为补齐后执行文本
    （符号形式）。返回物化后文本（调用方写回 run/<id>/input.gjf）。
    """
    refs = parse_link0_refs(text)
    if not refs:
        return text
    lines = text.split("\n")
    for ref in refs:
        if ref["kind"] == "task":
            src = resolve_upstream_chk(ref["target"],
                                       nproc_default=nproc_default,
                                       mem_gb_default=mem_gb_default)
            dep_name = f"dep-{ref['target']}.chk"
        else:  # exec（断点续跑）：protected 优先，回落保留期内 input.chk
            src = execution_chk_asset(ref["target"])
            if src is None:
                raise MaterializeError(
                    f"@exec:{ref['target']} 引用的执行无 chk 资产"
                    "（已清理或从未产生）",
                    {"execution_id": ref["target"]})
            dep_name = f"dep-exec-{ref['target']}.chk"
        try:
            shutil.copyfile(src, run_dir / dep_name)
        except OSError as exc:
            raise MaterializeError(
                f"复制上游 chk 失败（{src} → {dep_name}）：{exc}",
                {"source": str(src), "dep": dep_name}) from exc
        idx = ref["line"] - 1
        lines[idx] = _rewrite_line(lines[idx], dep_name)
    out = "\n".join(lines)
    leftover = parse_link0_refs(out)
    if leftover:  # 防御：行号错位等实现缺陷不得静默放行
        raise MaterializeError(
            f"物化后输入仍有 {len(leftover)} 处符号残留",
            {"lines": [r["line"] for r in leftover]})
    return out


# ---------------- formchk 有效性探针（§2.2，B9 续跑消费） ----------------

def probe_chk(chk: Path, g16_root: Path, *,
              timeout_s: int = PROBE_TIMEOUT_S) -> tuple[bool, str | None]:
    """对 chk 跑 `<g16_root>/formchk`（临时目录），formchk 成功且 fchk
    可读非空 ⇒ 有效。

    返回 (formchk_ok, reason)：reason ∈ None（有效）/ chk_corrupted
    （formchk 失败或 fchk 不可读）/ probe_timeout（超时按探针失败处理，
    formchk 典型耗时秒级、120s 为兜底上限）。探针失败不触碰源 chk。
    """
    if not chk.is_file():
        return False, "chk_corrupted"
    with tempfile.TemporaryDirectory(prefix="hq-probe-") as td:
        out = Path(td) / "probe.fchk"
        try:
            proc = subprocess.run(
                [str(g16_root / "formchk"), str(chk), str(out)],
                cwd=td, env=g16_env(g16_root, Path(td)),
                capture_output=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return False, "probe_timeout"
        except OSError as exc:
            print(f"[materialize] 探针进程失败：{exc}", file=sys.stderr)
            return False, "chk_corrupted"
        if proc.returncode != 0 or not out.is_file():
            return False, "chk_corrupted"
        try:
            head = out.read_text(encoding="utf-8", errors="replace")[:4096]
        except OSError:
            return False, "chk_corrupted"
        if not head.strip():  # formchk 成功但产物空（缺 fchk 数据段）
            return False, "chk_corrupted"
    return True, None
