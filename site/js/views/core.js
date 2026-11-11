// Source views (Hail evidence and CRC data tabs): shared state, colour, formats, the detail column and the on-map legend.
// Moved from site/app.js; the views write into the pane built by ../sources.js.
import { esc } from "../util.js";
export { esc };

export const { MapboxOverlay, H3HexagonLayer, GeoJsonLayer, ScatterplotLayer, LineLayer, SolidPolygonLayer, PathLayer } = globalThis.deck;
export const $ = (id) => document.getElementById(id);

export const state = {
  root: "",                  // registry paths ("data/...") are relative to site/
  registry: null, catalog: null, manifest: null, texas: null,
  origin: null, byOrigin: {}, // shown group of sources, and the last source picked in each
  source: null,              // active source id (registry.sources[].id)
  hazard: null, horizon: null, rp: null,   // active h3-cells layer and its view
  files: new Map(),          // "hazard/horizon" -> payload; "geo:<id>" -> GeoJSON
  domain: null, locked: false,
  overlays: new Map(),       // layer id -> boolean (layers shown beside the active source)
  selected: null,            // cells click: { hazard, horizon, index }
  pick: null,                // what is highlighted on the map: { kind: "cell", cell } | { kind: "point", position, key }
  events: null, eventsFilter: { from: null, to: null, types: null }, eventsShown: null,
  tracks: null, tracksFilter: { from: null, to: null, name: "", minWind: 0, colorBy: "wind" }, storm: null,
  extent: true,              // draw wind-radius swaths where IBTrACS has them
  nearOnly: true,            // storm player: only the reports near the track (false = all Texas reports)
  win: { on: false, start: "2024-03-14", days: 3 },   // Storm reports date window
  time: null,                // player: { key, mode, t0, t1, now, playing, speed, shade, range }
  baseLayers: [], series: null,
  map: null, overlay: null,
  cmp: null,                 // hail comparison: { data, lon[], mode, a, b, ra, rb, ownScale, split }
};
// Set by ../sources.js and ./time.js so the views can ask for a redraw without importing them.
export const api = { render: async () => {}, drawFrame: () => {}, clearSelection: () => {} };

// ---------- colour: one hue, light -> dark, built in OKLCH; fallback blue ramp ----------
const FALLBACK = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
const canvas = document.createElement("canvas"); canvas.width = canvas.height = 1;
const ctx = canvas.getContext("2d", { willReadFrequently: true });
export function parseColor(css) {
  ctx.fillStyle = "#000"; ctx.fillStyle = css;
  ctx.clearRect(0, 0, 1, 1); ctx.fillRect(0, 0, 1, 1);
  const d = ctx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2]];
}
const ramps = new Map();
export function ramp(style) {
  const key = style && style.hue !== undefined ? `${style.hue}/${style.chroma}` : "fallback";
  if (!ramps.has(key)) ramps.set(key, buildRamp(style));
  return ramps.get(key);
}
function buildRamp(style) {
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
export function colorAt(stops, t, alpha = 215) {
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x)); const f = x - i;
  const a = stops[i], b = stops[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, alpha];
}
export const NODATA = [201, 199, 193, 140];
export const INK = [11, 11, 11];
export const rgbCss = (c) => `rgb(${c.slice(0, 3).map((v) => Math.round(v)).join(",")})`;
export const gradient = (stops) => `linear-gradient(90deg, ${stops.map(rgbCss).join(",")})`;

// ---------- helpers ----------
export const layerById = (id) => state.registry.layers.find((l) => l.id === id);
export const sourceById = (id) => state.registry.sources.find((s) => s.id === id);
export const groupOf = (s) => state.registry.groups.find((g) => g.id === s.origin) || state.registry.groups[0];
export const layersOfSource = (id) => state.registry.layers.filter((l) => l.source_id === id);
export const fileKey = (h, y) => `${h}/${y}`;
export function display(layer, v) { if (v === null || v === undefined) return null; const d = layer.display; return d ? v + (d.offset || 0) : v; }
export function unitOf(layer, payload) { return (layer.display && layer.display.unit) || payload.unit; }
export function fmt(v, digits = 3) {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const a = Math.abs(v);
  if (a >= 100) return v.toFixed(0); if (a >= 10) return v.toFixed(1); if (a >= 1) return v.toFixed(2);
  return v.toPrecision(digits);
}
// Shorter numbers for legend ticks.
export function fmtTick(v) { if (v === 0) return "0"; const a = Math.abs(v); return a >= 100 ? v.toFixed(0) : a >= 10 ? v.toFixed(1) : String(Number(v.toPrecision(2))); }
export function quantile(sorted, q) { if (!sorted.length) return NaN; const i = (sorted.length - 1) * q; const lo = Math.floor(i); return sorted[lo] + (sorted[Math.min(lo + 1, sorted.length - 1)] - sorted[lo]) * (i - lo); }
export const asset = (path) => state.root + path;
export async function fetchJSON(path) { const r = await fetch(asset(path)); if (!r.ok) throw new Error(`${path}: ${r.status}`); return r.json(); }
export const horizonsOf = (layer) => (layer && layer.horizons) || state.manifest.horizons;
// time: events carry minutes since 1950-01-01T00:00Z; track fixes carry "YYYY-MM-DD HH:MM" (UTC)
const EPOCH = Date.UTC(1950, 0, 1);
export const minToMs = (m) => EPOCH + m * 60000;
export const msToMin = (ms) => (ms - EPOCH) / 60000;
export const parseT = (t) => Date.UTC(+t.slice(0, 4), +t.slice(5, 7) - 1, +t.slice(8, 10), +t.slice(11, 13), +t.slice(14, 16));
export const fmtT = (ms) => new Date(ms).toISOString().slice(0, 16).replace("T", " ");
export const cellSource = (id) => layersOfSource(id).some((l) => l.kind === "h3-cells");
export const compareLayerOf = (sourceId) => layersOfSource(sourceId).find((l) => l.kind === "h3-compare");
export const latLon = (lat, lon) => `${Math.abs(lat).toFixed(3)}° ${lat < 0 ? "S" : "N"}, ${Math.abs(lon).toFixed(3)}° ${lon < 0 ? "W" : "E"}`;

