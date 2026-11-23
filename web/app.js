/* Yale Jeopardy - browser client. The server is the referee; this file only shows state and sends taps. */
"use strict";

const $ = (s) => document.querySelector(s);
const RIVALS = [
  { name: "Archie", tag: "the history buff", color: "#b08d57" },
  { name: "Coach Bea", tag: "sports & traditions", color: "#3f7d4e" },
  { name: "Dr. Nova", tag: "science & campus", color: "#6b5ca5" },
];

let game = null;          // last state from the server
let timer = null;         // pending auto-advance
let anim = null;          // timer-bar animation frame
let busy = false;         // a request is in flight
let shownEvents = 0;
let lastScores = {};
let revealKey = null;

/* ------------------------------------------------------------ server calls */
async function api(path, body, method = "POST") {
  const res = await fetch(path, {
    method, headers: { "Content-Type": "application/json" },
    body: method === "POST" ? JSON.stringify(body || {}) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch (_) { /* empty */ }
  if (res.status === 409 && data.game) return data.game;          // not allowed right now: just resync
  if (!res.ok) throw new Error(data.detail || data.error || `Server error (${res.status})`);
  return data;
}

async function act(path, body) {
  if (!game || busy) return;
  busy = true;
  try {
    const g = await api(`/api/games/${game.id}/${path}`, body);
    render(g);
  } catch (e) {
    if (/not found/i.test(e.message)) { alert(e.message); return backToStart(); }
    console.warn(e);
    schedule(() => act("advance"), 1500);       // flaky network: try to resync
  } finally {
    busy = false;
  }
}

/* ------------------------------------------------------------ start screen */
async function initStart() {
  $("#rivals").innerHTML = RIVALS.map(r =>
    `<div class="rival"><div class="av" style="background:${r.color}">${r.name[0]}</div><b>${r.name}</b><small>${r.tag}</small></div>`).join("");
  try {
    const h = await api("/api/health", null, "GET");
    const live = h.mode === "live";
    $("#mode-pill").textContent = live ? `AI live · ${h.model}` : "Demo mode · offline AI";
    $("#mode-pill").className = `pill ${live ? "live" : "demo"}`;
    if (!live) {
      $("#custom-chip").classList.add("disabled");
      $("#custom-chip input").disabled = true;
      $("#custom-chip span").textContent = "Any topic (needs live AI)";
    }
  } catch (_) {
    $("#mode-pill").textContent = "Server unreachable";
  }
  const saved = localStorageGet("yj-name");
  if (saved) $("#f-name").value = saved;
}

function localStorageGet(k) { try { return localStorage.getItem(k); } catch (_) { return null; } }
function localStorageSet(k, v) { try { localStorage.setItem(k, v); } catch (_) { /* private mode */ } }

document.querySelectorAll('input[name="board"]').forEach(r => r.addEventListener("change", () => {
  $("#f-topic").classList.toggle("hidden", r.value !== "custom" || !r.checked);
  if (r.value === "custom" && r.checked) $("#f-topic").focus();
}));

$("#start-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#play-btn");
  const custom = document.querySelector('input[name="board"]:checked').value === "custom";
  const body = {
    name: $("#f-name").value.trim() || "You",
    size: document.querySelector('input[name="size"]:checked').value,
    level: document.querySelector('input[name="level"]:checked').value,
    topic: custom ? $("#f-topic").value.trim() : null,
  };
  if (custom && !body.topic) { $("#start-err").textContent = "Type a topic first."; return; }
  localStorageSet("yj-name", body.name);
  btn.disabled = true;
  btn.textContent = custom ? "The writer is building your board…" : "Setting up the board…";
  $("#start-err").textContent = "";
  try {
    const g = await withBulldog(api("/api/games", body), custom ? "The writer is building your board…" : "Fetching the board…");
    shownEvents = 0; lastScores = {}; revealKey = null;
    $("#feed-list").innerHTML = "";
    $("#start").classList.remove("active");
    $("#game").classList.add("active");
    render(g);
  } catch (err) {
    $("#start-err").textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Play";
  }
});

function backToStart() {
  clearTimers();
  game = null;
  ["#clue", "#over", "#about"].forEach(s => $(s).classList.remove("open"));
  $("#game").classList.remove("active");
  $("#start").classList.add("active");
}

/* ------------------------------------------------------------ rendering */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => (n < 0 ? "-$" : "$") + Math.abs(n).toLocaleString();
const playerName = (id) => (game.players.find(p => p.id === id) || {}).name || id;

