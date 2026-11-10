# Solar power plant data sources: U.S. and Texas (ERCOT)

Research report, 2026-11-10. Question: where to get a list of power plants, specifically solar plants, with
their parameters, for the U.S. and for Texas.

**Status for agents.** This is background research, not a requirement and not a phase. Nothing here is
scheduled; `docs/requirements.md` and `docs/implementation-plan.md` remain the source of what to build.
Release dates, counts and prices below were gathered by web research on 2026-11-10 and have not been checked
against a download made from this repo. Under the "never invent a number" rule, re-check any figure against
the primary source before it enters code, a data card or a report. Items that rest on third-party or
secondary sources are listed under [Caveats](#caveats).

**How it relates to this repo.** `src/crc_lab/assets/solar.py` already loads USPVDB v4.0 (187 Texas plants)
and keeps `eia_id`. That column is the join key to the EIA generator inventory described here, which would
add plants newer than USPVDB's cut-off (operational through Q4 2025) and per-generator array detail.

## Summary

Use EIA's generator inventories as the backbone: EIA-860M (monthly, free, every generator ≥1 MW, with
coordinates and status) for the current list, and the annual EIA-860 Schedule 3_3 "Solar" file (final 2025
data released September 10, 2026) for array parameters such as tracking type, tilt/azimuth, DC capacity and
module technology. Join both on EIA Plant ID + Generator ID. Then add USPVDB v4.0 (April 2026, 6,611
facilities) for array polygons and footprint, and, for Texas, ERCOT's unit-level reports (CDR/MORA unit
lists, the GIS queue report, the NP4-160-SG settlement point/resource-node mapping and the 60-day SCED
disclosure) for grid-specific attributes and unit-level output. Cleanview and other commercial tools mostly
repackage these same public sources. They are worth paying for only for daily-refreshed pipeline tracking and
developer attribution.

- **US-wide backbone:** EIA-860M (latest: September 2026 data, released October 23, 2026; next release
  November 24, 2026) joined to EIA-860 2025 final (Schedule 3_3 Solar) on `plant_id` + `generator_id`. The
  easiest programmatic route is Catalyst Cooperative's PUDL, which publishes free Parquet/SQLite on a public
  S3 bucket. Then attach USPVDB v4.0 polygons via `eia_id` = EIA Plant Code.
- **Texas/ERCOT layer:** ERCOT lists units by ERCOT unit code (e.g., `JAY_UNIT1`), INR queue number, county
  and CDR zone in its CDR/MORA reports. It maps units to resource nodes and load zones in NP4-160-SG. It
  publishes 5-minute unit-level output with a 60-day lag in NP3-965-ER, and hourly regional solar
  actual/forecast in NP4-745-CD, all through its public API. There is no official EIA↔ERCOT crosswalk; it has
  to be built by name, county and capacity matching.
- **Coverage pitfalls:** ERCOT's About page says it represents "about 90 percent of the state's electric
  load", so it does not cover all of Texas. Filter EIA by `state = TX` *and* balancing authority to separate
  ERCOT from SPP/MISO/El Paso plants. Watch AC vs DC capacity, plant- vs generator-level rows, and the
  1–2 year lag in USPVDB and annual EIA-860.

## Key findings

1. **EIA is the only free, comprehensive, generator-level, regularly updated U.S. inventory, and every
   serious dataset (USPVDB, PUDL, eGRID, Cleanview, GEM) is built on it.**
   - EIA-860 covers existing and planned generators at plants with 1 MW or more of combined nameplate capacity.
   - The 2025 final release (September 10, 2026) includes a dedicated `3_3_Solar` file with Operable and
     Retired/Canceled tabs.
   - The next early release (2026 data) is due in June 2027.
2. **EIA-860M is the freshest official list, but it is explicitly preliminary.**
   - EIA warns that capacities are preliminary estimates and are corrected in later months without notice.
   - It has Operating, Planned, Retired (since 2002) and Canceled/Postponed tabs, with lat/lon, balancing
     authority, nameplate and net summer/winter MW.
   - It does *not* carry the solar array detail; that comes only from annual EIA-860.
3. **USPVDB v4.0 (released April 14–16, 2026) is the best free source of solar array polygons in the U.S.**
   - It covers 6,611 facilities in 49 states + DC that became operational through Q4 2025.
   - It is public domain, with Shapefile, GeoJSON, CSV and a REST API.
   - It links to EIA via `eia_id`.
   - It lags installations by more than a year.
