// Texas hail risk explorer: shell. Tabs, address state, and the Risk tab. No build step.
import { $, esc, readAddress, writeAddress } from "./util.js";
import { initRisk, riskAddress } from "./risk.js";

const TABS = ["risk", "evidence", "crc", "methods"];
const DATA = "../data/";
const shell = { tab: "risk" };

// Tabs whose views have not moved into the new shell yet: say so, and link to where they live today.
const PENDING = {
  evidence: {
    title: "Hail evidence",
    body: "The records behind the plant figures: storm reports with the time player, hail and gust curves per cell, and hail days from four sources compared (reports, bias-corrected reports, radar hail size, radar hail signatures).",
    links: [["Open in the current explorer (Experimental new sources)", "../"]],
  },
  crc: {
    title: "CRC data",
    body: "Sources reached through crc-sdk: tropical cyclone tracks with wind extent, coastal water levels, airport station temperatures, the ERA5 baseline and the CRC Open climate projections.",
    links: [["Open in the current explorer", "../"]],
  },
  methods: {
    title: "Methods",
    body: "How a plant's loss is computed from hail reports, the four damage curves with their placeholders, the data sources and the decisions taken.",
    links: [["Phase 5 report: hail impact and loss", "https://github.com/shlyakh/crc-lab/blob/main/docs/reports/5-hail-impact.md"], ["How hail data is processed", "https://github.com/shlyakh/crc-lab/blob/main/docs/hail-data-processing.md"], ["Decisions and their effect", "https://github.com/shlyakh/crc-lab/blob/main/docs/decisions.md"]],
  },
};

function showTab(tab) {
  shell.tab = TABS.includes(tab) ? tab : "risk";
  for (const t of TABS) {
    $(`tab-${t}`).classList.toggle("hidden", t !== shell.tab);
    document.querySelector(`.tab[data-tab="${t}"]`).setAttribute("aria-selected", String(t === shell.tab));
  }
  document.body.dataset.tab = shell.tab;
  syncAddress();
  if (shell.tab === "risk") window.dispatchEvent(new Event("resize"));
}
export function syncAddress() { writeAddress({ tab: shell.tab, ...(shell.tab === "risk" ? riskAddress() : {}) }); }

async function main() {
  for (const [id, p] of Object.entries(PENDING)) {
    $(`tab-${id}`).innerHTML = `<h2>${esc(p.title)}</h2><p>${esc(p.body)}</p><p class="label">Being moved into this layout</p><ul>${p.links.map(([t, h]) => `<li><a href="${h}">${esc(t)}</a></li>`).join("")}</ul>`;
  }
  for (const b of document.querySelectorAll(".tab")) b.onclick = () => showTab(b.dataset.tab);
  const address = readAddress();
  try {
    await initRisk(DATA, address, syncAddress);
    document.body.dataset.ready = "1";
  } catch (e) {
    document.body.dataset.error = String(e.message || e);
    $("map-msg").textContent = `Could not load the plant data: ${e.message || e}`;
    $("map-msg").classList.remove("hidden");
  }
  showTab(address.tab || "risk");
}
// An address typed or pasted into an open page: start again from it (our own updates use replaceState and do not fire this).
window.addEventListener("hashchange", () => location.reload());
main();
