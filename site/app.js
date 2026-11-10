// Texas climate data explorer (v2, source-centric). No build step: MapLibre (ESM) + deck.gl (UMD global `deck`).
import * as maplibregl from "https://cdn.jsdelivr.net/npm/maplibre-gl@6.16.0/dist/maplibre-gl.mjs";

const { MapboxOverlay, H3HexagonLayer, GeoJsonLayer, ScatterplotLayer, LineLayer, SolidPolygonLayer, PathLayer } = globalThis.deck;
const $ = (id) => document.getElementById(id);

const state = {
  registry: null, catalog: null, manifest: null, sources: null, texas: null,
  source: null,              // active source id (registry.sources[].id)
  hazard: null, horizon: null, rp: null,   // active h3-cells layer and its view
  files: new Map(),          // "hazard/horizon" -> payload; "geo:<id>" -> GeoJSON
  domain: null, locked: false,
  overlays: new Map(),       // layer id -> boolean (layers shown beside the active source)
  selected: null,            // cells click: { hazard, horizon, index }
  events: null, eventsFilter: { from: null, to: null, types: null },
  tracks: null, tracksFilter: { from: null, to: null, name: "", minWind: 0, colorBy: "wind" }, storm: null,
  extent: true,              // draw wind-radius swaths where IBTrACS has them
  win: { on: false, start: "2024-03-14", days: 3 },   // Storm reports date window
  time: null,                // player: { key, mode, t0, t1, now, playing, speed, shade, range }
  baseLayers: [], series: null,
  map: null, overlay: null,
  cmp: null,                 // hail comparison: { data, lon[], mode, a, b, ownScale, split }
};

// ---------- colour: one hue, light -> dark, built in OKLCH; fallback blue ramp ----------
const FALLBACK = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
const canvas = document.createElement("canvas"); canvas.width = canvas.height = 1;
const ctx = canvas.getContext("2d", { willReadFrequently: true });
function parseColor(css) {
  ctx.fillStyle = "#000"; ctx.fillStyle = css;
  ctx.clearRect(0, 0, 1, 1); ctx.fillRect(0, 0, 1, 1);
  const d = ctx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2]];
}
function ramp(style) {
  const steps = 7;
  if (style && style.hue !== undefined) {
    const test = parseColor(`oklch(0.6 ${style.chroma} ${style.hue})`);
    if (!(test[0] === 0 && test[1] === 0 && test[2] === 0)) {
      return Array.from({ length: steps }, (_, i) => {
        const L = 0.93 - (0.58 * i) / (steps - 1);
        const C = style.chroma * (0.35 + 0.65 * Math.sin((Math.PI * (i + 0.5)) / steps));
        return parseColor(`oklch(${L} ${C} ${style.hue})`);
      });
    }
  }
  return FALLBACK.map(parseColor);
}
function colorAt(stops, t, alpha = 215) {
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x)); const f = x - i;
  const a = stops[i], b = stops[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, alpha];
}
const NODATA = [201, 199, 193, 140];
const gradient = (stops) => `linear-gradient(90deg, ${stops.map((c) => `rgb(${c.join(",")})`).join(",")})`;

// ---------- helpers ----------
const layerById = (id) => state.registry.layers.find((l) => l.id === id);
const sourceById = (id) => state.registry.sources.find((s) => s.id === id);
const groupOf = (s) => state.registry.groups.find((g) => g.id === s.origin) || state.registry.groups[0];
const badge = (s) => { const g = groupOf(s); return `<span class="badge" style="--g:${g.color}" title="${esc(g.title)}">${esc(g.badge)}</span>`; };
const layersOfSource = (id) => state.registry.layers.filter((l) => l.source_id === id);
const fileKey = (h, y) => `${h}/${y}`;
function display(layer, v) { if (v === null || v === undefined) return null; const d = layer.display; return d ? v + (d.offset || 0) : v; }
function unitOf(layer, payload) { return (layer.display && layer.display.unit) || payload.unit; }
function fmt(v, digits = 3) {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const a = Math.abs(v);
  if (a >= 100) return v.toFixed(0); if (a >= 10) return v.toFixed(1); if (a >= 1) return v.toFixed(2);
  return v.toPrecision(digits);
}
function quantile(sorted, q) { if (!sorted.length) return NaN; const i = (sorted.length - 1) * q; const lo = Math.floor(i); return sorted[lo] + (sorted[Math.min(lo + 1, sorted.length - 1)] - sorted[lo]) * (i - lo); }
async function fetchJSON(url) { const r = await fetch(url); if (!r.ok) throw new Error(`${url}: ${r.status}`); return r.json(); }
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const horizonsOf = (layer) => (layer && layer.horizons) || state.manifest.horizons;
// time: events carry minutes since 1950-01-01T00:00Z; track fixes carry "YYYY-MM-DD HH:MM" (UTC)
const EPOCH = Date.UTC(1950, 0, 1);
const minToMs = (m) => EPOCH + m * 60000;
const msToMin = (ms) => (ms - EPOCH) / 60000;
const parseT = (t) => Date.UTC(+t.slice(0, 4), +t.slice(5, 7) - 1, +t.slice(8, 10), +t.slice(11, 13), +t.slice(14, 16));
const fmtT = (ms) => new Date(ms).toISOString().slice(0, 16).replace("T", " ");
const cellSource = (id) => layersOfSource(id).some((l) => l.kind === "h3-cells");

// ---------- source list and per-source panel ----------
function buildSourceList() {
  const box = $("sources"); box.innerHTML = "";
  for (const g of state.registry.groups) {
    const members = state.registry.sources.filter((s) => s.origin === g.id); if (!members.length) continue;
    const head = document.createElement("div"); head.className = "grp"; head.style.setProperty("--g", g.color); head.dataset.group = g.id;
    head.innerHTML = `<div class="gt"><span class="badge" style="--g:${g.color}">${esc(g.badge)}</span>${esc(g.title)}</div><div class="gb">${esc(g.blurb)}</div>`;
    box.append(head);
    for (const s of members) {
      const b = document.createElement("button"); b.className = "src" + (s.id === state.source ? " on" : ""); b.dataset.id = s.id; b.style.setProperty("--g", g.color);
      b.innerHTML = `<span class="t">${esc(s.title)}</span><span class="s">${esc(s.short)}</span><span class="pills"><span class="pill ${s.status === "loaded" ? "on" : s.status === "prototype" ? "proto" : "plan"}">${s.status}</span><span class="pill">${esc(s.licence.split(";")[0].split("(")[0].trim())}</span></span>`;
      b.onclick = () => selectSource(s.id);
      box.append(b);
    }
  }
}

function selectSource(id, force = false) {
  if (state.source === id && !force) return Promise.resolve();
  state.source = id; state.selected = null; state.storm = null; $("detail").classList.add("hidden");
  const cells = layersOfSource(id).filter((l) => l.kind === "h3-cells");
  if (cells.length) {
    state.hazard = id === "crc_open" ? state.registry.defaults.crc_hazard : cells[0].id;
    const hs = horizonsOf(layerById(state.hazard)); if (!hs.includes(state.horizon)) state.horizon = hs[0];
    state.domain = null;
  }
  buildSourceList(); return render();
}

function buildSourcePanel() {
  const s = sourceById(state.source);
  $("source-blurb").innerHTML = `${badge(s)} <b>${esc(s.title)}</b> · ${esc(s.provider)}<br>${esc(s.returns)}<br><span>Coverage: ${esc(s.coverage)}. Licence: ${esc(s.licence)}.</span>`;
  for (const el of document.querySelectorAll("#source-panel .ctl")) el.classList.add("hidden");
  const show = (id) => $(id).classList.remove("hidden");
  if (state.source === "ibtracs") { show("ctl-ibtracs"); buildTracksControls(); }
  else if (state.source === "storm_events") { show("ctl-storm_events"); buildEventsControls(); }
  else if (compareLayerOf(state.source)) { show("ctl-compare"); buildCompareControls(); }
  else if (cellSource(state.source)) { show("ctl-cells"); buildCellControls(); }
  else { show("ctl-stations"); buildStationsList(); }
}

function buildOverlays() {
  const box = $("overlays"); box.innerHTML = "";
  const own = new Set(layersOfSource(state.source).map((l) => l.id));
  for (const l of state.registry.layers) {
    if (l.kind === "h3-cells" && l.id !== state.hazard) continue;
    if (l.kind === "h3-cells" && !own.has(l.id)) continue; // cells only through their source
    if (l.kind === "h3-compare" && !own.has(l.id)) continue;
    const lab = document.createElement("label");
    const cb = document.createElement("input"); cb.type = "checkbox";
    const forced = own.has(l.id);
    cb.checked = forced || state.overlays.get(l.id) === true; cb.disabled = forced;
    cb.onchange = () => { state.overlays.set(l.id, cb.checked); render(); };
    lab.append(cb, document.createTextNode(l.title), Object.assign(document.createElement("span"), { className: "mute", textContent: forced ? "this source" : (sourceById(l.source_id) || { title: l.source }).title }));
    box.append(lab);
  }
  for (const p of state.registry.planned) {
    const lab = document.createElement("label"); const cb = document.createElement("input"); cb.type = "checkbox"; cb.disabled = true;
    lab.append(cb, document.createTextNode(p.title), Object.assign(document.createElement("span"), { className: "mute", textContent: p.status }));
    box.append(lab);
  }
}

function buildCaveats(payload) {
  const { catalog, manifest } = state; const s = sourceById(state.source);
  const g = groupOf(s);
  const items = [`${badge(s)} <b>${esc(g.title)}.</b> ${esc(g.blurb)}`, ...(s.caveats || []).map((t) => `<b>${esc(s.title)}:</b> ${esc(t)}`)];
  for (const l of layersOfSource(state.source)) if (l.caveat) items.push(`<b>${esc(l.title)}:</b> ${esc(l.caveat)}`);
  if (payload && cellSource(state.source)) {
    const layer = layerById(state.hazard); const res = payload.h3_resolution;
    const km2 = res === 5 ? "about 253 km²" : res === 7 ? "about 5.2 km²" : res === 4 ? "about 1,770 km²" : `resolution ${res}`;
    items.push(`<b>Cells:</b> H3 resolution ${res}, ${km2} each; ${payload.cells.length.toLocaleString()} cells with a curve; cells without one are not drawn.`);
    items.push(`<b>Curve:</b> ${esc(payload.value_semantics)}; probability semantics ${esc(payload.probability_semantics || "unspecified")}; return periods read on the ${payload.tail} tail (1 in T years = non-exceedance ${payload.tail === "upper" ? "1 − 1/T" : "1/T"}). Displayed unit ${unitOf(layer, payload)}${layer.display && layer.display.offset ? ` (source ${payload.unit})` : ""}.`);
    if (state.source === "crc_open") {
      items.push(`<b>Release:</b> CRC Open <code>${esc(catalog.release)}</code>, ${esc(catalog.licence)}. Attribution: ${esc(catalog.attribution)}.`);
      const note = catalog.hazards[state.hazard] && catalog.hazards[state.hazard].notes; if (note) items.push(`<b>Release note for ${esc(state.hazard)}:</b> ${esc(note)}`);
      const build = manifest.hazards.find((h) => h.hazard === state.hazard);
      if (build && build.outside_tabulated_support) items.push(`<b>Tabulated curves:</b> ${build.kinds.tabulated || 0} cells per horizon carry only a few knots near the rare end; return periods outside those knots show as no value.`);
      if (build) for (const w of build.warnings) items.push(`<b>crc-sdk warning:</b> ${esc(w)}`);
    }
  }
  if (state.source === "storm_events" && state.events) items.push(...state.events.index.known_biases.slice(0, 4).map((t) => `<b>Reports:</b> ${esc(t)}`));
  if (state.source === "ibtracs" && state.tracks) items.push(`<b>Wind extent:</b> shaded bands are US agency estimates of how far 34, 50 and 64 kt winds reached in each quadrant (${state.tracks.storms.filter((x) => x.extent_points.r34).length} of ${state.tracks.storms.length} storms, from 2001), joined along the track; they are not observed damage footprints, and storms without them show a line only.`);
  if (state.time) items.push(`<b>Timeline:</b> storm reports are placed at their begin time (NCEI local standard time converted to UTC); most hail and wind reports are instants. Reports appear when the clock passes them and stay.`);
  if (state.source === "ibtracs" && state.tracks) items.push(`<b>Winds:</b> ${esc(state.tracks.wind_note)}. Snapshot SHA-256 ${esc((state.tracks.sha256 || "").slice(0, 12))}…, retrieved ${esc((state.tracks.retrieved_at || "").slice(0, 10))}. Cite: ${esc(state.tracks.citation)}.`);
  for (const l of state.registry.layers) {
    if (state.overlays.get(l.id) === true && l.source_id && l.source_id !== state.source) {
      const os = sourceById(l.source_id); items.push(`<b>Also shown, ${esc(os.title)}:</b> ${esc((os.caveats && os.caveats[0]) || l.caveat || os.short)} Licence: ${esc(os.licence)}.`);
    }
  }
  items.push(`<b>Built</b> ${esc(manifest.built_at)} with crc-sdk ${esc(manifest.versions["crc-sdk"])}, crc-framework ${esc(manifest.versions["crc-framework"])}. Basemap ${esc(state.registry.basemap.attribution)}.`);
  $("caveats").innerHTML = items.map((t) => `<li>${t}</li>`).join("");
}

