"""Classroom Edition API: materials -> grounded draft board -> teacher review -> live room -> evidence."""
from __future__ import annotations

import copy
import json
import secrets
import statistics
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from . import store
from .classroom import ROOMS, Room, cleanup, find_room
from .llm import LLM, Meter
from .materials import Passage, extract, read_images
from .writer import write_board

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample" / "sample_board.json"
router = APIRouter(prefix="/api")
MATERIALS: dict[str, dict] = {}          # materials_id -> {"passages": [...], "created": t, "info": {...}}
llm_ref: dict = {}                        # set by server.py so both editions share one LLM client + budget


def _llm() -> LLM:
    return llm_ref["llm"]


def _rate(request: Request, key: str, limit: int) -> None:
    from .server import _ip, _rate as rate
    rate(f"{key}:{_ip(request)}", limit)


def _owned(board_id: str, token: str | None) -> dict:
    b = store.get_board(board_id)
    if not b:
        raise HTTPException(404, "Board not found.")
    if not token or not secrets.compare_digest(token, b["token"]):
        raise HTTPException(403, "This board belongs to another teacher (missing or wrong teacher key).")
    return b


# ---------------------------------------------------------------- materials + boards
class MaterialItem(BaseModel):
    name: str = Field("pasted text", max_length=120)
    text: str | None = Field(None, max_length=300_000)
    data_b64: str | None = Field(None, max_length=17_000_000)


class Materials(BaseModel):
    items: list[MaterialItem] = Field(..., max_length=8)


@router.post("/materials")
async def upload_materials(body: Materials, request: Request):
    _rate(request, "materials", 30)
    ex = extract([i.model_dump() if hasattr(i, "model_dump") else i.__dict__ for i in body.items])
    ocr_meter = Meter()
    if ex.image_pages:                     # slides exported as pictures: the reader agent transcribes them
        ex = await read_images(_llm(), ocr_meter, ex)
    if not ex.passages:
        raise HTTPException(422, ("No readable text found. Slides saved as pictures need the live AI to read them. "
                                  if ex.image_pages else "No readable text found. ") + "; ".join(
            f"{f['name']}: {f.get('error', 'empty')}" for f in ex.files))
    mid = store.new_id(10)
    now = time.time()
    for k in [k for k, v in MATERIALS.items() if now - v["created"] > 6 * 3600]:
        MATERIALS.pop(k, None)
    MATERIALS[mid] = {"passages": ex.passages, "created": now, "info": ex.public(), "ocr_cost": ocr_meter.public()}
    return {"materials_id": mid, **ex.public()}


class BuildReq(BaseModel):
    materials_id: str
    categories: int = Field(5, ge=2, le=6)
    rows: int = Field(5, ge=3, le=5)
    audience: str = Field("university students", max_length=80)
    focus: str = Field("", max_length=300)
    client_started_at: float | None = None     # ms timestamp when the teacher opened the builder


@router.post("/boards")
async def build_board(body: BuildReq, request: Request):
    m = MATERIALS.get(body.materials_id)
    if not m:
        raise HTTPException(404, "Those materials expired. Please upload them again.")
    _rate(request, "build", 8)
    meter = Meter()
    res = await write_board(_llm(), meter, m["passages"], body.categories, body.rows, body.audience, body.focus)
    ocr = m.get("ocr_cost") or {}
    if ocr.get("calls"):                   # the cost of reading picture-only slides belongs to this build
        for k in ("calls", "input_tokens", "cached_tokens", "output_tokens"):
            setattr(meter, k, getattr(meter, k) + ocr.get(k, 0))
        meter.cost_usd += ocr.get("cost_usd", 0)
        meter.by_agent["reader"] = ocr.get("by_agent", {}).get("reader", {})
    if not res["ok"]:
        raise HTTPException(422 if "AI" not in res["error"] else 503, res["error"])
    build = {"source": "materials", "materials": m["info"]["files"], "passages": len(m["passages"]),
             "ocr_pages": m["info"].get("ocr_pages", 0),
             "hidden_removed": m["info"]["hidden_removed"], "ai_directed_removed": len(m["info"]["ai_directed_removed"]),
             "writer": res["stats"], "cost": meter.public(), "requested": body.model_dump(exclude={"materials_id"})
             if hasattr(body, "model_dump") else {}, "server_started": time.time() - res["stats"].get("seconds", 0),
             "client_started_at": body.client_started_at, "edits": {"edited": 0, "deleted": 0, "swapped": 0}}
    board = res["board"]
    board_id, token = store.save_board(board, build)
    return {"board_id": board_id, "teacher_token": token, "board": board, "build": build}


