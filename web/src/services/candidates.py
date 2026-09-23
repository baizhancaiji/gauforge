"""候选领域服务（B3）：导入 / 剔除 / title 实时解析。

- 导入即拷贝：inputs/<id> 按候选 id 存输入副本，与源文件彻底独立
  （roadmap §2.4）；原文落盘不转换换行（CRLF 保留，M2 编辑保存才转 LF）。
- 整批原子（m1-plan §8 决策点 2）：全部文件校验通过才建行+拷贝；任一失败
  422 + details 逐文件，不产生部分导入。
- title 不落库：展示时实时解析注入（roadmap §2.6 ①），文件缺失/解码失败
  /解析失败回落 null。
- 重复导入同一文件 → 两条候选不同 id（roadmap §2.4）；同名且内容哈希一致
  时结果带 duplicate 提示（m1-plan §5 测试表「哈希+内容双校验」：同名 +
  同 sha256）。

mode=folder 与 files 服务端语义相同：文件清单由前端给定，后端不做服务端
目录扫描（路径边界 roadmap §2.4）。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .. import config
from ..errors import not_found, validation_failed
from ..parse.blocks import parse_input
from ..store import tasks

SUPPORTED_EXTS = (".gjf", ".com")
_File = tuple[str, bytes]  # (filename, 原始字节)


def _inputs_default() -> Path:
    return config.HOME_DIR / "inputs"


def _basename(filename: str) -> str:
    return Path(filename).name


def _validate_one(filename: str, data: bytes) -> dict | None:
    """单文件校验：通过返回 None；否则返回逐文件错误条目。"""
    name = _basename(filename)
    if not name:
        return {"filename": filename, "reason": "INVALID_FILENAME",
                "message": "文件名为空"}
    if Path(name).suffix.casefold() not in SUPPORTED_EXTS:
        return {"filename": name, "reason": "UNSUPPORTED_EXTENSION",
                "message": "仅支持 .gjf/.com（不区分大小写）"}
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return {"filename": name, "reason": "INVALID_ENCODING",
                "message": "非 UTF-8 文本"}
    r = parse_input(text)
    if r["multistep"]:
        return {"filename": name, "reason": "INPUT_MULTISTEP_UNSUPPORTED",
                "message": "多步任务（--Link1--）不支持"}
    if r["parse_errors"]:
        first = r["parse_errors"][0]
        return {"filename": name, "reason": "PARSE_FAILED",
                "message": f"解析失败：{first['message']}（第 {first['line']} 行）",
                "parse_errors": r["parse_errors"]}
    return None


def _content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_duplicate(name: str, data_hash: str, inputs_dir: Path) -> bool:
    """同名且已存副本内容哈希一致 → 重复提示（哈希+内容双校验）。"""
    for row in tasks().list_by_form("candidate"):
        if row["filename"] != name:
            continue
        try:
            stored = (inputs_dir / str(row["id"])).read_bytes()
        except OSError:
            continue
        if _content_hash(stored) == data_hash:
            return True
    return False


def import_files(files: list[_File], *, mode: str = "files",
                 inputs_dir: Path | None = None) -> list[dict]:
    """整批导入：校验全部通过才建行+拷贝；任一失败抛 422（details 逐文件）。

    返回 CandidateCreate.files 条目 [{"id", "filename", "duplicate"}]；
    duplicate 为契约之外的提示字段（§5 测试表语义）。
    """
    if mode not in ("files", "folder"):
        raise validation_failed([{"field": "mode",
                                  "reason": "must_be_files_or_folder"}])
    if not files:
        raise validation_failed([{"field": "files", "reason": "empty"}])
    ind = inputs_dir if inputs_dir is not None else _inputs_default()

    errors = [e for e in (_validate_one(fn, data) for fn, data in files) if e]
    if errors:
        raise validation_failed(errors)

    ind.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    created: list[tuple[int, Path]] = []
    try:
        for fn, data in files:
            name = _basename(fn)
            dup = _is_duplicate(name, _content_hash(data), ind)
            tid = tasks().create_candidate(name, "imported")
            path = ind / str(tid)
            path.write_bytes(data)  # 原文落盘，CRLF 不转
            created.append((tid, path))
            out.append({"id": tid, "filename": name, "duplicate": dup})
    except Exception:
        # 补偿回滚：兑现整批原子（磁盘故障等运行期异常也不留半批）
        for tid, path in created:
            path.unlink(missing_ok=True)
            tasks().delete(tid)
        raise
    return out


def delete_candidate(task_id: int, inputs_dir: Path | None = None) -> None:
    """剔除候选：删 inputs/<id> 与记录（删除任务实体唯一入口）。

    仅 candidate 形态可删（roadmap §2.4）；其余形态按不存在处理。
    """
    ind = inputs_dir if inputs_dir is not None else _inputs_default()
    row = tasks().get(task_id)
    if row is None or row["form"] != "candidate":
        raise not_found("candidate", task_id)
    (ind / str(task_id)).unlink(missing_ok=True)
    tasks().delete(task_id)


def resolve_title(task_id: int, inputs_dir: Path | None = None) -> str | None:
    """实时解析 title（不落库）：文件缺失/解码失败/缺节 → None。"""
    ind = inputs_dir if inputs_dir is not None else _inputs_default()
    try:
        text = (ind / str(task_id)).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return parse_input(text)["blocks"]["title"]