// ---------- cells (CRC Open, ERA5): same code path as explorer v1 ----------
async function loadFile(hazard, horizon) {
  const key = fileKey(hazard, horizon);
  if (!state.files.has(key)) state.files.set(key, await fetchJSON(layerById(hazard).file.replace("{horizon}", horizon)));
  return state.files.get(key);
}
function buildCellControls() {
  const { catalog, registry } = state; const sel = $("hazard"); sel.innerHTML = "";
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
  rp.value = state.rp;
}
function computeDomain(payload, rpIndex, layer) {
  const vals = payload.values.map((r) => r[rpIndex]).filter((v) => v !== null).map((v) => display(layer, v)).sort((a, b) => a - b);
  let lo = quantile(vals, 0.02), hi = quantile(vals, 0.98);
  if (!(hi > lo)) { lo = vals[0] ?? 0; hi = vals[vals.length - 1] ?? 1; if (!(hi > lo)) hi = lo + 1; }
  return [lo, hi, vals.length];
}
function cellsLayer(layer, payload) {
  const rpIndex = state.manifest.return_periods.indexOf(state.rp);
  if (!state.locked || !state.domain) state.domain = computeDomain(payload, rpIndex, layer);
  const [lo, hi, n] = state.domain; const stops = ramp(layer.style);
  const color = (i) => { const v = payload.values[i][rpIndex]; return v === null ? NODATA : colorAt(stops, (display(layer, v) - lo) / (hi - lo)); };
  $("legend-title").textContent = `${layer.title}, ${state.horizon}, 1 in ${state.rp} years`;
  $("legend-unit").textContent = unitOf(layer, payload);
  $("legend-bar").style.background = gradient(stops);
  $("legend-min").textContent = `≤ ${fmt(lo)}`; $("legend-max").textContent = `≥ ${fmt(hi)}`;
  $("legend-note").textContent = `Scale spans the 2nd–98th percentile of ${n} cells with a value (${payload.cells.length - n} without). Grey: no value.`;
  return new H3HexagonLayer({
    id: "cells", data: payload.values.map((_, i) => i), getHexagon: (i) => payload.cells[i], getFillColor: color,
    filled: true, stroked: false, extruded: false, highPrecision: false, pickable: true, opacity: 1,
    updateTriggers: { getFillColor: [state.hazard, state.horizon, state.rp, lo, hi], getHexagon: [state.hazard, state.horizon] },
    onClick: (info) => { showDetail(info.index); return true; },
  });
}
function cellTooltip(index) {
  const payload = state.files.get(fileKey(state.hazard, state.horizon)); const layer = layerById(state.hazard);
  const i = state.manifest.return_periods.indexOf(state.rp); const v = payload.values[index][i];
  const kind = payload.kinds[payload.params[index][0]];
  return { text: v === null ? `${payload.cells[index]}\nno value (${kind === "no_data" ? payload.params[index][1] : "outside tabulated support"})` : `${fmt(display(layer, v))} ${unitOf(layer, payload)}  ·  1 in ${state.rp} years, ${state.horizon}\n${payload.cells[index]} · ${kind}` };
}
function showDetail(index) {
  const payload = state.files.get(fileKey(state.hazard, state.horizon)); const layer = layerById(state.hazard);
  state.selected = { hazard: state.hazard, horizon: state.horizon, index };
  const unit = unitOf(layer, payload); const rps = payload.return_periods; const vals = payload.values[index].map((v) => display(layer, v));
  const p = payload.params[index]; const kind = payload.kinds[p[0]];
  const centre = globalThis.h3 && globalThis.h3.cellToLatLng ? globalThis.h3.cellToLatLng(payload.cells[index]) : null;
  $("detail").classList.remove("hidden");
  $("detail-title").textContent = `${layer.title}, ${state.horizon}`;
  $("detail-meta").innerHTML = [["Cell", `${payload.cells[index]} (H3 r${payload.h3_resolution})`], ["Centre", centre ? `${centre[0].toFixed(3)}°N, ${(-centre[1]).toFixed(3)}°W` : "–"], ["Curve kind", kind], ["Family / reason", p[1]], ["Pathway", payload.pathway], ["Unit", unit]].map(([k, v]) => `<b>${k}</b><span>${esc(v)}</span>`).join("");
  const params = kind === "fitted" || kind === "hurdle" ? [["location", p[2]], ["scale", p[3]], ["shape", p[4]]] : kind === "point_mass" ? [["value", p[2]]] : kind === "tabulated" ? [["knots", p[2]]] : [];
  if (kind === "hurdle") params.push(["atom probability", p[5]], ["atom location", p[6]]);
  $("detail-params").innerHTML = params.length ? `<b>Raw parameters</b><span>(${esc(payload.unit)}, as shipped)</span>` + params.map(([k, v]) => `<b>${k}</b><span>${v === null ? "–" : v}</span>`).join("") : "";
  $("detail-table").innerHTML = `<tr><th>Return period</th><th class="num">Non-exceedance</th><th class="num">${esc(unit)}</th></tr>` + rps.map((t, i) => `<tr class="${t === state.rp ? "sel" : ""}"><td>1 in ${t} years</td><td class="num">${payload.probabilities[i]}</td><td class="num">${fmt(vals[i])}</td></tr>`).join("");
  $("detail-foot").textContent = "Regional screening: a cell is an average, not a site. Values are the curve crc-sdk evaluated at these return periods during the data build; the page draws them and interpolates between.";
  drawCurve(rps, vals, unit, ramp(layer.style));
}

// ---------- tracks (IBTrACS) ----------
const WIND_DOMAIN = [20, 140];
async function loadTracks(layer) {
  if (!state.tracks) {
    state.tracks = await fetchJSON(layer.file);
    const f = state.tracksFilter; const seasons = state.tracks.storms.map((s) => s.season);
    if (f.from === null) { f.from = Math.min(...seasons); f.to = Math.max(...seasons); }
  }
  return state.tracks;
}
function tracksMatch() {
  const f = state.tracksFilter; const q = f.name.trim().toLowerCase();
  return state.tracks.storms.filter((s) => s.season >= f.from && s.season <= f.to && (!q || s.name.toLowerCase().includes(q)) && (s.max_wind_kt || 0) >= f.minWind);
}
function categoryColor(layer, cat) { const c = layer.style.category_colors; return (cat === null || cat === undefined ? null : c[String(cat)]) || c["-5"]; }
function windColor(stops, w) { return w === null ? [160, 160, 158] : colorAt(stops, 0.3 + 0.7 * Math.min(1, Math.max(0, (w - WIND_DOMAIN[0]) / (WIND_DOMAIN[1] - WIND_DOMAIN[0]))), 255).slice(0, 3); }
function buildTracksControls() {
  const f = state.tracksFilter; const layer = layerById("ibtracs"); const stops = ramp(layer.style);
  $("tracks-from").value = f.from; $("tracks-to").value = f.to; $("tracks-name").value = f.name; $("tracks-min-wind").value = f.minWind; $("tracks-color").value = f.colorBy;
  $("tracks-from").onchange = (e) => { f.from = Number(e.target.value); render(); };
  $("tracks-to").onchange = (e) => { f.to = Number(e.target.value); render(); };
  $("tracks-name").oninput = (e) => { f.name = e.target.value; render(); };
  $("tracks-min-wind").onchange = (e) => { f.minWind = Number(e.target.value) || 0; render(); };
  $("tracks-color").onchange = (e) => { f.colorBy = e.target.value; render(); };
  $("tracks-extent").checked = state.extent; $("tracks-extent").onchange = (e) => { state.extent = e.target.checked; render(); };
  const legend = $("tracks-legend");
  if (f.colorBy === "wind") legend.innerHTML = `<div style="width:100%"><div class="bar" style="background:${gradient(stops.slice(2))}"></div><div style="display:flex;justify-content:space-between"><span>≤ ${WIND_DOMAIN[0]} kt</span><span>agency wind along the track</span><span>≥ ${WIND_DOMAIN[1]} kt</span></div></div>`;
  if (state.extent) { const b = ramp(layer.style)[5]; legend.innerHTML += `<div style="width:100%">${["34 kt", "50 kt", "64 kt"].map((t, i) => `<span><i class="sw" style="height:9px;background:rgba(${b.join(",")},${BAND_ALPHA[i]})"></i>${t} wind radius</span>`).join(" ")}</div>`; }
  if (f.colorBy !== "wind") legend.innerHTML = [["-5", "not a tropical cyclone / unknown"], ["-1", "tropical depression"], ["0", "tropical storm"], ["1", "category 1"], ["2", "category 2"], ["3", "category 3"], ["4", "category 4"], ["5", "category 5"]].map(([k, t]) => `<span><i class="sw" style="background:rgb(${layer.style.category_colors[k].join(",")})"></i>${t}</span>`).join("") + (state.extent ? `<span>shaded: 34, 50, 64 kt wind radii</span>` : "");
  const match = tracksMatch(); const list = $("tracks-list"); list.innerHTML = "";
  for (const s of [...match].sort((a, b) => b.season - a.season || a.name.localeCompare(b.name))) {
    const li = document.createElement("li"); li.className = state.storm === s.sid ? "sel" : "";
    li.innerHTML = `<span>${esc(s.label)}</span><span class="mute">${s.max_wind_kt === null ? "–" : `${s.max_wind_kt} kt`}${s.max_category !== null && s.max_category > 0 ? ` · cat ${s.max_category}` : ""}</span>`;
    li.onclick = () => { state.storm = state.storm === s.sid ? null : s.sid; render(); if (state.storm) showStorm(s); else $("detail").classList.add("hidden"); };
    list.append(li);
  }
  $("tracks-status").textContent = `${match.length} of ${state.tracks.storms.length} storms shown (${f.from}–${f.to}${f.minWind ? `, at least ${f.minWind} kt` : ""}${f.name ? `, name contains “${f.name}”` : ""}). Click a storm for its track and winds.`;
}
function tracksLayers(layer) {
  const f = state.tracksFilter; const stops = ramp(layer.style); const match = tracksMatch();
  const segments = [];
  for (const s of match) {
    const pts = s.points;
    for (let i = 0; i + 1 < pts.length; i++) segments.push({ sid: s.sid, label: s.label, i, a: [pts[i][0], pts[i][1]], b: [pts[i + 1][0], pts[i + 1][1]], w: pts[i][2], cat: pts[i][4], t: pts[i][5] });
  }
  const dim = state.storm !== null;
  const color = (d) => { const base = f.colorBy === "wind" ? windColor(stops, d.w) : categoryColor(layer, d.cat); return [...base, dim && d.sid !== state.storm ? 70 : 230]; };
  return [...(state.extent ? swathLayers(layer, match) : []), new LineLayer({
    id: "tracks", data: segments, pickable: true, widthUnits: "pixels",
    getSourcePosition: (d) => d.a, getTargetPosition: (d) => d.b, getColor: color, getWidth: (d) => (d.sid === state.storm ? 4 : 2),
    updateTriggers: { getColor: [f.colorBy, state.storm], getWidth: [state.storm] },
    onClick: (info) => { const s = state.tracks.storms.find((x) => x.sid === info.object.sid); state.storm = s.sid; render(); showStorm(s); return true; },
  })];
}
// wind extent: quadrant radii (NE, SE, SW, NW; nautical miles) -> a smooth outline around a fix
const QUAD_BEARINGS = [45, 135, 225, 315];
function radiusAt(r4, bearing) {
  // cosine interpolation between neighbouring quadrant centres; a missing quadrant counts as 0
  const b = ((bearing - 45) % 360 + 360) % 360; const k = Math.floor(b / 90); const f = (b - k * 90) / 90;
  const a = r4[k % 4] || 0, c = r4[(k + 1) % 4] || 0; const t = (1 - Math.cos(Math.PI * f)) / 2;
  return a + (c - a) * t;
}
function ringAt(lon, lat, r4, step = 10) {
  const out = []; const cos = Math.cos((lat * Math.PI) / 180);
  for (let b = 0; b < 360; b += step) { const r = radiusAt(r4, b) / 60; const rad = (b * Math.PI) / 180; out.push([lon + (r * Math.sin(rad)) / cos, lat + r * Math.cos(rad)]); }
  return out;
}
function lerpR(a, b, f) { if (!a && !b) return null; const x = a || [0, 0, 0, 0], y = b || [0, 0, 0, 0]; return x.map((v, i) => (v || 0) + ((y[i] || 0) - (v || 0)) * f); }
function stormTimes(s) { if (!s._t) s._t = s.points.map((p) => parseT(p[5])); return s._t; }
function fixAt(s, ms) {
  // linear interpolation between best-track fixes
  const t = stormTimes(s); const n = t.length;
  if (ms <= t[0]) return fixAt0(s.points[0]); if (ms >= t[n - 1]) return fixAt0(s.points[n - 1]);
  let lo = 0, hi = n - 1; while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (t[mid] <= ms) lo = mid; else hi = mid; }
  const a = s.points[lo], b = s.points[hi]; const f = t[hi] === t[lo] ? 0 : (ms - t[lo]) / (t[hi] - t[lo]);
  const mix = (x, y) => (x === null || y === null ? (f < 0.5 ? x : y) : x + (y - x) * f);
  return { lon: a[0] + (b[0] - a[0]) * f, lat: a[1] + (b[1] - a[1]) * f, wind: mix(a[2], b[2]), r: [lerpR(a[7], b[7], f), lerpR(a[8], b[8], f), lerpR(a[9], b[9], f)] };
}
const fixAt0 = (p) => ({ lon: p[0], lat: p[1], wind: p[2], r: [p[7], p[8], p[9]] });
const BAND_ALPHA = [0.2, 0.36, 0.55];
function swathLayers(layer, match) {
  // One translucent band per threshold along the track. Overlaps must not pile up, so the bands are drawn
  // with a "max" blend on premultiplied colour: where rings overlap the strongest band wins, nothing accumulates.
  // the selected storm, or every shown storm when the filter leaves a handful (30 swaths at once are unreadable)
  const storms = state.storm !== null ? match.filter((s) => s.sid === state.storm) : match.length <= 8 ? match : [];
  const base = ramp(layer.style)[5]; const rings = [[], [], []];
  for (const s of storms) {
    if (!s.extent_points.r34) continue;
    const t = stormTimes(s); const sub = state.storm !== null ? 3 : 1;
    for (let i = 0; i < t.length; i++) for (let k = 0; k < sub; k++) {
      if (i === t.length - 1 && k > 0) break;
      const fx = k === 0 ? fixAt0(s.points[i]) : fixAt(s, t[i] + ((t[i + 1] - t[i]) * k) / sub);
      for (let b = 0; b < 3; b++) if (fx.r[b] && fx.r[b].some((v) => v > 0)) rings[b].push(ringAt(fx.lon, fx.lat, fx.r[b]));
    }
  }
  return rings.map((data, b) => new SolidPolygonLayer({
    id: `swath-${b}`, data, getPolygon: (d) => d, pickable: false, filled: true,
    getFillColor: [base[0] * BAND_ALPHA[b], base[1] * BAND_ALPHA[b], base[2] * BAND_ALPHA[b], 255 * BAND_ALPHA[b]],
    parameters: { blend: true, blendColorOperation: "max", blendAlphaOperation: "max", blendColorSrcFactor: "one", blendColorDstFactor: "one", blendAlphaSrcFactor: "one", blendAlphaDstFactor: "one", depthCompare: "always" },
  }));
}
function trackTooltip(d) { return { text: `${d.label}\n${d.t} UTC · ${d.w === null ? "wind not given" : `${d.w} kt`}${d.cat !== null && d.cat > 0 ? ` · category ${d.cat}` : ""}` }; }
function showStorm(s) {
  const layer = layerById("ibtracs"); const stops = ramp(layer.style);
  $("detail").classList.remove("hidden");
  $("detail-title").textContent = `${s.label}`;
  const first = s.points[0][5], last = s.points[s.points.length - 1][5];
  $("detail-meta").innerHTML = [
    ["Storm id", s.sid], ["Season", s.season], ["Strongest wind on the shown track", s.max_wind_kt === null ? "–" : `${s.max_wind_kt} kt (${(s.max_wind_kt * 0.514444).toFixed(0)} m/s)`],
    ["Strongest wind while over the Texas box", s.max_wind_kt_in_texas === null ? "–" : `${s.max_wind_kt_in_texas} kt`],
    ["Lowest pressure", s.min_pressure_mb === null ? "–" : `${s.min_pressure_mb} mb`], ["Highest category", s.max_category === null ? "–" : s.max_category <= 0 ? "below hurricane strength" : `${s.max_category} (Saffir-Simpson, NOAA USA_SSHS)`],
    ["Wind extent", s.extent_points.r34 ? `34 kt radii at ${s.extent_points.r34} fixes, 64 kt at ${s.extent_points.r64}${s.extent_points.rmw ? `; radius of maximum wind at ${s.extent_points.rmw}` : ""}` : `no wind-radius estimate in IBTrACS for this storm${s.extent_points.rmw ? ` (radius of maximum wind at ${s.extent_points.rmw} fixes)` : ""}`],
    ["In the Texas box", `${s.first_texas_point} to ${s.last_texas_point} UTC`], ["Track shown", `${s.points.length} points, ${first} to ${last} UTC`], ["Wind source", s.wind_source === "wmo" ? "WMO agency" : s.wind_source === "usa" ? "US agency" : "WMO where present, else US agency"],
  ].map(([k, v]) => `<b>${k}</b><span>${esc(v)}</span>`).join("");
  $("detail-table").innerHTML = ""; $("detail-params").innerHTML = "";
  $("detail-foot").textContent = "Best-track observations of the storm centre. Winds are agency estimates of the maximum sustained wind near the centre, not winds at any place; nothing here is a return-period curve.";
  drawSeries(s.points.map((p) => p[2]), s.points.map((p) => p[5]), "kt", stops, s.points.map((p) => p[0] >= state.tracks.texas_box[0] && p[0] <= state.tracks.texas_box[2] && p[1] >= state.tracks.texas_box[1] && p[1] <= state.tracks.texas_box[3]));
}

