# Current plan: explore CRC data, then severe-storm sources and damage

Status: **draft for review** · 2026-11-10 · replaces the archived plan in `docs/archive/`

## Order of work

| Step | Output | Hours |
| --- | --- | --- |
| P1 | **Data explorer**: what is in CRC data today, shown as a catalogue and as map layers | 20–30 |
| P2 | **Storm Events source**: NOAA Storm Events as a cleaned event table on H3 cells, added to the explorer | 20–25 |
| P3 | **Hail and gust hazard curves** from P2, in CRC's hazard contract | 10–15 |
| P4 | **Assets**: solar farms (USGS / Berkeley Lab database) and real estate | 10–15 |
| P5 | **Damage curves and results**: hail and gust on solar farms and on buildings | 15–20 |
| Next | MRMS radar hail as a second source; comparison with P3 | 20–30 |

Each step ends in something visible in the explorer, so the explorer is also the demo.

## P1 — Data explorer

**Purpose.** Answer two questions without writing code: what does CRC data contain right now, and what does a
given layer look like on a map?

**Part A: catalogue page.**

- CRC Open: every hazard in the release from `HazardDataset.crc_open().catalog()` (63 in the release seen on
  2026-11-09), with unit, meaning, probability semantics, resolution, horizons, pathway and licence. The release
  ships a `_CATALOG.json`; the page is generated from it, so it stays correct when the release changes.
- Other sources reachable through crc-sdk: ERA5 (four recipes: `txx`, `tnn`, `rx1day`, `rx5day`), NOAA ISD and
  GHCNh stations, IBTrACS tracks, ECCC, HYDAT, USGS streamflow, NOAA water levels, JRC flood and drought, CHIRPS,
  CMIP6. For each: what it returns, coverage, licence.
- A "not in CRC" list: hail, gust, ice accretion, lightning, events. This is where later steps appear.

**Part B: map.**

- Static site: PMTiles + MapLibre on GitHub Pages, built with `crc_sdk.geometry.pmtiles`. No server.
- H3 cell layer coloured by one value, chosen with three selectors: hazard, horizon, return period.
- Click a cell: the full curve (value against return period) for that cell, and the cell's metadata.
- Overlay layers added by later steps: storm events (P2), derived hail and gust curves (P3), assets (P4), damage
  (P5).
- Caveat panel on every view: source, licence, cell size, and for CRC Open "high-emissions case (SSP5-8.5), not a
  forecast".

**Scope for the first version.** One region (Texas) and about eight hazards across the families (heat, cold, rain,
flood, wind, fire weather, drought), three horizons, three return periods. The catalogue page covers everything;
the map covers the sample. Widening the map is then a matter of tile size, not design.

**Licence.** CRC Open is CC BY-NC 4.0: a public, non-commercial page with attribution is within the licence.

**Decisions to make.**

1. Precomputed values in the tiles (simple, fixed return periods) or curve parameters in the tiles with
   evaluation in the browser through CRC's WebAssembly package (any return period, but the package is alpha)?
   Recommended: precomputed first.
2. Region and resolution of the first map: Texas at H3 res 5, or the contiguous US at res 4?

## P2 — Storm Events source

**Source of record: NCEI bulk files** (`https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/`): `details`,
`locations` and `fatalities` per year, 1950–2026.

**Source Cooperative copy (Earth Genome and partners).** Looked at on 2026-11-10:

| Question | What their page says |
| --- | --- |
| Do they clean the data? | Partly. They merge the yearly files and tables into one GeoParquet (about 2 million events, 188 MB) and add seven event-type families. "Data cleaning procedures" are mentioned but not described |
| Geometry | One point per event: the first reported point, or the centroid of the county or forecast zone. About 1% have no geometry |
| Known issues they note | Some records have county codes that conflict with their coordinates; no fix is described |
| Coverage | 1950–1954 tornadoes only; 1955–1995 tornadoes, thunderstorm wind and hail; all 55 types from 1996 |
| Updates | Aim is monthly; the page was last updated 17 Sep 2025 |
| Licence, code, contact | None stated |

**How to use it.** Good for the explorer layer and for cross-checking counts. Not enough alone for hazard curves:
one point per event drops storm paths, and it is not confirmed that hail size and wind magnitude are kept. So P2
reads NCEI directly and compares against their file.

**To ask Earth Genome** (not answered on their page): the licence; the cleaning steps; whether coordinate errors
are corrected; whether magnitude and magnitude-type columns are kept; whether the processing code is public.

**Steps**

