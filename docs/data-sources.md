# Data source catalog

Started 2026-11-10. One row per source this project uses, has probed, or is considering. The rule from
`AGENTS.md` applies: a figure counts only once it has been checked against a download made from this repo.
"Checked" below says what was actually run; anything else is a lead, not a fact.

Status: **in use** (built into a pipeline here) · **probed** (read from this repo, not built in) ·
**candidate** (from research, not yet read from here) · **not usable** (with the reason).

## Hazard and event sources

| Source | What it gives | Status | Where used | Access | Licence | Checked |
| --- | --- | --- | --- | --- | --- | --- |
| CRC Open (RiskThinking.AI) | Pre-fitted curves, 63 hazards, SSP5-8.5, H3 cells | in use | `explorer/` | crc-sdk `HazardDataset.crc_open()` | CC BY-NC 4.0 | Release `ssp585-global-2026-10-20-v1`; 8 hazards built and verified against `for_assets` |
| NOAA NCEI Storm Events (bulk CSV) | Storm reports 1950 on: type, time, size, location | in use | `storm_events/`, `curves/`, `assets/exposure.py` | NCEI directory listing | U.S. government work | 231 files, SHA-256 manifest; 166,214 Texas events |
| Storm Events copy (Earth Genome, Source Cooperative) | The same events as one GeoParquet, one point each | probed | `storm_events/compare.py` | `data.source.coop/earthgenome/storm-events-db` | not stated | Compared event by event; lags NCEI; local time without offset |
| NOAA IBTrACS v04r01 | Tropical cyclone tracks, winds, wind radii | in use | `crc_data_explorer/tracks.py` | crc-sdk `IBTrACSPlan` | U.S. government work | 91 storms crossing Texas, 30 with radii |
| NOAA CO-OPS extreme water levels | Published return levels at tide stations | in use (prototype) | `crc_data_explorer/sources.py` | crc-sdk `NOAAExtremeWaterLevelPlan` | U.S. government work | 9 of 39 Texas stations publish them |
| NOAA GHCNh stations | Hourly station temperature, fitted curves | in use (prototype) | `crc_data_explorer/sources.py` | crc-sdk `HazardDataset.ghcnh` | CC0 | 8 stations with 15 or more valid years of 40 probed |
| ERA5 (WeatherBench2 1.5° copy) | Annual hottest day 1991–2020, fitted | in use (prototype) | `crc_data_explorer/sources.py` | crc-sdk `HazardDataset.era5` | CC BY 4.0 (Copernicus) | 1,439 r4 cells |
| NOAA ISD, USGS streamflow, USDA CDL, sea-level scenarios | Station curves; gauge flows; crop classes; scenarios | probed | — | crc-sdk plans | U.S. government works | See `docs/sources-track/requirements.md` |
| CHIRPS, GloFAS | Monthly rain; flood depth rasters | probed, could not verify | — | crc-sdk | CC BY 4.0 | rasterio does not load on this Mac |
| EFAS, EDO, ECCC, HYDAT | European and Canadian sources | not usable | — | crc-sdk | — | No Texas coverage |
| MRMS radar hail (MESH) | Radar hail size, 0.01°, daily maxima | in use | `radar/mrms.py`, `radar/analysis.py` | AWS `noaa-mrms-pds`, `CONUS/MESH_Max_1440min_00.50/` | NOAA open data | 1,903 days decoded, 2020-10-15 to 2025-12-31; 2 days missing |
| NCEI Severe Weather Data Inventory, hail signatures (`nx3hail`) | Radar hail signatures per storm cell, 1995 on | in use | `radar/swdi.py` | NCEI yearly CSV | U.S. government (licence text not found) | Yearly files clipped to Texas; see `docs/research/radar-hail-sources.md` |
| MYRORSS radar reanalysis | Radar hail size 1998–2011, 0.01° | candidate | — | AWS `noaa-oar-myrorss-pds` | NOAA open data | Year folders listed; not opened |
| Iowa State MRMS archive | Radar hail size grid, August 2019 to October 2020 | candidate | — | `mtarchive.geol.iastate.edu` | open | Listed by research; daily maximum has gaps |
| SPC hail climatology maps | Hail days per year, 1986–2015 | probed | Phase 3 by-eye check | `spc.noaa.gov/wcm/climo/` | U.S. government work | Image viewed; not ingested |

## Asset sources