// ---------- points-binary layer (Storm Events) ----------
async function loadEvents(layer) {
  if (state.events) return state.events;
  const [index, buffer] = await Promise.all([fetchJSON(layer.index), fetch(layer.file).then((r) => { if (!r.ok) throw new Error(`${layer.file}: ${r.status}`); return r.arrayBuffer(); })]);
  const n = Math.floor(buffer.byteLength / index.record_bytes); const view = new DataView(buffer);
  const lon = new Float32Array(n), lat = new Float32Array(n), mag = new Float32Array(n), dmg = new Float32Array(n);
  const year = new Uint16Array(n), type = new Uint8Array(n), id = new Uint32Array(n), begin = new Uint32Array(n), end = new Uint32Array(n);
  const off = Object.fromEntries(index.fields.map((f) => [f.name, f.offset])); const rb = index.record_bytes;
  for (let i = 0; i < n; i++) {
    const b = i * rb;
    lon[i] = view.getFloat32(b + off.lon, true); lat[i] = view.getFloat32(b + off.lat, true);
    year[i] = view.getUint16(b + off.year, true); type[i] = view.getUint8(b + off.type);
    mag[i] = view.getFloat32(b + off.magnitude, true); id[i] = view.getUint32(b + off.event_id, true);
    dmg[i] = view.getFloat32(b + off.damage_usd, true);
    begin[i] = view.getUint32(b + off.begin_min, true); end[i] = view.getUint32(b + off.end_min, true);
  }
  state.events = { index, n, lon, lat, year, type, mag, id, dmg, begin, end };
  if (state.eventsFilter.from === null) {
    state.eventsFilter.from = index.years[0]; state.eventsFilter.to = index.years[1];
    state.eventsFilter.types = new Set((layer.default_types || index.types).filter((t) => index.types.includes(t)));
  }
  return state.events;
}
function eventColor(layer, typeName) { return layer.style.colors[typeName] || layer.style.other; }
function buildEventsControls() {
  if (!state.events) return;
  const layer = layerById("storm_events"); const { index } = state.events; const f = state.eventsFilter;
  $("events-from").value = f.from; $("events-to").value = f.to;
  $("events-from").min = index.years[0]; $("events-to").max = index.years[1];
  $("events-from").onchange = (e) => { f.from = Number(e.target.value); render(); };
  $("events-to").onchange = (e) => { f.to = Number(e.target.value); render(); };
  const w = state.win;
  $("win-on").checked = w.on; $("win-start").value = w.start; $("win-days").value = w.days;
  $("win-row").style.display = w.on ? "" : "none";
  $("win-on").onchange = (e) => { w.on = e.target.checked; render(); };
  $("win-start").onchange = (e) => { if (e.target.value) { w.start = e.target.value; render(); } };
  $("win-days").onchange = (e) => { w.days = Math.min(14, Math.max(1, Number(e.target.value) || 1)); render(); };
  const types = $("events-types"); types.innerHTML = "";
  const order = [...index.types].sort((a, b) => (index.counts[b] || 0) - (index.counts[a] || 0));
  for (const t of order) {
    const lab = document.createElement("label"); const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = f.types.has(t);
    cb.onchange = () => { if (cb.checked) f.types.add(t); else f.types.delete(t); render(); };
    const sw = document.createElement("span"); sw.className = "swatch"; sw.style.background = `rgb(${eventColor(layer, t).join(",")})`;
    lab.append(cb, sw, document.createTextNode(t), Object.assign(document.createElement("span"), { className: "mute", textContent: (index.counts[t] || 0).toLocaleString() }));
    types.append(lab);
  }
}
function eventsLayer(layer) {
  const ev = state.events; const f = state.eventsFilter; const { index } = ev;
  const typeOn = new Uint8Array(index.types.length); index.types.forEach((t, i) => { typeOn[i] = f.types.has(t) ? 1 : 0; });
  const keep = []; for (let i = 0; i < ev.n; i++) if (typeOn[ev.type[i]] && ev.year[i] >= f.from && ev.year[i] <= f.to && ev.lon[i] === ev.lon[i]) keep.push(i);
  $("events-status").textContent = `${keep.length.toLocaleString()} of ${index.events.toLocaleString()} located reports shown (${f.from}–${f.to}). ${index.events_without_point.toLocaleString()} county/zone reports have no point and are not drawn.`;
  const colors = index.types.map((t) => eventColor(layer, t));
  return new ScatterplotLayer({
    id: "events", data: keep, pickable: true, radiusUnits: "pixels", getRadius: 3, radiusMinPixels: 2, radiusMaxPixels: 6,
    stroked: true, lineWidthMinPixels: 1, getLineColor: [255, 255, 255, 160], opacity: 0.85,
    getPosition: (i) => [ev.lon[i], ev.lat[i]], getFillColor: (i) => colors[ev.type[i]],
    updateTriggers: { getFillColor: [layer.id] },
    onClick: (info) => { showEvent(layer, info.object); return true; },
  });
}
function eventTooltip(i) { const ev = state.events; const t = ev.index.types[ev.type[i]]; const m = Number.isNaN(ev.mag[i]) ? "" : ` · ${ev.mag[i]} ${ev.index.magnitude_units[t] || ""}`; return { text: `${t}, ${ev.begin[i] ? `${fmtT(minToMs(ev.begin[i]))} UTC` : ev.year[i]}${m}` }; }
function showEvent(layer, i) {
  const ev = state.events; const { index } = ev; const t = index.types[ev.type[i]];
  const unit = index.magnitude_units[t]; const mag = Number.isNaN(ev.mag[i]) ? null : ev.mag[i]; const dmg = Number.isNaN(ev.dmg[i]) ? null : ev.dmg[i];
  state.selected = null;
  $("detail").classList.remove("hidden");
  $("detail-title").textContent = `${t}, ${ev.year[i]}`;
  const url = layer.detail_url ? layer.detail_url.replace("{event_id}", ev.id[i]) : null;
  $("detail-meta").innerHTML = [
    ["Event", url ? `<a href="${url}" target="_blank" rel="noopener">${ev.id[i]} at NCEI</a>` : ev.id[i]],
    ["Begins", ev.begin[i] ? `${fmtT(minToMs(ev.begin[i]))} UTC` : "time not resolved"],
    ["Ends", ev.end[i] > ev.begin[i] ? `${fmtT(minToMs(ev.end[i]))} UTC (${ev.end[i] - ev.begin[i]} min)` : "same time (an instant report)"],
    ["Location", ev.lon[i] === ev.lon[i] ? `${ev.lat[i].toFixed(3)}°N, ${(-ev.lon[i]).toFixed(3)}°W (first point)` : "county or forecast zone only (no point)"],
    ["Magnitude", mag === null ? "–" : `${mag} ${unit || ""}${t === "Hail" ? ` (${(mag * 25.4).toFixed(0)} mm)` : t === "Thunderstorm Wind" ? ` (${(mag * 0.514444).toFixed(1)} m/s)` : ""}`],
    ["Property damage", dmg === null ? "not given" : `$${dmg.toLocaleString(undefined, { maximumFractionDigits: 0 })} (year-of-event dollars)`],
    ["Source", layer.source],
  ].map(([k, v]) => `<b>${k}</b><span>${v}</span>`).join("");
  $("chart").innerHTML = ""; $("detail-table").innerHTML = "";
  $("detail-params").innerHTML = `<b>Report</b><span>A storm report, not a measurement on a grid; the full record (narrative, end point, path) is in the event table.</span>`;
  $("detail-foot").textContent = "";
}

