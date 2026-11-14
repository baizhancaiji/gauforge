"""历史领域服务（B9）：终态条目序列化、输入/输出视图、批量输出导出、
归档、重新排队、退回候选、过期清理。

- 历史条目 = executions 终态行（m1-plan §2.2 运行与历史同表）；wall_time_s
  按 started_at→finished_at 派生（契约标注 F 字段不落库）；
- 批量导出（scope 三范围）：out=选中条目的 run/<id>/input.log（G16 输出，
  全内存 BytesIO 打包）；chk=chk 资产（execution_chk_asset 定位，临时文件
  顺序写、ZIP_STORED 按路径流式拷贝）；all=同执行两文件都入包。条目内以
  <stem>.<扩展> 归一命名（同 (stem, 扩展) 冲突组全部加补零 id 前缀），
  包内平铺不建子目录，包名仅靠时间戳区分；
- 重新排队：仅 failed/skipped、且任务不归属任何队列（队列成员经队列
  重新提交，防止撕裂队列成员构成）；沿用原任务 id 建席（finished→
  seat_task），满员 409 与一般任务同待遇（roadmap §2.1）；
- 退回候选：以 run/<id>/input.gjf 实际执行副本新建候选（新 id，skipped
  等无执行目录者回落任务输入副本），来源标记按终态分流——succeeded→
  returned_succeeded、failed→returned_failed(附归因)、skipped→
  returned_unrun（roadmap §2.1）；
- 清理：双档仅删正常结束执行的顶层 chk——expired（超保留期）/ all
  （无视保留期，「清理所有」），failed 的保全 chk 不受影响
  （engine/finalize）。
"""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from .. import config
from ..engine import finalize as finalize_files
from ..errors import err, not_found
from ..services import candidates as candidates_svc
from ..services import verify as verify_svc
from ..store import executions, seats, settings, tasks
from ..store.db import now_iso

_TERMINAL = ("succeeded", "failed", "skipped")
_ORIGIN_BY_STATE = {"succeeded": "returned_succeeded",
                    "failed": "returned_failed",
                    "skipped": "returned_unrun"}


def _iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _wall_time_s(row: dict) -> float:
    if row.get("started_at") and row.get("finished_at"):
        return (_iso(row["finished_at"]) - _iso(row["started_at"])).total_seconds()
    return 0.0


def entry_shape(row: dict, resumed_by: list[int] | None = None) -> dict:
    """HistoryEntry 序列化：bool 转换、派生 wall_time_s、chk_snapshot 缺省。

    resumed_from 透传库值（M4 续跑关联，无则 null）；resumed_by 为派生只读
    （不入存储，调用方按 _resumed_by_map 反查传入，缺省空列表）；kind 冗余
    自任务（M4 C7 crest 行徽标数据源，响应时反查注入、任务已删除缺省 g16）。
    """
    t = tasks().get(row["task_id"])
    return {**row,
            "archived": bool(row.get("archived")),
            "kind": (t or {}).get("kind") or "g16",
            "wall_time_s": _wall_time_s(row),
            "chk_snapshot": row.get("chk_snapshot")
            or {"protected": False, "location": None},
            "result_ref": row.get("result_ref"),
            "resumed_from": row.get("resumed_from"),
            "resumed_by": resumed_by if resumed_by is not None else []}


def _resumed_by_map() -> dict[int, list[int]]:
    """resumed_from 反查索引：原执行 id → 续跑执行 id 列表（升序）。

    「已续跑 → #MMM」的派生只读数据源（m4-plan §2.2）；单机终态量级小，
    全量扫描 resumed_from 非空行即可。"""
    out: dict[int, list[int]] = {}
    for r in executions().list_resumed_sources():
        src = r.get("resumed_from") or {}
        eid = src.get("execution_id")
        if eid is not None:
            out.setdefault(int(eid), []).append(int(r["id"]))
    return {k: sorted(v) for k, v in out.items()}


def _terminal_row(execution_id: int) -> dict:
    row = executions().get(execution_id)
    if row is None or row["state"] not in _TERMINAL:
        raise not_found("history", execution_id)
    return row


def list_entries(state: str | None, queue_id: str | None,
                 archived: bool | None, page: int, page_size: int | None,
                 sort: str = "submitted_desc") -> dict:
    size = page_size if page_size is not None \
        else int(settings().get("page_size"))
    items, total = executions().list_terminal(
        state=state, queue_id=queue_id, archived=archived,
        page=page, page_size=size, sort=sort)
    by_map = _resumed_by_map()
    return {"items": [entry_shape(r, by_map.get(r["id"])) for r in items],
            "page": page, "page_size": size, "total": total}


def get_entry(execution_id: int) -> dict:
    row = _terminal_row(execution_id)
    return entry_shape(row, _resumed_by_map().get(execution_id))


def load_input(execution_id: int) -> bytes:
    """输入查看：run/<id>/input.gjf 实际执行副本；skipped 等无执行目录
    者回落任务输入副本（roadmap §2.1）。"""
    row = _terminal_row(execution_id)
    src = _run_dir(execution_id) / "input.gjf"
    if not src.is_file():
        src = candidates_svc.default_inputs_dir() / str(row["task_id"])
    try:
        return src.read_bytes()
    except OSError:
        raise not_found("input", execution_id)


