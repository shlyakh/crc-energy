// Small SVG charts for the detail column. Each takes a target element; marks carry a hover readout
// shown in the chart's caption line. One hue for magnitude; values are labelled in ink, not in colour.
import { esc } from "./util.js";

const W = 308;
const svg = (h, body) => `<svg viewBox="0 0 ${W} ${h}" width="100%" role="img" style="display:block;overflow:visible">${body}</svg>`;
function mount(el, title, sub, h, body, idle) {
  el.innerHTML = `<div class="ch-title">${esc(title)}</div><div class="ch-sub">${esc(sub)}</div>${svg(h, body)}<div class="ch-cap num">${esc(idle)}</div>`;
  const cap = el.querySelector(".ch-cap");
  for (const m of el.querySelectorAll("[data-tip]")) { m.addEventListener("mouseenter", () => { cap.textContent = m.dataset.tip; m.setAttribute("opacity", ".7"); }); m.addEventListener("mouseleave", () => { cap.textContent = idle; m.removeAttribute("opacity"); }); }
  return el.querySelector("svg");
}
const niceMax = (v) => { if (v <= 0) return 1; const e = 10 ** Math.floor(Math.log10(v)); return [1, 2, 2.5, 5, 10].map((m) => m * e).find((m) => m >= v); };

// Vertical bars: counts per ordered bin. bins: [{ label, count, tip }]
export function histogram(el, { title, sub, bins, idle }) {
  const h = 104, x0 = 22, y0 = 82, top = 8, bw = (W - x0 - 4) / bins.length, max = niceMax(Math.max(1, ...bins.map((b) => b.count)));
  const y = (c) => y0 - ((y0 - top) * c) / max;
  let s = `<line x1="${x0}" x2="${W}" y1="${y0}" y2="${y0}" stroke="var(--rule-2)"/>`;
  for (const t of [max / 2, max]) s += `<line x1="${x0}" x2="${W}" y1="${y(t)}" y2="${y(t)}" stroke="var(--rule)"/><text x="${x0 - 4}" y="${y(t) + 3}" text-anchor="end" class="ch-tick">${t}</text>`;
  bins.forEach((b, i) => {
    const bx = x0 + i * bw + 1, bh = y0 - y(b.count);
    if (b.count) s += `<path d="M${bx},${y0} v${-Math.max(bh - 2, 0)} q0,-2 2,-2 h${bw - 6} q2,0 2,2 v${Math.max(bh - 2, 0)} z" fill="var(--c2)" data-tip="${esc(b.tip)}"/>`;
    s += `<text x="${bx + (bw - 2) / 2}" y="${y0 + 12}" text-anchor="middle" class="ch-tick">${esc(b.label)}</text>`;
    if (b.count) s += `<text x="${bx + (bw - 2) / 2}" y="${y(b.count) - 3}" text-anchor="middle" class="ch-val">${b.count}</text>`;
  });
  mount(el, title, sub, h, s, idle);
}

// A curve y(x) from shipped values, with the plant's reports marked on it. marks: [{ x, count }]
export function curve(el, { title, sub, xs, ys, marks, xUnit, idle, yFmt }) {
  const h = 132, x0 = 30, y0 = 104, top = 8, xmax = xs[xs.length - 1], ymax = niceMax(Math.max(...ys) * 100) / 100;
  const X = (v) => x0 + ((W - x0 - 6) * Math.min(v, xmax)) / xmax, Y = (v) => y0 - ((y0 - top) * v) / ymax;
  const at = (v) => { const c = Math.min(v, xmax); let i = 1; while (i < xs.length - 1 && xs[i] < c) i++; const f = (c - xs[i - 1]) / (xs[i] - xs[i - 1]); return ys[i - 1] + f * (ys[i] - ys[i - 1]); }; // position along the shipped polyline
  let s = `<line x1="${x0}" x2="${W}" y1="${y0}" y2="${y0}" stroke="var(--rule-2)"/>`;
  for (const t of [ymax / 2, ymax]) s += `<line x1="${x0}" x2="${W}" y1="${Y(t)}" y2="${Y(t)}" stroke="var(--rule)"/><text x="${x0 - 4}" y="${Y(t) + 3}" text-anchor="end" class="ch-tick">${(t * 100).toFixed(0)}%</text>`;
  for (const t of [25, 50, 75, 100]) if (t <= xmax) s += `<line x1="${X(t)}" x2="${X(t)}" y1="${y0}" y2="${y0 + 3}" stroke="var(--rule-2)"/><text x="${X(t)}" y="${y0 + 15}" text-anchor="middle" class="ch-tick">${t}</text>`;
  s += `<text x="${W}" y="${y0 + 25}" text-anchor="end" class="ch-tick">${esc(xUnit)}</text>`;
  s += `<path d="${xs.map((x, i) => `${i ? "L" : "M"}${X(x).toFixed(1)},${Y(ys[i]).toFixed(1)}`).join("")}" fill="none" stroke="var(--c3)" stroke-width="2" stroke-linejoin="round"/>`;
  const big = Math.max(1, ...marks.map((m) => m.count));
  for (const m of [...marks].sort((a, b) => b.count - a.count)) {
    const r = 3.5 + 3.5 * Math.sqrt(m.count / big), v = at(m.x);
    s += `<circle cx="${X(m.x).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="${r.toFixed(1)}" fill="var(--report)" fill-opacity=".8" stroke="#fff" stroke-width="2" data-tip="${esc(`${m.count} report${m.count > 1 ? "s" : ""} of ${m.x.toFixed(0)} mm (${(m.x / 25.4).toFixed(2)} in): ${yFmt(v)} if it covers the plant`)}"/>`;
  }
  mount(el, title, sub, h, s, idle);
}

// Horizontal bars with a label and a value each. rows: [{ label, note, value, tip }]
export function bars(el, { title, sub, rows, unit, idle }) {
  const rh = 30, h = rows.length * rh + 4, x0 = 4, max = niceMax(Math.max(...rows.map((r) => r.value ?? 0), 1e-9)), bw = W - x0 - 46;
  let s = "";
  rows.forEach((r, i) => {
    const y = i * rh; const w = r.value === null || r.value === undefined ? 0 : Math.max((bw * r.value) / max, 1);
    s += `<text x="${x0}" y="${y + 11}" class="ch-lab">${esc(r.label)} <tspan class="ch-tick">${esc(r.note)}</tspan></text>`;
    s += `<rect x="${x0}" y="${y + 15}" width="${bw}" height="8" fill="var(--hover)"/>`;
    if (w) s += `<path d="M${x0},${y + 15} h${Math.max(w - 2, 0)} q2,0 2,2 v4 q0,2 -2,2 h${-Math.max(w - 2, 0)} z" fill="var(--c2)" data-tip="${esc(r.tip)}"/>`;
    s += `<text x="${W}" y="${y + 23}" text-anchor="end" class="ch-val">${r.value === null || r.value === undefined ? "–" : r.value.toFixed(2)}</text>`;
  });
  mount(el, title, `${sub} · ${unit}`, h, s, idle);
}
