"""SQLite storage for classroom boards, sessions and feedback (the evidence for the trial)."""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("CLASSROOM_DB", str(ROOT / "data" / "classroom.db")))
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS boards (id TEXT PRIMARY KEY, teacher_token TEXT, title TEXT, status TEXT,
  created REAL, updated REAL, data TEXT, build TEXT);
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, board_id TEXT, code TEXT, created REAL, ended REAL, data TEXT);
CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, board_id TEXT,
  role TEXT, created REAL, data TEXT);
"""


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def new_id(n: int = 8) -> str:
    return secrets.token_urlsafe(n)[:n].replace("-", "x").replace("_", "y")


# ---------------------------------------------------------------- boards
def save_board(board: dict, build: dict, board_id: str | None = None, token: str | None = None,
               status: str = "draft") -> tuple[str, str]:
    board_id, token = board_id or new_id(), token or secrets.token_urlsafe(16)
    now = time.time()
    with _lock, _db() as con:
        con.execute("INSERT INTO boards VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                    "title=excluded.title, status=excluded.status, updated=excluded.updated, data=excluded.data, "
                    "build=excluded.build",
                    (board_id, token, board.get("title", "Review game"), status, now, now,
                     json.dumps(board), json.dumps(build)))
    return board_id, token


def get_board(board_id: str) -> dict | None:
    with _db() as con:
        r = con.execute("SELECT * FROM boards WHERE id=?", (board_id,)).fetchone()
    if not r:
        return None
    return {"id": r["id"], "token": r["teacher_token"], "title": r["title"], "status": r["status"],
            "created": r["created"], "updated": r["updated"], "board": json.loads(r["data"]),
            "build": json.loads(r["build"] or "{}")}


def all_boards() -> list[dict]:
    with _db() as con:
        rows = con.execute("SELECT id, title, status, created, updated, build FROM boards ORDER BY created DESC").fetchall()
    return [{"id": r["id"], "title": r["title"], "status": r["status"], "created": r["created"],
             "updated": r["updated"], "build": json.loads(r["build"] or "{}")} for r in rows]


# ---------------------------------------------------------------- sessions + feedback
def save_session(session_id: str, board_id: str, code: str, created: float, ended: float | None, data: dict) -> None:
    with _lock, _db() as con:
        con.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ended=excluded.ended, "
                    "data=excluded.data", (session_id, board_id, code, created, ended, json.dumps(data)))


def all_sessions() -> list[dict]:
    with _db() as con:
        rows = con.execute("SELECT * FROM sessions ORDER BY created DESC").fetchall()
    return [{"id": r["id"], "board_id": r["board_id"], "code": r["code"], "created": r["created"],
             "ended": r["ended"], **json.loads(r["data"] or "{}")} for r in rows]


def get_session(session_id: str) -> dict | None:
    return next((s for s in all_sessions() if s["id"] == session_id), None)


def add_feedback(session_id: str, board_id: str, role: str, data: dict) -> None:
    with _lock, _db() as con:
        con.execute("INSERT INTO feedback (session_id, board_id, role, created, data) VALUES (?,?,?,?,?)",
                    (session_id, board_id, role, time.time(), json.dumps(data)))


def all_feedback() -> list[dict]:
    with _db() as con:
        rows = con.execute("SELECT * FROM feedback ORDER BY created").fetchall()
    return [{"session_id": r["session_id"], "board_id": r["board_id"], "role": r["role"], "created": r["created"],
             **json.loads(r["data"] or "{}")} for r in rows]
