# Phase 5 report: hail impact functions v0 and hail loss at Texas solar plants

Built 2026-11-11 with crc-sdk 0.11.1 and crc-framework 0.6.0. Every number below is written by `python -m crc_lab.impacts.build` (`just impacts`).

**These are first-approximation numbers.** The curves are the v0 curves of [the spec](../requirements-hail-impact-v0.md). Four inputs have no source and are placeholders: the stow angle (60°), the chance a tracker is stowed when hail arrives (0.8), the modules' share of plant value (0.4) and the area hit per hail report (25 km²). The sensitivity table shows how far each moves the result.

## Result

- The 250 plants are worth $45,231.92 million at benchmark cost. Expected hail loss is **$82.43 million a year from reports as they are (0.182% of value) and $321.84 million a year after the reporting-bias correction (0.712%)**.
- Per plant, the expected annual damage ratio has median 0.142% (10th to 90th percentile 0.029% to 0.470%); bias-corrected, median 0.378% (0.125% to 1.337%).
- The correction multiplies a plant's loss by 3.0 at the median and by up to 13.2. The largest factors are in thinly populated country, where the fitted reporting rate is lowest and least certain.
- The cap at full loss changes almost nothing: without it the totals would be $82.44 million and $321.86 million.

## What was built

- `src/crc_lab/impacts/hail_v0.json`: the spec's parameter block, unchanged (a test compares the two).
- `src/crc_lab/impacts/hail_curves.py`: a validating loader, the three functional forms and the four curves. It imports only numpy and the standard library, so it can be offered to crc-sdk with the data file and tests.
- `src/crc_lab/impacts/annual.py`: from events at an asset to a year's damage ratio (events added, capped at full loss).
- `src/crc_lab/impacts/crc_adapter.py`: the curves as crc-sdk impact expressions.
- `src/crc_lab/impacts/build.py`: loss per plant, this report, `data/assets/solar_tx_hail_loss.parquet` with its card, and the loss fields on the explorer's plant panel.
- `tests/test_impacts.py`: every test vector in the spec, the extra checks, monotonicity and bounds on a grid from 0 to 150 mm, rejection of bad input, and the annual-loss rule against a simulation.

## How loss at a plant is computed

1. **Events.** The plant's circle from Phase 4 (grown to 100 reports, 10 to 75 km, clipped to the five-state reporting region) holds the located hail reports of 1996–2025 (77,485 in the region). Each report is one possible event with its own size.
2. **Reaching the plant.** A report stands for hail of that size over 25 km². The plant is a disc of its array area. The event touches the plant with chance hit area ÷ circle area, and damages the share of the plant the footprint covers.
3. **Damage.** `pv_plant_hail_v0` turns the report's size into a damage ratio, with the plant's glass class and mounting (rules below).
4. **A year.** Events arrive at random (Poisson). The damage ratios of a year's events are added and capped at 1.
5. **Bias-corrected.** The same, with the event rate divided by the fitted reporting rate around the plant ([report 5](5-reporting-bias.md)). Sizes are not changed.

One consequence of step 2 is checked in the build for every plant: the expected damage ratio equals report rate × footprint × mean damage ratio and does not depend on the plant's size. A larger plant is hit more often, but each hit covers a smaller share of it.

Per-plant rules:

- **Glass class** (the spec's rule): 2.0 mm glass-glass for plants first online in 2021 or later (171 plants), 3.2 mm glass and backsheet before (79). 47 plants have thin-film modules, for which the spec has no table; they follow the same rule and are marked.
- **Stow.** Trackers use the spec's mixture: stowed at 60° with chance 0.8, flat otherwise. 33 fixed-tilt plants use their reported tilt all the time (1 of them report no tilt and are taken as flat). 28 plants report no mounting, nearly all from 2025–2026, and are treated as trackers.

## Plants with the largest bias-corrected loss

| Plant (county) | MW AC | Year | Glass | Mounting | Damage ratio per year | Loss per year | Bias-corrected ratio | Bias-corrected loss | Largest radar hail over the plant, 2020–2025 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Azure Sky Solar (Haskell) | 225 | 2021 | 2.0 | tracker | 0.620% | $1.81 million | 4.699% | $13.75 million | 34 mm on 2024-04-09 |
| Roaring Springs, LLC (Motley) | 250 | 2025 | 2.0 | tracker | 0.567% | $1.85 million | 3.937% | $12.80 million | 48 mm on 2025-05-26 |
| Hornet Solar (TX) (Swisher) | 600 | 2025 | 2.0 | tracker | 0.230% | $1.79 million | 1.136% | $8.87 million | 47 mm on 2023-05-27 |
| Hecate Energy Longhorn Solar LLC (Jack) | 650 | 2026 | 2.0 | tracker | 0.233% | $1.97 million | 1.023% | $8.65 million | 38 mm on 2025-04-03 |
| Galloway 1 Solar Farm (Concho) | 250 | 2021 | 2.0 | tracker | 0.324% | $1.05 million | 2.635% | $8.57 million | 30 mm on 2024-04-18 |
| Texas Solar Nova 1 (Kent) | 252 | 2023 | 2.0 | tracker | 0.255% | $834,695 | 2.431% | $7.97 million | 42 mm on 2025-04-30 |
| 2W Permian Solar Project Hybrid (Andrews) | 420 | 2021 | 2.0 | tracker | 0.274% | $1.50 million | 1.404% | $7.67 million | 54 mm on 2025-06-10 |
| Hecate Energy Frye Solar LLC (Swisher) | 500 | 2024 | 2.0 | tracker | 0.212% | $1.38 million | 1.030% | $6.69 million | 31 mm on 2021-07-16 |
| Angelo Solar (Tom Green) | 195 | 2025 | 2.0 | tracker | 0.829% | $2.10 million | 2.632% | $6.67 million | 29 mm on 2023-06-10 |
| Fagus Solar Park (Childress) | 332 | 2025 | 2.0 | tracker | 0.344% | $1.48 million | 1.530% | $6.60 million | 41 mm on 2023-07-06 |

## Fort Bend County

Fort Bend is where the hailstorm of 16 March 2024 damaged the Fighting Jays plant. The spec notes that stowed 2.0 mm glass-glass modules in the county came through radar-estimated hail of 40 to 100 mm undamaged, which this curve would not predict.

| Plant (county) | MW AC | Year | Glass | Mounting | Damage ratio per year | Loss per year | Bias-corrected ratio | Bias-corrected loss | Largest radar hail over the plant, 2020–2025 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Old 300 Solar Center, LLC (Fort Bend) | 430 | 2024 | 2.0 | tracker | 0.054% | $302,937 | 0.109% | $610,212 | 49 mm on 2024-03-16 |
| Fort Bend Solar LLC (Fort Bend) | 240 | 2023 | 2.0 | tracker | 0.089% | $277,849 | 0.162% | $504,354 | 26 mm on 2024-05-14 |
| Fighting Jays Solar Project (Fort Bend) | 228 | 2022 | 2.0 | tracker | 0.073% | $214,808 | 0.138% | $409,473 | 105 mm on 2024-03-16 |
| Cutlass Solar II (Fort Bend) | 203 | 2024 | 2.0 | tracker | 0.082% | $215,597 | 0.137% | $361,986 | 81 mm on 2024-03-16 |
| Cutlass Solar 1 LLC (Fort Bend) | 111 | 2022 | 2.0 | tracker | 0.084% | $121,867 | 0.140% | $201,916 | 53 mm on 2024-03-16 |
| Bronson (Fort Bend) | 10 | 2018 | backsheet 3.2 | fixed | 0.059% | $7,653 | 0.106% | $13,725 | 26 mm on 2024-05-14 |

The report-based loss here is small because few large-hail reports lie near these plants; the radar column shows what the reports miss. A loss from radar hail is not computed: the spec keeps observed size and radar size as separate inputs, and v0 has no curve keyed to radar size.

## Bias correction: per cell or per region (tried 2026-11-11)

Two ways to correct for reporting, both from the same reporting-bias model:

- **Per cell (local).** Keep the plant's circle; divide its report rate by the mean fitted reporting rate of the cells in the circle.
- **Per region.** Drop the circle. Use the plant's model region (an H3 resolution-3 cell, about 12,000 km²): rate = reports in the region ÷ (years × sum over its cells of reporting rate × cell area). Report sizes are pooled over the region. Every plant in a region gets the same hail rate and size mix; only its glass type, mounting and area differ.

| Basis | Portfolio loss per year | Share of value | Damage ratio per year, 10th / 50th / 90th percentile of plants |
| --- | --- | --- | --- |
| Reports as they are | $82.43 million | 0.182% | 0.029% / 0.142% / 0.470% |
| Corrected per cell | $321.84 million | 0.712% | 0.125% / 0.378% / 1.337% |
| Corrected per region | $311.62 million | 0.689% | 0.151% / 0.448% / 1.312% |

- The plants fall in 45 regions. Regional ÷ per-cell loss: median 1.09, 10th to 90th percentile 0.56 to 2.05.
- The spread between plants narrows: 90th ÷ 10th percentile of the damage ratio is 10.7 per cell and 8.7 per region.
- Rank agreement between the two (Spearman): 0.86; between reports as they are and per region: 0.69.

Plants that move most between the two corrections:

| Plant (county) | MW | Reports as they are | Per cell | Per region | Reports in region | Region mean reporting rate |
| --- | --- | --- | --- | --- | --- | --- |
| SunE CPS3 LLC (Bexar) | 11 | 0.021% | 0.031% | 0.154% | 1,071 | 56% |
| PowerFin Kingsbery (Travis) | 3 | 1.331% | 1.331% | 0.321% | 812 | 48% |
| GVEC (Guadalupe) | 2 | 0.015% | 0.031% | 0.130% | 812 | 48% |
| RP SCG Texas Solar (Travis) | 2 | 4.043% | 4.043% | 0.999% | 812 | 48% |
| OCI Alamo 7 LLC (Haskell) | 100 | 0.271% | 2.055% | 0.544% | 1,228 | 25% |
| North Gainesville Solar (Cooke) | 5 | 1.574% | 2.698% | 0.764% | 2,541 | 63% |
| Niagara Bottling - Seguin (Guadalupe) | 5 | 0.192% | 0.285% | 0.970% | 1,071 | 56% |
| BT Cooke Solar, LLC (Cooke) | 59 | 0.454% | 1.142% | 0.338% | 2,541 | 63% |

What the regional value gains and loses: it does not depend on how many reports happen to lie near the plant, so it is steadier and cannot be driven by one town; but it assumes hail climate is uniform over about 110 km, and it erases real differences inside a region. Regions at the state border hold only their Texas cells.

## Sensitivity of the portfolio total

Expected annual loss over all plants (the cap is left out here; it moves the total by less than the rounding).

| Variant | From reports | × default | Bias-corrected | × default |
| --- | --- | --- | --- | --- |
| Defaults | $82.44 million | 1.00 | $321.86 million | 1.00 |
| Trackers never stow (p_stow 0) | $188.49 million | 2.29 | $726.87 million | 2.26 |
| Trackers stow half the time (p_stow 0.5) | $122.21 million | 1.48 | $473.74 million | 1.47 |
| Trackers stow 95% of the time | $62.55 million | 0.76 | $245.92 million | 0.76 |
| Stow angle 50 degrees | $108.81 million | 1.32 | $424.24 million | 1.32 |
| Stow angle 75 degrees | $47.66 million | 0.58 | $186.74 million | 0.58 |
| Module cost share 0.30 | $61.83 million | 0.75 | $241.40 million | 0.75 |
| Module cost share 0.50 | $103.05 million | 1.25 | $402.33 million | 1.25 |
| Every plant 2.0 mm glass-glass | $93.25 million | 1.13 | $370.04 million | 1.15 |
| Every plant 3.2 mm glass and backsheet | $25.16 million | 0.31 | $103.07 million | 0.32 |
| Footprint 16 km² per report | $52.76 million | 0.64 | $205.99 million | 0.64 |
| Footprint 61 km² per report | $201.15 million | 2.44 | $785.35 million | 2.44 |

Module cost share and footprint scale the loss in proportion. Stow settings touch trackers only.

## Buildings and cars: expected annual damage per $100,000 of value

There is no building or car asset set yet, so these are the four curves at the ten city centres, for a single building or car there. Regional screening only. City centres are where reports are densest, so the uncorrected figures are the least biased here; the last column is the fitted reporting rate.

| City | Reports in circle | Buildings, Swiss claims curve | Buildings, roof curve (laminated) | Buildings, roof curve (3-tab) | Cars, Swiss fleet curve | Fitted reporting rate |
| --- | --- | --- | --- | --- | --- | --- |
| Houston | 110 | $0.62 | $176 | $363 | $6.76 | 100% |
| Dallas | 101 | $1.74 | $374 | $681 | $13.52 | 100% |
| San Antonio | 122 | $3.00 | $566 | $903 | $19.62 | 100% |
| Austin | 137 | $3.66 | $785 | $1,283 | $26.53 | 100% |
| Fort Worth | 191 | $3.12 | $717 | $1,326 | $25.74 | 100% |
| El Paso | 100 | $0.24 | $73 | $164 | $2.89 | 71% |
| Amarillo | 498 | $5.39 | $1,293 | $2,523 | $48.49 | 100% |
| Lubbock | 111 | $1.42 | $366 | $714 | $13.38 | 99% |
| Corpus Christi | 100 | $0.17 | $42 | $85 | $1.62 | 72% |
| Midland | 167 | $4.56 | $971 | $1,614 | $33.30 | 100% |

The two building curves differ by a factor of 235 at the median city. The spec expects this: the Swiss curve is averaged over every building in a radar cell and is a lower bound; the roof curve assumes hail of the reported size fell on the roof and is an upper bound. The gap is the uncertainty in v0, and both are reported as a range.

## The curves in CRC

Checked against the pins: crc-framework's sigmoid is a logistic, not the Emanuel cubic; the impact context carries no glass class, stow or roof class; CRC has no hail factor. So each curve is built as a tabulated `ImpactExpression` with exposure variable `hail_diameter_obs_mm` (mm) and impact metric `damage_ratio`. The solar curves are exact (their knots); the others are sampled every millimetre to 150 mm.

| Expression | Points | Exact | Largest gap to the callable | Monotonicity |
| --- | --- | --- | --- | --- |
| `pv_break_probability_glass_glass_2.0` | 6 | yes | 1.1e-16 | non_decreasing |
| `pv_break_probability_glass_backsheet_3.2` | 6 | yes | 1.1e-16 | non_decreasing |
| `pv_plant_hail_v0` | 12 | yes | 1.7e-16 | non_decreasing |
| `bld_hail_swiss_v0` | 151 | sampled | 5.9e-05 | non_decreasing |
| `bld_hail_roof_v0` | 151 | sampled | 3.0e-05 | non_decreasing |
| `car_hail_swiss_v0` | 151 | sampled | 5.7e-05 | non_decreasing |

The definitions with their hashes are in `data/assets/hail_v0_crc_expressions.json`. Their provenance is "user defined": a published origin needs a source record in CRC's registry, which these curves do not have. Loss was not computed through CRC's return-level path, as the spec asks: the curves are applied to each event and losses are aggregated afterwards.

## Not done, and limits

- No hazard factor was registered inside crc-sdk: that is an upstream change. The expressions carry the variable name, so a hail factor added later must match it.
- The Swiss parameters are still tagged "verify against the paper's final Table 2"; the paper was not opened in this phase.
- Cars in the open have no curve.
- Lab breakage is applied to the largest reported stone, which overstates damage to unstowed modules; storm reports miss hail away from people, which understates the rate. The two errors do not cancel in any known way.
- A report's size is assumed over the whole 25 km² footprint.
- Report sizes cluster at reference objects (1.00, 1.75, 2.75 inches), so the size distribution is coarse.
- `docs/decisions.md` and `docs/hail-data-processing.md` do not yet describe this step.

## Questions for review

1. Glass class by year treats every plant before 2021 as 3.2 mm glass and backsheet, which is the stronger module. Is that the intent, or should older plants be run both ways?
2. Thin-film plants follow the year rule for lack of a table. Leave them in, or report them apart?
3. Should the next step be a loss from radar hail (needs a decision on feeding radar size into these curves), or a building asset set for Fort Bend?