def load_output(execution_id: int) -> bytes:
    """输出纯文本：run/<id>/input.log（g16 自写日志）。"""
    _terminal_row(execution_id)
    src = _run_dir(execution_id) / "input.log"
    try:
        return src.read_bytes()
    except OSError:
        raise not_found("output", execution_id)


def export_outputs(ids: list[int], scope: str = "out") -> bytes | Path:
    """批量导出选中条目为 ZIP（内存字节或临时文件路径，按 scope 分路径）。

    scope=out（缺省）：条目内容 = run/<id>/input.log（G16 输出），全内存
    BytesIO 打包（零回归原路径）；scope=chk：条目 = execution_chk_asset
    定位的 chk 资产（① protected/ 保全优先，② 按执行副本 %chk= 声明定位、
    无声明回落 input.chk）；scope=all：同执行 .out 与 .chk 都入包、说明按
    执行合并登记一条。条目内命名 <stem>.<扩展>（stem 取任务 filename 去
    扩展名）；同一 (stem, 扩展) 冲突组全部改用「三位补零执行 id-」前缀
    区分（scope=all 同执行同 stem 不互冲突）。缺漏条目跳过并在包内
    _导出说明.txt 逐条登记；所选 scope 采集全空 → 404（openapi
    /history/export）。续用形态 %chk=@task:X 的执行副本被物化为
    %chk=dep-<X>.chk 且其 dep-<X>.chk 即本任务自有 chk，②路径天然选中
    （不加 dep-* 过滤）；只读接续 %oldchk 的 dep-* 不满足判据、不会被选中。
    """
    from .dependencies import execution_chk_asset  # 延迟导入防环（requeue 先例）
    picked: list[tuple[int, str, str, object]] = []  # (执行 id, stem, 扩展, bytes|Path)
    missing: list[str] = []                          # 导出说明行
    want_out = scope in ("out", "all")
    want_chk = scope in ("chk", "all")
    for eid in dict.fromkeys(ids):                   # 去重保序
        row = executions().get(eid)
        if row is None or row["state"] not in _TERMINAL:
            missing.append(f"- 执行 {eid}：条目不存在或非终态")
            continue
        name = row["filename"]
        stem = name.rsplit(".", 1)[0] if "." in name else name
        out_data: bytes | None = None
        if want_out:
            try:
                out_data = _run_dir(eid).joinpath("input.log").read_bytes()
            except OSError:
                out_data = None  # 读清竞态：按缺登记，不阻塞不重试
        # skipped 未启动无 run 过程，无 chk（不查资产）；读清竞态按缺登记
        chk_path = (execution_chk_asset(eid)
                    if want_chk and row["state"] != "skipped" else None)
        out_miss = want_out and out_data is None
        chk_miss = want_chk and chk_path is None
        if out_miss or chk_miss:
            # 缺失描述按维度独立（scope=out 维持现状逐字文案），多维缺失
            # 拼接为一条（scope=all 按执行合并登记）
            line = "，".join(filter(None, [
                "无输出文件（任务未产生输出或已清理）" if out_miss else None,
                "无 chk（任务未启动）" if chk_miss and row["state"] == "skipped"
                else None,
                "无 chk 资产（已清理或从未产生）"
                if chk_miss and row["state"] != "skipped" else None]))
            missing.append(f"- 执行 {eid}：{line}")
        if out_data is not None:
            picked.append((eid, stem, "out", out_data))
        if chk_path is not None:
            picked.append((eid, stem, "chk", chk_path))
    if not picked:
        raise err("NOT_FOUND", "选中条目均无可导出文件",
                  {"missing": missing}, http=404)
    dup = {key for key, n in Counter((s, e) for _, s, e, _ in picked).items()
           if n > 1}

    def _inner(eid: int, stem: str, ext: str) -> str:
        return (f"{eid:03d}-{stem}.{ext}" if (stem, ext) in dup
                else f"{stem}.{ext}")

    if scope == "out":  # 内存原路径（零回归）
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for eid, stem, ext, data in picked:
                zf.writestr(_inner(eid, stem, ext), data)
            if missing:
                zf.writestr("_导出说明.txt", _export_manifest(missing))
        return buf.getvalue()
    # chk/all：临时文件顺序写（chk 可达数 GB，包内存峰值不可接受）
    tmp_dir = config.HOME_DIR / config.EXPORT_TMP_SUBDIR
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix="export-", suffix=".zip", dir=tmp_dir)
    os.close(fd)
    tmp_path = Path(raw)
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for eid, stem, ext, src in picked:
                if isinstance(src, Path):
                    # chk 按路径流式拷贝（zipfile 内部分块读写，不整文件载入
                    # 内存），ZIP_STORED：二进制压缩无收益
                    zf.write(src, _inner(eid, stem, ext),
                             compress_type=zipfile.ZIP_STORED)
                else:
                    zf.writestr(_inner(eid, stem, ext), src)
            if missing:
                zf.writestr("_导出说明.txt", _export_manifest(missing))
    except BaseException:
        tmp_path.unlink(missing_ok=True)  # 磁盘满等失败：不留半成品
        raise
    return tmp_path


