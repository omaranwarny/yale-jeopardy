"""Answer judging. CODE makes the ruling; the AI judge is only consulted in a narrow gray zone.

Same idea as the HW6 vendor desk: a player's answer is untrusted text. It can never change the rules,
the score, or the correct answer. It is matched against the accepted answers in code.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

MAX_ANSWER_CHARS = 80

QUESTION_FORM = re.compile(r"^\s*(?:what|who|where|when|which)\s+(?:is|are|was|were)\s+(?:a |an |the )?", re.I)
ARTICLES = {"a", "an", "the"}
FILLER = {"of", "and", "&", "s"}
NUMBER_WORDS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
                "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
                "thirteen": "13", "fourteen": "14", "fifteen": "15", "twenty": "20"}

# Answers that try to talk to the judge instead of answering (HW6 lesson: text is data, not instructions)
INJECTION = re.compile(
    r"(?:ignore|disregard|forget) (?:\w+ ){0,3}(?:instructions?|rules?|above)|system prompt|"
    r"you are now|as the judge|mark (?:this|it|me|my answer) (?:as )?(?:correct|right)|accept (?:this|my) answer|"
    r"give me \d+|award me|set (?:my )?score|developer mode|\bjailbreak\b|</?\w+>|\{\{",
    re.I,
)


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize(s: str) -> str:
    s = _strip_accents(s or "").lower().replace("&", " and ")
    s = QUESTION_FORM.sub("", s)
    s = re.sub(r"[\"'`’‘“”]", "", s)
    s = re.sub(r"[^a-z0-9.\- ]", " ", s).replace("-", " ")
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)
    words = [NUMBER_WORDS.get(w, w) for w in s.split()]
    while words and words[0] in ARTICLES:
        words = words[1:]
    return " ".join(words)


def _core(s: str) -> str:
    return " ".join(w for w in normalize(s).split() if w not in FILLER)


HARMLESS = {"i", "think", "maybe", "guess", "it", "its", "is", "probably", "perhaps", "um", "uh", "yale", "the", "a", "an"}


def _same_initials(gw: list[str], tw: list[str]) -> bool:
    """Every target word (3+ letters) has a word in the answer starting with the same letter."""
    starts = {w[0] for w in gw if w}
    return all(w[0] in starts for w in tw if len(w) >= 3)


def similarity(given: str, target: str) -> float:
    g, t = _core(given), _core(target)
    if not g or not t:
        return 0.0
    if g == t:
        return 1.0
    gw, tw = g.split(), t.split()
    # last-name rule: "Taft" for "William Howard Taft", "Hopper" for "Grace Hopper"
    if len(gw) == 1 and len(tw) > 1 and gw[0] == tw[-1] and len(gw[0]) >= 4:
        return 0.95
    # all the target's words are in the answer, plus only harmless extras ("the yale bowl i think").
    # Extra CONTENT words don't count: "Harkness Library" is not "Harkness" (Tower).
    extras = [w for w in gw if w not in tw]
    if all(w in gw for w in tw) and all(w in HARMLESS for w in extras):
        return 0.93
    seq = SequenceMatcher(None, g, t).ratio()
    if seq >= ACCEPT_AT and (not _same_initials(gw, tw) or
                             (len(gw) > len(tw) and any(w not in HARMLESS for w in extras))):
        # "West Rock" vs "East Rock": one letter apart, but a different place (real typos keep the first letter);
        # "Erector X" vs "Erector": an extra word may change the meaning. Let the AI judge decide.
        seq = min(seq, ACCEPT_AT - 0.01)
    overlap = len(set(gw) & set(tw)) / max(len(set(tw)), 1)
    return max(seq, 0.85 * overlap)


@dataclass
class Ruling:
    correct: bool
    score: float
    best_match: str
    method: str                     # exact | fuzzy | ai_judge | rejected
    flags: list[str] = field(default_factory=list)
    needs_ai: bool = False


ACCEPT_AT, REJECT_BELOW = 0.86, 0.55


def judge(given: str, accept: list[str]) -> Ruling:
    """Rule in code. needs_ai=True only when the answer is in the gray zone (and not suspicious)."""
    flags = []
    raw = (given or "").strip()
    if not raw:
        return Ruling(False, 0.0, accept[0], "rejected", ["empty"])
    if len(raw) > MAX_ANSWER_CHARS:
        flags.append("too_long")
    # (an answer key about, say, "system prompts" must still be answerable)
    if INJECTION.search(raw) and not any(INJECTION.search(a) for a in accept):
        flags.append("injection_attempt")
    if flags:
        return Ruling(False, 0.0, accept[0], "rejected", flags)
    scored = sorted(((similarity(raw, a), a) for a in accept), reverse=True)
    score, best = scored[0]
    # numbers must match exactly ("1701" vs "1702" is wrong no matter how similar it looks)
    nums_given, nums_target = set(re.findall(r"\d+", normalize(raw))), set(re.findall(r"\d+", normalize(best)))
    if nums_target and nums_given != nums_target:
        return Ruling(False, score, best, "exact", ["number_mismatch"])
    if score >= ACCEPT_AT:
        return Ruling(True, score, best, "exact" if score == 1.0 else "fuzzy")
    if score < REJECT_BELOW:
        return Ruling(False, score, best, "fuzzy")
    return Ruling(False, score, best, "fuzzy", needs_ai=True)
