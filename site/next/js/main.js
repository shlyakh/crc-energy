// Texas hail risk explorer: shell. Tabs, address state, and the Risk tab. No build step.
import { $, esc, readAddress, writeAddress } from "./util.js";
import { initRisk, riskAddress } from "./risk.js";

const TABS = ["risk", "evidence", "crc", "methods"];
const DATA = "../data/";
const shell = { tab: "risk" };

// Hail evidence and CRC data are one pane (js/sources.js) showing the sources of one origin each.
const ORIGIN = { evidence: "crc-lab", crc: "crc-sdk" };
const PANE = { risk: "tab-risk", evidence: "tab-sources", crc: "tab-sources", methods: "tab-methods" };
let sources = null; // the module, loaded on first use
let address = {};

// Not moved into the new shell yet: say so, and link to where it lives today.
const PENDING = {
  methods: {
    title: "Methods",
    body: "How a plant's loss is computed from hail reports, the four damage curves with their placeholders, the data sources and the decisions taken.",
    links: [["Phase 5 report: hail impact and loss", "https://github.com/shlyakh/crc-lab/blob/main/docs/reports/5-hail-impact.md"], ["How hail data is processed", "https://github.com/shlyakh/crc-lab/blob/main/docs/hail-data-processing.md"], ["Decisions and their effect", "https://github.com/shlyakh/crc-lab/blob/main/docs/decisions.md"]],
  },
};

async function showTab(tab) {
  shell.tab = TABS.includes(tab) ? tab : "risk";
  for (const pane of new Set(Object.values(PANE))) $(pane).classList.toggle("hidden", pane !== PANE[shell.tab]);
  for (const t of TABS) document.querySelector(`.tab[data-tab="${t}"]`).setAttribute("aria-selected", String(t === shell.tab));
  document.body.dataset.tab = shell.tab;
  if (ORIGIN[shell.tab]) {
    try {
      if (!sources) { sources = await import("./sources.js"); await sources.initSources({ dataUrl: DATA, address, onChange: syncAddress }); }
      await sources.showSources(ORIGIN[shell.tab]);
      delete document.body.dataset.error;
    } catch (e) { $("tab-sources").innerHTML = `<div class="page"><h2>Could not open this tab</h2><p>${esc(e.message || e)}</p></div>`; document.body.dataset.error = String(e.message || e); }
  }
  syncAddress();
  window.dispatchEvent(new Event("resize"));
}
export function syncAddress() { writeAddress({ tab: shell.tab, ...(shell.tab === "risk" ? riskAddress() : ORIGIN[shell.tab] && sources ? sources.sourcesAddress() : {}) }); }

async function main() {
  for (const [id, p] of Object.entries(PENDING)) {
    $(`tab-${id}`).innerHTML = `<h2>${esc(p.title)}</h2><p>${esc(p.body)}</p><p class="label">Being moved into this layout</p><ul>${p.links.map(([t, h]) => `<li><a href="${h}">${esc(t)}</a></li>`).join("")}</ul>`;
  }
  for (const b of document.querySelectorAll(".tab")) b.onclick = () => showTab(b.dataset.tab);
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
}
// An address typed or pasted into an open page: start again from it (our own updates use replaceState and do not fire this).
window.addEventListener("hashchange", () => location.reload());
main();
