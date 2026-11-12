// The tour: about 40 seconds through this project, then on to the data explorer for its last part. Driven through the shell's small API and the pages' own
// controls, so it shows what a visitor can do. body.dataset.demo is "running" then "done" (read by the recorder).
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let running = false, stop = false, handedOver = false;

export async function runDemo(app) {
  if (running) return; running = true; stop = false;
  const risk = globalThis.__risk, bar = $("demo-bar"), reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const big = risk.data.plants.filter((p) => p.mw >= 20);
  const top = [...big].sort((a, b) => b.loss_usd - a.loss_usd)[0];
  const jays = risk.data.plants.find((p) => p.name.includes("Fighting Jays")) || top;
  const usd = (v) => `$${(v / 1e6).toFixed(v >= 1e8 ? 0 : 1)} million`;
  const click = (sel) => document.querySelector(sel)?.click();
  const waitSources = async () => { for (let i = 0; i < 60 && !document.body.dataset.sourcesReady; i++) await sleep(100); await sleep(300); };
  const steps = [
    [3500, `<b>Hail risk at Texas solar plants.</b> ${big.length} plants of 20 MW or more, sized by capacity and coloured by expected hail loss as a share of value.`, async () => { await app.showTab("risk"); $("min-mw").value = "20"; $("min-mw").onchange(); app.setMeasure("loss_ratio"); app.setBasis(0); await app.selectPlant(null); $("reset-view").click(); }],
    [5000, `<b>${top.name}</b>, ${top.mw.toFixed(0)} MW: the largest expected loss, ${usd(top.loss_usd)} a year. Its report circle and the hail reports inside it are drawn on the map.`, async () => { app.setMeasure("loss_usd"); await app.selectPlant(top.id, { fly: true }); }],
    [4500, `<b>Corrected for where people report.</b> Reports are sparse in empty country. The correction lifts the portfolio from ${usd(risk.data.totals.loss_usd)} to ${usd(risk.data.totals.loss_usd_c)} a year.`, async () => { app.setBasis(1); }],
    [5000, `<b>${jays.name}.</b> Reports give it a small loss, yet radar saw ${jays.radar_max_mm} mm hail over it on ${jays.radar_max_day}. Reports miss hail.`, async () => { app.setBasis(0); await app.selectPlant(jays.id, { fly: true }); }],
    [5000, `<b>Hail evidence.</b> Radar hail days divided by reported hail days, cell by cell: where the two records disagree most, hail goes unreported.`, async () => { await app.selectPlant(null); await app.showTab("evidence"); await waitSources(); click('.src-row[data-id="hail_compare"]'); await sleep(900); click('#cmp-mode [data-mode="ratio"]'); }],
    [3500, `<b>Methods.</b> How a report becomes a loss, and the damage curves with their placeholder inputs marked.`, async () => { await app.showTab("methods"); await sleep(500); document.getElementById("m-solar")?.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" }); }],
    // The last part plays on the data explorer's page (../validation/explore/tour.js): Beryl 2024 in the storm player.
    [1800, `<b>Texas CRC data.</b> The tour ends in the data explorer, with Hurricane Beryl in the storm player.`, async () => { await sleep(1500); if (!stop) { handedOver = true; location.assign(`${app.explorer}?demo=beryl#tab=crc&source=ibtracs`); await sleep(5000); } }],
  ];
  const total = steps.reduce((a, s) => a + s[0], 0); let elapsed = 0;
  bar.classList.remove("hidden"); document.body.dataset.demo = "running"; const t0 = performance.now();
  $("demo-stop").onclick = () => { stop = true; };
  const onKey = (e) => { if (e.key === "Escape") stop = true; }; document.addEventListener("keydown", onKey);
  try {
    for (const [i, [ms, caption, act]] of steps.entries()) {
      if (stop) break;
      $("demo-step").textContent = `${i + 1} of ${steps.length}`; $("demo-caption").innerHTML = caption;
      try { await act(); } catch (e) { $("demo-caption").innerHTML = `${caption} <span style="color:#c3c2b7">(this step could not be shown: ${String(e.message || e)})</span>`; document.body.dataset.demoError = String(e.message || e); }
      const start = performance.now();
      while (performance.now() - start < ms && !stop) { await sleep(50); $("demo-progress").style.width = `${Math.min(100, ((elapsed + performance.now() - start) / total) * 100)}%`; }
      elapsed += ms;
    }
  } finally {
    document.removeEventListener("keydown", onKey); bar.classList.add("hidden"); $("demo-progress").style.width = "0";
    document.body.dataset.demoMs = String(Math.round(performance.now() - t0));
    if (document.body.dataset.playing) $("time-play")?.click();
    if (handedOver) return; // the explorer's page finishes the tour and sets body.dataset.demo there
    await app.showTab("risk"); $("reset-view").click(); running = false;
    document.body.dataset.demo = stop ? "stopped" : "done";
  }
}
