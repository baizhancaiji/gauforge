"""批量 fchk 导出作业（3.8.0 工具箱 B17，toolbox-plan §2.1/§4.7）。

进程内作业表（dict + 锁）+ 单后台工作线程（守护线程，串行转换——避免
与 G16 派发争抢 CPU）。零存储迁移（作业表内存、进程重启即消亡——单进程
部署前提，main.py 经 uvicorn.run 单进程运行）；重启后作业 id 一律 404，
`.part`/ZIP 由 purge_export_tmp 启动清扫删除（history 扩认
fchk-export-* 形态），已转换的 input.fchk 持久保留可重新导出。

状态机：queued → running → packing → done；queued/running/packing 可转
cancelled（queued 即时生效、running 于当前条目结束后生效、packing 于
条目写入间隙生效——history._pack_entries cancelled_check 注入）；取消/
失败统一 cleanup_job_artifacts（删 .part 与作业 ZIP，不留作业私有临时
文件；已落盘 input.fchk 为持久分析产物不随取消删除）；running/packing
未捕获异常或无任何成功条目（不出包）→ failed；done 超 TTL
（FCHK_EXPORT_TTL_S=1800）惰性转 expired 后移除记录（status/download/
创建时清扫，无常驻定时器）。

分类（创建时一次扫描，去重保序）：非终态/不存在 → missing「条目不存在
或非终态」；run/<id>/input.fchk 有效成品（fchk_head_valid 锚点判据复用
B12 finalize 单点）→ reused 零转换；skipped/无 chk 资产/资产越界 →
missing（「未运行无执行产物」/「无 chk 资产（已清理或从未产生）」/
「chk 资产越界（不读取）」）；其余终态 → 转换候选。创建时全缺（无
有效 fchk 且无候选）→ 404 NOT_FOUND（details.missing）。归档条目同口径
放行。执行时再次命中有效 fchk 计 reused（不重复转换）。

转换执行：逐候选复用 chktools.ensure_fchk 核心（幂等命中/前置体检闸/
containment/原子落盘/单项超时体检 120s + formchk 300s），按条目捕获
ApiError/OSError 记 failed（条目级失败不使作业失败——verdict≠ok/越界/
工具缺失/非零退出/超时只记数与缺漏说明）；作业仅在打包异常、未捕获
异常或无任何成功条目时转 failed。总预算 FCHK_BATCH_BUDGET_S=900（转换
阶段墙钟）：每候选启动前按单项最坏 420s 预留（体检 120s + formchk
300s 之和），剩余不足即停止转换、该候选与其余未处理候选记 missing
「超出批量转换时间预算」；已启动条目允许跑完，不中途杀进程（核验项 7
实测：真机 formchk 秒级 0.08–0.15s，远低于预留——常量维持计划值）。

打包：复用 history 导出 helper（compress_type/casualty_text/取消检查
参数化——fchk 条目 ZIP_DEFLATED 文本可压缩、chk 既有 ZIP_STORED 语义
不变）；条目 `<stem>.fchk` 平铺、同一 stem 冲突组「三位补零执行 id-」
前缀；缺漏 `_导出说明.txt` 按 fchk 维度文案（不复用 chk 资产文案）；
读清竞态弃包重建沿 history 同口径。临时包落 config.HOME_DIR /
EXPORT_TMP_SUBDIR，先写 fchk-export-<job_id>.zip.part，完成后 os.replace
为 .zip（下载只服务 .zip，FileResponse 流式发送，包名
gauforge-fchk-<时刻>.zip）；ZIP 保留 TTL 支持重复下载。

并发：同一时刻仅一个活动作业（queued/running/packing），重复创建 409
TASK_STATE_CONFLICT（details.active_job_id）；作业 id uuid4().hex 不可猜，
下载只认作业表登记的路径。
"""
from __future__ import annotations

import os
import re
import threading
import time
import uuid
import zipfile
from pathlib import Path

from .. import config
from ..engine import finalize
from ..errors import ApiError, err, not_found
from . import chktools, history as history_svc
from .dependencies import execution_chk_asset

FCHK_BATCH_BUDGET_S = 900   # 作业总预算（转换阶段墙钟）
FCHK_EXPORT_TTL_S = 1800    # ZIP 保留 30 分钟（惰性判定）
_PER_ITEM_RESERVE_S = 420   # 单项最坏预留（体检 120s + formchk 300s）

