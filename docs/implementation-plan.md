# Implementation plan: CRC data explorer and severe-storm sources (Texas)

Status: **agreed 2026-11-10** · for a separate Claude Code effort · requirement IDs refer to
[requirements.md](requirements.md)

## How to run this effort

- Work phase by phase. Stop at the end of each phase for review; do not start the next without a go-ahead.
- Each phase ends with a short report in `docs/reports/`: what was built, what was checked, what was not.
- Read before building: `AGENTS.md`, [primers/event-sources-in-crc.md](primers/event-sources-in-crc.md), and in
  crc-sdk `docs/sources/crc-open.md`, `docs/bring-your-own-data.md`, `crc_sdk/workflows/ibtracs.py`,
  `crc_sdk/geometry/pmtiles/`.
- Never invent a number. If a source cannot be reached, say so and stop.

## Phases

| Phase | Output | Requirements | Hours | Status |
| --- | --- | --- | --- | --- |
| 0 | Repo ready; open items from requirements section 10 checked | G1 | 3 | done, reviewed 2026-11-10 |
| 1 | Explorer v1: catalogue page and Texas hazard map, eight CRC Open hazards | E1–E9 | 20–30 | built 2026-11-10, awaiting review |
| 2 | Storm Events table and the two-source comparison | S1–S6 | 20–25 | built 2026-11-10, awaiting review |
| 3 | Hail and gust curves in CRC | C1–C6 | 10–15 | built 2026-11-10, awaiting review |
| 4 | Assets, solar value, hail at the asset by local report density | A1–A4, H1–H4 | 20–30 | built 2026-11-10, awaiting review |
| 5 | Hail impact functions v0 and loss per asset | draft in PR 3 | 15–20 | proposed 2026-11-10 |

Decided 2026-11-10: Phases 2–4 do not start until Phase 1 is reviewed. Their steps stay here so the explorer
is built to take them (E5, E9), and the explorer marks hail and gust as planned.

## Phase 0 — Setup and checks

1. `uv sync`; run the pin test.
2. Confirm current `crc-sdk` and `crc-framework` versions against the pins; update pins and `CHANGELOG-upstream.md`
   if a newer release is adopted.
3. Check what Phase 1 depends on, and record each answer in the report ("could not verify" is an answer):
   - which `curve_kind` (fitted, hurdle, point_mass, tabulated, no_data) CRC Open uses for the eight hazards, so
     the browser can evaluate the curve on click (E4);
   - how many resolution-5 cells Texas has once clipped to the state polygon (the 2,700 in the requirements is an
     area estimate);
   - which horizons the release actually holds (2030, 2050, 2080 assumed);
   - MapLibre, deck.gl and pmtiles versions that work together, pinned.
   Storm Events and National Structure Inventory checks move to Phase 2 and Phase 4.
4. Bring the repo to the current scope: `pyproject.toml` (description, drop extras from the archived scope),
   `AGENTS.md`, `README.md`, `CLAUDE.md`, `docs/reports/`, a `justfile` so that G5's "one command" has a home.

Done when: `docs/reports/0-setup.md` lists each check and its answer.

Conventions fixed in Phase 0:

- **Texas is a polygon, not a box.** `for_area()` takes a bounding box, which also covers parts of New Mexico,
  Oklahoma, Louisiana and Mexico. Clip cells with the Census TIGER state boundary (`cb_2024_us_state_500k`):
  keep every resolution-5 cell that **intersects** the state polygon (2,564 cells; decided 2026-11-10 so the
  borders are covered), not only cells whose centre lies inside (2,384).
- **Curves are evaluated in Python, not in JavaScript.** CRC Open mixes `hurdle`, `fitted`, `point_mass`,
  `tabulated` and `no_data` rows in every hazard (Phase 0 report). The data build calls
  `crc_sdk.workflows.distributions.curve_quantiles` at return periods 2, 5, 10, 20, 50, 100, 200 and 500 years
  and ships the values with the raw parameters; the browser draws a polyline and interpolates. Decided
  2026-11-10; the "no API" decision stands.