1. Fetch plan modelled on crc-sdk's `IBTrACSPlan`: list the folder, take the latest file per year, cache, record
   names and checksums.
2. Parse `details` and `locations`: event types; hail size (inches); wind magnitude (knots) with its type
   (measured or estimated, gust or sustained); damage strings to numbers.
3. Geometry: begin and end points where present, otherwise county or zone; keep a field saying which.
4. H3 cells (res 5); a path covers every cell it crosses.
5. One Parquet event table and a manifest. First pass cleans hail and thunderstorm wind fully and passes other
   types through.
6. Tests: row counts per year against the source and against the Source Cooperative file; a few known events.
7. Explorer: events as a point layer with type and year filters.

## P3 — Hail and gust curves

1. Per cell and year: largest hail size and largest thunderstorm gust. Years without a report are zeros.
2. Pool neighbouring cells before fitting to reduce the population bias; record the rule.
3. Use years from 1996; test sensitivity to the start year.
4. Bring into CRC through its own route for outside data, `HazardDataset.from_table(...)` with a fit policy
   (`probability_semantics="annual_value_distribution"`, unit, source). The result is a canonical dataset that
   `for_assets` evaluates like any CRC hazard.
5. Explorer: two new hazard layers, shown beside CRC Open's wind layer for contrast.

## P4 — Assets

**Solar farms.** USGS and Berkeley Lab US Large-Scale Solar Photovoltaic Database, version 4.0 (April 2026): 6,611
facilities of 1 MW or more with array boundaries; public domain.

**Is it a CRC source?** Not in the sense of the others. CRC's sources are hazards. For assets, CRC defines only a
table shape (an identifier and a location; extra columns pass through) and crc-sdk has no asset loaders. So this is
a small loader in this repo that returns a CRC-ready asset table, with capacity, year and mounting type as extra
columns. It could be offered upstream as a first "asset source", which would be a new category for them.

**Real estate.** Source to be chosen (open question 3). Candidates, none checked yet: the US Army Corps National
Structure Inventory (one point per structure with occupancy type and value); FEMA USA Structures; Overture Maps
buildings.

## P5 — Damage curves and results

| Curve | Intensity measure | Basis |
| --- | --- | --- |
| Hail on PV modules | hail diameter | module hail test point (25 mm ice ball) as lower anchor; variants for glass thickness and stowed trackers |
| Gust on PV racking and trackers | 3-second gust | design and stow wind speeds |
| Hail on roofs | hail diameter | published roofing damage thresholds (to be sourced) |
| Gust on buildings | 3-second gust | Hazus wind damage functions by building class |

Each is a CRC impact definition with parameters and sources in one file; ranges shown; nothing treated as
verified until checked against the original study.

Results: expected damage share per asset; `compute_risk` across solar farms with the independence caveat stated;
one event check (Fighting Jays solar farm, Fort Bend County, 15 March 2024). Explorer: assets coloured by result.

## Next — MRMS radar hail

A second, report-independent hail source: MESH on a 1 km grid, public on AWS. Hail only; short record. Kept as the
step after P5, ending in a cell-by-cell comparison with the P3 curves.

## Open questions

1. Explorer: precomputed values or in-browser curve evaluation? (Recommended: precomputed.)
2. Explorer: Texas at res 5, or contiguous US at res 4, for the first map?
3. Real estate asset source.
4. Event-table schema: propose a minimal one here, to offer upstream later?

## Not yet verified

- Storm Events magnitude-type codes and the exact pre-1996 coverage (the Source Cooperative page agrees with the
  1955 and 1996 breaks).
- Whether the CRC WebAssembly package matches Python 0.6.0 results.
- Tile sizes for a national map.
- Every damage-curve parameter; the real-estate data sources.

## Sources

- CRC Open guide (crc-sdk `docs/sources/crc-open.md`) and bring-your-own-data guide (`docs/bring-your-own-data.md`) — https://github.com/RiskThinking/crc-sdk
- Storm Events bulk files — https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/
- Earth Genome Storm Events on Source Cooperative — https://source.coop/earthgenome/storm-events-db
- Earth Genome post on the Storm Events explorer (18 Dec 2025) — https://www.earthgenome.org/blog/enhancing-science-data-access-building-the-storm-events-database-explorer
- Storm Events Database Explorer — https://stormevents.internetofwater.app
- USPVDB v4.0 — https://www.usgs.gov/data/united-states-large-scale-solar-photovoltaic-database-ver-40-april-2026
- MRMS on AWS Open Data — https://registry.opendata.aws/noaa-mrms-pds
