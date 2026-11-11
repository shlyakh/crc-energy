// Headless smoke test of the redesigned explorer at /next/ (Chrome DevTools protocol, no npm dependencies).
//   python3 -m http.server 8770 --bind 127.0.0.1 --directory site   (in another shell)
//   node tools/smoke-next.mjs <out dir> [url] [width] [height]
// Exits 1 on any failed check, console message or script error; writes screenshots to <out dir>.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";

const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const [S, URL = "http://127.0.0.1:8770/next/", W = "1440", H = "900"] = process.argv.slice(2);
const port = 9336; mkdirSync(S, { recursive: true });
const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox", `--remote-debugging-port=${port}`, `--user-data-dir=${S}/cdp-profile`, `--window-size=${W},${H}`, "about:blank"], { stdio: "ignore" });
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
let d = await data();
check("page ready, Risk tab first", d.ready === "1" && d.tab === "risk" && !d.error, d);
check("table lists every plant", d.rows === String(await ev("__risk.data.totals.plants")), d.rows);
const legend = await ev("document.getElementById('legend').innerText");
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
const detail = await ev("document.getElementById('detail').innerText");
check("detail shows the same plant with both bases", detail.includes(sel.name) && /as reported/i.test(detail) && /bias-corrected/i.test(detail), detail.slice(0, 200));
check("selected row is marked", (await ev("document.querySelector('#plants tr.sel')?.dataset.id")) === first);
check("address carries the selection", (await ev("location.hash")).includes(`plant=${first}`));
await shot("n2-selected");

// select from the map: click the pixel of another plant
const other = JSON.parse(await ev("JSON.stringify((() => { const p = __risk.data.plants.find((q) => q.name.includes('Fighting Jays')); const xy = __risk.map.project([p.lon, p.lat]); const r = document.getElementById('map').getBoundingClientRect(); return { id: p.id, x: r.left + xy.x, y: r.top + xy.y }; })())"));
await ev(`__risk.map.jumpTo({ center: __risk.map.getCenter() })`);
const pos = JSON.parse(await ev(`JSON.stringify((() => { const p = __risk.data.plants.find((q) => q.id === '${other.id}'); __risk.map.jumpTo({ center: [p.lon, p.lat], zoom: 9 }); const xy = __risk.map.project([p.lon, p.lat]); const r = document.getElementById('map').getBoundingClientRect(); return { x: r.left + xy.x, y: r.top + xy.y }; })())`));
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
check("legend follows the measure and the basis", /\$ million per year/.test(await ev("document.getElementById('legend').innerText")) && /bias-corrected/.test(await ev("document.getElementById('legend').innerText")));
const top = JSON.parse(await ev("JSON.stringify([...__risk.data.plants].sort((a, b) => (b.loss_usd_c ?? -1) - (a.loss_usd_c ?? -1))[0].id)"));
check("table sorted by the active basis, largest first", (await ev("document.querySelector('#plants tbody tr').dataset.id")) === top);
await ev("document.querySelector('#plants thead th[data-sort=\"name\"]').click()"); await sleep(300);
const names = JSON.parse(await ev("JSON.stringify([...document.querySelectorAll('#plants tbody tr')].slice(0, 3).map((r) => r.querySelector('td').childNodes[1].textContent))"));
check("sort by name", names.join("|") === [...names].sort((a, b) => a.toLowerCase() < b.toLowerCase() ? -1 : 1).join("|"), names);
await ev("(() => { const i = document.getElementById('plant-filter'); i.value = 'fort bend'; i.oninput({ target: i }); })()"); await sleep(300);
check("filter narrows the table", Number((await data()).rows) > 0 && Number((await data()).rows) < 20, (await data()).rows);
await ev("(() => { const s = document.getElementById('measure'); s.value = 'radar_days'; s.onchange(); })()"); await sleep(500);
check("radar measure disables the basis switch", (await ev("document.querySelector('#basis button').disabled")) === true && /days per year/.test(await ev("document.getElementById('legend').innerText")));
await ev("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))"); await sleep(400);
check("Escape clears the selection", ((await data()).selected || "") === "" && (await ev("document.querySelectorAll('.tag').length")) === 0);

// tabs and deep link
for (const tab of ["evidence", "crc", "methods", "risk"]) { await ev(`document.querySelector('.tab[data-tab="${tab}"]').click()`); await sleep(200); check(`tab ${tab} opens`, (await data()).tab === tab && (await ev(`!document.getElementById('tab-${tab}').classList.contains('hidden')`)) === true); }
await open(`${URL}#tab=risk&plant=${other.id}&measure=p2in&basis=1`); await sleep(1500); d = await data();
check("deep link restores plant, measure and basis", d.selected === other.id && d.measure === "p2in" && d.basis === "1", d);
await shot("n4-deep-link");

check("no console messages or script errors", messages.length === 0, messages);
writeFileSync(`${S}/smoke-next.json`, JSON.stringify({ url: URL, failures, messages }, null, 1));
ws.close(); chrome.kill();
console.log(failures.length ? `${failures.length} FAILED` : "all checks passed");
process.exit(failures.length ? 1 : 0);
