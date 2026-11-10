# Requirements: CRC data explorer and severe-storm sources (Texas)

Status: **agreed 2026-11-10** · no code has been written yet

This is the brief for a separate Claude Code effort. Steps are in
[implementation-plan.md](implementation-plan.md). Background on events in CRC is in
[primers/event-sources-in-crc.md](primers/event-sources-in-crc.md). Earlier requirements are in `archive/`.

## 1. Goals

1. See what is in CRC data today, as a catalogue and as map layers, without writing code. **← current work**
2. Add NOAA Storm Events as a source, cleaned and placed on H3 cells. *(coming; not started)*
3. Derive hail and thunderstorm-gust hazard curves from it and bring them into CRC. *(coming; not started)*
4. Add two asset sets: solar farms and real estate. *(coming; not started)*
5. Show every result in the same explorer.

Decided 2026-11-10: build goal 1 with the eight CRC Open hazards first and review it before goals 2–4
begin. The explorer lists hail and gust in its "not in CRC Open" list, marked as planned.

Region for everything: **Texas**. Later, not in this effort: MRMS radar hail; damage curves and loss results.

## 2. Classification

USE = CRC as shipped. OUTSIDE = external data or tools. EXTEND = new data, definitions or functions on CRC.

## 3. Explorer

| ID | Requirement | Tag |
| --- | --- | --- |
| E1 | Catalogue page listing every CRC Open hazard with unit, meaning, probability semantics, resolution, horizons, pathway and licence, generated from the release's own catalogue (`HazardDataset.crc_open().catalog()`) | USE |
| E2 | Catalogue also lists the other sources crc-sdk reaches (ERA5 recipes, stations, tracks, streamflow, water levels, flood, drought) with what each returns, coverage and licence, and a "not in CRC" list | USE |
| E3 | Map of Texas with an H3 cell layer coloured by one value chosen by hazard, horizon and return period. Version 1 loads eight hazards (hottest day, coldest night, wettest day, river flood, wind, fire weather, drought index, hot days); the selector lists all 63, with those not yet loaded marked as such | USE + OUTSIDE |
| E4 | Click a cell: its full curve (value against return period) and its metadata. The per-hazard file carries the curve evaluated by crc-sdk at fixed return periods (2, 5, 10, 20, 50, 100, 200, 500 years) plus the raw curve parameters; the browser draws and interpolates, never re-implements the curve; no API in version 1 (decided 2026-11-10) | USE |
| E5 | Layers can be switched on and off; later steps add layers (events, derived curves, assets) without redesign | OUTSIDE |
| E6 | A caveat panel on every view: source, licence, cell size; for CRC Open "high-emissions case (SSP5-8.5), not a forecast" | — |
| E7 | Fast: first view under 2 seconds on a laptop; switching hazard under 0.5 seconds | — |
| E8 | Deployable on a server you control with one command; also works as static files where no backend is needed | OUTSIDE |
| E9 | Layers are described in one registry file (name, source, unit, licence, file, style), so adding a layer is an entry, not code | EXTEND |

### 3.1 Map and UI: options and recommendation

A fact that drives the choice: Texas is about 695,000 km² and an H3 resolution-5 cell averages 253 km², so the
whole state is roughly **2,700 cells**. A cell layer that small needs no tiling. Points are different: events run
to hundreds of thousands and buildings to millions.

| Option | How it works | Speed | Server needs | Fit |
| --- | --- | --- | --- | --- |
| A. MapLibre + PMTiles, static | Everything pre-built into tile archives; browser reads byte ranges | Very fast | Any web server | Good for points and footprints; rigid for cells (re-tile to add a value) |
| B. MapLibre + deck.gl H3 layer | Browser draws hexagons from a list of cell ids and values; no geometry sent | Very fast at this size | Any web server | Best for the hazard cells: one small file per hazard, instant switching |
| C. Tile server (Martin) | Serves tiles from PMTiles or PostGIS; a DuckDB/GeoParquet backend was built in 2026 (maturity not checked) | Fast | One Rust binary | Worth it only if data changes often or filters must run server-side |
| D. DuckDB in the browser | Browser queries Parquet files directly | Slow first load, flexible after | Any web server | Good for an ad-hoc query panel, not for the main map |
| E. Python app (Streamlit, Panel, notebooks) | Server renders on each interaction | Slowest | Python process | Fast to build, poor fit for "fast and deployable" |

**Recommendation: A and B together, with a small optional API.**

- Base map and point layers (events, assets, buildings): MapLibre with PMTiles.
- Hazard cells: deck.gl's H3 layer over MapLibre, fed by one compact file per hazard holding cell id and the
  values for each horizon and return period.
- Curve on click: read from the same per-hazard file, which includes curve parameters. A small read-only API
  (FastAPI + DuckDB over the Parquet files) stays an option for later.
- Deployment: one container (Caddy or nginx serving static files and PMTiles; the API as an optional second
  service). The static part can also go to GitHub Pages unchanged.

