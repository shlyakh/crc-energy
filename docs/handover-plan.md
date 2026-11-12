# Handover: state of crc-lab and plan for further development

Written 2026-11-11 for whoever continues this work. The first stage (Phases 0 to 6) is finished and paused.
Nothing in the plan below is started.

- Live page: <https://shlyakh.github.io/crc-lab/> · code: `github.com/shlyakh/crc-lab`, one branch, `main`
- Pins: crc-sdk 0.11.1, crc-framework 0.6.0 (guarded by `tests/test_pins.py`)
- Start with `AGENTS.md`, then this page, then [algorithms.md](algorithms.md)

## 1. Where Climate Risk Commons is used today

CRC supplies the data access, the curve fitting and the dataset format. The hail-risk chain from reports to
dollars is built beside it, in this repository.

| What | CRC part used | Where in crc-lab |
| --- | --- | --- |
| CRC Open climate projections for Texas (catalogue, per-hazard curves, values at return periods) | `CRCCatalog`, `CRCOpenPlan`, `read_hazard_dataset`, `curve_quantiles` | `explorer/catalog.py`, `explorer/hazards.py` |
| Tropical cyclone tracks | `IBTrACSPlan` | `explorer/tracks.py` |
| Coastal water levels | `NOAAExtremeWaterLevelPlan` | `explorer/sources.py` |
| Airport station temperatures, ERA5 baseline | `HazardDataset`, `BlockExtremaPolicy` (fits done by crc-sdk) | `explorer/sources.py` |
| Hail and gust curves per cell from storm reports | `HazardDataset.from_table` with `CDFCurveFitPolicy`; the result loads through CRC's reader like any CRC hazard | `curves/fit.py` |
| Cells: polygons to H3 | `crc_sdk.geometry.vector.polyfill_wkb` | `explorer/texas.py`, `storm_events/geometry.py` |
| Damage curves expressed in CRC's form | `ImpactExpression.tabulated` | `impacts/crc_adapter.py` |

Built here without CRC, because CRC has no counterpart at the pinned versions:

- NOAA Storm Events: download, parsing, cell assignment, event table (`storm_events/`)
- Solar plant table and replacement value (`assets/solar.py`, `assets/value.py`)
- Hail at a plant from nearby reports, the reporting-bias model and both corrections (`assets/exposure.py`,
  `assets/regional.py`, report `5-reporting-bias.md`)
- Radar hail: MRMS grid and NEXRAD hail signatures (`radar/`)
- The four hail damage curves and the annual-loss rule (`impacts/hail_curves.py`, `impacts/annual.py`)
- The explorer page (`site/`)

Two limits of CRC met on the way, both recorded in report 5:

- The plant loss is **not** computed through CRC's return-level path. Each hail event is passed through the
  damage curve and a year's events are added and capped, which CRC has no step for.
- The CRC versions of the damage curves are tabulated copies with provenance "user defined": crc-framework's
  sigmoid is a logistic, not the form the curves use, CRC has no hail factor, and a published origin needs a
  source record in CRC's registry.

## 2. What could be added to CRC from this work

In rough order of readiness. None of this has been proposed upstream yet.

| Candidate | What exists here | What it still needs |
| --- | --- | --- |
| **Hail damage curves v0** | `hail_curves.py` imports only numpy, with its parameter file `hail_v0.json` and tests against the spec's vectors; written to be lifted as it is | Source records in CRC's registry; a hail factor (`hail_diameter_obs_mm`); a place in the impact context for glass class, stow and roof class; the Swiss parameters checked against the paper's final table |
| **Storm Events plan and event-table schema** | Snapshot, parser, cell assignment, data card; counts checked year by year against the Source Cooperative copy (report 2) | Recasting as a crc-sdk workflow plan with its provider record; agreement on the event-table columns |
| **Hail and convective gust hazard datasets for Texas** | Curves per cell that already pass `read_hazard_dataset` (report 3) | A decision on whether report-based curves belong in a CRC release at all: an empty cell may be unobserved |
| **Event-based annual loss** | `annual.py`: Poisson events, damages added, capped at 1, with exceedance chances | A design discussion upstream: it is a different path from return levels |
| **Reporting-bias correction** | Model, per-cell and per-region corrections, comparison against radar ([algorithms.md](algorithms.md) 6 to 8) | Validation beyond Texas; it is the least settled part (factors up to 13) |
| **Radar hail connectors** | MRMS hail size grid 2020 on; NEXRAD hail signatures 1995 on | Recasting as plans; older gridded years (see 4, Track A) |
| **Solar plant asset table with value** | USPVDB table with a data card; value from one benchmark cost per kW | Fits CRC's asset side only if CRC wants asset data at all |
| **An end-user skill** | Not built. The pattern is in `.claude/skills/` (five CRC skills) | "How much hail loss at this solar plant", once the curves are upstream |

Smaller items to report upstream:

- NEX-GDDP-CMIP6 fails in crc-sdk 0.11.1: the unit attribute arrives as bytes (`b'K'`), so the `txx` recipe rejects it.
- crc-sdk's L-moment and least-squares fits give no confidence intervals; the explorer cannot show any.
- Every upstream change that touches this repo goes into `CHANGELOG-upstream.md`.

## 3. State at handover

