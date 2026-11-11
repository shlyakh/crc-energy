// Hail evidence and CRC data tabs: one pane, one map, the sources of one origin at a time.
// The views under ./views/ are the source views of site/app.js moved into the new shell: a compact source picker with the
// selected source's controls beneath it, the map with its legend, scale bar, coordinates and hover readout, and the detail column.
import * as maplibregl from "https://cdn.jsdelivr.net/npm/maplibre-gl@6.16.0/dist/maplibre-gl.mjs";
// The view modules are loaded in three small waves, not seven files at once: python's http.server (`just serve`, the smoke
// test) queues five waiting connections and resets the rest, which made this tab fail to open now and then.
const { $, state, api, esc, MapboxOverlay, GeoJsonLayer, layerById, sourceById, groupOf, layersOfSource, horizonsOf, cellSource, compareLayerOf, fetchJSON, unitOf, rgbCss, renderLegend, closeDetail } = await import("./views/core.js");
const [cells, tracks, events] = await Promise.all([import("./views/cells.js"), import("./views/tracks.js"), import("./views/events.js")]);
const [stations, compare, time] = await Promise.all([import("./views/stations.js"), import("./views/compare.js"), import("./views/time.js")]);
const { loadFile, buildCellControls, cellsLayer, cellsLegend, cellHover, showDetail } = cells;
const { loadTracks, tracksMatch, buildTracksControls, tracksLayers, tracksLegend, trackHover } = tracks;
const { loadEvents, buildEventsControls, eventsLayer, eventsLegend, eventHover } = events;
const { loadGeo, geoLayer, geoLegend, geoHover, buildStationsList } = stations;
const { loadCompare, compareLayer, compareLegend, compareHover, buildCompareControls, placeSwipe, wireCompare, setCompare } = compare;
const { setupTime, stopPlay, drawFrame, buildTimebar, drawTimeline, seek } = time;

const HIDDEN_SOURCES = new Set(["solar_plants"]); // the Risk tab shows the plants
let notify = () => {};