This keeps the demo fast, has no database to run, and leaves room for server-side queries later.

To confirm during the build: deck.gl H3 layer and MapLibre versions that work together; whether to ship curve
parameters to the browser.

## 4. Storm Events source

| ID | Requirement | Tag |
| --- | --- | --- |
| S1 | Fetch NCEI bulk files (`details`, `locations`, `fatalities`) with a cached snapshot, checksums and a manifest, following crc-sdk's `IBTrACSPlan` pattern | EXTEND |
| S2 | Clean hail and thunderstorm-wind events fully: size in inches and mm; wind in knots and m/s with its type (measured or estimated, gust or sustained); dates in UTC; damage strings as numbers. Other event types pass through | EXTEND |
| S3 | Geometry: begin and end points where given, otherwise county or forecast zone; a field records which. H3 cells at resolution 5; a path covers every cell it crosses | EXTEND |
| S4 | One Parquet event table with a documented schema, plus a data card stating coverage and known biases | EXTEND |
| S5 | **Two-source comparison for Texas**: NCEI direct against the Source Cooperative (Earth Genome) copy; see section 4.1 | OUTSIDE |
| S6 | Events appear in the explorer as a point layer with type and year filters | — |

Source Cooperative is used for S5 and as a quick layer. NCEI is the source of record, because the copy keeps one
point per event (paths are lost), does not describe its cleaning, and states no licence.

### 4.1 What the two-source comparison must report

For Texas, by year and event type:

1. Event counts in each source and the difference.
2. Events present in one and missing in the other, matched on NOAA's event id.
3. For matched events: distance between the two locations; share where the copy used a county or zone centroid.
4. Whether hail size, wind magnitude and magnitude type are present in the copy and equal to NCEI.
5. Damage fields: equal or not, and how each source parsed them.
6. Records whose county code conflicts with their coordinates, and what each source did with them.
7. Latest date covered by each.

Output: a short report with one table per item and three maps (all events, hail, thunderstorm wind), and a
conclusion on what the copy can and cannot be used for.

Not done yet: the session that wrote this could not reach either data host, so no numbers exist. This is the
first analysis task of the build.

## 5. Hail and gust curves

| ID | Requirement | Tag |
| --- | --- | --- |
| C1 | Per cell and year, largest hail size and largest thunderstorm gust, 1996 onward; years without a report are zeros | EXTEND |
| C2 | Pool neighbouring cells before fitting to reduce reporting bias; record the rule; show sensitivity to it and to the start year | EXTEND |
| C3 | Bring both into CRC with `HazardDataset.from_table(...)` and a fit policy stating unit, meaning, source and `probability_semantics="annual_value_distribution"` | USE |
| C4 | Evaluate with `for_assets(...)` at the asset sets of section 6 | USE |
| C5 | Both curves appear in the explorer as hazard layers like any CRC Open hazard | — |
| C6 | Data card: these are report-based curves; an empty cell may be unobserved | — |

## 6. Assets

| ID | Requirement | Tag |
| --- | --- | --- |
| A1 | Solar farms: USGS / Berkeley Lab solar database v4.0 (April 2026; 6,611 facilities of 1 MW or more, with array boundaries; public domain), Texas subset, as a CRC-ready asset table with capacity, year and mounting type | OUTSIDE → USE |
| A2 | Real estate: explore **both** federal sources for one Texas county first (Fort Bend, where the March 2024 hail fell), then decide | OUTSIDE |
| A3 | Assets appear in the explorer; clicking one shows its hail and gust return levels | — |

The solar database is not a CRC source in the sense the hazards are. CRC defines only the shape of an asset table
(identifier and location; other columns pass through) and has no asset loaders. A1 is therefore a loader in this
repo. Offering it upstream would propose a new category.

### 6.1 The two real-estate sources

| | National Structure Inventory (US Army Corps) | USA Structures (FEMA / Oak Ridge) |
| --- | --- | --- |
| Geometry | One point per structure | Building footprint polygons, structures over 450 sq ft |
| Useful fields | Occupancy type, building type (wood, masonry, steel, manufactured), structure value, contents value | Occupancy class and primary occupancy, address, height; unique id |
| Strength for this work | Values and building type, which damage curves need | Roof footprint area, which hail exposure needs |
| Access | API and downloads (details to confirm) | State downloads; also GeoParquet and PMTiles on Source Cooperative |
| Licence | Not yet checked | US government work |

They complement each other. A2 reports, for the county: counts in each, agreement on occupancy, and how well
points join to footprints.

## 7. General requirements

| ID | Requirement |
| --- | --- |
| G1 | Pin `crc-sdk` and `crc-framework`; record versions in every output |
| G2 | Every dataset has a data card: source, date fetched, licence, coverage, known biases |
| G3 | Licences respected in what is published: CRC Open is non-commercial with attribution; NOAA and USGS data ask for attribution |
| G4 | Cell-level results are labelled regional screening (a cell is about 253 km²) |
| G5 | One command rebuilds every data file and the site from the sources |
| G6 | Tests for each parser and for the comparison counts |

