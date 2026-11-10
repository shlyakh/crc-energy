// CRC Open explorer, Texas. No build step: MapLibre (ESM) + deck.gl (UMD global `deck`).
import * as maplibregl from "https://cdn.jsdelivr.net/npm/maplibre-gl@6.16.0/dist/maplibre-gl.mjs";

const { MapboxOverlay, H3HexagonLayer, GeoJsonLayer, ScatterplotLayer } = globalThis.deck;
const $ = (id) => document.getElementById(id);

const state = {
  registry: null, catalog: null, manifest: null, sources: null,
  hazard: null, horizon: null, rp: null,
  files: new Map(),          // "hazard/horizon" -> payload
  domain: null, locked: false,
  layersOn: new Map(),       // layer id -> boolean
  selected: null,            // { hazard, horizon, index }
  map: null, overlay: null, texas: null,
  events: null,              // decoded points-binary layer { index, lon, lat, year, type, mag, id, dmg }
  eventsFilter: { from: null, to: null, types: null },
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
function colorAt(stops, t) {
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x)); const f = x - i;
  const a = stops[i], b = stops[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, 215];
}
const NODATA = [201, 199, 193, 140];

// ---------- helpers ----------
const layerById = (id) => state.registry.layers.find((l) => l.id === id);
const fileKey = (h, y) => `${h}/${y}`;
function display(layer, v) { // source unit -> display unit
  if (v === null || v === undefined) return null;
  const d = layer.display; return d ? v + (d.offset || 0) : v;
}
function unitOf(layer, payload) { return (layer.display && layer.display.unit) || payload.unit; }
function fmt(v, digits = 3) {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const a = Math.abs(v);
  if (a >= 100) return v.toFixed(0); if (a >= 10) return v.toFixed(1); if (a >= 1) return v.toFixed(2);
  return v.toPrecision(digits);
}
function quantile(sorted, q) { if (!sorted.length) return NaN; const i = (sorted.length - 1) * q; const lo = Math.floor(i); return sorted[lo] + (sorted[Math.min(lo + 1, sorted.length - 1)] - sorted[lo]) * (i - lo); }

async function fetchJSON(url) { const r = await fetch(url); if (!r.ok) throw new Error(`${url}: ${r.status}`); return r.json(); }
async function loadFile(hazard, horizon) {
  const key = fileKey(hazard, horizon);
  if (!state.files.has(key)) {
    const layer = layerById(hazard);
    state.files.set(key, await fetchJSON(layer.file.replace("{horizon}", horizon)));
  }
  return state.files.get(key);
}

// A layer may carry its own horizons (sources track: ERA5 baseline has one window centre).
const horizonsOf = (layer) => (layer && layer.horizons) || state.manifest.horizons;

// ---------- UI build ----------
function buildSelectors() {
  const { catalog, registry } = state;
  const loaded = registry.layers.filter((l) => l.kind === "h3-cells").map((l) => l.id);
  const sel = $("hazard"); sel.innerHTML = "";
  const g1 = document.createElement("optgroup"); g1.label = `Loaded (${loaded.length})`;
  for (const id of loaded) { const o = new Option(`${layerById(id).title} · ${id}`, id); g1.append(o); }
  const g2 = document.createElement("optgroup"); const rest = Object.keys(catalog.hazards).filter((h) => !loaded.includes(h));
  g2.label = `In the release, not loaded yet (${rest.length})`;
  for (const id of rest) { const o = new Option(`${id} · ${catalog.hazards[id].value_semantics} (not loaded yet)`, id); o.disabled = true; g2.append(o); }
  const g3 = document.createElement("optgroup"); g3.label = `Planned (${registry.planned.length})`;
  for (const p of registry.planned) { const o = new Option(`${p.title} · ${p.status}`, p.id); o.disabled = true; g3.append(o); }
  sel.append(g1, g2, g3);
  sel.value = state.hazard;

  const hz = $("horizon"); hz.innerHTML = "";
  for (const y of horizonsOf(layerById(state.hazard))) hz.append(new Option(String(y), y));
  hz.value = state.horizon;
  const rp = $("rp"); rp.innerHTML = "";
  for (const t of state.manifest.return_periods) rp.append(new Option(`1 in ${t} years`, t));
  rp.value = state.rp;

  const box = $("layers"); box.innerHTML = "";
  for (const l of registry.layers) {
    if (l.kind === "h3-cells" && l.id !== state.hazard) continue; // one hazard layer at a time
    const lab = document.createElement("label");
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = state.layersOn.get(l.id) !== false;
    cb.onchange = () => { state.layersOn.set(l.id, cb.checked); if (l.kind === "points-binary") toggleEventsControls(l); render(); };
    lab.append(cb, document.createTextNode(l.title), Object.assign(document.createElement("span"), { className: "mute", textContent: l.source }));
    box.append(lab);
  }
  for (const p of registry.planned) {
    const lab = document.createElement("label"); const cb = document.createElement("input"); cb.type = "checkbox"; cb.disabled = true;
    lab.append(cb, document.createTextNode(p.title), Object.assign(document.createElement("span"), { className: "mute", textContent: p.status }));
    box.append(lab);
  }
}

