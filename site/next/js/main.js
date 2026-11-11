// Shell for two projects on one page: "Texas hail risk" (new work: Risk, Hail evidence, Methods) and
// "Texas CRC data" (an explorer of the sources crc-sdk already reaches: Data, About). No build step.
import { $, esc, readAddress, writeAddress } from "./util.js";
import { initRisk, riskAddress, select as selectPlant, setBasis, setMeasure } from "./risk.js";

const DATA = "../data/";
// tab -> its project, the pane it shows and, for the two source tabs, the origin of the sources listed
const TABS = {
  risk: { project: "hail", pane: "tab-risk" },
  evidence: { project: "hail", pane: "tab-sources", origin: "crc-lab" },
  methods: { project: "hail", pane: "tab-methods" },
  crc: { project: "crc", pane: "tab-sources", origin: "crc-sdk" },
  "crc-about": { project: "crc", pane: "tab-crc-about" },
};
const FIRST = { hail: "risk", crc: "crc" };
const shell = { tab: "risk", last: { ...FIRST } };
let sources = null, methods = null; // modules, loaded on first use
let address = {};

export async function showTab(tab) {
  shell.tab = TABS[tab] ? tab : "risk";
  const t = TABS[shell.tab]; shell.last[t.project] = shell.tab;
  for (const pane of new Set(Object.values(TABS).map((x) => x.pane))) $(pane).classList.toggle("hidden", pane !== t.pane);
  for (const b of document.querySelectorAll(".tab")) { b.classList.toggle("hidden", b.dataset.project !== t.project); b.setAttribute("aria-selected", String(b.dataset.tab === shell.tab)); }
  for (const b of document.querySelectorAll(".proj")) b.setAttribute("aria-selected", String(b.dataset.project === t.project));
  document.body.dataset.tab = shell.tab; document.body.dataset.project = t.project;
  document.title = t.project === "hail" ? "Texas hail risk explorer" : "Texas CRC data explorer";
  try {
    if (t.origin) {
      if (!sources) { sources = await import("./sources.js"); await sources.initSources({ dataUrl: DATA, address, onChange: syncAddress }); }
      await sources.showSources(t.origin);
    } else if (t.pane !== "tab-risk") {
      if (!methods) methods = await import("./methods.js");
      await (shell.tab === "methods" ? methods.showMethods($(t.pane), DATA) : methods.showCrcAbout($(t.pane), DATA));
    }
    delete document.body.dataset.error;
  } catch (e) { $(t.pane).innerHTML = `<div class="doc-in"><h2>Could not open this tab</h2><p>${esc(e.message || e)}</p></div>`; document.body.dataset.error = String(e.message || e); }
  syncAddress();
  window.dispatchEvent(new Event("resize"));
}
export function syncAddress() { writeAddress({ tab: shell.tab, ...(shell.tab === "risk" ? riskAddress() : TABS[shell.tab].origin && sources ? sources.sourcesAddress() : {}) }); }

async function main() {
  for (const b of document.querySelectorAll(".tab")) b.onclick = () => showTab(b.dataset.tab);
  for (const b of document.querySelectorAll(".proj")) b.onclick = () => showTab(shell.last[b.dataset.project]);
  address = readAddress();
  try {
    await initRisk(DATA, address, syncAddress);
    document.body.dataset.ready = "1";
  } catch (e) {
    document.body.dataset.error = String(e.message || e);
    $("risk-msg").textContent = `Could not load the plant data: ${e.message || e}`;
    $("risk-msg").classList.remove("hidden");
  }
  await showTab(address.tab || "risk");
  // What the tour (js/demo.js) and the smoke test drive.
  const app = { showTab, selectPlant, setBasis, setMeasure, sources: () => sources };
  globalThis.__app = app;
  const tour = async () => { const demo = await import("./demo.js"); demo.runDemo(app); };
  $("demo-start").onclick = tour;
  if (new URLSearchParams(location.search).get("demo") === "1" && document.body.dataset.ready) tour();
}
// An address typed or pasted into an open page: start again from it (our own updates use replaceState and do not fire this).
window.addEventListener("hashchange", () => location.reload());
main();