// ---------- the pane ----------
const PANE = `
<section class="col src-left" aria-label="Sources">
  <div class="col-head"><span class="label" id="src-group"></span><span id="src-origin" class="origin"></span></div>
  <div class="src-scroll">
    <div id="sources" class="picker" role="listbox" aria-label="Source"></div>
    <div id="source-panel">
      <div class="sec-head"><span class="label">Controls</span><span id="status" class="mute num"></span></div>

      <div id="ctl-ibtracs" class="ctl hidden">
        <div class="frow c4">
          <label class="f"><span>From season</span><input type="number" id="tracks-from"></label>
          <label class="f"><span>To season</span><input type="number" id="tracks-to"></label>
          <label class="f"><span>Min wind, kt</span><input type="number" id="tracks-min-wind" min="0" step="5" value="0"></label>
        </div>
        <div class="frow">
          <label class="f"><span>Name contains</span><input type="search" id="tracks-name" placeholder="e.g. Harvey"></label>
          <label class="f"><span>Colour by</span><select id="tracks-color"><option value="wind">wind along the track</option><option value="category">Saffir-Simpson category</option></select></label>
        </div>
        <label class="check" title="For the selected storm, or for all shown storms when 8 or fewer"><input type="checkbox" id="tracks-extent" checked> Show wind extent (34, 50, 64 kt radii)</label>
        <div id="tracks-status" class="mute small"></div>
        <ol id="tracks-list" class="list"></ol>
      </div>

      <div id="ctl-storm_events" class="ctl hidden">
        <label class="check"><input type="checkbox" id="win-on"> Explore a date window with the timeline</label>
        <div class="frow" id="years-row">
          <label class="f"><span>From year</span><input type="number" id="events-from" min="1950" max="2030"></label>
          <label class="f"><span>To year</span><input type="number" id="events-to" min="1950" max="2030"></label>
        </div>
        <div class="frow hidden" id="win-row">
          <label class="f"><span>Start (UTC)</span><input type="date" id="win-start" value="2024-03-14"></label>
          <label class="f"><span>Days</span><input type="number" id="win-days" min="1" max="14" value="3"></label>
        </div>
        <div class="sub-head"><span class="label">Report types</span><span class="mute small">located reports, all years</span></div>
        <div id="events-types"></div>
        <div id="events-status" class="mute small"></div>
      </div>

      <div id="ctl-stations" class="ctl hidden">
        <div id="stations-status" class="mute small"></div>
        <ol id="stations-list" class="list tall"></ol>
      </div>

      <div id="ctl-compare" class="ctl hidden">
        <div class="seg" id="cmp-mode" role="radiogroup" aria-label="View">
          <button data-mode="single" role="radio">One source</button><button data-mode="swipe" role="radio">Swipe two</button><button data-mode="ratio" role="radio">Ratio</button>
        </div>
        <div class="seg hidden" id="cmp-preset" role="radiogroup" aria-label="Ratio of">
          <button data-b="reports" role="radio">Radar ÷ reports</button><button data-b="reports_corrected" role="radio">Radar ÷ bias-corrected</button>
        </div>
        <label class="f" id="cmp-a-label"><span>Source</span><select id="cmp-a"></select></label>
        <label class="f" id="cmp-b-label"><span>Against</span><select id="cmp-b"></select></label>
        <label class="check" id="cmp-own-label"><input type="checkbox" id="cmp-own"> Scale each source to its own range</label>
        <div id="cmp-summary"></div>
        <div id="cmp-years"></div>
      </div>

      <div id="ctl-cells" class="ctl hidden">
        <label class="f" id="hazard-label"><span>Hazard</span><select id="hazard"></select></label>
        <div class="frow">
          <label class="f"><span>Horizon</span><select id="horizon"></select></label>
          <label class="f"><span>Return period</span><select id="rp"></select></label>
        </div>
        <label class="check"><input type="checkbox" id="lock"> Keep this colour scale when switching</label>
      </div>
    </div>

    <details id="also" class="sec">
      <summary><span class="label">Also show</span><span id="also-count" class="mute small"></span></summary>
      <div id="overlays"></div>
    </details>

    <div class="sec caveats">
      <div class="sec-head"><span class="label">Read this first</span></div>
      <p id="source-blurb"></p>
      <ul id="caveats"></ul>
    </div>
  </div>
</section>

<section class="col src-mid">
  <div class="toolbar">
    <span class="label">Source</span><b id="src-title"></b><span id="src-sub" class="mute"></span>
    <button id="src-reset" class="btn">Texas</button>
  </div>
  <div id="src-map-wrap">
    <div id="map"></div>
    <div id="swipe" class="hidden" title="Drag to move the split"><span id="swipe-a"></span><span id="swipe-b"></span></div>
    <div id="src-hover" class="hover hidden"></div>
    <div id="src-legend" class="legend"></div>
    <div id="src-coords" class="coords num"></div>
    <div id="src-msg" class="map-msg hidden"></div>
  </div>
  <div id="timebar" class="hidden">
    <div class="timectl">
      <span class="label" id="time-title">Time</span>
      <button id="time-play" title="Play or pause">▶</button>
      <select id="time-speed" title="Playback speed"><option value="1">1 h/s</option><option value="3">3 h/s</option><option value="6" selected>6 h/s</option><option value="12">12 h/s</option><option value="24">24 h/s</option></select>
      <input type="range" id="time-slider" min="0" max="1000" value="0" aria-label="Time">
      <span id="time-clock" class="clock num"></span>
    </div>
    <div id="timeline"></div>
    <div id="timeline-note" class="mute small"></div>
    <div id="timeline-tip" class="tip hidden"></div>
  </div>
</section>

<section class="col col-detail" aria-label="Selection">
  <div id="src-empty" class="empty"><span class="label">Nothing selected</span><p id="src-empty-text"></p></div>
  <div id="detail" class="hidden">
    <div class="d-head"><h2 id="detail-title"></h2><p id="detail-sub"></p><button id="detail-close" class="d-close" title="Close (Esc)" aria-label="Close">×</button></div>
    <table id="detail-meta" class="kv"></table>
    <div id="chart"></div>
    <table id="detail-table" class="tbl"></table>
    <table id="detail-params" class="kv"></table>
    <p id="detail-foot" class="mute small"></p>
  </div>
</section>`;

