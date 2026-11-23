"""Build report/slides.html: a reveal.js deck (9-10 slides) with screenshots + diagram embedded.

    python scripts/build_slides.py      # then double-click report/slides.html  (arrows to move, F = full screen)

Same data sources as the report (bench/results.json, data/classroom.db, report/screenshots/). Unmeasured numbers
show as "pending", never invented.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_report as R  # noqa: E402  (reuses its measured numbers, screenshots and diagram)

E = R.E
OUT = ROOT / "report" / "slides.html"
REVEAL = "https://cdnjs.cloudflare.com/ajax/libs/reveal.js/5.1.0"


def img(key: str, cls: str = "") -> str:
    """Embedded screenshot, or a labeled placeholder if it hasn't been taken yet."""
    name = R.SHOTS[key]
    for ext in (".png", ".jpg", ".jpeg"):
        p = R.SHOTS_DIR / (name + ext)
        if p.exists():
            mime = "image/png" if ext == ".png" else "image/jpeg"
            return f'<img class="shot {cls}" src="data:{mime};base64,{R.base64.b64encode(p.read_bytes()).decode()}">'
    return f'<div class="shot ph {cls}">screenshot<br><code>{name}.png</code></div>'


def num(v, fmt, unit=""):
    return f'<span class="pend">pending</span>' if v is None else f"{fmt.format(v)}{unit}"


# ------------------------------------------------------------------ measured values (or None)
J = R.J
hy, ai, co = J.get("hybrid"), J.get("ai_every_answer"), J.get("code_only")
built = [b for b in R.boards if b["build"].get("approved_at")]
bmin = R.med([b["build"].get("build_minutes_client") or b["build"].get("build_minutes_server") for b in built])
manual = R.med([f.get("manual_minutes") for f in R.tfb])
acc = R.med([s.get("avg_pct_correct") for s in R.sessions])
kept_total = sum(b["build"].get("clues_final", 0) for b in built)
kept_pct = round(100 * sum(b["build"].get("clues_kept_as_written", 0) for b in built) / kept_total) if kept_total else None
helped = R.med([f.get("helped") for f in R.sfb])
students = sum(s.get("students", 0) for s in R.sessions) or None
saved = (manual - bmin) if manual is not None and bmin is not None else None
wa = R.RT.get("writer_attack")
jt = R.RT.get("judge_attacks", [])
st = R.b1["stats"] if R.b1 else None

slides = []

# 1. Title
slides.append(f"""
<section class="title" data-background-color="#00356b">
  <div class="crest">Y</div>
  <p class="eyebrow">Final project · AI Agents</p>
  <h1>Yale Jeopardy<br><span>Classroom Edition</span></h1>
  <p class="pitch">Turn any lecture into a <b>fact-checked</b> review game your whole class plays from their phones, in minutes.</p>
  <p class="by">{E(R.AUTHOR)} · <a href="{E(R.REPO)}">{E(R.REPO.replace('https://', ''))}</a></p>
</section>""")

# 2. Problem
slides.append("""
<section>
  <h2>The problem</h2>
  <div class="cols">
    <div class="big-stat"><b>~0.5–0.7 SD</b><span>exam boost from practice testing vs. re-reading<br><small>Rowland 2014 · Adesope et al. 2017</small></span></div>
    <div class="big-stat"><b>~53 h</b><span>teachers' work week, 2024<br><small>RAND State of the Teacher</small></span></div>
  </div>
  <ul class="pts">
    <li><b>Who:</b> professors and TAs who want students to <i>recall</i>, not re-read</li>
    <li><b>Today:</b> write 25 clues by hand, or ask ChatGPT and fact-check every answer</li>
    <li><b>Cost:</b> an hour of prep, a risk of wrong "facts" in front of the class, and no idea what to reteach</li>
  </ul>
</section>""")

