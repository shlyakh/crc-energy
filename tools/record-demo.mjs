// Record the page's own demo (?demo=1) to site/demo.webm with headless Chrome and ffmpeg (no npm dependencies).
//   python3 -m http.server 8770 --bind 127.0.0.1 --directory site   (in another shell)
//   node tools/record-demo.mjs <work dir> [url] [output]
// Takes JPEG screenshots as fast as the browser gives them, keeps each frame's real timestamp, and lets
// ffmpeg's concat demuxer hold every frame for its true duration, so the video runs at the demo's speed.
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";

const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const [S, URL = "http://127.0.0.1:8770/", OUT = "site/demo.webm"] = process.argv.slice(2);
const port = 9335; const frames = `${S}/frames`;
rmSync(frames, { recursive: true, force: true }); mkdirSync(frames, { recursive: true });
const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox", `--remote-debugging-port=${port}`, `--user-data-dir=${S}/rec-profile`, "--window-size=1280,800", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let version; for (let i = 0; i < 50 && !version; i++) { try { version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(); } catch { await sleep(200); } }
const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map();
ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async (expression) => (await send("Runtime.evaluate", { expression, returnByValue: true })).result?.result?.value;
await send("Page.enable"); await send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
await send("Page.navigate", { url: URL + "?demo=1" });
const t0 = Date.now(); const stamps = []; let started = false;
while (Date.now() - t0 < 60000) {
  const st = await evaluate("document.body ? (document.body.dataset.demo || '') : ''");
  if (st === "running") started = true;
  if (started) {
    const r = await send("Page.captureScreenshot", { format: "jpeg", quality: 80 });
    const name = `f${String(stamps.length).padStart(5, "0")}.jpg`; writeFileSync(`${frames}/${name}`, Buffer.from(r.result.data, "base64")); stamps.push([name, Date.now()]);
  } else await sleep(50);
  if (started && st && st !== "running") break;
}
ws.close(); chrome.kill();
const list = stamps.map(([name, t], i) => `file '${name}'\nduration ${(((stamps[i + 1] || [0, t + 200])[1] - t) / 1000).toFixed(3)}`).join("\n") + `\nfile '${stamps[stamps.length - 1][0]}'\n`;
writeFileSync(`${frames}/list.txt`, list);
const seconds = (stamps[stamps.length - 1][1] - stamps[0][1]) / 1000;
console.log(JSON.stringify({ frames: stamps.length, seconds, fps: stamps.length / seconds }));
const ff = spawnSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", `${frames}/list.txt`, "-vf", "fps=12,scale=1280:-2", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "40", "-pix_fmt", "yuv420p", OUT], { stdio: "inherit" });
console.log(JSON.stringify({ ffmpeg_exit: ff.status, output: OUT }));
