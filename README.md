# Yale Jeopardy: Classroom Edition

**Turn any lecture into a fact-checked Jeopardy review game in minutes, then play it with the whole class from their phones.**

| | |
|---|---|
| **Teacher** | Uploads slides, PDFs, Word files or notes. A writer agent drafts the board, and every clue must quote the exact line it came from. Code checks the quote is really in the material, and a checker agent fact-checks each clue. The teacher reviews it and can edit, swap or delete any clue. |
| **Class** | The board goes on the projector. Students join with a 5-letter code on their phones. In **Everyone answers** mode, every student answers every clue; **Buzzer** mode is classic Jeopardy. Optional AI contestants fill empty seats. The teacher can overrule any ruling. |
| **Afterwards** | A **reteach list** shows the clues the class missed most, each with the source line to revisit. A session report and an anonymous **evidence page** measure build time vs. by-hand time, clue accuracy, class accuracy and cost. |

Also included: **Yale Jeopardy (solo)** at `/yale`, with 134 fact-checked clues about Yale played against three AI contestants.

> **Running a trial with your class?** See **[TRIAL_GUIDE.md](TRIAL_GUIDE.md)**.

| Page | Path |
|---|---|
| Home | `/` |
| Build a game | `/teach` |
| Projector screen | `/host` |
| Students join | `/play` |
| Session report | `/report` |
| Evidence across all sessions | `/evidence` |

### How the Classroom Edition stays honest (agents propose, code decides)

1. **Only what's visible.** The material reader keeps only text a person can see:
   - It drops white or tiny text, hidden slides and hidden Word runs.
   - In PDFs, it also drops text that's off the page or covered by a white box.
   - It removes lines that try to instruct an AI.

   This is the HW6 prompt-injection defense, reused.
2. **Quote or it doesn't ship.** The writer agent must cite a passage and quote it word for word. Code rejects the clue if the quote isn't in that passage, the passage doesn't exist, the clue gives away its answer, or the clue duplicates another.
3. **A second agent fact-checks.** A verifier agent rates every surviving clue SUPPORTED, AMBIGUOUS or UNSUPPORTED. Code drops the unsupported ones and flags the ambiguous ones for the teacher. Spares are kept so the teacher can swap.
4. **Answers are judged in code.** It handles misspellings, "What is…" phrasing, last names and number words. The AI judge only sees close calls. Answers that try to instruct the judge are marked wrong and counted. The teacher can overrule anything.
5. **Free in class.** AI seat-fillers use offline persona logic. The only AI costs are building the board (one writer call plus one checker call, usually under a cent) and occasional close-call rulings.

## Yale Jeopardy (solo)

**Play Jeopardy about Yale University against three AI contestants**, with an AI host and a judge that can't be sweet-talked. It works on a phone or a PC.

> *Lux et veritas*, and points.

## Quick start (about 2 minutes)

