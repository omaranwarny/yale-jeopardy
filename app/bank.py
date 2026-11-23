"""Clue bank + board building. Boards come from the verified Yale bank or from an AI-written custom topic."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK_FILE = ROOT / "data" / "clues.json"

SIZES = {
    # name: (categories, values, difficulty per row, daily doubles)
    "full": (6, [200, 400, 600, 800, 1000], [1, 2, 3, 4, 5], 2),
    "quick": (4, [200, 600, 1000], [1, 3, 4], 1),
}


@dataclass
class Cell:
    id: str
    category: str
    value: int
    difficulty: int
    clue: str
    answer: str
    accept: list[str]
    source: str | None = None
    daily_double: bool = False
    used: bool = False

    def public(self, reveal: bool = False) -> dict:
        d = {"id": self.id, "value": self.value, "used": self.used}
        if reveal:
            d |= {"clue": self.clue, "answer": self.answer, "source": self.source}
        return d


@dataclass
class Board:
    title: str
    categories: list[str]
    grid: list[list[Cell]]            # grid[category][row]
    final: Cell
    verified: bool = True             # False for AI-written custom boards
    values: list[int] = field(default_factory=list)

    def cell(self, cell_id: str) -> Cell | None:
        return next((c for col in self.grid for c in col if c.id == cell_id), None)

    def remaining(self) -> list[Cell]:
        return [c for col in self.grid for c in col if not c.used]

    def public(self) -> dict:
        return {"title": self.title, "verified": self.verified, "values": self.values,
                "categories": [{"name": n, "cells": [c.public() for c in col]}
                               for n, col in zip(self.categories, self.grid)]}


def load_bank() -> dict:
    return json.loads(BANK_FILE.read_text(encoding="utf-8"))


def _pick(clues: list[dict], difficulty: int, used: set, rng: random.Random) -> dict:
    """A clue at this difficulty, else the nearest difficulty, never reusing one."""
    for d in sorted({1, 2, 3, 4, 5}, key=lambda x: (abs(x - difficulty), -x)):
        options = [c for c in clues if c["difficulty"] == d and c["id"] not in used]
        if options:
            return rng.choice(options)
    raise ValueError("category ran out of clues")


def build_board(size: str = "full", seed: int | None = None, bank: dict | None = None,
                verified: bool = True) -> Board:
    rng = random.Random(seed)
    bank = bank or load_bank()
    n_cats, values, diffs, n_dd = SIZES[size]
    cats = rng.sample(bank["categories"], min(n_cats, len(bank["categories"])))
    grid, used = [], set()
    for cat in cats:
        col = []
        for row, (value, diff) in enumerate(zip(values, diffs)):
            c = _pick(cat["clues"], diff, used, rng)
            used.add(c["id"])
            col.append(Cell(id=f"c{len(grid)}r{row}", category=cat["name"], value=value,
                            difficulty=c["difficulty"], clue=c["clue"], answer=c["answer"],
                            accept=c["accept"], source=c.get("source")))
        grid.append(col)
    # Daily Doubles hide in the lower rows, never in the top (easiest) row
    lower = [c for col in grid for c in col[1:]]
    for c in rng.sample(lower, min(n_dd, len(lower))):
        c.daily_double = True
    f = rng.choice(bank["final"]) if bank.get("final") else _pick(rng.choice(bank["categories"])["clues"], 3, used, rng)
    fcat = f.get("category") if f.get("category") not in (None, "FINAL") else "Final Jeopardy"
    final = Cell(id="final", category=fcat, value=0, difficulty=f["difficulty"],
                 clue=f["clue"], answer=f["answer"], accept=f["accept"], source=f.get("source"))
    return Board(title=bank.get("title", "Yale"), categories=[c["name"] for c in cats], grid=grid,
                 final=final, verified=verified, values=values)
