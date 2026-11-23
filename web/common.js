/* Shared helpers for the Classroom Edition pages. */
"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => (n < 0 ? "-$" : "$") + Math.abs(n || 0).toLocaleString();
const params = new URLSearchParams(location.search);

const store = {
  get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch (_) { return null; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) { /* private mode */ } },
};
const session = {
  get(k) { try { return JSON.parse(sessionStorage.getItem(k)); } catch (_) { return null; } },
  set(k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch (_) { /* private mode */ } },
};

/* Teacher keys live only in this browser: board id -> token */
const teacherKey = (boardId) => (store.get("yj-boards") || {})[boardId]?.token;
function rememberBoard(boardId, token, title) {
  const all = store.get("yj-boards") || {};
  all[boardId] = { token, title, saved: Date.now(), rooms: (all[boardId] || {}).rooms || [] };
  store.set("yj-boards", all);
}
function rememberRoom(boardId, code, sessionId) {
  const all = store.get("yj-boards") || {};
  if (all[boardId]) { all[boardId].rooms.unshift({ code, sessionId, at: Date.now() }); store.set("yj-boards", all); }
}

async function api(path, { body, method, headers = {} } = {}) {
  const res = await fetch(path, {
    method: method || (body !== undefined ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", ...headers },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch (_) { /* empty */ }
  if (!res.ok) {
    const msg = typeof data.detail === "string" ? data.detail
      : Array.isArray(data.detail) ? data.detail.map(d => d.msg).join("; ") : `Server error (${res.status})`;
    const err = new Error(msg); err.status = res.status; throw err;
  }
  return data;
}

function toast(msg, ms = 3200) {
  let t = $("#toast");
  if (!t) { t = document.createElement("div"); t.id = "toast"; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), ms);
}

function bar(el, elapsedMs, totalMs) {
  if (!el) return;
  cancelAnimationFrame(el._raf);
  const start = performance.now() - elapsedMs;
  const tick = () => {
    const left = Math.max(0, 1 - (performance.now() - start) / totalMs);
    el.style.transform = `scaleX(${left})`;
    el.classList.toggle("urgent", left > 0 && left * totalMs < 5000);     // last 5 seconds turn red
    if (left > 0) el._raf = requestAnimationFrame(tick);
  };
  tick();
}
