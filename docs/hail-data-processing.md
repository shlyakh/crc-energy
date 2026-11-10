# How hail data is processed in crc-lab

Written 2026-11-10. It follows hail from the raw sources to the numbers shown for a solar plant: what each step
does, where the code is, what it produces, and what it assumes. Choices with alternatives are charted in
[decisions.md](decisions.md); sources are listed in [data-sources.md](data-sources.md). Counts are from the
builds of 2026-11-10.

## The flow in one view

```text
NOAA Storm Events (reports) ─► cleaned event table ─► annual maxima per cell ─► hail curve per cell (CRC format)
            │                          │
            │                          └─► located hail reports ──┐
            │                                                     ├─► hail at a plant: rate, sizes, annual chance
Census people, roads ─► reporting-rate model ─► correction ───────┤        (with and without correction)
                                                                  │
MRMS radar hail size (grid, 2020 on) ─► hail days, swath areas ───┤─► radar hail days at a plant
NEXRAD hail signatures (points, 1995 on) ─► hail days per cell ───┘─► four-source comparison per cell
EIA plant list + solar database polygons + NREL cost ─► plants with area and value
```

## 1. Storm reports become an event table

Code: `src/crc_lab/storm_events/`. Report: [reports/2-storm-events.md](reports/2-storm-events.md).

1. **Snapshot.** The newest yearly `details`, `locations` and `fatalities` files are downloaded from NCEI with a
   SHA-256 per file (231 files, 360 MB). NCEI rewrites files in place, so the manifest is what pins a build.
2. **Parse.** Each row becomes a typed record. For hail: size in inches as reported, and in millimetres
   (× 25.4). Times are read as local standard time and shifted to UTC with the zone's offset. Damage strings
   such as `10.00K` become dollars. Anything unparseable stays empty with a flag; nothing is guessed.
3. **Locate.** A report's place is, in order: the points in the `locations` file (a path if several), the begin
   and end coordinates, the county polygon, the forecast-zone polygon. A field records which.
4. **Cells.** Each event gets the H3 resolution-5 cells it touches (a cell is about 253 km²). A path covers every
   cell it crosses.

Result: 166,214 Texas events, 55,572 of them hail. For 1996–2025 there are 39,767 hail reports, 39,624 with a
point and a size. The same snapshot gives 37,861 located hail reports in Oklahoma, New Mexico, Arkansas and
Louisiana, kept in a small side table for use near the state line.

Assumption to remember: a report exists only where someone saw the hail and told the Weather Service. Size is
usually an estimate against a coin or a ball.

## 2. A hail curve for every cell

Code: `src/crc_lab/curves/`. Report: [reports/3-curves.md](reports/3-curves.md).

1. **Annual maximum.** For each Texas cell and each year 1996–2025: the largest reported hail size, or zero if
   there was no report. 73% of cell-years are zero.
2. **Pooling.** A cell's sample is its own 30 values plus those of its six neighbours (210 values). This steadies
   the estimate and smooths real differences over about 35 km.
3. **Fit.** crc-sdk fits the sorted sample as a Gumbel distribution with a point mass at zero for the hail-free
   years (`HazardDataset.from_table`, lower bound 0). The result is a standard CRC hazard dataset: horizon 2025,
   pathway `observed`.
4. **Use.** `for_assets` reads the 1-in-N-year hail size at any point. The explorer shows the curve per cell.

Assumption: the curve describes reports in a 253 km² cell and its neighbours, not hail at a point.

## 3. Hail at one plant, from reports

Code: `src/crc_lab/assets/exposure.py`, `build.py`. Reports: [reports/4-assets.md](reports/4-assets.md),
[reports/4-hail-exposure-sensitivity.md](reports/4-hail-exposure-sensitivity.md).

1. **Circle.** Around the plant a circle grows until it holds 100 located hail reports, from Texas and the four
   neighbouring states. It is never smaller than 10 km, so a plant near a town does not inherit the town's
   report density, and never larger than 75 km, beyond which the plant is flagged.
2. **Clip.** The circle's area counts only where reports can exist: the five states. Mexico and the Gulf are cut
   away.
3. **Rate and sizes.** Reports in the circle ÷ (clipped area × 30 years) = reports per km² per year. The reports
   also give the local sizes: median, 90th percentile, largest, and the rate at or above 1, 1.5, 2 and 3 inches.
4. **From a rate to a hit.** A report is a point but hail covers ground. Each report is given a footprint of
   25 km², and the plant is a disc of its own array area. A hit is when the two overlap, so the target area is
   π (r_footprint + r_plant)². Annual chance = 1 − exp(−rate × target area).

Result per plant: circle radius, reports used, rate, sizes, annual chance of hail of 1 inch or more and of
2 inches or more.

Assumptions: 25 km² per report (measured radar swaths over Texas have a median of 16 km² and a mean of 61 km²);
reports are independent; the plant is a disc.

## 4. Correcting for where reports come from

Code: `src/crc_lab/assets/reporting_bias.py`. Report: [reports/5-reporting-bias.md](reports/5-reporting-bias.md).

