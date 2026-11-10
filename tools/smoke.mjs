// Headless smoke test of the explorer over the Chrome DevTools protocol (no npm dependencies).
//   python3 -m http.server 8765 --bind 127.0.0.1 --directory site   (in another shell)
//   node tools/smoke.mjs <out dir> [url] [--sources]
// Writes screenshots and smoke-report.json to <out dir>; prints one JSON line per step.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";

const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const [S, URL = "http://127.0.0.1:8765/"] = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const SOURCES = process.argv.includes("--sources");
const port = 9333;
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
  const step = { label, status: await evaluate("document.getElementById('status').textContent"), ms: await evaluate("document.body.dataset.ms"), error: await evaluate("document.body.dataset.error || ''"), wall_ms: Date.now() - t0 };
  report.steps.push(step); console.log(JSON.stringify(step)); return step;
}
async function shot(name) { const r = await send("Page.captureScreenshot", { format: "png" }); writeFileSync(`${S}/${name}.png`, Buffer.from(r.result.data, "base64")); }
async function change(selector, value) { await evaluate("document.body.dataset.ready=''"); await evaluate(`(() => { const el = document.querySelector('${selector}'); el.value = '${value}'; el.dispatchEvent(new Event('change')); })()`); }
async function toggle(layerId) { await evaluate("document.body.dataset.ready=''"); await evaluate(`(() => { const lab = [...document.querySelectorAll('#layers label')].find((l) => l.textContent.includes(${JSON.stringify(layerId)})); const cb = lab.querySelector('input'); cb.checked = !cb.checked; cb.dispatchEvent(new Event('change')); })()`); }
async function click(x, y) { await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y }); await sleep(200); await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 }); await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 }); await sleep(600); }
const detail = async () => ({ hidden: await evaluate("document.getElementById('detail').classList.contains('hidden')"), title: await evaluate("document.getElementById('detail-title').textContent"), meta: (await evaluate("document.getElementById('detail-meta').textContent")).slice(0, 200), rows: await evaluate("document.querySelectorAll('#detail-table tr').length"), svg: await evaluate("!!document.querySelector('#chart svg')") });

await send("Page.navigate", { url: URL });
await waitReady("first view"); await sleep(1500); await shot("s1-first");
await change("#rp", "500"); await waitReady("switch return period");
await change("#hazard", "rflood"); await waitReady("switch hazard to rflood (r7)"); await sleep(800);
await change("#hazard", "tx_max"); await waitReady("switch back to tx_max (cached)"); await sleep(800);
const box = await evaluate("(() => { const r = document.getElementById('map').getBoundingClientRect(); return [r.left + r.width/2, r.top + r.height/2]; })()");
await click(box[0], box[1]); report.cell_detail = await detail(); console.log(JSON.stringify(report.cell_detail)); await shot("s2-cell-detail");
if (SOURCES) {
  // switch on the three source layers, one at a time, and click a point
  for (const [title, id] of [["Tropical cyclone tracks", "ibtracs"], ["Coastal water levels", "coops"], ["Hottest hour of the year", "ghcnh"]]) {
    await toggle(title); const step = await waitReady(`toggle ${id}`); await sleep(1200);
    step.features = await evaluate(`(async () => { const r = await fetch('data/sources/${id}.geojson'); const j = await r.json(); return j.features.length; })()`);
    console.log(JSON.stringify({ id, features: step.features }));
  }
  await shot("s3-sources");
  // click a CO-OPS station: project its coordinates through MapLibre
  const pt = await evaluate(`(async () => { const r = await fetch('data/sources/coops.geojson'); const j = await r.json(); const f = j.features.find((f) => f.properties.station_id === '8771341') || j.features[0]; return f.geometry.coordinates; })()`);
  // jump to the station through the page's test hook, then click the map centre
  await evaluate(`(() => { document.dispatchEvent(new CustomEvent('crc:flyTo', { detail: { center: ${JSON.stringify(pt)}, zoom: 9 } })); })()`);
  await sleep(2500);
  const c = await evaluate("(() => { const r = document.getElementById('map').getBoundingClientRect(); return [r.left + r.width/2, r.top + r.height/2]; })()");
  await click(c[0], c[1]); report.point_detail = await detail(); console.log(JSON.stringify(report.point_detail)); await shot("s4-point-detail");
  // the ERA5 baseline is an h3-cells layer with its own horizon
  await change("#hazard", "era5_txx"); const era5 = await waitReady("switch hazard to era5_txx (r4 baseline)"); await sleep(1200);
  era5.horizon = await evaluate("document.getElementById('horizon').value"); era5.horizon_options = await evaluate("document.getElementById('horizon').options.length");
  era5.caveat_first = (await evaluate("document.querySelector('#caveats li').textContent")).slice(0, 120);
  console.log(JSON.stringify({ horizon: era5.horizon, options: era5.horizon_options, caveat: era5.caveat_first })); await shot("s4b-era5");
  await change("#hazard", "tx_max"); await waitReady("back to tx_max from era5");
}
await evaluate("document.querySelector('.tab[data-view=catalog]').click()"); await sleep(500);
report.catalog = { rows: await evaluate("document.querySelectorAll('#catalog-table tr').length - 1"), loaded: await evaluate("document.querySelectorAll('#catalog-table tr.loaded').length"), sources: await evaluate("document.querySelectorAll('#sources-table tr').length - 1") };
console.log(JSON.stringify(report.catalog)); await shot("s5-catalog");
report.console = console_; report.errors = errors;
writeFileSync(`${S}/smoke-report.json`, JSON.stringify(report, null, 1));
console.log("console:", JSON.stringify(console_.slice(0, 10))); console.log("errors:", JSON.stringify(errors.slice(0, 10)));
ws.close(); chrome.kill();