_TERMINAL = ("succeeded", "failed", "skipped")
_ACTIVE = ("queued", "running", "packing")
_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")

_jobs: dict[str, dict] = {}
_lock = threading.Lock()

_CASUALTY_TEXT = "无 fchk（转换产物已清理）"
_MANIFEST_HEAD = "以下选中条目无对应 fchk，未包含在本次导出中：\n"


def _run_dir(execution_id: int) -> Path:
    return config.HOME_DIR / "run" / str(execution_id)


def _stem_of(filename: str) -> str:
    return filename.rsplit(".", 1)[0] if "." in filename else filename


# ---------------- 创建（分类扫描 + 拉起工作线程） ----------------

def create_job(ids: object) -> dict:
    """POST /history/export/fchk：ids 校验/去重/终态扫描/分类 → 202。
    同刻仅一个活动作业；创建时全缺 404。"""
    if (not isinstance(ids, list) or not ids
            or any(isinstance(i, bool) or not isinstance(i, int) or i <= 0
                   for i in ids)):
        raise err("INVALID_REQUEST", "ids 须为非空正整数数组",
                  {"field": "ids"}, http=400)
    uniq = list(dict.fromkeys(ids))
    if len(uniq) > 500:
        raise err("INVALID_REQUEST",
                  "ids 元素数上限 500（更大批次由分批发起承载）",
                  {"field": "ids", "max": 500, "got": len(uniq)}, http=400)
    with _lock:
        active = next((j for j in _jobs.values()
                       if j["state"] in _ACTIVE), None)
        if active is not None:
            raise err("TASK_STATE_CONFLICT", "已有批量 fchk 导出在进行中",
                      {"active_job_id": active["job_id"]}, http=409)
    from ..store import executions  # 延迟导入（store 单例逐用例隔离）
    missing: list[str] = []
    candidates: list[int] = []
    entries: list[tuple[int, str]] = []  # reused：既有有效 fchk 直接入包清单
    missing_count, reused = 0, 0
    for eid in uniq:
        row = executions().get(eid)
        if row is None or row["state"] not in _TERMINAL:
            history_svc._append_missing(missing, eid, "条目不存在或非终态")
            missing_count += 1
            continue
        if finalize.fchk_head_valid(_run_dir(eid) / "input.fchk"):
            reused += 1  # 有效 fchk 直接复用（不查 chk 资产、不跑工具）
            entries.append((eid, _stem_of(row["filename"])))
            continue
        if row["state"] == "skipped":
            history_svc._append_missing(missing, eid, "未运行无执行产物")
            missing_count += 1
            continue
        asset = execution_chk_asset(eid)
        reason = None
        if asset is None:
            reason = "无 chk 资产（已清理或从未产生）"
        else:
            real_asset, real_run = asset.resolve(), _run_dir(eid).resolve()
            if real_asset != real_run and real_run not in real_asset.parents:
                reason = "chk 资产越界（不读取）"
        if reason is not None:
            history_svc._append_missing(missing, eid, reason)
            missing_count += 1
            continue
        candidates.append(eid)
    if reused + len(candidates) == 0:  # 全缺：无有效 fchk 且无转换候选
        raise err("NOT_FOUND", "选中条目均无可用 fchk 来源",
                  {"missing": missing}, http=404)
    job = {"job_id": uuid.uuid4().hex, "state": "queued",
           "total": len(uniq), "processed": reused + missing_count,
           "reused": reused, "converted": 0, "failed": 0,
           "missing": missing_count, "current_eid": None,
           "started": time.monotonic(), "done_at": None, "error": None,
           "cancel": False, "entries": entries, "zip_path": None,
           "part_path": None, "candidates": candidates,
           "missing_notes": list(missing)}
    resp = {"job_id": job["job_id"], "state": "queued",
            "total": job["total"]}  # 竞态防护：响应快照先于线程拉起构造
    with _lock:
        _jobs[job["job_id"]] = job
    threading.Thread(target=_worker, args=(job["job_id"],),
                     name=f"fchk-export-{job['job_id'][:8]}",
                     daemon=True).start()
    return resp


