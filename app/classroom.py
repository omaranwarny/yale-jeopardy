"""Classroom rooms: the teacher projects the board, students join on their phones with a room code.

Modes
  all   "Everyone answers": every student types an answer to every clue (best review data)
  buzz  Classic buzzer: first to buzz answers; if wrong, the others may buzz in
Rules are code. AI seat-fillers (optional) play with offline persona logic, so they cost nothing.
The teacher is the final authority: any ruling can be overridden at the reveal.
Phones and the projector poll /state; every request runs tick() so timers advance server-side.
"""
from __future__ import annotations

import random
import secrets
import string
import time
from dataclasses import dataclass, field

from . import store
from .agents import PERSONAS, Persona, buzz_time
from .bank import Cell
from .judge import judge
from .llm import LLM, Meter

READ_MS_MIN, READ_MS_MAX = 2500, 7000
ALL_WINDOW_MS = 30_000
BUZZ_WINDOW_MS = 9_000
ANSWER_MS = 20_000
FINAL_MS = 45_000
MAX_PLAYERS = 120
AI_JUDGE_PER_CLUE = 8
CODE_ALPHABET = "".join(c for c in string.ascii_uppercase if c not in "IOQ")


@dataclass
class Seat:
    id: str
    name: str
    token: str
    persona: Persona | None = None
    score: int = 0
    correct: int = 0
    answered: int = 0
    joined: float = field(default_factory=time.time)
    seen: float = field(default_factory=time.time)

    @property
    def ai(self) -> bool:
        return self.persona is not None

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "ai": self.ai, "score": self.score, "correct": self.correct,
                "answered": self.answered, "color": self.persona.color if self.persona else None}