- **No front-end build step.** One `site/index.html` with ES modules from pinned CDN versions (MapLibre GL,
  deck.gl's `H3HexagonLayer`, the pmtiles protocol), in the same style as the D0 explainers. The folder publishes
  unchanged to GitHub Pages and to the container.
- **Paths across cells** (S3, later) are already covered: `polyfill_wkb` handles LineStrings. Do not write a new one.
- **One command** is `just all` (`just data`, `just site` underneath); each phase adds its targets.

## Phase 1 — Explorer v1

1. **Catalogue data.** Call `HazardDataset.crc_open().catalog()`; write `catalog.json` with every hazard's
   unit, semantics, horizons, resolution, licence. Add a hand-written table of other crc-sdk sources.
2. **Hazard values for Texas.** Choose eight hazards across families (suggested: `tx_max`, `tn_min`, `rx1day`,
   `rflood`, `wind_max_daily_max`, `fwi`, `spei`, `hot_days`). For each: every Texas cell, three horizons, return
   periods 10, 50, 100, plus curve parameters. One compact file per hazard. Horizons 2030, 2050 and 2080 (the
   release runs 2025–2090). The selector lists all 63 hazards; the other 55 are marked "not loaded yet". The
   "not in CRC Open" list shows hail and thunderstorm gust as "planned (Phase 3)".
3. **Layer registry.** One file describing each layer: id, title, source, unit, licence, file, colour scale.
4. **Page.** MapLibre base map; deck.gl H3 layer for cells; selectors for hazard, horizon, return period; legend;
   click panel with the curve; layer switcher; caveat panel; catalogue tab.
5. **Performance check** against E7; record the numbers.
6. **Deployment.** One container serving the static site; `docker compose up` on a server; the same files publish
   to GitHub Pages.

Done when: the page loads for Texas, all eight hazards switch within the time limit, a clicked cell shows a curve
that matches `for_assets` at the cell centre, and the catalogue lists all hazards in the release.

Report: [reports/1-explorer.md](reports/1-explorer.md).

Decided: curve values at fixed return periods (and the parameters) are shipped to the browser; no API in
version 1. The "matches `for_assets` at the cell centre" test compares the shipped values with a fresh
`for_assets` call at the same return periods.

## Phase 2 — Storm Events

1. **Fetch plan** (S1): list the NCEI folder, latest file per year, cache, checksums, manifest.
2. **Parser** (S2): hail and thunderstorm wind in full; other types passed through; unit conversions; damage
   strings; UTC times. Tests on fixed sample files.
3. **Geometry and cells** (S3).
4. **Event table and data card** (S4).
5. **Two-source comparison** (S5): load the Source Cooperative file; run the seven comparisons of requirements
   section 4.1 for Texas; write the report with tables and three maps.
6. **Explorer layer** (S6): events as PMTiles points; filters for type and year.

Done when: yearly row counts match the NCEI files; the comparison report exists; the Fort Bend County hail of
15 March 2024 is found with its size and place; events show in the explorer.

Report: [reports/2-storm-events.md](reports/2-storm-events.md); comparison:
[reports/2-storm-events-comparison.md](reports/2-storm-events-comparison.md). Built 2026-11-10 in parallel with
the sources track (branch `sources-track`, `docs/sources-track/`), at Yuri's request.

## Phase 3 — Hail and gust curves

1. Annual maxima per cell from 1996, with zeros (C1).
2. Pooling rule and its sensitivity (C2); a short note with two or three alternatives compared.
3. `HazardDataset.from_table(...)` with a fit policy; read back; evaluate at ten Texas cities (C3).
4. Add both as hazard layers through the registry (C5); data card (C6).
5. Sanity check against a published hail climatology map, by eye and by a few city values.

Done when: both datasets load through CRC's reader, `for_assets` returns values, and both layers appear beside
CRC Open's wind layer in the explorer.

Report: [reports/3-curves.md](reports/3-curves.md); sensitivity: [reports/3-curves-sensitivity.md](reports/3-curves-sensitivity.md).

## Phase 4 — Assets and hail at the asset

Revised 2026-11-10 after the hail impact draft (`docs/requirements-hail-impact-v0.md`, PR 3) and Yuri's two
decisions: hail exposure by local report density, and a value source for solar plants from capacity.
Built 2026-11-10; report: [reports/4-assets.md](reports/4-assets.md).

1. Solar loader (A1): download the solar database, Texas subset, asset table with passthrough columns
   (capacity, year, mounting type, array boundary); tests.
2. Solar value source (A4): replacement value = capacity × installed cost per watt for the plant's year and
   mounting type, from a published cost series (candidates to check: Berkeley Lab "Utility-Scale Solar" annual
   data file; NREL Annual Technology Baseline). The series, its vintage and the dollar year are recorded in the
   asset table; no cost number is typed in.
3. Hail at the asset (H1–H4), the step the impact draft leaves open:
   - **Rule.** Around each asset, grow a circle until it holds N located hail reports from the window
     (1996 to the last complete year). The reports inside give the local size distribution; N over the circle's
     area and the years gives the local report rate per km² per year (a nearest-neighbour density estimate).
   - **Guards.** A minimum radius, because in cities the circle collapses to about 2 km and the rate then
     measures population, not hail; a maximum radius, beyond which the asset is flagged "too few reports".
   - **From rate to the asset.** A report is a point; the chance that hail of that size reached the asset needs
     an area per report (a footprint). That area is a placeholder to be stated and varied, not hidden.
   - **Sensitivity.** N, the two guards and the footprint, at the ten cities and at the solar plants, in the
     style of the Phase 3 note.
4. Evaluate hail and gust return levels at each farm (C4) from the Phase 3 curves, beside the density-based
   numbers; add an asset layer with a click panel (A3).
5. Real-estate exploration (A2) for Fort Bend County: load both federal sources; counts, occupancy agreement,
   point-to-footprint join rate; one map; recommendation.

Done when: Texas solar farms show in the explorer with value, local hail rate and size distribution, and
return levels; the exposure sensitivity note exists; and the real-estate note recommends a source with
numbers behind it.

Measured before writing this step (located hail reports 1996–2025, 39,624 in Texas):

| Place | Radius to reach 30 / 100 / 300 reports (km) | Reports within 10 km |
| --- | --- | --- |
| Amarillo | 2.4 / 2.5 / 6.7 | 498 |
| Fort Worth | 1.9 / 3.8 / 13.4 | 191 |
| Houston | 3.0 / 6.3 / 26.8 | 110 |
| Midland | 0.3 / 6.1 / 24.2 | 167 |
| Fort Bend solar area | 18.6 / 33.3 / 50.2 | 13 |
| Corpus Christi | 10.5 / 27.0 / 71.0 | 29 |
| El Paso | 10.4 / 27.7 / 261.4 | 28 |
| Presidio (remote) | 65.1 / 95.3 / 125.9 | 10 |

Corrected 2026-11-10: the first version of this table used DuckDB's `ST_Distance_Sphere` with longitude and
latitude in the wrong order and understated most radii; these are great-circle distances from the Phase 4 code.
The spread is the reporting bias: city centres reach 100 reports inside 3 to 6 km, rural sites need 27 to 95 km.
Suggested start: N = 100, minimum radius 10 km, maximum 75 km; to be confirmed by the sensitivity run.

## Phase 5 — Hail impact functions v0

From `docs/requirements-hail-impact-v0.md`. Checked against the pins on 2026-11-10: every test vector in the
draft reproduces; crc-framework's `SigmoidImpact` is a logistic (midpoint, steepness), so the Swiss curves are
callables; `PiecewiseLinearImpact` fits the solar breakage tables; crc-sdk's impact context carries only
country, continent, building type and historic mean, so glass class, stow and roof class are applied in this
repo's code; CRC has no hail factor yet.

1. Parameter file (the draft's JSON block) and a validating loader.
2. The three functional forms and four curve callables, free of CRC imports; tests from the draft's vectors,
   plus monotonicity and bounds on a fine grid.
3. Loss per asset from the Phase 4 hail exposure: expected annual damage ratio and loss in dollars (solar:
   value from A4), with the building baseline and roof sensitivity reported as a range.
4. Several hail events in one year at one asset: damage ratios are added and the year's total is capped at 1
   (the plant cannot lose more than its value in a year). Decided 2026-11-10.
5. Register with CRC where the form fits (`value_semantics="damage ratio"`, a hazard factor named
   `hail_diameter_obs_mm`); explorer: loss on the asset click panel.

Done when: the vectors pass, each Texas solar plant has an expected annual hail loss with its assumptions
listed, and the report states which numbers rest on placeholders.

Decided 2026-11-10: curve data and code stay in this repo, written so they can be offered to crc-sdk later
(no crc-lab imports in the curve module, parameters in one data file, metadata on every curve, tests from
published vectors). Open before Phase 5: the placeholder defaults; baseline versus range for buildings; cars
have no asset set.

## After this effort

MRMS radar hail and its comparison with the report-based curves; hail and gust damage curves for solar modules
and buildings (researched separately; added when that research is in); loss results; a proposal upstream for the Storm Events plan and the event-table schema.

## Risks

| Risk | Response |
| --- | --- |
| Report-based curves mostly reflect where people live | Pooling, sensitivity checks, a plain warning in the layer; MRMS as the next step |
| CRC releases change during the build | Pins; rerun Phase 1 step 1 after any upgrade |
| Source Cooperative file lacks the columns needed for comparison | Report what can be compared; ask Earth Genome |
| Building data too large for the first map | One county only in this effort |