4. **ERCOT publishes rich unit-level data, but no single "plant master list" with lat/lon or array parameters.**
   - Unit names, codes, county, zone, in-service year and capacities are in the CDR/MORA unit-capacity tabs.
   - Queue projects are in the monthly GIS report (PG7-200-ER).
   - Node and load-zone mapping is in NP4-160-SG.
   - Unit-level output is in the 60-day SCED disclosure.
   - The CDR was skipped in May 2026 with PUCT approval, so the December 2025 CDR is the last full one (a
     substitute generation-resource workbook was posted).
5. **Cleanview is a convenience layer, not a primary source.**
   - Its own API docs expose an "EIA 860M data" endpoint and ISO queue endpoints that mirror ERCOT's raw structure.
   - Pricing is $9,000/yr for the power-projects platform (up to 5 users), +$5,000/yr for API access, or a
     $4,900 one-time download.
6. **Several "obvious" sources are stale or gone.**
   - HIFLD Open was discontinued on August 26, 2025; only archived snapshots survive.
   - The WRI Global Power Plant Database has been unmaintained since v1.3.0 (June 2021).
   - EPA eGRID's latest official edition is eGRID2023rev2 (June 12, 2025), which covers 2023 data.

## Details

### 1. EIA products (primary backbone)

**Form EIA-860 (annual, final)**

- **Page:** https://www.eia.gov/electricity/data/eia860/
- **Latest:** 2025 final data, released September 10, 2026. Zip at
  https://www.eia.gov/electricity/data/eia860/xls/eia8602025.zip
- **Scope:** all plants ≥1 MW combined nameplate; existing, proposed (within 10 years), retired and canceled
  generators.
- **Files that matter for solar:**
  - `2___Plant` (lat/lon, county, balancing authority, NERC region, utility)
  - `3_1_Generator` (nameplate MW AC, summer/winter MW, operating month/year, status, prime mover PV, energy
    source SUN)
  - `3_3_Solar` (solar-specific)
  - `3_4_Energy_Storage` (co-located batteries)
  - `4___Owner` (fractional ownership)
