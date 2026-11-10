// Headless smoke test of the explorer (v2, source-centric) over the Chrome DevTools protocol (no npm dependencies).
//   python3 -m http.server 8770 --bind 127.0.0.1 --directory site   (in another shell)
//   node tools/smoke.mjs <out dir> [url]
// Walks every source, filters, a click per source kind and the Sources tab; writes screenshots and
// smoke-report.json to <out dir>; prints one JSON line per step.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";

const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const [S, URL = "http://127.0.0.1:8770/"] = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const port = 9334;
mkdirSync(S, { recursive: true });
const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox", `--remote-debugging-port=${port}`, `--user-data-dir=${S}/cdp-profile`, "--window-size=1400,900", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let version; for (let i = 0; i < 50 && !version; i++) { try { version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(); } catch { await sleep(200); } }
const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map(); const console_ = [], errors = [];
ws.onmessage = (ev) => { const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === "Runtime.consoleAPICalled" && m.params.type !== "debug") console_.push(`${m.params.type}: ${m.params.args.map((a) => a.value ?? a.description).join(" ").slice(0, 300)}`);
  if (m.method === "Runtime.exceptionThrown") errors.push((m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text).slice(0, 300));
  if (m.method === "Log.entryAdded" && m.params.entry.level === "error" && !/favicon/.test(m.params.entry.text + m.params.entry.url)) errors.push(`${m.params.entry.source}: ${m.params.entry.text} ${m.params.entry.url || ""}`); };
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async (expression) => { const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }); return r.result?.result?.value ?? r.result?.exceptionDetails?.text; };
await send("Runtime.enable"); await send("Page.enable"); await send("Log.enable"); await send("Network.enable"); await send("Network.setCacheDisabled", { cacheDisabled: true });
await send("Emulation.setDeviceMetricsOverride", { width: 1400, height: 900, deviceScaleFactor: 1, mobile: false });
const report = { url: URL, steps: [] };
async function waitReady(label, timeoutMs = 40000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) { const r = await evaluate("document.body ? (document.body.dataset.ready || document.body.dataset.error || '') : ''"); if (r && r !== "Uncaught") break; await sleep(100); }
  const step = { label, status: await evaluate("document.getElementById('status').textContent"), ms: await evaluate("document.body.dataset.ms"), source: await evaluate("document.body.dataset.source"), error: await evaluate("document.body.dataset.error || ''"), wall_ms: Date.now() - t0 };
  report.steps.push(step); console.log(JSON.stringify(step)); return step;
}
async function shot(name) { const r = await send("Page.captureScreenshot", { format: "png" }); writeFileSync(`${S}/${name}.png`, Buffer.from(r.result.data, "base64")); }
const reset = () => evaluate("document.body.dataset.ready=''");
async function change(selector, value, event = "change") { await reset(); await evaluate(`(() => { const el = document.querySelector('${selector}'); el.value = ${JSON.stringify(String(value))}; el.dispatchEvent(new Event('${event}')); })()`); }
async function source(id) { await reset(); await evaluate(`document.dispatchEvent(new CustomEvent('crc:source', { detail: ${JSON.stringify(id)} }))`); return waitReady(`source ${id}`); }
async function click(x, y) { await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y }); await sleep(200); await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 }); await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 }); await sleep(600); }
const detail = async () => ({ hidden: await evaluate("document.getElementById('detail').classList.contains('hidden')"), title: await evaluate("document.getElementById('detail-title').textContent"), meta: (await evaluate("document.getElementById('detail-meta').textContent")).slice(0, 160), rows: await evaluate("document.querySelectorAll('#detail-table tr').length"), svg: await evaluate("!!document.querySelector('#chart svg')") });
const centre = () => evaluate("(() => { const r = document.getElementById('map').getBoundingClientRect(); return [r.left + r.width/2, r.top + r.height/2]; })()");

