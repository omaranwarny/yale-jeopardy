"use strict";
$("#print").addEventListener("click", (e) => { e.preventDefault(); print(); });
const boardId = params.get("board");
let sessionId = params.get("session");

(async function () {
  const token = teacherKey(boardId);
  if (!token) { $("#title").textContent = "Open this report from the browser where you built the board."; return; }
  if (!sessionId) {
    const b = (store.get("yj-boards") || {})[boardId] || {};
    sessionId = (b.rooms || [])[0]?.sessionId;
    if (!sessionId) { $("#title").textContent = "No sessions yet for this board."; return; }
  }
  let r;
  try { r = await api(`/api/sessions/${sessionId}/report`, { headers: { "X-Teacher-Token": token } }); }
  catch (e) { $("#title").textContent = e.message; return; }
  const s = r.session, b = r.board.build || {}, w = b.writer || {};
  $("#title").textContent = s.title;
  $("#meta").textContent = `${new Date(s.created * 1000).toLocaleString()} · ${s.mode === "all" ? "Everyone answers" : "Buzzer mode"}` +
    `${s.ai_seats ? ` · ${s.ai_seats} AI contestant(s)` : ""} · room ${s.code}`;
  const st = [["good", s.students, "students"], ["", s.clues_played, "clues played"],
    ["", s.avg_pct_correct == null ? "–" : `${s.avg_pct_correct}%`, "average correct"], ["", `${s.minutes} min`, "length"],
    ["warn", s.overrides, "teacher rulings"], ["bad", s.injection_attempts_blocked, "tricks blocked"],
    ["", `$${((s.llm || {}).cost_usd || 0).toFixed(4)}`, "AI cost (game)"]];
  $("#stats").innerHTML = st.map(([k, v, l]) => `<div class="stat ${k}"><b>${esc(v)}</b>${l}</div>`).join("");
  $("#reteach").innerHTML = (s.reteach || []).map(x => `<li><span class="pct">${x.pct_correct}%</span><b>${esc(x.category)}</b>: ${esc(x.clue)}
     <br><b>Answer:</b> ${esc(x.answer)}${x.quote ? `<div class="quote" style="margin-top:8px">“${esc(x.quote)}”<small>${esc(x.source || "")}</small></div>` : ""}</li>`).join("")
    || "<li>Nothing below 80% correct.</li>";
  const mins = b.build_minutes_client ?? b.build_minutes_server;
  $("#build").innerHTML = `<table class="t">
    <tr><td>Source</td><td>${b.source === "sample" ? "Sample lecture" : esc((b.materials || []).map(f => f.name).join(", "))}</td></tr>
    <tr><td>Time to build (open → approve)</td><td>${mins == null ? "–" : `${mins} min`}</td></tr>
    <tr><td>Clues drafted / on the board</td><td>${w.generated ?? "–"} / ${b.clues_final ?? w.kept ?? "–"}</td></tr>
    <tr><td>Rejected by code (quote not found, giveaway…)</td><td>${w.rejected_by_code ?? 0}</td></tr>
    <tr><td>Rejected by the checker agent</td><td>${w.rejected_by_verifier ?? 0}</td></tr>
    <tr><td>Flagged for teacher review</td><td>${w.flagged ?? 0}</td></tr>
    <tr><td>Teacher edits / swaps / deletes</td><td>${(b.edits || {}).edited || 0} / ${(b.edits || {}).swapped || 0} / ${(b.edits || {}).deleted || 0}</td></tr>
    <tr><td>Hidden text removed from files</td><td>${b.hidden_removed ?? 0}</td></tr>
    <tr><td>AI cost to build</td><td>$${((b.cost || {}).cost_usd || 0).toFixed(4)}</td></tr></table>`;
  $("#clues").innerHTML = `<tr><th>Category</th><th>Clue</th><th>Answer</th><th>% correct</th><th>Answers</th></tr>` +
    (s.history || []).map(h => `<tr><td>${esc(h.category)}</td><td>${esc(h.clue)}</td><td>${esc(h.answer)}</td>
      <td>${h.pct_correct == null ? "–" : h.pct_correct + "%"}</td><td>${h.answered}/${h.humans}</td></tr>`).join("");
  $("#students").innerHTML = `<tr><th>Name</th><th>Score</th><th>Correct</th><th>Answered</th></tr>` +
    (s.students_detail || []).map(p => `<tr><td>${esc(p.name)}</td><td>${money(p.score)}</td><td>${p.correct}</td><td>${p.answered}</td></tr>`).join("");
  const tf = r.feedback.filter(f => f.role === "teacher"), sf = r.feedback.filter(f => f.role === "student");
  $("#fb").innerHTML = (tf.map(f => `<p><b>${esc(f.role_title || "Teacher")}</b>: by hand ≈ ${f.manual_minutes ?? "?"} min · usefulness ${f.usefulness ?? "?"}/5 ·
      accuracy ${f.accuracy ?? "?"}/5 · reteach list matched: ${esc(f.reteach_matches || "?")} · use again: ${esc(f.use_again || "?")}
      ${f.comment ? `<br>“${esc(f.comment)}”` : ""}</p>`).join("") || "<p class='muted'>No teacher feedback yet.</p>") +
    `<p>Students: ${sf.length} response(s)${sf.length ? `, median “helped me review” ${median(sf.map(f => f.helped))}/5` : ""}.</p>`;
})();

function median(xs) { xs = xs.filter(x => typeof x === "number").sort((a, b) => a - b); if (!xs.length) return "–"; const m = Math.floor(xs.length / 2); return xs.length % 2 ? xs[m] : (xs[m - 1] + xs[m]) / 2; }
