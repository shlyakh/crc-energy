// Tropical cyclone tracks (IBTrACS) with wind extent, moved from site/app.js.
import { $, state, api, esc, LineLayer, SolidPolygonLayer, PathLayer, layerById, fetchJSON, ramp, colorAt, rgbCss, parseT, kv, openDetail, closeDetail } from "./core.js";
import { drawSeries } from "./charts.js";

const WIND_DOMAIN = [20, 140];
// Saffir-Simpson classes as NOAA defines them (1-minute sustained wind, knots); the data carries the class per fix (USA_SSHS).
const CATEGORIES = [["-5", "not a tropical cyclone / unknown", ""], ["-1", "tropical depression", "≤ 33 kt"], ["0", "tropical storm", "34–63 kt"], ["1", "category 1", "64–82 kt"], ["2", "category 2", "83–95 kt"], ["3", "category 3", "96–112 kt"], ["4", "category 4", "113–136 kt"], ["5", "category 5", "≥ 137 kt"]];
export async function loadTracks(layer) {
  if (!state.tracks) {
    state.tracks = await fetchJSON(layer.file);
    const f = state.tracksFilter; const seasons = state.tracks.storms.map((s) => s.season);
    if (f.from === null) { f.from = Math.min(...seasons); f.to = Math.max(...seasons); }
  }
  return state.tracks;
}
export function tracksMatch() {
  const f = state.tracksFilter; const q = f.name.trim().toLowerCase();
  return state.tracks.storms.filter((s) => s.season >= f.from && s.season <= f.to && (!q || s.name.toLowerCase().includes(q)) && (s.max_wind_kt || 0) >= f.minWind);
}
function categoryColor(layer, cat) { const c = layer.style.category_colors; return (cat === null || cat === undefined ? null : c[String(cat)]) || c["-5"]; }
function windColor(stops, w) { return w === null ? [160, 160, 158] : colorAt(stops, 0.3 + 0.7 * Math.min(1, Math.max(0, (w - WIND_DOMAIN[0]) / (WIND_DOMAIN[1] - WIND_DOMAIN[0]))), 255).slice(0, 3); }
export function selectStorm(s) {
  state.storm = s ? s.sid : null; state.pick = null; state.selected = null;
  const done = api.render(); if (s) showStorm(s); else closeDetail();
  return done;
}
export function buildTracksControls() {
  if (!state.tracks) return;
  const f = state.tracksFilter;
  $("tracks-from").value = f.from; $("tracks-to").value = f.to; if ($("tracks-name").value !== f.name) $("tracks-name").value = f.name; $("tracks-min-wind").value = f.minWind; $("tracks-color").value = f.colorBy;
  $("tracks-from").onchange = (e) => { f.from = Number(e.target.value); api.render(); };
  $("tracks-to").onchange = (e) => { f.to = Number(e.target.value); api.render(); };
  $("tracks-name").oninput = (e) => { f.name = e.target.value; api.render(); };
  $("tracks-min-wind").onchange = (e) => { f.minWind = Number(e.target.value) || 0; api.render(); };
  $("tracks-color").onchange = (e) => { f.colorBy = e.target.value; api.render(); };
  $("tracks-extent").checked = state.extent; $("tracks-extent").onchange = (e) => { state.extent = e.target.checked; api.render(); };
  const match = tracksMatch(); const list = $("tracks-list"); const top = list.scrollTop; list.innerHTML = "";
  for (const s of [...match].sort((a, b) => b.season - a.season || a.name.localeCompare(b.name))) {
    const li = document.createElement("li"); li.className = state.storm === s.sid ? "sel" : ""; li.dataset.sid = s.sid;
    li.innerHTML = `<span>${esc(s.label)}</span><span class="mute num">${s.max_wind_kt === null ? "–" : `${s.max_wind_kt} kt`}${s.max_category !== null && s.max_category > 0 ? ` · cat ${s.max_category}` : ""}</span>`;
    li.onclick = () => selectStorm(state.storm === s.sid ? null : s);
    list.append(li);
  }
  list.scrollTop = top;
  $("tracks-status").textContent = `${match.length} of ${state.tracks.storms.length} storms (${f.from}–${f.to}${f.minWind ? `, at least ${f.minWind} kt` : ""}${f.name ? `, name contains “${f.name}”` : ""}). Pick one to play it.`;
}
export function tracksLegend(layer) {
  const f = state.tracksFilter; const stops = ramp(layer.style); const match = tracksMatch(); const rows = [];
  const section = { title: "Tropical cyclone tracks", foot: `Seasons ${f.from}–${f.to}: ${match.length} of ${state.tracks.storms.length} storms shown. Wind is the agency's maximum sustained wind near the centre, not the wind at a place.` };
  if (f.colorBy === "wind") {
    const ticks = [20, 50, 80, 110, 140];
    section.unit = "kt (knots), wind along the track";
    section.ramps = [{ css: `linear-gradient(90deg, ${Array.from({ length: 7 }, (_, i) => rgbCss(windColor(stops, WIND_DOMAIN[0] + ((WIND_DOMAIN[1] - WIND_DOMAIN[0]) * i) / 6))).join(",")})`, ticks: ticks.map((t, i) => (i === 0 ? `≤ ${t}` : i === ticks.length - 1 ? `≥ ${t}` : String(t))) }];
    rows.push({ color: "rgb(160,160,158)", shape: "line", label: "wind not given" });
  } else {
    section.unit = "Saffir-Simpson class, wind in kt (knots)";
    for (const [k, t, range] of CATEGORIES) rows.push({ color: rgbCss(layer.style.category_colors[k]), shape: "line", label: t, n: range });
  }
  if (state.extent) { const b = stops[5]; ["34 kt", "50 kt", "64 kt"].forEach((t, i) => rows.push({ color: `rgba(${b.join(",")},${BAND_ALPHA[i]})`, shape: "box", label: `${t} wind radius (estimate)` })); }
  section.rows = rows;
  return section;
}
export function tracksLayers(layer) {
  const f = state.tracksFilter; const stops = ramp(layer.style); const match = tracksMatch();
  const segments = [];
  for (const s of match) {
    const pts = s.points;
    for (let i = 0; i + 1 < pts.length; i++) segments.push({ sid: s.sid, label: s.label, i, a: [pts[i][0], pts[i][1]], b: [pts[i + 1][0], pts[i + 1][1]], w: pts[i][2], cat: pts[i][4], t: pts[i][5] });
  }
  const dim = state.storm !== null;
  const color = (d) => { const base = f.colorBy === "wind" ? windColor(stops, d.w) : categoryColor(layer, d.cat); return [...base, dim && d.sid !== state.storm ? 70 : 230]; };
  const chosen = dim ? match.find((s) => s.sid === state.storm) : null;
  return [...(state.extent ? swathLayers(layer, match) : []),
    // the selected track on a white casing, so it reads over the dimmed ones
    ...(chosen ? [new PathLayer({ id: "sel-track", data: [chosen.points.map((p) => [p[0], p[1]])], getPath: (d) => d, getColor: [255, 255, 255, 235], widthUnits: "pixels", getWidth: 8, jointRounded: true, capRounded: true, pickable: false })] : []),
    new LineLayer({
      id: "tracks", data: segments, pickable: true, widthUnits: "pixels",
      getSourcePosition: (d) => d.a, getTargetPosition: (d) => d.b, getColor: color, getWidth: (d) => (d.sid === state.storm ? 4 : 2),
      updateTriggers: { getColor: [f.colorBy, state.storm], getWidth: [state.storm] },
      onClick: (info) => { selectStorm(state.tracks.storms.find((x) => x.sid === info.object.sid)); return true; },
    })];
}
// wind extent: quadrant radii (NE, SE, SW, NW; nautical miles) -> a smooth outline around a fix
function radiusAt(r4, bearing) {
  // cosine interpolation between neighbouring quadrant centres; a missing quadrant counts as 0
  const b = ((bearing - 45) % 360 + 360) % 360; const k = Math.floor(b / 90); const f = (b - k * 90) / 90;
  const a = r4[k % 4] || 0, c = r4[(k + 1) % 4] || 0; const t = (1 - Math.cos(Math.PI * f)) / 2;
  return a + (c - a) * t;
}
export function ringAt(lon, lat, r4, step = 10) {
  const out = []; const cos = Math.cos((lat * Math.PI) / 180);
  for (let b = 0; b < 360; b += step) { const r = radiusAt(r4, b) / 60; const rad = (b * Math.PI) / 180; out.push([lon + (r * Math.sin(rad)) / cos, lat + r * Math.cos(rad)]); }
  return out;
}
function lerpR(a, b, f) { if (!a && !b) return null; const x = a || [0, 0, 0, 0], y = b || [0, 0, 0, 0]; return x.map((v, i) => (v || 0) + ((y[i] || 0) - (v || 0)) * f); }
export function stormTimes(s) { if (!s._t) s._t = s.points.map((p) => parseT(p[5])); return s._t; }
export function fixAt(s, ms) {
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
export function trackHover(d) { return `<b>${esc(d.label)}</b><br>${d.w === null ? "wind not given" : `${d.w} kt`}${d.cat !== null && d.cat > 0 ? ` · category ${d.cat}` : ""}<br><span>${esc(d.t)} UTC</span>`; }
export function showStorm(s) {
  const layer = layerById("ibtracs"); const stops = ramp(layer.style);
  openDetail(s.label, "Tropical cyclone track · IBTrACS best track");
  const first = s.points[0][5], last = s.points[s.points.length - 1][5];
  $("detail-meta").innerHTML = kv([
    ["Peak wind on the track", s.max_wind_kt === null ? "–" : `<span class="big">${s.max_wind_kt}</span> <small>kt (${(s.max_wind_kt * 0.514444).toFixed(0)} m/s)</small>`],
    ["Peak wind over the Texas box", s.max_wind_kt_in_texas === null ? "–" : `${s.max_wind_kt_in_texas} kt`],
    ["Lowest pressure", s.min_pressure_mb === null ? "–" : `${s.min_pressure_mb} mb`], ["Highest category", s.max_category === null ? "–" : s.max_category <= 0 ? "below hurricane strength" : `${s.max_category} <small>Saffir-Simpson, NOAA USA_SSHS</small>`],
    ["Storm id", esc(s.sid)], ["Season", s.season],
    ["Wind extent", s.extent_points.r34 ? `34 kt radii at ${s.extent_points.r34} fixes, 64 kt at ${s.extent_points.r64}${s.extent_points.rmw ? `; radius of maximum wind at ${s.extent_points.rmw}` : ""}` : `no wind-radius estimate in IBTrACS for this storm${s.extent_points.rmw ? ` (radius of maximum wind at ${s.extent_points.rmw} fixes)` : ""}`],
    ["In the Texas box", `${esc(s.first_texas_point)} to ${esc(s.last_texas_point)} UTC`], ["Track shown", `${s.points.length} points, ${esc(first)} to ${esc(last)} UTC`], ["Wind source", s.wind_source === "wmo" ? "WMO agency" : s.wind_source === "usa" ? "US agency" : "WMO where present, else US agency"],
  ], true);
  $("detail-table").innerHTML = ""; $("detail-params").innerHTML = "";
  $("detail-foot").textContent = "Best-track observations of the storm centre. Winds are agency estimates of the maximum sustained wind near the centre, not winds at any place; nothing here is a return-period curve.";
  drawSeries(s.points.map((p) => p[2]), s.points.map((p) => p[5]), "kt", stops, s.points.map((p) => p[0] >= state.tracks.texas_box[0] && p[0] <= state.tracks.texas_box[2] && p[1] >= state.tracks.texas_box[1] && p[1] <= state.tracks.texas_box[3]));
}