# ---------------- 工作线程（串行转换 → 打包） ----------------

class _Cancelled(Exception):
    """取消信号（转换循环/打包间隙探测到 cancel 标志）。"""


def _worker(job_id: str) -> None:
    job = _jobs.get(job_id)
    if job is None:
        return
    with _lock:
        if job["state"] == "cancelled":  # queued 即时取消已落定
            return
        job["state"] = "running"
    try:
        _convert_phase(job)
        if job["cancel"]:
            raise _Cancelled()
        if job["reused"] + job["converted"] == 0:
            raise err("TASK_STATE_CONFLICT",
                      "全部条目均无可导出 fchk（转换失败或不可转换），"
                      "未生成导出包", {"job_id": job_id}, http=409)
        _pack_phase(job)
    except _Cancelled:
        _finish(job, "cancelled")
    except ApiError as exc:  # 无成功条目等作业级失败（不出包）
        _finish(job, "failed", exc.message)
    except Exception as exc:  # noqa: BLE001 — 未捕获异常转作业级 failed
        _finish(job, "failed", f"作业异常终止（{type(exc).__name__}）")


def _convert_phase(job: dict) -> None:
    candidates = job["candidates"]
    for idx, eid in enumerate(candidates):
        if job["cancel"]:
            raise _Cancelled()
        elapsed = time.monotonic() - job["started"]
        if FCHK_BATCH_BUDGET_S - elapsed < _PER_ITEM_RESERVE_S:
            # 剩余预算不足单项最坏预留：本候选与其余未处理记 missing，停止
            for rest in candidates[idx:]:
                history_svc._append_missing(job["missing_notes"], rest,
                                            "超出批量转换时间预算")
                job["missing"] += 1
                job["processed"] += 1
            job["candidates"] = []
            return
        job["current_eid"] = eid
        try:
            path, generated = chktools.ensure_fchk(eid)
        except (ApiError, OSError) as exc:
            job["failed"] += 1
            job["processed"] += 1
            details = getattr(exc, "details", None)
            verdict = details.get("verdict") \
                if isinstance(details, dict) else None
            note = ("chk 损坏/不完整（体检未通过）"
                    if verdict in ("corrupted", "unreadable")
                    else getattr(exc, "message", None)
                    or "转换失败（工具不可用或执行失败）")
            history_svc._append_missing(job["missing_notes"], eid,
                                        f"转换失败（{note}）")
            continue
        finally:
            job["current_eid"] = None
        if job["cancel"]:
            raise _Cancelled()
        if generated:
            job["converted"] += 1
        else:
            job["reused"] += 1  # 执行时再次命中有效 fchk（不重复转换）
        job["processed"] += 1
        job["entries"].append((eid, _stem_of(
            _exec_filename(eid))))


def _exec_filename(eid: int) -> str:
    from ..store import executions
    row = executions().get(eid)
    return (row or {}).get("filename") or f"execution-{eid}"


def _pack_phase(job: dict) -> None:
    with _lock:
        job["state"] = "packing"
    tmp_dir = config.HOME_DIR / config.EXPORT_TMP_SUBDIR
    tmp_dir.mkdir(parents=True, exist_ok=True)
    zip_path = tmp_dir / f"fchk-export-{job['job_id']}.zip"
    part_path = tmp_dir / f"fchk-export-{job['job_id']}.zip.part"
    job["zip_path"] = zip_path
    job["part_path"] = part_path
    picked = [(eid, stem, "fchk", _run_dir(eid) / "input.fchk")
              for eid, stem in job["entries"]]
    from collections import Counter
    dup = {s for s, n in Counter(stem for _, stem in
                                 job["entries"]).items() if n > 1}

    def _inner(eid: int, stem: str, ext: str) -> str:
        return (f"{eid:03d}-{stem}.{ext}" if stem in dup
                else f"{stem}.{ext}")

    missing = list(job["missing_notes"])
    pending = list(picked)
    while True:
        try:
            with zipfile.ZipFile(part_path, "w",
                                 zipfile.ZIP_DEFLATED) as zf:
                casualty = history_svc._pack_entries(
                    zf, pending, _inner, missing, "fchk",
                    compress_type=zipfile.ZIP_DEFLATED,
                    casualty_text=_CASUALTY_TEXT,
                    manifest_head=_MANIFEST_HEAD,
                    cancelled_check=lambda: job["cancel"])
        except history_svc.PackCancelled:
            part_path.unlink(missing_ok=True)
            raise _Cancelled() from None
        if casualty is None:
            break
        # 读清竞态（打包期）：转换产物中途被清，弃包重建并按缺登记
        history_svc._append_missing(missing, casualty[0], _CASUALTY_TEXT)
        pending = [p for p in pending if p[:3] != casualty]
        job["missing"] += 1
        job["failed"] += 1
        job["processed"] += 1
        part_path.unlink(missing_ok=True)
    job["missing_notes"] = missing
    os.replace(part_path, zip_path)  # .part → .zip（下载只服务 .zip）
    job["done_at"] = time.monotonic()
    with _lock:
        job["state"] = "done"


