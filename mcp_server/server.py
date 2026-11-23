"""MCP server for the Yale clue bank (FastMCP), so any MCP client (Claude Desktop, Claude Code, ...)
can browse the verified Yale facts or quiz you, with answers checked by the same code judge as the game.

    python mcp_server/server.py            # stdio
Add to an MCP client config:  {"command": "python", "args": ["mcp_server/server.py"]}
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastmcp import FastMCP  # noqa: E402

from app.bank import load_bank  # noqa: E402
from app.judge import judge  # noqa: E402

mcp = FastMCP("yale-jeopardy")
BANK = load_bank()
CLUES = {q["id"]: q for c in BANK["categories"] for q in c["clues"]}


@mcp.tool
def list_categories() -> list[dict]:
    """The Yale Jeopardy categories and how many verified clues each has."""
    return [{"name": c["name"], "clues": len(c["clues"])} for c in BANK["categories"]]


@mcp.tool
def get_clues(category: str, difficulty: int | None = None, reveal_answers: bool = False) -> list[dict]:
    """Clues in a category (optionally one difficulty 1-5). Answers are hidden unless reveal_answers=True."""
    cat = next((c for c in BANK["categories"] if c["name"].lower() == category.lower()), None)
    if not cat:
        return [{"error": f"No category '{category}'. Call list_categories."}]
    out = []
    for q in cat["clues"]:
        if difficulty and q["difficulty"] != difficulty:
            continue
        d = {"id": q["id"], "difficulty": q["difficulty"], "value": q["difficulty"] * 200, "clue": q["clue"]}
        if reveal_answers:
            d |= {"answer": q["answer"], "source": q["source"]}
        out.append(d)
    return out


@mcp.tool
def random_clue(category: str | None = None) -> dict:
    """One random clue (answer hidden) to quiz someone with. Check the reply with check_answer."""
    pool = [q for q in CLUES.values() if not category or q["category"].lower() == category.lower()]
    if not pool:
        return {"error": "No clues match."}
    q = random.choice(pool)
    return {"id": q["id"], "category": q["category"], "value": q["difficulty"] * 200, "clue": q["clue"]}


@mcp.tool
def check_answer(clue_id: str, answer: str) -> dict:
    """Judge an answer in code (same rules as the game) and reveal the correct answer with its source."""
    q = CLUES.get(clue_id)
    if not q:
        return {"error": f"Unknown clue id '{clue_id}'."}
    r = judge(answer, q["accept"])
    return {"correct": r.correct, "close_call": r.needs_ai, "flags": r.flags, "answer": q["answer"],
            "source": q["source"]}


if __name__ == "__main__":
    mcp.run()
