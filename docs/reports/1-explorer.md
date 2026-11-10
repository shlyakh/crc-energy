# Phase 1 report: explorer v1

Date: 2026-11-10 · crc-sdk 0.11.1 · crc-framework 0.6.0 · CRC Open release `ssp585-global-2026-10-20-v1` ·
awaiting review before Phase 2.

## What was built

- **Data build** (`src/crc_lab/explorer/`, `just data`): the release catalogue as `site/data/catalog.json` (E1);
  the Texas outline and the H3 cells intersecting it; one file per hazard and horizon under `site/data/hazards/`
  with each cell's curve evaluated by crc-sdk at return periods 2, 5, 10, 20, 50, 100, 200 and 500 years plus the
  raw curve parameters (E3, E4); a `manifest.json` data card (G2: release, licence, attribution, versions, cell
  rule, per-hazard curve kinds, warnings, verification results). About 46 s on a laptop, 14.5 MB of JSON
  (r5 hazards 0.3 MB per horizon, river flood 2.5 MB; gzipped 87 KB and 524 KB).
- **Page** (`site/`, no build step): MapLibre basemap (OpenFreeMap Positron), deck.gl `H3HexagonLayer` for cells,
  selectors for hazard (all 63 listed, 8 loaded, 55 marked "not loaded yet", 4 planned layers disabled), horizon
  and return period, legend (2nd–98th percentile, lockable), layer toggles (E5), caveat panel (E6), click panel
  with the curve, value table and raw parameters (E4), catalogue tab with the 63 hazards, the other crc-sdk sources
  and a "not in CRC Open" list (E1, E2). Layers are entries in `site/layers.json` (E9).
- **Deployment** (E8): `Dockerfile` + `Caddyfile` + `compose.yaml` (`just up`); `.github/workflows/pages.yml`
  builds the data in CI, runs the `for_assets` check, and publishes `site/` to GitHub Pages.
- **Tests**: 8 offline tests (`tests/test_explorer.py`) for cell selection, atomic writes, rounding, parameter
  encoding, the tabulated-curve rule and the registry; the pin test still passes.

## Checks

| # | Check | Result |
| --- | --- | --- |
| 1 | Shipped values equal `for_assets` (the "done" test) | **Pass.** 5 random cells × 3 horizons × 8 return periods per hazard: 120 values each, 960 in all, 0 mismatches at relative tolerance 1e-5 (`just verify`; recorded in `manifest.json`). |
| 2 | E7, first view under 2 s | **402 ms** to a drawn map in headless Chrome (software WebGL) against a local server, 369 ms of it loading `tx_max/2050.json`; the eight CDN script and style files add their own fetch on a cold cache (deck.gl is 2 MB). |
| 3 | E7, hazard switch under 0.5 s | **8–51 ms** once a file is cached; river flood (16,892 r7 cells) 51 ms after a 27 ms local load. Other horizons of the current hazard are prefetched after the first view. |
| 4 | Cell count after clipping | 2,566 r5 cells intersect Texas (Phase 0 said 2,564 from a slightly different run; every one has a curve for all eight r5 hazards). 118,482 r7 cells intersect, of which 16,892 carry a river flood curve (rflood covers river corridors only). |
| 5 | Curve kinds in Texas | r5 hazards: `hurdle` and `fitted` (Gumbel) only; `fwi` is all fitted. `rflood`: 48,075 hurdle, 1,104 point-mass, 1,489 tabulated, 8 fitted (GEV) over three horizons; no `no_data` rows in Texas for the eight hazards. |
| 6 | Tabulated curves | crc-sdk refuses to evaluate a tabulated curve outside its knots (`ValueError`); the 1,489 rflood tabulated rows have knots at 0.996–0.999 only, so return periods 2–200 give no value for them (10,423 nulls, shown grey and explained in the caveat panel); `for_assets` raises on such a cell, so the verification samples skip them. |
| 7 | Catalogue tail field | All 63 hazards declare `tail: upper`, including `tn_min` (coldest night) and `spei`. The page follows the catalogue; a "1 in 100 years" coldest night is therefore the warm end of that distribution. Worth a question upstream. |
| 8 | Browser libraries | maplibre-gl 6.16.0 ships ESM only (`dist/maplibre-gl.mjs`, no default export); deck.gl 9.4.0's standalone bundle needs h3-js loaded first as a global (`h3-js@4.5.0/dist/h3-js.umd.js`). The smoke test runs the page in headless Chrome over the DevTools protocol: no script errors; the click panel and catalogue render. |
| 9 | Licence and attribution | CRC Open: CC BY-NC 4.0 with the release attribution on every view and in the map attribution; basemap credit to OpenFreeMap, OpenMapTiles and OpenStreetMap; Census boundary public domain. |

## Decisions taken during the build

- One hazard layer is shown at a time (the registry still lists all; the toggles show the active hazard and the
  boundary; planned layers appear disabled).
- Temperatures are displayed in °C (registry `display.offset`), the source unit K is shown in the panel.
- The colour scale is one hue per hazard, light to dark, built in OKLCH at run time; 2nd–98th percentile of the
  current view, lockable for comparisons across horizons or return periods.
- Values are rounded to six significant digits in the files.

## Not done / for review

- Pages: the first workflow run succeeded (2026-11-10, run 42854310771); the site is at
  https://shlyakh.github.io/crc-lab/ with the data built in CI (verification 0 mismatches) and the explainers at
  `/explainers/`. Pages was switched from the legacy `main:/docs` build to the workflow build.
- E7 from the Pages URL, same headless Chrome: first view **183 ms** after the scripts load (page wall time 2.9 s on
  a cold cache, dominated by the 2 MB deck.gl bundle); hazard switch 13–64 ms, river flood **217 ms** (189 ms of it
  the 0.5 MB gzipped file). Both limits hold; a cold-cache measurement with a real GPU on a laptop is still worth
  a look during review.
- No screenshots are committed; the smoke script lives in the session scratchpad and could move to `tools/`.
- Phases 2–4 remain deferred.
