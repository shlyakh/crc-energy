// Risk tab: ranked plant table, map with sized and coloured plants, and the selected plant's figures.
// One selection state drives the table row, the map (ring, outline, report circle, reports) and the detail column.
import * as maplibregl from "https://cdn.jsdelivr.net/npm/maplibre-gl@6.16.0/dist/maplibre-gl.mjs";
import { $, esc, css, rgb, classOf, classVar, fmtMeasure, fmtBreak, fmtInt, fmtMW, fmtUSD, fmtPct, circleRing } from "./util.js";

const { MapboxOverlay, ScatterplotLayer, GeoJsonLayer, PolygonLayer } = globalThis.deck;
const BASIS = ["as reported", "bias-corrected"];
const LABEL_FONT = ["Noto Sans Regular"];
const PAD = { top: 24, right: 24, bottom: 36, left: 110 };
const S = { data: null, detail: null, detailUrl: "", measure: null, basis: 0, sort: { key: "reports", dir: -1 }, filter: "", selected: null, hovered: null, map: null, overlay: null, tags: [], texas: null, onChange: () => {} };

const radiusPx = (mw) => 2.5 + 0.4 * Math.sqrt(mw);
const value = (p, basis = S.basis) => p[S.measure.fields[basis]];
const shown = (p, basis = S.basis) => (value(p, basis) === null || value(p, basis) === undefined ? null : value(p, basis) * S.measure.scale);
function colourVar(p) { const v = shown(p); return v === null ? "--nodata" : classVar(classOf(v, S.measure.breaks), S.measure.breaks.length); }
const byId = (id) => S.data.plants.find((p) => p.id === id);

globalThis.__risk = S; // read by tools/smoke-next.mjs

export function riskAddress() { return { plant: S.selected, measure: S.measure?.id, basis: S.basis || null }; }

export async function initRisk(dataUrl, address, onChange) {
  S.onChange = onChange; S.detailUrl = `${dataUrl}assets/plants_detail.json`;
  const [data, registry, texas] = await Promise.all([
    fetch(`${dataUrl}assets/plants.json`).then((r) => { if (!r.ok) throw new Error(`plants.json ${r.status}`); return r.json(); }),
    fetch("../layers.json").then((r) => r.json()),
    fetch(`${dataUrl}texas.geojson`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
  ]);
  S.data = data; S.texas = texas;
  S.measure = data.measures.find((m) => m.id === address.measure) || data.measures[0];
  S.basis = address.basis === "1" && S.measure.has_basis ? 1 : 0;
  S.sort.key = S.basis ? "corrected" : "reports";
  $("build").textContent = `data built ${data.built_at.slice(0, 10)}`;
  $("plant-count").textContent = data.totals.plants;

  $("measure").innerHTML = data.measures.map((m) => `<option value="${m.id}">${esc(m.label)} (${esc(m.unit)})</option>`).join("");
  $("measure").value = S.measure.id;
  $("measure").onchange = () => { S.measure = data.measures.find((m) => m.id === $("measure").value); if (!S.measure.has_basis) S.basis = 0; if (S.sort.key === "corrected" && !S.measure.has_basis) S.sort.key = "reports"; refresh(); };
  for (const b of $("basis").children) b.onclick = () => setBasis(Number(b.dataset.basis));
  $("plant-filter").oninput = (e) => { S.filter = e.target.value.trim().toLowerCase(); renderTable(); };
  for (const th of document.querySelectorAll("#plants thead th")) th.onclick = () => {
    const key = th.dataset.sort; S.sort = { key, dir: S.sort.key === key ? -S.sort.dir : key === "name" ? 1 : -1 }; renderTable();
  };
  $("reset-view").onclick = () => fitTexas(600);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && document.body.dataset.tab === "risk") select(null); });

  await initMap(registry.basemap);
  refresh();
  if (address.plant && byId(address.plant)) await select(address.plant, { fly: true, duration: 0 });
}

