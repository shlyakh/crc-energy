# Phase 4 report: solar plants, their value, and hail at the asset

Date: 2026-11-10 · crc-sdk 0.11.1 · crc-framework 0.6.0 · awaiting review before Phase 5 (hail impact functions).
Companions: [4-hail-exposure-sensitivity.md](4-hail-exposure-sensitivity.md),
[4-real-estate-fort-bend.md](4-real-estate-fort-bend.md). Every number here is computed by the builds.

## What was built

- **A1 solar asset table** (`src/crc_lab/assets/solar.py`): the USGS / Berkeley Lab solar database, release
  `uspvdb_v4_0_20260414`, cached with its SHA-256. Texas: 187 plants, 23,033 MW AC, with capacity, year online,
  mounting, module technology and the array boundary. Output `data/assets/solar_tx.parquet` with an embedded card.
- **A4 value** (`value.py`): replacement value = AC capacity × overnight capital cost. The cost is NREL's Annual
  Technology Baseline 2025, utility PV, 2024: 1,300.56 $/kW AC, extracted once from the 320 MB ATB table into a
  small committed reference file that records the source file's SHA-256. Texas total: $29.96 billion. One cost
  year applies to every plant, because replacement value is today's cost to rebuild.
- **H1–H3 hail at the asset** (`exposure.py`): around each plant a circle grows until it holds 100 located hail
  reports (1996–2025; 39,624 in Texas), never smaller than 10 km and never larger than 75 km. Reports inside give
  the size distribution; count over area and years gives a report rate. The annual chance of hail at the plant is
  `1 − exp(−rate × footprint)` with a footprint of 25 km² per report, **a placeholder with no source**.
- **C4 return levels**: hail and gust return levels at each plant from the Phase 3 cell curves through `for_assets`.
- **A3 explorer**: a new source "Solar plants with value and hail exposure" in the experimental group; clicking a
  plant shows capacity, value and its basis, the hail circle, sizes and chances, gust return levels and the cell's
  hail curve.
- **H4 sensitivity note** and **A2 real-estate note** (below). `just assets`, `just assets-sensitivity`; in
  `just all` and the Pages workflow. 6 new offline tests.

## Results

| Measure across the 187 plants | 10th percentile | Median | 90th percentile |
| --- | --- | --- | --- |
| Radius of the hail circle (km) | 13.9 | 26.0 | 39.2 |
| Annual chance of hail of 1 inch or more | 0.011 | 0.029 | 0.100 |
| Annual chance of hail of 2 inches or more | 0.0009 | 0.0038 | 0.0150 |

Three plants in Presidio and Culberson counties do not reach 100 reports within 75 km and are flagged.

## Two findings that matter for Phase 5

- **The method understates the plant that was actually hit.** Fighting Jays in Fort Bend County was badly damaged
  by hail in March 2024. Its circle is 35 km wide, holds 101 reports with a largest size of 69.8 mm, and gives an
  annual chance of 2-inch hail of 0.15%. The five Fort Bend plants sit between 0.08% and 0.17%. Rural plants are
  far from reporters, so report-based exposure is low exactly where the plants are. Radar hail (MRMS) is the
  known fix and is listed for after this effort.
- **The highest values are small plants in cities.** The top five by annual chance are 1 to 8 MW sites in
  Travis, Williamson, Collin and Tarrant counties, all at the 10 km minimum radius with 105 to 232 reports. That
  is reporting density, not more hail.

The sensitivity note shows the footprint placeholder moves the annual chance almost in proportion (median 0.08%
at 5 km², 0.38% at 25 km², 1.5% at 100 km²), while N and the minimum radius move the median plant little.

## Real estate in Fort Bend County (A2)

| | National Structure Inventory | USA Structures |
| --- | --- | --- |
| Records | 305,551 points | 265,565 footprints |
| Carries | occupancy type, building type, structure value ($187.6 billion) and contents value | footprint polygon, occupancy class, area (78.3 km² in all) |

79.5% of inventory points fall inside a footprint, carrying 80.3% of structure value; 85.4% of footprints hold a
point. On joined pairs the occupancy classes agree for 96.2%. **Recommendation:** use the inventory as the asset
table, since it has the values and building types damage curves need, and join footprints for roof area where a
point matches. The inventory states where its own footprints came from (mostly Bing), which explains part of the
20% that do not join. Neither source records roof cover, so the roof class in the hail impact draft stays a
statewide assumption.

## Corrections and caveats

- The radius table first written into the plan was wrong: DuckDB's `ST_Distance_Sphere` expects latitude before
  longitude. The plan is corrected, the Phase 4 code uses its own great-circle distance with a test, and the same
  call in the Phase 2 comparison is fixed (its results were unaffected, all distances there being zero).
- The ATB data file does not state its dollar year; the card says so and does not guess it.
- A plant is treated as its centroid. The largest plants cover several km², which is not added to the footprint.
- Value is a national benchmark per kW, not a plant's own cost or insured value.

## Update, same day: border clip, plant size, footprint evidence

After review the exposure gained two corrections. The circle is clipped to Texas (the event table has no reports
from Mexico, the Gulf or other states), and each plant is a disc of its own array area, so a large plant is a
larger target. Median annual chance of hail of 2 inches or more rose from 0.38% to 0.74%; Fighting Jays from
0.15% to 0.37%. The results table above predates this; current values are in the sensitivity note and the
asset table. The footprint stays a placeholder, now bracketed by published sizes: see
[../plan-hail-exposure.md](../plan-hail-exposure.md), which also plans the reporting-bias correction and radar.

## For review

- Is 25 km² a reasonable placeholder footprint, or do you have a better figure? It scales every annual chance.
- Given the Fighting Jays result, should Phase 5 losses be shown with a clear "report-based, likely low for rural
  plants" label, or wait for a radar hail source?
