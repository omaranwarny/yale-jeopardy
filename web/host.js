"use strict";
const code = (params.get("code") || "").toUpperCase();
const boardId = params.get("board");
const token = teacherKey(boardId);
let S = null, poll = null, busy = false, lastKey = "";
let prevPhase = null, pickedRect = null, lastSubmitted = 0, revealKey = "", celebrated = false;
const shownScores = {};

const joinUrl = `${location.host}/play`;
$("#url").textContent = joinUrl; $("#url2").textContent = joinUrl;
$("#code").textContent = code; $("#code2").textContent = code;
$("#o-report").href = `/report?board=${boardId}`;
$$(".likert").forEach(l => { l.innerHTML = [1, 2, 3, 4, 5].map(n =>
  `<label><input type="radio" name="${l.dataset.name}" value="${n}" ${n === 4 ? "checked" : ""}><span>${n}</span></label>`).join(""); });

async function refresh() {
  if (busy) return;
  try { render(await api(`/api/rooms/${code}/host`, { headers: { "X-Teacher-Token": token } })); }
  catch (e) { if (e.status === 403 || e.status === 404) { stop(); $("#title").textContent = e.message; } }
}
async function act(action, extra = {}) {
  busy = true;
  try {
    const s = await api(`/api/rooms/${code}/teacher`, { body: { action, ...extra }, headers: { "X-Teacher-Token": token } });
    if (s.error) toast(s.error);
    busy = false; render(s);
  } catch (e) { busy = false; toast(e.message); }
}
function stop() { clearInterval(poll); poll = null; }

function render(s) {
  const from = prevPhase;
  prevPhase = s.phase;
  S = s;
  $("#title").textContent = s.title;
  $("#mode").textContent = s.mode === "all" ? "Everyone answers" : "Buzzer mode";
  const ph = s.phase;
  $("#v-lobby").classList.toggle("hidden", ph !== "lobby");
  $("#v-main").classList.toggle("hidden", ph === "lobby" || ph === "over");
  $("#v-over").classList.toggle("hidden", ph !== "over");
  $("#codebox").style.visibility = ph === "lobby" || ph === "over" ? "hidden" : "visible";
  if (ph === "lobby") return lobby(s);
  if (ph === "over") return over(s);
  leaderboard(s);
  const onBoard = ["board", "final_ready"].includes(ph);
  $("#board").classList.toggle("hidden", !onBoard);
  $("#clue").classList.toggle("hidden", onBoard);
  if (onBoard) board(s); else clue(s);
  if (!onBoard && ["board", "final_ready"].includes(from) && s.phase === "clue") zoomFrom($("#clue"), pickedRect);
  controls(s);
}

function lobby(s) {
  $("#roster").innerHTML = s.roster.map(p => `<span class="${p.ai ? "ai" : ""}">${esc(p.name)}${p.ai ? " · AI" : ""}</span>`).join("");
  const n = s.players;
  $("#count").textContent = n ? `${n} student${n === 1 ? "" : "s"} joined` : "Waiting for players…";
}
$("#start").addEventListener("click", () => withBulldog(act("start"), "Shuffling the board…"));

function leaderboard(s) {
  const list = $("#lb"), pos = flipBefore(list);
  list.innerHTML = s.leaders.map(p => `<li class="${p.ai ? "ai" : ""}" data-k="${esc(p.id)}">${esc(p.name)}<b data-v="${shownScores[p.id] ?? p.score}">${money(shownScores[p.id] ?? p.score)}</b></li>`).join("");
  flipAfter(list, pos);
  s.leaders.forEach(p => { const b = list.querySelector(`[data-k="${CSS.escape(p.id)}"] b`); if (b) countUp(b, p.score); shownScores[p.id] = p.score; });
  $("#players").textContent = `${s.players} student${s.players === 1 ? "" : "s"} playing · code ${s.code}`;
}

