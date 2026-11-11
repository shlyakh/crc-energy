// H3 cell layers (CRC Open hazards, ERA5 baseline, hail and gust curves), moved from site/app.js.
import { $, state, api, esc, H3HexagonLayer, layerById, layersOfSource, fileKey, display, unitOf, fmt, fmtTick, quantile, fetchJSON, horizonsOf, ramp, colorAt, gradient, rgbCss, NODATA, kv, openDetail, latLon, ticksBetween } from "./core.js";
import { drawCurve } from "./charts.js";

export async function loadFile(hazard, horizon) {
  const key = fileKey(hazard, horizon);
  if (!state.files.has(key)) state.files.set(key, await fetchJSON(layerById(hazard).file.replace("{horizon}", horizon)));
  return state.files.get(key);
}
export function buildCellControls() {
  const { catalog } = state; const sel = $("hazard"); sel.innerHTML = "";
  const own = layersOfSource(state.source).filter((l) => l.kind === "h3-cells");
  if (state.source === "crc_open") {
    const loaded = own.map((l) => l.id);
    const g1 = document.createElement("optgroup"); g1.label = `Loaded (${loaded.length})`;
    for (const id of loaded) g1.append(new Option(`${layerById(id).title} · ${id}`, id));
    const rest = Object.keys(catalog.hazards).filter((h) => !loaded.includes(h));
    const g2 = document.createElement("optgroup"); g2.label = `In the release, not loaded yet (${rest.length})`;
    for (const id of rest) { const o = new Option(`${id} · ${catalog.hazards[id].value_semantics} (not loaded yet)`, id); o.disabled = true; g2.append(o); }
    sel.append(g1, g2);
  } else for (const l of own) sel.append(new Option(l.title, l.id));
  sel.value = state.hazard;
  const hz = $("horizon"); hz.innerHTML = "";
  for (const y of horizonsOf(layerById(state.hazard))) hz.append(new Option(String(y), y));
  hz.value = state.horizon;
  const rp = $("rp"); rp.innerHTML = "";
  for (const t of state.manifest.return_periods) rp.append(new Option(`1 in ${t} years`, t));
  rp.value = state.rp; $("lock").checked = state.locked;
}
function computeDomain(payload, rpIndex, layer) {
  const vals = payload.values.map((r) => r[rpIndex]).filter((v) => v !== null).map((v) => display(layer, v)).sort((a, b) => a - b);
  let lo = quantile(vals, 0.02), hi = quantile(vals, 0.98);
  if (!(hi > lo)) { lo = vals[0] ?? 0; hi = vals[vals.length - 1] ?? 1; if (!(hi > lo)) hi = lo + 1; }
  return [lo, hi, vals.length];
}
export function cellsLayer(layer, payload) {
  const rpIndex = state.manifest.return_periods.indexOf(state.rp);
  if (!state.locked || !state.domain) state.domain = computeDomain(payload, rpIndex, layer);
  const [lo, hi] = state.domain; const stops = ramp(layer.style);
  const color = (i) => { const v = payload.values[i][rpIndex]; return v === null ? NODATA : colorAt(stops, (display(layer, v) - lo) / (hi - lo)); };
  return new H3HexagonLayer({
    id: "cells", data: payload.values.map((_, i) => i), getHexagon: (i) => payload.cells[i], getFillColor: color,
    filled: true, stroked: false, extruded: false, highPrecision: false, pickable: true, opacity: 1,
    updateTriggers: { getFillColor: [state.hazard, state.horizon, state.rp, lo, hi], getHexagon: [state.hazard, state.horizon] },
    onClick: (info) => { showDetail(info.index); api.drawFrame(); return true; },
  });
}
// Legend for the map: the ramp with numeric ticks in the displayed unit, the period, and what grey means.
export function cellsLegend(layer, payload) {
  const [lo, hi, n] = state.domain; const stops = ramp(layer.style);
  const years = layer.title.match(/\d{4}\s*[–-]\s*\d{4}/);
  const period = state.source === "crc_open" ? `Projection for ${state.horizon}, pathway ${payload.pathway}` : years ? `Data period ${years[0]}` : `Horizon ${state.horizon}`;
  const ticks = ticksBetween(lo, hi).map(fmtTick); ticks[0] = `≤ ${ticks[0]}`; ticks[ticks.length - 1] = `≥ ${ticks[ticks.length - 1]}`;
  const none = payload.cells.length - n;
  return {
    title: layer.title.replace(/\s*\((reports, )?\d{4}\s*[–-]\s*\d{4}\)/, ""), unit: `${unitOf(layer, payload)} · value reached 1 year in ${state.rp}`,
    ramps: [{ css: gradient(stops), ticks }], rows: none ? [{ color: rgbCss(NODATA), shape: "box", label: "no value at this return period", n: none }] : [],
    foot: `${period}. ${n.toLocaleString("en-US")} cells; scale spans their 2nd–98th percentile${state.locked ? " (kept from the earlier view)" : ""}. Regional screening.`,
  };
}
export function cellHover(index) {
  const payload = state.files.get(fileKey(state.hazard, state.horizon)); const layer = layerById(state.hazard);
  const i = state.manifest.return_periods.indexOf(state.rp); const v = payload.values[index][i];
  const kind = payload.kinds[payload.params[index][0]];
  const head = v === null ? `no value <span>(${esc(kind === "no_data" ? payload.params[index][1] : "outside tabulated support")})</span>` : `<b>${fmt(display(layer, v))} ${esc(unitOf(layer, payload))}</b>`;
  return `${head}<br>${esc(layer.title.split(" (")[0])}<br><span>1 in ${state.rp} years · ${state.horizon} · cell ${payload.cells[index]} · ${esc(kind)}</span>`;
}
export function showDetail(index) {
  const payload = state.files.get(fileKey(state.hazard, state.horizon)); const layer = layerById(state.hazard);
  state.selected = { hazard: state.hazard, horizon: state.horizon, index };
  state.pick = { kind: "cell", cell: payload.cells[index] };
  const unit = unitOf(layer, payload); const rps = payload.return_periods; const vals = payload.values[index].map((v) => display(layer, v));
  const p = payload.params[index]; const kind = payload.kinds[p[0]];
  const centre = globalThis.h3.cellToLatLng(payload.cells[index]);
  openDetail(layer.title, `${state.horizon} · ${layer.source}`);
  const at = vals[rps.indexOf(state.rp)];
  $("detail-meta").innerHTML = kv([[`1 in ${state.rp} years`, `<span class="big">${fmt(at)}</span> <small>${esc(unit)}</small>`], ["Cell", `${payload.cells[index]} <small>H3 r${payload.h3_resolution}</small>`], ["Centre", latLon(centre[0], centre[1])], ["Curve kind", esc(kind)], ["Family / reason", esc(p[1])], ["Pathway", esc(payload.pathway)]], true);
  const params = kind === "fitted" || kind === "hurdle" ? [["location", p[2]], ["scale", p[3]], ["shape", p[4]]] : kind === "point_mass" ? [["value", p[2]]] : kind === "tabulated" ? [["knots", p[2]]] : [];
  if (kind === "hurdle") params.push(["atom probability", p[5]], ["atom location", p[6]]);
  $("detail-params").innerHTML = params.length ? kv([`Raw parameters (${payload.unit}, as shipped)`, ...params.map(([k, v]) => [k, v === null ? "–" : String(v)])]) : "";
  $("detail-table").innerHTML = `<tr><th>Return period</th><th class="num">Non-exceedance</th><th class="num">${esc(unit)}</th></tr>` + rps.map((t, i) => `<tr class="${t === state.rp ? "sel" : ""}"><td>1 in ${t} years</td><td class="num">${payload.probabilities[i]}</td><td class="num">${fmt(vals[i])}</td></tr>`).join("");
  $("detail-foot").textContent = "Regional screening: a cell is an average, not a site. Values are the curve crc-sdk evaluated at these return periods during the data build; the page draws them and interpolates between.";
  drawCurve(rps, vals, unit, ramp(layer.style));
}