function buildCaveats(payload) {
  const { catalog, manifest } = state; const layer = layerById(state.hazard);
  const res = payload.h3_resolution; const km2 = res === 5 ? "about 253 km²" : res === 7 ? "about 5.2 km²" : `resolution ${res}`;
  const crcOpen = layer.source === "CRC Open";
  const items = crcOpen ? [
    `<b>High-emissions case (SSP5-8.5), not a forecast.</b> One pathway, pooled model ensemble, no historical baseline in the release.`,
    `<b>Regional screening.</b> Each cell is ${km2} (H3 resolution ${res}); a value is the curve for the whole cell, not any site in it.`,
    `<b>Source:</b> CRC Open release <code>${catalog.release}</code>, licence ${catalog.licence} (non-commercial, with attribution). Attribution: ${catalog.attribution}.`,
    `<b>Curve:</b> ${payload.value_semantics}; probability semantics ${payload.probability_semantics || "unspecified"}; return periods read on the ${payload.tail} tail (1 in T years = non-exceedance ${payload.tail === "upper" ? "1 − 1/T" : "1/T"}).`,
    `<b>Cells:</b> every resolution-${res} cell that intersects the Texas boundary (${manifest.texas.cells[res]} cells); cells with no curve in the release are not drawn.`,
  ] : [
    `<b>${layer.title}.</b> ${layer.caveat || ""}`,
    `<b>Source:</b> ${layer.source}; licence ${layer.licence}.`,
    `<b>Curve:</b> ${payload.value_semantics}; probability semantics ${payload.probability_semantics || "unspecified"}; return periods read on the ${payload.tail} tail.`,
    `<b>Cells:</b> ${payload.cells.length} cells at H3 resolution ${res} inside the Texas box (land only).`,
  ];
  const note = crcOpen && catalog.hazards[state.hazard] ? catalog.hazards[state.hazard].notes : null; if (note) items.push(`<b>Release note for ${state.hazard}:</b> ${note}`);
  const build = manifest.hazards.find((h) => h.hazard === state.hazard);
  if (build && build.outside_tabulated_support) items.push(`<b>Tabulated curves:</b> ${build.kinds.tabulated || 0} cells per horizon carry only a few knots near the rare end; return periods outside those knots show as no value (${build.outside_tabulated_support} values across horizons).`);
  if (build && build.warnings.length) for (const w of build.warnings) items.push(`<b>crc-sdk warning:</b> ${w}`);
  for (const l of state.registry.layers) {
    if (l.kind === "points-binary" && state.layersOn.get(l.id) !== false && state.events) {
      const ix = state.events.index;
      items.push(`<b>${l.title}:</b> ${ix.source}; ${ix.licence}. Retrieved ${(ix.retrieved_at || "").slice(0, 10)}. ${ix.known_biases.slice(0, 3).join(" ")}`);
    }
  }
  for (const l of state.registry.layers) if ((l.kind === "points" || l.kind === "lines") && state.layersOn.get(l.id) === true) items.push(`<b>${l.title}:</b> ${l.caveat || ""} Source: ${l.source}; licence ${l.licence}.`);
  items.push(`<b>Built</b> ${manifest.built_at} with crc-sdk ${manifest.versions["crc-sdk"]}, crc-framework ${manifest.versions["crc-framework"]}. Displayed unit: ${unitOf(layer, payload)}${layer.display ? ` (source ${payload.unit})` : ""}.`);
  $("caveats").innerHTML = items.map((t) => `<li>${t}</li>`).join("");
}

