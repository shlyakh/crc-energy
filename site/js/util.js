// Small shared helpers: DOM, escaping, number formats with units, class colours, address state.
export const $ = (id) => document.getElementById(id);
export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

export const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export const rgb = (hex, alpha = 255) => { const n = parseInt(hex.replace("#", ""), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255, alpha]; };
export const CLASS_VARS = ["--c0", "--c1", "--c2", "--c3", "--c4"];

// Decimals shown per measure, in its display unit.
const DECIMALS = { loss_ratio: 3, loss_usd: 2, p2in: 2, radar_days: 2 };
export function fmtMeasure(measure, raw) {
  if (raw === null || raw === undefined) return "–";
  return (raw * measure.scale).toFixed(DECIMALS[measure.id] ?? 2);
}
export const fmtBreak = (b) => (b >= 100 ? b.toFixed(0) : String(Number(b.toPrecision(3))));
export const fmtInt = (v) => Math.round(v).toLocaleString("en-US");
export const fmtMW = (v) => (v >= 100 ? v.toFixed(0) : v.toFixed(1));
export function fmtUSD(v) {
  if (v === null || v === undefined) return "–";
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(2)} B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(Math.abs(v) >= 1e8 ? 0 : 2)} M`;
  return `$${(v / 1e3).toFixed(0)} k`;
}
export const fmtPct = (v, d = 3) => (v === null || v === undefined ? "–" : `${(100 * v).toFixed(d)} %`);

// Class index of a display-unit value against increasing breaks: 0 below the first, breaks.length at or above the last.
export function classOf(value, breaks) { let i = 0; while (i < breaks.length && value >= breaks[i]) i++; return i; }
// With fewer breaks than classes, spread the classes over the ramp so the darkest is still used.
export function classVar(i, nBreaks) { const n = nBreaks + 1; return CLASS_VARS[n <= 1 ? 2 : Math.round((i * (CLASS_VARS.length - 1)) / (n - 1))]; }

// Address state: #tab=risk&plant=eia-1&measure=loss_ratio&basis=1
export function readAddress() { return Object.fromEntries(new URLSearchParams(location.hash.slice(1))); }
export function writeAddress(values) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(values)) if (v !== null && v !== undefined && v !== "") p.set(k, v);
  history.replaceState(null, "", `#${p}`);
}

// A geodesic circle as a closed ring of [lon, lat].
export function circleRing(lon, lat, radiusKm, n = 96) {
  const R = 6371.0088, d = radiusKm / R, p1 = (lat * Math.PI) / 180, l1 = (lon * Math.PI) / 180, out = [];
  for (let i = 0; i <= n; i++) {
    const b = (2 * Math.PI * i) / n;
    const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b));
    const l2 = l1 + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
    out.push([(l2 * 180) / Math.PI, (p2 * 180) / Math.PI]);
  }
  return out;
}
