// Shell of the Texas hail risk page: Risk, Hail evidence, Methods. No build step.
// The map viewer (../shared/sources.js) and the data files under ../data/ are shared with the Texas CRC data explorer.
import { $, esc, readAddress, writeAddress } from "../shared/util.js";
import { initRisk, riskAddress, select as selectPlant, setBasis, setMeasure } from "./risk.js";

const ROOT = "../", DATA = `${ROOT}data/`;
export const EXPLORER = `${ROOT}validation/explore/`;
// tab -> the pane it shows and, for the source tab, the origin of the sources listed
const TABS = {
  risk: { pane: "tab-risk" },
  evidence: { pane: "tab-sources", origin: "crc-lab" },
  methods: { pane: "tab-methods" },
};
const shell = { tab: "risk" };
let sources = null, methods = null; // modules, loaded on first use
let address = {};

export async function showTab(tab) {
  shell.tab = TABS[tab] ? tab : "risk";
  const t = TABS[shell.tab];
  for (const pane of new Set(Object.values(TABS).map((x) => x.pane))) $(pane).classList.toggle("hidden", pane !== t.pane);
  for (const b of document.querySelectorAll(".tab")) b.setAttribute("aria-selected", String(b.dataset.tab === shell.tab));
  document.body.dataset.tab = shell.tab; document.body.dataset.project = "hail";
  try {
    if (t.origin) {
      if (!sources) { sources = await import("../shared/sources.js"); await sources.initSources({ dataUrl: DATA, address, onChange: syncAddress }); }
      await sources.showSources(t.origin);
    } else if (shell.tab === "methods") {
      if (!methods) methods = await import("./methods.js");
      await methods.showMethods($(t.pane), DATA);
    }
    delete document.body.dataset.error;
  } catch (e) { $(t.pane).innerHTML = `<div class="doc-in"><h2>Could not open this tab</h2><p>${esc(e.message || e)}</p></div>`; document.body.dataset.error = String(e.message || e); }
  syncAddress();
  window.dispatchEvent(new Event("resize"));
}
export function syncAddress() { writeAddress({ tab: shell.tab, ...(shell.tab === "risk" ? riskAddress() : TABS[shell.tab].origin && sources ? sources.sourcesAddress() : {}) }); }

async function main() {
  for (const b of document.querySelectorAll(".tab")) b.onclick = () => showTab(b.dataset.tab);
  address = readAddress();
  // An address from before the split that names a tab of the data explorer: send it there with its state.
  if (address.tab === "crc" || address.tab === "crc-about") { location.replace(EXPLORER + location.search + location.hash); return; }
  try {
    await initRisk(DATA, address, syncAddress);
    document.body.dataset.ready = "1";
  } catch (e) {
    document.body.dataset.error = String(e.message || e);
    $("risk-msg").textContent = `Could not load the plant data: ${e.message || e}`;
    $("risk-msg").classList.remove("hidden");
  }
  await showTab(address.tab || "risk");
  // What the tour (demo.js) and the smoke test drive.
  const app = { showTab, selectPlant, setBasis, setMeasure, sources: () => sources, explorer: EXPLORER };
  globalThis.__app = app;
  const tour = async () => { const demo = await import("./demo.js"); demo.runDemo(app); };
  $("demo-start").onclick = tour;
  if (new URLSearchParams(location.search).get("demo") === "1" && document.body.dataset.ready) tour();
}
// An address typed or pasted into an open page: start again from it (our own updates use replaceState and do not fire this).
window.addEventListener("hashchange", () => location.reload());
main();
