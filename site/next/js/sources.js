// Hail evidence and CRC data tabs. Placeholder until the source views are moved in.
export async function initSources() { document.getElementById("tab-sources").innerHTML = '<div class="page"><h2>Being moved into this layout</h2><p><a href="../">Open in the current explorer</a></p></div>'; }
export async function showSources(origin) { document.body.dataset.origin = origin; }
export function sourcesAddress() { return {}; }