function clearTimers() {
  if (timer) clearTimeout(timer);
  if (anim) cancelAnimationFrame(anim);
  timer = anim = null;
}
function schedule(fn, ms) {
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => { timer = null; fn(); }, Math.max(0, ms));
}

function render(g) {
  clearTimers();
  game = g;
  renderScores(g);
  renderBoard(g);
  renderFeed(g);
  $("#meter").textContent = `AI cost $${g.meter.cost_usd.toFixed(4)} · ${g.meter.calls} calls`;
  $("#game-mode").textContent = g.mode === "live" ? "AI live" : g.mode;
  $("#game-mode").className = `pill ${g.mode === "live" ? "live" : "demo"}`;
  $("#shield").classList.toggle("hidden", !g.flags);
  $("#shield").textContent = `${g.flags} trick${g.flags === 1 ? "" : "s"} blocked`;
  if (g.notice) flashStatus(g.notice);
  phase(g);
}

function renderScores(g) {
  $("#scores").innerHTML = g.players.map(p => {
    const cls = ["score", g.control === p.id ? "control" : "", g.answering === p.id ? "active" : ""].join(" ");
    const delta = lastScores[p.id] !== undefined ? p.score - lastScores[p.id] : 0;
    const flash = delta ? `<span class="flash" style="color:${delta > 0 ? "#a6f0c4" : "#ffb4b9"}">${delta > 0 ? "+" : ""}${money(delta)}</span>` : "";
    return `<div class="${cls}"><div class="nm"><span class="dot" style="background:${p.color}"></span>${esc(p.name)}</div>
      <div class="pts ${p.score < 0 ? "neg" : ""}">${money(p.score)}</div><small>${esc(p.tagline)}</small>${flash}</div>`;
  }).join("");
  lastScores = Object.fromEntries(g.players.map(p => [p.id, p.score]));
  const hostEv = [...g.events].reverse().find(e => e.kind === "host");
  if (hostEv) $("#host-line").textContent = hostEv.text;
}

function renderBoard(g) {
  const b = g.board, rows = b.values.length;
  const canPick = g.phase === "pick";
  const board = $("#board");
  board.style.gridTemplateColumns = `repeat(${b.categories.length}, minmax(0, 1fr))`;
  board.style.gridAutoFlow = "row";
  board.classList.toggle("locked", !canPick);
  board.innerHTML = b.categories.map((c, ci) =>
    `<div class="col" style="grid-template-rows: auto repeat(${rows}, 1fr)"><div class="cat">${esc(c.name)}</div>` +
    c.cells.map(cell => `<button class="cell ${cell.used ? "used" : ""}" data-id="${cell.id}" ${cell.used || !canPick ? "disabled" : ""}
      aria-label="${esc(c.name)} for ${cell.value}">${cell.used ? "" : money(cell.value)}</button>`).join("") + `</div>`).join("");
  board.style.display = "grid";
}

$("#board").addEventListener("click", (e) => {
  const btn = e.target.closest(".cell");
  if (btn && !btn.disabled) act("pick", { cell_id: btn.dataset.id });
});

function renderFeed(g) {
  const list = $("#feed-list");
  const fresh = g.events.filter(e => e.i >= shownEvents);
  fresh.forEach(e => {
    const li = document.createElement("li");
    li.className = e.kind;
    li.innerHTML = `<b>${esc(e.who)}:</b> ${esc(e.text)}`;
    list.appendChild(li);
  });
  if (fresh.length) { shownEvents = fresh[fresh.length - 1].i + 1; list.scrollTop = list.scrollHeight; }
}

/* ------------------------------------------------------------ phases */
function show(id, on) { $(id).classList.toggle("hidden", !on); }
function openClue(on) { $("#clue").classList.toggle("open", on); }
function flashStatus(msg) { $("#clue-status").textContent = msg; }

function clueHeader(g) {
  const c = g.clue || {};
  $("#clue-cat").textContent = c.category || (g.final && g.final.category) || "";
  $("#clue-val").textContent = c.daily_double ? (c.wager ? `Wager ${money(c.wager)}` : "Daily Double")
    : g.phase.startsWith("final") ? "Final Jeopardy" : c.value ? money(c.value) : "";
  show("#dd-banner", !!c.daily_double && g.phase === "dd_wager");
  $("#clue-text").textContent = c.text || (g.phase === "final_wager" ? `Category: ${g.final.category}` : "");
}

function panels({ buzz = false, answer = false, wager = false, reveal = false } = {}) {
  show("#act-buzz", buzz); show("#act-answer", answer); show("#act-wager", wager); show("#reveal", reveal);
  $(".timer").style.visibility = buzz || answer ? "visible" : "hidden";
  $(".timer").style.display = reveal ? "none" : "";
  $("#clue-status").style.display = reveal ? "none" : "";
}

