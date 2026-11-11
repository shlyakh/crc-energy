// Time: the storm player, the report date window and the timeline strip under the map. Moved from site/app.js.
import { $, state, api, esc, ScatterplotLayer, PathLayer, layerById, ramp, rgbCss, minToMs, msToMin, parseT, fmtT, highlightLayers } from "./core.js";
import { loadEvents, eventColor, showEvent } from "./events.js";
import { fixAt, ringAt, stormTimes } from "./tracks.js";

function lowerBound(arr, v) { let lo = 0, hi = arr.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid] < v) lo = mid + 1; else hi = mid; } return lo; }
export async function setupTime() {
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
export function stopPlay() { if (state.time) state.time.playing = false; $("time-play").textContent = "▶"; document.body.dataset.playing = ""; }
function windowTypes() { // in window mode the type checkboxes apply; in storm mode every type in the window shows
  const ev = state.events; const { index } = ev;
  return state.time.mode === "window" ? index.types.map((t) => state.eventsFilter.types.has(t)) : index.types.map(() => true);
}
export function drawFrame() {
  if (!state.overlay) return;
  const t0 = performance.now(); const layers = [...state.baseLayers]; const tm = state.time;
  if (tm && state.events) {
    const ev = state.events; const el = layerById("storm_events"); const on = windowTypes(); const nowMin = msToMin(tm.now);
    const keep = []; for (let i = tm.range[0]; i < tm.range[1]; i++) { if (ev.begin[i] > nowMin) break; if (on[ev.type[i]] && ev.lon[i] === ev.lon[i]) keep.push(i); }
    const colors = ev.index.types.map((t) => eventColor(el, t));
    layers.push(new ScatterplotLayer({
      id: "window-events", data: keep, pickable: true, radiusUnits: "pixels", getRadius: 4, stroked: true, lineWidthMinPixels: 1, getLineColor: [255, 255, 255, 200],
      getPosition: (i) => [ev.lon[i], ev.lat[i]], getFillColor: (i) => colors[ev.type[i]],
      onClick: (info) => { showEvent(el, info.object); drawFrame(); return true; },
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
  layers.push(...highlightLayers());
  state.overlay.setProps({ layers });
  document.body.dataset.layers = layers.map((l) => l.id).join(" ");
  if (tm) { const dt = performance.now() - t0; tm.frames++; tm.frameMs = tm.frameMs === null ? dt : tm.frameMs * 0.9 + dt * 0.1; document.body.dataset.frameMs = tm.frameMs.toFixed(2); }
}
function play() {
  const tm = state.time; if (!tm) return;
  if (tm.now >= tm.t1) tm.now = tm.t0;
  tm.playing = true; $("time-play").textContent = "❚❚"; document.body.dataset.playing = "1"; let last = performance.now(); const key = tm.key;
  const step = (t) => {
    if (!state.time || state.time.key !== key || !tm.playing) return;
    tm.now = Math.min(tm.t1, tm.now + ((t - last) / 1000) * tm.speed * 3600000); last = t;
    drawFrame();
    if (tm.now >= tm.t1) { stopPlay(); return; }
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
export function seek(fraction) { const tm = state.time; if (!tm) return; stopPlay(); tm.now = tm.t0 + fraction * (tm.t1 - tm.t0); drawFrame(); }
export function buildTimebar() {
  const tm = state.time; const bar = $("timebar");
  const was = bar.classList.contains("hidden"); bar.classList.toggle("hidden", !tm);
  if (was !== !tm && state.map) state.map.resize();
  if (!tm) return;
  $("time-title").textContent = tm.mode === "storm" ? "Storm player" : "Date window";
  $("time-play").onclick = () => { if (tm.playing) stopPlay(); else play(); };
  $("time-speed").onchange = (e) => { tm.speed = Number(e.target.value); };
  $("time-slider").oninput = (e) => seek(Number(e.target.value) / 1000);
  const filterKey = tm.mode === "window" ? [...state.eventsFilter.types].sort().join("|") : "";
  if (state.timelineKey !== tm.key + filterKey) { drawTimeline(); state.timelineKey = tm.key + filterKey; }
  drawFrame();
}
export function drawTimeline() {
  const started = performance.now(); const tm = state.time; const ev = state.events; const { index } = ev; const el = layerById("storm_events");
  const on = windowTypes(); const CAP = 6000;
  const counts = new Map(); const marks = [];
  for (let i = tm.range[0]; i < tm.range[1]; i++) { if (!on[ev.type[i]]) continue; counts.set(ev.type[i], (counts.get(ev.type[i]) || 0) + 1); if (marks.length < CAP) marks.push(i); }
  // rows: hail and thunderstorm wind always, then the other types present, by count (fixed order within a window)
  const always = ["Hail", "Thunderstorm Wind"].map((t) => index.types.indexOf(t)).filter((c) => c >= 0);
  const rest = [...counts.keys()].filter((c) => !always.includes(c)).sort((a, b) => counts.get(b) - counts.get(a));
  const rows = [...always, ...rest]; const rowOf = new Map(rows.map((c, k) => [c, k]));
  const box = $("timeline"); const W = Math.max(480, box.clientWidth || 900); const L = 150, R = 20, RH = 16, T = 16; const H = T + rows.length * RH + 4;
  const x = (ms) => L + ((ms - tm.t0) / (tm.t1 - tm.t0)) * (W - L - R);
  state.timelineX = x;
  const span = tm.t1 - tm.t0; let tickStep = span <= 2 * 86400000 ? 6 * 3600000 : span <= 6 * 86400000 ? 12 * 3600000 : 86400000;
  while ((span / tickStep) * 44 > W - L - R) tickStep *= 2; // keep the tick labels apart on a narrow strip
  const svg = [`<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Timeline of storm reports">`];
  if (tm.shade) svg.push(`<rect x="${x(tm.shade[0])}" y="${T}" width="${Math.max(2, x(tm.shade[1]) - x(tm.shade[0]))}" height="${rows.length * RH}" fill="#ecebe5"><title>Storm centre over the Texas box</title></rect>`);
  svg.push(`<g class="axis">`);
  for (let t = Math.ceil(tm.t0 / tickStep) * tickStep; t <= tm.t1; t += tickStep) svg.push(`<line x1="${x(t)}" x2="${x(t)}" y1="${T}" y2="${H - 4}"/><text x="${x(t)}" y="11" text-anchor="middle">${new Date(t).getUTCHours() === 0 ? fmtT(t).slice(5, 10) : fmtT(t).slice(11, 16)}</text>`);
  svg.push(`</g>`);
  rows.forEach((c, k) => { const col = eventColor(el, index.types[c]); svg.push(`<circle cx="6" cy="${T + k * RH + RH / 2}" r="4" fill="${rgbCss(col)}"/><text class="row-label" x="16" y="${T + k * RH + RH / 2 + 4}">${esc(index.types[c])} (${counts.get(c) || 0})</text><line x1="${L}" x2="${W - R}" y1="${T + (k + 1) * RH}" y2="${T + (k + 1) * RH}" stroke="#e1e0d9"/>`); });
  const hailC = index.types.indexOf("Hail"), windC = index.types.indexOf("Thunderstorm Wind");
  for (const i of marks) {
    const c = ev.type[i]; const k = rowOf.get(c); const col = eventColor(el, index.types[c]).join(",");
    // hail sized by diameter (0.75 to 4 in), wind by speed (50 to 100 kt); other types a fixed mark
    let s = 0.5; const m = ev.mag[i];
    if (m === m && c === hailC) s = Math.min(1, Math.max(0.15, (m - 0.5) / 3.5)); else if (m === m && c === windC) s = Math.min(1, Math.max(0.15, (m - 40) / 60));
    const h = 4 + s * (RH - 6); const y = T + k * RH + (RH - h) / 2; const located = ev.lon[i] === ev.lon[i];
    const x0 = x(minToMs(ev.begin[i])); const wd = ev.end[i] > ev.begin[i] ? Math.max(1.5, x(minToMs(Math.min(ev.end[i], msToMin(tm.t1)))) - x0) : 0;
    const op = (0.35 + 0.6 * s).toFixed(2);
    svg.push(wd ? `<rect class="mark" data-i="${i}" x="${x0.toFixed(1)}" y="${y.toFixed(1)}" width="${wd.toFixed(1)}" height="${h.toFixed(1)}" fill="${located ? `rgba(${col},${op})` : "none"}" stroke="rgb(${col})" stroke-width="${located ? 0 : 1}"/>`
      : `<line class="mark" data-i="${i}" x1="${x0.toFixed(1)}" x2="${x0.toFixed(1)}" y1="${y.toFixed(1)}" y2="${(y + h).toFixed(1)}" stroke="rgba(${col},${located ? op : 0.45})" stroke-width="2" ${located ? "" : 'stroke-dasharray="2 2"'}/>`);
  }
  svg.push(`<line class="cursor" x1="${x(tm.now)}" x2="${x(tm.now)}" y1="${T - 4}" y2="${H - 2}"/></svg>`);
  box.innerHTML = svg.join("");
  const total = [...counts.values()].reduce((a, b) => a + b, 0);
  $("timeline-note").textContent = `${total.toLocaleString("en-US")} reports begin between ${fmtT(tm.t0)} and ${fmtT(tm.t1)} UTC${total > marks.length ? `; the first ${marks.length.toLocaleString("en-US")} are drawn` : ""}. A tick is an instant report, a bar one with a duration; taller and darker = larger hail or stronger wind; dashed or hollow = county/zone report with no point on the map.${tm.shade ? " Shaded: storm centre over the Texas box." : ""}`;
  const tip = $("timeline-tip"); const svgEl = box.querySelector("svg");
  svgEl.onmousemove = (e) => {
    const i = e.target.dataset && e.target.dataset.i; if (i === undefined) { tip.classList.add("hidden"); return; }
    const t = index.types[ev.type[i]]; const m = ev.mag[i]; const u = index.magnitude_units[t];
    tip.textContent = `${t} · ${fmtT(minToMs(ev.begin[i]))} UTC${ev.end[i] > ev.begin[i] ? ` for ${ev.end[i] - ev.begin[i]} min` : ""}${m === m && u ? ` · ${m} ${u}` : ""}${ev.lon[i] === ev.lon[i] ? "" : " · county/zone"}`;
    const r = $("timebar").getBoundingClientRect(); tip.style.left = `${Math.max(4, Math.min(r.width - 320, e.clientX - r.left + 10))}px`; tip.style.top = `${e.clientY - r.top - 28 + $("timebar").scrollTop}px`; tip.classList.remove("hidden");
  };
  svgEl.onmouseleave = () => tip.classList.add("hidden");
  svgEl.onclick = (e) => {
    const i = e.target.dataset && e.target.dataset.i; if (i === undefined) { const r = svgEl.getBoundingClientRect(); const px = ((e.clientX - r.left) / r.width) * W; if (px >= L) { stopPlay(); tm.now = Math.min(tm.t1, Math.max(tm.t0, tm.t0 + ((px - L) / (W - L - R)) * (tm.t1 - tm.t0))); drawFrame(); } return; }
    showEvent(el, Number(i)); drawFrame(); if (ev.lon[i] === ev.lon[i]) state.map.easeTo({ center: [ev.lon[i], ev.lat[i]], duration: 300 });
  };
  document.body.dataset.timelineMs = (performance.now() - started).toFixed(1); document.body.dataset.timelineMarks = marks.length; document.body.dataset.timelineRows = rows.length;
}
api.drawFrame = drawFrame;