| Source | What it gives | Status | Where used | Access | Licence | Checked |
| --- | --- | --- | --- | --- | --- | --- |
| USPVDB v4.0 (USGS / Berkeley Lab) | Solar plants of 1 MW or more with array polygons, capacity, mounting | in use | `assets/solar.py` | `energy.usgs.gov/uspvdb` GeoJSON | Public domain | Release `uspvdb_v4_0_20260414`; 187 Texas plants, 23,033 MW AC |
| EIA-860 and EIA-860M through PUDL (Catalyst Cooperative) | Every generator of 1 MW or more: status, capacity, dates, balancing authority; solar schedule with tracking, tilt, bifacial, DC capacity | probed | — | Parquet on `s3://pudl.catalyst.coop/nightly/` | EIA: U.S. government work; PUDL: CC BY 4.0 (to confirm) | Read 2026-11-10: 251 existing Texas PV plants, 34,979 MW, against 187 in USPVDB. 66 plants (12,147 MW) are in EIA only, 61 of them online in 2025–2026. Solar schedule matched for 226 of 251 |
| NREL Annual Technology Baseline 2025 | Utility PV overnight capital cost by year | in use | `assets/value.py` | OEDI S3 CSV | NREL, attribution | 2024 OCC 1,300.56 $/kW AC; dollar year not in the file |
| National Structure Inventory (USACE) | One point per structure: occupancy, building type, values | probed | `assets/real_estate.py` | NSI API by county | to confirm | Fort Bend: 305,551 structures, $187.6 billion |
| USA Structures (FEMA / ORNL, Source Cooperative copy) | Building footprints with occupancy class | probed | `assets/real_estate.py` | GeoParquet, filter on `FIPS` | U.S. government work | Fort Bend: 265,565 footprints; 79.5% of NSI points join |
| ERCOT unit lists, queue, node mapping, 60-day output | Unit codes, zones, queue milestones, 5-minute output | candidate | — | ERCOT public API, `gridstatus` | ERCOT terms | Not read from here; research in `docs/research/solar-plant-data-sources.md` |
| Berkeley Lab Utility-Scale Solar | Verified tracking, capacity factors, cost per plant | candidate | — | `emp.lbl.gov` | LBNL | Site blocked scripted access from here (Cloudflare) |
| TransitionZero Solar Asset Mapper | Satellite-detected solar polygons, quarterly | candidate | — | TransitionZero | Non-commercial only | Not read from here |
| Cleanview, S&P, Wood Mackenzie, Enverus | Commercial repackaging with pipeline detail | not planned | — | paid | commercial | Research found no physical parameters beyond EIA |
| HIFLD Open, WRI Global Power Plant Database | Older plant lists | not usable | — | archives | — | Discontinued or unmaintained per the research |

## Reference and boundary data

| Source | What it gives | Status | Where used | Licence | Checked |
| --- | --- | --- | --- | --- | --- |
| Census cartographic boundaries (state, county, 2024) | Texas outline, county polygons | in use | `lab_common/texas.py`, `storm_events/geometry.py` | Public domain | 254 Texas counties |
| NWS public forecast zones (`z_16ap26`) | Zone polygons for zone-located events | in use | `storm_events/geometry.py` | U.S. government work | 298 Texas zones; 1,694 events carry retired zone codes |
| OpenFreeMap / OpenMapTiles / OpenStreetMap | Basemap | in use | `site/` | ODbL data, attribution | — |
| Census 2020 tract populations and TIGER 2024 primary and secondary roads | Covariates of the reporting-bias model | in use | `assets/reporting_bias.py` | Census Bureau | Public domain | See `docs/reports/5-reporting-bias.md` for files and checksums |
| GPWv4 gridded population (SEDAC) | Population density, 30 arc-seconds, 2000–2020 | candidate | planned, `docs/plan-hail-exposure.md` | Open, per its DOI page (research) | Not yet read from this repo |
| Census TIGER/Line roads | Road network for a reporting-bias covariate | in use (first attempt) | `assets/reporting_bias.py` | Public domain | `tl_2024_48_prisecroads.zip` read 2026-11-10: 102,802 km of primary and secondary road in the Texas cells |
| Census 2020 tract boundaries and tract populations | Population per tract for a reporting-bias covariate | in use (first attempt) | `assets/reporting_bias.py` | Public domain | `cb_2020_48_tract_500k.zip` and `CenPop2020_Mean_TR48.txt` read 2026-11-10: 6,884 tracts, 29,145,505 people. The Census API needs a key and was not used |

## What the solar research changes

Source: `docs/research/solar-plant-data-sources.md` (PR 4), checked here against PUDL on 2026-11-10.

- **EIA is the fuller list.** It holds 64 more Texas plants and half again the capacity of USPVDB, nearly all
  built in 2025–2026. USPVDB remains the only source of array polygons.
- **The join key works.** `eia_id` in USPVDB matches `plant_id_eia` for 185 of 187 plants.
- **EIA carries hail-relevant parameters** USPVDB lacks or only partly has: single-axis tracking flag, tilt,
  bifacial flag, crystalline or thin-film material, DC capacity.
- **Dates disagree.** Fighting Jays is 2016 in USPVDB and June 2022 in EIA. The build year decides the glass
  class in the hail impact draft, so the source of the date matters.
- **Five balancing authorities.** 237 plants are in ERCOT; 14 are in El Paso Electric, SPP, MISO or another
  area and will not appear in ERCOT reports.

Suggested order if these are built: EIA through PUDL as the plant list, USPVDB joined for polygons, ERCOT only
when unit output or grid attributes are needed.