| Phase | Result | Report |
| --- | --- | --- |
| 0–1 | Setup, explorer of CRC data | `reports/0-setup.md`, `1-explorer.md` |
| 2 | Storm Events on H3 cells | `2-storm-events.md` |
| 3 | Hail and gust curves | `3-curves.md` |
| 4 | Solar plants, value, hail at the plant, bias model, radar | `4-assets.md`, `4-radar-hail.md`, `5-reporting-bias.md` |
| 5 | Damage curves v0, loss per plant | `5-hail-impact.md` |
| 6 | Explorer redesign: two projects on one page | `6-explorer-redesign.md` |

Headline numbers (250 plants, value $45.2 billion): expected hail loss $82 million a year from reports as they
are, $322 million corrected per cell, $312 million corrected per region. The spread between the first and the
other two is the main uncertainty of the whole chain.

How far the numbers can be trusted:

- The damage curves are a first approximation. Stow angle, chance of stowing, module cost share and hail
  footprint are placeholders and are labelled so everywhere.
- Reports miss hail away from people. Fighting Jays has a small loss from reports, yet radar saw 105 mm hail
  over it on 16 March 2024.
- Glass type is assumed from the build year; 47 thin-film plants are flagged, not modelled separately.
- Cell-level results are regional screening (a cell is about 253 km²).

## 4. Plan for further development

Each stage ends with a report in `docs/reports/` and a stop for review, as before.

### Stage A: loss from radar hail (Phase 7)

The check on the weakest link. Detailed in [plan-radar-loss-and-buildings.md](plan-radar-loss-and-buildings.md), Track A.

1. Pair radar hail size with reported size to get a stated conversion, since the curves are keyed to observed size.
2. A second hazard input for radar size, kept apart from observed size.
3. Loss per plant from the measured swath, with a range from the conversion.
4. Lengthen the five-year record by pooling or by the 1995–2025 signature record.
5. A fourth basis on the Risk tab; report 7 says which bias correction radar supports.

### Stage B: buildings in Fort Bend County (Phase 8)

Gives the two building curves something to run on. Same document, Track B. Loss per H3 cell with a building
list, a range between the two curves, and a check against damage in the public record.

### Stage C: replace the placeholders

1. Check the Swiss curve parameters against the paper's final table.
2. Real module data for the largest plants (glass type, thickness), to test the build-year rule.
3. A thin-film breakage table; thin film recorded in the asset description.
4. Stow behaviour and hail footprint from evidence instead of placeholders (the radar swaths of Stage A give footprints).
5. The observed-size building curve named in the spec as the next extraction target.

### Stage D: upstream

1. Open the proposal for the hail curves and the hail factor (section 2, first row).
2. Propose the Storm Events plan and the event-table schema.
3. File the two smaller items.

   Order chosen on 2026-11-11: the NEX-GDDP-CMIP6 item goes first, as a small bug-fix pull request
   (built, awaiting review: [reports/u1-nex-bytes-fix.md](reports/u1-nex-bytes-fix.md)). Step 2 follows as
   a raw adapter in the IBTrACS pattern, carrying the hail design questions of step 1 in its description
   instead of a separate proposal: [plan-upstream-storm-events.md](plan-upstream-storm-events.md), not started.
4. After each accepted change: raise the pin, rerun `just all`, compare the numbers, log it in `CHANGELOG-upstream.md`.

### Stage E: beyond Texas solar

Other states, wind damage from the gust curves, a skill for end users. Not planned in detail; each depends
on Stages A and D.

**Suggested order:** A, then D1 in parallel with B, then C. A needs no new data and decides how much weight
the bias correction can bear; D1 is ready now and benefits from early feedback.

## 5. Decisions still open

| # | Question | Today |
| --- | --- | --- |
| 1 | Capacity threshold on the Risk tab | 20 MW, with a notice; EIA's 1 MW would hide nothing |
| 2 | Which bias correction is the default | Per cell; per region is shown beside it |
| 3 | Radar track: is a published size conversion acceptable where the pairing is thin; pursue older radar years; radar beside or replacing a basis | Unanswered |
| 4 | Buildings: residential only; show a range a factor of about 250 wide or wait for the better curve; leave cars out | Unanswered |

Earlier questions and their answers are in [open-questions.md](open-questions.md); choices with their
reasons are in [decisions.md](decisions.md).

## 6. Loose ends

- `docs/decisions.md` and `docs/hail-data-processing.md` do not yet cover Phase 5, the redesign or the regional correction.
- A stale "Solar farms, planned" entry remains under "Also show" in `site/layers.json`.
- The page was tested only in headless Chrome. At 1000–1280 px the legend covers part of Texas and the storm
  player's speed selector is squeezed.
- During the tour's last step the caption bar covers part of the report timeline.
- Raster sources (CHIRPS, GloFAS) could not be verified on the build Mac: `rasterio` fails to load there
  (report S1). They need a Linux build or a repaired local library.

## 7. Working on it

```sh
just all       # build every data file and the site
just impacts   # loss per plant, report 5, the Risk tab's files
just serve     # the page on a local port
just test      # pytest, offline
just lint
node tools/smoke.mjs <out dir> <url> 1440 900     # headless Chrome check, with the tour
node tools/record-demo.mjs <work dir> <url> site/demo.webm
```

Rules that held throughout and should keep holding (full list in `AGENTS.md`): one phase at a time with a
report and a stop; no invented numbers; every dataset has a data card; placeholders stay labelled; curves
are computed in Python and shipped to the page as values; [algorithms.md](algorithms.md) is updated whenever
a calculation changes. The Pages workflow rebuilds the data and runs the tests on every push to `main`.