// ---------- map ----------
function initMap() {
  const b = state.manifest.texas.bounds;
  const map = new maplibregl.Map({
    container: "map", style: state.registry.basemap.style,
    bounds: [[b[0], b[1]], [b[2], b[3]]], fitBoundsOptions: { padding: 20 },
    attributionControl: { customAttribution: `${state.registry.basemap.attribution} · Hazard data CRC Open (${state.catalog.licence})` },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  const overlay = new MapboxOverlay({
    interleaved: false, layers: [],
    getTooltip: (info) => {
      if (info.object === undefined || !info.layer) return null;
      if (info.layer.id === "cells") return tooltip(info.index);
      if (info.layer.id === "events" && state.events) { const ev = state.events; const i = info.object; const t = ev.index.types[ev.type[i]]; const m = Number.isNaN(ev.mag[i]) ? "" : ` · ${ev.mag[i]} ${ev.index.magnitude_units[t] || ""}`; return { text: `${t}, ${ev.year[i]}${m}` }; }
      if (info.layer.id.startsWith("geo:")) return geoTooltip(layerById(info.layer.id.slice(4)), info.object);
      return null;
    },
  });
  map.addControl(overlay);
  state.map = map; state.overlay = overlay;
  return new Promise((resolve) => map.on("load", resolve));
}

function tooltip(index) {
  const payload = state.files.get(fileKey(state.hazard, state.horizon)); const layer = layerById(state.hazard);
  const i = state.manifest.return_periods.indexOf(state.rp); const v = payload.values[index][i];
  const kind = payload.kinds[payload.params[index][0]];
  return { text: v === null ? `${payload.cells[index]}\nno value (${kind === "no_data" ? payload.params[index][1] : "outside tabulated support"})` : `${fmt(display(layer, v))} ${unitOf(layer, payload)}  ·  1 in ${state.rp} years, ${state.horizon}\n${payload.cells[index]} · ${kind}` };
}

function computeDomain(payload, rpIndex, layer) {
  const vals = payload.values.map((r) => r[rpIndex]).filter((v) => v !== null).map((v) => display(layer, v)).sort((a, b) => a - b);
  let lo = quantile(vals, 0.02), hi = quantile(vals, 0.98);
  if (!(hi > lo)) { lo = vals[0] ?? 0; hi = vals[vals.length - 1] ?? 1; if (!(hi > lo)) hi = lo + 1; }
  return [lo, hi, vals.length];
}

let rendering = 0;
async function render() {
  const started = performance.now(); const token = ++rendering;
  const layer = layerById(state.hazard);
  let payload;
  try { payload = await loadFile(state.hazard, state.horizon); }
  catch (e) { $("status").textContent = `Could not load ${state.hazard} ${state.horizon}: ${e.message}`; return; }
  if (token !== rendering) return;
  const fetched = performance.now();
  const rpIndex = state.manifest.return_periods.indexOf(state.rp);
  if (!state.locked || !state.domain) state.domain = computeDomain(payload, rpIndex, layer);
  const [lo, hi, n] = state.domain; const stops = ramp(layer.style);
  const color = (i) => { const v = payload.values[i][rpIndex]; return v === null ? NODATA : colorAt(stops, (display(layer, v) - lo) / (hi - lo)); };
  const indices = payload.values.map((_, i) => i);
  const layers = [];
  if (state.layersOn.get(state.hazard) !== false) layers.push(new H3HexagonLayer({
    id: "cells", data: indices, getHexagon: (i) => payload.cells[i], getFillColor: color,
    filled: true, stroked: false, extruded: false, highPrecision: false, pickable: true, opacity: 1,
    updateTriggers: { getFillColor: [state.hazard, state.horizon, state.rp, lo, hi], getHexagon: [state.hazard, state.horizon] },
    onClick: (info) => { showDetail(info.index); return true; },
  }));
  for (const l of state.registry.layers) {
    if (l.kind !== "points-binary" || state.layersOn.get(l.id) === false) continue;
    try { await loadEvents(l); } catch (e) { $("events-status").textContent = `Could not load ${l.title}: ${e.message}`; continue; }
    if (token !== rendering) return;
    toggleEventsControls(l);
    layers.push(eventsLayer(l));
  }
  if (state.layersOn.get("texas") !== false) layers.push(new GeoJsonLayer({
    id: "texas", data: state.texas, stroked: true, filled: false, getLineColor: layerById("texas").style.line, lineWidthMinPixels: layerById("texas").style.width, pickable: false,
  }));
  // sources track: generic GeoJSON layers (kind "points" or "lines"), loaded only when switched on
  for (const l of state.registry.layers) {
    if ((l.kind === "points" || l.kind === "lines") && state.layersOn.get(l.id) === true) {
      try { layers.push(geoLayer(l, await loadGeo(l))); }
      catch (e) { $("status").textContent = `Could not load ${l.id}: ${e.message}`; }
    }
  }
  if (token !== rendering) return;
  state.overlay.setProps({ layers });
  // legend
  $("legend-title").textContent = `${layer.title}, ${state.horizon}, 1 in ${state.rp} years`;
  $("legend-unit").textContent = unitOf(layer, payload);
  $("legend-bar").style.background = `linear-gradient(90deg, ${stops.map((c) => `rgb(${c.join(",")})`).join(",")})`;
  $("legend-min").textContent = `≤ ${fmt(lo)}`; $("legend-max").textContent = `≥ ${fmt(hi)}`;
  $("legend-note").textContent = `Scale spans the 2nd–98th percentile of ${n} cells with a value (${payload.cells.length - n} without). Grey: no value.`;
  buildCaveats(payload);
  buildSelectors();
  if (state.selected && (state.selected.hazard !== state.hazard || state.selected.horizon !== state.horizon)) { state.selected = null; $("detail").classList.add("hidden"); }
  else if (state.selected) showDetail(state.selected.index);
  requestAnimationFrame(() => {
    if (token !== rendering) return;
    const total = performance.now() - started;
    $("status").textContent = `${payload.cells.length} cells · ${(fetched - started).toFixed(0)} ms load, ${total.toFixed(0)} ms to view`;
    document.body.dataset.ready = "1"; document.body.dataset.ms = total.toFixed(0);
  });
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

function toggleEventsControls(layer) {
  const box = $("events-controls"); const on = state.layersOn.get(layer.id) !== false;
  box.classList.toggle("hidden", !on);
  if (!on || !state.events) return;
  const { index } = state.events; const f = state.eventsFilter;
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
  $("events-status").textContent = `${keep.length.toLocaleString()} of ${ev.n.toLocaleString()} located events shown (${f.from}–${f.to}). ${index.events_without_point.toLocaleString()} county/zone events have no point and are not drawn.`;
  const colors = index.types.map((t) => eventColor(layer, t));
  return new ScatterplotLayer({
    id: "events", data: keep, pickable: true, radiusUnits: "pixels", getRadius: 3, radiusMinPixels: 2, radiusMaxPixels: 6,
    stroked: true, lineWidthMinPixels: 1, getLineColor: [255, 255, 255, 160], opacity: 0.85,
    getPosition: (i) => [ev.lon[i], ev.lat[i]], getFillColor: (i) => colors[ev.type[i]],
    updateTriggers: { getFillColor: [layer.id] },
    onClick: (info) => { showEvent(layer, info.object); return true; },
  });
}

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
// ---------- sources track: GeoJSON layers (points, lines) ----------
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
function geoTooltip(l, feature) {
  const p = feature.properties || {};
  return { text: p.label ? `${p.label}\n${l.title}` : l.title };
}
function showFeature(l, feature) {
  const p = feature.properties || {}; state.selected = null;
  $("detail").classList.remove("hidden");
  $("detail-title").textContent = p.label ? `${p.label}` : l.title;
  const skip = new Set(["curve", "label"]);
  const meta = [["Layer", l.title], ["Source", l.source]];
  for (const [k, v] of Object.entries(p)) if (!skip.has(k) && v !== null && typeof v !== "object") meta.push([k.replaceAll("_", " "), String(v)]);
  $("detail-meta").innerHTML = meta.map(([k, v]) => `<b>${k}</b><span>${v}</span>`).join("");
  $("detail-params").innerHTML = "";
  const c = p.curve;
  if (c && Array.isArray(c.return_periods) && Array.isArray(c.values)) {
    $("detail-table").innerHTML = `<tr><th>Return period</th><th class="num">${c.unit || ""}</th></tr>` + c.return_periods.map((t, i) => `<tr><td>1 in ${t} years</td><td class="num">${fmt(c.values[i])}</td></tr>`).join("");
    drawCurve(c.return_periods, c.values, c.unit || "", ramp(l.style && l.style.hue !== undefined ? l.style : { hue: 250, chroma: 0.14 }));
    if (c.note) $("detail-params").innerHTML = `<b>Curve</b><span>${c.note}</span>`;
  } else {
    $("detail-table").innerHTML = ""; $("chart").innerHTML = "";
  }
}

// ---------- detail panel: curve on click ----------
function showDetail(index) {
  const payload = state.files.get(fileKey(state.hazard, state.horizon)); const layer = layerById(state.hazard);
  state.selected = { hazard: state.hazard, horizon: state.horizon, index };
  const unit = unitOf(layer, payload); const rps = payload.return_periods; const vals = payload.values[index].map((v) => display(layer, v));
  const p = payload.params[index]; const kind = payload.kinds[p[0]];
  $("detail").classList.remove("hidden");
  $("detail-title").textContent = `${layer.title}, ${state.horizon}`;
  const centre = globalThis.h3 && globalThis.h3.cellToLatLng ? globalThis.h3.cellToLatLng(payload.cells[index]) : null;
  $("detail-meta").innerHTML = [["Cell", `${payload.cells[index]} (H3 r${payload.h3_resolution})`], ["Centre", centre ? `${centre[0].toFixed(3)}°N, ${(-centre[1]).toFixed(3)}°W` : "–"], ["Curve kind", kind], ["Family / reason", p[1]], ["Pathway", payload.pathway], ["Unit", unit]].map(([k, v]) => `<b>${k}</b><span>${v}</span>`).join("");
  const params = kind === "fitted" || kind === "hurdle" ? [["location", p[2]], ["scale", p[3]], ["shape", p[4]]] : kind === "point_mass" ? [["value", p[2]]] : kind === "tabulated" ? [["knots", p[2]]] : [];
  if (kind === "hurdle") params.push(["atom probability", p[5]], ["atom location", p[6]]);
  $("detail-params").innerHTML = params.length ? `<b>Raw parameters</b><span>(${payload.unit}, as shipped by CRC)</span>` + params.map(([k, v]) => `<b>${k}</b><span>${v === null ? "–" : v}</span>`).join("") : "";
  $("detail-table").innerHTML = `<tr><th>Return period</th><th class="num">Non-exceedance</th><th class="num">${unit}</th></tr>` + rps.map((t, i) => `<tr class="${t === state.rp ? "sel" : ""}"><td>1 in ${t} years</td><td class="num">${payload.probabilities[i]}</td><td class="num">${fmt(vals[i])}</td></tr>`).join("");
  drawCurve(rps, vals, unit, ramp(layer.style));
}

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
  const every = Math.ceil(rps.length / 9); // at most nine tick labels (published tables can hold 20+)
  svg.push(...rps.filter((_, i) => i % every === 0 || i === rps.length - 1).map((t) => `<text x="${x(t)}" y="${H - m.b + 16}" text-anchor="middle">${t}</text>`), `<text x="${(m.l + W - m.r) / 2}" y="${H - 4}" text-anchor="middle">return period, years (log scale)</text>`, `<text x="4" y="${m.t - 10}" text-anchor="start">${unit}</text>`, `</g>`);
  svg.push(`<polyline class="curve" stroke="${line}" points="${pts.map((d) => `${x(d.t)},${y(d.v)}`).join(" ")}"/>`);
  svg.push(...pts.map((d) => `<circle class="dot" cx="${x(d.t)}" cy="${y(d.v)}" r="${d.t === state.rp ? 6 : 4}" fill="${line}" data-i="${d.i}"/>`));
  svg.push(`<g id="hover" style="display:none"><line class="cross" y1="${m.t}" y2="${H - m.b}"/><rect fill="#fff" stroke="#d9d7d2" rx="4"/><text class="tip"></text></g>`);
  svg.push(`<rect x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent" id="hit"/>`, `</svg>`);
  box.innerHTML = svg.join("");
  const el = box.querySelector("svg"), hover = el.querySelector("#hover"), cross = hover.querySelector("line"), tip = hover.querySelector("text"), rect = hover.querySelector("rect");
  el.querySelector("#hit").addEventListener("mousemove", (ev) => {
    const r = el.getBoundingClientRect(); const px = ((ev.clientX - r.left) / r.width) * W;
    let best = pts[0]; for (const d of pts) if (Math.abs(x(d.t) - px) < Math.abs(x(best.t) - px)) best = d;
    hover.style.display = ""; cross.setAttribute("x1", x(best.t)); cross.setAttribute("x2", x(best.t));
    tip.textContent = `1 in ${best.t}: ${fmt(best.v)} ${unit}`;
    const tx = Math.min(x(best.t) + 8, W - 130); tip.setAttribute("x", tx + 6); tip.setAttribute("y", m.t + 16);
    rect.setAttribute("x", tx); rect.setAttribute("y", m.t + 2); rect.setAttribute("width", 124); rect.setAttribute("height", 20);
  });
  el.querySelector("#hit").addEventListener("mouseleave", () => { hover.style.display = "none"; });
}

// ---------- catalogue view ----------
function buildCatalog() {
  const { catalog, sources, registry } = state; const loaded = new Set(registry.layers.map((l) => l.id));
  $("catalog-intro").textContent = `Release ${catalog.release} (schema ${catalog.schema_version}), retrieved ${catalog.retrieved_at}. Licence ${catalog.licence}; attribution “${catalog.attribution}”. ${Object.keys(catalog.hazards).length} hazards, pathway ${catalog.pathways.join(", ")}. Generated from the release's own catalogue; nothing here is hand-written.`;
  const rows = Object.entries(catalog.hazards).sort(([a], [b]) => (loaded.has(b) - loaded.has(a)) || a.localeCompare(b));
  const draw = (filter) => {
    const f = filter.trim().toLowerCase();
    $("catalog-table").innerHTML = `<tr><th>Hazard</th><th>Meaning</th><th>Unit</th><th>Tail</th><th class="num">H3</th><th>Probability semantics</th><th>Horizons</th><th>Pooling</th><th class="num">Rows</th><th>Explorer</th><th>Release note</th></tr>` +
      rows.filter(([n, h]) => !f || n.includes(f) || h.value_semantics.toLowerCase().includes(f) || h.unit.toLowerCase().includes(f)).map(([n, h]) => `<tr class="${loaded.has(n) ? "loaded" : ""}"><td>${n}</td><td>${h.value_semantics}</td><td>${h.unit}</td><td>${h.tail}</td><td class="num">${h.h3_resolution}</td><td>${h.probability_semantics || "unspecified"}</td><td>${h.horizons[0]}–${h.horizons[h.horizons.length - 1]} (${h.horizons.length})</td><td>${h.pooling}</td><td class="num">${h.rows.toLocaleString()}</td><td>${loaded.has(n) ? `<span class="pill on">loaded</span>` : `<span class="pill">not loaded yet</span>`}</td><td class="small">${h.notes || ""}</td></tr>`).join("");
  };
  draw(""); $("catalog-filter").oninput = (e) => draw(e.target.value);
  $("sources-table").innerHTML = `<tr><th>Source</th><th>Entry point</th><th>Returns</th><th>Coverage</th><th>Licence</th></tr>` + sources.sources.map((s) => `<tr><td>${s.name}</td><td><code>${s.entry}</code></td><td>${s.returns}</td><td>${s.coverage}</td><td>${s.licence}</td></tr>`).join("");
  $("not-in-crc").innerHTML = sources.not_in_crc.map((t) => `<li>${t}</li>`).join("");
}

// ---------- wiring ----------
async function main() {
  $("status").textContent = "Loading catalogue and registry…";
  const [registry, catalog, manifest, sources, texas] = await Promise.all([
    fetchJSON("layers.json"), fetchJSON("data/catalog.json"), fetchJSON("data/manifest.json"), fetchJSON("sources.json"), fetchJSON("data/texas.geojson"),
  ]);
  Object.assign(state, { registry, catalog, manifest, sources, texas });
  state.hazard = registry.defaults.hazard; state.horizon = registry.defaults.horizon; state.rp = registry.defaults.return_period;
  for (const l of registry.layers) state.layersOn.set(l.id, l.on !== false);
  $("release").innerHTML = `CRC Open <code>${catalog.release}</code> · crc-sdk ${manifest.versions["crc-sdk"]} · built ${manifest.built_at.slice(0, 10)}<br>${catalog.licence} · high-emissions case SSP5-8.5, not a forecast`;
  buildSelectors(); buildCatalog();
  $("hazard").onchange = (e) => {
    state.hazard = e.target.value; state.selected = null;
    const horizons = horizonsOf(layerById(state.hazard)); if (!horizons.includes(state.horizon)) state.horizon = horizons[0];
    render();
  };
  $("horizon").onchange = (e) => { state.horizon = Number(e.target.value); render(); };
  $("rp").onchange = (e) => { state.rp = Number(e.target.value); render(); };
  $("lock").onchange = (e) => { state.locked = e.target.checked; if (!state.locked) render(); };
  $("detail-close").onclick = () => { state.selected = null; $("detail").classList.add("hidden"); };
  for (const b of document.querySelectorAll(".tab")) b.onclick = () => {
    for (const t of document.querySelectorAll(".tab")) t.classList.toggle("on", t === b);
    for (const v of document.querySelectorAll(".view")) v.classList.toggle("on", v.id === `view-${b.dataset.view}`);
    if (b.dataset.view === "map") state.map.resize();
  };
  $("status").textContent = "Loading the base map…";
  await initMap();
  // test hook (tools/smoke.mjs): fly the map somewhere without animation
  document.addEventListener("crc:flyTo", (e) => state.map.jumpTo({ center: e.detail.center, zoom: e.detail.zoom }));
  $("status").textContent = "Loading hazard cells…";
  await render();
  // warm the other horizons of the current hazard so switching is instant
  for (const y of horizonsOf(layerById(state.hazard))) if (y !== state.horizon) loadFile(state.hazard, y).catch(() => {});
}
main().catch((e) => { $("status").textContent = `Failed to start: ${e.message}`; document.body.dataset.error = e.message; console.error(e); });
