"""FastAPI backend + static frontend.

    uvicorn app.server:app --reload --port 8000      ->  http://localhost:8000
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agents import Agents
from .bank import load_bank
from .engine import Game, new_game
from .llm import BUDGET, LLM, MODEL

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
LOG = Path(os.getenv("GAME_LOG", str(ROOT / "data" / "games_log.jsonl")))
MAX_GAMES = int(os.getenv("MAX_GAMES", "300"))
GAME_TTL_S = int(os.getenv("GAME_TTL_S", str(3 * 3600)))
NEW_GAMES_PER_HOUR = int(os.getenv("NEW_GAMES_PER_HOUR", "20"))
CUSTOM_BOARDS_PER_HOUR = int(os.getenv("CUSTOM_BOARDS_PER_HOUR", "4"))

app = FastAPI(title="Yale Jeopardy", version="1.0")
if os.getenv("CORS_ORIGINS"):
    app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS").split(","),
                       allow_methods=["GET", "POST"], allow_headers=["*"])

llm = LLM()
GAMES: dict[str, Game] = {}
LOCKS: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
HITS: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                               "script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


def _ip(req: Request) -> str:
    fwd = req.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (req.client.host if req.client else "?")


def _rate(key: str, limit: int) -> None:
    now, q = time.time(), HITS[key]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many new games from this device this hour. Try again later.")
    q.append(now)


def _cleanup() -> None:
    now = time.time()
    for gid in [k for k, g in GAMES.items() if now - g.touched > GAME_TTL_S]:
        GAMES.pop(gid, None)
        LOCKS.pop(gid, None)
    while len(GAMES) > MAX_GAMES:
        oldest = min(GAMES.values(), key=lambda g: g.touched)
        GAMES.pop(oldest.id, None)


def _log_end(g: Game) -> None:
    if g.phase != "over" or getattr(g, "_logged", False):
        return
    g._logged = True
    entry = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "game": g.id, "board": g.board.title,
             "verified": g.board.verified, "level": g.level, "mode": g.agents.llm.mode(),
             "scores": {p.name if p.ai else "human": p.score for p in g.players},
             "injection_attempts_blocked": g.flags, "llm": g.meter.public()}
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


class NewGame(BaseModel):
    name: str = Field("You", max_length=16)
    size: str = Field("quick", pattern="^(quick|full)$")
    level: str = Field("normal", pattern="^(easy|normal|hard)$")
    topic: str | None = Field(None, max_length=60)


class Pick(BaseModel):
    cell_id: str = Field(..., max_length=12)


class Wager(BaseModel):
    amount: int = Field(..., ge=0, le=100_000)


class Answer(BaseModel):
    text: str = Field("", max_length=200)


def _game(gid: str) -> Game:
    g = GAMES.get(gid)
    if not g:
        raise HTTPException(404, "Game not found (it may have expired). Start a new one.")
    return g


async def _act(gid: str, fn, *args) -> dict:
    g = _game(gid)
    async with LOCKS[gid]:
        res = await fn(g, *args)
    if res and not res.get("ok", True):
        return JSONResponse({"error": res["error"], "game": g.public()}, status_code=409)
    _log_end(g)
    out = g.public()
    if res and res.get("beaten_by"):
        out["notice"] = f"{res['beaten_by']} buzzed first!"
    return out


# ------------------------------------------------------------------ routes
@app.get("/api/health")
async def health():
    from .llm import KEY_SOURCE, PROVIDER
    return {"ok": True, "mode": llm.mode(), "model": MODEL, "provider": PROVIDER, "games": len(GAMES),
            "key_source": KEY_SOURCE,
            "budget": {"daily_usd": BUDGET.limit, "spent_today_usd": round(BUDGET.spent(), 6)},
            **({"last_error": llm.last_error} if os.getenv("DEBUG") else {})}


@app.get("/api/bank")
async def bank_info():
    b = load_bank()
    return {"title": b["title"], "clues": sum(len(c["clues"]) for c in b["categories"]),
            "categories": [{"name": c["name"], "clues": len(c["clues"])} for c in b["categories"]],
            "sources": sorted({q["source"] for c in b["categories"] for q in c["clues"] if q.get("source")})}


@app.post("/api/games")
async def create(body: NewGame, request: Request):
    _cleanup()
    ip = _ip(request)
    _rate(f"new:{ip}", NEW_GAMES_PER_HOUR)
    agents = Agents(llm, random.Random())
    board = None
    if body.topic and body.topic.strip():
        if not llm.live:
            raise HTTPException(503, "Custom topics need the live AI, which is off right now. Play the Yale board instead!")
        _rate(f"custom:{ip}", CUSTOM_BOARDS_PER_HOUR)
        from .llm import Meter
        m = Meter()
        board = await agents.write_board(m, body.topic, body.size)
        if not board:
            raise HTTPException(422, "The writer couldn't build a board for that topic. Try a different one.")
    g = new_game(agents, size=body.size, level=body.level, name=body.name, board=board)
    if board:
        g.meter = m
    GAMES[g.id] = g
    await g.start()
    return g.public()


@app.get("/api/games/{gid}")
async def state(gid: str):
    return _game(gid).public()


@app.post("/api/games/{gid}/pick")
async def pick(gid: str, body: Pick):
    return await _act(gid, lambda g, c: g.pick(c), body.cell_id)


@app.post("/api/games/{gid}/wager")
async def wager(gid: str, body: Wager):
    return await _act(gid, lambda g, a: g.wager(a), body.amount)


@app.post("/api/games/{gid}/buzz")
async def buzz(gid: str):
    return await _act(gid, lambda g: g.buzz())


@app.post("/api/games/{gid}/pass")
async def pass_(gid: str):
    return await _act(gid, lambda g: g.pass_())


@app.post("/api/games/{gid}/answer")
async def answer(gid: str, body: Answer):
    return await _act(gid, lambda g, t: g.answer(t), body.text)


@app.post("/api/games/{gid}/advance")
async def advance(gid: str):
    return await _act(gid, lambda g: g.advance())


# ------------------------------------------------------------------ frontend
app.mount("/static", StaticFiles(directory=WEB), name="static")


from . import classroom_api  # noqa: E402

classroom_api.llm_ref["llm"] = llm
app.include_router(classroom_api.router)

PAGES = {"/": "home.html", "/yale": "index.html", "/teach": "teach.html", "/host": "host.html",
         "/play": "play.html", "/join": "play.html", "/report": "report.html", "/evidence": "evidence.html"}


def _page(name: str):
    async def handler():
        return FileResponse(WEB / name, headers={"Cache-Control": "no-cache"})
    return handler


for _path, _file in PAGES.items():
    app.add_api_route(_path, _page(_file), methods=["GET"], include_in_schema=False)