- **Solar schedule fields** (per the EIA-860 instructions and PUDL's `core_eia860__scd_generators_solar` table):
  - tracking flags: single-axis, dual-axis, fixed tilt, east-west fixed tilt
  - tilt and azimuth angles (azimuth 0–359°, with 180 = south)
  - DC net capacity
  - module technology (crystalline silicon, thin-film, etc.)
  - bifacial flag
- **Generator granularity is useful for solar:** EIA asks for a separate generator ID per installation phase,
  and per fixed-tilt array with a different tilt or azimuth.
- **Lag:** a plant reaching COD in early 2025 appears in the final 2025 file only in September 2026. Use 860M
  for anything newer.

**Form EIA-860M (Preliminary Monthly Electric Generator Inventory)**

- **Page:** https://www.eia.gov/electricity/data/eia860m/
- **Latest:** October 23, 2026 release (September 2026 data). Next: November 24, 2026.
- **Coverage:** every operating, planned, retired (comprehensive since 2002) and canceled generator ≥1 MW,
  including Puerto Rico since 2018.
- **Fields:** entity, plant ID/name, generator ID, county, lat/lon, balancing authority, technology, prime
  mover, nameplate and net summer/winter MW, operating/planned month-year, status codes.
- **What it is for:** the right "as-of-now" list, and also the main free source of the *near-term pipeline*
  (planned units with expected COD).
- **Respondents:** EIA estimates 508 respondents for the monthly form, which tracks proposed generators due
  within 12 months and existing generators with modifications.
- **Revisions are material:** one third-party reconciliation found 2025 solar additions in the final EIA-860
  (29.5 GW net summer) were revised up about 8% from EIA's first monthly count (27.2 GW). This is an
  independent GitHub analysis, not an EIA statement.

**EIA Open Data API v2**

- **Endpoint:** `https://api.eia.gov/v2/electricity/operating-generator-capacity/data` (free API key).
- **What it serves:** the generator inventory (e.g., `nameplate-capacity-mw`), with facets for state,
  balancing authority, energy source, etc.
- **When to use it:** convenient for incremental pulls.
- **Limits:**
  - It does not expose the 860 solar schedule (tilt/azimuth/tracking).
  - It has row limits per request.
  - Bulk XLS or PUDL is simpler for full snapshots.
- **Plant-level generation:** use the `facility-fuel` route or EIA-923 bulk files (monthly net generation by
  plant/prime mover). EIA-923 generation is partly imputed: EIA's Electric Power Annual Technical Notes
  describe regression prediction for missing monthly data, covering approximately 10,200 plants not in the
  monthly sample. Validate against ISO data where possible.

**EIA Hourly Electric Grid Monitor and State profiles**

- Balancing-authority-level hourly generation by fuel, e.g., ERCOT's hourly solar total.
- Useful for aggregate validation and backtesting, but contain **no plant-level data**.
- The SEDS Texas fuel table is state-level energy consumption/production, not a plant list.

**EIA U.S. Energy Atlas / power-plant GIS layer**

- A point layer built from EIA-860, 860M and 923: Plant_Code, utility, installed MW by fuel, lat/lon.
- Good for quick maps, but it adds nothing beyond the underlying tables.
- One third-party audit of the HIFLD shutdown reports that some EIA layers DHS pointed users to now require a
  login. Prefer the EIA XLS/PUDL tables for reproducible pipelines.

### 2. USPVDB (USGS/LBNL), the polygon layer

- **Release and coverage:**
  - Latest release: **USPVDB_V4_0_20260414** (ScienceBase lists last revision April 16, 2026).
  - Covers **6,611 facilities** in 49 states + DC: ground-mounted, rooftop, canopy and floating systems of
    1 MW or more.
  - Newest facilities became operational in **Q4 2025**; oldest installed in 1985.
  - The prior v3.0 (April 30, 2025) had 5,712 facilities through Q3 2024.
- **How it is built:** EIA facility records are position-verified and digitized from aerial imagery, with
  array boundaries "digitized to within 10 meters". Attributes are added from EPA (contaminated
  lands/RE-Powering) and NREL (agrivoltaics).
- **Fields** (from the API doc): `case_id` (stable USPVDB ID), `eia_id`, `p_state`, `p_county`, `ylat`,
  `xlong`, `p_area` (m²), `p_img_date`, `p_dig_conf` (1–4 digitization confidence), `p_name`, `p_year`,
  `p_pwr_reg`, `p_tech_pri`, `p_tech_sec` (e.g., thin-film), `p_axis`, `p_azimuth`, `p_tilt`, `p_battery`,
  `p_cap_ac`, `p_cap_dc`, `p_type` (greenfield/RCRA/superfund/landfill…), `p_agrivolt`, `p_comm` (community
  solar), `p_sys_type`, `p_zscore` (outlier flag on DC MW per area), `multi_poly`.
- **Access:**
  - Downloads (Shapefile ~7 MB zipped, GeoJSON ~2 MB zipped, CSV, XML metadata): https://energy.usgs.gov/uspvdb/data/
  - Viewer: https://energy.usgs.gov/uspvdb/viewer/
  - REST API (PostgREST-style filters):
    `https://energy.usgs.gov/api/uspvdb/v1/projects?p_state=eq.TX&select=case_id,eia_id,p_name,p_cap_ac,p_cap_dc,p_axis,ylat,xlong`
  - DOI for all versions: 10.5066/P9IA3TUS
- **Licence:** public domain; an acknowledgment is requested.
- **Update cadence:** annual, with a lag of 1–2 years.
- **Caveats:**
  - Attributes are EIA self-reported.
  - `p_dig_conf` = 1 means one polygon represents several EIA records (multiphase sites), so capacity sums
    can double-count on a naive join.
  - Some third-party users report HTTP 403s on scripted downloads from USGS. Set a browser-like User-Agent or
    cache the file.

### 3. ERCOT, the grid-specific layer for Texas

**Coverage reality**

- ERCOT's About page says it serves more than 27 million Texas customers, "about 90 percent of the state's
  electric load". Its Company Profile page puts the grid at approximately 75 percent of Texas land area.
- The rest of Texas is in other grids:
  - **SPP:** Panhandle/South Plains (SPS/Xcel) and Northeast Texas (SWEPCO).
  - **MISO:** Southeast Texas (Entergy Texas).
  - **WECC:** El Paso Electric.
- West Texas Panhandle solar in SPS territory will **not** appear in any ERCOT report.

**Unit lists: CDR and MORA**

- **CDR unit lists:**
  - Each CDR has a unit-capacity tab with unit name, INR number, **ERCOT unit code** (e.g., `JAY_UNIT1`,
    `PHO_SOLAR1`), fuel/technology, county, CDR zone (e.g., HOUSTON, SOUTH, WEST, PANHANDLE, COASTAL, NORTH),
    in-service year, and seasonal capacities. Example row from the December 2024 CDR: FIGHTING JAYS SOLAR U1,
    21INR0278, `JAY_UNIT1`, Fort Bend, HOUSTON.
  - The last full CDR is **December 2025** (posted December 19, 2025):
    https://www.ercot.com/files/docs/2025/12/19/CapacityDemandandReservesReport_December2025.pdf
  - On May 18, 2026, ERCOT asked the PUCT (Project No. 55999) to skip the May 2026 CDR. It instead posted
    `Generation_Resource_Forecast_May2026.xlsx` on the Resource Adequacy page. Per a secondary source (TCAP),
    the PUCT granted this on June 18, 2026.
  - A December 2026 CDR would normally appear in mid/late December.
- **MORA:**
  - Monthly; latest is **December 2026**, posted October 2, 2026:
    https://www.ercot.com/files/docs/2026/10/02/MORA_December2026.pdf (plus an xlsx).
  - Includes a "Unit Capacities" tab (unit name, unit code, county, fuel, zone, year, installed and expected
    capacity).
  - Index page: https://www.ercot.com/gridinfo/resource
- **What these give:** the best **official list of operating ERCOT solar units by ERCOT resource code**.
- **What they lack:** lat/lon, DC capacity and tracking type.

**Interconnection queue: GIS report**

- **Product:** EMIL **PG7-200-ER**, interconnection milestone and trend information for generation resources
  in the ERCOT region. Monthly xlsx since February 2017, with sheets for large gen, small gen and inactive
  projects.
- **Cost add-on:** since March 2026 a companion "Transmission Interconnection Costs" report is included
  (PG7-201-ER).
- **Columns** (from a third-party reconstruction; verify against the current file): INR, Project Name, GIM
  Study Phase, Interconnecting Entity, POI Location, County, CDR Reporting Zone, Projected COD, Fuel,
  Technology, Capacity (MW), screening/FIS dates, IA Signed, Financial Security/NTP, construction
  start/finish, energization/synchronization dates, TSP. There are no coordinates.
- **Scale:**
  - As of June 30, 2026, ERCOT tracked 1,949 active requests totaling 462,785 MW, including 161,554 MW of solar.
  - A third-party reconciliation of the June 2026 GIS report found only 63.3 GW of solar with signed
    interconnection agreements.

**Resource node / settlement point mapping: NP4-160-SG**

- "Settlement Points List and Electrical Buses Mapping," posted weekly with the model DB load.
- Its `Resource_Node_to_Unit` table maps RESOURCE_NODE → UNIT_SUBSTATION → UNIT_NAME.
- Its `Settlement_Points` table maps electrical bus → resource node → settlement load zone → hub.
- A third-party count of the August 19, 2026 file found 19,379 electrical buses and 1,036 resource nodes.
- This is how to attach **load zone, resource node and hub** to each solar unit for price/basis analysis.

**Unit-level output: 60-Day SCED Disclosure (NP3-965-ER)**

- The "60 Day SCED Gen Resource Data" endpoint (`/np3-965-er/60_sced_gen_res_data`) gives per-resource
  5-minute telemetered output, HSL, base points and status. Settlement metered net energy is a separate
  endpoint.
- Published with a 60-day lag.
- This is the only free source of **unit-level ERCOT solar generation and curtailment proxies (HSL − output)**.
- ERCOT issued at least four market notices on NP3-965-ER file problems in 2026, so build in validation checks:
  - M-B020626-01 (Feb 6): corrected ESR files for the 02/03 and 02/04 postings.
  - M-A021826-01 (Feb 18): missing RRS capability data for OD Dec 5–20, 2025.
  - M-B030626-01 (Mar 6): null CLR base points.
  - M-B040326-01 (Apr 3): nulls converted to zeros in AS Offers files for OD Dec 5, 2025–Feb 2, 2026.

**Regional solar actual/forecast**

- NP4-745-CD gives hourly regional actuals, STPPF/PVGRPP forecasts and COP HSL for six PV regions (rolling
  48 h history + 168 h forecast).
- NP4-746-CD gives 5-minute regional actuals; NP4-737/738-CD are system-wide.
- ERCOT's forecasts target HSL, i.e. uncurtailed generation potential. Do not score forecasts against
  curtailed actuals.

**Access**

- ERCOT Public API: `https://api.ercot.com/api/public-reports` (free registration and subscription key;
  OpenAPI specs on developer.ercot.com).
- The open-source **gridstatus** Python library wraps these. For example,
  `get_solar_actual_and_forecast_by_geographical_region_hourly` hits `/np4-745-cd/spp_hrly_actual_fcast_geo`,
  and the library also parses the GIS report and the NP4-160-SG mapping.
- GridStatus.io offers a hosted, paid version.

### 4. Cleanview

- **Underlying data:**
  - The documented API exposes an "EIA 860M data" endpoint (`/api/v1/eia-860m`) with plant_id, generator_id,
    lat/lon and nameplate MW.
  - Its interconnection endpoints mirror ISO queues; ERCOT records keep INR IDs (e.g.,
    `source_id: "30INR0053"`, `source_table: "ercot_queue"`).
  - Its docs note that ERCOT queue data lack lat/lon.
  - Value added: developer identification, daily refresh, satellite imagery, project feed/alerts.
- **Pricing** (pricing page): power projects platform **$9,000/yr** (up to 5 users, unlimited downloads); API
  **+$5,000/yr**; one-time download **$4,900**.
- **Free tier:** public state pages such as the Texas solar-farms page are viewable. Bulk export/API is paid.
- **Verdict:** it brings no new physical parameters (no tilt, tracking or DC beyond EIA). Worth buying only
  for pipeline/developer intelligence. For operating-plant parameters, the free EIA + USPVDB stack is equal
  or better and fully reproducible.

### 5. Other sources, ranked by usefulness

- **Catalyst Cooperative PUDL** (recommended as the ingestion layer):
  - Cleaned, keyed EIA-860/860M/923 (+FERC) tables.
  - Free on AWS Open Data at `s3://pudl.catalyst.coop/` (nightly, stable and versioned), as Parquet, SQLite
    and DuckDB.
  - Latest monthly release v2026.10.0 (October 15, 2026) updated EIA-860M through August 2026; EIA-860
    coverage runs 2001–2025.
  - Key tables: `out_eia__yearly_generators`, `core_eia860__scd_generators_solar` (primary key
    `plant_id_eia, generator_id, report_date`).
  - Example: `pd.read_parquet("s3://pudl.catalyst.coop/nightly/out_eia__yearly_generators.parquet")`.
- **LBNL Utility-Scale Solar (2025 edition data update):**
  - Project-level sample of EIA-860 projects >5 MWAC: 1,759 projects, 111 GW AC.
  - LBNL independently verifies much of the metadata (location, fixed-tilt vs tracking, azimuth) from
    satellite imagery.
  - Adds capacity factors, CapEx, PPA prices and ILR.
  - Best for validated tracking flags and performance benchmarks. The 2025 Data Update (October 2025) covers
    generators coming online through the end of 2024.
- **LBNL Queued Up 2026 edition** (data through end-2025, data file May 2026):
  - Project-level queue data from 7 ISOs + 50 non-ISO utilities (~98% of installed capacity); 14.85 MB XLSX
    at https://emp.lbl.gov/queues.
  - Compiled with Interconnection.fyi/GridTracker. No lat/long.
  - Good for a harmonized cross-ISO pipeline; ERCOT's own GIS report is fresher for Texas.
- **EPA eGRID:**
  - Plant-level generation, emissions and BA/subregion attributes keyed on EIA ORISPL.
  - Latest official is **eGRID2023rev2 (June 12, 2025)**. Third-party trackers reported eGRID2024 still
    unpublished by EPA as of October 2026.
  - Adds little for solar parameters.
- **Global Energy Monitor:**
  - Global Solar Power Tracker (operating ≥1 MW; prospective ≥20 MW), latest February 2026; the Global
    Integrated Power Tracker had a September 2026 release.
  - CC BY 4.0, phase-level, with ownership and coordinates.
  - For the U.S. it is largely EIA-derived.
- **TransitionZero Solar Asset Mapper (TZ-SAM):**
  - Satellite/ML-derived global polygons with estimated MW and construction date; updated quarterly.
  - Over 106,800 facilities globally as of end-2025.
  - **CC licence for non-commercial use only**; commercial licensing is separate.
  - Useful to catch sites not yet in EIA/USPVDB, and small (<5 MW) assets.
- **OpenStreetMap solar polygons / Global Renewables Watch (Microsoft/Planet/TNC):**
  - Satellite- or crowd-derived footprints; good for gap-filling and change detection.
  - Not verified in this research for current U.S. release cadence; treat as supplementary.
- **HIFLD:**
  - HIFLD Open was discontinued August 26, 2025; the power-plant layer moved to the restricted HIFLD Secure.
  - Frozen August 2025 snapshots survive (HSDL, DataLumos, SeerAI/Source Cooperative).
  - **Do not use** as a live source; it was EIA-derived anyway.
- **WRI Global Power Plant Database:**
  - Not maintained; last version 1.3.0 (2021); generation data only to 2019. **Avoid** for U.S. work.
- **NREL/DOE:**
  - NSRDB for irradiance/weather inputs paired with plant coordinates and tilt/azimuth.
  - PVDAQ offers performance time series for a small number of systems.
  - ATB covers cost/performance assumptions, not plant lists (already used in `assets/value.py`).
  - Not separately re-verified here.
- **SEIA Major Projects List, Interconnection.fyi, S&P Global, Wood Mackenzie, Enverus, Yes Energy:**
  - Commercial or partly commercial. Typical legacy platform contracts run $40k–80k/yr, per Cleanview's own
    comparison (a marketing claim).
  - Yes Energy and Enverus are strongest at ERCOT node-level mapping and generation. Consider them only if a
    vendor-maintained EIA↔ISO crosswalk is needed.
- **Texas-specific:**
  - PUCT filings and Texas Comptroller Chapter 313/JETI agreements can confirm project owners and phases, but
    are document-based, not datasets. Not evaluated in depth here.
- **Distributed solar** (out of scope):
  - LBNL Tracking the Sun (system-level, behind-the-meter).
  - EIA-861 / Electric Power Monthly small-scale estimates (state-level).

### Comparison table

| Source | Scope / threshold | Solar parameters | Spatial | IDs for joining | Latest (as of Nov 2026) / cadence | Access | Cost |
|---|---|---|---|---|---|---|---|
| EIA-860 | All US plants ≥1 MW; operable, proposed, retired | MW AC, DC, tracking type, tilt, azimuth, module tech, bifacial, COD, owner, BA | Point (plant) | EIA Plant ID + Generator ID | 2025 final, Sep 10 2026 / annual | XLS zip, PUDL | Free |
| EIA-860M | ≥1 MW; operating, planned, retired, canceled | MW AC (nameplate, summer/winter), status, COD, BA | Point | Plant ID + Gen ID | Sep 2026 data, Oct 23 2026 / monthly | XLS, API v2, PUDL | Free |
| EIA-923 / API facility-fuel | Plant-level generation | Monthly MWh | — | Plant ID | Monthly/annual | XLS, API | Free |
| USPVDB v4.0 | PV ≥1 MW, operational through Q4 2025 (6,611) | AC/DC, axis, tilt, azimuth, tech, battery, site type, agrivoltaic | **Polygon** + point | `case_id`, `eia_id` | Apr 2026 / annual, 1–2 yr lag | SHP, GeoJSON, CSV, REST API | Public domain |
| ERCOT CDR/MORA | ERCOT units (operating + planned) | Seasonal MW, county, zone, in-service year | County only | ERCOT unit code, INR | CDR Dec 2025 (May 2026 skipped); MORA Dec 2026 posted Oct 2 2026 / monthly | PDF/XLSX | Free |
| ERCOT GIS (PG7-200-ER) | ERCOT queue | MW, fuel, tech, county, POI, milestones, COD | County / POI | INR | Monthly (posted early following month) | XLSX, gridstatus | Free |
| ERCOT NP4-160-SG | All settlement points | Node ↔ unit ↔ load zone ↔ hub | Bus/substation | Unit name, resource node | Weekly | Zip/xls, API | Free |
| ERCOT NP3-965-ER | All ERCOT resources | 5-min output, HSL, status | — | Resource name | Daily, 60-day lag | API, zip | Free |
| ERCOT NP4-745/746-CD | 6 PV regions + system | Hourly/5-min actual, STPPF, PVGRPP, HSL | Region | — | Hourly / 5-min | API | Free |
| PUDL | EIA/FERC cleaned | All EIA fields, keyed | Point | Plant/Gen ID | v2026.10.0 (Oct 15 2026); nightly | S3 Parquet/SQLite | Free |
| LBNL Utility-Scale Solar | EIA PV >5 MWAC (1,759 projects) | Verified tracking, CF, CapEx, PPA | Point | EIA ID | 2025 edition / annual | XLSX | Free |
| LBNL Queued Up | 7 ISOs + 50 utilities queues | MW, type, status, dates | County (no lat/lon) | Queue IDs | 2026 ed. (data thru 2025) / annual | XLSX | Free |
| Cleanview | 860M + ISO queues + research | As EIA + developer, IA status | Point | Plant ID, INR | Daily | Web, CSV, API | $9k/yr; API +$5k; $4.9k one-off |
| GEM GSPT / GIPT | Global; op ≥1 MW, prospective ≥20 MW | MW, status, owner, start year | Point | GEM IDs (+ some EIA) | Feb 2026 (GSPT); Sep 2026 (GIPT) / semiannual | XLSX | CC BY 4.0 |
| TZ-SAM | Global, satellite-detected | Est. MW, construction date | **Polygon** | TZ cluster_id | Quarterly | GPKG/CSV, GEE | CC non-commercial |
| eGRID | Plants reporting to EIA | Generation, emissions | Point | ORISPL = EIA Plant ID | eGRID2023rev2 (Jun 2025) | XLSX | Free |
| HIFLD Open | (archived) | EIA-derived | Point | EIA ID | Frozen Aug 2025 | Archives only | Free |
| WRI GPPD | Global | Basic | Point | GPPD ID | v1.3.0 (2021), unmaintained | CSV | CC BY |

## Recommendations

**(a) U.S.-wide solar plant list with parameters**

1. Ingest EIA via PUDL (stable or nightly Parquet). Filter generators to `energy_source_code_1 = 'SUN'` /
   prime mover `PV`.
2. Take status and capacity from the latest EIA-860M snapshot. Left-join the latest final EIA-860 solar
   attributes on (`plant_id_eia`, `generator_id`).
3. For generators too new for 860 (CODs after 2025), flag tracking/tilt as missing. Optionally impute
   single-axis tracking (LBNL reports 99% of new project capacity chose it over fixed-tilt), labelled as imputed.
4. Aggregate to plant level, then join USPVDB v4.0 on `eia_id`. Watch `p_dig_conf` = 1/2 rows (multi-record
   polygons) and keep `case_id` as the polygon key.
5. Gap-fill post-2025 sites with TZ-SAM or OSM polygons by spatial join, if licensing allows (TZ-SAM is
   non-commercial).

**(b) Texas/ERCOT solar plant list**

1. Start from the EIA list with `plant_state = 'TX'`. Split by `balancing_authority_code` (ERCO vs
   SWPP/MISO/EPE) so SPS Panhandle plants are not treated as ERCOT.
2. Build an EIA↔ERCOT crosswalk:
   - Match MORA/CDR unit rows (unit code, county, MW, in-service year) to EIA generators by fuzzy name +
     county + capacity (±5%) + COD year.
   - Then attach resource node, substation and load zone from NP4-160-SG
     `Resource_Node_to_Unit`/`Settlement_Points`.
   - Expect manual review for multi-phase sites (ERCOT often splits plants into U1/U2 units that map to EIA
     generator IDs only loosely).
3. Use INR numbers (in the CDR and GIS report) to link planned EIA-860M units to the ERCOT queue for pipeline work.
4. Pull unit-level 5-minute output from NP3-965-ER (60-day lag) and regional hourly actual/forecast from
   NP4-745-CD via the ERCOT API or gridstatus.
5. Persist the crosswalk and re-validate it monthly when new MORA/GIS files post. Unit codes are stable, but
   new phases appear.

**Pitfalls to handle explicitly**

- **AC vs DC:**
  - EIA nameplate and ERCOT MW are AC (POI-limited).
  - EIA-860's DC field and USPVDB `p_cap_dc` are DC.
  - LBNL's Utility-Scale Solar 2024 Edition puts the 2023 median ILR (DC/AC) at 1.34: 1.32 for tracking
    projects and 1.38 for fixed-tilt. Its 2025 Data Update says the average ILR has held steady since 2017.
  - Model irradiance-to-power on DC, then clip at AC.
- **Granularity:** EIA generator ≠ ERCOT unit ≠ USPVDB polygon. Always aggregate to a common key before summing.
- **Lags:** EIA-860 is final about 9 months after the data year; USPVDB is 1–2 years behind; ERCOT SCED is
  60 days behind; 860M is about 1–2 months behind but preliminary and silently revised.
- **Curtailment:** ERCOT actuals are curtailed; HSL/forecasts are not.
- **Co-located storage:** EIA `3_4_Energy_Storage` and USPVDB `p_battery` flag it. ERCOT registers storage as
  separate ESR resources with their own INRs.

## Caveats

- Some facts come from secondary or third-party sources and should be spot-checked:
  - the GIS report column list (2023 third-party reconstruction)
  - the NP4-160-SG bus/node counts
  - the June 2026 signed-IA solar total
  - the PUCT approval of the skipped May 2026 CDR
  - the eGRID2024 status
  - the EIA-860M→860 revision magnitude
- EIA-923 details, the EIA Energy Atlas login status, NREL products, SEIA, Interconnection.fyi, Global
  Renewables Watch and Texas Comptroller data were not independently verified for November 2026 status.
- An ERCOT Market Reports file dated October 23, 2026 under the CDR heading could not be identified. Check
  whether it is an interim CDR update before assuming December 2025 is the latest.
- Cleanview's comparison with "legacy platforms" is vendor marketing.

## Sources

Primary and official:

- EIA-860: https://www.eia.gov/electricity/data/eia860/
- EIA-860M: https://www.eia.gov/electricity/data/eia860m/
- USPVDB: https://energy.usgs.gov/uspvdb/ · data https://energy.usgs.gov/uspvdb/data/ · API doc
  https://energy.usgs.gov/uspvdb/api-doc · ScienceBase https://www.sciencebase.gov/catalog/item/66707f69d34e89718fa3f82f
- ERCOT resource adequacy (CDR, MORA): https://www.ercot.com/gridinfo/resource
- ERCOT GIS report: https://www.ercot.com/mp/data-products/data-product-details?id=PG7-200-ER
- ERCOT interconnection costs: https://www.ercot.com/mp/data-products/data-product-details?id=pg7-201-er
- ERCOT settlement points mapping: https://www.ercot.com/mp/data-products/data-product-details?id=NP4-160-SG
- ERCOT regional solar actual/forecast: https://www.ercot.com/mp/data-products/data-product-details?id=NP4-745-CD
- ERCOT CDR skip notice: https://www.ercot.com/services/comm/mkt_notices/M-A051826-01
- ERCOT Monthly Operational Overview, June 2026:
  https://www.ercot.com/files/docs/2026/07/17/ERCOT-Monthly-Operational-Overview-June-2026.pdf
- PUDL data access: https://docs.catalyst.coop/pudl/en/latest/data_access.html · solar table
  https://data.catalyst.coop/preview/pudl/core_eia860__scd_generators_solar
- LBNL Utility-Scale Solar 2025 slides:
  https://emp.lbl.gov/sites/default/files/2025-10/Utility%20Scale%20Solar%202025%20Edition%20Slides.pdf
- LBNL Queued Up: https://emp.lbl.gov/queues
- gridstatus: https://opensource.gridstatus.io/en/latest/autoapi/gridstatus/ercot_api/ercot_api/
- Global Energy Monitor solar tracker: https://globalenergymonitor.org/projects/global-solar-power-tracker
- TransitionZero Solar Asset Mapper: https://www.transitionzero.org/products/solar-asset-mapper
- WRI Global Power Plant Database: https://github.com/wri/global-power-plant-database
- HIFLD archives: https://www.hsdl.org/hifld/ · https://source.coop/seerai/hifld
- Cleanview: https://cleanview.co/pricing · https://docs.cleanview.co/api-reference/endpoint/eia-860m ·
  https://docs.cleanview.co/api-reference/endpoint/ercot

Secondary and third-party (behind the items listed under Caveats):

- EIA-860M revision analysis: https://github.com/munimtechnologies/eia860m-slip/blob/main/docs/eia860-2025-scored.md
- CDR skip approval: https://tccfui.org/ercot-to-skip-two-key-reports-this-year-as-batch-zero-rush-continues/
- ERCOT queue by fuel and IA status: https://tafelpower.com/insights/ercot-queue-by-fuel-and-ia-status
- GIS report columns: https://hemanthhariharan.github.io/Projects/Final_Presentation_ERCOT_Queue.pdf
- eGRID 2024 status: https://emission-factors.com/blog/egrid-2024-preliminary-emission-factors.html
- HIFLD shutdown: https://www.datarescueproject.org/hifld-data-saved/
