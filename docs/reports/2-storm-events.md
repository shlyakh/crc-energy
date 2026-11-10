# Phase 2 report: NOAA Storm Events as a cleaned source on H3 cells, Texas

Date: 2026-11-10 · crc-sdk 0.11.1 · crc-framework 0.6.0 · NCEI snapshot 2026-11-10 (231 files, 360 MB) ·
awaiting review before Phase 3. Companion: [2-storm-events-comparison.md](2-storm-events-comparison.md) (S5).

## What was built

- **S1 fetch plan** (`src/crc_lab/storm_events/plan.py`): `StormEventsPlan` names the newest yearly `details`,
  `locations` and `fatalities` file per year from the NCEI directory listing, downloads to
  `data/cache/storm-events/ncei/`, records SHA-256, size, ETag, Last-Modified and retrieval time per file in a
  `manifest.json`, replays offline (`mode="offline"`) and re-downloads on `refresh`. Pattern: crc-sdk's
  `IBTrACSPlan`; no private crc-sdk helpers are imported. 231 files, 360 MB, 614 s on the first run.
- **S2 parser** (`parse.py`): every details row becomes a typed row with a documented schema (46 columns).
  Hail and thunderstorm wind in full: size in inches and mm; wind in knots and m/s with `wind_measure`
  (measured/estimated) and `wind_kind` (gust/sustained) from NCEI's EG/MG/ES/MS codes. Times: NCEI's split
  date fields read as local standard time and shifted by the `CZ_TIMEZONE` offset (the number when present,
  the standard offset of the bare label in the older files). Damage strings `10.00K` become dollars with a
  parse flag; the raw string is kept. Other event types pass through.
- **S3 geometry** (`geometry.py`): `locations`-file points (a path when several), else begin/end points, else
  the county (Census `cb_2024_us_county_500k`) or NWS public forecast zone (`z_16ap26`) polygon;
  `geometry_kind` records which. H3 r5 cells through `polyfill_wkb`: a path covers every cell it crosses
  (up to 26 for one event), a polygon every cell it intersects (16.5 on average for a zone).
- **S4 event table** (`table.py`): `data/storm-events/events.parquet` (166,214 Texas events 1950–2026,
  10.6 MB, zstd) with the data card embedded in the Parquet metadata and beside it as `events.card.json`:
  source, files and checksums, coverage, counts by type and geometry kind, parse flags, column notes, known
  biases.
- **S5 comparison** (`compare.py`): the seven tables of requirements §4.1 plus a time-convention check and
  three density maps, written to the companion report by the build (`--compare`), conclusion included,
  every number computed.
- **S6 explorer layer** (`explorer_layer.py`, `site/app.js`): events with a point or path as a packed binary
  file (24 bytes each; 107,549 events, 2.6 MB) drawn by deck.gl `ScatterplotLayer`, with year-range and
  event-type filters, a click panel linking to the NCEI event page, and the data card's biases in the caveat
  panel. Registry kind `points-binary` in `site/layers.json`.
- `just storm-events`, `just storm-events-compare`; `just all` now rebuilds it; the Pages workflow runs it.
  15 new offline tests on a fixed 2024 sample (89 real Texas rows, 29 event types) plus synthetic edge cases.

## Checks (the plan's "done" tests)

| # | Check | Result |
| --- | --- | --- |
| 1 | Yearly row counts match the NCEI files | **Pass.** 166,214 Texas rows in the table = 166,214 Texas rows read leniently from the 77 details files; every year equal; every raw `EVENT_ID` present. (The 1997 file has unescaped quotes in one row; pyarrow's reader coped, and this count check is the proof.) |
| 2 | The comparison report exists | **Yes**, with the seven tables, the time check, three maps and a computed conclusion. |
| 3 | Fort Bend County hail of 15 March 2024 is found with size and place | **Yes.** Event 1158847: 2.75 in (69.85 mm) at 29.39°N 95.83°W, cell `8548934ffffffff`, 02:59 local 16 March = 08:59 UTC (plus 2.50 in at 01:59 and 02:03). The largest Texas report in the snapshot is 7.02 in, Swisher County, 2024. |
| 4 | Events show in the explorer | **Yes**: layer toggle 40 ms, year filter 8 ms in headless Chrome; no script errors; the Phase 1 timings are unchanged. |
| 5 | Parse flags | Time: 166,212 ok, 2 without a resolvable zone label. Property damage: 129,009 parsed, 37,205 empty, 0 unparsed; crop damage 3 unparsed. Wind: 5,818 measured, 14,775 estimated, 145,621 not wind. |
| 6 | Geometry kinds | point 91,789 · path 15,760 · zone 44,064 · county 12,899 · none 1,702. |

## Findings worth knowing

- **The copy keeps NCEI's local time with no offset** (all 162,949 matched `begin_ts` equal the printed local
  time, none equal UTC). NCEI's own files label standard time only (`CST-6` even in summer), so summer times
  in both sources may be one hour off true local time; this table converts with the stated offset and says so.
- **Older files use bare labels** (`CST`, `PST`, `MST`: 71,674 rows, 1950–1990s) which the first parser left
  unconverted; a label table now resolves them. Two rows remain unresolved.
- **Retired forecast zones.** 1,694 zone-located events (1996–2023) carry zone numbers absent from the April
  2026 NWS zone file (e.g. TX258 "Guadalupe Mountains of Culberson County", TX074, TX257) and 8 county events
  from 1993–95 carry codes not in the county file; they have no cells (`geometry_kind = none`). An older zone
  shapefile would recover most of them.
- **County code against coordinates:** 5,486 of 107,515 county-located events (5.1%) have a point outside
  that county's polygon in NCEI itself; the copy keeps them as they are.
- **Hail and wind since 1996:** 40,532 hail and 26,710 thunderstorm-wind reports, the inputs to Phase 3.
- **Magnitudes, damage and points are identical** between NCEI and the copy where both have them; the copy
  lags NCEI (January versus August 2026 in this snapshot) and turns empty damage into 0.

## Deviations from the plan

- **No PMTiles.** Requirement S6 said "events as PMTiles points"; tippecanoe is not installed here and 107,549
  points fit in a 2.6 MB binary file that deck.gl draws directly, so PMTiles would add a toolchain for nothing.
  The registry kind is `points-binary`; a `pmtiles-points` kind can be added when buildings arrive (Phase 4).
- **Maps are density bins** (0.25°, log scale) rather than individual points, to keep the SVGs under 300 KB;
  events missing from the copy are drawn individually.
- **The copy is downloaded by hand** (`curl` to `data/cache/storm-events/sourcecoop/events.parquet`); the
  build's `--compare` reads it from there and records its SHA-256 and Last-Modified. A fetch step for it can
  follow if the comparison is to be rerun regularly.
- The Pages workflow now downloads the 360 MB snapshot on every deploy (about ten minutes); a cache step
  would cut that.

## Not done / for review

- Phases 3 and 4 remain deferred. Phase 3 can start from `events.parquet` (`hail_size_in`, `wind_knots`,
  `cells`, `year`).
- Event-table schema (requirements §9.2): column names follow NCEI's, lower-cased, with the derived columns
  named here; the copy's names (`begin_ts`, `damage_property`) were not adopted, since the copy drops the
  offset and the raw strings. Say if you prefer the copy's names for the shared columns.
- Questions for Earth Genome (§9.4) can now be asked with numbers: the time convention, the empty-damage
  zeros, the 1,044 null geometries, and the monthly cutoff.
