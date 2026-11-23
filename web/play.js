"use strict";
let code = (params.get("code") || "").toUpperCase();
let me = null, S = null, poll = null, busy = false, lastKey = "", flashed = "", celebrated = false;
$("#code").value = code;
$("#lk").innerHTML = [1, 2, 3, 4, 5].map(n => `<label><input type="radio" name="helped" value="${n}" ${n === 4 ? "checked" : ""}><span>${n}</span></label>`).join("");

const hdr = () => ({ "X-Player-Id": me.player_id, "X-Player-Token": me.player_token });

$("#join").addEventListener("submit", async (e) => {
  e.preventDefault();
  code = $("#code").value.trim().toUpperCase();
  try {
    me = await withBulldog(api(`/api/rooms/${code}/join`, { body: { name: $("#name").value } }), "Joining the game…");
    session.set(`yj-seat-${code}`, me);
    history.replaceState(null, "", `/play?code=${code}`);
    start();
  } catch (err) { $("#err").textContent = err.message; }
});

function start() {
  $("#v-join").classList.add("hidden");
  $("#me").classList.remove("hidden");
  $("#me-name").textContent = me.name;
  refresh();
  poll = setInterval(refresh, 1000);
}

async function refresh() {
  if (busy) return;
  try { render(await api(`/api/rooms/${code}/me`, { headers: hdr() })); }
  catch (e) {
    if (e.status === 403 || e.status === 404) { clearInterval(poll); session.set(`yj-seat-${code}`, null); location.reload(); }
  }
}
async function act(action, text = "") {
  busy = true;
  try {
    const s = await api(`/api/rooms/${code}/play`, { body: { action, text }, headers: hdr() });
    if (s.error) toast(s.error);
    busy = false; render(s);
  } catch (e) { busy = false; toast(e.message); }
}

function render(s) {
  S = s;
  const m = s.me;
  countUp($("#me-pts"), m.score);
  $("#me-rank").textContent = s.phase === "lobby" ? "" : `#${m.rank} of ${m.of}`;
  if (s.phase === "over") return over(s);
  $("#v-game").classList.remove("hidden");
  const c = s.clue;
  const t = s.timer;
  const show = (el, on) => $(el).classList.toggle("hidden", !on);
  if (s.phase === "lobby" || !c) {
    $("#g-cat").textContent = s.phase === "lobby" ? "You're in!" : s.title;
    $("#g-txt").textContent = s.phase === "lobby" ? "Look at the big screen. The game starts soon." : "The teacher is picking the next clue…";
    show("#ans", false); show("#buzz", false); show("#g-timer", false); $("#g-msg").innerHTML = "";
    return;
  }
  $("#g-cat").textContent = `${c.final ? "Final Jeopardy · " : ""}${c.category} · ${money(c.value)}`;
  $("#g-txt").textContent = c.text;
  const revealed = ["reveal", "final_reveal"].includes(s.phase);
  show("#g-timer", !revealed);
  if (t) {
    const key = `${s.phase}:${c.text}:${t.window_ms}`;
    if (key !== lastKey) { lastKey = key; s.phase === "answering" ? bar($("#g-bar"), 20000 - (t.answer_ms_left || 0), 20000) : bar($("#g-bar"), t.elapsed_ms, t.window_ms); }
  }
  const reading = t && t.elapsed_ms < t.read_ms;
  const wasHidden = $("#ans").classList.contains("hidden");
  show("#ans", m.can_answer && !reading);
  if (m.can_answer && !reading && wasHidden) { $("#ans-in").value = ""; setTimeout(() => $("#ans-in").focus(), 50); }
  show("#buzz", m.can_buzz);
  $("#buzz").disabled = !!reading;
  $("#buzz").textContent = reading ? "Reading…" : "Buzz";
  let msg = "";
  if (revealed) {
    const r = m.result;
    const fk = `${c.text}:${s.phase}`;
    if (r && flashed !== fk) { flashed = fk; flash(r.correct); }
    msg = r ? `<div class="big-ok ${r.correct ? "ok" : "no"}">${r.correct ? "Correct!" : "Not quite"}</div>` : `<div class="big-ok">Time!</div>`;
    if (r && r.blocked) msg += `<p class="err">Blocked: answers can't give instructions to the judge.</p>`;
    msg += `<p>The answer: <b>${esc(c.answer)}</b></p>`;
  } else if (reading && (m.can_answer || m.can_buzz || s.everyone_answers)) msg = `<p class="muted">Read the clue…</p>`;
  else if (m.answered && !m.can_answer) msg = `<p><b>Locked in.</b> Watch the screen!</p>`;
  else if (s.phase === "answering" && !m.can_answer) msg = `<p>${esc(s.answering)} is answering…</p>`;
  $("#g-msg").innerHTML = msg;
}

$("#ans").addEventListener("submit", (e) => { e.preventDefault(); const v = $("#ans-in").value.trim(); if (v) act("answer", v); });
$("#buzz").addEventListener("click", () => act("buzz"));

function over(s) {
  clearInterval(poll);
  $("#v-game").classList.add("hidden");
  $("#v-over").classList.remove("hidden");
  $("#o-rank").textContent = `You finished #${s.me.rank} of ${s.me.of} with ${money(s.me.score)}.`;
  if (!celebrated && s.me.rank <= 3) { celebrated = true; confetti(s.me.rank === 1 ? 3500 : 1800); }
}
$("#sfb").addEventListener("submit", async (e) => {
  e.preventDefault();
  const helped = Number(new FormData(e.target).get("helped"));
  try {
    const sid = S.session_id;
    await api("/api/feedback", { body: { session_id: sid, role: "student", helped }, headers: hdr() });
    e.target.innerHTML = "<p><b>Thanks!</b></p>";
  } catch (err) { toast(err.message); }
});

const saved = session.get(`yj-seat-${code}`);
if (code && saved) { me = saved; start(); }
else if (code) $("#name").focus();