// ---------- GeoJSON layers (stations: CO-OPS, GHCNh) ----------
async function loadGeo(l) {
  const key = `geo:${l.id}`;
  if (!state.files.has(key)) state.files.set(key, await fetchJSON(l.file));
  return state.files.get(key);
}
function geoLayer(l, data) {
  const s = l.style || {};
  return new GeoJsonLayer({
    id: `geo:${l.id}`, data, pickable: true, autoHighlight: true,
    pointType: "circle", pointRadiusUnits: "pixels", getPointRadius: s.radius || 5,
    getFillColor: s.fill || [42, 120, 214, 200], getLineColor: s.line || [255, 255, 255, 220],
    lineWidthUnits: "pixels", getLineWidth: s.width || 1, lineWidthMinPixels: s.width || 1,
    stroked: true, filled: true,
    onClick: (info) => { showFeature(l, info.object); return true; },
  });
}
function geoTooltip(l, feature) { const p = feature.properties || {}; return { text: p.label ? `${p.label}\n${l.title}` : l.title }; }
function buildStationsList() {
  const own = layersOfSource(state.source).filter((l) => l.kind === "points"); const list = $("stations-list"); list.innerHTML = "";
  let count = 0;
  for (const l of own) {
    const data = state.files.get(`geo:${l.id}`); if (!data) continue;
    for (const f of data.features) {
      count++;
      const li = document.createElement("li"); const p = f.properties || {};
      li.innerHTML = `<span>${esc(p.label || l.title)}</span><span class="mute">${p.curve && p.curve.values ? `${p.curve.values.length} levels` : ""}</span>`;
      li.onclick = () => { state.map.jumpTo({ center: f.geometry.coordinates, zoom: Math.max(state.map.getZoom(), 7) }); showFeature(l, f); };
      list.append(li);
    }
  }
  $("stations-status").textContent = `${count} stations. Click one for its levels or curve.`;
}
function showFeature(l, feature) {
  const p = feature.properties || {}; state.selected = null;
  $("detail").classList.remove("hidden");
  $("detail-title").textContent = p.label ? `${p.label}` : l.title;
  const skip = new Set(["curve", "label"]);
  if (Array.isArray(l.panel_groups)) { // grouping is declared on the layer in layers.json
    const cell = (v, f) => (f === "percent" ? `${(100 * v).toFixed(v < 0.01 ? 3 : 2)}%` : f === "percent0" ? `${(100 * v).toFixed(0)}%` : typeof v === "boolean" ? (v ? "yes" : "no") : String(v));
    const html = [`<h3>Source</h3><b>Layer</b><span>${esc(l.title)}</span><b>From</b><span>${esc(l.source)}</span>`];
    for (const g of l.panel_groups) {
      const rows = g.fields.filter(([k]) => p[k] !== null && p[k] !== undefined && typeof p[k] !== "object").map(([k, label, f]) => `<b>${esc(label || k.replaceAll("_", " "))}</b><span>${esc(cell(p[k], f))}</span>`);
      if (rows.length) html.push(`<h3>${esc(g.title)}</h3>`, ...rows);
    }
    $("detail-meta").innerHTML = html.join(""); $("detail-meta").dataset.groups = l.panel_groups.length;
  } else {
    const meta = [["Layer", l.title], ["Source", l.source]];
    for (const [k, v] of Object.entries(p)) if (!skip.has(k) && v !== null && typeof v !== "object") meta.push([k.replaceAll("_", " "), String(v)]);
    $("detail-meta").innerHTML = meta.map(([k, v]) => `<b>${esc(k)}</b><span>${esc(v)}</span>`).join(""); delete $("detail-meta").dataset.groups;
  }
  $("detail-params").innerHTML = ""; $("detail-foot").textContent = l.caveat || "";
  const c = p.curve;
  if (c && Array.isArray(c.return_periods) && Array.isArray(c.values)) {
    $("detail-table").innerHTML = `<tr><th>Return period</th><th class="num">${esc(c.unit || "")}</th></tr>` + c.return_periods.map((t, i) => `<tr><td>1 in ${t} years</td><td class="num">${fmt(c.values[i])}</td></tr>`).join("");
    drawCurve(c.return_periods, c.values, c.unit || "", ramp(l.style && l.style.hue !== undefined ? l.style : { hue: 250, chroma: 0.14 }));
    if (c.note) $("detail-params").innerHTML = `<b>Curve</b><span>${esc(c.note)}</span>`;
  } else { $("detail-table").innerHTML = ""; $("chart").innerHTML = ""; }
}

// ---------- hail days: four sources compared (h3-compare) ----------
const compareLayerOf = (sourceId) => layersOfSource(sourceId).find((l) => l.kind === "h3-compare");
async function loadCompare(l) {
  if (state.cmp) return state.cmp;
  const data = await fetchJSON(l.file);
  const lon = data.cells.map((c) => globalThis.h3.cellToLatLng(c)[1]);
  const ids = Object.keys(data.sources);
  const q = (arr, p) => quantile([...arr].sort((x, y) => x - y), p);
  const own = Object.fromEntries(ids.map((k) => [k, q(data.sources[k].values, 0.98) || 1]));
  const shared = q(ids.flatMap((k) => data.sources[k].values), 0.98) || 1;
  const d = l.defaults || {};
  state.cmp = { data, lon, ids, own, shared, mode: "single", a: d.a || ids[0], b: d.b || ids[1], ownScale: false, split: 0.5 };
  return state.cmp;
}
function divergingAt(dv, t) { // t in [-1, 1]; neutral midpoint, one hue per side
  const to = t < 0 ? dv.low : dv.high; const f = Math.min(1, Math.abs(t));
  return [dv.mid[0] + (to[0] - dv.mid[0]) * f, dv.mid[1] + (to[1] - dv.mid[1]) * f, dv.mid[2] + (to[2] - dv.mid[2]) * f, 225];
}
const RATIO_SPAN = 4; // log2: colours saturate at 16 times either way
function splitLon() { const r = $("map").getBoundingClientRect(); return state.map.unproject([state.cmp.split * r.width, r.height / 2]).lng; }
function compareLayer(l) {
  const c = state.cmp; const { data } = c; const stops = ramp(l.style); const A = data.sources[c.a].values, B = data.sources[c.b].values;
  const top = (k) => (c.ownScale ? c.own[k] : c.shared);
  let color; let trigger;
  if (c.mode === "ratio") {
    color = (i) => (A[i] > 0 && B[i] > 0 ? divergingAt(l.style.diverging, Math.log2(A[i] / B[i]) / RATIO_SPAN) : NODATA);
    trigger = ["ratio", c.a, c.b];
  } else if (c.mode === "swipe") {
    const x = splitLon();
    color = (i) => (c.lon[i] < x ? colorAt(stops, A[i] / top(c.a)) : colorAt(stops, B[i] / top(c.b)));
    trigger = ["swipe", c.a, c.b, c.ownScale, x];
  } else {
    color = (i) => colorAt(stops, A[i] / top(c.a));
    trigger = ["single", c.a, c.ownScale];
  }
  return new H3HexagonLayer({
    id: "cmp", data: data.cells.map((_, i) => i), getHexagon: (i) => data.cells[i], getFillColor: color,
    filled: true, stroked: false, extruded: false, highPrecision: false, pickable: true, opacity: 1,
    updateTriggers: { getFillColor: trigger },
    onClick: (info) => { showCompareCell(l, info.index); return true; },
  });
}
function compareTooltip(i) {
  const c = state.cmp; const s = c.data.sources;
  return { text: `${c.data.cells[i]}\n` + c.ids.map((k) => `${fmt(s[k].values[i])}  ${s[k].title}`).join("\n") + `\n${c.data.unit}` };
}
function buildCompareControls() {
  const l = compareLayerOf(state.source); const c = state.cmp; if (!c) return; const s = c.data.sources;
  for (const id of ["cmp-a", "cmp-b"]) { const sel = $(id); sel.innerHTML = ""; for (const k of c.ids) sel.append(new Option(`${s[k].title} (${s[k].period})`, k)); }
  $("cmp-mode").value = c.mode; $("cmp-a").value = c.a; $("cmp-b").value = c.b; $("cmp-own").checked = c.ownScale;
  $("cmp-b-label").classList.toggle("hidden", c.mode === "single"); $("cmp-own-label").classList.toggle("hidden", c.mode === "ratio");
  $("cmp-a-label").firstChild.textContent = c.mode === "ratio" ? "Numerator " : c.mode === "swipe" ? "Left of the line " : "Source ";
  $("cmp-b-label").firstChild.textContent = c.mode === "ratio" ? "Denominator " : "Right of the line ";
  const stops = ramp(l.style);
  if (c.mode === "ratio") {
    const dv = l.style.diverging; const css = (a) => `rgb(${a.join(",")})`;
    $("cmp-legend-title").textContent = `${s[c.a].title} ÷ ${s[c.b].title}`; $("cmp-legend-unit").textContent = "ratio";
    $("cmp-legend-bar").style.background = `linear-gradient(90deg, ${css(dv.low)}, ${css(dv.mid)}, ${css(dv.high)})`;
    $("cmp-legend-min").textContent = "1/16 or less"; $("cmp-legend-mid").textContent = "equal"; $("cmp-legend-max").textContent = "16 times or more";
    const both = c.data.cells.filter((_, i) => s[c.a].values[i] > 0 && s[c.b].values[i] > 0).length;
    $("cmp-legend-note").textContent = `Log scale centred on equal. ${both.toLocaleString()} cells have a value in both; grey cells have none in one of them. The two records cover ${s[c.a].period} and ${s[c.b].period}.`;
  } else {
    const range = (k) => fmt(c.ownScale ? c.own[k] : c.shared);
    $("cmp-legend-title").textContent = c.mode === "swipe" ? "Left and right of the line" : s[c.a].title; $("cmp-legend-unit").textContent = c.data.unit;
    $("cmp-legend-bar").style.background = gradient(stops);
    $("cmp-legend-min").textContent = "0"; $("cmp-legend-mid").textContent = "";
    $("cmp-legend-max").textContent = c.ownScale && c.mode === "swipe" ? `≥ ${range(c.a)} left, ${range(c.b)} right` : `≥ ${range(c.a)}`;
    $("cmp-legend-note").textContent = c.ownScale ? "Each source is scaled to its own 98th percentile: read the pattern, not the level." : "One scale for all four sources (98th percentile of all values), so levels can be compared across sources.";
  }
  const med = (k) => quantile([...s[k].values].sort((x, y) => x - y), 0.5);
  $("cmp-summary").innerHTML = `<table><tr><th>Source</th><th>Period</th><th class="num">Median cell</th></tr>` + c.ids.map((k) => `<tr><td><span class="sw" style="background:rgb(${l.style.series[k].join(",")})"></span>${esc(s[k].title)}</td><td>${esc(s[k].period)}</td><td class="num">${fmt(med(k))}</td></tr>`).join("") + `</table>`;
  drawSignatureYears(l);
}
function drawSignatureYears(l) {
  const yrs = state.cmp.data.signatures_per_year || []; const box = $("cmp-years"); if (!yrs.length) { box.innerHTML = ""; return; }
  const W = 290, H = 110, m = { l: 34, r: 4, t: 16, b: 18 }; const max = Math.max(...yrs.map((y) => y.rows_ge_threshold)) || 1;
  const bw = (W - m.l - m.r) / yrs.length; const col = `rgb(${l.style.series.signatures.join(",")})`;
  const y = (v) => m.t + (1 - v / max) * (H - m.t - m.b);
  const parts = [`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Radar hail signatures per year"><text x="0" y="10" font-size="10.5" fill="#2a2a28" font-weight="600">Radar hail signatures of 1.25 in or more, per year</text>`];
  for (const t of [0, max / 2, max]) parts.push(`<line x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}" stroke="#d9d7d2"/><text x="${m.l - 4}" y="${y(t) + 3}" text-anchor="end" font-size="9" fill="#7a7976">${t >= 1000 ? `${Math.round(t / 1000)}k` : Math.round(t)}</text>`);
  yrs.forEach((d, i) => { const h = H - m.b - y(d.rows_ge_threshold); parts.push(`<rect x="${(m.l + i * bw + 1).toFixed(1)}" y="${y(d.rows_ge_threshold).toFixed(1)}" width="${Math.max(1, bw - 2).toFixed(1)}" height="${Math.max(0, h).toFixed(1)}" rx="1" fill="${col}"><title>${d.year}: ${d.rows_ge_threshold.toLocaleString()} signatures, ${d.radars} radars</title></rect>`); if (d.year % 5 === 0) parts.push(`<text x="${(m.l + i * bw + bw / 2).toFixed(1)}" y="${H - 5}" text-anchor="middle" font-size="9" fill="#7a7976">${d.year}</text>`); });
  parts.push(`</svg><div class="mute small">The swings are partly weather and partly the record itself: missing values in the first years, and changes in the radar network and algorithm.</div>`);
  box.innerHTML = parts.join("");
}
function showCompareCell(l, i) {
  const c = state.cmp; const s = c.data.sources; state.selected = null;
  const centre = globalThis.h3.cellToLatLng(c.data.cells[i]); const rate = c.data.reporting_rate[i];
  $("detail").classList.remove("hidden"); $("detail-title").textContent = "Hail days per year in this cell";
  $("detail-meta").innerHTML = [["Cell", `${c.data.cells[i]} (H3 r${c.data.h3_resolution})`], ["Centre", `${centre[0].toFixed(3)}°N, ${(-centre[1]).toFixed(3)}°W`], ["Fitted reporting rate", rate === null || Number.isNaN(rate) ? "–" : `${(100 * rate).toFixed(0)}% of hail days reported (model)`]].map(([k, v]) => `<b>${k}</b><span>${esc(v)}</span>`).join("");
  delete $("detail-meta").dataset.groups;
  const vals = c.ids.map((k) => s[k].values[i]); const max = Math.max(...vals, 0.001);
  const W = 348, row = 34, left = 8, barMax = W - 70; const parts = [`<svg viewBox="0 0 ${W} ${c.ids.length * row + 6}" role="img" aria-label="Hail days per year by source">`];
  c.ids.forEach((k, j) => { const y = j * row; const w = (vals[j] / max) * barMax; parts.push(`<text x="${left}" y="${y + 12}" font-size="11.5" fill="#2a2a28">${esc(s[k].title)} · ${esc(s[k].period)}</text><rect class="bar" data-k="${k}" x="${left}" y="${y + 17}" width="${Math.max(1, w).toFixed(1)}" height="11" rx="3" fill="rgb(${l.style.series[k].join(",")})"/><text x="${(left + Math.max(1, w) + 6).toFixed(1)}" y="${y + 27}" font-size="11.5" fill="#2a2a28">${fmt(vals[j])}</text>`); });
  parts.push("</svg>");
  $("chart").innerHTML = `<div class="bars">${parts.join("")}</div>`;
  $("detail-table").innerHTML = `<tr><th>Source</th><th>Period</th><th class="num">${esc(c.data.unit)}</th></tr>` + c.ids.map((k, j) => `<tr><td>${esc(s[k].title)}</td><td>${esc(s[k].period)}</td><td class="num">${fmt(vals[j])}</td></tr>`).join("");
  $("detail-params").innerHTML = ""; $("detail-foot").textContent = c.data.notes || l.caveat || "";
}
function placeSwipe() {
  const on = !!(state.cmp && compareLayerOf(state.source) && state.cmp.mode === "swipe"); const el = $("swipe"); el.classList.toggle("hidden", !on);
  if (!on) return; const s = state.cmp.data.sources;
  el.style.left = `${(state.cmp.split * 100).toFixed(2)}%`; $("swipe-a").textContent = `◀ ${s[state.cmp.a].title}`; $("swipe-b").textContent = `${s[state.cmp.b].title} ▶`;
}
function refreshCompareLayer() { // re-colour only the comparison layer (swipe drag, map move)
  const l = compareLayerOf(state.source); if (!l || !state.cmp) return;
  state.baseLayers = state.baseLayers.map((x) => (x.id === "cmp" ? compareLayer(l) : x)); drawFrame(); placeSwipe();
}
function wireCompare() {
  const set = (patch) => { Object.assign(state.cmp, patch); render(); };
  $("cmp-mode").onchange = (e) => set({ mode: e.target.value });
  $("cmp-a").onchange = (e) => set({ a: e.target.value });
  $("cmp-b").onchange = (e) => set({ b: e.target.value });
  $("cmp-own").onchange = (e) => set({ ownScale: e.target.checked });
  const el = $("swipe"); let drag = false;
  el.addEventListener("pointerdown", (e) => { drag = true; el.setPointerCapture(e.pointerId); e.preventDefault(); e.stopPropagation(); });
  el.addEventListener("pointermove", (e) => { if (!drag) return; const r = $("map").getBoundingClientRect(); state.cmp.split = Math.min(0.97, Math.max(0.03, (e.clientX - r.left) / r.width)); refreshCompareLayer(); });
  el.addEventListener("pointerup", () => { drag = false; });
  document.addEventListener("crc:swipe", (e) => { if (state.cmp) { state.cmp.split = e.detail; refreshCompareLayer(); } });
  state.map.on("move", () => { if (state.cmp && state.cmp.mode === "swipe" && compareLayerOf(state.source)) refreshCompareLayer(); });
}