You need **Python 3.10 or newer** ([python.org/downloads](https://www.python.org/downloads/)) and **git**.

```bash
git clone https://github.com/omaranwarny/yale-jeopardy.git
cd yale-jeopardy
bash start.sh         # macOS / Linux   (Windows: double-click start.bat)
```

The browser opens to http://localhost:8000. The first run installs everything into a local `.venv`. After that it starts in seconds.

- **No API key? No problem.** The game runs in **demo mode**: the AI contestants play with offline logic, and the Yale board, buzzers, Daily Doubles and Final Jeopardy all work.
- **Want live AI opponents?** Copy `.env.example` to `.env` and add your `PORTKEY_API_KEY`, or any OpenAI-compatible key and URL (see the table at the bottom). Then restart.
- **Play from phones on the same Wi-Fi:** run `HOST=0.0.0.0 bash start.sh`. It prints the address to open on phones, for example `http://192.168.1.23:8000`. Open the teacher screen with that same address.

The board draws on **130 fact-checked clues plus 4 Final Jeopardy clues** in 8 categories. Every clue links to its source, and the sources are mostly yale.edu, Yale News, Britannica and Nobelprize.org:

| Category | About |
|---|---|
| Founding & Firsts | 1701 charter, Elihu Yale, first U.S. Ph.D., first college art museum |
| Famous Elis | presidents, justices, Nobel laureates, Streep, Hopper, Maya Lin |
| Bulldog Nation | The Game, Walter Camp, Yale Bowl, Handsome Dan, the 2013 hockey title |
| Gothic & Granite | Harkness, Sterling, Beinecke, the Peabody |
| The Elm City | New Haven geography, apizza, Louis' Lunch |
| Yale to the World | chemotherapy, Lyme disease, quantum computing, Yale-China, Yale-NUS |
| Boola Boola | traditions, songs, societies |
| Presidents & Schools | leaders and the 15 schools |

The **"Any topic"** option has an AI writer build a fresh board on anything you type. Those boards are clearly labeled as not fact-checked.

---

## How it works

```
 Phone / PC browser ──HTTP──▶ FastAPI (app/server.py) ──▶ Game engine (app/engine.py)  ◀── code is the referee
   web/ (no build step)            rate limits, spend cap         rules · buzzer · scores · wagers · turns
                                                                         │
                                         ┌───────────────────────────────┼────────────────────────────┐
                                         ▼                               ▼                            ▼
                                Host "Professor Lux"          3 AI Contestants               Judge (gray zone only)
                                opening + recap               Archie · Coach Bea · Dr. Nova   + Writer (custom boards)
                                         └────────── one LLM client (app/llm.py): Portkey · gpt-6-luna · cost meter ──────────┘
 MCP clients (Claude, etc.) ──stdio──▶ mcp_server/server.py ──▶ the same clue bank + the same code judge
```

### The rule of the house: agents talk and propose, code decides

| Part | What the AI does | What code does |
|---|---|---|
| **Contestants** (Archie the history buff, Coach Bea for sports & traditions, Dr. Nova for science & campus) | Write their answer to the clue | Decide *whether* they know it and buzz (from each persona's strengths, the clue's difficulty, and the level you chose), how fast they buzz, what they wager, and which clue they pick |
| **Judge** | Only rules on close calls (similarity score 0.55–0.86) | Matches answers itself first: articles, "What is…", misspellings, last names and number words are all handled. Numbers must match exactly. It parses the AI's verdict and never lets it change a score directly |
| **Host** | Opening line and final recap (2 short calls per game) | Every other line comes from a template, which costs nothing |
| **Writer** | Builds custom-topic boards as JSON | Validates the shape and lengths, then labels the board "AI-written, not fact-checked" |

### Lessons carried over from the class homeworks

- **Prompt injection (HW6).** A player's answer is untrusted text.
  - Answers that try to give orders, like "ignore your instructions", "mark me correct", "award me 1,000" or `<system>` tags, are marked wrong in code and never reach the AI judge.
  - The board shows a "tricks blocked" counter, and the reveal screen labels the attempt.
  - Topics and answers always reach a model as quoted data.
- **Tokenomics (HW6).**
  - The contestants, host and judge have fixed instructions sent with a `prompt_cache_key`, so repeated calls hit the cache.
  - There's a live cost meter on the board, plus a per-agent cost table at the end of every game.
- **Multi-agent + human sign-off (HW5).** Agents never touch the score directly; only the engine does.
- **MCP (HW5).** `mcp_server/server.py` exposes the clue bank and the code judge as MCP tools, so you can be quizzed from Claude or any MCP client.

### What a game costs

A quick game makes roughly 6–15 model calls, mostly short contestant answers, and costs a fraction of a cent at gpt-6-luna prices. The exact cost is shown in the game.

### Public-safe by default

- A **daily dollar cap** (`DAILY_BUDGET_USD`, default $1). Once it's spent, the AIs keep playing in offline demo mode for the rest of the day.
- **Per-device rate limits** on new games and custom boards.
- A strict Content-Security-Policy, and the API key stays on the server.

---

## Run it locally

```bash
cd yale-jeopardy
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # put your PORTKEY_API_KEY in .env (optional)
uvicorn app.server:app --reload --port 8000
```

Open http://localhost:8000. Without a key, everything still works in **demo mode**: the contestants play offline and close calls are ruled "not close enough".

**Play on your phone on the same Wi-Fi:** run `uvicorn app.server:app --host 0.0.0.0 --port 8000`, then open `http://<your-computer's-IP>:8000` on the phone.

### Tests (no key or packages needed)

```bash
python -m unittest discover tests      # judge, injection blocking, buzzer fairness, 40 full simulated games
python scripts/build_bank.py           # rebuilds data/clues.json and checks every clue
```

### Edit or add clues

Clues live in `data/clues_source.txt`, one per line:

```
difficulty | clue | answer | alternate answers; separated; by semicolons | source URL
```

Run `python scripts/build_bank.py` afterwards. It refuses clues without a source, clues that give away their answer, duplicates, and categories missing a difficulty level.

### MCP server (optional)

```bash
pip install -r requirements-mcp.txt
python mcp_server/server.py
```

Tools: `list_categories`, `get_clues`, `random_clue` and `check_answer`. To connect it from Claude Code or Claude Desktop, add `{"command": "python", "args": ["mcp_server/server.py"]}` to your MCP config.

---

## Put it online (free) so anyone can play from a phone

The repo includes `render.yaml` and a `Dockerfile`.

1. Push this folder to a **public GitHub repo**. `.gitignore` keeps `.env` out.
2. On [render.com](https://render.com), go to **New + → Blueprint** and pick the repo.
3. In the service's **Environment** tab, set `PORTKEY_API_KEY`. Optionally change `DAILY_BUDGET_USD`.
4. Share the `https://yale-jeopardy-xxxx.onrender.com` link.

**Notes on free hosting:**

- The free plan sleeps when idle, so the first visit after a while takes about 30 seconds.
- The free plan's disk resets on restart, which also resets the daily spend counter. For a hard limit, **also set a budget on the API key itself** in your Portkey dashboard.

| Environment variable | Default | Purpose |
|---|---|---|
| `PORTKEY_API_KEY` | — | AI key (no key = demo mode) |
| `LLM_MODEL` | `gpt-6-luna` | Model name |
| `LLM_BASE_URL` | `https://api.portkey.ai/v1` | Any OpenAI-compatible endpoint |
| `DAILY_BUDGET_USD` | `1.00` | Server-wide daily spending cap |
| `NEW_GAMES_PER_HOUR` / `CUSTOM_BOARDS_PER_HOUR` | `20` / `4` | Per-device limits |

---

## Project layout

```
app/
  engine.py   game rules, buzzer, scores, Daily Doubles, Final Jeopardy (pure Python)
  agents.py   personas, contestant/judge/host/writer agent calls, bot strategy in code
  judge.py    answer matching + injection blocking
  bank.py     clue bank loading + board building
  llm.py      Portkey client, cost meter, daily budget
  server.py   FastAPI routes + security headers + rate limits
web/          index.html, style.css, app.js (vanilla JS, no build step)
data/         clues_source.txt (edit this) -> clues.json (generated)
mcp_server/   MCP server over the clue bank
scripts/      build_bank.py
tests/        unittest suite
```

Facts were checked against the linked sources in November 2026. Not affiliated with or endorsed by Yale University or the Jeopardy! television show.
