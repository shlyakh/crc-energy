# Requirements: the other crc-sdk sources in the explorer (sources track)

Status: **draft 2026-11-10, from probes run against Texas** · a side track to the Phase 1 explorer; Phase 2
(Storm Events) runs in parallel on `main` · requirement IDs X1–X9 · classification as in
[../requirements.md](../requirements.md) (USE / OUTSIDE / EXTEND)

## 1. Goal

Show, in the same explorer, what every other source crc-sdk 0.11.1 reaches looks like for Texas, at a
schematic level and a lower resolution than the CRC Open layers: enough to see where the data is, what it
returns (a curve, an observation, a published table) and what it costs to fetch, not a second full product.
CMIP6 and NEX-GDDP projections are last in line (Yuri, 2026-11-10: less interest in the CMIP predictions).

Region: Texas. Pins: crc-sdk 0.11.1, crc-framework 0.6.0 (unchanged).

## 2. What the probes found

Every row below was measured on 2026-11-10 with `tools/probes/sources.py <name>` (one JSON record per source)
or by the S1 build (`python -m crc_lab.explorer.sources`). "Could not verify" states the error, not a guess.

| Source (crc-sdk entry) | Covers Texas? | Returns | Schematic representation | Measured cost | Licence / attribution |
| --- | --- | --- | --- | --- | --- |
| NOAA GHCNh stations (`HazardDataset.ghcnh`) | Yes: 699 stations in the Texas box (347 `USW` airport, 222 `USC` co-op, 22 Mexican) | Canonical curves at station points (GEV, L-moments) from hourly temperature | Points with the fitted curve, airport stations only | Catalogue 0.4 s. Three stations, 2000–2024: 38 s, 2 curves (one station short of 15 valid years), 1.8 MB cache; about 13 s per station | CC0-1.0 (AWS registry); attribution requested |
| NOAA ISD stations (`HazardDataset.isd`) | Yes: 732 stations in the box; archive ends August 2025 | Same recipe, archived archive | Not prototyped (GHCNh is the live successor) | Catalogue 0.4 s, 0.7 MB | NOAA open data; attribution, no endorsement |
| USGS daily streamflow (`USGSStreamflowPlan`) | Yes (United States); station IDs must be known, no area search in crc-sdk | Daily mean discharge with approval status (observations, not curves) | Gauges as points with a flow summary; needs a Texas gauge list from USGS | 5 years at Colorado River at Austin: 1,827 rows, 3.9 s, 4 pages, 0.8 MB | U.S. government work; cite doi:10.5066/F7P55KJN |
| CHIRPS v3 monthly (`CHIRPSMonthlyPlan`) | Yes (60°S–60°N) | Pixel centres with monthly mm from a global COG | Coarse monthly map (H3 r3/r4 means) for one month | **Could not verify on this machine**: the 23 MB COG downloaded in 325 s, then `rasterio` failed to load (Homebrew `libheif` references a missing `libx265.216.dylib`) | CC BY 4.0; cite the Climate Hazards Center |
| IBTrACS tracks (`IBTrACSPlan("NA")`) | Yes: 54 storms with a best-track point in the Texas box, 1980–2024 (847 points) | Track points with agency wind and pressure | Lines, one per storm, clipped to a box around Texas | 3.4 s to scan the basin CSV; 55 MB cached; output 41 KB | U.S. government work; cite Schreck et al. 2024, doi:10.25921/82ty-9e16 |
| NOAA CO-OPS extreme water levels (`NOAAExtremeWaterLevelPlan`) | Yes: 39 water-level stations in Texas; **9** carry the published extreme-levels product | Published annual-exceedance levels (22 per station, 1.01–100 years) and detrended annual extremes (62 years at Galveston Bay Entrance) | Points with the published levels as the curve, plus the sea-level trend | 0.7 s per station, 43 KB; output 9 KB | U.S. government work; attribution requested |
| NOAA CO-OPS sea-level scenarios (`NOAASeaLevelPlan`) | Yes (U.S. tide stations) | 2022 interagency scenarios, 75 rows per station (5 scenarios × 15 decades) vs a 2005 baseline | A per-station table in the click panel (not drawn) | 0.2 s per station | U.S. government work |
| JRC GloFAS river flood (`HazardDataset.glofas`) | Global tiles, so Texas in principle | Flood-depth curves fitted from return-period rasters | H3 r6 cells on one river reach | **Could not verify on this machine**: same `rasterio` load failure before any download | CC BY 4.0; cite JRC |
| JRC EFAS river flood (`HazardDataset.efas`) | No: Europe only (continental rasters) | — | — | Not probed (EFAS is European by construction) | CC BY 4.0 |
| JRC EDO soil-moisture drought (`HazardDataset.smi`) | **No**: `bounds do not intersect the raster` for an Austin box | — | — | 13 s to find out | CC BY 4.0 |
| ECCC IDF, daily climate, HYDAT (`eccc_idf`, `ECCCDailyPlan`, `HYDATDailyPlan`) | **No**: Canadian station IDs and a province argument; no area search | — | — | Not applicable | Open Government Licence – Canada |
| USDA Cropland Data Layer (`AgriculturalLayer.usda_cdl`) | Yes | Crop-class pixel counts (land cover, not acreage) | Coarse crop-mix summary per H3 r4 cell for one year | 0.1° box, 2024, 30 m: 21 classes, 10 s; needs the `agriculture` extra (`icechunk`, `pyproj`), not in this repo's pins | Public domain (USDA NASS) |
| Fields of The World (`AgriculturalLayer.ftw_fields`) | Nominally (requires `in_country("US")`) | Predicted field polygons | Polygons where present | 0.1° box near Austin: **0 fields** in 51 s; coverage in Texas unknown | Per dataset |
| ERA5 `txx` 1991–2020 (`HazardDataset.era5(..., store="wb2-1p5")`) | Yes | Curves on H3 cells from reanalysis annual maxima (historical baseline, `annual_exceedance`, pathway `historical`) | H3 r4 cells (about 1,770 km²), one horizon (2005, the window centre); **built in S1** | 30 variable-years from the 1.5° store: 646 s (21.5 s per year), 0.3 MB cache, 1,439 land cells, all `fitted` GEV; output 181 KB | CC BY 4.0; "Contains modified Copernicus Climate Change Service information" |
| NEX-GDDP-CMIP6 (`HazardDataset.nex_gddp_cmip6`) | Yes (0.25° global) | Annual extremes per model and scenario (samples, not curves) | Not planned (low interest) | **Could not verify**: crc-sdk 0.11.1 rejects the store's unit attribute (`'tasmax' is published in "b'K'" but recipe 'txx' converts from 'K'`), after 455 s; a `RestrictiveLicenceWarning` on CC BY-SA model terms | CC0 archive plus the model licence |
| CMIP6 native (`HazardDataset.cmip6`) | Yes (model grids) | Curves per model, member and scenario | Not planned (low interest) | Not probed | Per modelling centre |

