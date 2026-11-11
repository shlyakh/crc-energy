# Plan: explorer redesign (Phase 6) — "Texas hail risk explorer"

Approved by Yuri 2026-11-10 after a question round; replaces the earlier draft list. **Status: done.** Swapped to the main address on 2026-11-11; report: [reports/6-explorer-redesign.md](reports/6-explorer-redesign.md)
(live at `/crc-lab/next/`; the current explorer is untouched until the swap). One change from the plan as
approved: plants under 20 MW are hidden by default (Yuri, 2026-11-10), with the count stated in the table head, the
legend and the note, and a selector to show them; class breaks and measures live in the generated `site/data/assets/plants.json`, not in the registry.

Changed by Yuri on 2026-11-11: the page holds **two projects**, switched at the top left. "Texas hail risk" (new work:
Risk, Hail evidence, Methods) and "Texas CRC data" (an explorer of what crc-sdk already reaches: Data, About).
This replaces the single row of four tabs in the table below.

## Context

The explorer grew one feature at a time and reads as amateur: nine sources listed as equals, controls below
the fold, a 46-line plant panel, no legend or scale on the map, no highlight on the selected plant, and loss
(Phase 5) invisible until a plant is clicked. Yuri wants the next phase to be a UI redesign. Decisions below
were settled in a question round on 2026-11-10.

## Decisions (from the question round)

| Topic | Decision |
| --- | --- |
| Main job | Hail risk at solar plants; the page opens there |
| Reader | Risk engineer / analyst: dense, exact, units and assumptions visible |
| Tabs | **Risk · Hail evidence · CRC data · Methods** |
| Risk layout | Ranked plant table left, map centre, plant detail right; all three in sync |
| Plant symbols | Size = capacity (MW); colour = loss as % of value per year by default; selector for other measures |
| Bias | One global switch "Reports as they are / Bias-corrected", default uncorrected; table and detail always print both; warning mark where the correction factor is above 5 |
| On the map | Legend with numeric class breaks and units, scale bar, cursor coordinates, data period; selection ring + label + array outline + report circle with its reports; hover readout and zoom-dependent labels. **No** hazard underlay under plants |
| Look | Technical light: thin rules, small caps labels, tabular numbers, muted basemap, colour for data only |
| Plant detail | Headline figures, three small charts (hail sizes in circle; damage curve with reports marked; reports / corrected / radar bars), other groups collapsed; assumptions marked "reported" or "placeholder" |
| Other tabs | New shell and map furniture (compact source picker, legends, hover, highlight); features unchanged |
| Screens | Designed for ≥1280 px; table becomes a drawer at 900–1280 px; no phone layout |
| Methods | About, sources, "from reports to loss at a plant" with a diagram, the four damage curves with a stow slider |
| Demo | Rewritten around the risk story, re-recorded at the end |
| Delivery | Built at `site/next/` on main, live at `/crc-lab/next/`; three review stops; then swapped to the root |
| Title | "Texas hail risk explorer · built on Climate Risk Commons" |

Choices made without asking (say if any is wrong):

- Still a static site with no build step and libraries pinned by URL. The code is split into ES modules.
- Curves are still never computed in the browser. The stow slider picks among curves precomputed in Python
  (a grid of stow angles and stow chances shipped as values).
- The current view is kept in the address (tab, source, plant, switch) so a view can be linked.
- Open questions 1–3 are settled by this plan as suggested: own-range scale in one-source view, shared scale in
  swipe; ratio opens on radar ÷ reports with "radar ÷ corrected" one click away; comparison is in the new demo.
- Colours use class breaks (5–6 classes), not a continuous ramp, so the legend can print exact ranges.

## Technical approach

**What exists** (`site/`, surveyed): one 1,100-line ES module `app.js` tied to fixed DOM ids; MapLibre 6.16 ESM
plus deck.gl 9.4 through `MapboxOverlay` (not interleaved); continuous OKLCH colour ramps with no class breaks;
legends only in the sidebar; no scale bar; deck's default text tooltip; no selection highlight for points or
cells; plants drawn by the generic `geoLayer` as identical 5 px dots. The whole `site/` folder is published,
so `site/next/` appears at `/next/` with no workflow change.

**Structure of `site/next/`** (ES modules, no build step, same pinned libraries, data read from `../data/`):

