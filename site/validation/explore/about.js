// About (Texas CRC data explorer): a reading page built from the registry and the hand-written catalogue.
import { esc, fmtInt } from "../../shared/util.js";

const GH = "https://github.com/shlyakh/crc-lab/blob/main/";
const json = (url) => fetch(url).then((r) => { if (!r.ok) throw new Error(`${url.split("/").pop()} ${r.status}`); return r.json(); });
const done = new Set();

export async function showCrcAbout(el, dataUrl) {
  if (done.has(el.id)) return;
  const root = dataUrl.replace(/data\/?$/, "");
  const [registry, catalog, manifest] = await Promise.all([json(`${root}layers.json`), json(`${root}sources.json`), json(`${dataUrl}manifest.json`).catch(() => null)]);
  const group = registry.groups.find((g) => g.id === "crc-sdk"), shown = registry.sources.filter((s) => s.origin === "crc-sdk");
  const versions = manifest?.versions ? Object.entries(manifest.versions).map(([k, v]) => `${k} ${v}`).join(", ") : "";
  el.innerHTML = `<div class="doc-in">
    <h2>About the Texas CRC data explorer</h2>
    <p class="lead">A look at what Climate Risk Commons' SDK already reaches for Texas, shown as the SDK returns it.</p>
    <p>${esc(group.blurb)} Nothing on the Data tab is modelled here: every value is read through <code>crc-sdk</code>${versions ? ` (${esc(versions)})` : ""} and drawn as its source publishes it. The <a href="${root}hail/">Texas hail risk</a> project is new and experimental; this part is an explorer. What crc-sdk does to each source between the publisher&#39;s files and its output is checked in <a href="../">Source validation</a>.</p>
    <h3>Shown on the Data tab</h3>
    <table class="plain"><thead><tr><th>Source</th><th>What it is</th><th>Licence</th></tr></thead><tbody>
      ${shown.map((s) => `<tr><td>${esc(s.title)}</td><td>${esc(s.short || s.returns || "")}</td><td>${esc(s.licence || "")}</td></tr>`).join("")}
    </tbody></table>
    <h3>Everything crc-sdk reaches</h3>
    <p>From the SDK's own source pages for the pinned version. Texas coverage was probed on 2026-11-10.</p>
    <table class="plain"><thead><tr><th>Source</th><th>Entry point</th><th>Returns</th><th>Coverage</th><th>Licence</th></tr></thead><tbody>
      ${catalog.sources.map((s) => `<tr><td>${esc(s.name)}</td><td><code>${esc(s.entry || "")}</code></td><td>${esc(s.returns || "")}</td><td>${esc(s.coverage || "")}</td><td>${esc(s.licence || "")}</td></tr>`).join("")}
    </tbody></table>
    <h3>Reading the data</h3>
    <ul>
      <li>Cell values are regional screening: a resolution-5 cell is about 253 km².</li>
      <li>CRC Open projections are CC BY-NC 4.0: non-commercial use, with attribution.</li>
      <li>Curves are evaluated by the SDK and shipped as values; the page never re-implements a curve.</li>
    </ul>
    <p>${fmtInt(shown.length)} sources are on the map today. <a href="https://github.com/RiskThinking/crc-sdk">crc-sdk on GitHub</a> · <a href="${GH}docs/sources-track/">notes on the other sources</a></p>
  </div>`;
  done.add(el.id); document.body.dataset.crcAbout = "1";
}
