// Tropical cyclone tracks (IBTrACS) with wind extent, moved from site/app.js.
import { $, state, api, esc, LineLayer, SolidPolygonLayer, PathLayer, layerById, fetchJSON, ramp, colorAt, rgbCss, parseT, kv, openDetail, closeDetail, quantile } from "./core.js";
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
  const chosen = state.extent && state.storm !== null ? match.find((s) => s.sid === state.storm) : null;
  const avg = chosen ? avgSummary(chosen) : [];
  if (avg.length) {
    rows.push({ color: rgbCss(stops[6]), shape: "ring dashed", label: "average radius, not observed" });
    section.foot = `Dashed circle: at fixes with no 34 kt radii, one radius from the agency record drawn as a circle (${avg.map(avgText).join("; ")}). A single average radius, not an observed wind extent. ${section.foot}`;
  }
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
  return [...(state.extent ? swathLayers(layer, match) : []), ...(state.extent && chosen ? avgRadiusLayers(layer, chosen) : []),
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
  // the single radius follows the nearer fix; it is interpolated only when the other fix carries the same kind
  const near = avgRadius(f < 0.5 ? a : b), far = avgRadius(f < 0.5 ? b : a);
  const avg = near && far && far.kind === near.kind ? { kind: near.kind, nm: near.nm + (far.nm - near.nm) * (f < 0.5 ? f : 1 - f) } : near;
  return { lon: a[0] + (b[0] - a[0]) * f, lat: a[1] + (b[1] - a[1]) * f, wind: mix(a[2], b[2]), r: [lerpR(a[7], b[7], f), lerpR(a[8], b[8], f), lerpR(a[9], b[9], f)], avg };
}
const fixAt0 = (p) => ({ lon: p[0], lat: p[1], wind: p[2], r: [p[7], p[8], p[9]], avg: avgRadius(p) });
// ---------- a single radius where the fix has no 34 kt quadrant radii ----------
// IBTrACS carries two single radii per fix (USA_ROCI, USA_RMW; nautical miles). Neither is a wind extent: the outermost closed
// isobar is the storm's outer size on the pressure map, the radius of maximum wind is the inner core. The outer one is preferred.
export const NM_KM = 1.852;
export const AVG_NAME = { roci: "radius of the outermost closed isobar", rmw: "radius of maximum wind" };
export const nmKm = (nm) => `${Math.round(nm)} nmi (${Math.round(nm * NM_KM)} km)`;
const maxR34 = (p) => (p[7] ? Math.max(...p[7].map((v) => v || 0)) : 0);
export function avgRadius(p) {
  if (maxR34(p) > 0) return null;
  return p[11] > 0 ? { kind: "roci", nm: p[11] } : p[10] > 0 ? { kind: "rmw", nm: p[10] } : null;
}
// per kind: how many fixes of the storm get the circle, and the range of the radius
export function avgSummary(s) {
  if (!s._avg) {
    const by = {}; for (const p of s.points) { const a = avgRadius(p); if (!a) continue; const k = (by[a.kind] ||= { kind: a.kind, n: 0, min: Infinity, max: -Infinity }); k.n++; k.min = Math.min(k.min, a.nm); k.max = Math.max(k.max, a.nm); }
    s._avg = ["roci", "rmw"].map((k) => by[k]).filter(Boolean);
  }
  return s._avg;
}
const avgText = (a) => `${AVG_NAME[a.kind]}, ${a.min === a.max ? nmKm(a.min) : `${Math.round(a.min)}–${nmKm(a.max)}`} at ${a.n} fix${a.n > 1 ? "es" : ""}`;
// a circle as short dashes (deck.gl's PathLayer has no dash without an extension)
export function dashedRing(lon, lat, nm) {
  const step = nm < 40 ? 15 : 5; const ring = ringAt(lon, lat, [nm, nm, nm, nm], step); const out = [];
  for (let i = 0; i < ring.length; i += 2) out.push([ring[i], ring[i + 1]]);
  return out;
}
function avgRadiusLayers(layer, s) {
  // along the whole track only for storms with no 34 kt radii at all; elsewhere the player draws the circle at the current fix
  if (s.extent_points.r34 || !avgSummary(s).length) return [];
  const data = []; for (const p of s.points) { const a = avgRadius(p); if (a) data.push(...dashedRing(p[0], p[1], a.nm)); }
  return [new PathLayer({ id: "avg-radius", data, getPath: (d) => d, getColor: [...ramp(layer.style)[6], 110], widthUnits: "pixels", getWidth: 1, pickable: false })];
}
// ---------- reports near the track ----------
// The fixed distance used where a fix has no 34 kt radii: the median, over every fix in this file that has them, of the
// largest quadrant radius, rounded to 5 nmi.
export function nearDistance() {
  const T = state.tracks;
  if (!T._near) {
    const v = []; let storms = 0;
    for (const s of T.storms) { let any = false; for (const p of s.points) { const m = maxR34(p); if (m > 0) { v.push(m); any = true; } } storms += any; }
    v.sort((a, b) => a - b); const median = quantile(v, 0.5);
    T._near = { nm: Math.round(median / 5) * 5, median, fixes: v.length, storms };
  }
  return T._near;
}
// (lon, lat, ms) -> is the report near the storm? Inside the largest 34 kt quadrant radius of the nearest-in-time fix, measured
// from the storm centre at the report's time; where that fix has no 34 kt radii, within the fixed distance of the track line.
export function nearTester(s) {
  const t = stormTimes(s); const n = t.length; const D = nearDistance().nm; const r34 = s.points.map(maxR34);
  const rad = Math.PI / 180;
  return (lon, lat, ms) => {
    let i = 0; while (i < n - 1 && t[i + 1] <= ms) i++; if (i < n - 1 && t[i + 1] - ms < ms - t[i]) i++;
    const cos = Math.cos(lat * rad); const dx = (p) => (p[0] - lon) * cos * 60, dy = (p) => (p[1] - lat) * 60; // nautical miles, flat around the report
    if (r34[i] > 0) { const c = fixAt(s, ms); return Math.hypot(dx([c.lon, c.lat]), dy([c.lon, c.lat])) <= r34[i]; }
    let best = Infinity;
    for (let k = 0; k + 1 < n; k++) {
      const ax = dx(s.points[k]), ay = dy(s.points[k]), bx = dx(s.points[k + 1]), by = dy(s.points[k + 1]);
      const l2 = (bx - ax) ** 2 + (by - ay) ** 2; const u = l2 ? Math.min(1, Math.max(0, -(ax * (bx - ax) + ay * (by - ay)) / l2)) : 0;
      best = Math.min(best, Math.hypot(ax + (bx - ax) * u, ay + (by - ay) * u)); if (best <= D) return true;
    }
    return false;
  };
}
// the rule in words for the stretch [t0, t1] of one storm
export function nearRule(s, t0, t1) {
  const t = stormTimes(s); const d = nearDistance(); let lo = Infinity, hi = -Infinity, withR = 0, without = 0;
  s.points.forEach((p, i) => { if (t[i] < t0 || t[i] > t1) return; const m = maxR34(p); if (m > 0) { withR++; lo = Math.min(lo, m); hi = Math.max(hi, m); } else without++; });
  const fixed = `within ${nmKm(d.nm)} of the track line`;
  const origin = `${d.nm} nmi is the median 34 kt radius in this file (largest quadrant, ${d.fixes} fixes of ${d.storms} storms${d.median === d.nm ? "" : `, ${d.median.toFixed(1)} rounded`})`;
  const km = (v) => Math.round(v * NM_KM);
  const text = withR
    ? `Near the track = inside the 34 kt wind radius at the nearest fix in time (${lo === hi ? nmKm(lo) : `${Math.round(lo)}–${Math.round(hi)} nmi, ${km(lo)}–${km(hi)} km`} here)${without ? `; where the fix has none, ${fixed}, the median 34 kt radius in this file` : ""}.`
    : `Near the track = ${fixed}: this storm has no 34 kt wind radii in the record; ${d.nm} nmi is the median 34 kt radius of the storms that have them.`;
  const title = `The 34 kt radius is the largest of the four quadrant radii, measured from the storm centre at the report's begin time; ${withR} of ${withR + without} fixes in this window have one. ${origin}.`;
  return { text, title, withR, without, lo, hi, ...d };
}
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
  // a band with no rings is left out altogether: handed an empty list, the layer kept drawing the previous storm's band
  return rings.map((data, b) => data.length === 0 ? null : new SolidPolygonLayer({
    id: `swath-${b}`, data, getPolygon: (d) => d, pickable: false, filled: true,
    getFillColor: [base[0] * BAND_ALPHA[b], base[1] * BAND_ALPHA[b], base[2] * BAND_ALPHA[b], 255 * BAND_ALPHA[b]],
    parameters: { blend: true, blendColorOperation: "max", blendAlphaOperation: "max", blendColorSrcFactor: "one", blendColorDstFactor: "one", blendAlphaSrcFactor: "one", blendAlphaDstFactor: "one", depthCompare: "always" },
  })).filter(Boolean);
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
    ["Size where no wind radii", `${avgSummary(s).length ? `dashed circle: ${avgSummary(s).map(avgText).join("; ")}. A single average radius from the agency record, not an observed wind extent.` : "no single radius (outermost closed isobar or maximum wind) in the record at fixes without 34 kt radii"}<br><small id="storm-avg-now"></small>`],
    ["Wind extent", s.extent_points.r34 ? `34 kt radii at ${s.extent_points.r34} fixes, 64 kt at ${s.extent_points.r64}${s.extent_points.rmw ? `; radius of maximum wind at ${s.extent_points.rmw}` : ""}` : `no wind-radius estimate in IBTrACS for this storm${s.extent_points.rmw ? ` (radius of maximum wind at ${s.extent_points.rmw} fixes)` : ""}`],
    ["In the Texas box", `${esc(s.first_texas_point)} to ${esc(s.last_texas_point)} UTC`], ["Track shown", `${s.points.length} points, ${esc(first)} to ${esc(last)} UTC`], ["Wind source", s.wind_source === "wmo" ? "WMO agency" : s.wind_source === "usa" ? "US agency" : "WMO where present, else US agency"],
  ], true);
  $("detail-table").innerHTML = ""; $("detail-params").innerHTML = "";
  $("detail-foot").textContent = "Best-track observations of the storm centre. Winds are agency estimates of the maximum sustained wind near the centre, not winds at any place; nothing here is a return-period curve.";
  drawSeries(s.points.map((p) => p[2]), s.points.map((p) => p[5]), "kt", stops, s.points.map((p) => p[0] >= state.tracks.texas_box[0] && p[0] <= state.tracks.texas_box[2] && p[1] >= state.tracks.texas_box[1] && p[1] <= state.tracks.texas_box[3]));
}
