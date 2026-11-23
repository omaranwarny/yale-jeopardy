"""The game engine: every rule, score and turn lives here, in plain code.

Phases
  pick         a human has control and picks a clue
  bot_pick     an AI contestant has control              -> client calls advance()
  dd_wager     the human found a Daily Double and wagers
  clue         clue is open, anyone eligible may buzz    -> buzz() / pass_() / advance() on timers
  answer       the human is answering
  bot_answer   an AI contestant is answering             -> advance()
  reveal       result shown                              -> advance() moves on
  final_wager  Final Jeopardy wager (human)              -> wager()
  final_answer Final Jeopardy answer (human)             -> answer() / advance() on timeout
  over         game over
"""
from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass, field

from .agents import (HOST, PERSONAS, Agents, Persona, bot_final_wager, bot_pick, bot_wager, buzz_time,
                     host_line, knows)
from .bank import Board, Cell, build_board
from .judge import judge
from .llm import Meter

ANSWER_MS = 25_000
FINAL_ANSWER_MS = 40_000
BUZZ_WINDOW_MS = 6_500
SLACK_MS = 250                      # network allowance when a human and a bot buzz close together


@dataclass
class Player:
    id: str
    name: str
    color: str
    persona: Persona | None = None
    score: int = 0
    correct: int = 0
    wrong: int = 0

    @property
    def ai(self) -> bool:
        return self.persona is not None

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "color": self.color, "ai": self.ai, "score": self.score,
                "tagline": self.persona.tagline if self.persona else "you", "correct": self.correct,
                "wrong": self.wrong}