function board(s) {
  const b = s.board, el = $("#board");
  const rows = Math.max(...b.categories.map(c => c.cells.length));
  el.style.gridTemplateColumns = `repeat(${b.categories.length}, minmax(0,1fr))`;
  el.style.gridAutoFlow = "row";
  el.innerHTML = b.categories.map((c, ci) => `<div class="col" style="grid-template-rows:auto repeat(${rows},1fr)"><div class="cat">${esc(c.name)}</div>` +
    c.cells.map((x, ri) => `<button class="cell ${x.used ? "used" : ""}" data-c="${ci}" data-r="${ri}" ${x.used ? "disabled" : ""}>${x.used ? "" : money(x.value)}</button>`).join("") + "</div>").join("");
}
$("#board").addEventListener("click", (e) => {
  const b = e.target.closest(".cell");
  if (b && !b.disabled) { pickedRect = b.getBoundingClientRect(); act("pick", { c: +b.dataset.c, r: +b.dataset.r }); }
});

function clue(s) {
  const c = s.clue || {};
  $("#c-cat").textContent = c.final ? `Final Jeopardy · ${c.category}` : c.category;
  $("#c-val").textContent = money(c.value);
  $("#c-txt").textContent = c.text || "";
  const revealed = ["reveal", "final_reveal"].includes(s.phase);
  $("#reveal").classList.toggle("hidden", !revealed);
  $("#c-timerwrap").style.display = revealed ? "none" : "";
  if (!revealed) {
    const t = s.timer || {};
    const key = `${s.phase}:${c.text}:${t.window_ms}:${s.answering}`;
    if (key !== lastKey) { lastKey = key; s.phase === "answering" ? bar($("#c-bar"), 20000 - (t.answer_ms_left || 0), 20000) : bar($("#c-bar"), t.elapsed_ms, t.window_ms); }
    const reading = t.elapsed_ms < t.read_ms;
    if (s.submitted > lastSubmitted) bump($("#c-status"));
    lastSubmitted = s.submitted || 0;
    $("#c-status").textContent = s.phase === "answering" ? `${s.answering} is answering…`
      : reading ? "Read the clue…" : s.everyone_answers ? `${s.submitted} of ${s.players} answered — answer on your phone!`
      : "Buzzers are open!";
    $("#c-txt").style.fontSize = "";
    return;
  }
  $("#c-status").textContent = "";
  $("#r-ans").textContent = c.answer;
  $("#r-quote").innerHTML = c.quote ? `“${esc(c.quote)}”<small>${esc(c.source || "")}</small>` : "";
  const pct = s.pct_correct;
  $("#r-meter").style.display = pct === null || pct === undefined ? "none" : "";
  const rk = `${c.text}:${s.phase}`;
  if (rk !== revealKey) {                       // new reveal: fill the bar from zero
    revealKey = rk; lastSubmitted = 0;
    $("#r-meter i").style.transition = "none"; $("#r-meter i").style.width = "0%";
    requestAnimationFrame(() => requestAnimationFrame(() => { $("#r-meter i").style.transition = ""; $("#r-meter i").style.width = `${pct || 0}%`; }));
  } else $("#r-meter i").style.width = `${pct || 0}%`;
  $("#r-meter span").textContent = pct === null || pct === undefined ? "" : `${pct}% of the class got it`;
  const tricks = (s.results || []).filter(r => r.flags.includes("injection_attempt")).length;
  $("#r-shield").classList.toggle("hidden", !tricks);
  $("#r-shield").textContent = `Safety check: ${tricks} answer${tricks === 1 ? "" : "s"} tried to give orders to the judge and ${tricks === 1 ? "was" : "were"} blocked`;
  const ordered = [...(s.results || [])].sort((a, b) => (b.correct - a.correct));
  const sig = rk + JSON.stringify(ordered.map(r => [r.player_id, r.correct]));
  if ($("#r-list").dataset.sig === sig) return;          // unchanged: don't replay the entrance animation
  $("#r-list").dataset.sig = sig;
  $("#r-list").innerHTML = ordered.map((r, i) => `<li class="${r.correct ? "ok" : "no"}" style="--i:${i}"><span class="who">${esc(r.name)}${r.ai ? " · AI" : ""}</span>
      <span>${esc(r.text || "(no answer)")}</span><span class="mark">${r.correct ? "✓" : "✗"}</span>
      ${r.flags.includes("injection_attempt") ? `<span class="blocked">Blocked: tried to instruct the judge</span>` : `<span class="tg">${r.overridden ? "teacher ruling" : r.method === "ai_judge" ? "AI judge" : r.close ? "close" : ""}</span>`}
      ${r.ai ? "" : `<button class="ov" data-p="${r.player_id}" data-v="${r.correct ? 0 : 1}">${r.correct ? "Mark wrong" : "Accept"}</button>`}</li>`).join("")
    || `<li>No answers.</li>`;
}
$("#r-list").addEventListener("click", (e) => { const b = e.target.closest(".ov"); if (b) act("override", { player_id: b.dataset.p, correct: b.dataset.v === "1" }); });