function bar(fromMs, totalMs) {
  const start = performance.now() - fromMs;
  const el = $("#timer-bar");
  const tick = () => {
    const left = Math.max(0, 1 - (performance.now() - start) / totalMs);
    el.style.transform = `scaleX(${left})`;
    if (left > 0) anim = requestAnimationFrame(tick);
  };
  tick();
}

function phase(g) {
  const ph = g.phase;
  $("#over").classList.remove("open");
  if (ph === "pick") { openClue(false); return; }
  if (ph === "bot_pick") { openClue(false); return schedule(() => act("advance"), 1300); }

  if (ph === "over") { openClue(false); return showOver(g); }
  openClue(true);
  clueHeader(g);

  if (ph === "dd_wager" || ph === "final_wager") {
    panels({ wager: true });
    const max = ph === "dd_wager" ? g.max_wager : g.final.max_wager;
    $("#wager-max").textContent = `(up to ${money(max)})`;
    $("#wager-in").max = max; $("#wager-in").min = ph === "dd_wager" ? 5 : 0;
    $("#wager-in").value = Math.min(max, ph === "dd_wager" ? 500 : Math.floor(max / 2));
    flashStatus(ph === "dd_wager" ? "Only you can answer this one." : "Wager before you see the clue.");
    return setTimeout(() => $("#wager-in").focus(), 50);
  }
  if (ph === "clue") {
    const t = g.timer;
    panels({ buzz: true });
    const openIn = t.read_ms - t.elapsed_ms;
    $("#buzz-btn").disabled = !t.you_can_buzz || openIn > 0;
    $("#buzz-btn").textContent = openIn > 0 ? "Reading…" : "Buzz";
    $("#pass-btn").disabled = !t.you_can_buzz;
    if (openIn > 0 && t.you_can_buzz) {
      setTimeout(() => {
        if (game && game.phase === "clue") { $("#buzz-btn").disabled = false; $("#buzz-btn").textContent = "Buzz"; }
      }, openIn);
    }
    if (!g.notice) flashStatus(g.clue.rebound ? (t.you_can_buzz ? "Rebound! Anyone else?" : "Rebound: the others can try.") : "");
    bar(t.elapsed_ms, t.window_ms);
    const waits = [t.window_ms - t.elapsed_ms + 60];
    if (t.next_bot_ms !== null) waits.push(t.next_bot_ms - t.elapsed_ms + 40);
    return schedule(() => act("advance"), Math.min(...waits));
  }
  if (ph === "answer") {
    panels({ answer: true });
    flashStatus(g.clue.daily_double ? "Your Daily Double answer:" : "You buzzed in! Your answer:");
    const left = g.timer.answer_ms_left;
    bar(25000 - left, 25000);
    $("#answer-in").value = "";
    setTimeout(() => $("#answer-in").focus(), 50);
    return schedule(() => act("advance"), left + 150);
  }
  if (ph === "bot_answer") {
    panels({});
    $("#clue-status").innerHTML = `<span class="thinking">${esc(playerName(g.answering))} is answering</span>`;
    return schedule(() => act("advance"), 700);
  }
  if (ph === "final_answer" || ph === "final_judging") {
    const mine = g.final.players.includes("you");
    if (mine && ph === "final_answer") {
      panels({ answer: true });
      flashStatus("Final Jeopardy! Your answer:");
      bar(40000 - g.final.ms_left, 40000);
      $("#answer-in").value = "";
      setTimeout(() => $("#answer-in").focus(), 50);
      return schedule(() => act("advance"), g.final.ms_left + 200);
    }
    panels({});
    $("#clue-status").innerHTML = `<span class="thinking">The contestants are writing their answers</span>`;
    return schedule(() => act("advance"), 900);
  }
  if (ph === "reveal") return showReveal(g);
}