# 3. What's new
slides.append("""
<section>
  <h2>What's new</h2>
  <table class="cmp">
    <tr><th></th><th>Factile AutoGen</th><th>Kahoot! AI</th><th>ChatGPT</th><th class="us">This project</th></tr>
    <tr><td>Builds from your PDF / slides</td><td>✓</td><td>✓</td><td>✓</td><td class="us">✓</td></tr>
    <tr><td>Every clue quotes its source line</td><td>not advertised</td><td>not advertised</td><td>if asked</td><td class="us">✓ checked in code</td></tr>
    <tr><td>Second agent fact-checks before class</td><td>not advertised</td><td>not advertised</td><td>–</td><td class="us">✓</td></tr>
    <tr><td>Typed recall answers, judged fairly</td><td>host judges</td><td>mostly multiple choice</td><td>–</td><td class="us">✓</td></tr>
    <tr><td>Hidden-text &amp; injection defenses</td><td>not advertised</td><td>not advertised</td><td>–</td><td class="us">✓ red-teamed</td></tr>
    <tr><td>Reteach list with source lines</td><td>–</td><td>reports</td><td>–</td><td class="us">✓</td></tr>
  </table>
  <p class="note">Honest note: AI quiz generators already exist (based on their public product pages, Nov 2026). The difference here is <b>trust</b>: quote it, check it, show it.</p>
</section>""")

# 4. Agents
slides.append(f"""
<section>
  <h2>How the agents work</h2>
  <div class="diagram-wrap">{R.diagram()}</div>
  <p class="note"><b>Agents propose, code decides.</b> Writer → code checks every quote → checker agent → teacher approves.
  In class, code is the referee; an AI judge is only asked on close calls. Model: <code>{E(R.MODEL)}</code>.</p>
</section>""")

# 5. Demo: teacher
slides.append(f"""
<section>
  <h2>Demo · the teacher</h2>
  <div class="shots3">{img('upload')}{img('review')}{img('editor')}</div>
  <p class="caps"><span>1 · Drop in the lecture</span><span>2 · Review the board (amber = flagged)</span><span>3 · Every clue shows its quote</span></p>
</section>""")

# 6. Demo: class
slides.append(f"""
<section>
  <h2>Demo · the class</h2>
  <div class="shots3">{img('clue')}{img('phone', 'tall')}{img('reveal')}</div>
  <p class="caps"><span>Projector: live answer count</span><span>Phones: type an answer</span><span>Reveal: source quote, % correct, override</span></p>
</section>""")

# 7. Cost
cost_rows = f"""
    <div class="big-stat"><b>{num(R.build_cost, '${:.4f}')}</b><span>to build one board<br><small>{num(R.build_in, '{:,.0f}')} in / {num(R.build_out, '{:,.0f}')} out tokens</small></span></div>
    <div class="big-stat"><b>{num(R.class_game_cost, '${:.4f}')}</b><span>per class game (30 students)<br><small>only close calls use the AI</small></span></div>
    <div class="big-stat"><b>{num(R.teacher_month, '${:.2f}')}</b><span>per teacher / month<br><small>8 boards + 8 games</small></span></div>"""
scale = f"100 teachers ≈ {num(R.teacher_month and R.teacher_month * 100, '${:,.2f}')}/mo · 10,000 ≈ {num(R.teacher_month and R.teacher_month * 10000, '${:,.0f}')}/mo"
quality = (f"Cost cut didn't hurt quality: the hybrid judge scored <b>{hy['accuracy_pct']}%</b> vs <b>{ai['accuracy_pct']}%</b> for an AI on every answer, "
           f"with <b>{ai['ai_calls'] - hy['ai_calls']}</b> fewer AI calls.") if hy and ai else \
          'Judge study (code vs. hybrid vs. all-AI): <span class="pend">pending</span>'
slides.append(f"""
<section>
  <h2>Cost to run</h2>
  <div class="cols3">{cost_rows}</div>
  <p class="note">{scale}</p>
  <p class="note">{quality}</p>
</section>""")