export function setBasis(basis) {
  if (!S.measure.has_basis) return;
  if (S.sort.key === (S.basis ? "corrected" : "reports")) S.sort.key = basis ? "corrected" : "reports";
  S.basis = basis; refresh();
}

function refresh() {
  for (const b of $("basis").children) { b.setAttribute("aria-checked", String(Number(b.dataset.basis) === S.basis)); b.disabled = !S.measure.has_basis; }
  renderTable(); renderLegend(); renderLayers(); renderDetail(); S.onChange();
  document.body.dataset.measure = S.measure.id; document.body.dataset.basis = String(S.basis);
}

// ---------- map ----------
function texasBounds() { let b = [-106.7, 25.8, -93.5, 36.6]; return [[b[0] - 0.4, b[1] - 0.4], [b[2] + 0.4, b[3] + 0.4]]; }
function fitTexas(duration = 0) { S.map.fitBounds(texasBounds(), { padding: PAD, duration }); }

function initMap(basemap) {
  const map = new maplibregl.Map({ container: "map", style: basemap.style, bounds: texasBounds(), fitBoundsOptions: { padding: PAD }, attributionControl: { compact: true, customAttribution: `${basemap.attribution} · plants: EIA-860/860M via PUDL, USPVDB · hail: NOAA Storm Events, MRMS` } });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 140, unit: "metric" }), "bottom-right");
  map.on("mousemove", (e) => { $("coords").textContent = `${e.lngLat.lat.toFixed(3)}° N  ${Math.abs(e.lngLat.lng).toFixed(3)}° W`; });
  map.on("mouseout", () => { $("coords").textContent = ""; });
  const overlay = new MapboxOverlay({
    interleaved: false, layers: [],
    onHover: (info) => hover(info), getCursor: ({ isHovering }) => (isHovering ? "pointer" : "grab"),
    onClick: (info) => { if (info.layer?.id === "plants" && info.object) select(info.object.id, { fly: true }); else if (!info.object) select(null); },
  });
  map.addControl(overlay);
  S.map = map; S.overlay = overlay;
  return new Promise((resolve) => map.on("load", () => { addLabels(); document.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show"); resolve(); }));
}

// Plant names as native map labels (collision-handled), shown from zoom 7 for large plants and from 9 for all.
function addLabels() {
  const features = S.data.plants.map((p) => ({ type: "Feature", geometry: { type: "Point", coordinates: [p.lon, p.lat] }, properties: { label: `${p.name}\n${fmtMW(p.mw)} MW`, mw: p.mw, off: 0.35 + radiusPx(p.mw) / 11 } }));
  try {
    S.map.addSource("plant-labels", { type: "geojson", data: { type: "FeatureCollection", features } });
    S.map.addLayer({ id: "plant-labels", type: "symbol", source: "plant-labels", minzoom: 7,
      filter: ["any", [">=", ["zoom"], 9], [">=", ["get", "mw"], 150]],
      layout: { "text-field": ["get", "label"], "text-font": LABEL_FONT, "text-size": 11, "text-anchor": "top", "text-offset": [0, 1.3], "text-line-height": 1.15, "symbol-sort-key": ["-", ["get", "mw"]] },
      paint: { "text-color": css("--ink"), "text-halo-color": "#ffffff", "text-halo-width": 1.6 } });
  } catch (e) { console.warn("plant labels not added:", e.message); }
}

function hover(info) {
  const box = $("hover"); const o = info.object;
  if (!o || !["plants", "sel-reports"].includes(info.layer?.id)) { box.classList.add("hidden"); if (S.hovered) { S.hovered = null; markRow(); } return; }
  if (info.layer.id === "plants") {
    const v = shown(o); const other = S.measure.has_basis ? shown(o, 1 - S.basis) : null;
    box.innerHTML = `<b>${esc(o.name)}</b> · ${fmtMW(o.mw)} MW · ${esc(o.county)} Co.<br>${esc(S.measure.label)}: <b>${fmtMeasure(S.measure, value(o))}</b> ${esc(S.measure.unit)}${S.measure.has_basis ? `<br><span>${BASIS[1 - S.basis]}: ${other === null ? "–" : fmtMeasure(S.measure, value(o, 1 - S.basis))}</span>` : ""}`;
    if (S.hovered !== o.id) { S.hovered = o.id; markRow(); }
  } else {
    box.innerHTML = `Hail report · <b>${o[2].toFixed(0)} mm</b> (${(o[2] / 25.4).toFixed(2)} in)<br><span>${o[1].toFixed(3)}° N ${Math.abs(o[0]).toFixed(3)}° W · ${S.data.periods.reports}</span>`;
  }
  box.style.left = `${info.x}px`; box.style.top = `${info.y}px`; box.classList.remove("hidden");
}

function renderLayers() {
  const ink = rgb(css("--ink")), surface = [255, 255, 255, 255]; const layers = [];
  if (S.texas) layers.push(new GeoJsonLayer({ id: "texas", data: S.texas, stroked: true, filled: false, getLineColor: rgb(css("--ink-2")), lineWidthUnits: "pixels", getLineWidth: 1 }));
  const sel = S.selected ? byId(S.selected) : null; const d = sel && S.detail ? S.detail[sel.id] : null;
  if (sel && d) {
    layers.push(new PolygonLayer({ id: "sel-circle", data: [circleRing(sel.lon, sel.lat, d.circle.radius_km)], getPolygon: (r) => r, filled: true, getFillColor: [11, 11, 11, 10], stroked: true, getLineColor: ink, lineWidthUnits: "pixels", getLineWidth: 1.25 }));
    layers.push(new ScatterplotLayer({ id: "sel-reports", data: d.reports, getPosition: (r) => [r[0], r[1]], radiusUnits: "pixels", getRadius: (r) => 2 + r[2] / 14, getFillColor: rgb(css("--report"), 200), stroked: true, getLineColor: surface, lineWidthUnits: "pixels", getLineWidth: 0.75, pickable: true }));
    if (d.outline.length) layers.push(new PolygonLayer({ id: "sel-outline", data: d.outline, getPolygon: (r) => r, filled: true, getFillColor: rgb(css("--c2"), 70), stroked: true, getLineColor: ink, lineWidthUnits: "pixels", getLineWidth: 1.25 }));
  }
  // largest first so small plants stay on top and clickable
  const plants = [...S.data.plants].sort((a, b) => b.mw - a.mw);
  layers.push(new ScatterplotLayer({ id: "plants", data: plants, getPosition: (p) => [p.lon, p.lat], radiusUnits: "pixels", getRadius: (p) => radiusPx(p.mw),
    getFillColor: (p) => rgb(css(colourVar(p)), sel && sel.id !== p.id ? 150 : 235), stroked: true, getLineColor: surface, lineWidthUnits: "pixels", getLineWidth: 1, pickable: true,
    updateTriggers: { getFillColor: [S.measure.id, S.basis, S.selected] } }));
  if (sel) layers.push(new ScatterplotLayer({ id: "sel-ring", data: [sel], getPosition: (p) => [p.lon, p.lat], radiusUnits: "pixels", getRadius: (p) => radiusPx(p.mw) + 4, filled: false, stroked: true, getLineColor: ink, lineWidthUnits: "pixels", getLineWidth: 2.5 }));
  S.overlay.setProps({ layers });

  for (const t of S.tags) t.remove(); S.tags = [];
  if (sel) {
    S.tags.push(tag([sel.lon, sel.lat], `${sel.name} · ${fmtMW(sel.mw)} MW`, "", radiusPx(sel.mw)));
    if (d) { const north = circleRing(sel.lon, sel.lat, d.circle.radius_km, 4)[0]; S.tags.push(tag(north, `report circle r = ${d.circle.radius_km.toFixed(1)} km · ${d.circle.reports} reports ${S.data.periods.reports}`, "light", 0)); }
  }
}
function tag(lngLat, text, cls, lift) {
  const el = document.createElement("div"); el.className = `tag ${cls}`; el.textContent = text;
  return new maplibregl.Marker({ element: el, anchor: "bottom", offset: [0, -(lift + 7)] }).setLngLat(lngLat).addTo(S.map);
}

// ---------- legend (on the map) ----------
function renderLegend() {
  const m = S.measure, n = m.breaks.length; const counts = new Array(n + 1).fill(0); let none = 0;
  for (const p of S.data.plants) { const v = shown(p); if (v === null) none++; else counts[classOf(v, m.breaks)]++; }
  const range = (i) => (i === 0 ? `< ${fmtBreak(m.breaks[0])}` : i === n ? `≥ ${fmtBreak(m.breaks[n - 1])}` : `${fmtBreak(m.breaks[i - 1])} – ${fmtBreak(m.breaks[i])}`);
  const rows = counts.map((c, i) => `<div class="row"><span class="dot" style="background:var(${classVar(i, n)})"></span><span class="num">${range(i)}</span><span class="n num">${c}</span></div>`).join("");
  const sizes = [50, 200, 600].map((mw) => `<span><i style="width:${2 * radiusPx(mw)}px;height:${2 * radiusPx(mw)}px"></i>${mw}</span>`).join("");
  const sel = S.selected && S.detail ? `<div class="sep"></div><div class="row"><span class="ring"></span>Report circle of the selected plant</div><div class="row"><span class="dot" style="background:var(--report)"></span>Hail report, sized by hail size</div><div class="row"><span class="dot" style="background:var(--c2);opacity:.5;border-radius:1px"></span>Array outline (USPVDB)</div>` : "";
  const period = m.id === "radar_days" ? `Radar (MRMS) ${S.data.periods.radar}.` : `Storm reports ${S.data.periods.reports}, ${BASIS[S.basis]}.`;
  $("legend").innerHTML = `<h3>${esc(m.label)}</h3><div class="unit">${esc(m.unit)} · plants per class at right</div>${rows}${none ? `<div class="row"><span class="dot" style="background:var(--nodata)"></span>no value<span class="n num">${none}</span></div>` : ""}
    <div class="sep"></div><div class="label">Capacity, MW AC</div><div class="sizes">${sizes}</div>${sel}
    <div class="foot">${period}${m.id.startsWith("loss") ? " First-approximation damage curve with placeholder inputs." : ""}</div>`;
  document.body.dataset.legend = `${m.unit} | ${counts.map((_, i) => range(i)).join(" | ")}`;
}

// ---------- table ----------
function renderTable() {
  const m = S.measure; const active = S.basis ? "corrected" : "reports";
  $("th-reports").textContent = m.has_basis ? "Reports" : "Radar"; $("th-corrected").classList.toggle("hidden", !m.has_basis);
  for (const th of document.querySelectorAll("#plants thead th")) { th.classList.toggle("active", th.dataset.sort === active); th.classList.toggle("offcol", m.has_basis && ["reports", "corrected"].includes(th.dataset.sort) && th.dataset.sort !== active); if (th.dataset.sort === S.sort.key) th.setAttribute("aria-sort", S.sort.dir > 0 ? "ascending" : "descending"); else th.removeAttribute("aria-sort"); }
  const key = { name: (p) => p.name.toLowerCase(), mw: (p) => p.mw, reports: (p) => value(p, 0) ?? -Infinity, corrected: (p) => value(p, 1) ?? -Infinity }[S.sort.key];
  const rows = S.data.plants.filter((p) => !S.filter || `${p.name} ${p.county}`.toLowerCase().includes(S.filter)).sort((a, b) => (key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0) * S.sort.dir);
  $("plants").tBodies[0].innerHTML = rows.map((p) => `<tr data-id="${p.id}"${p.id === S.selected ? ' class="sel"' : ""}><td class="l" title="${esc(p.name)}"><span class="sw" style="background:var(${colourVar(p)})"></span>${esc(p.name)}<small>${esc(p.county)} · ${p.year ?? "–"} · ${esc(p.mount)}</small></td><td>${fmtMW(p.mw)}</td><td class="${S.basis === 0 || !m.has_basis ? "" : "off offcol"}">${fmtMeasure(m, value(p, 0))}</td>${m.has_basis ? `<td class="${S.basis === 1 ? "" : "off offcol"}">${fmtMeasure(m, value(p, 1))}${p.factor_warning ? ' <span class="warn" title="The bias correction multiplies this plant\'s hail rate by ' + p.factor + ", above " + S.data.factor_warning_above + '. It rests on the least certain part of the reporting model.">!</span>' : ""}</td>` : ""}</tr>`).join("");
  for (const tr of $("plants").tBodies[0].rows) { tr.onclick = () => select(tr.dataset.id, { fly: true }); tr.onmouseenter = () => { S.hovered = tr.dataset.id; }; }
  const stat = (basis) => { const vals = rows.map((p) => value(p, basis)).filter((v) => v !== null && v !== undefined); if (!vals.length) return "–"; if (m.id === "loss_usd") return fmtMeasure(m, vals.reduce((a, b) => a + b, 0)); vals.sort((a, b) => a - b); return fmtMeasure(m, vals[Math.floor(vals.length / 2)]); };
  const mw = rows.reduce((a, p) => a + p.mw, 0);
  $("plants").tFoot.innerHTML = `<tr><th class="l">${m.id === "loss_usd" ? "Total" : "Median"} · ${rows.length} plants</th><th>${fmtInt(mw)}</th><th class="${S.basis === 0 || !m.has_basis ? "" : "offcol"}">${stat(0)}</th>${m.has_basis ? `<th class="${S.basis === 1 ? "" : "offcol"}">${stat(1)}</th>` : ""}</tr>`;
  const t = S.data.totals;
  $("table-note").innerHTML = `${esc(m.label)}, ${esc(m.unit)}. All ${t.plants} plants: value ${fmtUSD(t.value)}; expected hail loss <b>${fmtUSD(t.loss_usd)}</b> a year from reports as they are, <b>${fmtUSD(t.loss_usd_c)}</b> bias-corrected.${m.has_basis ? ' <span class="warn">!</span> correction factor above ' + S.data.factor_warning_above + "." : ""}`;
  document.body.dataset.rows = String(rows.length); document.body.dataset.first = rows[0]?.id || "";
}
function markRow() { for (const tr of $("plants").tBodies[0].rows) tr.style.background = tr.dataset.id === S.hovered && tr.dataset.id !== S.selected ? "var(--hover)" : ""; }

// ---------- selection and detail ----------
export async function select(id, { fly = false, duration = 700 } = {}) {
  S.selected = id && byId(id) ? id : null;
  if (S.selected && !S.detail) {
    try { S.detail = await fetch(S.detailUrl).then((r) => { if (!r.ok) throw new Error(`plants_detail.json ${r.status}`); return r.json(); }); }
    catch (e) { $("map-msg").textContent = `Report circles could not be loaded: ${e.message}`; $("map-msg").classList.remove("hidden"); }
  }
  for (const tr of $("plants").tBodies[0].rows) tr.classList.toggle("sel", tr.dataset.id === S.selected);
  renderLegend(); renderLayers(); renderDetail(); S.onChange();
  document.body.dataset.selected = S.selected || "";
  const sel = S.selected ? byId(S.selected) : null;
  if (sel) {
    document.querySelector(`#plants tr[data-id="${sel.id}"]`)?.scrollIntoView({ block: "center" });
    if (fly) {
      const r = S.detail?.[sel.id]?.circle.radius_km ?? sel.radius_km; const ring = circleRing(sel.lon, sel.lat, r, 4);
      S.map.fitBounds([[ring[3][0], ring[2][1]], [ring[1][0], ring[0][1]]], { padding: { top: 60, right: 40, bottom: 40, left: 270 }, duration, maxZoom: 11 });
    }
  }
}

function renderDetail() {
  const p = S.selected ? byId(S.selected) : null;
  $("detail-empty").classList.toggle("hidden", !!p); $("detail").classList.toggle("hidden", !p);
  if (!p) return;
  const d = S.detail?.[p.id]; const rule = S.data.rule, def = S.data.curve_defaults || {};
  const on = (b) => (S.basis === b ? ' class="sub on"' : ' class="sub"');
  const glass = p.glass === "glass_glass_2.0" ? "2.0 mm glass-glass" : "3.2 mm glass, backsheet";
  const ph = '<span class="pill ph">placeholder</span>', inf = '<span class="pill">rule</span>';
  $("detail").innerHTML = `
    <div class="d-head"><button class="d-close" title="Clear selection (Esc)" aria-label="Clear selection">×</button>
      <h2>${esc(p.name)}</h2><p>${esc(p.county)} County · ${p.lat.toFixed(3)}° N ${Math.abs(p.lon).toFixed(3)}° W</p>
      <p>${fmtMW(p.mw)} MW AC · online ${p.year ?? "–"} · ${esc(p.mount)} · ${glass}</p></div>
    <table class="kv">
      <tr><th>Replacement value</th><td class="big">${fmtUSD(p.value)}</td></tr>
      <tr><th>Expected hail loss</th><td class="mute">per year</td></tr>
      <tr${on(0)}><th>as reported</th><td>${fmtUSD(p.loss_usd)}<small>${fmtPct(p.loss_ratio)}</small></td></tr>
      <tr${on(1)}><th>bias-corrected${p.factor_warning ? ' <span class="warn" title="Correction factor above ' + S.data.factor_warning_above + '">!</span>' : ""}</th><td>${fmtUSD(p.loss_usd_c)}<small>${fmtPct(p.loss_ratio_c)}</small></td></tr>
      <tr class="sub"><th>correction factor</th><td>${p.factor === null ? "–" : `× ${p.factor.toFixed(2)}`}</td></tr>
      <tr><th>Chance of hail ≥ 2 in</th><td class="mute">per year</td></tr>
      <tr${on(0)}><th>as reported</th><td>${fmtPct(p.p2in, 2)}</td></tr>
      <tr${on(1)}><th>bias-corrected</th><td>${fmtPct(p.p2in_c, 2)}</td></tr>
      <tr><th>Radar hail size</th><td class="mute">MRMS ${esc(S.data.periods.radar)}</td></tr>
      <tr class="sub"><th>hail days ≥ 30 mm (25 km mean)</th><td>${p.radar_days === null ? "–" : `${p.radar_days.toFixed(2)} / yr`}</td></tr>
      <tr class="sub"><th>largest over the plant</th><td>${p.radar_max_mm ? `${p.radar_max_mm} mm<small>${esc(p.radar_max_day)}</small>` : "none ≥ 30 mm"}</td></tr>
      <tr><th>Report circle</th><td class="mute">${esc(S.data.periods.reports)}</td></tr>
      <tr class="sub"><th>radius</th><td>${(d?.circle.radius_km ?? p.radius_km).toFixed(1)} km</td></tr>
      <tr class="sub"><th>hail reports inside</th><td>${p.reports}</td></tr>
      <tr class="sub"><th>share inside reporting region</th><td>${d ? fmtPct(d.circle.share_inside_region, 0) : "–"}</td></tr>
    </table>
    <div class="d-sec"><span class="label">Assumptions behind the loss</span>
      <ul>
        <li>Module glass: ${glass}, by year online ${inf}</li>
        <li>${esc(d?.stow_basis ?? p.mount)}${p.mount === "tracker" ? ph : ""}</li>
        <li>Modules are ${def.module_cost_share ?? "–"} of plant value ${ph}</li>
        <li>Each report stands for ${rule.footprint_km2} km² of hail ${ph}</li>
        <li>Circle grown to ${rule.n_target} reports, ${rule.min_radius_km}–${rule.max_radius_km} km ${inf}</li>
        ${(d?.notes ?? []).map((n) => `<li>${esc(n)}</li>`).join("")}
      </ul>
      <p>Value: benchmark cost per kW AC × capacity. Charts of hail sizes and the damage curve come with the next stop.</p></div>`;
  $("detail").querySelector(".d-close").onclick = () => select(null);
}
