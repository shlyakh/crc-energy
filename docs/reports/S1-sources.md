# S1 report: the other crc-sdk sources in the explorer (sources track)

Date: 2026-11-10 · branch `sources-track` (not merged) · crc-sdk 0.11.1 · crc-framework 0.6.0 · awaiting review.
Requirements and the per-source findings table: [../sources-track/requirements.md](../sources-track/requirements.md);
plan: [../sources-track/plan.md](../sources-track/plan.md).

## What was built

- **Probes** (`tools/probes/sources.py <name>`): one run per source against Texas, each printing a JSON record with
  what came back, time, bytes and, where it failed, the error. Thirteen sources probed; results in the findings table.
- **Four explorer layers** (`python -m crc_lab.explorer.sources`, `just sources`), all under `site/data/sources/`:
  - `ibtracs.geojson` (lines): 54 tropical cyclones 1980–2024 with a best-track point in the Texas box, tracks clipped
    to a box around Texas; name, season, strongest agency wind and lowest pressure while in Texas. 41 KB.
  - `coops.geojson` (points): the 9 of 39 Texas NOAA CO-OPS water-level stations that publish extreme water levels;
    22 published annual-exceedance levels each (1.01–100 years) as the curve, datum, trend. 9 KB. The 30 stations
    without the product are listed in the data card with the error crc-sdk raised.
  - `ghcnh.geojson` (points): airport (`USW`) stations with a GEV curve fitted by crc-sdk from GHCNh hourly
    temperature, 2000–2024, evaluated at the eight explorer return periods; 8 curves from the first 40 stations
    requested (the others have fewer than 15 valid years). 5 KB.
  - `era5_txx/2005.json` (h3-cells): ERA5 `txx` 1991–2020 from the 1.5° WeatherBench2 store, fitted by crc-sdk on
    1,439 land cells at H3 resolution 4 (about 1,770 km² each), in the same file shape as the CRC Open layers; it
    appears in the hazard selector with its own horizon (2005, the window centre). 181 KB.
  - `manifest.json`: the data card (G2) with source, retrieval, licence, counts, skipped stations, warnings,
    verification and the pinned versions.
- **Page** (`site/app.js`, additive): generic `points` and `lines` kinds (`loadGeo`, `geoLayer`, `geoTooltip`,
  `showFeature`), a click panel listing a feature's properties and drawing `curve.return_periods/values` with the
  existing chart, source caveats in the caveat panel, per-layer `horizons`, caveat text for non-CRC-Open cell layers,
  and a `crc:flyTo` test hook. Source GeoJSON layers start switched off (X3).
- **Registry** (`site/layers.json`): four entries. **Tests**: 4 new offline tests (12 in all). **Smoke test** moved
  into the repo as `tools/smoke.mjs` (`--sources` runs the source scenario).

## Checks

| # | Check | Result |
| --- | --- | --- |
| 1 | GHCNh shipped values equal `for_assets` at the station point | **Pass**: 3 stations × 8 return periods = 24 values, 0 mismatches (`just sources` runs it; recorded in the data card). |
| 2 | ERA5 cells | 1,439 r4 cells, all `fitted` (GEV), pathway `historical`, `annual_exceedance`, unit °C; fit `sample_lmoments`, minimum 20 complete years. Built from the cached canonical file; the fetch itself took 646 s for 30 variable-years (21.5 s per year), 0.3 MB cache. |
| 3 | Page still works, Phase 1 timings unchanged | Headless Chrome against a local server: first view **420 ms** (378 ms loading `tx_max/2050.json`), return-period switch 11 ms, river flood 33 ms; no script errors. |
| 4 | Source layers toggle and click | IBTrACS 54 features (21 ms to view after a 0.7 s fetch), CO-OPS 9 (19 ms), GHCNh 8 (17 ms); a clicked CO-OPS station shows 22 levels and the chart; ERA5 switch 10 ms with 1,439 cells, horizon selector shows 2005 only, caveat panel shows the ERA5 text. |
| 5 | `just site` | Complete: 13 layers, 14.8 MB of data. |
| 6 | Lint and tests | `ruff` clean; 12 tests pass offline. |

## Findings worth passing on

- **Raster sources cannot be verified on this Mac.** `rasterio` (1.4.4 and 1.5.2) fails to load because the
  Homebrew `libheif` it links references a missing `libx265.216.dylib`; CHIRPS (23 MB COG downloaded, then failed)
  and GloFAS (failed before downloading) are blocked until `brew reinstall x265 libheif` or a Linux build.
- **NEX-GDDP-CMIP6 fails in crc-sdk 0.11.1**: `'tasmax' is published in "b'K'", but recipe 'txx' converts from 'K'`
  (the unit attribute arrives as bytes). An upstream bug report; low priority here.
- **EDO drought has no Texas coverage** (`bounds do not intersect the raster`); ECCC sources take a Canadian
  province and station IDs; EFAS is European. These rows now say so in `site/sources.json`.
- **CO-OPS extreme levels exist at 9 Texas stations**; sea-level scenarios (75 rows per station) are available for
  more and could be the next table.
- **GHCNh yield**: the first 40 airport stations gave 8 curves with at least 15 valid years; the catalogue has no
  record lengths for them, so station selection needs a rule (S2). About 13 s per station.
- **FTW** gave 0 fields in a 0.1° box near Austin in 51 s; **CDL** works with the `agriculture` extra (not pinned
  here): 21 classes in 10 s for the same box.

## Not done / for review

- Nothing merged: the branch waits for review beside Phase 2 on `main`.
- Raster sources, USGS gauges, CO-OPS sea-level tables and more GHCNh stations are S2/S3 (plan).
- `rasterio` in the worktree's `.venv` was downgraded to 1.4.4 while testing the load failure; `uv sync` restores
  the locked 1.5.2. Nothing in `uv.lock` changed.
- The probe JSON outputs are not committed (session scratch); the scripts that produced them are.