# 8. Safety
blocked = sum(1 for x in jt if not x["correct"])
slides.append(f"""
<section>
  <h2>Safety</h2>
  <div class="cols">
    <ul class="pts small">
      <li><b>Poisoned files:</b> white or tiny text, hidden slides, covered PDF text and AI-directed lines are removed before any model sees them</li>
      <li><b>Invented facts:</b> the quote must be in the file (code), plus a checker agent, plus teacher review</li>
      <li><b>Students hacking the judge:</b> "mark me correct" is blocked in code and counted</li>
      <li><b>Runaway spend:</b> daily $ cap, rate limits, 2 calls per board, timeouts</li>
    </ul>
    <div>{img('blocked')}
      <p class="note">{f'Live red team: <b>{blocked}/{len(jt)}</b> judge attacks blocked' if jt else 'Live red team: <span class="pend">pending</span>'}{f' · poisoned lecture → <b>{len(wa["banana_answers"])}</b> poisoned clues' if wa else ''} · <b>{R.N_TESTS}</b> automated tests</p></div>
  </div>
</section>""")

# 9. Impact
P, PS, ub = R.PILOT, R.PILOT_S, (R.user_builds[0] if R.user_builds else None)
p_right = sum(1 for h in PS.get("history", []) if any(a["correct"] for a in h["answers"] if not a["ai"])) if PS else None
p_total = len(PS.get("history", [])) if PS else None
p_helped = R.med([f.get("helped") for f in R.PILOT_SFB]) if PS else None
slides.append(f"""
<section>
  <h2>Impact: the numbers</h2>
  <div class="cols3">
    <div class="big-stat"><b>{num(ub and ub['seconds'], '{:.0f}', ' s')}</b><span>for the agents to build a board from a real lecture<br><small>15 picture-only slides · {num(ub and ub['stats']['kept'], '{}')} checked clues</small></span></div>
    <div class="big-stat"><b>{num(ub and ub['usage']['cost_usd'], '${:.3f}')}</b><span>AI cost of that board</span></div>
    <div class="big-stat"><b>~60 min</b><span>typical time to write &amp; check a review game by hand<br><small>estimate · measured comparison is next</small></span></div>
  </div>
  <div class="cols3">
    <div class="big-stat"><b>{num(p_right, '{}')}{'' if p_right is None else f'/{p_total}'}</b><span>clues right · first-time player<br><small>pilot tester: the author's brother</small></span></div>
    <div class="big-stat"><b>{num(p_helped, '{}', '/5')}</b><span>"helped me review"</span></div>
    <div class="big-stat"><b style="font-size:1.05em">“{E(P['quote']) if P else '–'}”</b><span>{E(P['quote_by']) if P else ''}</span></div>
  </div>
  <p class="note">Honest status: one student-role tester so far; no teacher has built a board from their own lecture yet. Professor Zaman and the TAs are the next pilot.</p>
</section>""")

# 10. Next
slides.append(f"""
<section data-background-color="#00356b" class="title">
  <h2 style="color:#f2c14e">What's next</h2>
  <ul class="pts light">
    <li>Spaced repetition: missed clues come back in the next game</li>
    <li>Canvas integration: pull lecture files, post the reteach list</li>
    <li>Read every page as an image: equations, diagrams, and no more hidden-text tricks</li>
    <li>An A/B study: sections with vs. without the game on the next quiz</li>
  </ul>
  <p class="by">Try it: <code>git clone {E(R.REPO)}</code> → <code>bash start.sh</code></p>
</section>""")