const EMPTY_HINT = {
  tracks: "Pick a storm in the list or on the map. Its track is emphasised, its wind extent is shaded, and the time bar under the map plays it with the storm reports of those days.",
  "points-binary": "Click a report on the map, or switch on the date window and click a mark on the timeline. The report is ringed on the map.",
  "h3-cells": "Click a cell for its curve: the values at every return period, as crc-sdk evaluated them. The cell is outlined on the map.",
  "h3-compare": "Click a cell to see hail days per year from all four sources side by side. The cell is outlined on the map.",
  points: "Pick a station in the list or on the map for its published levels or fitted curve. The station is ringed on the map.",
};

// ---------- source picker and per-source controls ----------
const sourcesOf = (origin) => state.registry.sources.filter((s) => s.origin === origin && !HIDDEN_SOURCES.has(s.id));
function licenceShort(text) {
  const cc = text.match(/^CC0[-\d.]*|^CC BY(?:-[A-Z]+)* [\d.]+/); if (cc) return cc[0];
  return /U\.S\. government/.test(text) ? "US Gov work" : text.split(/[;(]/)[0].trim();
}
function buildSourceList() {
  const g = state.registry.groups.find((x) => x.id === state.origin);
  $("src-group").textContent = g.title; $("src-group").title = g.blurb;
  $("src-origin").textContent = g.badge; $("src-origin").style.setProperty("--g", g.color);
  const box = $("sources"); box.innerHTML = "";
  for (const s of sourcesOf(state.origin)) {
    const b = document.createElement("button"); b.className = "src-row"; b.dataset.id = s.id; b.setAttribute("role", "option"); b.setAttribute("aria-selected", String(s.id === state.source));
    b.title = `${s.short} Licence: ${s.licence}`;
    b.innerHTML = `<span class="t">${esc(s.title)}</span><span class="m">${esc(s.status)}<span class="lic"> · ${esc(licenceShort(s.licence))}</span></span>`;
    b.onclick = () => selectSource(s.id);
    box.append(b);
  }
}
function clearSelection(redraw = true) {
  const hadStorm = state.storm !== null;
  state.selected = null; state.pick = null; state.storm = null; closeDetail();
  if (!redraw) return;
  if (hadStorm) api.render(); else { if (!$("ctl-stations").classList.contains("hidden")) buildStationsList(); drawFrame(); }
}
function selectSource(id, force = false) {
  if (state.source === id && !force) return Promise.resolve();
  if (!sourceById(id) || HIDDEN_SOURCES.has(id)) return Promise.resolve();
  state.source = id; state.byOrigin[sourceById(id).origin] = id; clearSelection(false);
  const cells = layersOfSource(id).filter((l) => l.kind === "h3-cells");
  if (cells.length) {
    state.hazard = id === "crc_open" ? state.registry.defaults.crc_hazard : cells[0].id;
    const hs = horizonsOf(layerById(state.hazard)); if (!hs.includes(state.horizon)) state.horizon = hs.includes(state.registry.defaults.horizon) ? state.registry.defaults.horizon : hs[0];
    state.domain = null;
  }
  buildSourceList(); notify();
  return render();
}
const kindOf = (id) => (id === "ibtracs" ? "tracks" : id === "storm_events" ? "points-binary" : compareLayerOf(id) ? "h3-compare" : cellSource(id) ? "h3-cells" : "points");
function buildSourcePanel() {
  const s = sourceById(state.source); const kind = kindOf(state.source);
  $("src-title").textContent = s.title; $("src-sub").textContent = s.provider;
  $("source-blurb").innerHTML = `<b>${esc(s.title)}</b> · ${esc(s.provider)}. ${esc(s.returns)} <span>Coverage: ${esc(s.coverage)}. Licence: ${esc(s.licence)}.</span>`;
  $("src-empty-text").textContent = EMPTY_HINT[kind];
  const show = { tracks: "ctl-ibtracs", "points-binary": "ctl-storm_events", "h3-compare": "ctl-compare", "h3-cells": "ctl-cells", points: "ctl-stations" }[kind];
  for (const el of document.querySelectorAll("#source-panel .ctl")) el.classList.toggle("hidden", el.id !== show);
  if (kind === "tracks") buildTracksControls();
  else if (kind === "points-binary") buildEventsControls();
  else if (kind === "h3-compare") buildCompareControls();
  else if (kind === "h3-cells") buildCellControls();
  else buildStationsList();
}
function buildOverlays() {
  const box = $("overlays"); box.innerHTML = ""; let on = 0;
  const own = new Set(layersOfSource(state.source).map((l) => l.id));
  for (const l of state.registry.layers) {
    if (HIDDEN_SOURCES.has(l.source_id)) continue;
    if ((l.kind === "h3-cells" || l.kind === "h3-compare") && !own.has(l.id)) continue; // cells only through their source
    if (l.kind === "h3-cells" && l.id !== state.hazard) continue;
    const lab = document.createElement("label");
    const cb = document.createElement("input"); cb.type = "checkbox";
    const forced = own.has(l.id);
    cb.checked = forced || state.overlays.get(l.id) === true; cb.disabled = forced; cb.dataset.layer = l.id;
    if (cb.checked && !forced && l.id !== "texas") on++;
    cb.onchange = () => { state.overlays.set(l.id, cb.checked); render(); };
    lab.append(cb, document.createTextNode(l.title), Object.assign(document.createElement("span"), { className: "mute", textContent: forced ? "this source" : (sourceById(l.source_id) || { title: "" }).title }));
    box.append(lab);
  }
  for (const p of state.registry.planned) {
    const lab = document.createElement("label"); const cb = document.createElement("input"); cb.type = "checkbox"; cb.disabled = true;
    lab.append(cb, document.createTextNode(p.title), Object.assign(document.createElement("span"), { className: "mute", textContent: p.status }));
    box.append(lab);
  }
  $("also-count").textContent = on ? `${on} other layer${on > 1 ? "s" : ""} on` : "layers of other sources, Texas boundary";
}
function buildCaveats(payload) {
  const { catalog, manifest } = state; const s = sourceById(state.source);
  const g = groupOf(s);
  const items = [`<b>${esc(g.title)}.</b> ${esc(g.blurb)}`, ...(s.caveats || []).map((t) => `<b>${esc(s.title)}:</b> ${esc(t)}`)];
  for (const l of layersOfSource(state.source)) if (l.caveat) items.push(`<b>${esc(l.title)}:</b> ${esc(l.caveat)}`);
  if (payload && cellSource(state.source)) {
    const layer = layerById(state.hazard); const res = payload.h3_resolution;
    const km2 = res === 5 ? "about 253 km²" : res === 7 ? "about 5.2 km²" : res === 4 ? "about 1,770 km²" : `resolution ${res}`;
    items.push(`<b>Cells:</b> H3 resolution ${res}, ${km2} each; ${payload.cells.length.toLocaleString("en-US")} cells with a curve; cells without one are not drawn.`);
    items.push(`<b>Curve:</b> ${esc(payload.value_semantics)}; probability semantics ${esc(payload.probability_semantics || "unspecified")}; return periods read on the ${payload.tail} tail (1 in T years = non-exceedance ${payload.tail === "upper" ? "1 − 1/T" : "1/T"}). Displayed unit ${esc(unitOf(layer, payload))}${layer.display && layer.display.offset ? ` (source ${esc(payload.unit)})` : ""}.`);
    if (state.source === "crc_open") {
      items.push(`<b>Release:</b> CRC Open <code>${esc(catalog.release)}</code>, ${esc(catalog.licence)}. Attribution: ${esc(catalog.attribution)}.`);
      const note = catalog.hazards[state.hazard] && catalog.hazards[state.hazard].notes; if (note) items.push(`<b>Release note for ${esc(state.hazard)}:</b> ${esc(note)}`);
      const build = manifest.hazards.find((h) => h.hazard === state.hazard);
      if (build && build.outside_tabulated_support) items.push(`<b>Tabulated curves:</b> ${build.kinds.tabulated || 0} cells per horizon carry only a few knots near the rare end; return periods outside those knots show as no value.`);
      if (build) for (const w of build.warnings) items.push(`<b>crc-sdk warning:</b> ${esc(w)}`);
    }
  }
  if (state.source === "storm_events" && state.events) items.push(...state.events.index.known_biases.slice(0, 4).map((t) => `<b>Reports:</b> ${esc(t)}`));
  if (state.source === "ibtracs" && state.tracks) items.push(`<b>Wind extent:</b> shaded bands are US agency estimates of how far 34, 50 and 64 kt winds reached in each quadrant (${state.tracks.storms.filter((x) => x.extent_points.r34).length} of ${state.tracks.storms.length} storms, from 2001), joined along the track; they are not observed damage footprints, and storms without them show a line only.`);
  if (state.time) items.push(`<b>Timeline:</b> storm reports are placed at their begin time (NCEI local standard time converted to UTC); most hail and wind reports are instants. Reports appear when the clock passes them and stay.`);
  if (state.source === "ibtracs" && state.tracks) items.push(`<b>Winds:</b> ${esc(state.tracks.wind_note)}. Snapshot SHA-256 ${esc((state.tracks.sha256 || "").slice(0, 12))}…, retrieved ${esc((state.tracks.retrieved_at || "").slice(0, 10))}. Cite: ${esc(state.tracks.citation)}.`);
  for (const l of state.registry.layers) {
    if (state.overlays.get(l.id) === true && l.source_id && l.source_id !== state.source && !HIDDEN_SOURCES.has(l.source_id)) {
      const os = sourceById(l.source_id); items.push(`<b>Also shown, ${esc(os.title)}:</b> ${esc((os.caveats && os.caveats[0]) || l.caveat || os.short)} Licence: ${esc(os.licence)}.`);
    }
  }
  items.push(`<b>Built</b> ${esc(manifest.built_at)} with crc-sdk ${esc(manifest.versions["crc-sdk"])}, crc-framework ${esc(manifest.versions["crc-framework"])}. Basemap ${esc(state.registry.basemap.attribution)}.`);
  $("caveats").innerHTML = items.map((t) => `<li>${t}</li>`).join("");
}

// ---------- render ----------
let rendering = 0;
function fail(what, e) { const m = $("src-msg"); m.textContent = `Could not load ${what}: ${e.message || e}`; m.classList.remove("hidden"); document.body.dataset.sourcesError = String(e.message || e); }
async function render() {
  const started = performance.now(); const token = ++rendering; document.body.dataset.sourcesReady = "";
  const src = state.source; const layers = []; let payload = null; let fetched = started; let count = "";
  const legend = []; const also = [];
  $("src-msg").classList.add("hidden"); delete document.body.dataset.sourcesError; $("src-hover").classList.add("hidden");
  try {
    if (cellSource(src)) {
      payload = await loadFile(state.hazard, state.horizon); fetched = performance.now();
      if (token !== rendering) return;
      const l = layerById(state.hazard);
      layers.push(cellsLayer(l, payload)); count = `${payload.cells.length.toLocaleString("en-US")} cells`;
      legend.push(() => cellsLegend(l, payload));
    }
    const wanted = new Set(layersOfSource(src).map((l) => l.id));
    for (const [id, on] of state.overlays) if (on && layerById(id) && layerById(id).kind !== "h3-cells" && layerById(id).kind !== "h3-compare" && !HIDDEN_SOURCES.has(layerById(id).source_id)) wanted.add(id);
    for (const l of state.registry.layers) {
      if (!wanted.has(l.id) || l.kind === "h3-cells" || l.kind === "geojson") continue;
      const own = l.source_id === src;
      if (l.kind === "tracks") {
        await loadTracks(l); if (token !== rendering) return; layers.push(...tracksLayers(l));
        if (own) { count = `${tracksMatch().length} storms`; legend.push(() => tracksLegend(l)); } else also.push({ color: rgbCss(l.style.category_colors["1"]), shape: "line", label: "Tropical cyclone tracks" });
      } else if (l.kind === "points-binary") {
        await loadEvents(l); if (token !== rendering) return; if (!(own && state.win.on)) layers.push(eventsLayer(l));
        if (own) { count = `${state.events.index.events.toLocaleString("en-US")} located reports`; legend.push(() => eventsLegend(l)); } else also.push({ color: rgbCss(l.style.colors.Hail), label: "Storm reports (default types)" });
      } else if (l.kind === "h3-compare") {
        await loadCompare(l); if (token !== rendering) return; layers.push(compareLayer(l)); count = `${state.cmp.data.cells.length.toLocaleString("en-US")} cells, ${state.cmp.ids.length} sources`;
        legend.push(() => compareLegend(l));
      } else if (l.kind === "points" || l.kind === "lines") {
        const data = await loadGeo(l); if (token !== rendering) return; layers.push(geoLayer(l, data));
        if (own) { count = `${data.features.length} stations`; legend.push(() => geoLegend(l, data)); } else also.push({ color: rgbCss((l.style && l.style.fill) || [42, 120, 214]), label: l.title, n: data.features.length });
      }
      if (fetched === started) fetched = performance.now();
    }
  } catch (e) { fail(sourceById(src).title, e); return; }
  if (state.overlays.get("texas") !== false) layers.push(new GeoJsonLayer({ id: "texas", data: state.texas, stroked: true, filled: false, getLineColor: layerById("texas").style.line, lineWidthMinPixels: layerById("texas").style.width, pickable: false }));
  try { await setupTime(); } catch (e) { fail("the timeline", e); }
  if (token !== rendering) return;
  state.baseLayers = layers; drawFrame();
  buildSourcePanel(); buildOverlays(); buildCaveats(payload); buildTimebar(); placeSwipe();
  renderLegend([...legend.map((f) => f()), also.length ? { title: "Also shown", rows: also } : null]);
  if (state.selected && (state.selected.hazard !== state.hazard || state.selected.horizon !== state.horizon)) clearSelection();
  else if (state.selected && cellSource(src)) showDetail(state.selected.index);
  await new Promise((done) => requestAnimationFrame(() => {
    if (token === rendering) {
      const total = performance.now() - started;
      $("status").textContent = `${count} · ${total.toFixed(0)} ms`; $("status").title = `${(fetched - started).toFixed(0)} ms load, ${total.toFixed(0)} ms to view`;
      document.body.dataset.sourcesReady = "1"; document.body.dataset.ms = total.toFixed(0); document.body.dataset.source = src;
    }
    done();
  }));
}
api.render = render; api.clearSelection = clearSelection;

// ---------- map ----------
function texasBounds() { const b = state.manifest.texas.bounds; return [[b[0] - 1.5, b[1] - 1], [b[2] + 1.5, b[3] + 0.5]]; }
function hoverHtml(info) {
  if (!info.picked || !info.layer) return null;
  const id = info.layer.id;
  if (id === "cells") return cellHover(info.index);
  if (id === "cmp") return compareHover(info.index);
  if (id === "tracks") return trackHover(info.object);
  if ((id === "events" || id === "window-events") && state.events) return eventHover(info.object);
  if (id.startsWith("geo:")) return geoHover(layerById(id.slice(4)), info.object);
  return null;
}
function hover(info) {
  const box = $("src-hover"); const html = hoverHtml(info);
  box.classList.toggle("hidden", !html); if (!html) return;
  box.innerHTML = html;
  // keep the box inside the map: flip to the left of the pointer near the right edge, above it near the bottom
  const wrap = $("src-map-wrap").getBoundingClientRect(); const w = box.offsetWidth, h = box.offsetHeight;
  box.style.left = `${info.x + 24 + w > wrap.width ? Math.max(0, info.x - w - 24) : info.x}px`; box.style.top = `${info.y + 24 + h > wrap.height ? Math.max(0, info.y - h - 24) : info.y}px`;
}
function initMap() {
  const map = new maplibregl.Map({
    container: "map", style: state.registry.basemap.style, bounds: texasBounds(), fitBoundsOptions: { padding: 20 },
    attributionControl: { compact: true, customAttribution: `${state.registry.basemap.attribution} · data sources credited per source (CRC Open ${state.catalog.licence})` },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 140, unit: "metric" }), "bottom-right");
  map.on("mousemove", (e) => { $("src-coords").textContent = `${Math.abs(e.lngLat.lat).toFixed(3)}° ${e.lngLat.lat < 0 ? "S" : "N"}  ${Math.abs(e.lngLat.lng).toFixed(3)}° ${e.lngLat.lng < 0 ? "W" : "E"}`; });
  map.on("mouseout", () => { $("src-coords").textContent = ""; $("src-hover").classList.add("hidden"); });
  const overlay = new MapboxOverlay({ interleaved: false, layers: [], onHover: hover, getCursor: ({ isHovering, isDragging }) => (isDragging ? "grabbing" : isHovering ? "pointer" : "grab") });
  map.addControl(overlay);
  state.map = map; state.overlay = overlay;
  // the compact attribution opens expanded and would cover the legend and the scale bar: start it collapsed (the "i" opens it)
  const collapse = () => { const el = $("map").querySelector(".maplibregl-ctrl-attrib"); if (el) { el.classList.remove("maplibregl-compact-show"); el.removeAttribute("open"); } };
  return new Promise((resolve) => map.on("load", () => { collapse(); resolve(); }));
}

