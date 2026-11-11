// Station layers (GeoJSON points: CO-OPS water levels, GHCNh airport stations), moved from site/app.js.
import { $, state, api, esc, GeoJsonLayer, layersOfSource, fetchJSON, fmt, ramp, rgbCss, kv, openDetail, latLon } from "./core.js";
import { drawCurve } from "./charts.js";

export async function loadGeo(l) {
  const key = `geo:${l.id}`;
  if (!state.files.has(key)) state.files.set(key, await fetchJSON(l.file));
  return state.files.get(key);
}
const keyOf = (l, f) => `${l.id}:${(f.properties || {}).label || f.geometry.coordinates.join(",")}`;
export function geoLayer(l, data) {
  const s = l.style || {};
  return new GeoJsonLayer({
    id: `geo:${l.id}`, data, pickable: true, autoHighlight: true, highlightColor: [11, 11, 11, 60],
    pointType: "circle", pointRadiusUnits: "pixels", getPointRadius: s.radius || 5,
    getFillColor: s.fill || [42, 120, 214, 200], getLineColor: s.line || [255, 255, 255, 220],
    lineWidthUnits: "pixels", getLineWidth: s.width || 1, lineWidthMinPixels: s.width || 1,
    stroked: true, filled: true,
    onClick: (info) => { showFeature(l, info.object); return true; },
  });
}
// The value a station is read by on hover and in the legend: its level at 1 in 100 years when shipped, else at the rarest level shipped.
function headline(feature) {
  const c = (feature.properties || {}).curve; if (!c || !Array.isArray(c.return_periods) || !Array.isArray(c.values)) return null;
  let i = c.return_periods.indexOf(100); if (i < 0) i = c.return_periods.length - 1;
  return c.values[i] === null || c.values[i] === undefined ? null : { rp: c.return_periods[i], value: c.values[i], unit: c.unit || "" };
}
export function geoHover(l, feature) {
  const p = feature.properties || {}; const h = headline(feature);
  return `<b>${esc(p.label || l.title)}</b>${h ? `<br>${fmt(h.value)} ${esc(h.unit)} <span>· 1 in ${h.rp} years</span>` : ""}<br><span>${esc(l.title)}</span>`;
}
export function geoLegend(l, data) {
  const s = l.style || {}; const hs = data.features.map(headline).filter(Boolean); const section = { title: l.title, unit: `${data.features.length} stations`, rows: [{ color: rgbCss(s.fill || [42, 120, 214]), label: "station; click for its levels", n: data.features.length }] };
  if (hs.length) {
    const vals = hs.map((h) => h.value); const rps = [...new Set(hs.map((h) => h.rp))];
    section.unit = hs[0].unit;
    // the record behind the levels, where the file states it per station (CO-OPS trend period)
    const years = data.features.flatMap((f) => String((f.properties || {}).trend_period || "").match(/\d{4}/g) || []).map(Number);
    if (years.length) section.unit += ` · station records ${Math.min(...years)}–${Math.max(...years)}`;
    section.foot = `1-in-${rps.length === 1 ? rps[0] : "100"}-year level across ${hs.length} stations: ${fmt(Math.min(...vals))} to ${fmt(Math.max(...vals))} ${hs[0].unit}. ${l.source}.`;
  } else section.foot = `${l.source}.`;
  return section;
}
export function buildStationsList() {
  const own = layersOfSource(state.source).filter((l) => l.kind === "points"); const list = $("stations-list"); const top = list.scrollTop; list.innerHTML = "";
  let count = 0;
  for (const l of own) {
    const data = state.files.get(`geo:${l.id}`); if (!data) continue;
    for (const f of data.features) {
      count++;
      const li = document.createElement("li"); const p = f.properties || {}; const h = headline(f);
      li.className = state.pick && state.pick.key === keyOf(l, f) ? "sel" : "";
      li.innerHTML = `<span>${esc(p.label || l.title)}</span><span class="mute num">${h ? `${fmt(h.value)}` : ""}</span>`;
      li.onclick = () => { state.map.jumpTo({ center: f.geometry.coordinates, zoom: Math.max(state.map.getZoom(), 7) }); showFeature(l, f); };
      list.append(li);
    }
  }
  list.scrollTop = top;
  const any = own.map((l) => state.files.get(`geo:${l.id}`)).filter(Boolean).flatMap((d) => d.features).map(headline).find(Boolean);
  $("stations-status").textContent = `${count} stations${any ? `; the number is the 1-in-${any.rp}-year level, ${any.unit}` : ""}. Pick one for its levels or curve.`;
}
export function showFeature(l, feature) {
  const p = feature.properties || {}; state.selected = null;
  state.pick = { kind: "point", position: feature.geometry.coordinates, key: keyOf(l, feature) };
  openDetail(p.label ? `${p.label}` : l.title, l.title);
  const skip = new Set(["curve", "label"]); const h = headline(feature);
  const head = h ? [[`1 in ${h.rp} years`, `<span class="big">${fmt(h.value)}</span> <small>${esc(h.unit)}</small>`]] : [];
  const where = [["Location", latLon(feature.geometry.coordinates[1], feature.geometry.coordinates[0])]];
  if (Array.isArray(l.panel_groups)) { // grouping is declared on the layer in layers.json
    const cell = (v, f) => (f === "percent" ? `${(100 * v).toFixed(v < 0.01 ? 3 : 2)}%` : f === "percent0" ? `${(100 * v).toFixed(0)}%` : typeof v === "boolean" ? (v ? "yes" : "no") : String(v));
    const rows = [...head, ...where, "Source", ["Layer", esc(l.title)], ["From", esc(l.source)]];
    for (const g of l.panel_groups) {
      const own = g.fields.filter(([k]) => p[k] !== null && p[k] !== undefined && typeof p[k] !== "object").map(([k, label, f]) => [label || k.replaceAll("_", " "), esc(cell(p[k], f))]);
      if (own.length) rows.push(g.title, ...own);
    }
    $("detail-meta").innerHTML = kv(rows, true); $("detail-meta").dataset.groups = l.panel_groups.length;
  } else {
    const meta = [...head, ...where];
    for (const [k, v] of Object.entries(p)) if (!skip.has(k) && v !== null && typeof v !== "object") meta.push([k.replaceAll("_", " "), esc(String(v))]);
    meta.push(["Source", esc(l.source)]);
    $("detail-meta").innerHTML = kv(meta, true); delete $("detail-meta").dataset.groups;
  }
  $("detail-params").innerHTML = ""; $("detail-foot").textContent = l.caveat || "";
  const c = p.curve;
  if (c && Array.isArray(c.return_periods) && Array.isArray(c.values)) {
    $("detail-table").innerHTML = `<tr><th>Return period</th><th class="num">${esc(c.unit || "")}</th></tr>` + c.return_periods.map((t, i) => `<tr><td>1 in ${t} years</td><td class="num">${fmt(c.values[i])}</td></tr>`).join("");
    drawCurve(c.return_periods, c.values, c.unit || "", ramp(l.style && l.style.hue !== undefined ? l.style : { hue: 250, chroma: 0.14 }));
    if (c.note) $("detail-params").innerHTML = kv([["Curve", c.note]]);
  } else { $("detail-table").innerHTML = ""; $("chart").innerHTML = ""; }
  if (state.source === l.source_id) buildStationsList();
  api.drawFrame();
}