@dataclass
class Game:
    board: Board
    players: list[Player]
    agents: Agents
    level: str = "normal"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    rng: random.Random = field(default_factory=random.Random)
    clock: callable = time.monotonic
    meter: Meter = field(default_factory=Meter)
    phase: str = "pick"
    control: str = "you"
    cell: Cell | None = None
    open_at: float = 0.0
    window_ms: int = BUZZ_WINDOW_MS
    eligible: list[str] = field(default_factory=list)
    sure: dict = field(default_factory=dict)          # bot id -> knows this clue (decided once per clue)
    bot_buzz: dict = field(default_factory=dict)      # bot id -> ms after open
    answering: str | None = None
    answer_deadline: float = 0.0
    wager_amount: int = 0
    attempts: list = field(default_factory=list)
    last: dict | None = None
    events: list = field(default_factory=list)
    final: dict = field(default_factory=dict)
    created: float = field(default_factory=time.time)
    touched: float = field(default_factory=time.time)
    flags: int = 0
    read_ms: int = 0

    # ------------------------------------------------------------------ helpers
    def p(self, pid: str) -> Player:
        return next(pl for pl in self.players if pl.id == pid)

    @property
    def human(self) -> Player:
        return next(pl for pl in self.players if not pl.ai)

    def ms(self) -> int:
        return int((self.clock() - self.open_at) * 1000)

    def say(self, who: str, text: str, kind: str = "host") -> None:
        self.events.append({"i": len(self.events), "who": who, "kind": kind, "text": text})

    def _err(self, msg: str) -> dict:
        return {"ok": False, "error": msg}

    # ------------------------------------------------------------------ flow
    async def start(self) -> None:
        names = ", ".join(f"{p.name} ({p.persona.tagline})" for p in self.players if p.ai)
        line = await self.agents.host_say(self.meter, "opening",
                                          f"Board: {self.board.title}. Categories: {', '.join(self.board.categories)}."
                                          f" Contestants: you, {names}.",
                                          host_line("intro", self.rng))
        self.say(HOST["name"], line)
        self._to_pick()

    def _to_pick(self) -> None:
        if not self.board.remaining():
            return self._to_final()
        self.cell, self.answering, self.attempts, self.wager_amount = None, None, [], 0
        ctrl = self.p(self.control)
        self.phase = "bot_pick" if ctrl.ai else "pick"
        self.say(HOST["name"], host_line("pick", self.rng, name=ctrl.name))

    def _open_clue(self, cell: Cell, chooser: Player) -> None:
        self.cell, cell.used, self.attempts = cell, True, []
        self.say(chooser.name, f"{cell.category} for ${cell.value}.", "player")
        if cell.daily_double:
            self.say(HOST["name"], host_line("dd", self.rng))
            if chooser.ai:
                cap = max(chooser.score, max(self.board.values))
                self.wager_amount = bot_wager(chooser.persona, chooser.score, max(self.board.values), self.rng)
                self.wager_amount = min(self.wager_amount, cap)
                self.say(chooser.name, f"I'll wager ${self.wager_amount}.", "player")
                self.answering, self.phase = chooser.id, "bot_answer"
            else:
                self.phase = "dd_wager"
            return
        self.sure = {pl.id: knows(pl.persona, cell, self.level, self.rng) for pl in self.players if pl.ai}
        self.eligible = [pl.id for pl in self.players]
        self._open_buzz()

    def _open_buzz(self) -> None:
        self.phase, self.answering = "clue", None
        self.open_at = self.clock()
        read_ms = min(4500, 1200 + 28 * len(self.cell.clue))
        self.window_ms = read_ms + BUZZ_WINDOW_MS
        self.bot_buzz = {}
        for pid in self.eligible:
            pl = self.p(pid)
            if pl.ai:
                t = buzz_time(pl.persona, self.sure.get(pid, False), self.rng)
                if t is not None:
                    self.bot_buzz[pid] = t + read_ms
        self.read_ms = read_ms

    def _earliest_bot(self) -> tuple[str, int] | None:
        live = {k: v for k, v in self.bot_buzz.items() if k in self.eligible}
        return min(live.items(), key=lambda kv: kv[1]) if live else None

    # ------------------------------------------------------------------ human actions
    async def pick(self, cell_id: str) -> dict:
        if self.phase != "pick":
            return self._err("It's not your turn to pick.")
        cell = self.board.cell(cell_id)
        if not cell or cell.used:
            return self._err("That clue is gone.")
        self._open_clue(cell, self.human)
        return {"ok": True}

    async def wager(self, amount: int) -> dict:
        h = self.human
        if self.phase == "dd_wager":
            top = max(h.score, max(self.board.values))
            if not 5 <= amount <= top:
                return self._err(f"Wager between $5 and ${top}.")
            self.wager_amount = amount
            self.say(h.name, f"I'll wager ${amount}.", "player")
            self.answering, self.phase = h.id, "answer"
            self.answer_deadline = self.clock() + ANSWER_MS / 1000
            return {"ok": True}
        if self.phase == "final_wager":
            if not 0 <= amount <= max(h.score, 0):
                return self._err(f"Wager between $0 and ${max(h.score, 0)}.")
            self.final["wagers"][h.id] = amount
            self._final_open()
            return {"ok": True}
        return self._err("No wager is open.")

    async def buzz(self) -> dict:
        if self.phase != "clue" or "you" not in self.eligible:
            return self._err("You can't buzz now.")
        t = self.ms()
        if t < self.read_ms - SLACK_MS:
            return self._err("Wait for the buzzers to open!")
        first = self._earliest_bot()
        if first and first[1] + SLACK_MS < t:         # a bot really was faster
            await self._bot_buzzes(first[0])
            return {"ok": True, "beaten_by": self.p(first[0]).name}
        self.answering, self.phase = "you", "answer"
        self.answer_deadline = self.clock() + ANSWER_MS / 1000
        self.say(self.human.name, "Buzz!", "buzz")
        return {"ok": True}

    async def pass_(self) -> dict:
        if self.phase != "clue":
            return self._err("Nothing to pass.")
        if "you" in self.eligible:
            self.eligible.remove("you")
        first = self._earliest_bot()
        if first:
            await self._bot_buzzes(first[0])
        else:
            self._nobody()
        return {"ok": True}

    async def answer(self, text: str) -> dict:
        text = (text or "").strip()[:200]
        if self.phase == "answer" and self.answering == "you":
            await self._resolve("you", text)
            return {"ok": True}
        if self.phase == "final_answer" and "you" in self.final.get("players", []):
            self.final["answers"]["you"] = text
            return await self._final_resolve()
        return self._err("You can't answer now.")

    # ------------------------------------------------------------------ the clock + bots
    async def advance(self) -> dict:
        """Called by the client whenever it's waiting on a bot or a timer. Safe to call any time."""
        ph = self.phase
        if ph == "bot_pick":
            ctrl = self.p(self.control)
            self._open_clue(bot_pick(ctrl.persona, self.board, self.rng), ctrl)
        elif ph == "clue":
            first, t = self._earliest_bot(), self.ms()
            if first and t >= first[1]:
                await self._bot_buzzes(first[0])
            elif t >= self.window_ms:
                self._nobody()
        elif ph == "bot_answer":
            await self._bot_answers(self.answering)
        elif ph == "answer" and self.clock() >= self.answer_deadline:
            await self._resolve("you", "")
        elif ph == "reveal":
            self._to_pick()
        elif ph == "final_answer" and self.clock() >= self.final.get("deadline", 0):
            return await self._final_resolve()
        return {"ok": True}

    async def _bot_buzzes(self, pid: str) -> None:
        self.answering, self.phase = pid, "bot_answer"
        self.say(self.p(pid).name, "Buzz!", "buzz")

    async def _bot_answers(self, pid: str) -> None:
        pl = self.p(pid)
        pool = [c.answer for col in self.board.grid for c in col if c.category == self.cell.category]
        sure = self.sure.get(pid, True) if not self.cell.daily_double else knows(pl.persona, self.cell, self.level, self.rng)
        text = await self.agents.contestant_answer(self.meter, pl.persona, self.cell, sure, pool)
        await self._resolve(pid, text)

    # ------------------------------------------------------------------ rulings
    async def _rule(self, cell: Cell, text: str) -> dict:
        r = judge(text, cell.accept)
        correct, reason, method = r.correct, "", r.method
        if r.needs_ai:
            correct, reason = await self.agents.judge_gray(self.meter, cell, text)
            method = "ai_judge"
        return {"correct": correct, "method": method, "flags": r.flags, "reason": reason,
                "similarity": round(r.score, 2)}

    async def _resolve(self, pid: str, text: str) -> None:
        pl, cell = self.p(pid), self.cell
        ruling = await self._rule(cell, text)
        value = self.wager_amount if cell.daily_double else cell.value
        self.say(pl.name, text or "(no answer)", "answer")
        self.attempts.append({"player": pid, "answer": text, **ruling})
        if "injection_attempt" in ruling["flags"]:
            self.flags += 1
            self.say(HOST["name"], host_line("flag", self.rng, name=pl.name))
        if ruling["correct"]:
            pl.score += value
            pl.correct += 1
            self.control = pid
            self.say(HOST["name"], host_line("correct", self.rng, name=pl.name, value=value))
            return self._reveal(winner=pid)
        pl.score -= value
        pl.wrong += 1
        if "injection_attempt" not in ruling["flags"]:
            self.say(HOST["name"], host_line("wrong", self.rng, name=pl.name, value=value))
        if cell.daily_double:
            return self._reveal(winner=None)
        if pid in self.eligible:
            self.eligible.remove(pid)
        if self.eligible:
            self._open_buzz()          # rebound: the others may buzz in
        else:
            self._reveal(winner=None)

    def _nobody(self) -> None:
        self.say(HOST["name"], host_line("nobody", self.rng, answer=self.cell.answer))
        self._reveal(winner=None, announce=False)

    def _reveal(self, winner: str | None, announce: bool = True) -> None:
        c = self.cell
        self.phase, self.answering = "reveal", None
        self.last = {"cell": c.id, "category": c.category, "value": c.value, "daily_double": c.daily_double,
                     "clue": c.clue, "answer": c.answer, "source": c.source, "winner": winner,
                     "attempts": self.attempts}

    # ------------------------------------------------------------------ final jeopardy
    def _to_final(self) -> None:
        finalists = [pl.id for pl in self.players if pl.score > 0]
        self.cell = self.board.final
        self.final = {"players": finalists, "wagers": {}, "answers": {}, "results": {}}
        self.say(HOST["name"], host_line("final", self.rng) + f" The category: {self.board.final.category}.")
        for pid in finalists:
            pl = self.p(pid)
            if pl.ai:
                others = [o.score for o in self.players if o.id != pid]
                self.final["wagers"][pid] = bot_final_wager(pl.persona, pl.score, others)
        if "you" in finalists:
            self.phase = "final_wager"
        elif finalists:
            self._final_open()
        else:
            self.phase = "over"
            self.say(HOST["name"], "Nobody finished in the black, so there's no Final Jeopardy. Better luck next time!")

    def _final_open(self) -> None:
        self.phase = "final_answer"
        self.final["deadline"] = self.clock() + FINAL_ANSWER_MS / 1000
        if "you" not in self.final["players"]:
            self.final["deadline"] = self.clock()

    async def _final_resolve(self) -> dict:
        if self.phase != "final_answer":
            return self._err("Final Jeopardy isn't open.")
        self.phase = "final_judging"
        pool = [c.answer for col in self.board.grid for c in col]
        for pid in self.final["players"]:
            pl = self.p(pid)
            if pl.ai:
                sure = knows(pl.persona, self.cell, self.level, self.rng)
                self.final["answers"][pid] = await self.agents.contestant_answer(self.meter, pl.persona, self.cell,
                                                                                 sure, pool)
            text = self.final["answers"].get(pid, "")
            ruling = await self._rule(self.cell, text)
            w = self.final["wagers"].get(pid, 0)
            pl.score += w if ruling["correct"] else -w
            self.final["results"][pid] = {"answer": text, "wager": w, **ruling}
            if "injection_attempt" in ruling["flags"]:
                self.flags += 1
        self.phase = "over"
        standings = sorted(self.players, key=lambda x: -x.score)
        recap = "; ".join(f"{p.name} ${p.score}" for p in standings)
        self.last = {"cell": "final", "category": self.cell.category, "clue": self.cell.clue,
                     "answer": self.cell.answer, "source": self.cell.source, "final": self.final["results"]}
        self.say(HOST["name"], await self.agents.host_say(
            self.meter, "game over", f"The answer was {self.cell.answer}. Final scores: {recap}.",
            f"The answer: {self.cell.answer}. "
            + (f"You win with ${standings[0].score}!" if not standings[0].ai
               else f"{standings[0].name} wins with ${standings[0].score}!")))
        return {"ok": True}

    # ------------------------------------------------------------------ what the browser sees
    def public(self) -> dict:
        self.touched = time.time()
        d = {"id": self.id, "phase": self.phase, "control": self.control, "level": self.level,
             "players": [p.public() for p in self.players], "board": self.board.public(),
             "events": self.events[-40:], "meter": self.meter.public(), "mode": self.agents.llm.mode(),
             "host": HOST, "answering": self.answering, "last": self.last, "flags": self.flags}
        c = self.cell
        if c and self.phase in ("clue", "answer", "bot_answer", "dd_wager", "final_wager", "final_answer",
                                "final_judging"):
            d["clue"] = {"category": c.category, "value": c.value, "daily_double": c.daily_double,
                         "text": c.clue if self.phase != "dd_wager" and self.phase != "final_wager" else None,
                         "wager": self.wager_amount, "rebound": bool(self.attempts) and self.phase == "clue"}
        if self.phase == "clue":
            first = self._earliest_bot()
            d["timer"] = {"elapsed_ms": self.ms(), "window_ms": self.window_ms, "read_ms": self.read_ms,
                          "next_bot_ms": first[1] if first else None, "you_can_buzz": "you" in self.eligible}
        if self.phase == "answer":
            d["timer"] = {"answer_ms_left": int((self.answer_deadline - self.clock()) * 1000)}
        if self.phase.startswith("final") or self.phase == "over":
            d["final"] = {"category": self.board.final.category, "players": self.final.get("players", []),
                          "results": self.final.get("results") if self.phase == "over" else None,
                          "ms_left": int((self.final.get("deadline", 0) - self.clock()) * 1000)
                          if self.phase == "final_answer" else None,
                          "max_wager": max(self.human.score, 0)}
        if self.phase == "dd_wager":
            d["max_wager"] = max(self.human.score, max(self.board.values))
        return d


def new_game(agents: Agents, size: str = "quick", level: str = "normal", name: str = "You",
             seed: int | None = None, board: Board | None = None, clock=time.monotonic) -> Game:
    rng = random.Random(seed)
    you = Player("you", (name or "You").strip()[:16] or "You", "#c99a2e")
    bots = [Player(p.id, p.name, p.color, persona=p) for p in PERSONAS]
    g = Game(board=board or build_board(size, seed=seed), players=[you] + bots, agents=agents,
             level=level if level in ("easy", "normal", "hard") else "normal", rng=rng, clock=clock)
    return g
