"""candidates 域路由（§2.3 / §2.4，M0 mock）。"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi import Response

from ..errors import NOT_FOUND, VALIDATION_FAILED, err
from ..mock import get_state
from starlette import status

router = APIRouter(tags=["candidates"])

_MOL_SUMMARY = {
    "atom_count": 3,
    "formula": "H2O1",
    "variables_present": True,
    "constants_present": False,
}


def _preview(cid: int) -> dict:
    state = get_state()
    cand = state.get_candidate(cid)
    if cand is None:
        raise NOT_FOUND("candidate", cid)
    route = _fake_route(cid)
    link0_missing = []
    if not (cid % 2):
        link0_missing.append("NProcShared")
    if not (cid % 3):
        link0_missing.append("Mem")
    return {
        "candidate_id": cid,
        "filename": cand["filename"],
        "blocks": {
            "link0": {"lines": [f"%mem={int(state.get_runtime('link0_mem_gb'))}GB"],
                      "missing": link0_missing},
            "route": route,
            "title": cand["title"],
            "charge_mult": "0 1",
            "molecule": dict(_MOL_SUMMARY),
            "additional_sections": [
                {"lines": ["%chk=out.chk"], "terminator_blank": True}
            ],
        },
        "parse_errors": [],
    }


@router.get("/candidates")
def list_candidates(origin: str | None = None, page: int = 1,
                    page_size: int = 50) -> dict:
    state = get_state()
    items = [dict(c) for c in state.candidates]
    if origin:
        items = [c for c in items if c["origin"] == origin]
    items.sort(key=lambda c: c["id"], reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    paged = items[start:start + page_size]
    return {"items": paged, "page": page, "page_size": page_size, "total": total}


@router.post("/candidates", status_code=status.HTTP_201_CREATED)
def import_candidates(files: list[str] | None = None,
                      mode: str = "files") -> dict:
    if mode not in ("files", "folder"):
        raise VALIDATION_FAILED([{"field": "mode", "reason": "must_be_files_or_folder"}])
    state = get_state()
    out = []
    for fn in files or ["untitled.gjf"]:
        cand = state.add_candidate(fn)
        state.emit("candidates.changed",
                   {"action": "created", "candidate_id": cand["id"]})
        out.append({"id": cand["id"], "filename": cand["filename"]})
    return {"files": out}


@router.get("/candidates/{id}")
def get_candidate(id: int) -> dict:
    cand = get_state().get_candidate(id)
    if cand is None:
        raise NOT_FOUND("candidate", id)
    return dict(cand)


@router.delete("/candidates/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(id: int) -> Response:
    if not get_state().remove_candidate(id):
        raise NOT_FOUND("candidate", id)
    get_state().emit("candidates.changed",
                     {"action": "deleted", "candidate_id": id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/candidates/{id}/preview")
def preview_candidate(id: int) -> dict:
    return _preview(id)


@router.get("/candidates/{id}/input")
def get_candidate_input(id: int) -> Response:
    state = get_state()
    if state.get_candidate(id) is None:
        raise NOT_FOUND("candidate", id)
    text = _render_routefied_input(id)
    return Response(content=text, media_type="text/plain; charset=utf-8")


@router.put("/candidates/{id}/blocks/{section}")
def save_block(id: int, section: str, payload: dict) -> dict:
    state = get_state()
    if state.get_candidate(id) is None:
        raise NOT_FOUND("candidate", id)
    if section == "molecule":
        raise err("INVALID_REQUEST", "molecule 节不可编辑", http=400)
    lines = payload.get("lines")
    warnings = []
    for ln, text in enumerate(lines or [], 1):
        if "Opit" in str(text):
            warnings.append({"line": ln, "keyword": "Opit",
                             "kind": "keyword_spell", "suggestion": "Opt"})
    return {**_preview(id), "warnings": warnings}


@router.post("/candidates/{id}/submit")
def submit_candidate(id: int, payload: dict | None = None) -> dict:
    state = get_state()
    cand = state.get_candidate(id)
    if cand is None:
        raise NOT_FOUND("candidate", id)
    limit = int(state.get_runtime("seat_limit"))
    if len(state.seats) >= limit:
        raise err("PENDING_CAPACITY_FULL", "在途席位满员",
                  {"limit": limit}, http=409)
    seat_id = state.next_id()
    state.seats.append({
        "seat_id": seat_id, "kind": "task", "task_id": id, "queue_id": None,
        "position": len(state.seats), "members": [{
            "task_id": id, "filename": cand["filename"], "state": "staged",
        }], "locked": False,
    })
    state.remove_candidate(id)
    state.emit("candidates.changed",
               {"action": "moved_out", "candidate_id": id})
    state.emit("pending.snapshot", state.pending())
    return {"seat_id": seat_id, "task_id": id}


def _fake_route(cid: int) -> str:
    return "#B3LYP/6-31G(d) Opt" if cid % 2 else "# B3LYP/6-31G(d) Opit"


def _render_routefied_input(cid: int) -> str:
    """以契约规定的输入原文形态返回（LF）；仅 key 由 C==id 派生。"""
    cand = get_state().get_candidate(cid)
    if cand is None:
        raise NOT_FOUND("candidate", cid)
    return (f"%chk=run/{cid}.chk\n"
            f"%nprocshared=4\n%mem=8GB\n\n"
            f"{_fake_route(cid)}\n\n"
            f"{cand['title']}\n\n0 1\n\nO 0 0 0\nH 0 0 0.95\nH 0 0.75 -0.6\n\n")