"""Tiny LLM client: Portkey (or any OpenAI-compatible endpoint), token + dollar meter, daily spend cap.

No key, no `openai` package, or the daily budget is used up  ->  demo mode (agents play with offline logic).
The model is set once in config (default gpt-6-luna) - the same setup as the class homeworks.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


KEY_NAMES = ("PORTKEY_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY")     # first one found wins
KEY_SOURCE = "shell environment" if any(os.getenv(k) for k in KEY_NAMES) else None


def _load_env() -> None:
    global KEY_SOURCE
    for p in (ROOT / ".env", ROOT.parent / ".env"):
        if p.exists():
            for line in p.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.split(" #")[0].strip().strip('"').strip("'")
                    if k in KEY_NAMES and not os.getenv(k) and v:
                        KEY_SOURCE = str(p)
                    os.environ.setdefault(k, v)


_load_env()

_KEY_NAME = next((k for k in KEY_NAMES if os.getenv(k)), None)
_KEY = os.getenv(_KEY_NAME) if _KEY_NAME else ""
# Works with whichever key you have:
#   a Portkey key            -> Portkey gateway, gpt-6-luna (the class setup)
#   an OpenAI key (sk-...)   -> OpenAI directly, gpt-5.6-luna by default
# LLM_BASE_URL / LLM_MODEL in .env always win.
PROVIDER = "openai" if (_KEY_NAME == "OPENAI_API_KEY" or _KEY.startswith("sk-")) and not os.getenv("LLM_BASE_URL") else \
    ("portkey" if "portkey" in os.getenv("LLM_BASE_URL", "portkey") else "custom")
BASE_URL = os.getenv("LLM_BASE_URL") or ("https://api.openai.com/v1" if PROVIDER == "openai" else "https://api.portkey.ai/v1")
MODEL = os.getenv("LLM_MODEL") or ("gpt-5.6-luna" if PROVIDER == "openai" else "gpt-6-luna")
# $ per 1M tokens. gpt-6-luna: the class prices.json. gpt-5.6-luna, gpt-5-mini: OpenAI model pages (Nov 2026). Env vars override.
_DEFAULT_PRICES = {"gpt-6-luna": (0.10, 0.01, 0.50), "gpt-5.6-luna": (0.20, 0.02, 1.20),
                   "gpt-5-mini": (0.25, 0.025, 2.00)}.get(MODEL, (0.10, 0.01, 0.50))
PRICES = {
    "input": float(os.getenv("PRICE_INPUT_PER_1M", _DEFAULT_PRICES[0])),
    "cached": float(os.getenv("PRICE_CACHED_PER_1M", _DEFAULT_PRICES[1])),
    "output": float(os.getenv("PRICE_OUTPUT_PER_1M", _DEFAULT_PRICES[2])),
}
DAILY_BUDGET = float(os.getenv("DAILY_BUDGET_USD", "1.00"))
SPEND_FILE = Path(os.getenv("SPEND_FILE", str(ROOT / "data" / "spend.json")))


@dataclass
class Meter:
    calls: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    by_agent: dict = field(default_factory=dict)

    def add(self, agent: str, inp: int, cached: int, out: int) -> float:
        cost = ((inp - cached) * PRICES["input"] + cached * PRICES["cached"] + out * PRICES["output"]) / 1e6
        self.calls += 1
        self.input_tokens += inp
        self.cached_tokens += cached
        self.output_tokens += out
        self.cost_usd += cost
        a = self.by_agent.setdefault(agent, {"calls": 0, "tokens": 0, "cost_usd": 0.0})
        a["calls"] += 1
        a["tokens"] += inp + out
        a["cost_usd"] = round(a["cost_usd"] + cost, 8)
        return cost

    def public(self) -> dict:
        return {"calls": self.calls, "input_tokens": self.input_tokens, "cached_tokens": self.cached_tokens,
                "output_tokens": self.output_tokens, "cost_usd": round(self.cost_usd, 6), "by_agent": self.by_agent}


class Budget:
    """Daily dollar cap shared by every game on this server. Survives restarts via a small JSON file."""
    _lock = threading.Lock()

    def __init__(self, limit: float = DAILY_BUDGET, path: Path = SPEND_FILE):
        self.limit, self.path = limit, path

    def _read(self) -> dict:
        try:
            d = json.loads(self.path.read_text())
            return d if d.get("day") == date.today().isoformat() else {"day": date.today().isoformat(), "usd": 0.0}
        except Exception:
            return {"day": date.today().isoformat(), "usd": 0.0}

    def spent(self) -> float:
        return self._read()["usd"]

    def remaining(self) -> float:
        return max(self.limit - self.spent(), 0.0)

    def add(self, usd: float) -> None:
        with self._lock:
            d = self._read()
            d["usd"] = round(d["usd"] + usd, 8)
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(d))
            except OSError:
                pass


BUDGET = Budget()


class LLM:
    def __init__(self) -> None:
        self.key = _KEY or None
        self.client = None
        if self.key:
            try:
                from openai import AsyncOpenAI
                headers = {"x-portkey-api-key": self.key, "x-portkey-provider": os.getenv("PORTKEY_PROVIDER", "openai")} \
                    if "portkey" in BASE_URL else {}
                self.client = AsyncOpenAI(api_key="unused" if headers else self.key, base_url=BASE_URL,
                                          default_headers=headers, timeout=float(os.getenv("LLM_TIMEOUT", "20")))
            except ImportError:
                self.client = None
        self.last_error: str | None = None
        self.failures = 0

    @property
    def live(self) -> bool:
        return self.client is not None and BUDGET.remaining() > 0 and self.failures < 5

    def mode(self) -> str:
        if self.client is None:
            return "demo"
        if BUDGET.remaining() <= 0:
            return "demo (daily budget used)"
        if self.failures >= 5:
            return "demo (AI unavailable)"
        return "live"

    async def ask(self, meter: Meter, agent: str, instructions: str, prompt: str, max_tokens: int = 120,
                  timeout: float | None = None, image: tuple[str, bytes] | None = None,
                  effort: str | None = None, json_mode: bool = False) -> str | None:
        """One model call. Returns text, or None if we are in demo mode or the call failed."""
        if not self.live:
            return None
        t0 = time.perf_counter()
        try:
            # max_output_tokens leaves room for hidden reasoning tokens; the agents' answers are short
            client = self.client.with_options(timeout=timeout) if timeout else self.client
            inp_ = prompt
            if image:   # (mime, bytes): a page image for the reader to transcribe
                import base64
                inp_ = [{"role": "user", "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": f"data:{image[0]};base64,{base64.b64encode(image[1]).decode()}"}]}]
            extra = {"prompt_cache_key": f"yale-jeopardy-{agent}"}
            if json_mode:      # the API guarantees syntactically valid JSON
                extra["text"] = {"format": {"type": "json_object"}}
            if MODEL.startswith("gpt-5") and not getattr(self, "_no_reasoning_param", False):
                extra["reasoning"] = {"effort": effort or "low"}   # keep hidden reasoning small so answers fit
            try:
                r = await client.responses.create(model=MODEL, instructions=instructions, input=inp_,
                                                  max_output_tokens=max(max_tokens, 400), extra_body=extra)
            except Exception as e:     # some models reject the reasoning setting: retry once without it
                if "reasoning" not in str(e).lower() or "reasoning" not in extra:
                    raise
                self._no_reasoning_param = True
                extra.pop("reasoning")
                r = await client.responses.create(model=MODEL, instructions=instructions, input=inp_,
                                                  max_output_tokens=max(max_tokens, 400), extra_body=extra)
            text = (r.output_text or "").strip()
            if not text:
                self.last_error = f"empty reply (status={getattr(r, 'status', '?')}, " \
                                  f"reason={getattr(getattr(r, 'incomplete_details', None), 'reason', None)})"
            u = r.usage
            inp = getattr(u, "input_tokens", 0) or 0
            cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
            out = getattr(u, "output_tokens", 0) or 0
            BUDGET.add(meter.add(agent, inp, cached, out))
            self.failures = 0
            return text
        except Exception as e:  # network, auth, rate limit ... the game must go on
            self.failures += 1
            self.last_error = f"{type(e).__name__}: {str(e)[:160]} ({time.perf_counter() - t0:.1f}s)"
            return None