Corrections to `site/sources.json` from the probes: ECCC and JRC EFAS/EDO have no Texas coverage (the table
said "Canada" and "Europe" without saying so); FTW needs a country; CDL needs an extra the repo does not pin.

## 3. Requirements

| ID | Requirement | Tag |
| --- | --- | --- |
| X1 | Generic layer kinds in the explorer: `points` and `lines` as GeoJSON files, drawn by one code path, with a click panel that lists the feature's properties and, when the feature carries `curve.return_periods` and `curve.values`, draws it with the same chart as the CRC Open cells. No source-specific page code | EXTEND |
| X2 | One registry entry per source layer in `site/layers.json` (title, source, licence, caveat, file, style); the caveat panel shows the caveat, source and licence of every source layer switched on | USE |
| X3 | Source layers start switched off, so the Phase 1 first view and its timings are unchanged | — |
| X4 | Tropical cyclone tracks (IBTrACS): every storm with a best-track point inside the Texas box, clipped to a box around Texas, with name, season, strongest agency wind and lowest pressure while in Texas | USE |
| X5 | Coastal water levels (NOAA CO-OPS): every Texas station that publishes extreme water levels, the published levels as the curve (not fitted), datum, trend; stations without the product listed in the data card | USE |
| X6 | Station temperature curves (GHCNh): airport (`USW`) stations in Texas, 2000–2024, curves fitted by crc-sdk, evaluated at the same eight return periods as the CRC Open layers, with raw parameters; a `for_assets` check at sampled stations equals the shipped values | USE |
| X7 | A data card (`site/data/sources/manifest.json`): per layer the source, retrieval time, licence, counts, skipped items and warnings; versions of the pins | G2 |
| X8 | `just sources` rebuilds every source layer; `just all` includes it; `just site` fails when a registered file is missing | G5 |
| X9 | ERA5 `txx` 1991–2020 as an `h3-cells` layer at r4 in the hazard selector, with its own horizon (2005) and its own caveat text; the page reads a layer's `horizons` when present | USE |
| X10 | Later, each after review: USGS gauges as points (needs a gauge list); CHIRPS and GloFAS once raster reading works on the build machine (or in CI); CDL crop mix if the `agriculture` extra is pinned; CO-OPS sea-level scenarios as a table in the station panel | USE |

## 4. Out of scope

CMIP6 and NEX-GDDP projections as layers (low interest; NEX also fails in crc-sdk 0.11.1); ECCC, HYDAT,
EFAS, EDO (no Texas coverage); anything beyond Texas; fitting curves to observations that crc-sdk does not
fit itself (USGS flow, CO-OPS annual extremes).

## 5. Not yet verified

- Raster sources (CHIRPS, GloFAS) on this machine: `rasterio` 1.4.4 and 1.5.2 both fail to load because the
  Homebrew `libheif` they link references `libx265.216.dylib`, which is missing. `brew reinstall x265 libheif`
  or a Linux build (the Pages workflow) would answer it.
- GHCNh coverage beyond the first airport stations; the cost per station is measured, the station count is not
  chosen yet.
- FTW coverage anywhere in Texas (one box gave zero fields).
- Whether NOAA CO-OPS publishes extreme levels for more than the nine Texas stations found (the station list is
  from the CO-OPS metadata API; the product exists where the API returned levels).
