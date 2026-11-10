// Texas climate data explorer (v2, source-centric). No build step: MapLibre (ESM) + deck.gl (UMD global `deck`).
import * as maplibregl from "https://cdn.jsdelivr.net/npm/maplibre-gl@6.16.0/dist/maplibre-gl.mjs";

const { MapboxOverlay, H3HexagonLayer, GeoJsonLayer, ScatterplotLayer, LineLayer } = globalThis.deck;
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
  map: null, overlay: null,
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
const cellSource = (id) => layersOfSource(id).some((l) => l.kind === "h3-cells");

// ---------- source list and per-source panel ----------
function buildSourceList() {
  const box = $("sources"); box.innerHTML = "";
  for (const s of state.registry.sources) {
    const b = document.createElement("button"); b.className = "src" + (s.id === state.source ? " on" : ""); b.dataset.id = s.id;
    b.innerHTML = `<span class="t">${esc(s.title)}</span><span class="s">${esc(s.short)}</span><span class="pills"><span class="pill ${s.status === "loaded" ? "on" : s.status === "prototype" ? "proto" : "plan"}">${s.status}</span><span class="pill">${esc(s.licence.split(";")[0].split("(")[0].trim())}</span></span>`;
    b.onclick = () => selectSource(s.id);
    box.append(b);
  }
}

function selectSource(id) {
  if (state.source === id) return;
  state.source = id; state.selected = null; state.storm = null; $("detail").classList.add("hidden");
  const cells = layersOfSource(id).filter((l) => l.kind === "h3-cells");
  if (cells.length) {
    state.hazard = id === "crc_open" ? state.registry.defaults.crc_hazard : cells[0].id;
    const hs = horizonsOf(layerById(state.hazard)); if (!hs.includes(state.horizon)) state.horizon = hs[0];
    state.domain = null;
  }
  buildSourceList(); render();
}

function buildSourcePanel() {
  const s = sourceById(state.source);
  $("source-blurb").innerHTML = `<b>${esc(s.title)}</b> · ${esc(s.provider)}<br>${esc(s.returns)}<br><span>Coverage: ${esc(s.coverage)}. Licence: ${esc(s.licence)}.</span>`;
  for (const el of document.querySelectorAll("#source-panel .ctl")) el.classList.add("hidden");
  const show = (id) => $(id).classList.remove("hidden");
  if (state.source === "ibtracs") { show("ctl-ibtracs"); buildTracksControls(); }
  else if (state.source === "storm_events") { show("ctl-storm_events"); buildEventsControls(); }
  else if (cellSource(state.source)) { show("ctl-cells"); buildCellControls(); }
  else { show("ctl-stations"); buildStationsList(); }
}

