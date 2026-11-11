// SVG charts of the detail column, moved from site/app.js. They draw values shipped in the data files; nothing is computed here.
import { $, state, esc, fmt, parseT } from "./core.js";

const SHADE = "#ecebe5"; // "over the Texas box" band

export function drawCurve(rps, vals, unit, stops) {
  const W = 348, H = 210, m = { l: 48, r: 12, t: 24, b: 32 };
  const pts = rps.map((t, i) => ({ t, v: vals[i], i })).filter((d) => d.v !== null);
  const box = $("chart");
  if (pts.length < 1) { box.innerHTML = `<p class="mute small">No values to draw: this curve has no data at these return periods.</p>`; return; }
  const x = (t) => m.l + ((Math.log10(t) - Math.log10(rps[0])) / (Math.log10(rps[rps.length - 1]) - Math.log10(rps[0]))) * (W - m.l - m.r);
  let vmin = Math.min(...pts.map((d) => d.v)), vmax = Math.max(...pts.map((d) => d.v)); if (!(vmax > vmin)) { vmin -= 1; vmax += 1; }
  const pad = (vmax - vmin) * 0.1; vmin = vmin >= 0 ? Math.max(0, vmin - pad) : vmin - pad; vmax += pad; // no negative axis under values that cannot be negative
  const y = (v) => m.t + (1 - (v - vmin) / (vmax - vmin)) * (H - m.t - m.b);
  const line = `rgb(${stops[4].join(",")})`;
  const ticks = 4; const yt = Array.from({ length: ticks + 1 }, (_, k) => vmin + ((vmax - vmin) * k) / ticks);
  // label only as many return periods as fit (station curves carry up to 22 levels)
  const every = Math.ceil(rps.length / 8);
  const svg = [`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Value against return period">`];
  svg.push(`<g class="axis">`, ...yt.map((v) => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${fmt(v)}</text>`));
  svg.push(...rps.map((t, i) => (i % every === 0 || i === rps.length - 1) && !(i !== rps.length - 1 && rps.length - 1 - i < every) ? `<text x="${x(t)}" y="${H - m.b + 16}" text-anchor="middle">${t}</text>` : ""), `<text x="${(m.l + W - m.r) / 2}" y="${H - 4}" text-anchor="middle">return period, years (log scale)</text>`, `<text x="2" y="${m.t - 10}" text-anchor="start">${esc(unit)}</text>`, `</g>`);
  svg.push(`<polyline class="curve" stroke="${line}" points="${pts.map((d) => `${x(d.t)},${y(d.v)}`).join(" ")}"/>`);
  svg.push(...pts.map((d) => `<circle class="dot" cx="${x(d.t)}" cy="${y(d.v)}" r="${d.t === state.rp ? 5 : pts.length > 10 ? 2.5 : 3.5}" fill="${line}" data-i="${d.i}"/>`));
  svg.push(`<g class="hov" style="display:none"><line class="cross" y1="${m.t}" y2="${H - m.b}"/><rect fill="#fff" stroke="#c3c2b7"/><text class="tip"></text></g>`);
  svg.push(`<rect x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent" class="hit"/>`, `</svg>`);
  box.innerHTML = svg.join("");
  hoverChart(box, pts.map((d) => ({ px: x(d.t), label: `1 in ${d.t}: ${fmt(d.v)} ${unit}` })), m, W, H);
}
export function drawSeries(vals, times, unit, stops, inTexas) {
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
  const first = inTexas.indexOf(true), last = inTexas.lastIndexOf(true);
  if (first >= 0) svg.push(`<rect x="${x(first)}" y="${m.t}" width="${Math.max(2, x(last) - x(first))}" height="${H - m.t - m.b}" fill="${SHADE}"/>`);
  svg.push(...yt.map((v) => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${v.toFixed(0)}</text>`));
  svg.push(`<text x="${m.l}" y="${H - m.b + 16}" text-anchor="start">${esc(times[0])}</text>`, `<text x="${W - m.r}" y="${H - m.b + 16}" text-anchor="end">${esc(times[n - 1])}</text>`, `<text x="${W - m.r}" y="${H - 3}" text-anchor="end">track points in time order (UTC); shaded = over the Texas box</text>`, `<text x="${m.l - 6}" y="${m.t - 8}" text-anchor="end">${esc(unit)}</text>`, `</g>`);
  svg.push(`<polyline class="curve" stroke="${line}" points="${pts.map((d) => `${x(d.i)},${y(d.v)}`).join(" ")}"/>`);
  svg.push(...pts.filter((d) => inTexas[d.i]).map((d) => `<circle class="dot" cx="${x(d.i)}" cy="${y(d.v)}" r="3.5" fill="${line}"/>`));
  svg.push(`<line id="series-cursor" class="cross now" y1="${m.t}" y2="${H - m.b}" x1="${m.l}" x2="${m.l}"/>`);
  svg.push(`<g class="hov" style="display:none"><line class="cross" y1="${m.t}" y2="${H - m.b}"/><rect fill="#fff" stroke="#c3c2b7"/><text class="tip"></text></g>`);
  svg.push(`<rect x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent" class="hit"/>`, `</svg>`);
  box.innerHTML = svg.join("");
  const tms = times.map(parseT);
  state.series = (ms) => { let i = 0; while (i + 1 < n && tms[i + 1] <= ms) i++; const f = i + 1 < n && tms[i + 1] > tms[i] ? Math.min(1, Math.max(0, (ms - tms[i]) / (tms[i + 1] - tms[i]))) : 0; return x(i + f); };
  hoverChart(box, pts.map((d) => ({ px: x(d.i), label: `${times[d.i]}: ${d.v} ${unit}` })), m, W, H);
}
function hoverChart(box, marks, m, W) {
  const el = box.querySelector("svg"), hover = el.querySelector(".hov"), cross = hover.querySelector("line"), tip = hover.querySelector("text"), rect = hover.querySelector("rect");
  el.querySelector(".hit").addEventListener("mousemove", (ev) => {
    const r = el.getBoundingClientRect(); const px = ((ev.clientX - r.left) / r.width) * W;
    let best = marks[0]; for (const d of marks) if (Math.abs(d.px - px) < Math.abs(best.px - px)) best = d;
    hover.style.display = ""; cross.setAttribute("x1", best.px); cross.setAttribute("x2", best.px);
    tip.textContent = best.label;
    const w = Math.min(W - 40, 8 + best.label.length * 6.2); const tx = Math.max(2, Math.min(best.px + 8, W - w - 6)); tip.setAttribute("x", tx + 6); tip.setAttribute("y", m.t + 16);
    rect.setAttribute("x", tx); rect.setAttribute("y", m.t + 2); rect.setAttribute("width", w); rect.setAttribute("height", 20);
  });
  el.querySelector(".hit").addEventListener("mouseleave", () => { hover.style.display = "none"; });
}