// ---------- the three exports main.js uses ----------
export async function initSources({ dataUrl = "../data/", address = {}, onChange } = {}) {
  state.root = dataUrl.replace(/data\/?$/, ""); if (onChange) notify = onChange;
  $("tab-sources").innerHTML = PANE;
  const [registry, catalog, manifest, texas] = await Promise.all([fetchJSON("layers.json"), fetchJSON("data/catalog.json"), fetchJSON("data/manifest.json"), fetchJSON("data/texas.geojson")]);
  Object.assign(state, { registry, catalog, manifest, texas });
  state.hazard = registry.defaults.crc_hazard; state.horizon = registry.defaults.horizon; state.rp = registry.defaults.return_period;
  for (const l of registry.layers) state.overlays.set(l.id, l.on === true);
  const linked = sourceById(address.source); if (linked && !HIDDEN_SOURCES.has(linked.id)) state.byOrigin[linked.origin] = linked.id;

  $("hazard").onchange = (e) => {
    state.hazard = e.target.value; state.selected = null; state.pick = null; closeDetail();
    const horizons = horizonsOf(layerById(state.hazard)); if (!horizons.includes(state.horizon)) state.horizon = horizons[0];
    render();
  };
  $("horizon").onchange = (e) => { state.horizon = Number(e.target.value); render(); };
  $("rp").onchange = (e) => { state.rp = Number(e.target.value); render(); };
  $("lock").onchange = (e) => { state.locked = e.target.checked; render(); };
  $("detail-close").onclick = () => clearSelection();
  $("src-reset").onclick = () => state.map.fitBounds(texasBounds(), { padding: 20, duration: 400 });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("tab-sources").classList.contains("hidden")) clearSelection(); });
  let tlWidth = 0; new ResizeObserver(() => { const w = $("timeline").clientWidth; if (state.time && w && Math.abs(w - tlWidth) > 8) { tlWidth = w; drawTimeline(); if (state.map) state.map.resize(); } }).observe($("timeline"));

  await initMap();
  // hooks kept from the old page (the demo and the smoke test drive the views through them)
  document.addEventListener("crc:flyTo", (e) => state.map.jumpTo({ center: e.detail.center, zoom: e.detail.zoom }));
  document.addEventListener("crc:source", (e) => selectSource(e.detail));
  document.addEventListener("crc:compare", (e) => setCompare(e.detail));
  document.addEventListener("crc:time", (e) => seek(e.detail));
  wireCompare();
  globalThis.__sources = state;
}
export async function showSources(origin) {
  const members = sourcesOf(origin); if (!members.length) throw new Error(`no sources with origin ${origin}`);
  const changed = state.origin !== origin;
  state.origin = origin; document.body.dataset.origin = origin;
  const id = state.byOrigin[origin] || (members.find((s) => s.id === state.registry.defaults.source) || members[0]).id;
  state.map.resize();
  if (changed || state.source !== id) { stopPlay(); buildSourceList(); await selectSource(id, true); }
}
export function sourcesAddress() { return state.source ? { source: state.source } : {}; }
