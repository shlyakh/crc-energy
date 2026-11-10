# Plan: sources track

Status: **S1 built 2026-11-10 on branch `sources-track`, awaiting review; nothing merged** · requirement IDs
refer to [requirements.md](requirements.md) · runs beside Phase 2 on `main`

## How to run this track

- Same rules as the main plan: one phase at a time, a report per phase in `docs/reports/`, never invent a
  number, stop when a source cannot be reached.
- Keep additions to `site/app.js` generic (layer kinds, not sources) and small, so the branch merges under
  Phase 2's `pmtiles-points` kind without conflict.
- Every probe is a script in `tools/probes/` whose output is quoted, not retyped.

## Phases

| Phase | Output | Requirements | Hours | Status |
| --- | --- | --- | --- | --- |
| S0 | Probes of every non-CRC-Open source against Texas; the findings table | — | 3 | done 2026-11-10 |
| S1 | Generic `points`/`lines` kinds; IBTrACS tracks, CO-OPS water levels, GHCNh station curves, ERA5 `txx` baseline at r4; data card; `just sources`; smoke test | X1–X9 | 6–8 | built 2026-11-10, awaiting review |
| S2 | USGS gauges from a Texas gauge list; CO-OPS sea-level scenarios in the station panel; more GHCNh stations (or all, in CI) | X10 | 4–6 | deferred |
| S3 | Raster sources (CHIRPS monthly, GloFAS reach) once raster reading works on the build machine or in CI; CDL crop mix with the `agriculture` extra pinned | X10 | 4–6 | deferred |

## S1 — what was done

1. `src/crc_lab/explorer/sources.py`: four builders under `site/data/sources/` (three GeoJSON layers and the
   ERA5 `h3-cells` files) and a `manifest.json` data card; `verify_ghcnh` runs `for_assets` on sampled stations.
2. `site/app.js`: `loadGeo`, `geoLayer`, `geoTooltip`, `showFeature`; source caveats appended to the caveat
   panel; a layer may carry its own `horizons` (`horizonsOf`); non-CRC-Open `h3-cells` layers get their own
   caveat text; a `crc:flyTo` test hook. The CRC Open code path is otherwise unchanged.
3. `site/layers.json`: four entries; the three GeoJSON layers `on: false`, ERA5 in the hazard selector.
4. `tests/test_sources.py`: pure-function tests on synthetic rows; registry checks.
5. `tools/smoke.mjs` (`--sources`): headless Chrome drives the page, toggles the three layers, clicks a
   station; timings in the S1 report.

Done when: the three layers toggle on without errors, a clicked CO-OPS station shows its published levels as a
curve, the GHCNh check reports 0 mismatches, `just site` passes, and the Phase 1 first-view timing is unchanged.

## S2 — USGS gauges, sea-level scenarios, more stations (deferred)

1. USGS: fetch the Texas gauge list from the USGS OGC API (`monitoring-locations`, state 48, parameter 00060),
   choose active daily-mean gauges, ship points with the period of record and the last complete year's mean,
   maximum and minimum daily flow (no fitting).
2. CO-OPS sea-level scenarios (`NOAASeaLevelPlan`, 75 rows per station) as a table in the station click panel.
3. GHCNh: the 40 first airport stations yielded 8 curves with at least 15 valid years in 2000–2024; choose
   stations by record length (the catalogue has no years for them, so probe the daily summaries first) or run
   the full `USW` set in CI (about 13 s per station).

Done when: the gauges draw with their flow summary, a CO-OPS station shows its scenarios, and the GHCNh layer
has a stated station-selection rule.

## S3 — raster sources (deferred)

Blocked on the machine (see requirements §5). CHIRPS one month at H3 r4; GloFAS at r6 for one river reach;
CDL crop mix at r4 for one year.

## Risks

| Risk | Response |
| --- | --- |
| GHCNh full airport set costs about 13 s per station (347 stations, over an hour) | Build a subset; cache is reused; a full run can go to CI |
| CO-OPS extreme-levels product exists at only 9 Texas stations | Say so on the layer; the sea-level scenarios cover more stations and could be the next table |
| Raster stack broken on the build machine | Record "could not verify"; run in CI or fix Homebrew |