await send("Page.navigate", { url: URL });
const first = await waitReady("first view (default source)"); await sleep(1500); await shot("s1-first");
first.sources_listed = await evaluate("document.querySelectorAll('#sources .src').length");
first.groups = await evaluate("[...document.querySelectorAll('#sources .grp')].map((g) => g.dataset.group + ':' + g.querySelector('.badge').textContent)");
first.header_badge = await evaluate("document.querySelector('#source-blurb .badge')?.textContent"); first.caveat_badge = await evaluate("document.querySelector('#caveats .badge')?.textContent");
console.log(JSON.stringify({ groups: first.groups, header_badge: first.header_badge, caveat_badge: first.caveat_badge }));
// IBTrACS: filters, list click, track detail
await change("#tracks-min-wind", 100); const strong = await waitReady("tracks: at least 100 kt"); strong.list = await evaluate("document.querySelectorAll('#tracks-list li').length");
await change("#tracks-name", "harvey", "input"); const harvey = await waitReady("tracks: name contains harvey"); harvey.list = await evaluate("document.querySelectorAll('#tracks-list li').length");
await reset(); await evaluate("document.querySelector('#tracks-list li').click()"); await waitReady("tracks: click Harvey in the list"); await sleep(800);
report.track_detail = await detail(); console.log(JSON.stringify(report.track_detail)); await shot("s2-track");
// storm player: scrub, then play; the marker must move and reports must appear
const ds = (k) => evaluate(`document.body.dataset.${k} || ''`);
const at = async (f) => { await evaluate(`document.dispatchEvent(new CustomEvent('crc:time', { detail: ${f} }))`); await sleep(300); return { f, now: await ds("now"), marker: await ds("marker"), shown: Number(await ds("shown")) }; };
report.player = { timebar_hidden: await evaluate("document.getElementById('timebar').classList.contains('hidden')"), timeline_ms: await ds("timelineMs"), marks: await ds("timelineMarks"), rows: await ds("timelineRows"), steps: [await at(0.1), await at(0.4), await at(0.8)] };
await evaluate("document.getElementById('time-play').click()"); await sleep(2500);
report.player.after_play = { now: await ds("now"), marker: await ds("marker"), shown: Number(await ds("shown")), frame_ms: await ds("frameMs"), fps: await evaluate("new Promise((res) => { let n = 0; const t0 = performance.now(); const f = () => { n++; if (performance.now() - t0 < 1000) requestAnimationFrame(f); else res(n); }; requestAnimationFrame(f); })") };
await evaluate("document.getElementById('time-play').click()"); await at(0.45); await sleep(600);
console.log(JSON.stringify(report.player)); await shot("s2b-player");
await change("#tracks-name", "", "input"); await waitReady("tracks: clear name");
await change("#tracks-min-wind", 0); await waitReady("tracks: clear wind"); await change("#tracks-color", "category"); await waitReady("tracks: colour by category"); await sleep(800); await shot("s3-tracks-category");
// Storm Events
await source("storm_events"); await sleep(800); report.events = { status: await evaluate("document.getElementById('events-status').textContent"), types: await evaluate("document.querySelectorAll('#events-types label').length") }; console.log(JSON.stringify(report.events)); await shot("s4-events");
await change("#events-from", 2020); await waitReady("events from 2020");
// date window with the timeline: the Fort Bend hail days (default example)
await reset(); await evaluate("(() => { const cb = document.getElementById('win-on'); cb.checked = true; cb.dispatchEvent(new Event('change')); })()"); await waitReady("events: date window 2024-03-14 + 3 days"); await sleep(800);
report.window = { clock: await evaluate("document.getElementById('time-clock').textContent"), note: (await evaluate("document.getElementById('timeline-note').textContent")).slice(0, 90), timeline_ms: await evaluate("document.body.dataset.timelineMs"), marks: await evaluate("document.body.dataset.timelineMarks"), rows: await evaluate("document.body.dataset.timelineRows"), shown: await evaluate("document.body.dataset.shown") };
await evaluate("(() => { const m = document.querySelector('#timeline .mark'); m.dispatchEvent(new MouseEvent('click', { bubbles: true })); })()"); await sleep(600);
report.window.clicked = await detail(); console.log(JSON.stringify(report.window)); await shot("s4b-window");
await reset(); await evaluate("(() => { const cb = document.getElementById('win-on'); cb.checked = false; cb.dispatchEvent(new Event('change')); })()"); await waitReady("events: window off");
// CO-OPS: list click -> detail with levels
await source("coops"); await sleep(600); await reset(); await evaluate("document.querySelector('#stations-list li').click()"); await sleep(1200);
report.coops_detail = await detail(); console.log(JSON.stringify(report.coops_detail)); await shot("s5-coops");
// GHCNh
await source("ghcnh"); await sleep(600); report.ghcnh_stations = await evaluate("document.querySelectorAll('#stations-list li').length"); console.log(JSON.stringify({ ghcnh_stations: report.ghcnh_stations }));
// ERA5 baseline (cells) and CRC Open (cells) with a cell click
await source("era5"); report.era5 = { horizon: await evaluate("document.getElementById('horizon').value"), options: await evaluate("document.getElementById('horizon').options.length") }; console.log(JSON.stringify(report.era5)); await sleep(800); await shot("s6-era5");
await source("storm_curves"); report.curves = { hazards: await evaluate("document.getElementById('hazard').options.length"), horizon: await evaluate("document.getElementById('horizon').value") }; console.log(JSON.stringify(report.curves)); await sleep(800); await shot("s6b-curves");
await source("crc_open"); await sleep(800);
await change("#hazard", "rflood"); await waitReady("crc_open: rflood"); await change("#hazard", "tx_max"); await waitReady("crc_open: tx_max"); await sleep(600);
const c = await centre(); await click(c[0], c[1]); report.cell_detail = await detail(); console.log(JSON.stringify(report.cell_detail)); await shot("s7-crc-cell");
// overlay: tracks over cells
await reset(); await evaluate("(() => { const lab = [...document.querySelectorAll('#overlays label')].find((l) => l.textContent.includes('Tropical cyclone')); const cb = lab.querySelector('input'); cb.checked = true; cb.dispatchEvent(new Event('change')); })()"); await waitReady("overlay: tracks over CRC Open cells"); await sleep(800); await shot("s8-overlay");
// Sources tab
await evaluate("document.querySelector('.tab[data-view=catalog]').click()"); await sleep(500);
report.catalog = { sources: await evaluate("document.querySelectorAll('#catalog-sources tr').length - 1"), hazards: await evaluate("document.querySelectorAll('#catalog-table tr').length - 1"), others: await evaluate("document.querySelectorAll('#sources-table tr').length - 1") };
console.log(JSON.stringify(report.catalog)); await shot("s9-sources-tab");
report.catalog.badges = await evaluate("document.querySelectorAll('#catalog-sources .badge').length");
// About tab: numbers come from the data files
await evaluate("document.querySelector('.tab[data-view=about]').click()"); await sleep(800);
report.about = { built: await evaluate("document.body.dataset.about || ''"), headings: await evaluate("[...document.querySelectorAll('#about h2')].map((h) => h.textContent)"), storms_line: await evaluate("[...document.querySelectorAll('#about li')].find((l) => l.textContent.includes('Tropical cyclone'))?.textContent.slice(0, 200)"), version_line: (await evaluate("[...document.querySelectorAll('#about p')].find((p) => p.textContent.startsWith('Built '))?.textContent")).slice(0, 160), video: await evaluate("!!document.querySelector('#about video')") };
console.log(JSON.stringify(report.about)); await shot("s10-about");
if (!process.argv.includes("--no-demo")) {
// demo: ?demo=1 must reach the end card in 27-33 s and leave the page usable
await send("Page.navigate", { url: URL + "?demo=1" }); const d0 = Date.now(); let state_ = ""; let mid = false;
while (Date.now() - d0 < 60000) { state_ = await evaluate("document.body ? (document.body.dataset.demo || '') : ''"); if (!mid && Date.now() - d0 > 12000) { mid = true; await shot("s11-demo-mid"); report.demo_mid_caption = await evaluate("document.getElementById('demo-caption').textContent"); } if (state_ && state_ !== "running" && await evaluate("document.body.dataset.demoMs || ''")) break; await sleep(250); }
report.demo = { state: state_, tour_ms: Number(await evaluate("document.body.dataset.demoTourMs")), total_ms: Number(await evaluate("document.body.dataset.demoMs")), bar_hidden: await evaluate("document.getElementById('demo-bar').classList.contains('hidden')"), source_after: await evaluate("document.querySelector('#sources .src.on')?.dataset.id"), view_after: await evaluate("document.querySelector('.view.on').id"), timebar_hidden_after: await evaluate("document.getElementById('timebar').classList.contains('hidden')") };
await reset(); await evaluate("document.dispatchEvent(new CustomEvent('crc:source', { detail: 'coops' }))"); report.demo.usable_after = (await waitReady("after demo: switch source")).source;
console.log(JSON.stringify(report.demo)); console.log(JSON.stringify({ mid: report.demo_mid_caption }));
// Escape exits a running demo
await evaluate("document.getElementById('demo-start').click()"); await sleep(2500); await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 }); await sleep(2500);
report.demo_escape = { state: await evaluate("document.body.dataset.demo"), bar_hidden: await evaluate("document.getElementById('demo-bar').classList.contains('hidden')") }; console.log(JSON.stringify(report.demo_escape));
}
report.console = console_; report.errors = errors;
writeFileSync(`${S}/smoke-report.json`, JSON.stringify(report, null, 1));
console.log("console:", JSON.stringify(console_.slice(0, 10))); console.log("errors:", JSON.stringify(errors.slice(0, 10)));
ws.close(); chrome.kill();
