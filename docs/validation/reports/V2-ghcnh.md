# Report V2: GHCNh

Date: 2026-11-12 · crc-sdk 0.11.1, crc-framework 0.6.0 · awaiting review

Phase V2 of the [plan](../plan.md) is built: the first source that crc-sdk reduces and fits. The
generated assessment is [sources/ghcnh.md](../sources/ghcnh.md). Nothing is committed, pushed or sent
upstream.

## Result

crc-sdk's annual extremes of GHCNh temperature are what its documentation says they are, for the stations
and years the Texas data explorer uses.

| Measure | Value |
| --- | --- |
| Stations, years | 40 stations, 2000 to 2024 (the explorer's selection) |
| Station-years recomputed | 1,000, of which 592 have a file at NOAA |
| Hourly reports read from NOAA | 13,885,491 |
| Values compared (11 fields per station-year, two recipes) | 22,000 |
| Values that differ | 0 |
| Checks | 8: all confirmed |
| Statement steps | 14: all confirmed, two with a stated limit |

No finding was opened.

The annual value was recomputed two ways, both without crc-sdk and without its parser:

- from NOAA's Parquet files, for every station-year;
- from NOAA's pipe-separated files, with the standard library only, for a seeded sample of 8
  station-years.

## Why 40 stations give 8 curves

| Stage | Count |
| --- | --- |
| Stations crc-sdk's catalogue selects in the Texas box | 699 |
| Stations the explorer asks for (the first 40 whose ID starts with USW) | 40 |
| Station-years with a file, of 1,000 | 592 |
| Station-years complete | 427 |
| Stations with at least 15 complete years (the explorer's setting) | 8 |
| Stations with at least 20 complete years (crc-sdk's default) | 0 |

The first 40 USW stations are small airports and oil platforms whose records begin around 2005. No
station in this selection could have 20 complete years. This is a property of the explorer's selection
rule, not of crc-sdk: crc-sdk applied the minimum per station exactly as stated.

## What the confirmation rests on

- **On NOAA's data:** the file layout, the time and day rules, the 18-hour and 90 per cent rules, the
  annual value, the location, the range limits (7 reports excluded) and the quality codes (8,078 reports
  excluded for a code that is not accepted; 174,166 had no temperature).
- **On constructed files only:** the two lists of source codes for quality codes 1 and 5, and the refusal
  of a station that moves. No report or station in these files triggered them. The offline tests build
  files that sit on each boundary (17 against 18 hours, 328 against 329 days, 61.8 against 61.9 degrees,
  listed against unlisted source codes, a station that moves 0.06 degrees) and crc-sdk and the reference
  agree on all of them.
- **Not checked:** the fit itself. Only the family named in the output was confirmed. Parameters, method
  and behaviour on short records belong to validation (V7).

## What a user should know

- Days are UTC days. In Texas a UTC day runs from the local evening to the next.
- A value on a day with fewer than 18 valid hours is ignored, even if it is the year's extreme.
- The values are extremes of sampled hourly temperature, not of an instrument's daily maximum.
- A station whose coordinates move by more than 0.05 degrees within a year stops the whole request with
  an error; it is not skipped.

## What was built

| Piece | Where |
| --- | --- |
| Reference readers and rules (Parquet through DuckDB's reader; pipe-separated with the standard library) | `src/data_source_check/reference/ghcnh.py` |
| crc-sdk side | `src/data_source_check/adapters/crc/ghcnh.py` |
| The assessment (4 checks per recipe) | `src/data_source_check/assessments/ghcnh.py` |
| Transformation statement (14 steps) | `src/data_source_check/sources/crc_sdk/ghcnh.toml` |
| Records | `site/validation/data/records/ghcnh.json` |
| Generic report and page | Each assessment now supplies its own headline numbers, tables and chart; the report and the page no longer know about IBTrACS |

## Checks of the tool itself

| Check | Result |
| --- | --- |
| `just test` | 153 passed (61 in `tests/validation/`) |
| `just lint` | Clean |
| Deliberate faults: ten reference rules, each broken on its own | Each ends as `differs` |
| Second run from the caches | Identical records apart from run times |
| Page in headless Chrome | 16 of 16 checks |

## Departures from the plan

- All 40 stations were recomputed, not a seeded sample; the seed picks only the station-years read a
  second time from the pipe-separated files.
- The plan's "stored curve reproduces its own samples" check was not built. It tests the fit, which is
  left to validation; the check built instead is that the right stations receive a curve.
- The Parquet reference reader uses DuckDB, which crc-sdk also uses (for aggregation, not for reading
  the file). The pipe-separated reader shares nothing with crc-sdk.

## Limits

- Texas, 2000 to 2024, default quality settings. Other regions, older years and custom `quality(...)`
  settings were not run.
- Station selection by area (the catalogue) was used but not verified against NOAA's station list.
- The cache holds 0.8 GB under `data/cache/validation/ghcnh/` (git-ignored).

## Open for your review

1. **The assessment** and its sign-off.
2. **The explorer's station rule.** "First 40 USW stations" picks short records. A rule that prefers long
   records (for example by `start_year` in the catalogue) would give more and better curves. This is a
   change to the Texas data explorer, not to this project; say if you want it.
3. **The two limits** stated on the quality and location steps: is "confirmed on constructed files" an
   acceptable basis, or should such steps carry a separate outcome?
