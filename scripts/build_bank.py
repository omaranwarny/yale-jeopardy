"""Build data/clues.json from data/clues_source.txt and check every clue.

    python scripts/build_bank.py

Checks: 5 fields per line, difficulty 1-5, a source URL, the answer is not given away in the clue,
no duplicate clues, and every regular category has at least one clue at each difficulty.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "clues_source.txt"
OUT = ROOT / "data" / "clues.json"


def norm(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s.lower()).split())


def build() -> dict:
    cats: dict[str, list] = defaultdict(list)
    errors, cat = [], None
    for n, raw in enumerate(SRC.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("# "):
            continue
        if line.startswith("## "):
            cat = line[3:].strip()
            continue
        parts = [p.strip() for p in line.split(" | ")]
        if len(parts) != 5:
            errors.append(f"line {n}: expected 5 fields, got {len(parts)}")
            continue
        diff, clue, answer, alts, source = parts
        if diff not in "12345" or len(diff) != 1:
            errors.append(f"line {n}: difficulty must be 1-5")
        if not source.startswith("http"):
            errors.append(f"line {n}: missing source URL")
        a = norm(answer)
        if len(a) > 3 and re.search(rf"\b{re.escape(a)}\b", norm(clue)):
            errors.append(f"line {n}: clue gives away the answer '{answer}'")
        accept = [answer] + [x.strip() for x in alts.split(";") if x.strip() and x.strip() != "—"]
        cats[cat].append({
            "id": f"{norm(cat).replace(' ', '-')[:12]}-{len(cats[cat]) + 1:02d}",
            "category": cat, "difficulty": int(diff), "clue": clue, "answer": answer,
            "accept": accept, "source": source,
        })
    seen = set()
    for c in cats.values():
        for q in c:
            if norm(q["clue"]) in seen:
                errors.append(f"duplicate clue: {q['clue'][:50]}")
            seen.add(norm(q["clue"]))
    for name, c in cats.items():
        if name.startswith("FINAL"):
            continue
        missing = {1, 2, 3, 4, 5} - {q["difficulty"] for q in c}
        if missing:
            errors.append(f"category '{name}' has no clue at difficulty {sorted(missing)}")
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    final = []
    for name in [k for k in cats if k.startswith("FINAL")]:
        for q in cats.pop(name):
            q["category"] = name.split(":", 1)[1].strip() if ":" in name else "Final Jeopardy"
            final.append(q)
    return {"title": "Yale University", "categories": [{"name": k, "clues": v} for k, v in cats.items()],
            "final": final}


if __name__ == "__main__":
    bank = build()
    OUT.write_text(json.dumps(bank, indent=1, ensure_ascii=False), encoding="utf-8")
    n = sum(len(c["clues"]) for c in bank["categories"])
    print(f"wrote {OUT.relative_to(ROOT)}: {len(bank['categories'])} categories, {n} clues, "
          f"{len(bank['final'])} final clues")