@router.post("/boards/sample")
async def sample_board(request: Request):
    _rate(request, "build", 30)
    board = json.loads(SAMPLE.read_text())
    build = {"source": "sample", "writer": {"generated": 20, "kept": 20, "rejected_by_code": 0,
             "rejected_by_verifier": 0, "flagged": 0}, "cost": Meter().public(),
             "edits": {"edited": 0, "deleted": 0, "swapped": 0}, "server_started": time.time()}
    board_id, token = store.save_board(board, build)
    return {"board_id": board_id, "teacher_token": token, "board": board, "build": build}


@router.get("/boards/{board_id}")
async def get_board(board_id: str, x_teacher_token: str | None = Header(None)):
    b = _owned(board_id, x_teacher_token)
    return {"board_id": b["id"], "status": b["status"], "board": b["board"], "build": b["build"]}


class Edit(BaseModel):
    c: int
    r: int
    action: str = Field(..., pattern="^(update|delete|swap)$")
    clue: str | None = Field(None, max_length=300)
    answer: str | None = Field(None, max_length=80)
    accept: list[str] | None = None


@router.post("/boards/{board_id}/edit")
async def edit_board(board_id: str, body: Edit, x_teacher_token: str | None = Header(None)):
    b = _owned(board_id, x_teacher_token)
    board, build = b["board"], b["build"]
    try:
        cat = board["categories"][body.c]
        q = cat["clues"][body.r]
    except (IndexError, KeyError):
        raise HTTPException(404, "No such clue.")
    edits = build.setdefault("edits", {"edited": 0, "deleted": 0, "swapped": 0})
    if body.action == "update":
        if body.clue:
            q["clue"] = body.clue.strip()
        if body.answer:
            q["answer"] = body.answer.strip()
        acc = [a.strip()[:80] for a in (body.accept or []) if a.strip()][:6]
        q["accept"] = [q["answer"]] + [a for a in acc if a != q["answer"]]
        q["status"], q["edited"] = "ok", True
        edits["edited"] += 1
    elif body.action in ("swap", "delete"):
        spares = cat.setdefault("spares", [])
        if body.action == "swap" and not spares:
            raise HTTPException(409, "No spare clues left in this category.")
        if spares:
            new = spares.pop(0)
            new["value"] = q.get("value", 200)
            cat["clues"][body.r] = new
        else:
            cat["clues"].pop(body.r)
            for i, x in enumerate(cat["clues"]):
                x["value"] = 200 * (i + 1)
        edits["swapped" if body.action == "swap" else "deleted"] += 1
    board["categories"] = [c for c in board["categories"] if c["clues"]]
    store.save_board(board, build, board_id=b["id"], token=b["token"], status=b["status"])
    return {"board": board, "build": build}


class Approve(BaseModel):
    client_seconds: float | None = Field(None, ge=0, le=86_400)


@router.post("/boards/{board_id}/approve")
async def approve(board_id: str, body: Approve, x_teacher_token: str | None = Header(None)):
    b = _owned(board_id, x_teacher_token)
    build = b["build"]
    if "approved_at" not in build:
        build["approved_at"] = time.time()
        build["build_minutes_server"] = round((build["approved_at"] - build.get("server_started", build["approved_at"])) / 60, 1)
        build["build_minutes_client"] = round(body.client_seconds / 60, 1) if body.client_seconds else None
        total = sum(len(c["clues"]) for c in b["board"]["categories"])
        untouched = sum(1 for c in b["board"]["categories"] for q in c["clues"] if not q.get("edited"))
        build["clues_final"], build["clues_kept_as_written"] = total, untouched
    store.save_board(b["board"], build, board_id=b["id"], token=b["token"], status="ready")
    return {"ok": True, "build": build}


# ---------------------------------------------------------------- rooms
class NewRoom(BaseModel):
    board_id: str
    mode: str = Field("all", pattern="^(all|buzz)$")
    ai_seats: int = Field(0, ge=0, le=3)