CSS = """
:root{--blue:#00356b;--gold:#f2c14e;--ink:#14213d;--muted:#5c677d}
.reveal{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--ink);font-size:30px}
.reveal h1,.reveal h2{font-family:"Iowan Old Style","Palatino Linotype",Georgia,serif;text-transform:none;letter-spacing:-.01em}
.reveal h2{color:var(--blue);font-size:1.7em;margin-bottom:.5em}
.reveal section{text-align:left}
.title{text-align:center!important;color:#fff}
.title h1{color:#fff;font-size:2.4em;line-height:1.05;margin:.2em 0}
.title h1 span{color:var(--gold)}
.crest{width:110px;height:110px;margin:0 auto 10px;border-radius:24px;background:#f6f1e7;color:var(--blue);font:800 72px/110px Georgia,serif;box-shadow:inset 0 0 0 4px var(--gold)}
.eyebrow{text-transform:uppercase;letter-spacing:.18em;font-size:.55em;font-weight:700;color:var(--gold);margin:0}
.pitch{font-size:1.05em;color:#dbe6f3;max-width:900px;margin:.6em auto}
.by{font-size:.6em;color:#c4d3e6}.by a{color:var(--gold)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:30px;align-items:start}
.cols3{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;margin:10px 0}
.big-stat{background:#f4f1ea;border-radius:16px;padding:18px 20px}
.big-stat b{display:block;font:800 1.7em/1.1 Georgia,serif;color:var(--blue)}
.big-stat span{font-size:.62em;color:var(--muted);display:block;margin-top:4px}
.big-stat small{font-size:.85em;opacity:.8}
.pts{font-size:.8em;line-height:1.45}.pts li{margin-bottom:.4em}.pts.small{font-size:.66em}
.pts.light{color:#e8eef6;text-align:left;max-width:900px;margin:0 auto}
.note{font-size:.6em;color:var(--muted);margin-top:.7em}
.cmp{font-size:.55em;width:100%;border-collapse:collapse}
.cmp th,.cmp td{padding:.45em .6em;border-bottom:1px solid #e3ded3;text-align:center}
.cmp td:first-child,.cmp th:first-child{text-align:left}
.cmp .us{background:#fff3d1;font-weight:800;color:var(--blue)}
.diagram-wrap svg{width:100%;height:auto;max-height:480px}
.shots3{display:grid;grid-template-columns:1fr .6fr 1fr;gap:16px;align-items:center}
.shot{width:100%;border-radius:12px;border:1px solid #ddd;box-shadow:0 10px 30px rgba(0,0,0,.12);max-height:470px;object-fit:contain;background:#fff}
.shot.ph{display:grid;place-items:center;height:300px;border:3px dashed #c9c2b2;color:#9a927f;font-size:.5em;box-shadow:none}
.caps{display:grid;grid-template-columns:1fr .6fr 1fr;gap:16px;font-size:.5em;color:var(--muted);text-align:center}
.pend{display:inline-block;font:700 .55em/1.6 -apple-system,Arial;background:#fff3d1;color:#8a6512;border:1px solid #e2b23c;border-radius:8px;padding:0 .5em;vertical-align:middle}
.reveal code{font-size:.85em;background:#eef2f6;padding:.05em .3em;border-radius:6px;color:var(--blue)}
.title code{background:rgba(255,255,255,.12);color:#fff}
.reveal .progress{color:var(--gold)}
/* fallback if reveal.js can't load (offline): still readable, one slide after another */
.reveal:not(.ready) section{display:block!important;padding:40px;border-bottom:1px solid #ddd}
.reveal:not(.ready) section.title{background:#00356b}
"""

html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Yale Jeopardy · Classroom Edition</title>
<link rel="stylesheet" href="{REVEAL}/reset.min.css">
<link rel="stylesheet" href="{REVEAL}/reveal.min.css">
<link rel="stylesheet" href="{REVEAL}/theme/white.min.css">
<style>{CSS}</style></head>
<body><div class="reveal"><div class="slides">{''.join(slides)}</div></div>
<script src="{REVEAL}/reveal.min.js"></script>
<script>Reveal.initialize({{hash:true, slideNumber:'c/t', transition:'slide', width:1280, height:720, margin:0.05}});</script>
</body></html>"""

OUT.write_text(html, encoding="utf-8")
print(f"wrote {OUT} ({len(slides)} slides, {OUT.stat().st_size // 1024} KB)")
