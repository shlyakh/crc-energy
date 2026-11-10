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
| 1 | Explorer v1: catalogue page and Texas hazard map, eight CRC Open hazards | E1–E9 | 20–30 | in progress |
| 2 | Storm Events table and the two-source comparison | S1–S6 | 20–25 | deferred |
| 3 | Hail and gust curves in CRC | C1–C6 | 10–15 | deferred |
| 4 | Assets: solar farms; real-estate exploration | A1–A3 | 10–15 | deferred |

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

## Phase 3 — Hail and gust curves

1. Annual maxima per cell from 1996, with zeros (C1).
2. Pooling rule and its sensitivity (C2); a short note with two or three alternatives compared.
3. `HazardDataset.from_table(...)` with a fit policy; read back; evaluate at ten Texas cities (C3).
4. Add both as hazard layers through the registry (C5); data card (C6).
5. Sanity check against a published hail climatology map, by eye and by a few city values.

Done when: both datasets load through CRC's reader, `for_assets` returns values, and both layers appear beside
CRC Open's wind layer in the explorer.

## Phase 4 — Assets

1. Solar loader (A1): download the solar database, Texas subset, asset table with passthrough columns; tests.
2. Evaluate hail and gust return levels at each farm (C4); add an asset layer with a click panel (A3).
3. Real-estate exploration (A2) for Fort Bend County: load both federal sources; counts, occupancy agreement,
   point-to-footprint join rate; one map; recommendation.

Done when: Texas solar farms show in the explorer with their return levels, and the real-estate note recommends a
source with numbers behind it.

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
