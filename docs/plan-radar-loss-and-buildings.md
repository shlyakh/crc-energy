# Plan: loss from radar hail, and a building asset set

Draft for review, 2026-11-11. Yuri asked for a plan for both follow-ups to Phase 5. Nothing here is started.
The two tracks are independent and can run in either order or side by side; each ends with a report and a stop.

## Track A (Phase 7): hail loss from radar

### Why

Reports miss hail away from people. At Fighting Jays, reports give an expected loss of 0.07% of value a year,
yet radar saw 105 mm hail over the plant on 16 March 2024. A loss computed from radar does not depend on who
was there to report. It is also the natural check on the two bias corrections.

### The obstacle

The damage curves are keyed to **observed** hail size. Radar hail size (MESH) is a different quantity: an
estimate built to exceed most stones that fall. The spec forbids feeding one into a curve calibrated on the
other without saying so. So the first step is a stated conversion, not code.

### Steps

1. **Conversion from radar size to observed size.** Pair radar and reports: for every located hail report
   2020–2025, read the radar size at that place and day. This gives, for each radar size, the distribution of
   reported sizes (and the share of radar hail with no report nearby, which is reporting, not size). Compare
   with the published relation (MESH as roughly the 75th percentile of observed size; to be checked against the
   source, not assumed). Output: a table "radar size → observed size quantiles" with counts, and a chart.
2. **Hazard factor.** A second hazard input, `hail_mesh_mm`, kept distinct from `hail_diameter_obs_mm`, so a
   curve cannot be fed the wrong one unnoticed.
3. **Events at a plant from radar.** For each plant and each radar hail day: the share of the array area at or
   above each size, straight from the 1 km grid. No circle, no footprint placeholder, no disc geometry: the
   swath is measured.
4. **Loss.** Convert sizes with step 1, apply the solar curve, add a year's events, cap at 1 (the existing
   `annual.py`). Report loss per plant with the conversion's low, middle and high quantile as a range.
5. **Short record.** Five years is too short for a plant-level rate: 90 of 250 plants have no radar hail day.
   Two ways to lengthen it, to be compared:
   - pool radar over 25 km around the plant (as the hail-day figure already does);
   - scale by the 1995–2025 hail-signature record: signatures per year in the cell over 2020–2025 against the
     long-run mean, to see whether the five radar years were busy or quiet.
6. **Explorer.** A fourth basis on the Risk tab ("from radar"), the plant's radar hail days listed with
   dates and sizes, and the 16 March 2024 swath as a worked example on the map.
7. **Report 7** with the comparison: reports, per cell, per region, radar; where they agree and where not.

### Done when

Each plant has a radar-based expected loss with its range and its number of radar hail days; the conversion
table is published with counts; and the report says which of the two bias corrections radar supports.

### Questions for Yuri

1. If the pairing in step 1 is too thin at large sizes (few reports above 3 inches), is a published
   conversion acceptable in its place, tagged as taken from the literature?
2. Should the older radar years be pursued (MYRORSS 1998–2011 exists; nothing open covers 2012–2019 as a
   grid), or is 2020 onward enough for now?
3. Is the radar basis shown beside the other three, or does it replace one of them?

## Track B (Phase 8): buildings

### Why

Two of the four damage curves are for buildings and have nothing to run on: today they are evaluated at ten
city centres only. Phase 4 already compared the two federal building sources for Fort Bend County.

### Steps

1. **Asset table for Fort Bend County.** One row per building from the two federal sources compared in
   [reports/4-real-estate-fort-bend.md](reports/4-real-estate-fort-bend.md): the National Structure Inventory
   for position, occupancy class, building type and structure value; USA Structures for footprints (79.5% of
   inventory points fall inside a footprint). A data card with licence, date and coverage.
2. **What the curves need and the data lacks.** The roof curve needs roof cover (3-tab or laminated
   shingle); the federal sources do not list it. State the rule used (for example laminated for all, as the
   spec's default) and mark it as an assumption on every row, like glass type for the plants.
3. **Hail at a building.** The same algorithms as for plants, with zero asset area: report circle, per-cell
   and per-region correction. One county has hundreds of thousands of buildings, so rates are computed per
   H3 cell (resolution 8, about 0.7 km²) and joined, not per building.
4. **Loss.** Both building curves, reported as a range (Swiss claims curve as the low end, roof curve as the
   high end), per building and summed by cell and by occupancy class.
5. **A check against the public record.** Storm Events carries property damage estimates per event. Compare
   the county's modelled annual hail loss with the damage reported for hail events in the county, as an
   order-of-magnitude check, stating how rough those estimates are.
6. **Explorer.** Buildings cannot be drawn one by one from a static file at county scale without tiles
   (tippecanoe is not installed here). Show loss per cell, with a building list for the selected cell.
7. **Report 8**, and a note on what a second county or the whole state would take.

### Done when

Fort Bend buildings have a hail loss range each; the county total is set against reported damage; and the
report states the cost of extending the method.

### Questions for Yuri

1. Residential only, or all occupancy classes?
2. The two curves differ by a factor of about 250. Is a range that wide useful to show, or should the build
   wait for the observed-size curve (Schmid et al. 2025) named in the spec as the next extraction target?
3. Cars: the spec has a fleet curve but there is no vehicle data. Leave cars out?

## Order

Suggested: Track A first. It tests the weakest link in the current numbers (how much hail is missed), needs
no new data source, and its conversion step is also what the building curves need, since the Swiss curves
were calibrated on radar size. Track B can start in parallel as a side track once question B2 is answered.
