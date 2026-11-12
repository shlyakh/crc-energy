// Hail days per year, four sources compared on the same cells (one source / swipe / ratio), moved from site/app.js.
// Settled by the redesign plan: one source opens on its own range, swipe on the shared scale, ratio on radar ÷ reports.
import { $, state, api, esc, H3HexagonLayer, fetchJSON, quantile, fmt, fmtTick, ramp, colorAt, gradient, rgbCss, NODATA, compareLayerOf, kv, openDetail, latLon, ticksBetween } from "./core.js";

export async function loadCompare(l) {
  if (state.cmp) return state.cmp;
  const data = await fetchJSON(l.file);
  const lon = data.cells.map((c) => globalThis.h3.cellToLatLng(c)[1]);
  const ids = Object.keys(data.sources);
  const q = (arr, p) => quantile([...arr].sort((x, y) => x - y), p);
  const own = Object.fromEntries(ids.map((k) => [k, q(data.sources[k].values, 0.98) || 1]));
  const shared = q(ids.flatMap((k) => data.sources[k].values), 0.98) || 1;
  const d = l.defaults || {}; const has = (k, alt) => (ids.includes(k) ? k : alt);
  state.cmp = { data, lon, ids, own, shared, mode: "single", a: d.a || ids[0], b: d.b || ids[1], ra: has("mrms", ids[0]), rb: has("reports", ids[1]), ownScale: true, split: 0.5 };
  return state.cmp;
}
// The two sources in play: the ratio view keeps its own pair, so it opens on radar ÷ reports whatever the other views show.
const pair = (c) => (c.mode === "ratio" ? [c.ra, c.rb] : [c.a, c.b]);
export function setCompare(patch) {
  const c = state.cmp; if (!c) return;
  if (patch.mode && patch.mode !== c.mode) { c.mode = patch.mode; if (c.mode === "single") c.ownScale = true; if (c.mode === "swipe") c.ownScale = false; }
  const [ka, kb] = c.mode === "ratio" ? ["ra", "rb"] : ["a", "b"];
  if (patch.a) c[ka] = patch.a; if (patch.b) c[kb] = patch.b;
  if (patch.ownScale !== undefined) c.ownScale = patch.ownScale; if (patch.split !== undefined) c.split = patch.split;
  return api.render();
}
function divergingAt(dv, t) { // t in [-1, 1]; neutral midpoint, one hue per side
  const to = t < 0 ? dv.low : dv.high; const f = Math.min(1, Math.abs(t));
  return [dv.mid[0] + (to[0] - dv.mid[0]) * f, dv.mid[1] + (to[1] - dv.mid[1]) * f, dv.mid[2] + (to[2] - dv.mid[2]) * f, 225];
}
const RATIO_SPAN = 4; // log2: colours saturate at 16 times either way
function splitLon() { const r = $("map").getBoundingClientRect(); return state.map.unproject([state.cmp.split * r.width, r.height / 2]).lng; }
export function compareLayer(l) {
  const c = state.cmp; const { data } = c; const stops = ramp(l.style); const [a, b] = pair(c); const A = data.sources[a].values, B = data.sources[b].values;
  const top = (k) => (c.ownScale ? c.own[k] : c.shared);
  let color; let trigger;
  if (c.mode === "ratio") {
    color = (i) => (A[i] > 0 && B[i] > 0 ? divergingAt(l.style.diverging, Math.log2(A[i] / B[i]) / RATIO_SPAN) : NODATA);
    trigger = ["ratio", a, b];
  } else if (c.mode === "swipe") {
    const x = splitLon();
    color = (i) => (c.lon[i] < x ? colorAt(stops, A[i] / top(a)) : colorAt(stops, B[i] / top(b)));
    trigger = ["swipe", a, b, c.ownScale, x];
  } else {
    color = (i) => colorAt(stops, A[i] / top(a));
    trigger = ["single", a, c.ownScale];
  }
  return new H3HexagonLayer({
    id: "cmp", data: data.cells.map((_, i) => i), getHexagon: (i) => data.cells[i], getFillColor: color,
    filled: true, stroked: false, extruded: false, highPrecision: false, pickable: true, opacity: 1,
    updateTriggers: { getFillColor: trigger },
    onClick: (info) => { showCompareCell(l, info.index); api.drawFrame(); return true; },
  });
}
export function compareHover(i) {
  const c = state.cmp; const s = c.data.sources; const [a, b] = pair(c);
  const lines = c.ids.map((k) => `<tr class="${k === a || (c.mode !== "single" && k === b) ? "on" : ""}"><td class="num">${fmt(s[k].values[i])}</td><td>${esc(s[k].title)}</td></tr>`).join("");
  const ratio = c.mode === "ratio" && s[a].values[i] > 0 && s[b].values[i] > 0 ? `<br>ratio ${fmt(s[a].values[i] / s[b].values[i])} ×` : "";
  return `<b>${esc(c.data.unit)}</b>${ratio}<table>${lines}</table><span>cell ${c.data.cells[i]}</span>`;
}
export function compareLegend(l) {
  const c = state.cmp; const s = c.data.sources; const [a, b] = pair(c); const stops = ramp(l.style);
  if (c.mode === "ratio") {
    const dv = l.style.diverging;
    const both = c.data.cells.filter((_, i) => s[a].values[i] > 0 && s[b].values[i] > 0).length;
    return {
      title: `${s[a].title} ÷ ${s[b].title}`, unit: "ratio of hail days per year (×), log scale",
      ramps: [{ css: `linear-gradient(90deg, ${rgbCss(dv.low)}, ${rgbCss(dv.mid)}, ${rgbCss(dv.high)})`, ticks: ["≤ 1/16", "1/4", "1", "4", "≥ 16"] }],
      rows: [{ color: rgbCss(NODATA), shape: "box", label: "no value in one of the two", n: c.data.cells.length - both }],
      foot: `${both.toLocaleString("en-US")} cells have a value in both. Periods: ${s[a].period} and ${s[b].period}.`,
    };
  }
  const top = (k) => (c.ownScale ? c.own[k] : c.shared);
  const ticks = (k) => ticksBetween(0, top(k)).map((v, i, all) => (i === all.length - 1 ? `≥ ${fmtTick(v)}` : fmtTick(v)));
  const note = c.ownScale ? "Each source is scaled to its own 98th percentile: read the pattern, not the level." : "One scale for all four sources (98th percentile of all values), so levels can be compared.";
  if (c.mode === "swipe") {
    return {
      title: "Left and right of the line", unit: c.data.unit,
      ramps: c.ownScale ? [{ label: `Left: ${s[a].title}`, css: gradient(stops), ticks: ticks(a) }, { label: `Right: ${s[b].title}`, css: gradient(stops), ticks: ticks(b) }] : [{ css: gradient(stops), ticks: ticks(a) }],
      foot: `Left ${s[a].title} (${s[a].period}); right ${s[b].title} (${s[b].period}). ${note}`,
    };
  }
  return { title: s[a].title, unit: `${c.data.unit} · ${s[a].period}`, ramps: [{ css: gradient(stops), ticks: ticks(a) }], foot: note };
}
export function buildCompareControls() {
  const l = compareLayerOf(state.source); const c = state.cmp; if (!c) return; const s = c.data.sources; const [a, b] = pair(c);
  for (const id of ["cmp-a", "cmp-b"]) { const sel = $(id); sel.innerHTML = ""; for (const k of c.ids) sel.append(new Option(`${s[k].title} (${s[k].period})`, k)); }
  for (const btn of document.querySelectorAll("#cmp-mode button")) btn.setAttribute("aria-checked", String(btn.dataset.mode === c.mode));
  $("cmp-a").value = a; $("cmp-b").value = b; $("cmp-own").checked = c.ownScale;
  $("cmp-b-label").classList.toggle("hidden", c.mode === "single"); $("cmp-own-label").classList.toggle("hidden", c.mode === "ratio");
  $("cmp-preset").classList.toggle("hidden", c.mode !== "ratio");
  for (const btn of document.querySelectorAll("#cmp-preset button")) btn.setAttribute("aria-checked", String(c.ra === "mrms" && c.rb === btn.dataset.b));
  $("cmp-a-label").firstElementChild.textContent = c.mode === "ratio" ? "Numerator" : c.mode === "swipe" ? "Left of the line" : "Source";
  $("cmp-b-label").firstElementChild.textContent = c.mode === "ratio" ? "Denominator" : "Right of the line";
  const med = (k) => quantile([...s[k].values].sort((x, y) => x - y), 0.5);
  $("cmp-summary").innerHTML = `<table class="tbl"><tr><th>Source</th><th>Period</th><th class="num">Median cell</th></tr>` + c.ids.map((k) => `<tr><td><span class="sw" style="background:${rgbCss(l.style.series[k])}"></span>${esc(s[k].title)}</td><td class="num">${esc(s[k].period)}</td><td class="num">${fmt(med(k))}</td></tr>`).join("") + `</table>`;
  drawSignatureYears(l);
}
function drawSignatureYears(l) {
  const yrs = state.cmp.data.signatures_per_year || []; const box = $("cmp-years"); if (!yrs.length) { box.innerHTML = ""; return; }
  const W = 290, H = 96, m = { l: 34, r: 4, t: 16, b: 18 }; const max = Math.max(...yrs.map((y) => y.rows_ge_threshold)) || 1;
  const bw = (W - m.l - m.r) / yrs.length; const col = rgbCss(l.style.series.signatures);
  const y = (v) => m.t + (1 - v / max) * (H - m.t - m.b);
  const parts = [`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Radar hail signatures per year"><text x="0" y="10" font-size="10.5" fill="#0b0b0b" font-weight="600">Radar hail signatures of 1.25 in or more, per year</text>`];
  for (const t of [0, max / 2, max]) parts.push(`<line x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}" stroke="#e1e0d9"/><text x="${m.l - 4}" y="${y(t) + 3}" text-anchor="end" font-size="9" fill="#52514e">${t >= 1000 ? `${Math.round(t / 1000)}k` : Math.round(t)}</text>`);
  yrs.forEach((d, i) => { const h = H - m.b - y(d.rows_ge_threshold); parts.push(`<rect x="${(m.l + i * bw + 1).toFixed(1)}" y="${y(d.rows_ge_threshold).toFixed(1)}" width="${Math.max(1, bw - 2).toFixed(1)}" height="${Math.max(0, h).toFixed(1)}" fill="${col}"><title>${d.year}: ${d.rows_ge_threshold.toLocaleString("en-US")} signatures, ${d.radars} radars</title></rect>`); if (d.year % 5 === 0) parts.push(`<text x="${(m.l + i * bw + bw / 2).toFixed(1)}" y="${H - 5}" text-anchor="middle" font-size="9" fill="#52514e">${d.year}</text>`); });
  parts.push(`</svg><div class="mute small">The swings are partly weather and partly the record itself: missing values in the first years, and changes in the radar network and algorithm.</div>`);
  box.innerHTML = parts.join("");
}
export function showCompareCell(l, i) {
  const c = state.cmp; const s = c.data.sources; state.selected = null;
  state.pick = { kind: "cell", cell: c.data.cells[i], key: `cmp:${i}` };
  const centre = globalThis.h3.cellToLatLng(c.data.cells[i]); const rate = c.data.reporting_rate[i];
  openDetail("Hail days per year in this cell", "Four sources on the same cell");
  $("detail-meta").innerHTML = kv([["Cell", `${c.data.cells[i]} <small>H3 r${c.data.h3_resolution}</small>`], ["Centre", latLon(centre[0], centre[1])], ["Fitted reporting rate", rate === null || Number.isNaN(rate) ? "–" : `${(100 * rate).toFixed(0)}% <small>of hail days reported (model)</small>`]], true);
  delete $("detail-meta").dataset.groups;
  const vals = c.ids.map((k) => s[k].values[i]); const max = Math.max(...vals, 0.001);
  const W = 348, row = 34, left = 2, barMax = W - 64; const parts = [`<svg viewBox="0 0 ${W} ${c.ids.length * row + 6}" role="img" aria-label="Hail days per year by source">`];
  c.ids.forEach((k, j) => { const y = j * row; const w = (vals[j] / max) * barMax; parts.push(`<text x="${left}" y="${y + 12}" font-size="11.5" fill="#0b0b0b">${esc(s[k].title)} · ${esc(s[k].period)}</text><rect class="bar" data-k="${k}" x="${left}" y="${y + 17}" width="${Math.max(1, w).toFixed(1)}" height="11" fill="${rgbCss(l.style.series[k])}"/><text x="${(left + Math.max(1, w) + 6).toFixed(1)}" y="${y + 27}" font-size="11.5" fill="#0b0b0b">${fmt(vals[j])}</text>`); });
  parts.push("</svg>");
  $("chart").innerHTML = `<div class="bars">${parts.join("")}</div>`;
  $("detail-table").innerHTML = `<tr><th style="width:52%">Source</th><th>Period</th><th class="num">${esc(c.data.unit)}</th></tr>` + c.ids.map((k, j) => `<tr><td>${esc(s[k].title)}</td><td class="num">${esc(s[k].period)}</td><td class="num">${fmt(vals[j])}</td></tr>`).join("");
  $("detail-params").innerHTML = ""; $("detail-foot").textContent = c.data.notes || l.caveat || "";
}
export function placeSwipe() {
  const on = !!(state.cmp && compareLayerOf(state.source) && state.cmp.mode === "swipe"); const el = $("swipe"); el.classList.toggle("hidden", !on);
  if (!on) return; const s = state.cmp.data.sources;
  el.style.left = `${(state.cmp.split * 100).toFixed(2)}%`; $("swipe-a").textContent = `◀ ${s[state.cmp.a].title}`; $("swipe-b").textContent = `${s[state.cmp.b].title} ▶`;
  document.body.dataset.split = state.cmp.split.toFixed(3);
}
function refreshCompareLayer() { // re-colour only the comparison layer (swipe drag, map move)
  const l = compareLayerOf(state.source); if (!l || !state.cmp) return;
  state.baseLayers = state.baseLayers.map((x) => (x.id === "cmp" ? compareLayer(l) : x)); api.drawFrame(); placeSwipe();
}
export function wireCompare() {
  for (const btn of document.querySelectorAll("#cmp-mode button")) btn.onclick = () => setCompare({ mode: btn.dataset.mode });
  for (const btn of document.querySelectorAll("#cmp-preset button")) btn.onclick = () => setCompare({ a: "mrms", b: btn.dataset.b });
  $("cmp-a").onchange = (e) => setCompare({ a: e.target.value });
  $("cmp-b").onchange = (e) => setCompare({ b: e.target.value });
  $("cmp-own").onchange = (e) => setCompare({ ownScale: e.target.checked });
  const el = $("swipe"); let drag = false;
  el.addEventListener("pointerdown", (e) => { drag = true; el.setPointerCapture(e.pointerId); e.preventDefault(); e.stopPropagation(); });
  el.addEventListener("pointermove", (e) => { if (!drag) return; const r = $("map").getBoundingClientRect(); state.cmp.split = Math.min(0.97, Math.max(0.03, (e.clientX - r.left) / r.width)); refreshCompareLayer(); });
  el.addEventListener("pointerup", () => { drag = false; });
  document.addEventListener("crc:swipe", (e) => { if (state.cmp) { state.cmp.split = e.detail; refreshCompareLayer(); } });
  const moved = () => { if (state.cmp && state.cmp.mode === "swipe" && compareLayerOf(state.source)) refreshCompareLayer(); };
  state.map.on("move", moved); state.map.on("resize", moved);
}