1. **Count** hail days per Texas cell, 1996–2025.
2. **Covariates** per cell: people per km² (Census 2020 tracts) and kilometres of primary and secondary road per
   km² (Census TIGER 2024).
3. **Model.** Reported hail days = years × true rate of the region × reporting rate, where the reporting rate
   rises from a floor toward 1 with people and roads:
   `floor + (1 − floor) × (1 − exp(−(b_pop × people + b_road × roads)))`. The true rate is one value per
   larger region (73 regions). Fitted: floor 0.059, b_pop 0.0104, b_road 1.21. Roads explain more than people.
4. **Apply.** For a plant, the reporting rates of the cells inside its hail circle are averaged, and the report
   rate is divided by that average. Both versions are kept: every corrected column sits beside the uncorrected one.

Assumption that carries the result: hail climate is flat inside a region while reporting varies cell by cell.
Radar is the check: at the median plant, radar hail days are 2.7 times the uncorrected report-based figure and
0.9 times the corrected one.

## 5. Radar hail size (MRMS)

Code: `src/crc_lab/radar/mrms.py`, `analysis.py`, `build.py`. Report: [reports/4-radar-hail.md](reports/4-radar-hail.md).

1. **Pull.** One file per day from NOAA's open archive: the 24-hour maximum of radar hail size (MESH) valid at
   12 UTC, about 1 km grid. 1,903 days from 15 October 2020 to the end of 2025; two days are missing.
2. **Reduce.** Each day is clipped to a Texas box and only cells of 19 mm or more are kept (13 MB in all).
3. **Hail day.** A day counts where the value reaches **30 mm**, the threshold in use, with 50 mm beside it.
4. **At a plant.** Days on which the maximum over the plant's array area reaches the threshold; and the same
   averaged over 25 km around the plant, which is steadier over a five-year record.
5. **Swaths.** Connected areas at or above the threshold on one day give measured hail areas for Texas.

Test case: the night of 15–16 March 2024, radar shows up to 105 mm over Fighting Jays. The largest report
nearby was 70 mm.

Assumptions: radar hail size is an estimate built to exceed most observed stones; it says where hail probably
fell, not what reached the ground. Five years is short: 90 of 250 plants have no radar hail day in it.

## 6. Radar hail signatures (NEXRAD, 1995 on)

Code: `src/crc_lab/radar/swdi.py`. Note: [research/radar-hail-sources.md](research/radar-hail-sources.md).

1. **Pull.** NCEI's yearly files of hail signatures: one row per storm cell per radar scan, with a maximum
   expected size. Each national file (80–180 MB) is clipped to the Texas box at 0.75 inch or more.
2. **Result.** 7.64 million rows from 41 radars; 2.34 million at 1.25 inches or more. The first usable row is
   from August 1996: earlier rows carry no size.
3. **Hail day.** A calendar day with a signature of 1.25 inches or more in a cell.

This is a separate source, not merged with the grid: one storm is seen by several radars and many scans, and the
network and algorithm changed over the years. It is the only open radar record that covers 2012–2019.

## 7. The four records side by side

Code: `src/crc_lab/radar/compare_cells.py`. Output: `site/data/hail_compare/cells.json`.

Hail days per year in each of the 2,566 Texas cells:

| Source | Period | Median cell | 10th–90th percentile |
| --- | --- | --- | --- |
| Storm reports, 1 inch or more | 1996–2025 | 0.17 | 0.00–0.63 |
| Storm reports, bias-corrected | 1996–2025 | 0.72 | 0.00–2.63 |
| Radar hail size, 30 mm or more | 2020–2025 | 1.73 | 0.58–2.97 |
| Radar hail signatures, 1.25 inches or more | 1995–2025 (sizes from August 1996; averaged over 31 years) | 3.10 | 1.39–4.74 |

They do not measure the same thing: a report is hail someone saw; a radar hail day is a 253 km² cell in which
the radar estimate reached the threshold anywhere. That is why radar counts are higher per cell, while at a
single plant corrected reports and radar agree.

## 8. Plants

Code: `src/crc_lab/assets/eia.py`, `solar.py`, `value.py`.

- **List:** EIA's generator inventory through PUDL: 251 existing Texas solar plants; 250 kept, one has no
  coordinates.
- **Shape and place:** array polygons, area and imagery-checked coordinates from the USGS / Berkeley Lab solar
  database for the 185 plants it has; for the rest, EIA coordinates and an area estimated from capacity. The
  source of each plant's position is stored.
- **Value:** AC capacity × NREL's benchmark capital cost for utility solar (2024: 1,300.56 $/kW).

## What is not done

- No loss yet: damage curves (Phase 5) turn these hail numbers into a damage ratio and dollars.
- Radar and reports are compared, not merged into one estimate.
- Gridded radar for 1998–2011 exists and is not pulled; 2012–2019 exists only as signatures or raw volumes.
- The thunderstorm-gust curve follows steps 1 and 2 only.

## Rebuilding

```sh
just storm-events      # steps 1
just curves            # step 2
just reporting-bias    # step 4
just assets            # steps 3 and 8 (run again after radar to refresh the plant layer)
just radar             # steps 5, 6 and 7 (needs the radar extra; hours of download the first time)
just decisions         # the decisions document and charts
```
