"use strict";
const startedAt = Date.now();          // build-time evidence: from opening this page to approving the board
let files = [];                         // {name, data_b64}
let boardId = null, token = null, board = null, build = null, editing = null;

$("#join-url").textContent = `${location.host}/play`;

/* ------------------------------------------------ files */
const drop = $("#drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); addFiles(e.dataTransfer.files); });
$("#file").addEventListener("change", (e) => addFiles(e.target.files));

function addFiles(list) {
  [...list].forEach(f => {
    if (files.length >= 8) return toast("8 files max.");
    if (f.size > 12 * 1024 * 1024) return toast(`${f.name} is over 12 MB.`);
    const r = new FileReader();
    r.onload = () => { files.push({ name: f.name, data_b64: String(r.result).split(",")[1] || "" }); showFiles(); };
    r.readAsDataURL(f);
  });
}
function showFiles() {
  $("#files").innerHTML = files.map((f, i) => `<li>${esc(f.name)}<button class="x" data-i="${i}" aria-label="remove">✕</button></li>`).join("");
}
$("#files").addEventListener("click", (e) => { const b = e.target.closest(".x"); if (b) { files.splice(+b.dataset.i, 1); showFiles(); } });

/* ------------------------------------------------ build */
function show(id) { ["#s-upload", "#s-build", "#s-review"].forEach(s => $(s).classList.toggle("hidden", s !== id)); window.scrollTo(0, 0); }
function step(n) { $$("#steps li").forEach(li => { const s = +li.dataset.s; li.className = s < n ? "done" : s === n ? "on" : ""; }); }

$("#build").addEventListener("click", async () => {
  const items = [...files];
  const paste = $("#paste").value.trim();
  if (paste) items.push({ name: "pasted notes", text: paste });
  if (!items.length) { $("#err").textContent = "Add a file or paste some notes first."; return; }
  $("#err").textContent = "";
  show("#s-build"); step(0);
  try {
    const m = await api("/api/materials", { body: { items } });
    const bad = m.files.filter(f => f.error).map(f => `${f.name}: ${f.error}`);
    $("#read-info").textContent = `Read ${m.passages} passages from ${m.files.length - bad.length} source(s)` +
      (m.ocr_pages ? ` · read ${m.ocr_pages} picture-only slide(s) with the reader agent` : "") +
      (m.hidden_removed ? ` · removed ${m.hidden_removed} hidden text item(s)` : "") +
      (m.ai_directed_removed.length ? ` · dropped ${m.ai_directed_removed.length} line(s) aimed at an AI` : "") +
      (bad.length ? ` · skipped: ${bad.join("; ")}` : "");
    step(1);
    const timers = [setTimeout(() => step(2), 9000), setTimeout(() => step(3), 16000), setTimeout(() => step(4), 26000)];
    const res = await api("/api/boards", { body: {
      materials_id: m.materials_id, categories: +$("#o-cats").value, rows: +$("#o-rows").value,
      audience: $("#o-aud").value, focus: $("#o-focus").value, client_started_at: startedAt } });
    timers.forEach(clearTimeout);
    loaded(res);
  } catch (e) {
    show("#s-upload");
    $("#err").textContent = e.message;
  }
});

$("#sample").addEventListener("click", async () => {
  try { loaded(await api("/api/boards/sample", { body: {} })); } catch (e) { $("#err").textContent = e.message; }
});

function loaded(res) {
  boardId = res.board_id; token = res.teacher_token; board = res.board; build = res.build;
  rememberBoard(boardId, token, board.title);
  history.replaceState(null, "", `/teach?board=${boardId}`);
  renderReview();
  show("#s-review");
}

/* ------------------------------------------------ review */
function renderReview() {
  $("#b-title").textContent = board.title;
  const w = build.writer || {}, c = build.cost || {};
  const st = [
    ["good", w.kept ?? "-", "clues on the board"],
    ["", w.generated ?? "-", "drafted by the writer"],
    ["bad", (w.rejected_by_code || 0) + (w.rejected_by_verifier || 0), "rejected by the checks"],
    ["warn", w.flagged ?? 0, "flagged for you"],
    ["", build.hidden_removed ?? 0, "hidden text items removed"],
    ["", c.cost_usd !== undefined ? `$${(c.cost_usd || 0).toFixed(4)}` : "$0", "AI cost to build"],
  ];
  $("#b-stats").innerHTML = st.map(([k, v, l]) => `<div class="stat ${k}"><b>${esc(v)}</b>${l}</div>`).join("");
  const rb = $("#rboard");
  rb.style.gridTemplateColumns = `repeat(${board.categories.length}, minmax(0,1fr))`;
  rb.innerHTML = board.categories.map((cat, ci) => `<div class="rcol"><div class="cat">${esc(cat.name)}</div>` +
    cat.clues.map((q, ri) => `<button class="rcell ${q.status === "flagged" ? "flagged" : ""} ${q.edited ? "edited" : ""}" data-c="${ci}" data-r="${ri}">
      <span class="v">${money(q.value)}</span>${esc(q.clue.slice(0, 90))}${q.clue.length > 90 ? "…" : ""}</button>`).join("") +
    `<small class="muted">${(cat.spares || []).length} spare(s)</small></div>`).join("");
  const f = board.final;
  $("#final-tile").innerHTML = f ? `<h3>Final Jeopardy: ${esc(f.category)}</h3><p>${esc(f.clue)}</p><p><b>Answer:</b> ${esc(f.answer)}</p>
    <div class="quote">“${esc(f.quote)}”<small>${esc(f.source)}</small></div>` : `<p class="muted">No Final Jeopardy clue passed the checks.</p>`;
}

$("#rboard").addEventListener("click", (e) => {
  const b = e.target.closest(".rcell"); if (!b) return;
  editing = { c: +b.dataset.c, r: +b.dataset.r };
  const q = board.categories[editing.c].clues[editing.r];
  $("#ed-cat").textContent = board.categories[editing.c].name;
  $("#ed-val").textContent = money(q.value);
  $("#ed-clue").value = q.clue; $("#ed-ans").value = q.answer;
  $("#ed-acc").value = (q.accept || []).filter(a => a !== q.answer).join(", ");
  $("#ed-quote").innerHTML = `“${esc(q.quote)}”<small>${esc(q.source)} · passage ${esc(q.passage)}</small>`;
  $("#ed-note").textContent = q.status === "flagged" ? `Checker: ${q.note || q.verifier_note || "please double-check this clue"}`
    : q.verdict ? `Checker: ${q.verdict.toLowerCase()}${q.verifier_note ? " · " + q.verifier_note : ""}` : "";
  $("#ed-swap").disabled = !(board.categories[editing.c].spares || []).length;
  $("#ed").classList.add("open");
});
async function edit(action) {
  const body = { ...editing, action };
  if (action === "update") Object.assign(body, { clue: $("#ed-clue").value, answer: $("#ed-ans").value,
    accept: $("#ed-acc").value.split(",").map(s => s.trim()).filter(Boolean) });
  try {
    const res = await api(`/api/boards/${boardId}/edit`, { body, headers: { "X-Teacher-Token": token } });
    board = res.board; build = res.build; renderReview(); $("#ed").classList.remove("open");
  } catch (e) { toast(e.message); }
}
$("#ed-save").addEventListener("click", () => edit("update"));
$("#ed-swap").addEventListener("click", () => edit("swap"));
$("#ed-del").addEventListener("click", () => { if (confirm("Delete this clue?")) edit("delete"); });
$("#ed-close").addEventListener("click", () => $("#ed").classList.remove("open"));

$("#host").addEventListener("click", async () => {
  try {
    await api(`/api/boards/${boardId}/approve`, { body: { client_seconds: (Date.now() - startedAt) / 1000 }, headers: { "X-Teacher-Token": token } });
    const room = await api("/api/rooms", { body: { board_id: boardId, mode: $("#h-mode").value, ai_seats: +$("#h-ai").value },
      headers: { "X-Teacher-Token": token } });
    rememberRoom(boardId, room.code, room.session_id);
    location.href = `/host?code=${room.code}&board=${boardId}`;
  } catch (e) { toast(e.message); }
});
$("#restart").addEventListener("click", () => { location.href = "/teach"; });

/* ------------------------------------------------ reopen a saved board */
(async function init() {
  const mine = store.get("yj-boards") || {};
  const ids = Object.keys(mine).sort((a, b) => mine[b].saved - mine[a].saved).slice(0, 8);
  if (ids.length) {
    $("#mine").style.display = "";
    $("#mine-list").innerHTML = ids.map(id => `<li><a href="/teach?board=${id}">${esc(mine[id].title || id)}</a>
      <small class="muted">${new Date(mine[id].saved).toLocaleDateString()}</small>
      ${(mine[id].rooms || []).slice(0, 1).map(r => `<a style="margin-left:auto" href="/report?session=${r.sessionId}&board=${id}">last report</a>`).join("")}</li>`).join("");
  }
  const id = params.get("board");
  if (id && teacherKey(id)) {
    try {
      const b = await api(`/api/boards/${id}`, { headers: { "X-Teacher-Token": teacherKey(id) } });
      boardId = id; token = teacherKey(id); board = b.board; build = b.build;
      renderReview(); show("#s-review");
    } catch (e) { toast(e.message); }
  }
})();