@router.post("/rooms")
async def new_room(body: NewRoom, request: Request, x_teacher_token: str | None = Header(None)):
    b = _owned(body.board_id, x_teacher_token)
    _rate(request, "room", 30)
    cleanup()
    room = Room(board_id=b["id"], board=copy.deepcopy(b["board"]), teacher_token=b["token"], llm=_llm(),
                mode=body.mode, ai_seats=body.ai_seats)
    while room.code in ROOMS:
        room.code = Room.__dataclass_fields__["code"].default_factory()
    ROOMS[room.code] = room
    room._save()
    return {"code": room.code, "session_id": room.session_id}


def _room(code: str) -> Room:
    r = find_room(code)
    if not r:
        raise HTTPException(404, "No game with that code. Check the code on the screen.")
    return r


def _host(code: str, token: str | None) -> Room:
    r = _room(code)
    if not token or not secrets.compare_digest(token, r.teacher_token):
        raise HTTPException(403, "Only the teacher's screen can do that.")
    return r


@router.get("/rooms/{code}/host")
async def host_state(code: str, x_teacher_token: str | None = Header(None)):
    r = _host(code, x_teacher_token)
    await r.tick()
    return r.public(host=True)


class TeacherAct(BaseModel):
    action: str = Field(..., max_length=20)
    c: int | None = None
    r: int | None = None
    player_id: str | None = None
    correct: bool | None = None


@router.post("/rooms/{code}/teacher")
async def teacher_act(code: str, body: TeacherAct, x_teacher_token: str | None = Header(None)):
    r = _host(code, x_teacher_token)
    await r.tick()
    res = await r.teacher(body.action, {k: v for k, v in body.__dict__.items() if v is not None})
    out = r.public(host=True)
    if not res.get("ok"):
        out["error"] = res.get("error")
    return out


class Join(BaseModel):
    name: str = Field("", max_length=30)


@router.post("/rooms/{code}/join")
async def join(code: str, body: Join, request: Request):
    _rate(request, "join", 60)
    r = _room(code)
    res = r.join(body.name)
    if not res["ok"]:
        raise HTTPException(409, res["error"])
    return res


def _seat(r: Room, pid: str | None, token: str | None):
    s = r.seats.get(pid or "")
    if not s or s.ai or not token or not secrets.compare_digest(token, s.token):
        raise HTTPException(403, "Please join the game again.")
    return s


@router.get("/rooms/{code}/me")
async def me(code: str, x_player_id: str | None = Header(None), x_player_token: str | None = Header(None)):
    r = _room(code)
    s = _seat(r, x_player_id, x_player_token)
    s.seen = time.time()
    await r.tick()
    return r.public(seat=s)


class PlayAct(BaseModel):
    action: str = Field(..., pattern="^(answer|buzz)$")
    text: str = Field("", max_length=120)


@router.post("/rooms/{code}/play")
async def play(code: str, body: PlayAct, x_player_id: str | None = Header(None),
               x_player_token: str | None = Header(None)):
    r = _room(code)
    s = _seat(r, x_player_id, x_player_token)
    res = await r.player(s, body.action, {"text": body.text})
    out = r.public(seat=s)
    if not res.get("ok"):
        out["error"] = res.get("error")
    return out


# ---------------------------------------------------------------- feedback + evidence
class Feedback(BaseModel):
    session_id: str
    role: str = Field(..., pattern="^(teacher|student)$")
    manual_minutes: float | None = Field(None, ge=0, le=1000)     # teacher: how long by hand?
    usefulness: int | None = Field(None, ge=1, le=5)
    accuracy: int | None = Field(None, ge=1, le=5)                # teacher: were the clues correct?
    use_again: str | None = Field(None, max_length=10)
    reteach_matches: str | None = Field(None, max_length=10)      # teacher: did the reteach list match reality?
    helped: int | None = Field(None, ge=1, le=5)                  # student: did this help you review?
    comment: str | None = Field(None, max_length=1000)
    role_title: str | None = Field(None, max_length=40)           # professor / TA / ...


@router.post("/feedback")
async def feedback(body: Feedback, request: Request, x_teacher_token: str | None = Header(None),
                   x_player_id: str | None = Header(None), x_player_token: str | None = Header(None)):
    _rate(request, "feedback", 20)
    s = store.get_session(body.session_id)
    if not s:
        raise HTTPException(404, "Unknown session.")
    if body.role == "teacher":
        _owned(s["board_id"], x_teacher_token)
    data = {k: v for k, v in body.__dict__.items() if v is not None and k not in ("session_id", "role")}
    store.add_feedback(body.session_id, s["board_id"], body.role, data)
    return {"ok": True}


