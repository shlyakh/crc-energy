// The last part of the hail project's tour, played here because the storm player belongs to this page:
// Hurricane Beryl, July 2024, from the best-track record. body.dataset.demo is "running" then "done" (read by the recorder).
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const MS = 9500;

export async function runTour(app) {
  let stop = false; const bar = $("demo-bar"), t0 = performance.now();
  const caption = `<b>Texas CRC data.</b> An explorer of what crc-sdk already reaches. Here Hurricane Beryl, July 2024, replayed from the best-track record with its wind radii and the storm reports near its track.`;
  bar.classList.remove("hidden"); document.body.dataset.demo = "running";
  $("demo-step").textContent = "last part"; $("demo-caption").innerHTML = caption;
  $("demo-stop").onclick = () => { stop = true; };
  const onKey = (e) => { if (e.key === "Escape") stop = true; }; document.addEventListener("keydown", onKey);
  try {
    try {
      await app.showTab("crc");
      for (let i = 0; i < 60 && !document.body.dataset.sourcesReady; i++) await sleep(100);
      await sleep(300); document.querySelector('.src-row[data-id="ibtracs"]')?.click();
      const src = globalThis.__sources; for (let i = 0; i < 60 && !src.tracks; i++) await sleep(100);
      const beryl = src.tracks.storms.find((x) => x.name.toUpperCase() === "BERYL" && x.season === 2024); if (!beryl) throw new Error("Beryl 2024 is not in the track file");
      (await import("../../shared/views/tracks.js")).selectStorm(beryl);
      for (let i = 0; i < 60 && !(src.time && src.time.key === `storm:${beryl.sid}` && !$("timebar").classList.contains("hidden")); i++) await sleep(100);
      await sleep(600);
      // from the start of the player's window, at the fastest speed: about 87 hours in 7 seconds
      const speed = $("time-speed"); speed.value = "12"; speed.dispatchEvent(new Event("change"));
      const slider = $("time-slider"); slider.value = "0"; slider.dispatchEvent(new Event("input"));
      $("time-play").click();
    } catch (e) { $("demo-caption").innerHTML = `${caption} <span style="color:#c3c2b7">(this step could not be shown: ${String(e.message || e)})</span>`; document.body.dataset.demoError = String(e.message || e); }
    const start = performance.now();
    while (performance.now() - start < MS && !stop) { await sleep(50); $("demo-progress").style.width = `${Math.min(100, ((performance.now() - start) / MS) * 100)}%`; }
  } finally {
    document.removeEventListener("keydown", onKey); bar.classList.add("hidden"); $("demo-progress").style.width = "0";
    document.body.dataset.demoMs = String(Math.round(performance.now() - t0));
    if (document.body.dataset.playing) $("time-play")?.click();
    history.replaceState(null, "", location.pathname + location.hash); // drop ?demo=beryl so a reload does not replay
    document.body.dataset.demo = stop ? "stopped" : "done";
  }
}