- `index.html`, `style.css` (design tokens: spacing scale, type scale, rules, one accent, data palettes)
- `js/main.js` (tabs, address state), `js/state.js`, `js/map.js` (map, overlay, `ScaleControl`, coordinates,
  hover box, selection layer), `js/legend.js` (on-map legend from class breaks), `js/scale.js` (class breaks,
  palettes, formatters with units), `js/charts.js` (SVG charts that take a target element)
- `js/risk.js` (table, plant layers, detail), `js/evidence.js` and `js/crcdata.js` (source picker + the existing
  per-kind views), `js/methods.js`, `js/demo.js`
- `js/views/` — the existing renderers moved over largely as they are: tracks and wind swaths, events and the
  player/timeline, h3 cells, h3-compare, stations.

**Reused from `site/app.js`**: the pure helpers (`parseColor`, `ramp`, `colorAt`, `fmt`, `quantile`, `esc`, time
helpers, swath geometry `radiusAt`/`ringAt`/`fixAt`, `divergingAt`, `hoverChart`); the per-kind layer builders
and loaders, changed only so they return legend and status data instead of writing to fixed ids; `drawCurve` /
`drawSeries`, changed to take a target element; the registry `site/layers.json` (kept as the single
declaration, with a `tab` on each source and a `risk` block for the plant measures and class breaks).

**New data, built in Python** (committed like the other plant files; new module `src/crc_lab/explorer/risk_layer.py`,
run from `just impacts`):

- `site/data/assets/solar_tx.geojson`: numeric fields for every map measure and table column (loss ratio and
  dollars on both bases, correction factor, chance of 2-inch hail, radar hail days, capacity, value).
- `site/data/assets/solar_tx_detail.json`: per plant, the report circle (radius, share inside the region), the
  reports inside it (lon, lat, size), the array outline (from `geometry_wkb` in `assets/solar.py`, simplified),
  the plant's damage curve as values, and hail days from reports / corrected / radar. Reuses
  `exposure.local_reports`, `impacts.build.plant_parameters` and `hail_curves.pv_plant_hail`.
- `site/data/methods/curves.json`: the four v0 curves and the solar curve on a grid of stow angles and stow
  chances, from `hail_curves`, with the placeholder list from `hail_v0.json`.
- Class breaks for each measure are computed in Python (rounded quantile breaks) and stored in the registry, so
  the legend, the map and the reports use the same ranges.

**Risk tab behaviour**: one selection state shared by table row, map and detail; selecting flies to the plant,
draws ring, label, outline, circle (radius and report count labelled) and its reports sized by hail size;
`Esc` clears. The measure selector and the bias switch recolour the dots, re-sort the table and update the
legend and the totals line. Hover shows name, MW and the current measure with its unit.

## Stops

1. **Shell and Risk map.** `site/next/` skeleton, tokens and styles, four tabs, Risk tab map with sized and
   coloured plants, on-map legend, scale bar, coordinates, hover readout, selection ring, array outline, report
   circle with reports. Data additions built in Python.
2. **Risk table and detail; other tabs.** Ranked sortable table with totals, bias switch, detail column with
   headline and three charts, collapsed groups; Hail evidence and CRC data tabs moved into the shell with the
   compact source picker and the same map furniture; deep links.
3. **Methods, demo, swap.** Methods sections and curves page; new demo and recording; smoke test rewritten;
   `site/next/` becomes `site/`; old page deleted; docs and report `docs/reports/6-explorer-redesign.md`.

## Verification

- `just test`, `just lint`: new offline tests for `risk_layer.py` (every plant has the numeric fields; circle
  report counts equal `reports_in_circle` in the loss table; class breaks increase and cover the data; curve
  grid equals `hail_curves` at the spec's test vectors) and for the extended registry.
- `tools/smoke.mjs` gets a second script for `/next/` (the old one keeps guarding the live page until the
  swap): opens each tab, checks the legend text contains numeric ranges and a unit, selects a plant from the
  table and from the map and checks ring, circle and detail agree, flips the bias switch and checks the totals
  line changes from the uncorrected to the corrected total of the Phase 5 report, sorts the table, walks every
  source in the other two tabs, opens a deep link, and fails on any console message.
- Screenshots at 1440×900 and 1100×800 at each stop, looked at before reporting.
- The colour classes are run through the palette validator of the dataviz skill.
- At the swap: `check_site.py` and the registry tests updated to the new file names; old smoke script and old
  `app.js` removed; `tools/record-demo.mjs` re-records `site/demo.webm`; Pages deploy checked live.

## Out of scope

Hazard underlay beneath plants (declined), phone layout, radar swath playback, buildings, redesign of the
storm player and comparison features, any change to the loss numbers.