function controls(s) {
  const c = [];
  if (s.phase === "board") c.push(`<button class="btn ghost" data-a="end">End game</button>`);
  if (s.phase === "board" && s.board.has_final) c.push(`<button class="btn ghost" data-a="final">Skip to Final Jeopardy</button>`);
  if (["clue", "answering"].includes(s.phase)) c.push(`<button class="btn ghost" data-a="close">Close &amp; reveal</button>`);
  if (s.phase === "reveal") c.push(`<button class="btn gold big" data-a="next">Next clue</button>`);
  if (s.phase === "final_ready") c.push(s.board.has_final ? `<button class="btn gold big" data-a="final">Final Jeopardy</button>` : "", `<button class="btn ghost" data-a="end">End game</button>`);
  if (s.phase === "final_reveal") c.push(`<button class="btn gold big" data-a="end">Show results</button>`);
  $("#ctl").innerHTML = c.join("");
}
$("#ctl").addEventListener("click", (e) => { const b = e.target.closest("[data-a]"); if (b) act(b.dataset.a); });

function over(s) {
  stop();
  const m = s.summary;
  $("#o-report").href = `/report?session=${m.session_id}&board=${boardId}`;
  const st = [["good", m.students, "students played"], ["", m.clues_played, "clues played"],
    ["", m.avg_pct_correct === null ? "–" : `${m.avg_pct_correct}%`, "average correct"],
    ["", `${m.minutes} min`, "game length"], ["warn", m.overrides, "teacher rulings"],
    ["bad", m.injection_attempts_blocked, "tricks blocked"]];
  $("#o-stats").innerHTML = st.map(([k, v, l]) => `<div class="stat ${k}"><b>${esc(v)}</b>${l}</div>`).join("");
  if (!celebrated) { celebrated = true; confetti(); }
  $("#o-reteach").innerHTML = m.reteach.length ? m.reteach.map((r, i) => `<li style="--i:${i}"><span class="pct">${r.pct_correct}%</span>
     <b>${esc(r.category)}</b>: ${esc(r.clue)}<br><b>Answer:</b> ${esc(r.answer)}
     ${r.quote ? `<div class="quote" style="margin-top:8px">“${esc(r.quote)}”<small>${esc(r.source || "")}</small></div>` : ""}</li>`).join("")
    : `<li>Everyone got at least 80% of every clue. Nothing to reteach!</li>`;
}
$("#fb").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const body = { session_id: S.summary.session_id, role: "teacher" };
  for (const [k, v] of f.entries()) body[k] = ["manual_minutes", "usefulness", "accuracy"].includes(k) ? Number(v) : v;
  try { await api("/api/feedback", { body, headers: { "X-Teacher-Token": token } }); e.target.innerHTML = "<p><b>Thank you!</b> Your feedback is saved in the evidence report.</p>"; }
  catch (err) { toast(err.message); }
});

if (!token) { $("#title").textContent = "This screen needs the teacher's key. Open it from the browser where you built the board."; }
else { refresh(); poll = setInterval(refresh, 800); }