@router.get("/sessions/{session_id}/report")
async def report(session_id: str, x_teacher_token: str | None = Header(None)):
    s = store.get_session(session_id)
    if not s:
        raise HTTPException(404, "Unknown session.")
    b = _owned(s["board_id"], x_teacher_token)
    return {"session": s, "board": {"title": b["title"], "build": b["build"]},
            "feedback": [f for f in store.all_feedback() if f["session_id"] == session_id]}


def _med(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(statistics.median(xs), 1) if xs else None


@router.get("/evidence")
async def evidence(include_sample: int = 0):
    """Anonymous roll-up of every board build and class session on this server: the Tier-3 evidence.
    Sessions played on the built-in sample board are left out unless ?include_sample=1."""
    all_b = store.all_boards()
    real = {b["id"] for b in all_b if b["build"].get("source") == "materials"}
    boards = [b for b in all_b if b["id"] in real]
    sessions = [s for s in store.all_sessions() if s.get("clues_played") and (include_sample or s["board_id"] in real)]
    fb = [f for f in store.all_feedback() if include_sample or f["board_id"] in real]
    tfb, sfb = [f for f in fb if f["role"] == "teacher"], [f for f in fb if f["role"] == "student"]
    w = [b["build"].get("writer", {}) for b in boards]
    gen = sum(x.get("generated", 0) for x in w)
    approved = [b for b in boards if b["build"].get("approved_at")]
    clues_final = sum(b["build"].get("clues_final", 0) for b in approved)
    kept_as_is = sum(b["build"].get("clues_kept_as_written", 0) for b in approved)
    build_cost = [b["build"].get("cost", {}).get("cost_usd", 0) for b in boards]
    sess_cost = [s.get("llm", {}).get("cost_usd", 0) for s in sessions]
    return {
        "generated_at": time.time(),
        "boards": {"built": len(boards), "approved": len(approved),
                   "median_build_minutes": _med([b["build"].get("build_minutes_client") or b["build"].get("build_minutes_server")
                                                 for b in approved]),
                   "clues_generated": gen,
                   "rejected_by_code": sum(x.get("rejected_by_code", 0) for x in w),
                   "rejected_by_verifier": sum(x.get("rejected_by_verifier", 0) for x in w),
                   "flagged_for_teacher": sum(x.get("flagged", 0) for x in w),
                   "clues_final": clues_final, "kept_without_edits": kept_as_is,
                   "pct_kept_without_edits": round(100 * kept_as_is / clues_final) if clues_final else None,
                   "hidden_text_removed": sum(b["build"].get("hidden_removed", 0) for b in boards),
                   "median_cost_usd": _med(build_cost)},
        "sessions": {"run": len(sessions), "students": sum(s.get("students", 0) for s in sessions),
                     "clues_played": sum(s.get("clues_played", 0) for s in sessions),
                     "median_avg_pct_correct": _med([s.get("avg_pct_correct") for s in sessions]),
                     "overrides": sum(s.get("overrides", 0) for s in sessions),
                     "median_minutes": _med([s.get("minutes") for s in sessions]),
                     "median_cost_usd": _med(sess_cost),
                     "reteach_examples": [{"title": s.get("title"), **x} for s in sessions[:5] for x in s.get("reteach", [])[:2]]},
        "teacher_feedback": {"responses": len(tfb),
                             "median_manual_minutes": _med([f.get("manual_minutes") for f in tfb]),
                             "median_usefulness": _med([f.get("usefulness") for f in tfb]),
                             "median_accuracy": _med([f.get("accuracy") for f in tfb]),
                             "use_again": {k: sum(1 for f in tfb if f.get("use_again") == k) for k in ("yes", "maybe", "no")},
                             "reteach_matches": {k: sum(1 for f in tfb if f.get("reteach_matches") == k) for k in ("yes", "partly", "no")},
                             "comments": [{"role": f.get("role_title"), "text": f["comment"]} for f in tfb if f.get("comment")][-12:]},
        "student_feedback": {"responses": len(sfb), "median_helped": _med([f.get("helped") for f in sfb])},
    }