## 8. Out of scope here

MRMS radar hail; joint-loss event sets; anything outside Texas; CMIP beyond displaying CRC Open as it is.

Damage curves for hail and gust on solar and real-estate assets are being researched separately. This effort
stops at hazard return levels at each asset; damage and loss numbers follow once that research is in.

## 9. Open questions

1. Decided: curve parameters go to the browser; no API in version 1.
2. Event-table schema: adopt the Source Cooperative column names where they exist, to make comparison easy?
3. Real-estate source: decided after A2.
4. Questions for Earth Genome (licence, cleaning steps, coordinate fixes, magnitude columns, code): hold until
   the two-source comparison has been run and the data looked at.

## 10. Not yet verified

- Verified in Phase 2 (2026-11-10): magnitude-type codes are EG/MG (estimated/measured gust) and ES/MS
  (sustained), from NCEI's bulk-format document; hail carries no type. Coverage: tornado only 1950–54; tornado,
  thunderstorm wind and hail 1955–95; all types from 1996 (NCEI database details page, Earth Genome README).
- National Structure Inventory access and licence.
- Martin's DuckDB backend maturity (not needed in version 1).
- Verified in Phase 1 (2026-11-10): deck.gl 9.4.0 with MapLibre 6.16.0 and h3-js 4.5.0 work together; Texas has
  2,566 resolution-5 cells intersecting the state polygon (118,482 at resolution 7, of which 16,892 carry river
  flood curves).

## Appendix: all hazards in CRC Open

From the saved output of crc-docs' `notebooks/sources/crc_open_hazards.ipynb` (release seen 2026-11-09). All are at
H3 resolution 5 except the three flood layers at resolution 7. Horizons run 2025–2090 (flood layers to 2100;
`cyclone` 2010–2100). One pathway: SSP5-8.5. The eight loaded in version 1 are in bold. Meanings in plain words
are to be taken from the catalogue during the build, not guessed.

| Family | Hazards (unit) |
| --- | --- |
| Heat | **`tx_max`** (K), `tx_mean` (K), `tx_min` (K), `tg_max` (K), `tg_mean` (K), `tg_min` (K), `at` (K), `heat_index` (°C), `humidex` (°C), `wbgt` (K), **`hot_days`** (days), `summer_days` (days), `tropical_nights` (days), `heat_wave_frequency` (events), `heat_wave_index` (days), `heat_wave_max_length` (days), `heat_wave_total_length` (days), `hot_spell_frequency` (events), `hot_spell_max_length` (days), `cooling_degree_days` (K days) |
| Cold | **`tn_min`** (K), `tn_mean` (K), `tn_max` (K), `windchill` (°C), `frost_days` (days), `ice_days` (days), `maximum_consecutive_frost_days` (days), `daily_freezethaw_cycles` (days), `cold_spell_days` (days), `cold_spell_frequency` (events), `heating_degree_days` (K days) |
| Temperature range | `dtr` (K), `dtrmax` (K), `dtrvar` (K), `etr` (K) |
| Rain and snow | **`rx1day`** (mm/day), `rx5day` (mm), `prcptot` (mm), `liquidprcptot` (mm), `solidprcptot` (mm), `sdii` (mm/day), `wet_days` (days), `maximum_consecutive_wet_days` (days) |
| Flood | **`rflood`** (m), `cflood` (m), `inundation` (m) |
| Drought and water | **`spei`** (index), `dry_days` (days), `max_consecutive_dry_days` (days), `pet` (mm/day), `water_budget` (kg m⁻² s⁻¹) |
| Wind | **`wind_max_daily_max`** (m/s), `wind_max_daily_mean` (m/s), `calm_days` ((m/s) days), `cyclone` (m/s) |
| Fire weather | **`fwi`**, `isi`, `bui`, `ffmc`, `dc`, `dmc` (all indices) |
| Agriculture | `growing_degree_days` (K days), `corn_heat_units` (CHU) |

Not in CRC Open: hail, gust, lightning, ice accretion, wave height, water temperature, streamflow.

## Sources

- crc-sdk docs (`sources/crc-open.md`, `bring-your-own-data.md`, `sources/observations.md`) — https://github.com/RiskThinking/crc-sdk
- Storm Events bulk files — https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/
- Earth Genome Storm Events copy — https://source.coop/earthgenome/storm-events-db
- Solar database v4.0 — https://www.usgs.gov/data/united-states-large-scale-solar-photovoltaic-database-ver-40-april-2026
- National Structure Inventory field description — https://gee-community-catalog.org/projects/nsi/
- USA Structures — https://gis-fema.hub.arcgis.com/pages/usa-structures · https://source.coop/wherobots/usa-structures
- Martin tile server — https://maplibre.org/martin/sources-tiles/ · https://maplibre.org/news/2026-08-15-gsoc-martin-duckdb/