def _export_manifest(missing: list[str]) -> str:
    return ("以下选中条目无对应导出文件，未包含在本次导出中：\n"
            + "\n".join(missing) + "\n")


def purge_export_tmp() -> None:
    """启动清扫导出临时包残留（BackgroundTask 删除为主，服务中断时
    BackgroundTask 不执行，残留交本清扫兜底；只认 export-*.zip 形态）。"""
    tmp_dir = config.HOME_DIR / config.EXPORT_TMP_SUBDIR
    if not tmp_dir.is_dir():
        return
    for f in tmp_dir.iterdir():
        if f.is_file() and f.name.startswith("export-") and f.suffix == ".zip":
            with contextlib.suppress(OSError):
                f.unlink()


def archive(execution_id: int) -> None:
    _terminal_row(execution_id)  # 404 语义先行
    executions().set_archived(execution_id)


def requeue(execution_id: int) -> dict:
    """重新排队（原样重跑）：沿用原任务 id 建席，满员 409。

    提交核验（m2-plan §2.5）在建席前统一执行，normalized 标记随响应返回。
    事件（pending.snapshot）由路由层发（#8 模式）。
    """
    row = _terminal_row(execution_id)
    if row["state"] == "succeeded":
        raise err("TASK_STATE_CONFLICT",
                  "succeeded 条目无重新排队（结果沿用或经队列重提交）",
                  {"state": row["state"]}, http=409)
    tid = row["task_id"]
    task = tasks().get(tid)
    if task is None:
        raise not_found("task", tid)
    if task["form"] == "queue_member":
        raise err("TASK_STATE_CONFLICT",
                  "队列成员经所属队列重新提交，不经历史重排队",
                  {"task_id": tid}, http=409)
    limit = int(settings().get("pending_seat_limit"))
    if seats().count() >= limit:
        raise err("PENDING_CAPACITY_FULL", "在途席位满员",
                  {"limit": limit}, http=409)
    # 核验先于建席；B3：warnings 非阻断随响应透传（normalized 取 dict 值）
    res = verify_svc.verify_and_store(tid)
    from .dependencies import validate_single_seat_input
    validate_single_seat_input(tid)  # B6：单任务席位载体符号引用校验
    sid = seats().append(kind="task", task_id=tid)
    tasks().to_seat_task(tid)  # finished → seat_task（沿用原 id）
    return {"seat_id": sid, "task_id": tid,
            "normalized": res["normalized"], "warnings": res["warnings"]}


def return_candidate(execution_id: int) -> dict:
    """退回候选：新 id、带来源标记（编辑再提交入口）。

    取数经 copy_execution_input 单点（m2-plan §9 风险 5「不另写复制逻辑」
    兑现：与队列移除分流同源同口径，物化明文 dep 行随单点剥离，
    oldchk-duplicate-write-fix-plan §2.3）；源不可读的 not_found("input")
    语义保留在本侧（OSError 兜底不变）。
    事件（candidates.changed created）由路由层发（#8 模式）。
    """
    row = _terminal_row(execution_id)
    tid = row["task_id"]
    if tasks().get(tid) is None:
        raise not_found("task", tid)
    try:
        data = candidates_svc.copy_execution_input(execution_id, tid)
    except OSError:
        raise not_found("input", execution_id)
    origin = _ORIGIN_BY_STATE[row["state"]]
    note = row.get("cause") if row["state"] == "failed" else None
    new_id = tasks().create_candidate(row["filename"], origin,
                                      failure_note=note)
    (candidates_svc.default_inputs_dir() / str(new_id)).write_bytes(data)
    row2 = tasks().get(new_id)
    return {"id": row2["id"], "filename": row2["filename"],
            "origin": row2["origin"], "failure_note": row2["failure_note"],
            "created_at": row2["created_at"],
            "title": candidates_svc.resolve_title(new_id),
            # B9 G13：Candidate 契约必填现算字段（与列表/单条 GET 同口径）
            "warning_count": candidates_svc.warning_count(new_id)}


def cleanup(scope: str = "expired") -> dict:
    """手动 chk 清理双档（自动定时延后启用，m1-plan §8 决策点 11）：
    expired（默认）仅删「正常结束且超保留期」的顶层 .chk；all（「清理
    所有」）无视保留期删所有正常结束执行的顶层 .chk；failed 的保全
    chk 两档均不受影响（engine/finalize）。"""
    run_root = config.HOME_DIR / "run"
    succeeded = executions().list_by_state("succeeded")
    if scope == "all":
        return finalize_files.cleanup_all(succeeded, run_root)
    return finalize_files.cleanup_expired(
        succeeded, run_root,
        int(settings().get("chk_rwf_retention_days")), _iso(now_iso()))


def _run_dir(execution_id: int) -> Path:
    return config.HOME_DIR / "run" / str(execution_id)