function showReveal(g) {
  const L = g.last;
  panels({ reveal: true });
  $("#clue-cat").textContent = L.category;
  $("#clue-val").textContent = L.daily_double ? "Daily Double" : money(L.value);
  show("#dd-banner", false);
  $("#clue-text").textContent = L.clue;
  $("#reveal-ans").textContent = L.answer;
  $("#attempts").innerHTML = (L.attempts || []).map(a => {
    const tag = a.flags.includes("injection_attempt") ? "blocked: tried to instruct the judge"
      : a.method === "ai_judge" ? `AI judge: ${esc(a.reason)}` : a.method === "fuzzy" && a.correct ? "close enough" : "";
    return `<li class="${a.correct ? "ok" : "no"}"><b>${esc(playerName(a.player))}</b>: ${esc(a.answer || "(no answer)")}
      ${a.correct ? "✓" : "✗"}<span class="tag">${tag}</span></li>`;
  }).join("") || `<li>Nobody buzzed in.</li>`;
  const src = $("#reveal-src");
  if (L.source) { src.href = L.source; src.textContent = `Source: ${new URL(L.source).hostname}`; src.classList.remove("hidden"); }
  else { src.textContent = g.board.verified ? "" : "AI-written clue, not fact-checked"; src.removeAttribute("href"); }
  flashStatus("");
  revealKey = `${g.id}:${L.cell}`;
  schedule(() => act("advance"), 5200);
}

function showOver(g) {
  const ranked = [...g.players].sort((a, b) => b.score - a.score);
  const you = g.players.find(p => !p.ai);
  $("#over-title").textContent = ranked[0].id === you.id ? "You win!" : `${ranked[0].name} wins`;
  $("#standings").innerHTML = ranked.map(p =>
    `<li><i class="sdot" style="background:${p.color}"></i>${esc(p.name)}<span class="amt">${money(p.score)}</span></li>`).join("");
  const f = g.final && g.final.results;
  const L = g.last || {};
  $("#final-box").innerHTML = f ? `<p><b>Final Jeopardy:</b> ${esc(L.clue)}<br><b>Answer:</b> ${esc(L.answer)}</p><ul class="attempts">` +
    Object.entries(f).map(([pid, r]) => `<li class="${r.correct ? "ok" : "no"}"><b>${esc(playerName(pid))}</b> wagered ${money(r.wager)}:
      ${esc(r.answer || "(no answer)")} ${r.correct ? "✓" : "✗"}</li>`).join("") + "</ul>" : "";
  const m = g.meter;
  $("#cost-detail").innerHTML = `<p>${m.calls} AI calls · ${m.input_tokens.toLocaleString()} input tokens (${m.cached_tokens.toLocaleString()} cached) ·
    ${m.output_tokens.toLocaleString()} output · <b>$${m.cost_usd.toFixed(5)}</b></p>` +
    (Object.keys(m.by_agent).length ? `<table><tr><th>Agent</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr>` +
      Object.entries(m.by_agent).map(([a, v]) => `<tr><td>${esc(a)}</td><td>${v.calls}</td><td>${v.tokens}</td><td>$${v.cost_usd.toFixed(5)}</td></tr>`).join("") + `</table>`
      : `<p class="muted">Demo mode: the AIs played offline, so this game cost nothing.</p>`);
  $("#over").classList.add("open");
}

/* ------------------------------------------------------------ inputs */
$("#buzz-btn").addEventListener("click", () => act("buzz"));
$("#pass-btn").addEventListener("click", () => act("pass"));
$("#act-answer").addEventListener("submit", (e) => { e.preventDefault(); act("answer", { text: $("#answer-in").value }); });
$("#act-wager").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = parseInt($("#wager-in").value, 10);
  if (Number.isNaN(v)) return flashStatus("Enter a number.");
  act("wager", { amount: v });
});
$("#continue-btn").addEventListener("click", () => act("advance"));
$("#again-btn").addEventListener("click", backToStart);
$("#quit-btn").addEventListener("click", () => { if (confirm("Leave this game and start a new one?")) backToStart(); });
$("#feed-btn").addEventListener("click", () => $("#feed").classList.add("open"));
$("#feed-close").addEventListener("click", () => $("#feed").classList.remove("open"));
document.addEventListener("keydown", (e) => {
  const typing = ["INPUT", "TEXTAREA"].includes(document.activeElement.tagName);
  if (e.code === "Space" && !typing && game && game.phase === "clue") {
    e.preventDefault();
    if (!$("#buzz-btn").disabled) act("buzz");
  }
  if (e.key === "Escape") { $("#feed").classList.remove("open"); $("#about").classList.remove("open"); }
});

$("#about-link").addEventListener("click", async (e) => {
  e.preventDefault();
  $("#about").classList.add("open");
  try {
    const b = await api("/api/bank", null, "GET");
    $("#bank-line").textContent = `${b.clues} fact-checked clues in ${b.categories.length} categories: ${b.categories.map(c => c.name).join(", ")}.`;
    $("#sources").innerHTML = b.sources.map(s => `<li><a href="${esc(s)}" target="_blank" rel="noopener">${esc(s)}</a></li>`).join("");
  } catch (_) { /* offline */ }
});
$("#about-close").addEventListener("click", () => $("#about").classList.remove("open"));

initStart();