@dataclass
class Room:
    board_id: str
    board: dict
    teacher_token: str
    llm: LLM
    mode: str = "all"
    ai_seats: int = 0
    code: str = field(default_factory=lambda: "".join(secrets.choice(CODE_ALPHABET) for _ in range(5)))
    session_id: str = field(default_factory=lambda: store.new_id(10))
    clock: callable = time.time
    rng: random.Random = field(default_factory=random.Random)
    seats: dict = field(default_factory=dict)
    phase: str = "lobby"
    cur: tuple | None = None
    used: set = field(default_factory=set)
    open_at: float = 0.0
    read_ms: int = 0
    window_ms: int = 0
    answers: dict = field(default_factory=dict)         # pid -> {text, at_ms, correct, method, flags, overridden}
    ai_plan: dict = field(default_factory=dict)         # pid -> (at_ms, text)  for this clue
    excluded: set = field(default_factory=set)          # buzz mode: already tried
    answering: str | None = None
    answer_deadline: float = 0.0
    ai_judge_calls: int = 0
    history: list = field(default_factory=list)         # one analytics record per clue played
    meter: Meter = field(default_factory=Meter)
    created: float = field(default_factory=time.time)
    ended: float | None = None
    touched: float = field(default_factory=time.time)

    # ------------------------------------------------------------ setup
    def __post_init__(self):
        for p in PERSONAS[: max(0, min(3, self.ai_seats))]:
            self.seats[p.id] = Seat(p.id, p.name, "", persona=p)

    def now_ms(self) -> int:
        return int((self.clock() - self.open_at) * 1000)

    def humans(self) -> list[Seat]:
        return [s for s in self.seats.values() if not s.ai]

    def join(self, name: str) -> dict:
        if self.phase == "over":
            return {"ok": False, "error": "This game has ended."}
        if len(self.humans()) >= MAX_PLAYERS:
            return {"ok": False, "error": "This room is full."}
        name = " ".join((name or "").split())[:18] or f"Player {len(self.seats) + 1}"
        taken = {s.name.lower() for s in self.seats.values()}
        base, n = name, 2
        while name.lower() in taken:
            name, n = f"{base} {n}", n + 1
        seat = Seat(store.new_id(8), name, secrets.token_urlsafe(12))
        self.seats[seat.id] = seat
        return {"ok": True, "player_id": seat.id, "player_token": seat.token, "name": seat.name}

    def cell(self, c: int, r: int) -> dict:
        return self.board["categories"][c]["clues"][r]

    def remaining(self) -> list[tuple]:
        return [(c, r) for c, cat in enumerate(self.board["categories"]) for r in range(len(cat["clues"]))
                if (c, r) not in self.used]

    # ------------------------------------------------------------ teacher actions
    async def teacher(self, action: str, data: dict) -> dict:
        if action == "start" and self.phase == "lobby":
            self.phase = "board"
        elif action == "pick" and self.phase == "board":
            c, r = int(data.get("c", -1)), int(data.get("r", -1))
            if (c, r) in self.used or not (0 <= c < len(self.board["categories"])) or not (
                    0 <= r < len(self.board["categories"][c]["clues"])):
                return {"ok": False, "error": "That clue isn't available."}
            self._open((c, r))
        elif action == "close" and self.phase in ("clue", "answering"):
            await self._close()
        elif action == "override" and self.phase in ("reveal", "final_reveal"):
            return self._override(str(data.get("player_id")), bool(data.get("correct")))
        elif action == "next" and self.phase == "reveal":
            self.phase = "board" if self.remaining() else "final_ready"
            self.cur = None
        elif action == "final" and self.phase in ("board", "final_ready") and self.board.get("final"):
            self._open("final")
        elif action == "end" and self.phase in ("board", "final_ready", "final_reveal", "reveal", "lobby"):
            self._finish()
        else:
            return {"ok": False, "error": f"Can't {action} right now."}
        return {"ok": True}

    def _clue(self) -> dict:
        return self.board["final"] if self.cur == "final" else self.cell(*self.cur)

    def _open(self, cur) -> None:
        self.cur, self.answers, self.excluded, self.answering, self.ai_judge_calls = cur, {}, set(), None, 0
        if cur != "final":
            self.used.add(cur)
        q = self._clue()
        self.read_ms = max(READ_MS_MIN, min(READ_MS_MAX, 1500 + 30 * len(q["clue"])))
        final = cur == "final"
        self.window_ms = self.read_ms + (FINAL_MS if final else ALL_WINDOW_MS if self.mode == "all" else BUZZ_WINDOW_MS)
        self.open_at = self.clock()
        self.phase = "clue"
        self._plan_ai(q, everyone=final or self.mode == "all")

    def _plan_ai(self, q: dict, everyone: bool) -> None:
        self.ai_plan = {}
        pool = [x["answer"] for cat in self.board["categories"] for x in cat["clues"] if x["answer"] != q["answer"]]
        for s in self.seats.values():
            if not s.ai or s.id in self.excluded:
                continue
            chance = s.persona.skill + 0.12 - (int(q.get("difficulty", 3)) - 3) * 0.12
            sure = self.rng.random() < max(0.1, min(0.9, chance))
            text = q["answer"] if sure else (self.rng.choice(pool) if pool else "I don't know")
            if everyone:
                self.ai_plan[s.id] = (self.read_ms + int(self.rng.uniform(3000, 18000)), text)
            else:
                t = buzz_time(s.persona, sure, self.rng)
                if t is not None:
                    self.ai_plan[s.id] = (self.read_ms + t, text)

    # ------------------------------------------------------------ player actions
    async def player(self, seat: Seat, action: str, data: dict) -> dict:
        seat.seen = time.time()
        await self.tick()
        everyone = self.cur == "final" or self.mode == "all"
        if action == "answer":
            text = str(data.get("text", ""))[:120]
            if self.phase == "clue" and everyone:
                if self.now_ms() < self.read_ms - 300:
                    return {"ok": False, "error": "Read the clue first!"}
                if seat.id in self.answers:
                    return {"ok": False, "error": "You already answered."}
                await self._record(seat.id, text)
                if all(h.id in self.answers for h in self.humans()):
                    for pid, (_, ai_text) in self.ai_plan.items():     # AIs lock in now so nobody waits
                        if pid not in self.answers:
                            await self._record(pid, ai_text)
                    await self._close()
                return {"ok": True}
            if self.phase == "answering" and self.answering == seat.id:
                await self._record(seat.id, text)
                await self._after_buzz_answer(seat.id)
                return {"ok": True}
            return {"ok": False, "error": "You can't answer right now."}
        if action == "buzz":
            if self.phase != "clue" or everyone or seat.id in self.excluded:
                return {"ok": False, "error": "You can't buzz right now."}
            if self.now_ms() < self.read_ms - 300:
                return {"ok": False, "error": "Too early! Wait for the buzzers."}
            self._give_floor(seat.id)
            return {"ok": True}
        return {"ok": False, "error": "Unknown action."}

    def _give_floor(self, pid: str) -> None:
        self.answering, self.phase = pid, "answering"
        self.answer_deadline = self.clock() + ANSWER_MS / 1000

    async def _record(self, pid: str, text: str) -> None:
        q = self._clue()
        r = judge(text, q["accept"])
        correct, method, reason = r.correct, r.method, ""
        if r.needs_ai and self.llm.live and self.ai_judge_calls < AI_JUDGE_PER_CLUE:
            self.ai_judge_calls += 1
            from .agents import Agents
            cell = Cell(id="x", category=q.get("category", ""), value=0, difficulty=3, clue=q["clue"],
                        answer=q["answer"], accept=q["accept"])
            correct, reason = await Agents(self.llm).judge_gray(self.meter, cell, text)
            method = "ai_judge"
        self.answers[pid] = {"text": text, "at_ms": self.now_ms(), "correct": correct, "method": method,
                             "flags": r.flags, "close": r.needs_ai, "reason": reason, "overridden": False}
        seat = self.seats[pid]
        seat.answered += 1
        value = self._value()
        if correct:
            seat.score += value
            seat.correct += 1

    def _value(self) -> int:
        if self.cur == "final":
            return 2 * max((x["value"] for c in self.board["categories"] for x in c["clues"]), default=1000)
        return int(self._clue().get("value", 200))

    async def _after_buzz_answer(self, pid: str) -> None:
        self.excluded.add(pid)
        self.answering = None
        if self.answers[pid]["correct"]:
            return await self._close()
        # wrong: reopen the buzzers for everyone else, for the rest of the window
        self.phase = "clue"
        self.window_ms = max(self.window_ms, self.now_ms() + 6000)
        q = self._clue()
        self._plan_ai(q, everyone=False)
        for k in list(self.ai_plan):
            at, text = self.ai_plan[k]
            self.ai_plan[k] = (max(at, self.now_ms() + 800), text)

    # ------------------------------------------------------------ the clock
    async def tick(self) -> None:
        self.touched = time.time()
        if self.phase == "clue":
            t = self.now_ms()
            everyone = self.cur == "final" or self.mode == "all"
            due = sorted((at, pid, text) for pid, (at, text) in self.ai_plan.items()
                         if at <= t and pid not in self.answers and pid not in self.excluded)
            for at, pid, text in due:
                if everyone:
                    await self._record(pid, text)
                elif self.phase == "clue":       # first AI to buzz takes the floor and answers at once
                    self._give_floor(pid)
                    await self._record(pid, text)
                    await self._after_buzz_answer(pid)
                    if self.phase != "clue":
                        return
            if self.phase == "clue" and self.now_ms() >= self.window_ms:
                await self._close()
        elif self.phase == "answering" and self.clock() >= self.answer_deadline:
            await self._record(self.answering, "")
            await self._after_buzz_answer(self.answering)

    async def _close(self) -> None:
        q = self._clue()
        humans = self.humans()
        answered = [h for h in humans if h.id in self.answers]
        n_correct = sum(1 for h in answered if self.answers[h.id]["correct"])
        everyone = self.cur == "final" or self.mode == "all"
        denom = len(humans) if everyone else len(answered)
        rec = {"key": "final" if self.cur == "final" else f"{self.cur[0]}-{self.cur[1]}",
               "category": q.get("category") or (self.board["categories"][self.cur[0]]["name"] if self.cur != "final" else "Final"),
               "clue": q["clue"], "answer": q["answer"], "value": self._value(), "source": q.get("source"),
               "quote": q.get("quote"), "mode": "all" if everyone else "buzz", "humans": len(humans),
               "answered": len(answered), "correct": n_correct,
               "pct_correct": round(100 * n_correct / denom) if denom else None,
               "answers": [{"player_id": pid, "name": self.seats[pid].name, "ai": self.seats[pid].ai, **a}
                           for pid, a in self.answers.items()],
               "played_at": time.time()}
        self.history = [h for h in self.history if h["key"] != rec["key"]] + [rec]
        self.phase = "final_reveal" if self.cur == "final" else "reveal"
        self.answering = None
        self._save()

    def _override(self, pid: str, correct: bool) -> dict:
        a = self.answers.get(pid)
        if not a or a["correct"] == correct:
            return {"ok": False, "error": "Nothing to change."}
        seat, value = self.seats[pid], self._value()
        seat.score += value if correct else -value
        seat.correct += 1 if correct else -1
        a["correct"], a["overridden"] = correct, True
        for rec in self.history:
            if rec["key"] == ("final" if self.cur == "final" else f"{self.cur[0]}-{self.cur[1]}"):
                for x in rec["answers"]:
                    if x["player_id"] == pid:
                        x["correct"], x["overridden"] = correct, True
                hs = [x for x in rec["answers"] if not x["ai"]]
                rec["correct"] = sum(1 for x in hs if x["correct"])
                denom = rec["humans"] if rec["mode"] == "all" else len(hs)
                rec["pct_correct"] = round(100 * rec["correct"] / denom) if denom else None
        self._save()
        return {"ok": True}

    def _finish(self) -> None:
        self.phase, self.ended = "over", time.time()
        self._save()

    # ------------------------------------------------------------ evidence
    def summary(self) -> dict:
        played = [h for h in self.history if h["pct_correct"] is not None]
        humans = self.humans()
        reteach = sorted(played, key=lambda h: h["pct_correct"])[:5]
        return {"session_id": self.session_id, "board_id": self.board_id, "title": self.board.get("title"),
                "mode": self.mode, "ai_seats": self.ai_seats, "students": len(humans),
                "clues_played": len(self.history),
                "avg_pct_correct": round(sum(h["pct_correct"] for h in played) / len(played)) if played else None,
                "overrides": sum(1 for h in self.history for a in h["answers"] if a.get("overridden")),
                "injection_attempts_blocked": sum(1 for h in self.history for a in h["answers"]
                                                  if "injection_attempt" in a.get("flags", [])),
                "minutes": round(((self.ended or time.time()) - self.created) / 60, 1),
                "reteach": [{k: h[k] for k in ("category", "clue", "answer", "pct_correct", "source", "quote")}
                            for h in reteach if h["pct_correct"] < 80],
                "students_detail": sorted([{"name": s.name, "score": s.score, "correct": s.correct,
                                            "answered": s.answered} for s in humans], key=lambda x: -x["score"]),
                "history": self.history, "llm": self.meter.public()}

    def _save(self) -> None:
        try:
            store.save_session(self.session_id, self.board_id, self.code, self.created, self.ended, self.summary())
        except Exception:
            pass

    # ------------------------------------------------------------ views
    def _clue_view(self, host: bool) -> dict | None:
        if self.cur is None or self.phase in ("board", "lobby", "final_ready", "over"):
            return None
        q = self._clue()
        revealed = self.phase in ("reveal", "final_reveal")
        cat = q.get("category") if self.cur == "final" else self.board["categories"][self.cur[0]]["name"]
        v = {"category": cat, "value": self._value(), "final": self.cur == "final", "text": q["clue"]}
        if revealed:
            v |= {"answer": q["answer"], "source": q.get("source"), "quote": q.get("quote")}
        return v

    def public(self, host: bool = False, seat: Seat | None = None) -> dict:
        everyone = self.cur == "final" or self.mode == "all"
        d = {"code": self.code, "session_id": self.session_id, "phase": self.phase, "mode": self.mode,
             "title": self.board.get("title"),
             "clue": self._clue_view(host), "answering": self.seats[self.answering].name if self.answering else None,
             "timer": {"elapsed_ms": self.now_ms(), "read_ms": self.read_ms, "window_ms": self.window_ms,
                       "answer_ms_left": int((self.answer_deadline - self.clock()) * 1000) if self.phase == "answering" else None}
             if self.phase in ("clue", "answering") else None,
             "everyone_answers": everyone,
             "leaders": sorted([s.public() for s in self.seats.values()], key=lambda x: -x["score"])[:8],
             "players": len(self.humans())}
        if host:
            d["board"] = {"title": self.board.get("title"), "values": self.board.get("values"),
                          "categories": [{"name": c["name"], "cells": [{"value": x.get("value"), "used": (ci, ri) in self.used}
                                                                       for ri, x in enumerate(c["clues"])]}
                                         for ci, c in enumerate(self.board["categories"])],
                          "has_final": bool(self.board.get("final"))}
            d["roster"] = [s.public() for s in self.seats.values()]
            d["submitted"] = len([p for p in self.answers if not self.seats[p].ai])
            if self.phase in ("reveal", "final_reveal"):
                d["results"] = [{"player_id": pid, "name": self.seats[pid].name, "ai": self.seats[pid].ai, **a}
                                for pid, a in sorted(self.answers.items(), key=lambda kv: kv[1]["at_ms"])]
                d["pct_correct"] = self.history[-1]["pct_correct"] if self.history else None
            if self.phase == "over":
                d["summary"] = self.summary()
        if seat:
            mine = self.answers.get(seat.id)
            ranked = sorted(self.seats.values(), key=lambda s: -s.score)
            d["me"] = {"id": seat.id, "name": seat.name, "score": seat.score,
                       "rank": [s.id for s in ranked].index(seat.id) + 1, "of": len(ranked),
                       "answered": bool(mine), "can_buzz": self.phase == "clue" and not everyone and seat.id not in self.excluded,
                       "can_answer": (self.phase == "clue" and everyone and not mine) or
                                     (self.phase == "answering" and self.answering == seat.id),
                       "result": ({"correct": mine["correct"], "text": mine["text"],
                                   "blocked": "injection_attempt" in mine.get("flags", [])} if mine and
                                  self.phase in ("reveal", "final_reveal", "over") else None)}
        return d


ROOMS: dict[str, Room] = {}


def find_room(code: str) -> Room | None:
    return ROOMS.get((code or "").strip().upper())


def cleanup(max_age_s: int = 8 * 3600) -> None:
    now = time.time()
    for code in [c for c, r in ROOMS.items() if now - r.touched > max_age_s]:
        ROOMS.pop(code, None)
