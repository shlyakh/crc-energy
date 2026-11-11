// Storm reports (NOAA Storm Events, a binary point file), moved from site/app.js.
import { $, state, api, esc, ScatterplotLayer, layerById, fetchJSON, asset, rgbCss, minToMs, fmtT, kv, openDetail, latLon } from "./core.js";

export async function loadEvents(layer) {
  if (state.events) return state.events;
  const [index, buffer] = await Promise.all([fetchJSON(layer.index), fetch(asset(layer.file)).then((r) => { if (!r.ok) throw new Error(`${layer.file}: ${r.status}`); return r.arrayBuffer(); })]);
  const n = Math.floor(buffer.byteLength / index.record_bytes); const view = new DataView(buffer);
  const lon = new Float32Array(n), lat = new Float32Array(n), mag = new Float32Array(n), dmg = new Float32Array(n);
  const year = new Uint16Array(n), type = new Uint8Array(n), id = new Uint32Array(n), begin = new Uint32Array(n), end = new Uint32Array(n);
  const off = Object.fromEntries(index.fields.map((f) => [f.name, f.offset])); const rb = index.record_bytes;
  for (let i = 0; i < n; i++) {
    const b = i * rb;
    lon[i] = view.getFloat32(b + off.lon, true); lat[i] = view.getFloat32(b + off.lat, true);
    year[i] = view.getUint16(b + off.year, true); type[i] = view.getUint8(b + off.type);
    mag[i] = view.getFloat32(b + off.magnitude, true); id[i] = view.getUint32(b + off.event_id, true);
    dmg[i] = view.getFloat32(b + off.damage_usd, true);
    begin[i] = view.getUint32(b + off.begin_min, true); end[i] = view.getUint32(b + off.end_min, true);
  }
  state.events = { index, n, lon, lat, year, type, mag, id, dmg, begin, end };
  if (state.eventsFilter.from === null) {
    state.eventsFilter.from = index.years[0]; state.eventsFilter.to = index.years[1];
    state.eventsFilter.types = new Set((layer.default_types || index.types).filter((t) => index.types.includes(t)));
  }
  return state.events;
}
export function eventColor(layer, typeName) { return layer.style.colors[typeName] || layer.style.other; }
export function buildEventsControls() {
  if (!state.events) return;
  const layer = layerById("storm_events"); const { index } = state.events; const f = state.eventsFilter;
  $("events-from").value = f.from; $("events-to").value = f.to;
  $("events-from").min = index.years[0]; $("events-to").max = index.years[1];
  $("events-from").onchange = (e) => { f.from = Number(e.target.value); api.render(); };
  $("events-to").onchange = (e) => { f.to = Number(e.target.value); api.render(); };
  const w = state.win;
  $("win-on").checked = w.on; $("win-start").value = w.start; $("win-days").value = w.days;
  $("win-row").classList.toggle("hidden", !w.on); $("years-row").classList.toggle("hidden", w.on);
  $("win-on").onchange = (e) => { w.on = e.target.checked; state.pick = null; api.render(); };
  $("win-start").onchange = (e) => { if (e.target.value) { w.start = e.target.value; api.render(); } };
  $("win-days").onchange = (e) => { w.days = Math.min(14, Math.max(1, Number(e.target.value) || 1)); api.render(); };
  const types = $("events-types"); const top = types.scrollTop; types.innerHTML = "";
  const order = [...index.types].sort((a, b) => (index.counts[b] || 0) - (index.counts[a] || 0));
  for (const t of order) {
    const lab = document.createElement("label"); const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = f.types.has(t);
    cb.onchange = () => { if (cb.checked) f.types.add(t); else f.types.delete(t); api.render(); };
    const sw = document.createElement("span"); sw.className = "swatch"; sw.style.background = rgbCss(eventColor(layer, t));
    lab.append(cb, sw, document.createTextNode(t), Object.assign(document.createElement("span"), { className: "mute num", textContent: (index.counts[t] || 0).toLocaleString("en-US") }));
    types.append(lab);
  }
  types.scrollTop = top;
}
export function eventsLayer(layer) {
  const ev = state.events; const f = state.eventsFilter; const { index } = ev;
  const typeOn = new Uint8Array(index.types.length); index.types.forEach((t, i) => { typeOn[i] = f.types.has(t) ? 1 : 0; });
  const keep = []; const shown = new Map();
  for (let i = 0; i < ev.n; i++) if (typeOn[ev.type[i]] && ev.year[i] >= f.from && ev.year[i] <= f.to && ev.lon[i] === ev.lon[i]) { keep.push(i); shown.set(ev.type[i], (shown.get(ev.type[i]) || 0) + 1); }
  state.eventsShown = { total: keep.length, byType: shown };
  const colors = index.types.map((t) => eventColor(layer, t));
  return new ScatterplotLayer({
    id: "events", data: keep, pickable: true, radiusUnits: "pixels", getRadius: 3, radiusMinPixels: 2, radiusMaxPixels: 6,
    stroked: true, lineWidthMinPixels: 1, getLineColor: [255, 255, 255, 160], opacity: 0.85,
    getPosition: (i) => [ev.lon[i], ev.lat[i]], getFillColor: (i) => colors[ev.type[i]],
    updateTriggers: { getFillColor: [layer.id] },
    onClick: (info) => { showEvent(layer, info.object); api.drawFrame(); return true; },
  });
}
// Legend: the report types on the map with their colours, counts under the current filter and magnitude units.
export function eventsLegend(layer) {
  const ev = state.events; const { index } = ev; const f = state.eventsFilter; const tm = state.time && state.time.mode === "window" ? state.time : null;
  let byType = state.eventsShown ? state.eventsShown.byType : new Map(); let period = `${f.from}–${f.to}`;
  if (tm) {
    byType = new Map(); period = `${fmtT(tm.t0).slice(0, 10)} + ${state.win.days} days (UTC)`;
    for (let i = tm.range[0]; i < tm.range[1]; i++) if (f.types.has(index.types[ev.type[i]]) && ev.lon[i] === ev.lon[i]) byType.set(ev.type[i], (byType.get(ev.type[i]) || 0) + 1);
  }
  const on = index.types.map((t, c) => ({ t, c, n: byType.get(c) || 0 })).filter((d) => f.types.has(d.t)).sort((a, b) => b.n - a.n);
  const named = on.filter((d) => layer.style.colors[d.t]), other = on.filter((d) => !layer.style.colors[d.t]);
  const unit = (t) => (index.magnitude_units[t] ? `, ${index.magnitude_units[t]}` : "");
  const rows = named.map((d) => ({ color: rgbCss(eventColor(layer, d.t)), label: `${d.t}${unit(d.t)}`, n: d.n }));
  if (other.length) rows.push({ color: rgbCss(layer.style.other), label: other.length === 1 ? other[0].t : `${other.length} other types`, n: other.reduce((a, d) => a + d.n, 0) });
  const total = on.reduce((a, d) => a + d.n, 0);
  $("events-status").textContent = tm ? `${total.toLocaleString("en-US")} located reports begin in the window; the time bar under the map plays them.` : `${total.toLocaleString("en-US")} of ${index.events.toLocaleString("en-US")} located reports shown (${f.from}–${f.to}). ${index.events_without_point.toLocaleString("en-US")} county/zone reports have no point and are not drawn.`;
  return {
    title: "Storm reports by type", unit: `reports with a point · ${period}`, rows,
    foot: `${total.toLocaleString("en-US")} reports on the map. Hail size in inches, wind in knots. Reports follow people: an empty area may be unobserved.`,
  };
}
export function eventHover(i) {
  const ev = state.events; const t = ev.index.types[ev.type[i]]; const u = ev.index.magnitude_units[t];
  return `<b>${esc(t)}</b>${Number.isNaN(ev.mag[i]) ? "" : ` · ${ev.mag[i]} ${esc(u || "")}`}<br><span>${ev.begin[i] ? `${fmtT(minToMs(ev.begin[i]))} UTC` : ev.year[i]}</span>`;
}
export function showEvent(layer, i) {
  const ev = state.events; const { index } = ev; const t = index.types[ev.type[i]];
  const unit = index.magnitude_units[t]; const mag = Number.isNaN(ev.mag[i]) ? null : ev.mag[i]; const dmg = Number.isNaN(ev.dmg[i]) ? null : ev.dmg[i];
  const located = ev.lon[i] === ev.lon[i];
  state.selected = null; state.pick = located ? { kind: "point", position: [ev.lon[i], ev.lat[i]], key: `event:${ev.id[i]}` } : null;
  openDetail(`${t}, ${ev.year[i]}`, "Storm report · NOAA Storm Events");
  const url = layer.detail_url ? layer.detail_url.replace("{event_id}", ev.id[i]) : null;
  $("detail-meta").innerHTML = kv([
    ["Magnitude", mag === null ? "–" : `<span class="big">${mag}</span> <small>${esc(unit || "")}${t === "Hail" ? ` (${(mag * 25.4).toFixed(0)} mm)` : t === "Thunderstorm Wind" ? ` (${(mag * 0.514444).toFixed(1)} m/s)` : ""}</small>`],
    ["Event", url ? `<a href="${url}" target="_blank" rel="noopener">${ev.id[i]} at NCEI</a>` : ev.id[i]],
    ["Begins", ev.begin[i] ? `${fmtT(minToMs(ev.begin[i]))} UTC` : "time not resolved"],
    ["Ends", ev.end[i] > ev.begin[i] ? `${fmtT(minToMs(ev.end[i]))} UTC (${ev.end[i] - ev.begin[i]} min)` : "same time (an instant report)"],
    ["Location", located ? `${latLon(ev.lat[i], ev.lon[i])} <small>first point</small>` : "county or forecast zone only (no point)"],
    ["Property damage", dmg === null ? "not given" : `$${dmg.toLocaleString("en-US", { maximumFractionDigits: 0 })} <small>year-of-event dollars</small>`],
    ["Source", esc(layer.source)],
  ], true);
  $("chart").innerHTML = ""; $("detail-table").innerHTML = ""; $("detail-params").innerHTML = "";
  $("detail-foot").textContent = "A storm report, not a measurement on a grid; the full record (narrative, end point, path) is in the event table.";
}