def _finish(job: dict, state: str, message: str | None = None) -> None:
    """终态落定：failed/cancelled 统一清理作业私有临时文件（.part/作业
    ZIP 不残留）；记录仅保留 state/计数供前端轮询、随进程重启消亡。"""
    with _lock:
        job["state"] = state
        if message is not None:
            job["error"] = {"message": message}
        for key in ("part_path", "zip_path"):
            path = job.get(key)
            if isinstance(path, Path):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
                job[key] = None


# ---------------- 状态 / 下载 / 取消 ----------------

def _sweep_expired() -> None:
    """TTL 惰性清扫：done 超 FCHK_EXPORT_TTL_S → 删 ZIP、移除记录
    （status/download/创建时调用，无常驻定时器）。"""
    now = time.monotonic()
    expired = [jid for jid, j in _jobs.items()
               if j["state"] == "done" and j["done_at"] is not None
               and now - j["done_at"] > FCHK_EXPORT_TTL_S]
    for jid in expired:
        job = _jobs.pop(jid, None)
        if job:
            _finish(job, "expired")  # 清理 ZIP（记录随 pop 消亡）


def get_job(job_id: str) -> dict:
    if not isinstance(job_id, str) or not _JOB_ID_RE.match(job_id):
        raise _job_not_found(job_id)
    _sweep_expired()
    job = _jobs.get(job_id)
    if job is None:
        raise _job_not_found(job_id)
    elapsed = time.monotonic() - job["started"]
    return {"job_id": job["job_id"], "state": job["state"],
            "total": job["total"], "processed": job["processed"],
            "reused": job["reused"], "converted": job["converted"],
            "failed": job["failed"], "missing": job["missing"],
            "current_eid": job["current_eid"],
            "elapsed_s": int(elapsed), "error": job["error"]}


def get_job_zip(job_id: str) -> Path:
    """下载取数：仅 done 可下载（其余状态 409 TASK_STATE_CONFLICT）；
    未知/过期 404。"""
    if not isinstance(job_id, str) or not _JOB_ID_RE.match(job_id):
        raise _job_not_found(job_id)
    _sweep_expired()
    job = _jobs.get(job_id)
    if job is None:
        raise _job_not_found(job_id)
    if job["state"] != "done":
        raise err("TASK_STATE_CONFLICT",
                  "作业尚未完成或已取消/失败，无可下载包",
                  {"job_id": job_id, "state": job["state"]}, http=409)
    return job["zip_path"]


def cancel_job(job_id: str) -> dict:
    if not isinstance(job_id, str) or not _JOB_ID_RE.match(job_id):
        raise _job_not_found(job_id)
    _sweep_expired()
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise _job_not_found(job_id)
        if job["state"] not in _ACTIVE:
            raise err("TASK_STATE_CONFLICT",
                      "作业已终态（done/failed/expired/cancelled），"
                      "不可取消",
                      {"job_id": job_id, "state": job["state"]}, http=409)
        job["cancel"] = True
        if job["state"] == "queued":  # queued 即时生效（工作线程启动让位）
            job["state"] = "cancelled"
            for key in ("part_path", "zip_path"):
                path = job.get(key)
                if isinstance(path, Path):
                    path.unlink(missing_ok=True)
                    job[key] = None
        return {"job_id": job_id, "state": job["state"]}


def _job_not_found(job_id: object) -> ApiError:
    return not_found("export_job", job_id)