function buildOverlays() {
  const box = $("overlays"); box.innerHTML = "";
  const own = new Set(layersOfSource(state.source).map((l) => l.id));
  for (const l of state.registry.layers) {
    if (l.kind === "h3-cells" && l.id !== state.hazard) continue;
    if (l.kind === "h3-cells" && !own.has(l.id)) continue; // cells only through their source
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
  const items = (s.caveats || []).map((t) => `<b>${esc(s.title)}:</b> ${esc(t)}`);
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
  const legend = $("tracks-legend");
  if (f.colorBy === "wind") legend.innerHTML = `<div style="width:100%"><div class="bar" style="background:${gradient(stops.slice(2))}"></div><div style="display:flex;justify-content:space-between"><span>≤ ${WIND_DOMAIN[0]} kt</span><span>agency wind along the track</span><span>≥ ${WIND_DOMAIN[1]} kt</span></div></div>`;
  else legend.innerHTML = [["-5", "not a tropical cyclone / unknown"], ["-1", "tropical depression"], ["0", "tropical storm"], ["1", "category 1"], ["2", "category 2"], ["3", "category 3"], ["4", "category 4"], ["5", "category 5"]].map(([k, t]) => `<span><i class="sw" style="background:rgb(${layer.style.category_colors[k].join(",")})"></i>${t}</span>`).join("");
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
  return [new LineLayer({
    id: "tracks", data: segments, pickable: true, widthUnits: "pixels",
    getSourcePosition: (d) => d.a, getTargetPosition: (d) => d.b, getColor: color, getWidth: (d) => (d.sid === state.storm ? 4 : 2),
    updateTriggers: { getColor: [f.colorBy, state.storm], getWidth: [state.storm] },
    onClick: (info) => { const s = state.tracks.storms.find((x) => x.sid === info.object.sid); state.storm = s.sid; render(); showStorm(s); return true; },
  })];
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
  const year = new Uint16Array(n), type = new Uint8Array(n), id = new Uint32Array(n);
  const off = Object.fromEntries(index.fields.map((f) => [f.name, f.offset])); const rb = index.record_bytes;
  for (let i = 0; i < n; i++) {
    const b = i * rb;
    lon[i] = view.getFloat32(b + off.lon, true); lat[i] = view.getFloat32(b + off.lat, true);
    year[i] = view.getUint16(b + off.year, true); type[i] = view.getUint8(b + off.type);
    mag[i] = view.getFloat32(b + off.magnitude, true); id[i] = view.getUint32(b + off.event_id, true);
    dmg[i] = view.getFloat32(b + off.damage_usd, true);
  }
  state.events = { index, n, lon, lat, year, type, mag, id, dmg };
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
  const keep = []; for (let i = 0; i < ev.n; i++) if (typeOn[ev.type[i]] && ev.year[i] >= f.from && ev.year[i] <= f.to) keep.push(i);
  $("events-status").textContent = `${keep.length.toLocaleString()} of ${ev.n.toLocaleString()} located reports shown (${f.from}–${f.to}). ${index.events_without_point.toLocaleString()} county/zone reports have no point and are not drawn.`;
  const colors = index.types.map((t) => eventColor(layer, t));
  return new ScatterplotLayer({
    id: "events", data: keep, pickable: true, radiusUnits: "pixels", getRadius: 3, radiusMinPixels: 2, radiusMaxPixels: 6,
    stroked: true, lineWidthMinPixels: 1, getLineColor: [255, 255, 255, 160], opacity: 0.85,
    getPosition: (i) => [ev.lon[i], ev.lat[i]], getFillColor: (i) => colors[ev.type[i]],
    updateTriggers: { getFillColor: [layer.id] },
    onClick: (info) => { showEvent(layer, info.object); return true; },
  });
}
function eventTooltip(i) { const ev = state.events; const t = ev.index.types[ev.type[i]]; const m = Number.isNaN(ev.mag[i]) ? "" : ` · ${ev.mag[i]} ${ev.index.magnitude_units[t] || ""}`; return { text: `${t}, ${ev.year[i]}${m}` }; }
function showEvent(layer, i) {
  const ev = state.events; const { index } = ev; const t = index.types[ev.type[i]];
  const unit = index.magnitude_units[t]; const mag = Number.isNaN(ev.mag[i]) ? null : ev.mag[i]; const dmg = Number.isNaN(ev.dmg[i]) ? null : ev.dmg[i];
  state.selected = null;
  $("detail").classList.remove("hidden");
  $("detail-title").textContent = `${t}, ${ev.year[i]}`;
  const url = layer.detail_url ? layer.detail_url.replace("{event_id}", ev.id[i]) : null;
  $("detail-meta").innerHTML = [
    ["Event", url ? `<a href="${url}" target="_blank" rel="noopener">${ev.id[i]} at NCEI</a>` : ev.id[i]],
    ["Location", `${ev.lat[i].toFixed(3)}°N, ${(-ev.lon[i]).toFixed(3)}°W (first point)`],
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
  const meta = [["Layer", l.title], ["Source", l.source]];
  for (const [k, v] of Object.entries(p)) if (!skip.has(k) && v !== null && typeof v !== "object") meta.push([k.replaceAll("_", " "), String(v)]);
  $("detail-meta").innerHTML = meta.map(([k, v]) => `<b>${esc(k)}</b><span>${esc(v)}</span>`).join("");
  $("detail-params").innerHTML = ""; $("detail-foot").textContent = l.caveat || "";
  const c = p.curve;
  if (c && Array.isArray(c.return_periods) && Array.isArray(c.values)) {
    $("detail-table").innerHTML = `<tr><th>Return period</th><th class="num">${esc(c.unit || "")}</th></tr>` + c.return_periods.map((t, i) => `<tr><td>1 in ${t} years</td><td class="num">${fmt(c.values[i])}</td></tr>`).join("");
    drawCurve(c.return_periods, c.values, c.unit || "", ramp(l.style && l.style.hue !== undefined ? l.style : { hue: 250, chroma: 0.14 }));
    if (c.note) $("detail-params").innerHTML = `<b>Curve</b><span>${esc(c.note)}</span>`;
  } else { $("detail-table").innerHTML = ""; $("chart").innerHTML = ""; }
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
      else if (l.kind === "points-binary") { await loadEvents(l); if (token !== rendering) return; layers.push(eventsLayer(l)); if (l.source_id === src) count = `${state.events.n.toLocaleString()} reports`; }
      else if (l.kind === "points" || l.kind === "lines") { const data = await loadGeo(l); if (token !== rendering) return; layers.push(geoLayer(l, data)); if (l.source_id === src) count = `${data.features.length} stations`; }
      if (fetched === started) fetched = performance.now();
    }
  } catch (e) { $("status").textContent = `Could not load ${src}: ${e.message}`; document.body.dataset.error = e.message; return; }
  if (state.overlays.get("texas") !== false) layers.push(new GeoJsonLayer({ id: "texas", data: state.texas, stroked: true, filled: false, getLineColor: layerById("texas").style.line, lineWidthMinPixels: layerById("texas").style.width, pickable: false }));
  state.overlay.setProps({ layers });
  buildSourcePanel(); buildOverlays(); buildCaveats(payload);
  if (state.selected && (state.selected.hazard !== state.hazard || state.selected.horizon !== state.horizon)) { state.selected = null; $("detail").classList.add("hidden"); }
  else if (state.selected && cellSource(src)) showDetail(state.selected.index);
  requestAnimationFrame(() => {
    if (token !== rendering) return;
    const total = performance.now() - started;
    $("status").textContent = `${count} · ${(fetched - started).toFixed(0)} ms load, ${total.toFixed(0)} ms to view`;
    document.body.dataset.ready = "1"; document.body.dataset.ms = total.toFixed(0); document.body.dataset.source = src;
  });
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
  box.innerHTML = svg.join("");
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
      if (info.layer.id === "tracks") return trackTooltip(info.object);
      if (info.layer.id === "events" && state.events) return eventTooltip(info.object);
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
  $("catalog-sources").innerHTML = `<tr><th>Source</th><th>Provider, via crc-sdk</th><th>What it returns</th><th>Coverage here</th><th>Licence</th><th>Status</th></tr>` +
    registry.sources.map((s) => `<tr><td><b>${esc(s.title)}</b></td><td>${esc(s.provider)}</td><td>${esc(s.returns)}</td><td>${esc(s.coverage)}</td><td>${esc(s.licence)}</td><td><span class="pill ${s.status === "loaded" ? "on" : s.status === "prototype" ? "proto" : "plan"}">${s.status}</span></td></tr>`).join("") +
    registry.planned.map((p) => `<tr><td>${esc(p.title)}</td><td colspan="3" class="mute">${esc(p.status)}</td><td></td><td><span class="pill plan">planned</span></td></tr>`).join("");
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
  $("status").textContent = "Loading the base map…";
  await initMap();
  document.addEventListener("crc:flyTo", (e) => state.map.jumpTo({ center: e.detail.center, zoom: e.detail.zoom }));
  document.addEventListener("crc:source", (e) => selectSource(e.detail));
  $("status").textContent = "Loading the first source…";
  await render();
}
main().catch((e) => { $("status").textContent = `Failed to start: ${e.message}`; document.body.dataset.error = e.message; console.error(e); });
