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

| Phase | Output | Requirements | Hours |
| --- | --- | --- | --- |
| 0 | Repo ready; open items from requirements section 10 checked | G1 | 3 |
| 1 | Explorer v1: catalogue page and Texas hazard map | E1–E9 | 20–30 |
| 2 | Storm Events table and the two-source comparison | S1–S6 | 20–25 |
| 3 | Hail and gust curves in CRC | C1–C6 | 10–15 |
| 4 | Assets: solar farms; real-estate exploration | A1–A3 | 10–15 |

## Phase 0 — Setup and checks

1. `uv sync`; run the pin test.
2. Confirm current `crc-sdk` and `crc-framework` versions against the pins; update pins and `CHANGELOG-upstream.md`
   if a newer release is adopted.
3. Check the items listed as not verified: Storm Events format PDF (magnitude types, coverage by year); National
   Structure Inventory access and licence; deck.gl and MapLibre versions.
4. Update `AGENTS.md` and `README.md` to the new scope.

Done when: a one-page report lists each check and its answer.

## Phase 1 — Explorer v1

1. **Catalogue data.** Call `HazardDataset.crc_open().catalog()`; write `catalog.json` with every hazard's
   unit, semantics, horizons, resolution, licence. Add a hand-written table of other crc-sdk sources.
2. **Hazard values for Texas.** Choose eight hazards across families (suggested: `tx_max`, `tn_min`, `rx1day`,
   `rflood`, `wind_max_daily_max`, `fwi`, `spei`, `hot_days`). For each: every Texas cell, three horizons, return
   periods 10, 50, 100, plus curve parameters. One compact file per hazard. Horizons 2030, 2050 and 2080 (the
   release runs 2025–2090). The selector lists all 63 hazards; the other 55 are marked "not loaded yet".
3. **Layer registry.** One file describing each layer: id, title, source, unit, licence, file, colour scale.
4. **Page.** MapLibre base map; deck.gl H3 layer for cells; selectors for hazard, horizon, return period; legend;
   click panel with the curve; layer switcher; caveat panel; catalogue tab.
5. **Performance check** against E7; record the numbers.
6. **Deployment.** One container serving the static site; `docker compose up` on a server; the same files publish
   to GitHub Pages.

Done when: the page loads for Texas, all eight hazards switch within the time limit, a clicked cell shows a curve
that matches `for_assets` at the cell centre, and the catalogue lists all hazards in the release.

Decided: curve parameters are shipped to the browser; no API in version 1.

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
