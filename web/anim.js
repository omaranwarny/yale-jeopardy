/* Small, purposeful animations for the classroom screens. No libraries. Honors "reduce motion". */
"use strict";
const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;

/* Roll a dollar amount from its old value to the new one. */
function countUp(el, to, ms = 700) {
  const from = Number(el.dataset.v ?? to);
  el.dataset.v = to;
  if (REDUCE || from === to) { el.textContent = money(to); return; }
  const t0 = performance.now();
  const step = (t) => {
    const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3);
    el.textContent = money(Math.round(from + (to - from) * e));
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/* FLIP: rows slide to their new places when the ranking changes. Call before() then after() around a re-render. */
function flipBefore(list) {
  const pos = {};
  [...list.children].forEach(li => { pos[li.dataset.k] = li.getBoundingClientRect().top; });
  return pos;
}
function flipAfter(list, pos) {
  if (REDUCE) return;
  [...list.children].forEach(li => {
    const old = pos[li.dataset.k];
    if (old === undefined) return;
    const dy = old - li.getBoundingClientRect().top;
    if (!dy) return;
    li.animate([{ transform: `translateY(${dy}px)` }, { transform: "translateY(0)" }],
      { duration: 450, easing: "cubic-bezier(.2,.8,.2,1)" });
  });
}

/* Make an element pop once (e.g. the "12 of 30 answered" counter ticking up). */
function bump(el) {
  if (REDUCE || !el) return;
  el.animate([{ transform: "scale(1)" }, { transform: "scale(1.12)" }, { transform: "scale(1)" }], { duration: 300 });
}

/* Zoom the clue card up from the board cell that was picked. */
function zoomFrom(card, rect) {
  if (REDUCE || !rect) return;
  const c = card.getBoundingClientRect();
  const sx = rect.width / c.width, sy = rect.height / c.height;
  const dx = rect.left + rect.width / 2 - (c.left + c.width / 2);
  const dy = rect.top + rect.height / 2 - (c.top + c.height / 2);
  card.animate([{ transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`, opacity: .6 },
    { transform: "translate(0,0) scale(1,1)", opacity: 1 }], { duration: 480, easing: "cubic-bezier(.2,.8,.2,1)" });
}

/* Full-screen green / red wash + vibration on phones when the result comes in. */
function flash(ok) {
  if (navigator.vibrate) { try { navigator.vibrate(ok ? 60 : [40, 60, 40]); } catch (_) { /* not allowed */ } }
  if (REDUCE) return;
  const d = document.createElement("div");
  d.className = `flash-wash ${ok ? "ok" : "no"}`;
  document.body.appendChild(d);
  d.animate([{ opacity: .85 }, { opacity: 0 }], { duration: 700, easing: "ease-out" }).onfinish = () => d.remove();
}

/* Lightweight confetti for the winner. */
function confetti(ms = 3200) {
  if (REDUCE) return;
  const cv = document.createElement("canvas");
  cv.className = "confetti";
  document.body.appendChild(cv);
  const ctx = cv.getContext("2d");
  const W = cv.width = innerWidth * devicePixelRatio, H = cv.height = innerHeight * devicePixelRatio;
  const colors = ["#f2c14e", "#ffffff", "#4a7bb7", "#a6f0c4", "#ff9aa2"];
  const bits = Array.from({ length: 140 }, () => ({
    x: Math.random() * W, y: -Math.random() * H * .6, r: (4 + Math.random() * 6) * devicePixelRatio,
    vx: (Math.random() - .5) * 3 * devicePixelRatio, vy: (2 + Math.random() * 4) * devicePixelRatio,
    a: Math.random() * 6.28, va: (Math.random() - .5) * .3, c: colors[(Math.random() * colors.length) | 0] }));
  const t0 = performance.now();
  (function draw(t) {
    ctx.clearRect(0, 0, W, H);
    const fade = Math.max(0, 1 - Math.max(0, t - t0 - ms * .6) / (ms * .4));
    bits.forEach(b => {
      b.x += b.vx; b.y += b.vy; b.a += b.va; b.vy += .04 * devicePixelRatio;
      ctx.save(); ctx.globalAlpha = fade; ctx.translate(b.x, b.y); ctx.rotate(b.a);
      ctx.fillStyle = b.c; ctx.fillRect(-b.r / 2, -b.r / 4, b.r, b.r / 2); ctx.restore();
    });
    if (t - t0 < ms) requestAnimationFrame(draw); else cv.remove();
  })(t0);
}
