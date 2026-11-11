// Headless smoke test of the redesigned explorer at /next/ (Chrome DevTools protocol, no npm dependencies).
//   python3 -m http.server 8770 --bind 127.0.0.1 --directory site   (in another shell)
//   node tools/smoke-next.mjs <out dir> [url] [width] [height]
// Covers the Risk tab, then every source of the Hail evidence and CRC data tabs (js/sources.js).
// Exits 1 on any failed check, console message or script error; writes screenshots to <out dir>.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";

const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const [S, URL = "http://127.0.0.1:8770/next/", W = "1440", H = "900"] = process.argv.slice(2);
const port = Number(process.env.CDP_PORT) || 9336; mkdirSync(S, { recursive: true });
const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox", `--remote-debugging-port=${port}`, `--user-data-dir=${S}/cdp-profile`, `--window-size=${W},${H}`, "about:blank"], { stdio: "ignore" });
process.on("exit", () => chrome.kill());
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let targets; for (let i = 0; i < 50 && !targets; i++) { try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(200); } }
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl); await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map(); const messages = [];
ws.onmessage = (ev) => { const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === "Runtime.consoleAPICalled" && m.params.type !== "debug") messages.push(`${m.params.type}: ${m.params.args.map((a) => a.value ?? a.description).join(" ").slice(0, 300)}`);
  if (m.method === "Runtime.exceptionThrown") messages.push((m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text).slice(0, 300));
  if (m.method === "Log.entryAdded" && m.params.entry.level === "error" && !/favicon/.test(m.params.entry.text + m.params.entry.url)) messages.push(`${m.params.entry.source}: ${m.params.entry.text} ${m.params.entry.url || ""}`); };
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (e) => { const r = await send("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true }); return r.result?.result?.value ?? r.result?.exceptionDetails?.exception?.description; };
await send("Runtime.enable"); await send("Page.enable"); await send("Log.enable"); await send("Network.enable"); await send("Network.setCacheDisabled", { cacheDisabled: true });
await send("Emulation.setDeviceMetricsOverride", { width: +W, height: +H, deviceScaleFactor: 1, mobile: false });
const shot = async (name) => { const s = await send("Page.captureScreenshot", { format: "png" }); writeFileSync(`${S}/${name}.png`, Buffer.from(s.result.data, "base64")); };
const open = async (url) => { await send("Page.navigate", { url }); for (let i = 0; i < 120; i++) { await sleep(250); const d = await ev("document.body.dataset.ready || document.body.dataset.error || ''"); if (d) break; } await sleep(2500); };
const failures = []; const check = (name, ok, got) => { console.log(`${ok ? "ok  " : "FAIL"} ${name}${ok ? "" : ` — got ${JSON.stringify(got)}`}`); if (!ok) failures.push(name); };
const data = async () => JSON.parse(await ev("JSON.stringify(document.body.dataset)"));

await open(URL);
// Default view: plants under 20 MW are hidden, and the page says so in the table head, the legend and the note.
{ const dd = JSON.parse(await ev("JSON.stringify(document.body.dataset)")); const small = await ev("__risk.data.plants.filter((p) => p.mw < 20).length");
  check("default hides plants under 20 MW", dd.minMw === "20" && Number(dd.hidden) === small && small > 0 && Number(dd.rows) === (await ev("__risk.data.plants.length")) - small, dd);
  const said = [await ev("document.getElementById('hidden-note').textContent"), await ev("document.getElementById('risk-legend').innerText"), await ev("document.getElementById('table-note').innerText"), await ev("document.getElementById('plant-count').textContent")];
  check("the hidden plants are mentioned on the display", said[0].includes(`${small} plants under 20 MW`) && /under 20 MW are not shown/.test(said[1]) && said[2].includes(`${small} smaller plants are hidden`) && / of /.test(said[3]), said); }
// The Risk table now opens with a capacity filter (#min-mw); the checks below are about all plants, so show them all.
await ev("(() => { const s = document.getElementById('min-mw'); if (s && s.value !== '0') { s.value = '0'; s.onchange(); } })()"); await sleep(400);
let d = await data();
check("page ready, Risk tab first", d.ready === "1" && d.tab === "risk" && !d.error, d);
check("table lists every plant", d.rows === String(await ev("__risk.data.totals.plants")), d.rows);
const legend = await ev("document.getElementById('risk-legend').innerText");
check("legend on the map has a unit and numeric ranges", /% per year/.test(legend) && /<\s*[\d.]+/.test(legend) && /≥\s*[\d.]+/.test(legend) && /[\d.]+ – [\d.]+/.test(legend), legend);
check("legend names the data period and the size scale", /1996–\d{4}/.test(legend) && /CAPACITY, MW AC/i.test(legend), legend);
check("scale bar present", (await ev("document.querySelector('.maplibregl-ctrl-scale')?.textContent || ''")).includes("km"));
await shot("n1-overview");

// select from the table: row, ring, circle, tags and detail agree
const first = d.first; await ev("document.querySelector('#plants tbody tr').click()"); await sleep(3000); d = await data();
check("table click selects the plant", d.selected === first, d.selected);
const layers = await ev("JSON.stringify(__risk.overlay._props.layers.map((l) => l.id))");
check("map draws ring, report circle and reports", ["sel-ring", "sel-circle", "sel-reports", "plants"].every((l) => layers.includes(l)), layers);
const tags = await ev("JSON.stringify([...document.querySelectorAll('.tag')].map((t) => t.textContent))");
const sel = JSON.parse(await ev(`JSON.stringify(__risk.data.plants.find((p) => p.id === '${first}'))`));
check("name tag and circle label on the map", tags.includes(sel.name) && /report circle r = [\d.]+ km · \d+ reports/.test(tags), tags);
check("circle label matches the plant's report count", tags.includes(`${sel.reports} reports`), tags);
const detail = await ev("document.getElementById('risk-detail').innerText");
check("detail shows the same plant with both bases", detail.includes(sel.name) && /as reported/i.test(detail) && /bias-corrected/i.test(detail), detail.slice(0, 200));
check("selected row is marked", (await ev("document.querySelector('#plants tr.sel')?.dataset.id")) === first);
check("address carries the selection", (await ev("location.hash")).includes(`plant=${first}`));
await shot("n2-selected");

// select from the map: click the pixel of another plant
const other = JSON.parse(await ev("JSON.stringify((() => { const p = __risk.data.plants.find((q) => q.name.includes('Fighting Jays')); const xy = __risk.map.project([p.lon, p.lat]); const r = document.getElementById('risk-map').getBoundingClientRect(); return { id: p.id, x: r.left + xy.x, y: r.top + xy.y }; })())"));
await ev(`__risk.map.jumpTo({ center: __risk.map.getCenter() })`);
const pos = JSON.parse(await ev(`JSON.stringify((() => { const p = __risk.data.plants.find((q) => q.id === '${other.id}'); __risk.map.jumpTo({ center: [p.lon, p.lat], zoom: 9 }); const xy = __risk.map.project([p.lon, p.lat]); const r = document.getElementById('risk-map').getBoundingClientRect(); return { x: r.left + xy.x, y: r.top + xy.y }; })())`));
await sleep(1500);
for (const type of ["mouseMoved", "mousePressed", "mouseReleased"]) await send("Input.dispatchMouseEvent", { type, x: pos.x, y: pos.y, button: type === "mouseMoved" ? "none" : "left", clickCount: 1 });
await sleep(3000); d = await data();
check("map click selects the plant under the pointer", d.selected === other.id, d.selected);
await shot("n3-map-click");

// measure and basis: totals move from the as-reported to the bias-corrected total
await ev("(() => { const s = document.getElementById('measure'); s.value = 'loss_usd'; s.onchange(); })()"); await sleep(600);
const totals = JSON.parse(await ev("JSON.stringify(__risk.data.totals)"));
const foot = () => ev("document.querySelector('#plants tfoot').innerText");
check("loss total in the table foot, as reported", (await foot()).includes((totals.loss_usd / 1e6).toFixed(2)), await foot());
await ev("document.querySelector('#basis [data-basis=\"1\"]').click()"); await sleep(600); d = await data();
check("basis switch sets bias-corrected", d.basis === "1" && (await ev("document.querySelector('#basis [data-basis=\"1\"]').getAttribute('aria-checked')")) === "true", d.basis);
check("loss total in the table foot, bias-corrected", (await foot()).includes((totals.loss_usd_c / 1e6).toFixed(2)), await foot());
check("legend follows the measure and the basis", /\$ million per year/.test(await ev("document.getElementById('risk-legend').innerText")) && /bias-corrected/.test(await ev("document.getElementById('risk-legend').innerText")));
const top = JSON.parse(await ev("JSON.stringify([...__risk.data.plants].sort((a, b) => (b.loss_usd_c ?? -1) - (a.loss_usd_c ?? -1))[0].id)"));
check("table sorted by the active basis, largest first", (await ev("document.querySelector('#plants tbody tr').dataset.id")) === top);
await ev("document.querySelector('#plants thead th[data-sort=\"name\"]').click()"); await sleep(300);
const names = JSON.parse(await ev("JSON.stringify([...document.querySelectorAll('#plants tbody tr')].slice(0, 3).map((r) => r.querySelector('td').childNodes[1].textContent))"));
check("sort by name", names.join("|") === [...names].sort((a, b) => a.toLowerCase() < b.toLowerCase() ? -1 : 1).join("|"), names);
await ev("(() => { const i = document.getElementById('plant-filter'); i.value = 'fort bend'; i.oninput({ target: i }); })()"); await sleep(300);
check("filter narrows the table", Number((await data()).rows) > 0 && Number((await data()).rows) < 20, (await data()).rows);
await ev("(() => { const s = document.getElementById('measure'); s.value = 'radar_days'; s.onchange(); })()"); await sleep(500);
check("radar measure disables the basis switch", (await ev("document.querySelector('#basis button').disabled")) === true && /days per year/.test(await ev("document.getElementById('risk-legend').innerText")));
await ev("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))"); await sleep(400);
check("Escape clears the selection", ((await data()).selected || "") === "" && (await ev("document.querySelectorAll('.tag').length")) === 0);

// tabs: Hail evidence and CRC data share the pane #tab-sources
const PANE = { risk: "tab-risk", evidence: "tab-sources", crc: "tab-sources", methods: "tab-methods" };
const srcReady = async () => { for (let i = 0; i < 240; i++) { await sleep(125); if (await ev("document.body.dataset.sourcesReady || document.body.dataset.sourcesError || document.body.dataset.error || ''")) break; } await sleep(700); };
const srcReset = () => ev("document.body.dataset.sourcesReady = ''");
// python's http.server now and then drops a connection Chrome wanted to reuse (net::ERR_SOCKET_NOT_CONNECTED) and a module import fails.
// That is the test server, not the page: say so, forget that one message and load once more. Anything else stays a failure.
let retries = 0;
const dropped = async () => { const k = messages.findIndex((m) => /ERR_SOCKET_NOT_CONNECTED/.test(m)); if (k < 0 || retries >= 2 || !/dynamically imported module/.test((await data()).error || "")) return false; retries++; console.log(`note retrying after a dropped connection: ${messages[k]}`); messages.splice(k, 1); return true; };
const openTabOnce = async (tab) => { const wait = (tab === "evidence" || tab === "crc") && (await ev("document.body.dataset.origin || ''")) !== { evidence: "crc-lab", crc: "crc-sdk" }[tab]; if (wait) await srcReset(); await ev(`document.querySelector('.tab[data-tab="${tab}"]').click()`); if (wait) await srcReady(); else await sleep(300); };
const openTab = async (tab) => { await openTabOnce(tab); if (await dropped()) { await open(URL); await openTabOnce(tab); } };
const openLink = async (url) => { await open(url); await srcReady(); if (await dropped()) { await open(url); await srcReady(); } };
for (const tab of ["evidence", "crc", "methods", "risk"]) { await openTab(tab); check(`tab ${tab} opens`, (await data()).tab === tab && (await ev(`!document.getElementById('${PANE[tab]}').classList.contains('hidden')`)) === true && !(await data()).error, await data()); }

// ---------- Hail evidence and CRC data: every source of each origin ----------
const registry = JSON.parse(await ev("fetch('../layers.json').then((r) => r.text())"));
const S_ = (expr) => ev(`(() => { const S = __sources; return ${expr}; })()`);
const J = async (expr) => JSON.parse(await ev(`JSON.stringify((() => { const S = __sources; return ${expr}; })())`));
const text = (id) => ev(`document.getElementById('${id}').innerText`);
const legendText = async () => (await text("src-legend")).replace(/\s+/g, " ");
const layerIds = async () => ((await data()).layers || "").split(" ");
const detailState = () => J(`({ open: !document.getElementById('detail').classList.contains('hidden'), empty: !document.getElementById('src-empty').classList.contains('hidden'), title: document.getElementById('detail-title').textContent, rows: document.querySelectorAll('#detail-meta tr').length, table: document.querySelectorAll('#detail-table tr').length, svg: !!document.querySelector('#chart svg'), picked: document.body.dataset.picked || '' })`);
const pickSource = async (id) => { if ((await data()).source !== id) { await srcReset(); await ev(`document.querySelector('#sources .src-row[data-id="${id}"]').click()`); await srcReady(); } };
const setValue = async (id, value, event = "change") => { await srcReset(); await ev(`(() => { const el = document.getElementById('${id}'); if (el.type === 'checkbox') el.checked = ${JSON.stringify(value)}; else el.value = ${JSON.stringify(String(value))}; el.dispatchEvent(new Event('${event}')); })()`); await srcReady(); };
const press = async (selector) => { await srcReset(); await ev(`document.querySelector('${selector}').click()`); await srcReady(); };
const mouse = async (type, x, y, extra = {}) => send("Input.dispatchMouseEvent", { type, x, y, button: type === "mouseMoved" ? "none" : "left", clickCount: 1, ...extra });
// move the pointer to a place on the sources map (optionally jumping there first), report the hover box, then click
const clickMap = async (lon, lat, zoom) => {
  const pos = await J(`(() => { ${zoom ? `S.map.jumpTo({ center: [${lon}, ${lat}], zoom: ${zoom} });` : ""} const xy = S.map.project([${lon}, ${lat}]); const r = document.getElementById('map').getBoundingClientRect(); return { x: r.left + xy.x, y: r.top + xy.y }; })()`);
  await sleep(1500); await mouse("mouseMoved", pos.x - 3, pos.y - 3); await sleep(150); await mouse("mouseMoved", pos.x, pos.y); await sleep(500);
  const hover = await J("({ shown: !document.getElementById('src-hover').classList.contains('hidden'), text: document.getElementById('src-hover').innerText })");
  await mouse("mousePressed", pos.x, pos.y); await mouse("mouseReleased", pos.x, pos.y); await sleep(1200);
  return hover;
};
const escape = async () => { await ev("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))"); await sleep(700); };
const fits = () => J("({ page: document.documentElement.scrollWidth <= innerWidth && document.body.scrollWidth <= innerWidth, pane: (() => { const p = document.getElementById('tab-sources'); return p.scrollWidth <= p.clientWidth + 1; })(), cols: [...document.querySelectorAll('#tab-sources > .col')].every((c) => c.scrollWidth <= c.clientWidth + 1) })");
// every control of the selected source sits above the fold, without scrolling the column
const controlsVisible = () => J("(() => { const ctl = document.querySelector('#source-panel .ctl:not(.hidden)'); const els = [...ctl.querySelectorAll('input, select, button')].filter((e) => e.offsetParent && !e.closest('.list') && !e.closest('#events-types')); const bottom = Math.max(0, ...els.map((e) => e.getBoundingClientRect().bottom)); const lists = [...ctl.querySelectorAll('.list, #events-types')].filter((e) => e.offsetParent).map((e) => e.getBoundingClientRect().top); return { n: els.length, bottom: Math.round(bottom), listTop: Math.round(Math.max(0, ...lists)), h: innerHeight, scrolled: document.querySelector('.src-scroll').scrollTop }; })()");
const UNIT = { storm_events: /inches/, storm_curves: /\bmm\b/, hail_compare: /hail days per year/, ibtracs: /\bkt\b/, coops: /\bm\b/, ghcnh: /degC|°C/, era5: /°C/, crc_open: /°C/ };
const KIND = { storm_events: "events", storm_curves: "cells", hail_compare: "compare", ibtracs: "tracks", coops: "stations", ghcnh: "stations", era5: "cells", crc_open: "cells" };
const walk = async (tab, origin) => {
  await openTab(tab);
  const want = registry.sources.filter((s) => s.origin === origin && s.id !== "solar_plants").map((s) => s.id);
  const rows = await J("[...document.querySelectorAll('#sources .src-row')].map((b) => b.dataset.id)");
  check(`${tab}: picker lists the ${want.length} sources of ${origin}, one line each, plants left out`, rows.join() === want.join() && (await J("[...document.querySelectorAll('#sources .src-row')].every((b) => b.offsetHeight <= 32 && /loaded|prototype/.test(b.querySelector('.m').textContent))")), rows);
  check(`${tab}: one source is marked as selected`, (await ev("document.querySelectorAll('#sources .src-row[aria-selected=\"true\"]').length")) === 1 && want.includes((await data()).source), (await data()).source);
  for (const id of want) {
    const before = messages.length; await pickSource(id); const d = await data();
    check(`${id}: renders`, d.source === id && d.sourcesReady === "1" && !d.sourcesError && !d.error && (await layerIds()).length >= 2 && (await ev("document.querySelector('#sources .src-row[aria-selected=\"true\"]').dataset.id")) === id, d);
    check(`${id}: no console message or script error`, messages.length === before, messages.slice(before));
    const lg = await legendText();
    check(`${id}: legend on the map has numbers and a unit`, /\d/.test(lg) && UNIT[id].test(lg) && /\d{4}/.test(lg), lg);
    if (KIND[id] === "cells" || KIND[id] === "compare" || id === "ibtracs") { const ticks = await J("[...document.querySelectorAll('#src-legend .ticks span')].map((t) => t.textContent)"); check(`${id}: colour ramp carries numeric ticks`, ticks.length >= 5 && ticks.every((t) => /\d/.test(t)) && /≥/.test(ticks[ticks.length - 1]), ticks); }
    check(`${id}: address carries the source`, (await ev("location.hash")).includes(`source=${id}`) && (await ev("location.hash")).includes(`tab=${tab}`), await ev("location.hash"));
    const f = await fits(); check(`${id}: no horizontal overflow at ${W}px`, f.page && f.pane && f.cols, f);
    const cv = await controlsVisible(); check(`${id}: controls are above the fold`, (cv.n > 0 ? cv.bottom <= cv.h : cv.listTop > 0) && cv.listTop < cv.h - 120 && cv.scrolled === 0, cv);
    check(`${id}: legend, scale bar and attribution do not cover each other`, await J("(() => { const r = (el) => el.getBoundingClientRect(); const hit = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom; const w = document.getElementById('src-map-wrap'); const lg = r(document.getElementById('src-legend')), sc = r(w.querySelector('.maplibregl-ctrl-scale')), at = r(w.querySelector('.maplibregl-ctrl-attrib')), co = r(document.getElementById('src-coords')), m = r(w); return !hit(lg, sc) && !hit(lg, at) && !hit(sc, at) && !hit(co, sc) && !hit(co, at) && !hit(co, lg) && lg.top >= m.top && lg.bottom <= m.bottom && document.getElementById('src-legend').scrollHeight <= document.getElementById('src-legend').clientHeight + 1; })()"));
    check(`${id}: detail column shows its empty state`, (await detailState()).empty === true && (await text("src-empty-text")).length > 40);
    await sleep(600); await shot(`s-${tab}-${id}`);
    await perSource[id]();
  }
};
const cellClick = async (id, layerId) => {
  // a cell with a value near the middle of Texas
  const c = await J(`(() => { const p = [...S.files.entries()].find(([k]) => k.startsWith(S.hazard + '/'))[1]; const k = S.manifest.return_periods.indexOf(S.rp); let best = -1, bd = 1e9; p.cells.forEach((cell, i) => { if (p.values[i][k] === null) return; const [la, lo] = h3.cellToLatLng(cell); const dd = (la - 31.3) ** 2 + (lo + 99.2) ** 2; if (dd < bd) { bd = dd; best = i; } }); const [lat, lon] = h3.cellToLatLng(p.cells[best]); return { cell: p.cells[best], lat, lon }; })()`);
  const hover = await clickMap(c.lon, c.lat);
  check(`${id}: hover readout shows value and unit`, hover.shown && /\d/.test(hover.text) && UNIT[id].test(hover.text), hover);
  const d = await detailState(); const ids = await layerIds();
  check(`${id}: cell click fills the detail column`, d.open && !d.empty && d.rows >= 5 && d.table === 9 && d.svg && d.picked === "cell" && (await text("detail-meta")).includes(c.cell), d);
  check(`${id}: selected cell is outlined on the map`, ids.includes("sel-cell") && ids.indexOf("sel-cell") > ids.indexOf(layerId), ids);
  await shot(`s-${id}-cell`);
  await escape(); check(`${id}: Escape clears the selection`, (await detailState()).empty && !(await layerIds()).includes("sel-cell"), await layerIds());
};
const stationClick = async (id) => {
  const st = await J(`(() => { const f = S.files.get('geo:${id}').features[2]; return { lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1], label: f.properties.label }; })()`);
  const hover = await clickMap(st.lon, st.lat, 8);
  check(`${id}: hover readout names the station with value and unit`, hover.shown && hover.text.includes(st.label) && /\d/.test(hover.text) && UNIT[id].test(hover.text), hover);
  let d = await detailState(); let ids = await layerIds();
  check(`${id}: station click fills the detail column`, d.open && d.title === st.label && d.rows >= 3 && d.table > 3 && d.svg && d.picked === "point", d);
  check(`${id}: selected station is ringed on the map and marked in the list`, ids.includes("sel-ring") && (await ev("document.querySelector('#stations-list li.sel')?.textContent || ''")).includes(st.label), ids);
  await shot(`s-${id}-station`);
  await escape(); check(`${id}: Escape clears the selection`, (await detailState()).empty && !(await layerIds()).includes("sel-ring") && (await ev("document.querySelectorAll('#stations-list li.sel').length")) === 0);
  await ev("document.querySelector('#stations-list li').click()"); await sleep(1200); d = await detailState(); ids = await layerIds();
  check(`${id}: list click selects a station`, d.open && d.svg && ids.includes("sel-ring"), d);
  await escape(); await ev("document.getElementById('src-reset').click()"); await sleep(900);
};
const perSource = {
  storm_events: async () => {
    const lg = await legendText(); check("storm_events: legend lists the report types with counts", /Hail, inches [\d,]+/.test(lg) && /Thunderstorm Wind, knots [\d,]+/.test(lg), lg);
    await setValue("events-from", 2023);
    const e = await J("(() => { const ev = S.events; const hail = ev.index.types.indexOf('Hail'); for (let i = ev.n - 1; i >= 0; i--) if (ev.type[i] === hail && ev.year[i] === 2024 && ev.lon[i] === ev.lon[i] && ev.mag[i] >= 2) return { i, lon: ev.lon[i], lat: ev.lat[i], id: ev.id[i] }; })()");
    const hover = await clickMap(e.lon, e.lat, 11);
    check("storm_events: hover readout shows type, size and unit", hover.shown && /Hail|Wind/.test(hover.text) && /[\d.]+ (inches|knots)/.test(hover.text) && /UTC/.test(hover.text), hover);
    let d = await detailState(); let ids = await layerIds();
    check("storm_events: report click fills the detail column", d.open && /, 20\d\d$/.test(d.title) && d.rows === 7 && d.picked === "point" && /at NCEI/.test(await text("detail-meta")), d);
    check("storm_events: selected report is ringed on the map", ids.includes("sel-ring") && ids.indexOf("sel-ring") > ids.indexOf("events"), ids);
    await shot("s-storm_events-report");
    await escape(); check("storm_events: Escape clears the selection", (await detailState()).empty && !(await layerIds()).includes("sel-ring"));
    await ev("document.getElementById('src-reset').click()"); await sleep(900); await setValue("events-from", 1950);
    // the date window with the timeline
    await setValue("win-on", true); d = await data();
    check("storm_events: date window opens the time bar with a timeline", (await ev("!document.getElementById('timebar').classList.contains('hidden')")) === true && Number(d.timelineMarks) > 50 && Number(d.timelineRows) >= 2 && /2024-03-1[67]/.test(await text("time-clock")), { marks: d.timelineMarks, rows: d.timelineRows, clock: await text("time-clock") });
    const at = async (f) => { await ev(`document.dispatchEvent(new CustomEvent('crc:time', { detail: ${f} }))`); await sleep(350); return Number((await data()).shown); };
    const a = await at(0.1), b = await at(0.95);
    check("storm_events: moving the clock adds reports to the map", b > a && (await layerIds()).includes("window-events") && !(await layerIds()).includes("events"), { a, b });
    check("storm_events: legend names the window", /2024-03-14 \+ 3 days/.test(await legendText()), await legendText());
    await ev("(() => { const m = [...document.querySelectorAll('#timeline line.mark')].find((x) => !x.getAttribute('stroke-dasharray')); m.dispatchEvent(new MouseEvent('click', { bubbles: true })); })()"); await sleep(1200);
    d = await detailState(); check("storm_events: timeline mark opens the report and rings it", d.open && d.rows === 7 && (await layerIds()).includes("sel-ring"), d);
    const tb = await J("(() => { const t = document.getElementById('timebar').getBoundingClientRect(), m = document.getElementById('map').getBoundingClientRect(); return { top: t.top, bottom: t.bottom, h: innerHeight, mapH: m.height }; })()");
    check("storm_events: time bar sits under the map, inside the window", tb.bottom <= tb.h + 1 && tb.mapH > 250, tb);
    await setValue("win-days", 5); check("storm_events: window length changes the timeline", /\+ 5 days/.test(await legendText()) && (await text("timeline-note")).includes("2024-03-19"), await text("timeline-note"));
    await shot("s-storm_events-window");
    await setValue("win-days", 3); await escape(); await setValue("win-on", false);
    check("storm_events: window off hides the time bar", (await ev("document.getElementById('timebar').classList.contains('hidden')")) === true && (await layerIds()).includes("events"));
  },
  storm_curves: async () => {
    check("storm_curves: both curve layers are offered", (await ev("document.getElementById('hazard').options.length")) === 2);
    await cellClick("storm_curves", "cells");
    await setValue("hazard", "thunderstorm_gust"); check("storm_curves: gust layer renders with its unit", /m\/s|kt|knots|mph|km\/h/.test(await legendText()) && (await data()).sourcesReady === "1", await legendText());
    await setValue("hazard", "hail_size");
  },
  hail_compare: async () => {
    const c = () => J("({ mode: S.cmp.mode, a: S.cmp.a, b: S.cmp.b, ra: S.cmp.ra, rb: S.cmp.rb, own: S.cmp.ownScale, top: S.cmp.own[S.cmp.a], shared: S.cmp.shared })");
    let s = await c(); let lg = await legendText();
    check("hail_compare: one-source view opens on the source's own range", s.mode === "single" && s.own === true && (await ev("document.getElementById('cmp-own').checked")) === true && /own 98th percentile/.test(lg), s);
    check("hail_compare: summary table and signature chart are in the controls", (await ev("document.querySelectorAll('#cmp-summary tr').length")) === 5 && (await ev("document.querySelectorAll('#cmp-years rect').length")) > 20);
    await press('#cmp-mode [data-mode="swipe"]'); s = await c(); lg = await legendText();
    check("hail_compare: swipe view uses the shared scale", s.mode === "swipe" && s.own === false && (await ev("document.getElementById('cmp-own').checked")) === false && /One scale for all four/.test(lg) && /Left and right/.test(lg), lg);
    check("hail_compare: swipe line and its two labels are on the map", (await ev("!document.getElementById('swipe').classList.contains('hidden')")) === true && (await text("swipe-a")).length > 5 && (await text("swipe-b")).length > 5);
    const r = await J("(() => { const m = document.getElementById('map').getBoundingClientRect(); const sw = document.getElementById('swipe').getBoundingClientRect(); return [sw.left, m.top + m.height / 2, m.left + m.width * 0.3]; })()");
    const left0 = await ev("document.getElementById('swipe').style.left");
    await mouse("mouseMoved", r[0], r[1]); await mouse("mousePressed", r[0], r[1]); await mouse("mouseMoved", r[2], r[1], { button: "left", buttons: 1 }); await mouse("mouseReleased", r[2], r[1]); await sleep(500);
    const left1 = await ev("document.getElementById('swipe').style.left");
    check("hail_compare: dragging the swipe line moves the split", parseFloat(left0) === 50 && Math.abs(parseFloat(left1) - 30) < 2, { left0, left1 });
    await shot("s-hail_compare-swipe");
    await ev("document.dispatchEvent(new CustomEvent('crc:swipe', { detail: 0.5 }))"); await sleep(300);
    await press('#cmp-mode [data-mode="ratio"]'); s = await c(); lg = await legendText();
    check("hail_compare: ratio view opens on radar ÷ reports", s.mode === "ratio" && s.ra === "mrms" && s.rb === "reports" && (await ev("document.getElementById('cmp-a').value")) === "mrms" && (await ev("document.getElementById('cmp-b').value")) === "reports" && /MRMS.*÷.*Storm reports, hail/.test(lg), lg);
    check("hail_compare: ratio legend is a diverging scale with numeric ends", /≤ 1\/16/.test(lg) && /≥ 16/.test(lg) && /ratio/.test(lg) && (await ev("document.getElementById('swipe').classList.contains('hidden')")) === true, lg);
    await shot("s-hail_compare-ratio");
    await press('#cmp-preset [data-b="reports_corrected"]'); s = await c(); lg = await legendText();
    check("hail_compare: one button switches to radar ÷ bias-corrected reports", s.ra === "mrms" && s.rb === "reports_corrected" && /÷.*corrected/.test(lg) && (await ev("document.querySelector('#cmp-preset [data-b=\"reports_corrected\"]').getAttribute('aria-checked')")) === "true", lg);
    const cell = await J("(() => { let best = 0, bd = 1e9; S.cmp.data.cells.forEach((c, i) => { const [la, lo] = h3.cellToLatLng(c); const dd = (la - 31.3) ** 2 + (lo + 99.2) ** 2; if (dd < bd) { bd = dd; best = i; } }); const [lat, lon] = h3.cellToLatLng(S.cmp.data.cells[best]); return { cell: S.cmp.data.cells[best], lat, lon }; })()");
    const hover = await clickMap(cell.lon, cell.lat);
    check("hail_compare: hover readout lists the four sources with the unit", hover.shown && /hail days per year/.test(hover.text) && (hover.text.match(/\d\.\d|\d{2}/g) || []).length >= 4, hover);
    const d = await detailState(); const ids = await layerIds();
    check("hail_compare: cell click fills the detail column and outlines the cell", d.open && d.table === 5 && (await ev("document.querySelectorAll('#chart .bar').length")) === 4 && ids.includes("sel-cell") && (await text("detail-meta")).includes(cell.cell), d);
    await shot("s-hail_compare-cell");
    await press('#cmp-mode [data-mode="single"]'); s = await c();
    check("hail_compare: back in the one-source view the own range and the first pair return", s.mode === "single" && s.own === true && s.a === "reports", s);
    await escape();
  },
  ibtracs: async () => {
    await setValue("tracks-color", "category"); let lg = await legendText();
    check("ibtracs: category legend gives the wind range of each class", /category 1 64–82 kt/.test(lg) && /category 5 ≥ 137 kt/.test(lg) && /34 kt wind radius/.test(lg), lg);
    await setValue("tracks-color", "wind");
    // click a track on the map
    const t = await J("(() => { const s = S.tracks.storms.find((x) => x.name === 'Harvey' && x.season === 2017); const tb = S.tracks.texas_box; const k = s.points.findIndex((p) => p[0] >= tb[0] && p[0] <= tb[2] && p[1] >= tb[1] && p[1] <= tb[3]); const a = s.points[k + 1], b = s.points[k + 2]; return { sid: s.sid, label: s.label, lon: (a[0] + b[0]) / 2, lat: (a[1] + b[1]) / 2 }; })()");
    await setValue("tracks-name", "harvey", "input");
    check("ibtracs: name filter narrows the list", (await ev("document.querySelectorAll('#tracks-list li').length")) >= 1 && (await ev("document.querySelectorAll('#tracks-list li').length")) < 6);
    await srcReset(); const hover = await clickMap(t.lon, t.lat, 7); await srcReady();
    check("ibtracs: hover readout names the storm with wind in kt", hover.shown && /HARVEY/i.test(hover.text) && /\d+ kt/.test(hover.text), hover);
    let d = await detailState(); let ids = await layerIds();
    check("ibtracs: track click fills the detail column", d.open && d.title === t.label && d.rows === 10 && d.svg && d.picked === "storm" && (await J("S.storm")) === t.sid, d);
    check("ibtracs: selected track is emphasised and marked in the list", ids.includes("sel-track") && ids.includes("storm-marker") && (await ev("document.querySelector('#tracks-list li.sel')?.dataset.sid")) === t.sid, ids);
    // the storm player
    const dd = await data();
    check("ibtracs: storm player opens under the map with the timeline", (await ev("!document.getElementById('timebar').classList.contains('hidden')")) === true && Number(dd.timelineRows) >= 2 && /Storm player/i.test(await text("time-title")), { rows: dd.timelineRows });
    const at = async (f) => { await ev(`document.dispatchEvent(new CustomEvent('crc:time', { detail: ${f} }))`); await sleep(350); const x = await data(); return { now: x.now, marker: x.marker, shown: Number(x.shown) }; };
    const a = await at(0.1), b = await at(0.8);
    check("ibtracs: scrubbing moves the storm marker and adds reports", a.marker !== b.marker && a.now < b.now && b.shown > a.shown, { a, b });
    await at(0.2); await ev("document.getElementById('time-play').click()"); await sleep(2000); const p = await data();
    check("ibtracs: play advances the clock", p.playing === "1" && p.now > "2017-08" && Number(p.frameMs) >= 0 && (await at(0.2)).now < p.now, { now: p.now, playing: p.playing });
    check("ibtracs: scrubbing pauses the player", (await data()).playing === "" && (await text("time-play")) === "▶");
    await at(0.45); await sleep(500); await shot("s-ibtracs-player");
    await escape(); d = await detailState(); ids = await layerIds();
    check("ibtracs: Escape clears the storm and closes the player", d.empty && (await J("S.storm")) === null && !ids.includes("sel-track") && (await ev("document.getElementById('timebar').classList.contains('hidden')")) === true, ids);
    await srcReady(); await press("#tracks-list li"); d = await detailState();
    check("ibtracs: list click selects a storm", d.open && d.picked === "storm" && (await layerIds()).includes("sel-track"), d);
    await srcReset(); await ev("document.getElementById('detail-close').click()"); await srcReady();
    await setValue("tracks-name", "", "input"); await ev("document.getElementById('src-reset').click()"); await sleep(900);
  },
  coops: () => stationClick("coops"),
  ghcnh: () => stationClick("ghcnh"),
  era5: () => cellClick("era5", "cells"),
  crc_open: async () => {
    check("crc_open: three horizons and the loaded hazards are offered", (await ev("document.getElementById('horizon').options.length")) === 3 && (await ev("document.querySelectorAll('#hazard optgroup:first-child option').length")) === 8);
    await setValue("horizon", 2080); let lg = await legendText();
    check("crc_open: horizon selector redraws and the legend names the horizon and pathway", /2080/.test(lg) && /ssp585/i.test(lg), lg);
    await setValue("horizon", 2050);
    await cellClick("crc_open", "cells");
    await setValue("hazard", "rflood"); lg = await legendText();
    check("crc_open: another hazard renders with its own unit and caveats", /River flood depth/.test(lg) && /\d/.test(lg) && (await ev("document.querySelectorAll('#caveats li').length")) >= 5 && /CC BY-NC|CC-BY-NC/.test(await text("caveats")), lg);
    await setValue("hazard", "tx_max");
    // overlay: tracks over the cells
    await srcReset(); await ev("(() => { document.getElementById('also').open = true; const cb = document.querySelector('#overlays input[data-layer=\"ibtracs\"]'); cb.checked = true; cb.dispatchEvent(new Event('change')); })()"); await srcReady();
    check("crc_open: an overlay draws beside the cells and is named in the legend", (await layerIds()).includes("tracks") && (await layerIds()).includes("cells") && /Also shown.*Tropical cyclone tracks/.test(await legendText()), await legendText());
    await shot("s-crc_open-overlay");
    await srcReset(); await ev("(() => { const cb = document.querySelector('#overlays input[data-layer=\"ibtracs\"]'); cb.checked = false; cb.dispatchEvent(new Event('change')); document.getElementById('also').open = false; })()"); await srcReady();
  },
};
await walk("evidence", "crc-lab");
await walk("crc", "crc-sdk");
check("sources map has a metric scale bar and a coordinate readout", /km|\bm\b/.test(await ev("document.querySelector('#src-map-wrap .maplibregl-ctrl-scale')?.textContent || ''")) && /° N\s+[\d.]+° W/.test(await text("src-coords")), await text("src-coords"));
check("sources pane never sets the shell's ready flag by itself", (await data()).ready === "1");
// deep link to a source
await openLink(`${URL}#tab=evidence&source=hail_compare`); d = await data();
check("deep link opens Hail evidence on the linked source", d.tab === "evidence" && d.source === "hail_compare" && d.origin === "crc-lab" && d.sourcesReady === "1" && (await ev("location.hash")).includes("source=hail_compare") && (await layerIds()).includes("cmp"), d);
await shot("s-deep-link-hail_compare");
await openLink(`${URL}#tab=crc&source=crc_open`); d = await data();
check("deep link opens CRC data on the linked source", d.tab === "crc" && d.source === "crc_open" && (await layerIds()).includes("cells"), d);
await open(`${URL}#tab=risk&plant=${other.id}&measure=p2in&basis=1`); await sleep(1500); d = await data();
check("deep link restores plant, measure and basis", d.selected === other.id && d.measure === "p2in" && d.basis === "1", d);
await shot("n4-deep-link");

// ---------- two projects, Methods, About, the tour ----------
await open(URL); await sleep(500);
check("opens on the hail project with its three tabs", (await data()).project === "hail" && (await ev("[...document.querySelectorAll('.tab:not(.hidden)')].map((b) => b.dataset.tab).join()")) === "risk,evidence,methods");
await ev("document.querySelector('.proj[data-project=\"crc\"]').click()"); await sleep(4000); d = await data();
check("project switch opens Texas CRC data with its own tabs", d.project === "crc" && d.tab === "crc" && d.origin === "crc-sdk" && (await ev("[...document.querySelectorAll('.tab:not(.hidden)')].map((b) => b.dataset.tab).join()")) === "crc,crc-about" && (await ev("document.title")).includes("CRC data"), d);
await ev("document.querySelector('.tab[data-tab=\"crc-about\"]').click()"); await sleep(1500);
const about = await ev("document.getElementById('tab-crc-about').innerText");
check("CRC About lists the sources shown and the SDK catalogue", (await data()).crcAbout === "1" && /Tropical cyclone tracks/.test(about) && /HazardDataset/.test(about) && /crc-sdk 0\.\d+/.test(about), about.slice(0, 200));
await shot("p-crc-about");
await ev("document.querySelector('.proj[data-project=\"hail\"]').click()"); await sleep(800);
check("switching back returns to the hail project's last tab", (await data()).project === "hail" && (await data()).tab === "risk", await data());
await ev("document.querySelector('.tab[data-tab=\"methods\"]').click()"); await sleep(2000);
const mText = await ev("document.getElementById('tab-methods').innerText");
check("Methods has the steps, the placeholders and the limits", (await data()).methods === "1" && /Report circle/.test(mText) && /PLACEHOLDER/i.test(mText) && /Known limits/i.test(mText) && (await ev("document.querySelectorAll('#tab-methods .flow .box').length")) === 5, mText.slice(0, 200));
check("four curve charts drawn", (await ev("document.querySelectorAll('#tab-methods svg path[stroke]').length")) >= 6);
// the stow sliders pick among curves shipped as values: at the defaults the curve gives the spec's 0.1248 at 2 inches
const curves = JSON.parse(await ev("fetch('../data/assets/curves.json').then((r) => r.text())"));
const at2 = (glass, tilt, p) => curves.solar.plant[glass][`${tilt}|${p}`][curves.d_mm.indexOf(50)];
check("solar curve at the defaults matches the shipped values", Math.abs(Number(await ev("document.getElementById('tab-methods').dataset.solarAt2in")) - at2("glass_glass_2.0", 60, 0.8)) < 1e-9 && Math.abs(at2("glass_glass_2.0", 60, 0.8) - 0.1161) < 0.02);
await ev("(() => { const s = document.querySelector('#m-p'); s.value = '0'; s.dispatchEvent(new Event('input')); const t = document.querySelector('#m-tilt'); t.value = String(t.max); t.dispatchEvent(new Event('input')); })()"); await sleep(300);
check("sliders move the curve to the never-stowed values", (await ev("document.getElementById('tab-methods').dataset.solarKey")) === "glass_glass_2.0|75|0" && Math.abs(Number(await ev("document.getElementById('tab-methods').dataset.solarAt2in")) - at2("glass_glass_2.0", 75, 0)) < 1e-9 && at2("glass_glass_2.0", 75, 0) > at2("glass_glass_2.0", 60, 0.8));
check("Methods fits the window width", (await ev("document.documentElement.scrollWidth <= innerWidth")) === true);
await shot("p-methods");
if (!process.argv.includes("--no-demo")) {
  await ev("document.getElementById('demo-start').click()"); await sleep(1500);
  check("tour starts with a caption", (await data()).demo === "running" && (await ev("document.getElementById('demo-caption').textContent.length")) > 20);
  const seen = new Set(); for (let i = 0; i < 120 && (await data()).demo === "running"; i++) { seen.add(`${(await data()).project}/${(await data()).tab}`); if (i === 30) await shot("p-tour-mid"); await sleep(500); }
  d = await data();
  check("tour finishes in 30 to 45 seconds without a failed step", d.demo === "done" && Number(d.demoMs) > 30000 && Number(d.demoMs) < 45000 && !d.demoError, d);
  check("tour visits both projects and returns to Risk", ["hail/risk", "hail/evidence", "hail/methods", "crc/crc"].every((s) => seen.has(s)) && d.tab === "risk", [...seen]);
}

check("no console messages or script errors", messages.length === 0, messages);
writeFileSync(`${S}/smoke-next.json`, JSON.stringify({ url: URL, failures, messages }, null, 1));
ws.close(); chrome.kill();
console.log(failures.length ? `${failures.length} FAILED` : "all checks passed");
process.exit(failures.length ? 1 : 0);