// ---------- detail column ----------
// rows: [label, value] pairs, or a string for a group heading. Values are escaped unless `raw`.
export function kv(rows, raw = false) {
  return rows.map((r) => (typeof r === "string" ? `<tr class="grp"><th colspan="2">${esc(r)}</th></tr>` : `<tr><th>${esc(r[0])}</th><td>${raw ? r[1] : esc(r[1])}</td></tr>`)).join("");
}
export function openDetail(title, sub = "") {
  $("src-empty").classList.add("hidden"); $("detail").classList.remove("hidden");
  $("detail-title").textContent = title; $("detail-sub").textContent = sub;
  document.body.dataset.picked = state.pick ? state.pick.kind : state.storm !== null ? "storm" : "";
}
export function closeDetail() {
  $("detail").classList.add("hidden"); $("src-empty").classList.remove("hidden");
  document.body.dataset.picked = "";
}

// ---------- selection highlight (drawn last, above every data layer) ----------
export function highlightLayers() {
  const p = state.pick; if (!p) return [];
  if (p.kind === "cell") {
    const ring = globalThis.h3.cellToBoundary(p.cell, true);
    return [[255, 255, 255, 255], [...INK, 255]].map((color, k) => new PathLayer({
      id: `sel-cell${k ? "" : "-case"}`, data: [ring], getPath: (d) => d, getColor: color, widthUnits: "pixels", getWidth: k ? 2.25 : 5, jointRounded: true, pickable: false,
    }));
  }
  if (p.kind === "point") {
    return [[255, 255, 255, 255], [...INK, 255]].map((color, k) => new ScatterplotLayer({
      id: `sel-ring${k ? "" : "-case"}`, data: [p.position], getPosition: (d) => d, radiusUnits: "pixels", getRadius: 11, filled: false, stroked: true,
      lineWidthUnits: "pixels", getLineWidth: k ? 2 : 5, getLineColor: color, pickable: false,
    }));
  }
  return [];
}

// ---------- legend on the map ----------
// sections: { title, unit, ramps: [{ label, css, ticks: [text] }], rows: [{ color, shape: "dot" | "line" | "band" | "box", label, n }], foot }
export function renderLegend(sections) {
  const tick = (t, i, n) => `<span style="left:${((i / (n - 1)) * 100).toFixed(1)}%" class="${i === 0 ? "first" : i === n - 1 ? "last" : ""}">${esc(t)}</span>`;
  $("src-legend").innerHTML = sections.filter(Boolean).map((s) => [
    s.title ? `<h3>${esc(s.title)}</h3>` : "",
    s.unit ? `<div class="unit">${esc(s.unit)}</div>` : "",
    ...(s.ramps || []).map((r) => `${r.label ? `<div class="ramp-label">${esc(r.label)}</div>` : ""}<div class="ramp"><div class="bar" style="background:${r.css}"></div><div class="ticks num">${r.ticks.map((t, i) => tick(t, i, r.ticks.length)).join("")}</div></div>`),
    ...(s.rows || []).map((r) => `<div class="row"><span class="${r.shape || "dot"}" style="${(r.shape || "").startsWith("ring") ? "border-color" : "background"}:${r.color}"></span>${esc(r.label)}${r.n !== undefined && r.n !== null ? `<span class="n num">${esc(typeof r.n === "number" ? r.n.toLocaleString("en-US") : r.n)}</span>` : ""}</div>`),
    s.foot ? `<div class="foot">${esc(s.foot)}</div>` : "",
  ].join("")).join('<div class="sep"></div>');
  document.body.dataset.legend = $("src-legend").innerText.replace(/\s+/g, " ").slice(0, 400);
}
export const ticksBetween = (lo, hi, n = 5) => Array.from({ length: n }, (_, k) => lo + ((hi - lo) * k) / (n - 1));
