// Methods (hail project): a reading page built from the same files the maps use.
// Curves are shipped as values by src/crc_lab/risk_layer.py; the sliders pick among them.
import { esc, fmtUSD, fmtInt } from "../shared/util.js";
import { lineChart } from "./charts.js";

const GH = "https://github.com/shlyakh/crc-lab/blob/main/";
const json = (url) => fetch(url).then((r) => { if (!r.ok) throw new Error(`${url.split("/").pop()} ${r.status}`); return r.json(); });
const done = new Set();
const ph = '<span class="pill ph">placeholder</span>';

export async function showMethods(el, dataUrl) {
  if (done.has(el.id)) return;
  const root = dataUrl.replace(/data\/?$/, "");
  const [plants, curves, registry] = await Promise.all([json(`${dataUrl}assets/plants.json`), json(`${dataUrl}assets/curves.json`), json(`${root}layers.json`)]);
  const t = plants.totals, rule = plants.rule, d = curves.solar.defaults;
  const big = plants.plants.filter((p) => p.mw >= 20), sum = (f) => big.reduce((a, p) => a + (p[f] ?? 0), 0);
  const hail = registry.sources.filter((s) => s.origin === "crc-lab");
  el.innerHTML = `<div class="doc-in">
    <h2>Methods</h2>
    <p class="lead">How the hail-loss figures on the Risk tab are produced, what they rest on, and where they are weak.</p>
    <div class="tiles">
      <div class="tile"><b>${t.plants}</b><span>Texas solar plants in the EIA list (${big.length} of 20 MW or more)</span></div>
      <div class="tile"><b>${fmtUSD(t.value)}</b><span>replacement value at benchmark cost</span></div>
      <div class="tile"><b>${fmtUSD(t.loss_usd)}</b><span>expected hail loss a year, reports as they are</span></div>
      <div class="tile"><b>${fmtUSD(t.loss_usd_c)}</b><span>bias-corrected per cell (${fmtUSD(t.loss_usd_r)} per region)</span></div>
    </div>
    <p><b>These are first-approximation numbers.</b> The damage curve is a version-0 curve from laboratory data. Four inputs have no source and are placeholders: the stow angle (${d.stow_tilt_deg}°), the chance that a tracker is stowed when hail arrives (${d.p_stow}), the modules' share of plant value (${d.module_cost_share}) and the area hit per hail report (${rule.footprint_km2} km²). Read the results as orders of magnitude and as a ranking, not as prices.</p>

    <h3>From hail reports to loss at a plant</h3>
    <div class="flow">
      <div class="box"><b>Hail reports</b>Located reports with a size, ${esc(plants.periods.reports)}, Texas and its four neighbouring states (NOAA Storm Events).</div>
      <div class="box"><b>Report circle</b>Around the plant, grown until it holds ${rule.n_target} reports; never under ${rule.min_radius_km} km or over ${rule.max_radius_km} km; clipped to where reports can exist.</div>
      <div class="box"><b>Events at the plant</b>Each report stands for hail of its size over <span class="ph">${rule.footprint_km2} km²</span>. The plant is a disc of its array area. Rate = reports ÷ circle area ÷ years.</div>
      <div class="box"><b>Damage per event</b>The solar curve turns hail size into a share of plant value lost, with the plant's glass type and mounting; scaled by the share of the plant covered.</div>
      <div class="box"><b>A year</b>Events arrive at random. A year's damage shares are added and capped at full loss. Times plant value = expected loss per year.</div>
    </div>
    <div class="flow-side"><b>Bias-corrected variants.</b> Reports are sparse where few people live. A model gives every cell a reporting rate from population and roads. <b>Per cell:</b> the rate at step 3 is divided by the mean reporting rate of the cells in the plant's circle. <b>Per region:</b> the circle is dropped; the rate is the reports in the plant's model region (about 12,000 km²) ÷ (years × sum of reporting rate × cell area), and the region's report sizes are pooled. Per region is steadier but blurs differences inside a region. Hail sizes are not changed by either. All three figures are always shown; plants whose per-cell factor is above ${plants.factor_warning_above} are marked.</div>
    <p>One consequence, checked in the build for every plant: expected damage does not depend on the plant's size. A larger plant is hit more often, but each hit covers a smaller share of it.</p>
    <p>Plant value is capacity × a national benchmark cost per kW (NREL ATB), not the plant's own cost or insured value. Plants under 20 MW (${t.plants - big.length} of ${t.plants}, mostly rooftop and parking arrays) are hidden on the Risk tab by default; the ${big.length} larger plants carry ${fmtUSD(sum("loss_usd"))} of the ${fmtUSD(t.loss_usd)}.</p>

    <h3>Damage curves (version 0)</h3>
    <p>Four curves map hail diameter to a damage ratio. They are drawn here from the same parameter file the calculation uses (schema ${esc(curves.schema)}, as of ${esc(curves.as_of)}). Only the solar curve feeds the Risk tab; buildings and cars have no asset set yet.</p>
    <h4>Solar plant</h4>
    <p>Module glass breakage from the Kiwa PVEL hail stress test, a stow adjustment (a tilted module takes less normal impact energy), and the modules' share of plant value. Move the sliders to see how the two stow placeholders move the curve.</p>
    <div class="ctl">
      <label>Glass <select id="m-glass"><option value="glass_glass_2.0">2.0 mm glass-glass (plants from 2021)</option><option value="glass_backsheet_3.2">3.2 mm glass, backsheet (older plants)</option></select></label>
      <label>Stow angle ${ph} <input id="m-tilt" type="range" min="0" max="${curves.solar.stow_tilts_deg.length - 1}" step="1"> <output id="m-tilt-o"></output></label>
      <label>Chance stowed ${ph} <input id="m-p" type="range" min="0" max="${curves.solar.stow_chances.length - 1}" step="1"> <output id="m-p-o"></output></label>
      <button id="m-reset" class="btn" style="margin-left:0">Defaults</button>
    </div>
    <div id="m-solar"></div>
    <p class="meta"><b>Measured on:</b> ${esc(curves.solar.meta.native_metric)}. <b>Source:</b> ${esc(curves.solar.meta.source)}. <b>Confidence:</b> ${esc(curves.solar.meta.confidence)}. The curve tops out at the module cost share, ${d.module_cost_share} ${ph}.</p>
    <p>Direction of error: the lab fires stones of the stated size at every module, while a report gives the largest stone, so unstowed damage is likely too high. For stowed modules field evidence conflicts.</p>
    <h4>Buildings and cars</h4>
    <p>Two building curves bracket the answer: Swiss insurance claims (low: averaged over every building in a radar cell) and a roof curve from engineering thresholds (high: assumes the hail fell on the roof). They differ by a factor of about 250 at 2 inches; note the different vertical scales.</p>
    <div class="grid3"><div id="m-bld-swiss"></div><div id="m-bld-roof"></div><div id="m-car"></div></div>
    <p class="meta"><b>Sources:</b> ${esc(curves.buildings.swiss.meta.source)}; ${esc(curves.buildings.roof.meta.source)}. Roof cost share ${curves.buildings.roof.defaults.roof_cost_share} and the roof curve's spread are placeholders. The Swiss curves were calibrated on radar hail size, not observed size, and are fed observed sizes here.</p>

    <h3>Hail records used</h3>
    <table class="plain"><thead><tr><th>Record</th><th>What it is</th><th>Licence</th></tr></thead><tbody>
      ${hail.map((s) => `<tr><td>${esc(s.title)}</td><td>${esc(s.short || s.returns || "")}</td><td>${esc(s.licence || "")}</td></tr>`).join("")}
    </tbody></table>
    <p>The Hail evidence tab shows each of them on the map. Storm reports say where people saw hail; radar says where hail probably fell. Radar sees about ten times more hail days than reports in the median cell.</p>

    <h3>Known limits</h3>
    <ul>
      <li>Report-based rates follow where people live and drive. The correction is a first model; its largest factors are its least certain.</li>
      <li>A report's size is assumed over its whole footprint; report sizes cluster at reference objects (1, 1.75, 2.75 inches).</li>
      <li>Glass type is set by the year the plant came online; no source lists the modules. Thin-film plants follow the same rule for lack of a table.</li>
      <li>No loss is computed from radar hail size: the curves are keyed to observed size, and the two must not be mixed.</li>
      <li>Cell-level values (about 253 km²) are regional screening, not site assessments.</li>
    </ul>

    <h3>Read more</h3>
    <ul>
      <li><a href="${GH}docs/reports/5-hail-impact.md">Phase 5 report: hail impact functions and loss per plant</a></li>
      <li><a href="${GH}docs/requirements-hail-impact-v0.md">The curve specification, with a source tag on every number</a></li>
      <li><a href="${GH}docs/hail-data-processing.md">How hail data is processed</a> · <a href="${GH}docs/decisions.md">Decisions and their effect, with charts</a></li>
      <li><a href="${GH}docs/reports/5-reporting-bias.md">The reporting-bias model</a> · <a href="${GH}docs/reports/4-radar-hail.md">Radar hail</a> · <a href="${GH}docs/data-sources.md">Data source catalog</a></li>
    </ul>
    <div id="m-video"></div>
  </div>`;

  const S = curves.solar, xs = curves.d_mm, $ = (id) => el.querySelector(`#${id}`);
  const reset = () => { $("m-glass").value = d.glass_class; $("m-tilt").value = S.stow_tilts_deg.indexOf(d.stow_tilt_deg); $("m-p").value = S.stow_chances.indexOf(d.p_stow); draw(); };
  const key = (tilt, p) => `${tilt}|${p}`;
  function draw() {
    const glass = $("m-glass").value, tilt = S.stow_tilts_deg[+$("m-tilt").value], p = S.stow_chances[+$("m-p").value];
    $("m-tilt-o").textContent = `${tilt}°`; $("m-p-o").textContent = p.toFixed(2);
    const set = S.plant[glass];
    lineChart($("m-solar"), { title: "Solar plant: share of plant value lost", sub: `if hail of this size covers the plant · stow ${tilt}°, stowed with chance ${p}`, xs, width: 720, height: 260,
      series: [{ label: "Selected settings", ys: set[key(tilt, p)], color: "var(--c3)", width: 2.5 }, { label: "Never stowed", ys: set[key(tilt, 0)], color: "var(--report)", width: 1.5, dash: "5 3" }, { label: `Always stowed at ${tilt}°`, ys: set[key(tilt, 1)], color: "var(--mute)", width: 1.5, dash: "2 3" }],
      marks: [{ x: 25.4, label: "1 in" }, { x: 50.8, label: "2 in" }, { x: 76.2, label: "3 in" }] });
    el.dataset.solarKey = `${glass}|${key(tilt, p)}`; el.dataset.solarAt2in = String(set[key(tilt, p)][xs.indexOf(50)]);
  }
  for (const id of ["m-glass", "m-tilt", "m-p"]) $(id).addEventListener("input", draw);
  $("m-reset").onclick = reset; reset();
  const B = curves.buildings;
  lineChart($("m-bld-swiss"), { title: "Buildings: Swiss claims curve", sub: "share of building value · lower bound", xs, width: 330, height: 200, digits: 2, series: [{ label: "Damage ratio", ys: B.swiss.damage_ratio, color: "var(--c3)" }] });
  lineChart($("m-bld-roof"), { title: "Buildings: roof curve", sub: "share of building value · upper bound", xs, width: 330, height: 200, digits: 0, series: [{ label: "Laminated shingle", ys: B.roof.asphalt_laminated, color: "var(--c3)" }, { label: "3-tab shingle", ys: B.roof.asphalt_3tab, color: "var(--report)", dash: "5 3" }] });
  lineChart($("m-car"), { title: "Cars: Swiss fleet curve", sub: "share of insured value · general fleet, not open lots", xs, width: 330, height: 200, digits: 2, series: [{ label: "Damage ratio", ys: curves.cars.swiss.damage_ratio, color: "var(--c3)" }] });
  $("m-video").innerHTML = `<h3>The tour, recorded</h3><p>The same tour as the Tour button at the top right, about 35 seconds.</p><video controls preload="none" src="${root}demo.webm"></video>`;
  done.add(el.id); document.body.dataset.methods = "1";
}
