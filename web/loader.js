/* Bulldog loader: an original cartoon bulldog runs along a progress bar.
   withBulldog(work, text) shows it for at least MIN_MS (or as long as `work` takes) and resolves with work's result.
   Self-contained (its own CSS), so any page can use it. Honors "reduce motion". */
"use strict";
(function () {
  const MIN_MS = 2000;
  const css = `
  .bd-wrap{position:fixed;inset:0;z-index:200;display:grid;place-items:center;background:radial-gradient(1000px 600px at 50% 30%,#0b4c95,#00356b 55%,#001d3d);
    opacity:0;transition:opacity .2s}
  .bd-wrap.on{opacity:1}
  .bd-box{width:min(560px,88vw);text-align:center;color:#fff;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
  .bd-track{position:relative;height:104px;margin-bottom:6px}
  .bd-dog{position:absolute;bottom:0;left:0;width:140px;height:94px;transform:translateX(-10px);will-change:transform}
  .bd-bar{height:10px;border-radius:99px;background:rgba(255,255,255,.14);overflow:hidden;box-shadow:inset 0 1px 2px rgba(0,0,0,.4)}
  .bd-fill{height:100%;width:0;border-radius:99px;background:linear-gradient(90deg,#f2c14e,#ffe08a)}
  .bd-txt{margin-top:16px;font:600 17px/1.4 "Iowan Old Style","Palatino Linotype",Georgia,serif;letter-spacing:.01em;color:#e8eef6}
  .bd-txt small{display:block;margin-top:4px;font:600 11px/1 -apple-system,Arial,sans-serif;letter-spacing:.18em;text-transform:uppercase;color:#f2c14e}
  .bd-body{animation:bd-bob .32s ease-in-out infinite alternate}
  .bd-legA{transform-box:fill-box;transform-origin:50% 0;animation:bd-leg .32s ease-in-out infinite alternate}
  .bd-legB{transform-box:fill-box;transform-origin:50% 0;animation:bd-leg .32s ease-in-out infinite alternate-reverse}
  .bd-ear{transform-box:fill-box;transform-origin:30% 90%;animation:bd-ear .32s ease-in-out infinite alternate}
  .bd-tail{transform-box:fill-box;transform-origin:0% 100%;animation:bd-tail .16s linear infinite alternate}
  .bd-dust{animation:bd-dust .64s linear infinite;opacity:.0}
  @keyframes bd-bob{from{transform:translateY(0)}to{transform:translateY(-4px)}}
  @keyframes bd-leg{from{transform:rotate(32deg)}to{transform:rotate(-32deg)}}
  @keyframes bd-ear{from{transform:rotate(-8deg)}to{transform:rotate(10deg)}}
  @keyframes bd-tail{from{transform:rotate(-20deg)}to{transform:rotate(25deg)}}
  @keyframes bd-dust{0%{opacity:.55;transform:translate(0,0) scale(.6)}100%{opacity:0;transform:translate(-26px,-6px) scale(1.4)}}
  @media (prefers-reduced-motion:reduce){.bd-body,.bd-legA,.bd-legB,.bd-ear,.bd-tail,.bd-dust{animation:none}}`;

  // Original bulldog drawing (side view, facing right): cream coat, Yale-blue collar, gold tag.
  const dog = `
  <svg class="bd-dog" viewBox="0 0 150 100" aria-hidden="true">
    <g class="bd-dust" fill="#cfdcec"><circle cx="8" cy="92" r="4"/><circle cx="16" cy="95" r="3"/></g>
    <!-- far legs (short, bowed) -->
    <g class="bd-legB" fill="#cbb89a"><rect x="34" y="66" width="14" height="22" rx="6"/><rect x="84" y="66" width="14" height="22" rx="6"/></g>
    <g class="bd-body">
      <path class="bd-tail" d="M22 52 q-8 -4 -7 -12" stroke="#e6d6b8" stroke-width="6" fill="none" stroke-linecap="round"/>
      <!-- barrel body: low, wide, deep chest -->
      <path d="M22 56 C22 38 44 32 68 34 C92 34 104 40 108 52 C112 70 96 80 66 80 C38 80 22 74 22 56Z" fill="#efe3cb"/>
      <path d="M70 76 C86 76 100 70 104 58 C100 70 86 74 70 74Z" fill="#d9c7a6"/>
      <ellipse cx="46" cy="48" rx="13" ry="9" fill="#b9946a" opacity=".55"/>
      <!-- big square head, set low and forward -->
      <g transform="translate(92 20)">
        <path class="bd-ear" d="M8 10 q-4 -10 6 -9 q3 4 1 10z" fill="#9c7b57"/>
        <path d="M2 22 C2 8 16 2 30 3 C44 4 52 12 52 26 C52 40 44 50 28 50 C12 50 2 40 2 22Z" fill="#efe3cb"/>
        <!-- brow wrinkles -->
        <path d="M18 13 q8 -4 16 0 M20 18 q7 -3 13 0" stroke="#a88d6a" stroke-width="1.8" fill="none" stroke-linecap="round"/>
        <!-- eye -->
        <circle cx="34" cy="21" r="4" fill="#fff"/><circle cx="35" cy="21.5" r="2.6" fill="#1c1a1a"/><circle cx="35.9" cy="20.5" r=".9" fill="#fff"/>
        <path d="M29 16.5 q5 -2.5 10 0.5" stroke="#6e5640" stroke-width="2" fill="none" stroke-linecap="round"/>
        <!-- flat, pushed-in muzzle + nose -->
        <path d="M38 24 C46 22 54 26 54 32 C54 38 46 40 40 38" fill="#fbf5ea"/>
        <ellipse cx="51" cy="27" rx="4.5" ry="3.5" fill="#2f2622"/>
        <!-- droopy jowls -->
        <path d="M30 36 C34 46 46 47 52 38 C50 44 40 50 32 46 C28 44 28 40 30 36Z" fill="#e2d1b2"/>
        <!-- underbite: lower jaw juts out with two little teeth -->
        <path d="M34 44 C40 48 48 47 53 41" stroke="#6e5640" stroke-width="2.2" fill="none" stroke-linecap="round"/>
        <path d="M45 44.5 l1.4 -3.6 l1.6 3.4z M50 42.6 l1 -3.4 l1.6 2.8z" fill="#fff" stroke="#6e5640" stroke-width=".6"/>
      </g>
      <!-- Yale-blue collar with a gold tag -->
      <path d="M90 38 q6 14 8 24" stroke="#00356b" stroke-width="7" fill="none" stroke-linecap="round"/>
      <circle cx="99" cy="64" r="4.5" fill="#f2c14e" stroke="#b8891f" stroke-width="1"/>
    </g>
    <!-- near legs -->
    <g class="bd-legA" fill="#e2d2b4"><rect x="26" y="66" width="15" height="23" rx="6.5"/><rect x="76" y="66" width="15" height="23" rx="6.5"/></g>
  </svg>`;

  let styled = false;
  function mount(text) {
    if (!styled) { const s = document.createElement("style"); s.textContent = css; document.head.appendChild(s); styled = true; }
    const w = document.createElement("div");
    w.className = "bd-wrap";
    w.setAttribute("role", "status");
    w.innerHTML = `<div class="bd-box"><div class="bd-track">${dog}</div><div class="bd-bar"><div class="bd-fill"></div></div>
      <div class="bd-txt">${text}<small>Lux et veritas</small></div></div>`;
    document.body.appendChild(w);
    requestAnimationFrame(() => w.classList.add("on"));
    return w;
  }

  /** Run `work` (a promise, a function returning one, or nothing) behind the loader for at least MIN_MS. */
  window.withBulldog = async function (work, text = "Fetching the board…") {
    const w = mount(text);
    const dogEl = w.querySelector(".bd-dog"), fill = w.querySelector(".bd-fill"), track = w.querySelector(".bd-track");
    const t0 = performance.now();
    let done = false, result, error;
    const p = Promise.resolve(typeof work === "function" ? work() : work)
      .then(r => { result = r; }, e => { error = e; }).finally(() => { done = true; });
    await new Promise(resolve => {
      (function frame(t) {
        const el = t - t0;
        // fill to 90% over MIN_MS, then creep while waiting, then race to 100% when the work is done
        let k = Math.min(.9, el / MIN_MS * .9);
        if (el > MIN_MS && !done) k = .9 + .08 * (1 - Math.exp(-(el - MIN_MS) / 4000));
        if (done && el >= MIN_MS) k = 1;
        fill.style.width = `${k * 100}%`;
        dogEl.style.transform = `translateX(${k * (track.clientWidth - dogEl.clientWidth)}px)`;
        if (k >= 1) return setTimeout(resolve, 180);
        requestAnimationFrame(frame);
      })(t0);
    });
    await p;
    w.classList.remove("on");
    setTimeout(() => w.remove(), 220);
    if (error) throw error;
    return result;
  };
})();
