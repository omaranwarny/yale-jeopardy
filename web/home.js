"use strict";
$("#join").addEventListener("submit", (e) => {
  e.preventDefault();
  const code = $("#code").value.trim().toUpperCase();
  if (code.length >= 4) withBulldog(null, "Finding your game…").then(() => { location.href = `/play?code=${encodeURIComponent(code)}`; });
  else toast("Enter the code shown on the screen.");
});
