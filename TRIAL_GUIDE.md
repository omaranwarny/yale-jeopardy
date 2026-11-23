# Trial guide: Classroom Edition with Professor Zaman and TAs

**Goal:** find out whether this saves teachers time and helps students review, with real numbers.
**What a trial takes:** about 10 minutes to build a board, 15–20 minutes of class time to play, and 1 minute of feedback.

## 1. Before class (the person running the server, about 10 minutes)

Students' phones must be able to reach the app, and campus Wi-Fi often blocks phone-to-laptop connections. The easiest reliable setup is to run it on your Mac and share it through a free secure tunnel:

```bash
cd yale-jeopardy
bash start.sh                                  # needs PORTKEY_API_KEY in .env to build boards from material
# in a second terminal (one-time install: brew install cloudflared)
cloudflared tunnel --url http://localhost:8000
```

`cloudflared` prints a public link like `https://something.trycloudflare.com`. That link is what the teacher and the students open. Keep both terminals open during class.

All trial data (boards, sessions, feedback) stays on your Mac in `data/classroom.db`. Nothing is sent anywhere except the material sent to the AI model when a board is built.

## 2. The teacher builds a board (about 5–10 minutes)

1. Open `<link>/teach` on the laptop that will drive the projector.
2. Drop in the lecture slides, PDF, or notes. Pick 5 categories × 5 clues, or 4 × 3 for a short game.
3. Click **Build my board** and wait about 30–60 seconds.
4. Review the board:
   - Tap any clue to see the exact quote it came from.
   - Clues with an **amber** border were flagged by the checker agent. Read those, and edit, swap or delete as needed.
5. Choose a mode, then click **Approve & open the room**:
   - **Everyone answers** is recommended: it gives the best reteach data.
   - **Buzzer** is classic Jeopardy.

The build timer starts when the page opens and stops at **Approve**. Don't leave the page open idle for a long time before building, or the measured time will be inflated.

## 3. In class (15–20 minutes)

1. Project the host screen. Students go to `<link>/play` and type the 5-letter code.
2. Click **Start**, then pick clues on the board. In "Everyone answers" mode, a clue closes when every student has answered.
3. At each reveal, you'll see the answer, the source quote, and what % of the class got it. Use **Accept** or **Mark wrong** to overrule the judge.
4. Play **Final Jeopardy**, then **Show results**.

## 4. Right after class (1 minute, important)

- **Teacher:** fill in the **1-minute feedback** on the results screen. The most important question is *"Without this tool, how many minutes would this take you?"*
- **Students:** answer the one-tap question on their phones: "Did this help you review?"
- Use **Full session report** for the printable reteach list and the per-clue results.

## 5. What gets measured (shown on `<link>/evidence`, anonymous)

| Question | Measured by |
|---|---|
| Does it save time? | Build time (page open → approve) vs. the teacher's by-hand estimate |
| Are the clues right? | Clues rejected by code and by the checker agent, clues teachers kept without edits, and teacher-rated accuracy |
| Does it help learning? | Per-clue class accuracy, whether the reteach list matched what students struggle with, and students' "helped me review" rating |
| What does it cost? | Measured AI dollars per board and per game, plus a projection for a whole school |

Sessions played on the built-in **sample lecture** are left out of the evidence, so practice runs don't count.

## Privacy

- Students choose their own nickname. No logins, emails or student IDs are collected.
- Names appear only in the teacher's own session report, never on the evidence page.
- Course material is sent to the AI model (gpt-6-luna via Portkey) only while the board is being built.
