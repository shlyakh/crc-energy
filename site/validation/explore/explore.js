// Shell of the Texas CRC data explorer, the map side of the source validation project: Texas data, About.
// The map viewer (../../shared/sources.js) and the data files under ../../data/ are shared with the hail project. No build step.
import { $, esc, readAddress, writeAddress } from "../../shared/util.js";

const ROOT = "../../", DATA = `${ROOT}data/`;
const HAIL = `${ROOT}hail/`;
const TABS = {
  crc: { pane: "tab-sources", origin: "crc-sdk" },
  "crc-about": { pane: "tab-crc-about" },
};
const shell = { tab: "crc" };
let sources = null, about = null; // modules, loaded on first use
let address = {};

export async function showTab(tab) {
  shell.tab = TABS[tab] ? tab : "crc";
  const t = TABS[shell.tab];
  for (const pane of new Set(Object.values(TABS).map((x) => x.pane))) $(pane).classList.toggle("hidden", pane !== t.pane);
  for (const b of document.querySelectorAll("button.tab")) b.setAttribute("aria-selected", String(b.dataset.tab === shell.tab));
  document.body.dataset.tab = shell.tab; document.body.dataset.project = "crc";
  try {
    if (t.origin) {
      if (!sources) { sources = await import("../../shared/sources.js"); await sources.initSources({ dataUrl: DATA, address, onChange: syncAddress }); }
      await sources.showSources(t.origin);
    } else {
      if (!about) about = await import("./about.js");
      await about.showCrcAbout($(t.pane), DATA);
    }
    delete document.body.dataset.error;
  } catch (e) { $(t.pane).innerHTML = `<div class="doc-in"><h2>Could not open this view</h2><p>${esc(e.message || e)}</p></div>`; document.body.dataset.error = String(e.message || e); }
  syncAddress();
  window.dispatchEvent(new Event("resize"));
}
export function syncAddress() { writeAddress({ tab: shell.tab, ...(TABS[shell.tab].origin && sources ? sources.sourcesAddress() : {}) }); }

async function main() {
  for (const b of document.querySelectorAll("button.tab")) b.onclick = () => showTab(b.dataset.tab);
  address = readAddress();
  // An address that names a tab of the hail project: send it there with its state.
  if (["risk", "evidence", "methods"].includes(address.tab)) { location.replace(HAIL + location.search + location.hash); return; }
  await showTab(address.tab || "crc");
  document.body.dataset.ready = "1";
  // What the tour (tour.js) and the smoke test drive.
  const app = { showTab, sources: () => sources, hail: HAIL };
  globalThis.__app = app;
  // The hail project's tour hands over to this page for its last part.
  if (new URLSearchParams(location.search).get("demo") === "beryl" && !document.body.dataset.error) (await import("./tour.js")).runTour(app);
}
// An address typed or pasted into an open page: start again from it (our own updates use replaceState and do not fire this).
window.addEventListener("hashchange", () => location.reload());
main();
