"use strict";
$("#print").addEventListener("click", (e) => { e.preventDefault(); print(); });
let E = null;
const DEFAULTS = { build_cost: 0.006, session_cost: 0.002, manual_minutes: 60, build_minutes: 8 };  // used only until real data exists
const stat = (k, v, l) => `<div class="stat ${k}"><b>${esc(v ?? "–")}</b>${l}</div>`;
const pct = (v) => v == null ? "–" : `${v}%`;

(async function () {
  try { E = await api("/api/evidence"); } catch (e) { $("#asof").textContent = e.message; return; }
  const b = E.boards, s = E.sessions, t = E.teacher_feedback, st = E.student_feedback;
  $("#asof").textContent = `As of ${new Date(E.generated_at * 1000).toLocaleString()}: ${b.built} board(s) built from real course material, ${s.run} class session(s), ${s.students} student seat(s), ${t.responses} teacher response(s).`;
  $("#e-build").innerHTML = stat("good", b.median_build_minutes == null ? "–" : `${b.median_build_minutes} min`, "median time to build (open → approve)") +
    stat("", t.median_manual_minutes == null ? "–" : `${t.median_manual_minutes} min`, "teachers' estimate by hand") +
    stat("", b.approved, "boards approved for class") +
    stat("", b.median_cost_usd == null ? "–" : `$${b.median_cost_usd.toFixed(4)}`, "median AI cost per board");
  const saved = b.median_build_minutes != null && t.median_manual_minutes != null ? t.median_manual_minutes - b.median_build_minutes : null;
  $("#e-build-note").textContent = saved != null ? `≈ ${Math.round(saved)} minutes saved per review game (median teacher estimate minus measured build time).` : "Time saved appears once teachers have built a board and sent feedback.";
  $("#e-quality").innerHTML = stat("", b.clues_generated, "clues drafted") + stat("bad", b.rejected_by_code, "rejected by code (quote not in material, giveaways…)") +
    stat("bad", b.rejected_by_verifier, "rejected by the checker agent") + stat("warn", b.flagged_for_teacher, "flagged for the teacher") +
    stat("good", pct(b.pct_kept_without_edits), "of final clues kept without edits") + stat("", b.hidden_text_removed, "hidden text items removed from files") +
    stat("", t.median_accuracy == null ? "–" : `${t.median_accuracy}/5`, "teacher-rated accuracy");
  $("#e-class").innerHTML = stat("good", s.students, "student seats") + stat("", s.clues_played, "clues played") +
    stat("", pct(s.median_avg_pct_correct), "median class accuracy") + stat("warn", s.overrides, "teacher overrides of the judge") +
    stat("", s.median_minutes == null ? "–" : `${s.median_minutes} min`, "median game length") +
    stat("", s.median_cost_usd == null ? "–" : `$${s.median_cost_usd.toFixed(4)}`, "median AI cost per game");
  $("#e-reteach").innerHTML = s.reteach_examples.map(x => `<li><span class="pct">${x.pct_correct}%</span><b>${esc(x.title)}</b> · ${esc(x.category)}: ${esc(x.clue)} <i>(${esc(x.answer)})</i></li>`).join("");
  $("#e-fb").innerHTML = stat("", t.median_usefulness == null ? "–" : `${t.median_usefulness}/5`, "teacher usefulness") +
    stat("good", `${t.use_again.yes}/${t.responses}`, "would use again") + stat("", `${t.reteach_matches.yes + t.reteach_matches.partly}/${t.responses}`, "reteach list matched (yes/partly)") +
    stat("", st.median_helped == null ? "–" : `${st.median_helped}/5`, `students: helped me review (${st.responses})`);
  $("#e-comments").innerHTML = t.comments.map(c => `<div class="quote" style="margin:8px 0">“${esc(c.text)}”<small>${esc(c.role || "Teacher")}</small></div>`).join("");
  project();
})();

function project() {
  if (!E) return;
  const courses = +$("#p-courses").value || 0, games = +$("#p-games").value || 0, students = +$("#p-students").value || 0, rate = +$("#p-rate").value || 0;
  const m = (v, d) => (v == null ? [d, true] : [v, false]);
  const [bc, bcA] = m(E.boards.median_cost_usd, DEFAULTS.build_cost);
  const [sc, scA] = m(E.sessions.median_cost_usd, DEFAULTS.session_cost);
  const [mm, mmA] = m(E.teacher_feedback.median_manual_minutes, DEFAULTS.manual_minutes);
  const [bm, bmA] = m(E.boards.median_build_minutes, DEFAULTS.build_minutes);
  const perYear = courses * games * 2;                       // two semesters
  const ai = perYear * (bc + sc);
  const hours = perYear * Math.max(0, mm - bm) / 60;
  const star = (a) => (a ? "*" : "");
  $("#p-out").innerHTML = stat("", perYear.toLocaleString(), "review games / year") +
    stat("", (perYear * students).toLocaleString(), "student plays / year") +
    stat("good", `$${ai.toFixed(2)}${star(bcA || scA)}`, "AI cost / year") +
    stat("good", `${Math.round(hours).toLocaleString()} h${star(mmA || bmA)}`, "teacher hours saved / year") +
    stat("", `$${Math.round(hours * rate).toLocaleString()}`, "value of that time");
  $("#p-note").textContent = [bcA && `*build cost assumed $${DEFAULTS.build_cost}`, scA && `*game cost assumed $${DEFAULTS.session_cost}`,
    mmA && `*by-hand time assumed ${DEFAULTS.manual_minutes} min`, bmA && `*build time assumed ${DEFAULTS.build_minutes} min`].filter(Boolean).join(" · ")
    || "All inputs measured in this trial.";
}
$$(".opts input").forEach(i => i.addEventListener("input", project));