// ---------- render ----------
let rendering = 0;
async function render() {
  const started = performance.now(); const token = ++rendering;
  const src = state.source; const layers = []; let payload = null; let fetched = started; let count = "";
  try {
    if (cellSource(src)) {
      payload = await loadFile(state.hazard, state.horizon); fetched = performance.now();
      if (token !== rendering) return;
      layers.push(cellsLayer(layerById(state.hazard), payload)); count = `${payload.cells.length.toLocaleString()} cells`;
    }
    const wanted = new Set(layersOfSource(src).map((l) => l.id));
    for (const [id, on] of state.overlays) if (on && layerById(id) && layerById(id).kind !== "h3-cells") wanted.add(id);
    for (const l of state.registry.layers) {
      if (!wanted.has(l.id) || l.kind === "h3-cells" || l.kind === "geojson") continue;
      if (l.kind === "tracks") { await loadTracks(l); if (token !== rendering) return; layers.push(...tracksLayers(l)); if (l.source_id === src) count = `${tracksMatch().length} storms`; }
      else if (l.kind === "points-binary") { await loadEvents(l); if (token !== rendering) return; if (!(l.source_id === src && state.win.on)) layers.push(eventsLayer(l)); if (l.source_id === src) count = `${state.events.index.events.toLocaleString()} located reports`; }
      else if (l.kind === "h3-compare") { await loadCompare(l); if (token !== rendering) return; layers.push(compareLayer(l)); count = `${state.cmp.data.cells.length.toLocaleString()} cells, ${state.cmp.ids.length} sources`; }
      else if (l.kind === "points" || l.kind === "lines") { const data = await loadGeo(l); if (token !== rendering) return; layers.push(geoLayer(l, data)); if (l.source_id === src) count = `${data.features.length} stations`; }
      if (fetched === started) fetched = performance.now();
    }
  } catch (e) { $("status").textContent = `Could not load ${src}: ${e.message}`; document.body.dataset.error = e.message; return; }
  if (state.overlays.get("texas") !== false) layers.push(new GeoJsonLayer({ id: "texas", data: state.texas, stroked: true, filled: false, getLineColor: layerById("texas").style.line, lineWidthMinPixels: layerById("texas").style.width, pickable: false }));
  try { await setupTime(); } catch (e) { $("status").textContent = `Could not load the timeline: ${e.message}`; }
  if (token !== rendering) return;
  state.baseLayers = layers; drawFrame();
  buildSourcePanel(); buildOverlays(); buildCaveats(payload); buildTimebar(); placeSwipe();
  if (state.selected && (state.selected.hazard !== state.hazard || state.selected.horizon !== state.horizon)) { state.selected = null; $("detail").classList.add("hidden"); }
  else if (state.selected && cellSource(src)) showDetail(state.selected.index);
  requestAnimationFrame(() => {
    if (token !== rendering) return;
    const total = performance.now() - started;
    $("status").textContent = `${count} · ${(fetched - started).toFixed(0)} ms load, ${total.toFixed(0)} ms to view`;
    document.body.dataset.ready = "1"; document.body.dataset.ms = total.toFixed(0); document.body.dataset.source = src;
  });
}

// ---------- time: storm player, report window, timeline strip ----------
function lowerBound(arr, v) { let lo = 0, hi = arr.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid] < v) lo = mid + 1; else hi = mid; } return lo; }
async function setupTime() {
  let key = null;
  if (state.source === "ibtracs" && state.storm !== null) key = `storm:${state.storm}`;
  else if (state.source === "storm_events" && state.win.on) key = `win:${state.win.start}:${state.win.days}`;
  if (key === null) { stopPlay(); state.time = null; state.series = null; return; }
  if (state.time && state.time.key === key) return;
  stopPlay();
  const ev = await loadEvents(layerById("storm_events"));
  let t0, t1, now, shade = null, mode;
  if (key.startsWith("storm:")) {
    const s = state.tracks.storms.find((x) => x.sid === state.storm); const t = stormTimes(s);
    const a = parseT(s.first_texas_point), b = parseT(s.last_texas_point); const day = 86400000;
    // the storm's stretch over the Texas box plus a day either side, kept inside the shown track
    t0 = Math.max(t[0], a - day); t1 = Math.min(t[t.length - 1], b + day); if (t1 - t0 < 3600000) { t0 = t[0]; t1 = t[t.length - 1]; }
    now = Math.max(t0, a); shade = [a, b]; mode = "storm";
  } else {
    const [y, m, d] = state.win.start.split("-").map(Number);
    t0 = Date.UTC(y, m - 1, d); t1 = t0 + state.win.days * 86400000; now = t1; mode = "window";
  }
  const i0 = lowerBound(ev.begin, Math.max(1, Math.floor(msToMin(t0)))), i1 = lowerBound(ev.begin, Math.floor(msToMin(t1)) + 1);
  state.time = { key, mode, t0, t1, now, shade, range: [i0, i1], playing: false, speed: Number($("time-speed").value) || 6, frameMs: null, frames: 0 };
  state.timelineKey = null;
}
function stopPlay() { if (state.time) state.time.playing = false; $("time-play").textContent = "▶"; }
function windowTypes() { // in window mode the type checkboxes apply; in storm mode every type in the window shows
  const ev = state.events; const { index } = ev;
  return state.time.mode === "window" ? index.types.map((t) => state.eventsFilter.types.has(t)) : index.types.map(() => true);
}
function drawFrame() {
  const t0 = performance.now(); const layers = [...state.baseLayers]; const tm = state.time;
  if (tm && state.events) {
    const ev = state.events; const el = layerById("storm_events"); const on = windowTypes(); const nowMin = msToMin(tm.now);
    const keep = []; for (let i = tm.range[0]; i < tm.range[1]; i++) { if (ev.begin[i] > nowMin) break; if (on[ev.type[i]] && ev.lon[i] === ev.lon[i]) keep.push(i); }
    const colors = ev.index.types.map((t) => eventColor(el, t));
    layers.push(new ScatterplotLayer({
      id: "window-events", data: keep, pickable: true, radiusUnits: "pixels", getRadius: 4, stroked: true, lineWidthMinPixels: 1, getLineColor: [255, 255, 255, 200],
      getPosition: (i) => [ev.lon[i], ev.lat[i]], getFillColor: (i) => colors[ev.type[i]],
      onClick: (info) => { showEvent(el, info.object); return true; },
    }));
    tm.shown = keep.length;
    if (tm.mode === "storm") {
      const s = state.tracks.storms.find((x) => x.sid === state.storm);
      if (s) {
        const fx = fixAt(s, tm.now); const base = ramp(layerById("ibtracs").style)[6];
        const outlines = fx.r.map((r4, b) => (r4 && r4.some((v) => v > 0) ? { path: [...ringAt(fx.lon, fx.lat, r4, 6), ringAt(fx.lon, fx.lat, r4, 6)[0]], b } : null)).filter(Boolean);
        if (state.extent && outlines.length) layers.push(new PathLayer({ id: "storm-outline", data: outlines, getPath: (d) => d.path, getColor: [...base, 230], widthUnits: "pixels", getWidth: (d) => 1 + d.b * 0.5, pickable: false }));
        layers.push(new ScatterplotLayer({ id: "storm-marker", data: [fx], getPosition: (d) => [d.lon, d.lat], radiusUnits: "pixels", getRadius: 7, getFillColor: [...base, 255], stroked: true, getLineColor: [255, 255, 255, 255], lineWidthMinPixels: 2, pickable: false }));
        tm.fix = fx;
      }
    }
    $("time-slider").value = Math.round(((tm.now - tm.t0) / (tm.t1 - tm.t0)) * 1000);
    $("time-clock").textContent = `${fmtT(tm.now)} UTC${tm.fix && tm.mode === "storm" && tm.fix.wind !== null ? ` · ${tm.fix.wind.toFixed(0)} kt` : ""} · ${keep.length} reports`;
    const cur = document.querySelector("#timeline .cursor"); if (cur && state.timelineX) { const px = state.timelineX(tm.now); cur.setAttribute("x1", px); cur.setAttribute("x2", px); }
    const sc = document.getElementById("series-cursor"); if (sc && state.series && tm.mode === "storm") { const px = state.series(tm.now); sc.setAttribute("x1", px); sc.setAttribute("x2", px); }
    document.body.dataset.now = fmtT(tm.now); document.body.dataset.shown = keep.length; if (tm.fix) document.body.dataset.marker = `${tm.fix.lon.toFixed(3)},${tm.fix.lat.toFixed(3)}`;
  }
  state.overlay.setProps({ layers });
  if (tm) { const dt = performance.now() - t0; tm.frames++; tm.frameMs = tm.frameMs === null ? dt : tm.frameMs * 0.9 + dt * 0.1; document.body.dataset.frameMs = tm.frameMs.toFixed(2); }
}
function play() {
  const tm = state.time; if (!tm) return;
  if (tm.now >= tm.t1) tm.now = tm.t0;
  tm.playing = true; $("time-play").textContent = "❚❚"; let last = performance.now(); const key = tm.key;
  const step = (t) => {
    if (!state.time || state.time.key !== key || !tm.playing) return;
    tm.now = Math.min(tm.t1, tm.now + ((t - last) / 1000) * tm.speed * 3600000); last = t;
    drawFrame();
    if (tm.now >= tm.t1) { stopPlay(); return; }
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
function buildTimebar() {
  const tm = state.time; const bar = $("timebar");
  const was = bar.classList.contains("hidden"); bar.classList.toggle("hidden", !tm);
  if (was !== !tm && state.map) state.map.resize();
  if (!tm) return;
  $("time-play").onclick = () => { if (tm.playing) stopPlay(); else play(); };
  $("time-speed").onchange = (e) => { tm.speed = Number(e.target.value); };
  $("time-slider").oninput = (e) => { stopPlay(); tm.now = tm.t0 + (Number(e.target.value) / 1000) * (tm.t1 - tm.t0); drawFrame(); };
  const filterKey = tm.mode === "window" ? [...state.eventsFilter.types].sort().join("|") : "";
  if (state.timelineKey !== tm.key + filterKey) { drawTimeline(); state.timelineKey = tm.key + filterKey; }
  drawFrame();
}
function drawTimeline() {
  const started = performance.now(); const tm = state.time; const ev = state.events; const { index } = ev; const el = layerById("storm_events");
  const on = windowTypes(); const CAP = 6000;
  const counts = new Map(); const marks = [];
  for (let i = tm.range[0]; i < tm.range[1]; i++) { if (!on[ev.type[i]]) continue; counts.set(ev.type[i], (counts.get(ev.type[i]) || 0) + 1); if (marks.length < CAP) marks.push(i); }
  // rows: hail and thunderstorm wind always, then the other types present, by count (fixed order within a window)
  const always = ["Hail", "Thunderstorm Wind"].map((t) => index.types.indexOf(t)).filter((c) => c >= 0);
  const rest = [...counts.keys()].filter((c) => !always.includes(c)).sort((a, b) => counts.get(b) - counts.get(a));
  const rows = [...always, ...rest]; const rowOf = new Map(rows.map((c, k) => [c, k]));
  const box = $("timeline"); const W = Math.max(600, box.clientWidth || 900); const L = 150, R = 12, RH = 16, T = 16; const H = T + rows.length * RH + 4;
  const x = (ms) => L + ((ms - tm.t0) / (tm.t1 - tm.t0)) * (W - L - R);
  state.timelineX = x;
  const span = tm.t1 - tm.t0; const tickStep = span <= 2 * 86400000 ? 6 * 3600000 : span <= 6 * 86400000 ? 12 * 3600000 : 86400000;
  const svg = [`<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Timeline of storm reports">`];
  if (tm.shade) svg.push(`<rect x="${x(tm.shade[0])}" y="${T}" width="${Math.max(2, x(tm.shade[1]) - x(tm.shade[0]))}" height="${rows.length * RH}" fill="#fff3c4"><title>Storm centre over the Texas box</title></rect>`);
  svg.push(`<g class="axis">`);
  for (let t = Math.ceil(tm.t0 / tickStep) * tickStep; t <= tm.t1; t += tickStep) svg.push(`<line x1="${x(t)}" x2="${x(t)}" y1="${T}" y2="${H - 4}"/><text x="${x(t)}" y="11" text-anchor="middle">${new Date(t).getUTCHours() === 0 ? fmtT(t).slice(5, 10) : fmtT(t).slice(11, 16)}</text>`);
  svg.push(`</g>`);
  rows.forEach((c, k) => { const col = eventColor(el, index.types[c]); svg.push(`<circle cx="8" cy="${T + k * RH + RH / 2}" r="4" fill="rgb(${col.join(",")})"/><text class="row-label" x="16" y="${T + k * RH + RH / 2 + 4}">${esc(index.types[c])} (${counts.get(c) || 0})</text><line x1="${L}" x2="${W - R}" y1="${T + (k + 1) * RH}" y2="${T + (k + 1) * RH}" stroke="#eeede9"/>`); });
  const hailC = index.types.indexOf("Hail"), windC = index.types.indexOf("Thunderstorm Wind");
  for (const i of marks) {
    const c = ev.type[i]; const k = rowOf.get(c); const col = eventColor(el, index.types[c]).join(",");
    // hail sized by diameter (0.75 to 4 in), wind by speed (50 to 100 kt); other types a fixed mark
    let s = 0.5; const m = ev.mag[i];
    if (m === m && c === hailC) s = Math.min(1, Math.max(0.15, (m - 0.5) / 3.5)); else if (m === m && c === windC) s = Math.min(1, Math.max(0.15, (m - 40) / 60));
    const h = 4 + s * (RH - 6); const y = T + k * RH + (RH - h) / 2; const located = ev.lon[i] === ev.lon[i];
    const x0 = x(minToMs(ev.begin[i])); const wd = ev.end[i] > ev.begin[i] ? Math.max(1.5, x(minToMs(Math.min(ev.end[i], msToMin(tm.t1)))) - x0) : 0;
    const op = (0.35 + 0.6 * s).toFixed(2);
    svg.push(wd ? `<rect class="mark" data-i="${i}" x="${x0.toFixed(1)}" y="${y.toFixed(1)}" width="${wd.toFixed(1)}" height="${h.toFixed(1)}" rx="1.5" fill="${located ? `rgba(${col},${op})` : "none"}" stroke="rgb(${col})" stroke-width="${located ? 0 : 1}"/>`
      : `<line class="mark" data-i="${i}" x1="${x0.toFixed(1)}" x2="${x0.toFixed(1)}" y1="${y.toFixed(1)}" y2="${(y + h).toFixed(1)}" stroke="rgba(${col},${located ? op : 0.45})" stroke-width="2" ${located ? "" : 'stroke-dasharray="2 2"'}/>`);
  }
  svg.push(`<line class="cursor" x1="${x(tm.now)}" x2="${x(tm.now)}" y1="${T - 4}" y2="${H - 2}"/></svg>`);
  box.innerHTML = svg.join("");
  const total = [...counts.values()].reduce((a, b) => a + b, 0);
  $("timeline-note").textContent = `${total.toLocaleString()} reports begin between ${fmtT(tm.t0)} and ${fmtT(tm.t1)} UTC${total > marks.length ? `; the first ${marks.length.toLocaleString()} are drawn` : ""}. A tick is an instant report, a bar one with a duration; taller and darker = larger hail or stronger wind; dashed or hollow = county/zone report with no point on the map.${tm.shade ? " Shaded: storm centre over the Texas box." : ""}`;
  const tip = $("timeline-tip"); const svgEl = box.querySelector("svg");
  svgEl.onmousemove = (e) => {
    const i = e.target.dataset && e.target.dataset.i; if (i === undefined) { tip.classList.add("hidden"); return; }
    const t = index.types[ev.type[i]]; const m = ev.mag[i]; const u = index.magnitude_units[t];
    tip.textContent = `${t} · ${fmtT(minToMs(ev.begin[i]))} UTC${ev.end[i] > ev.begin[i] ? ` for ${ev.end[i] - ev.begin[i]} min` : ""}${m === m && u ? ` · ${m} ${u}` : ""}${ev.lon[i] === ev.lon[i] ? "" : " · county/zone"}`;
    const r = $("timebar").getBoundingClientRect(); tip.style.left = `${Math.min(r.width - 320, e.clientX - r.left + 10)}px`; tip.style.top = `${e.clientY - r.top - 28 + $("timebar").scrollTop}px`; tip.classList.remove("hidden");
  };
  svgEl.onmouseleave = () => tip.classList.add("hidden");
  svgEl.onclick = (e) => {
    const i = e.target.dataset && e.target.dataset.i; if (i === undefined) { const r = svgEl.getBoundingClientRect(); const px = ((e.clientX - r.left) / r.width) * W; if (px >= L) { stopPlay(); tm.now = Math.min(tm.t1, Math.max(tm.t0, tm.t0 + ((px - L) / (W - L - R)) * (tm.t1 - tm.t0))); drawFrame(); } return; }
    showEvent(el, Number(i)); if (ev.lon[i] === ev.lon[i]) state.map.easeTo({ center: [ev.lon[i], ev.lat[i]], duration: 300 });
  };
  document.body.dataset.timelineMs = (performance.now() - started).toFixed(1); document.body.dataset.timelineMarks = marks.length; document.body.dataset.timelineRows = rows.length;
}

// ---------- charts ----------
function drawCurve(rps, vals, unit, stops) {
  const W = 348, H = 210, m = { l: 48, r: 12, t: 24, b: 32 };
  const pts = rps.map((t, i) => ({ t, v: vals[i], i })).filter((d) => d.v !== null);
  const box = $("chart");
  if (pts.length < 1) { box.innerHTML = `<p class="mute small">No values to draw: this curve has no data at these return periods.</p>`; return; }
  const x = (t) => m.l + ((Math.log10(t) - Math.log10(rps[0])) / (Math.log10(rps[rps.length - 1]) - Math.log10(rps[0]))) * (W - m.l - m.r);
  let vmin = Math.min(...pts.map((d) => d.v)), vmax = Math.max(...pts.map((d) => d.v)); if (!(vmax > vmin)) { vmin -= 1; vmax += 1; }
  const pad = (vmax - vmin) * 0.1; vmin -= pad; vmax += pad;
  const y = (v) => m.t + (1 - (v - vmin) / (vmax - vmin)) * (H - m.t - m.b);
  const line = `rgb(${stops[4].join(",")})`;
  const ticks = 4; const yt = Array.from({ length: ticks + 1 }, (_, k) => vmin + ((vmax - vmin) * k) / ticks);
  const svg = [`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Value against return period">`];
  svg.push(`<g class="axis">`, ...yt.map((v) => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${fmt(v)}</text>`));
  svg.push(...rps.map((t) => `<text x="${x(t)}" y="${H - m.b + 16}" text-anchor="middle">${t}</text>`), `<text x="${(m.l + W - m.r) / 2}" y="${H - 4}" text-anchor="middle">return period, years (log scale)</text>`, `<text x="${m.l - 6}" y="${m.t - 10}" text-anchor="end">${esc(unit)}</text>`, `</g>`);
  svg.push(`<polyline class="curve" stroke="${line}" points="${pts.map((d) => `${x(d.t)},${y(d.v)}`).join(" ")}"/>`);
  svg.push(...pts.map((d) => `<circle class="dot" cx="${x(d.t)}" cy="${y(d.v)}" r="${d.t === state.rp ? 6 : 4}" fill="${line}" data-i="${d.i}"/>`));
  svg.push(`<g id="hover" style="display:none"><line class="cross" y1="${m.t}" y2="${H - m.b}"/><rect fill="#fff" stroke="#d9d7d2" rx="4"/><text class="tip"></text></g>`);
  svg.push(`<rect x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent" id="hit"/>`, `</svg>`);
  box.innerHTML = svg.join("");
  hoverChart(box, pts.map((d) => ({ px: x(d.t), label: `1 in ${d.t}: ${fmt(d.v)} ${unit}` })), m, W, H);
}
function drawSeries(vals, times, unit, stops, inTexas) {
  // along-track series: x = point order (time labels at the ends), y = value; dots mark points inside the Texas box
  const W = 348, H = 190, m = { l: 44, r: 12, t: 22, b: 30 };
  const box = $("chart"); const n = vals.length;
  const pts = vals.map((v, i) => ({ i, v })).filter((d) => d.v !== null);
  if (pts.length < 2) { box.innerHTML = `<p class="mute small">Wind is not given along this track.</p>`; return; }
  const x = (i) => m.l + (i / Math.max(1, n - 1)) * (W - m.l - m.r);
  let vmin = 0, vmax = Math.max(...pts.map((d) => d.v), 40); vmax *= 1.08;
  const y = (v) => m.t + (1 - (v - vmin) / (vmax - vmin)) * (H - m.t - m.b);
  const line = `rgb(${stops[4].join(",")})`; const ticks = 4; const yt = Array.from({ length: ticks + 1 }, (_, k) => vmin + ((vmax - vmin) * k) / ticks);
  const svg = [`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Wind along the track">`, `<g class="axis">`];
  svg.push(...yt.map((v) => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${v.toFixed(0)}</text>`));
  const first = inTexas.indexOf(true), last = inTexas.lastIndexOf(true);
  if (first >= 0) svg.push(`<rect x="${x(first)}" y="${m.t}" width="${Math.max(2, x(last) - x(first))}" height="${H - m.t - m.b}" fill="#fff3c4"/>`);
  svg.push(`<text x="${m.l}" y="${H - m.b + 16}" text-anchor="start">${esc(times[0])}</text>`, `<text x="${W - m.r}" y="${H - m.b + 16}" text-anchor="end">${esc(times[n - 1])}</text>`, `<text x="${(m.l + W - m.r) / 2}" y="${H - 4}" text-anchor="middle">track points in time order (UTC); shaded = over the Texas box</text>`, `<text x="${m.l - 6}" y="${m.t - 8}" text-anchor="end">${esc(unit)}</text>`, `</g>`);
  svg.push(`<polyline class="curve" stroke="${line}" points="${pts.map((d) => `${x(d.i)},${y(d.v)}`).join(" ")}"/>`);
  svg.push(...pts.filter((d) => inTexas[d.i]).map((d) => `<circle class="dot" cx="${x(d.i)}" cy="${y(d.v)}" r="4" fill="${line}"/>`));
  svg.push(`<g id="hover" style="display:none"><line class="cross" y1="${m.t}" y2="${H - m.b}"/><rect fill="#fff" stroke="#d9d7d2" rx="4"/><text class="tip"></text></g>`);
  svg.push(`<rect x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent" id="hit"/>`, `</svg>`);
  svg.splice(svg.length - 2, 0, `<line id="series-cursor" class="cross" style="stroke:#2a2a28;stroke-dasharray:none" y1="${m.t}" y2="${H - m.b}" x1="${m.l}" x2="${m.l}"/>`);
  box.innerHTML = svg.join("");
  const tms = times.map(parseT);
  state.series = (ms) => { let i = 0; while (i + 1 < n && tms[i + 1] <= ms) i++; const f = i + 1 < n && tms[i + 1] > tms[i] ? Math.min(1, Math.max(0, (ms - tms[i]) / (tms[i + 1] - tms[i]))) : 0; return x(i + f); };
  hoverChart(box, pts.map((d) => ({ px: x(d.i), label: `${times[d.i]}: ${d.v} ${unit}` })), m, W, H);
}
function hoverChart(box, marks, m, W, H) {
  const el = box.querySelector("svg"), hover = el.querySelector("#hover"), cross = hover.querySelector("line"), tip = hover.querySelector("text"), rect = hover.querySelector("rect");
  el.querySelector("#hit").addEventListener("mousemove", (ev) => {
    const r = el.getBoundingClientRect(); const px = ((ev.clientX - r.left) / r.width) * W;
    let best = marks[0]; for (const d of marks) if (Math.abs(d.px - px) < Math.abs(best.px - px)) best = d;
    hover.style.display = ""; cross.setAttribute("x1", best.px); cross.setAttribute("x2", best.px);
    tip.textContent = best.label;
    const w = Math.min(W - 40, 8 + best.label.length * 6.2); const tx = Math.min(best.px + 8, W - w - 6); tip.setAttribute("x", tx + 6); tip.setAttribute("y", m.t + 16);
    rect.setAttribute("x", tx); rect.setAttribute("y", m.t + 2); rect.setAttribute("width", w); rect.setAttribute("height", 20);
  });
  el.querySelector("#hit").addEventListener("mouseleave", () => { hover.style.display = "none"; });
}

// ---------- map ----------
function initMap() {
  const b = state.manifest.texas.bounds;
  const map = new maplibregl.Map({
    container: "map", style: state.registry.basemap.style,
    bounds: [[b[0] - 3, b[1] - 3], [b[2] + 3, b[3] + 1]], fitBoundsOptions: { padding: 20 },
    attributionControl: { customAttribution: `${state.registry.basemap.attribution} · data sources credited per source (CRC Open ${state.catalog.licence})` },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  const overlay = new MapboxOverlay({
    interleaved: false, layers: [],
    getTooltip: (info) => {
      if (info.object === undefined || !info.layer) return null;
      if (info.layer.id === "cells") return cellTooltip(info.index);
      if (info.layer.id === "cmp") return compareTooltip(info.index);
      if (info.layer.id === "tracks") return trackTooltip(info.object);
      if ((info.layer.id === "events" || info.layer.id === "window-events") && state.events) return eventTooltip(info.object);
      if (info.layer.id.startsWith("geo:")) return geoTooltip(layerById(info.layer.id.slice(4)), info.object);
      return null;
    },
  });
  map.addControl(overlay);
  state.map = map; state.overlay = overlay;
  return new Promise((resolve) => map.on("load", resolve));
}

// ---------- catalogue (sources) view ----------
function buildCatalog() {
  const { catalog, sources, registry } = state;
  const loaded = new Set(registry.layers.map((l) => l.id));
  $("catalog-sources").innerHTML = `<tr><th>Group</th><th>Source</th><th>Provider</th><th>What it returns</th><th>Coverage here</th><th>Licence</th><th>Status</th></tr>` +
    registry.groups.flatMap((g) => registry.sources.filter((s) => s.origin === g.id)).map((s) => `<tr data-origin="${s.origin}"><td>${badge(s)}</td><td><b>${esc(s.title)}</b></td><td>${esc(s.provider)}</td><td>${esc(s.returns)}</td><td>${esc(s.coverage)}</td><td>${esc(s.licence)}</td><td><span class="pill ${s.status === "loaded" ? "on" : s.status === "prototype" ? "proto" : "plan"}">${s.status}</span></td></tr>`).join("") +
    registry.planned.map((p) => `<tr><td></td><td>${esc(p.title)}</td><td colspan="3" class="mute">${esc(p.status)}</td><td></td><td><span class="pill plan">planned</span></td></tr>`).join("");
  $("catalog-intro").textContent = `Release ${catalog.release} (schema ${catalog.schema_version}), retrieved ${catalog.retrieved_at}. Licence ${catalog.licence}; attribution “${catalog.attribution}”. ${Object.keys(catalog.hazards).length} hazards, pathway ${catalog.pathways.join(", ")}. Generated from the release's own catalogue; nothing here is hand-written.`;
  const rows = Object.entries(catalog.hazards).sort(([a], [b]) => (loaded.has(b) - loaded.has(a)) || a.localeCompare(b));
  const draw = (filter) => {
    const f = filter.trim().toLowerCase();
    $("catalog-table").innerHTML = `<tr><th>Hazard</th><th>Meaning</th><th>Unit</th><th>Tail</th><th class="num">H3</th><th>Probability semantics</th><th>Horizons</th><th>Pooling</th><th class="num">Rows</th><th>Explorer</th><th>Release note</th></tr>` +
      rows.filter(([n, h]) => !f || n.includes(f) || h.value_semantics.toLowerCase().includes(f) || h.unit.toLowerCase().includes(f)).map(([n, h]) => `<tr class="${loaded.has(n) ? "loaded" : ""}"><td>${n}</td><td>${esc(h.value_semantics)}</td><td>${esc(h.unit)}</td><td>${h.tail}</td><td class="num">${h.h3_resolution}</td><td>${h.probability_semantics || "unspecified"}</td><td>${h.horizons[0]}–${h.horizons[h.horizons.length - 1]} (${h.horizons.length})</td><td>${h.pooling}</td><td class="num">${h.rows.toLocaleString()}</td><td>${loaded.has(n) ? `<span class="pill on">loaded</span>` : `<span class="pill">not loaded yet</span>`}</td><td class="small">${esc(h.notes || "")}</td></tr>`).join("");
  };
  draw(""); $("catalog-filter").oninput = (e) => draw(e.target.value);
  $("sources-table").innerHTML = `<tr><th>Source</th><th>Entry point</th><th>Returns</th><th>Coverage</th><th>Licence</th></tr>` + sources.sources.map((s) => `<tr><td>${esc(s.name)}</td><td><code>${esc(s.entry)}</code></td><td>${esc(s.returns)}</td><td>${esc(s.coverage)}</td><td>${esc(s.licence)}</td></tr>`).join("");
  $("not-in-crc").innerHTML = sources.not_in_crc.map((t) => `<li>${esc(t)}</li>`).join("");
}

// ---------- About (every number is read from the data files at load time) ----------
async function buildAbout() {
  const { registry, manifest, catalog } = state;
  const [tracks, evIndex, srcManifest] = await Promise.all([
    fetchJSON(layerById("ibtracs").file).catch(() => null), fetchJSON(layerById("storm_events").index).catch(() => null), fetchJSON("data/sources/manifest.json").catch(() => null),
  ]);
  const n = (v) => (v === null || v === undefined ? "–" : Number(v).toLocaleString());
  const facts = {
    ibtracs: tracks ? `${n(tracks.storms.length)} storms, seasons ${Math.min(...tracks.storms.map((s) => s.season))}–${Math.max(...tracks.storms.map((s) => s.season))}; ${n(tracks.storms.filter((s) => s.extent_points.r34).length)} with wind-radius estimates` : "",
    storm_events: evIndex ? `${n(evIndex.records)} reports ${evIndex.years[0]}–${evIndex.years[1]}, ${n(evIndex.events)} with a point on the map; ${n(evIndex.counts_all.Hail)} hail and ${n(evIndex.counts_all["Thunderstorm Wind"])} thunderstorm-wind reports` : "",
    storm_curves: `${layersOfSource("storm_curves").length} cell layers (${layersOfSource("storm_curves").map((l) => l.title.split(" (")[0].toLowerCase()).join("; ")})`,
    coops: srcManifest && srcManifest.layers.coops ? `${n(srcManifest.layers.coops.stations_with_levels)} stations with published levels` : "",
    ghcnh: srcManifest && srcManifest.layers.ghcnh ? `${n(srcManifest.layers.ghcnh.stations_with_curves)} stations with a fitted curve` : "",
    era5: "",
    crc_open: `${n(Object.keys(catalog.hazards).length)} hazards in the release, ${n(layersOfSource("crc_open").length)} loaded; horizons ${manifest.horizons.join(", ")}; ${n(manifest.texas.cells["5"])} resolution-5 cells over Texas`,
  };
  const groupHtml = registry.groups.map((g) => `<h3><span class="badge" style="--g:${g.color}">${esc(g.badge)}</span> ${esc(g.title)}</h3><p>${esc(g.blurb)}</p><ul>${registry.sources.filter((s) => s.origin === g.id).map((s) => `<li><b>${esc(s.title)}</b> (${esc(s.status)}). ${esc(s.short)} ${facts[s.id] ? `<span class="mute">Now: ${esc(facts[s.id])}.</span>` : ""}</li>`).join("")}</ul>`).join("");
  const licences = `<table><tr><th>Source</th><th>Provider</th><th>Licence and attribution</th></tr>${registry.sources.map((s) => `<tr><td>${badge(s)} ${esc(s.title)}</td><td>${esc(s.provider)}</td><td>${esc(s.licence)}</td></tr>`).join("")}<tr><td>Basemap</td><td colspan="2">${esc(registry.basemap.attribution)}</td></tr></table>`;
  const repo = "https://github.com/shlyakh/crc-lab"; const rep = (f, t) => `<a href="${repo}/blob/main/docs/reports/${f}" target="_blank" rel="noopener">${t}</a>`;
  const video = Boolean(registry.demo && registry.demo.video);
  $("about").innerHTML = `
    <h2 style="margin-top:0">What this page is</h2>
    <p class="lead">A map of Texas for looking at climate and severe-weather data sources side by side: where storms tracked, what was reported on the ground, and what fitted hazard curves say, each shown the way its source publishes it.</p>
    <p>It is part of <a href="${repo}" target="_blank" rel="noopener">crc-lab</a>, a project by Yuri Shlyakhter that works with Climate Risk Commons data, Texas first. <button id="about-demo" class="demo-btn" style="margin-left:0">▶ Play the 30-second demo</button></p>
    ${video ? `<p class="mute">Or watch a recording of the demo:</p><video src="${esc(registry.demo.video)}" controls preload="none" width="720"></video>` : ""}
    <h2>Climate Risk Commons and crc-sdk</h2>
    <p>Climate Risk Commons (CRC) is an open project that publishes climate hazard data as fitted curves: for a place and a period, the distribution of an annual value such as the hottest day. crc-sdk is its Python toolkit; it reads many public sources through one interface and keeps the licence, retrieval time and checksum of what it reads. This page was built with crc-sdk ${esc(manifest.versions["crc-sdk"])} and crc-framework ${esc(manifest.versions["crc-framework"])}.</p>
    <h2>Two groups of sources</h2>
    ${groupHtml}
    <h2>How to use it</h2>
    <ul>
      <li><b>Pick a source</b> on the left of the Map tab. Its filters, legend and caveats appear below the list; "Also show" draws other sources on top.</li>
      <li><b>Click</b> a track, a report, a station or a cell for its details and, where there is one, its curve.</li>
      <li><b>Storm player:</b> select a cyclone to get a time bar under the map. Play it to watch the centre and its wind-radius outlines move while storm reports appear as the clock passes them.</li>
      <li><b>Timeline:</b> the strip under the player has one row per report type; a tick is an instant, a bar a report with a duration. Click a mark to open the report, or empty space to move the clock.</li>
      <li><b>Date window:</b> on Storm reports, "Explore a date window" gives the same timeline for any 1 to 14 days, for example a spring hail outbreak.</li>
      <li><b>Sources tab:</b> every source with what it returns, its coverage and licence, and the full CRC Open hazard list.</li>
    </ul>
    <h2>What the numbers mean, and do not mean</h2>
    <ul>
      <li><b>Regional screening.</b> A cell value is the curve for a whole H3 cell (about 253 km² at resolution 5), not for any site inside it.</li>
      <li><b>Reports follow people.</b> Storm reports come from the public, spotters and officials; an empty area may be unobserved, not calm. The hail and gust curves are built from those reports and inherit that bias.</li>
      <li><b>CRC Open is one scenario.</b> RiskThinking.AI's CMIP6-based projections under the high-emissions pathway SSP5-8.5: a "what if", not a forecast, with no historical baseline in the release.</li>
      <li><b>Wind radii are estimates.</b> The shaded bands around a cyclone are US agency estimates of how far 34, 50 and 64 kt winds reached in each quadrant, not damage footprints; older storms have none.</li>
      <li><b>Track points are the storm centre,</b> with the agency's maximum sustained wind near it, not the wind at any place.</li>
      <li><b>Times are UTC,</b> converted from the local standard time the National Weather Service records; summer times can be an hour off true local time, and many report times are rounded.</li>
      <li><b>Return periods</b> ("1 in 100 years") are read from each curve as its source defines it; curves were evaluated by crc-sdk during the build and the page only draws them.</li>
    </ul>
    <h2>Licences and attribution</h2>
    ${licences}
    <h2>Versions and build</h2>
    <p>Built ${esc(manifest.built_at)} with crc-sdk ${esc(manifest.versions["crc-sdk"])} and crc-framework ${esc(manifest.versions["crc-framework"])}. CRC Open release <code>${esc(catalog.release)}</code>${tracks ? `; IBTrACS snapshot retrieved ${esc((tracks.retrieved_at || "").slice(0, 10))} (SHA-256 ${esc((tracks.sha256 || "").slice(0, 12))}…)` : ""}${evIndex ? `; Storm Events snapshot retrieved ${esc((evIndex.retrieved_at || "").slice(0, 10))}` : ""}. Code: AGPL-3.0-or-later.</p>
    <h2>Read more</h2>
    <p>${rep("1-explorer.md", "Explorer v1")} · ${rep("2-storm-events.md", "Storm Events source")} · ${rep("2-storm-events-comparison.md", "two-source comparison")} · ${rep("3-curves.md", "hail and gust curves")} · <a href="${repo}/blob/explorer-v2/docs/reports/E2-explorer-v2.md" target="_blank" rel="noopener">explorer v2</a> · <a href="${repo}/blob/explorer-v2/docs/reports/E3-time-and-extent.md" target="_blank" rel="noopener">time and extent</a> · <a href="${repo}" target="_blank" rel="noopener">repository</a></p>`;
  $("about-demo").onclick = () => runDemo();
  document.body.dataset.about = "1";
}

// ---------- demo: a scripted tour that drives the real page ----------
const demo = { running: false, abort: false, paused: false, next: null };
function demoCaption(html, i, n) { $("demo-caption").innerHTML = html; $("demo-step").textContent = `${i} of ${n}`; }
async function demoWait(ms, onFrame) {
  // waits `ms` of un-paused time; calls onFrame(fraction) every animation frame
  let elapsed = 0; let last = performance.now();
  while (elapsed < ms) {
    await new Promise((r) => requestAnimationFrame(r));
    const now = performance.now(); if (demo.abort) throw new Error("demo stopped");
    if (!demo.paused) { elapsed += now - last; demo.elapsed += now - last; if (onFrame) onFrame(Math.min(1, elapsed / ms)); $("demo-progress").firstElementChild.style.width = `${Math.min(100, (demo.elapsed / demo.total) * 100)}%`; }
    last = now;
  }
}
function demoNext() { return new Promise((resolve, reject) => { demo.next = () => { demo.next = null; if (demo.abort) reject(new Error("demo stopped")); else resolve(); }; }); }
async function runDemo() {
  if (demo.running || !state.map) return;
  const spec = state.registry.demo; const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  Object.assign(demo, { running: true, abort: false, paused: false, elapsed: 0, total: spec.seconds * 1000 });
  const t0 = performance.now(); document.body.dataset.demo = "running";
  $("demo-bar").classList.remove("hidden"); $("demo-next").classList.toggle("hidden", !reduced); $("demo-pause").classList.toggle("hidden", reduced); $("demo-pause").textContent = "Pause";
  $("demo-pause").onclick = () => { demo.paused = !demo.paused; $("demo-pause").textContent = demo.paused ? "Resume" : "Pause"; };
  $("demo-stop").onclick = () => { demo.abort = true; if (demo.next) demo.next(); };
  $("demo-next").onclick = () => { if (demo.next) demo.next(); };
  const onKey = (e) => { if (e.key === "Escape") { demo.abort = true; if (demo.next) demo.next(); } }; document.addEventListener("keydown", onKey);
  demoCaption("Loading what the tour needs…", 0, 8);
  // preload so no step stalls; a failed file makes its step skip
  const ok = {}; const pre = async (k, f) => { try { await f(); ok[k] = true; } catch (e) { ok[k] = false; } };
  await Promise.all([pre("tracks", () => loadTracks(layerById("ibtracs"))), pre("events", () => loadEvents(layerById("storm_events"))), pre("curve", () => loadFile(spec.curve_layer, horizonsOf(layerById(spec.curve_layer))[0])), pre("crc", () => loadFile(state.registry.defaults.crc_hazard, state.registry.defaults.horizon))]);
  const hold = (ms, onFrame) => (reduced ? (onFrame && onFrame(1), demoNext()) : demoWait(ms, onFrame));
  const skipped = (what) => `<span class="mute">(${what} could not be loaded; step skipped)</span>`;
  const b = state.manifest.texas.bounds; const texasView = () => { state.map.resize(); state.map.fitBounds([[b[0] - 1, b[1] - 1], [b[2] + 1, b[3] + 0.5]], { padding: 20, duration: reduced ? 0 : 600 }); };
  const N = 8;
  try {
    // 1. overview of tracks
    state.showView("map"); Object.assign(state.tracksFilter, { name: "", minWind: 0, colorBy: "wind" }); state.storm = null; state.win.on = false; state.extent = true;
    await selectSource("ibtracs", true); texasView();
    demoCaption(ok.tracks ? `<b>Tropical cyclone tracks.</b> ${state.tracks.storms.length} storms that crossed Texas since ${Math.min(...state.tracks.storms.map((s) => s.season))}, read through crc-sdk and coloured by wind.` : skipped("IBTrACS"), 1, N);
    await hold(3000);
    // 2. one storm with its wind extent
    const storm = ok.tracks ? state.tracks.storms.find((s) => s.name === spec.storm.name && s.season === spec.storm.season) || state.tracks.storms.filter((s) => s.extent_points.r34).pop() : null;
    if (storm) {
      state.storm = storm.sid; await render(); showStorm(storm);
      const xs = storm.points.map((p) => p[0]), ys = storm.points.map((p) => p[1]); const a = parseT(storm.first_texas_point) - 86400000, z = parseT(storm.last_texas_point) + 86400000; const near = storm.points.filter((p) => parseT(p[5]) >= a && parseT(p[5]) <= z);
      const nx = near.map((p) => p[0]), ny = near.map((p) => p[1]);
      state.map.fitBounds([[Math.min(...nx) - 2.5, Math.min(...ny) - 2], [Math.max(...nx) + 2.5, Math.max(...ny) + 2]], { padding: 30, duration: reduced ? 0 : 800 });
      demoCaption(`<b>${esc(storm.label)}.</b> The shaded bands are agency estimates of how far 34, 50 and 64 kt winds reached${storm.extent_points.r34 ? "" : " (none exist for this storm)"}; peak wind ${storm.max_wind_kt} kt.`, 2, N);
      await hold(4000);
      // 3. play it with reports
      const tm = state.time;
      if (tm && ok.events) {
        demoCaption(`<b>Playing the storm.</b> The centre moves along its track while National Weather Service storm reports appear as the clock passes them; the strip below is the timeline.`, 3, N);
        await hold(7000, (f) => { tm.now = tm.t0 + f * (tm.t1 - tm.t0); drawFrame(); });
      } else { demoCaption(skipped("Storm reports"), 3, N); await hold(1500); demo.total -= 5500; }
    } else { demoCaption(skipped("IBTrACS"), 2, N); await hold(1500); demo.total -= 9500; }
    // 4. hail outbreak window
    if (ok.events) {
      state.storm = null; $("detail").classList.add("hidden"); Object.assign(state.win, { on: true, start: spec.window.start, days: spec.window.days });
      state.eventsFilter.types = new Set(["Hail", "Thunderstorm Wind"]);
      await selectSource("storm_events", true); texasView();
      const tm = state.time; const hail = state.events.index.types.indexOf("Hail"); let nh = 0; for (let i = tm.range[0]; i < tm.range[1]; i++) if (state.events.type[i] === hail) nh++;
      demoCaption(`<b>Storm reports, new in this project.</b> ${state.win.days} days from ${state.win.start}: ${nh} hail reports across Texas, each placed at its time and size.`, 4, N);
      await hold(5000, (f) => { tm.now = tm.t0 + Math.min(1, f * 1.15) * (tm.t1 - tm.t0); drawFrame(); });
      state.win.on = false;
    } else { demoCaption(skipped("Storm reports"), 4, N); await hold(1500); demo.total -= 3500; }
    // 5. hail curve layer and one cell's curve
    if (ok.curve) {
      await selectSource("storm_curves", true); state.hazard = spec.curve_layer; state.horizon = horizonsOf(layerById(spec.curve_layer))[0]; state.domain = null; await render();
      const payload = state.files.get(fileKey(state.hazard, state.horizon)); const k = state.manifest.return_periods.indexOf(state.rp); let best = 0; payload.values.forEach((v, i) => { if (v[k] !== null && v[k] > (payload.values[best][k] ?? -1)) best = i; });
      showDetail(best);
      demoCaption(`<b>Hail curves fitted from those reports.</b> Each cell gets a curve of the largest hail of the year; here the cell with the highest 1-in-${state.rp}-year value.`, 5, N);
      await hold(4000);
    } else { demoCaption(skipped("The hail curve layer"), 5, N); await hold(1500); demo.total -= 2500; }
    // 6. CRC Open as one source
    if (ok.crc) {
      $("detail").classList.add("hidden"); state.selected = null; await selectSource("crc_open", true);
      demoCaption(`<b>CRC Open, one source among the others.</b> RiskThinking.AI's CMIP6-based projections under SSP5-8.5: ${Object.keys(state.catalog.hazards).length} hazards on cells, a what-if, not a forecast.`, 6, N);
      await hold(3000);
    } else { demoCaption(skipped("CRC Open"), 6, N); await hold(1500); demo.total -= 1500; }
    // 7. Sources tab
    state.showView("catalog");
    demoCaption(`<b>Sources.</b> Two groups: ${state.registry.groups.map((g) => `${esc(g.title.toLowerCase())} (${state.registry.sources.filter((s) => s.origin === g.id).length})`).join(" and ")}, each with what it returns, coverage and licence.`, 7, N);
    await hold(2000);
    // 8. end card
    demoCaption(`<b>That is the tour.</b> Pick a source and explore; the About tab explains what the numbers mean.`, 8, N);
    await hold(2000);
    document.body.dataset.demoTourMs = (performance.now() - t0).toFixed(0); document.body.dataset.demo = "done";
  } catch (e) { document.body.dataset.demo = demo.abort ? "stopped" : `error: ${e.message}`; }
  // leave the page in its normal state
  document.removeEventListener("keydown", onKey); $("demo-bar").classList.add("hidden");
  state.win.on = false; state.storm = null; state.selected = null; $("detail").classList.add("hidden");
  if (state.events) state.eventsFilter.types = new Set((layerById("storm_events").default_types || []).filter((t) => state.events.index.types.includes(t)));
  state.showView("map"); await selectSource(state.registry.defaults.source, true); texasView();
  demo.running = false; document.body.dataset.demoMs = (performance.now() - t0).toFixed(0);
}

// ---------- wiring ----------
async function main() {
  $("status").textContent = "Loading registry and catalogue…";
  const [registry, catalog, manifest, sources, texas] = await Promise.all([
    fetchJSON("layers.json"), fetchJSON("data/catalog.json"), fetchJSON("data/manifest.json"), fetchJSON("sources.json"), fetchJSON("data/texas.geojson"),
  ]);
  Object.assign(state, { registry, catalog, manifest, sources, texas });
  state.source = registry.defaults.source; state.hazard = registry.defaults.crc_hazard; state.horizon = registry.defaults.horizon; state.rp = registry.defaults.return_period;
  for (const l of registry.layers) state.overlays.set(l.id, l.on === true);
  $("release").innerHTML = `${registry.sources.length} sources read through crc-sdk ${esc(manifest.versions["crc-sdk"])} · built ${esc(manifest.built_at.slice(0, 10))}<br>Texas · every value shown as its source publishes it`;
  buildSourceList(); buildCatalog();
  $("demo-start").onclick = () => runDemo();
  $("hazard").onchange = (e) => {
    state.hazard = e.target.value; state.selected = null;
    const horizons = horizonsOf(layerById(state.hazard)); if (!horizons.includes(state.horizon)) state.horizon = horizons[0];
    render();
  };
  $("horizon").onchange = (e) => { state.horizon = Number(e.target.value); render(); };
  $("rp").onchange = (e) => { state.rp = Number(e.target.value); render(); };
  $("lock").onchange = (e) => { state.locked = e.target.checked; if (!state.locked) render(); };
  $("detail-close").onclick = () => { state.selected = null; if (state.storm !== null) { state.storm = null; render(); } $("detail").classList.add("hidden"); };
  for (const b of document.querySelectorAll(".tab")) b.onclick = () => {
    for (const t of document.querySelectorAll(".tab")) t.classList.toggle("on", t === b);
    for (const v of document.querySelectorAll(".view")) v.classList.toggle("on", v.id === `view-${b.dataset.view}`);
    if (b.dataset.view === "map") state.map.resize();
  };
  state.showView = (name) => document.querySelector(`.tab[data-view=${name}]`).click();
  let tlWidth = 0; new ResizeObserver(() => { const w = $("timeline").clientWidth; if (state.time && w && Math.abs(w - tlWidth) > 8) { tlWidth = w; drawTimeline(); if (state.map) state.map.resize(); } }).observe($("timeline"));
  $("status").textContent = "Loading the base map…";
  await initMap();
  document.addEventListener("crc:flyTo", (e) => state.map.jumpTo({ center: e.detail.center, zoom: e.detail.zoom }));
  document.addEventListener("crc:source", (e) => selectSource(e.detail));
  document.addEventListener("crc:compare", (e) => { if (state.cmp) { Object.assign(state.cmp, e.detail); render(); } });
  wireCompare();
  document.addEventListener("crc:time", (e) => { if (state.time) { stopPlay(); state.time.now = state.time.t0 + e.detail * (state.time.t1 - state.time.t0); drawFrame(); } });
  $("status").textContent = "Loading the first source…";
  await render();
  buildAbout().catch((e) => { $("about").innerHTML = `<p>Could not build this page: ${esc(e.message)}</p>`; });
  if (new URLSearchParams(location.search).get("demo") === "1") runDemo();
}
main().catch((e) => { $("status").textContent = `Failed to start: ${e.message}`; document.body.dataset.error = e.message; console.error(e); });
