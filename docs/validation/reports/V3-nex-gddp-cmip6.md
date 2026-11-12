# Report V3: NEX-GDDP-CMIP6

Date: 2026-11-12 · crc-sdk 0.11.1, crc-framework 0.6.0 · awaiting review

Phase V3 of the [plan](../plan.md) is built: the gridded case. The generated assessment is
[sources/nex-gddp-cmip6.md](../sources/nex-gddp-cmip6.md). Nothing is committed, pushed or sent upstream.

## Result

The rainfall recipes deliver exactly what a recomputation from NASA's files gives. The temperature
recipes do not run at this version. NASA has a newer file version than crc-sdk can ask for.

| Measure | Value |
| --- | --- |
| Selection | ACCESS-CM2, member r1i1p1f1, the Texas box (2,332 grid cells, 2,158 on land), 2014 historical and 2050 ssp585 |
| Cases run | 11: four recipes in two years, plus file version 1.1 for rainfall |
| Rainfall cell values compared at the installed version | 15,106 (7 cases of 2,158 cells) |
| Rainfall values that differ | 0 (largest difference 0) |
| Temperature cell values compared on the fixed clone | 8,632 (4 cases); 0 differ |
| Checks | 24: 19 confirmed, 5 differ |
| Statement steps | 15: 12 confirmed, 2 differ, 1 not checked |

What differs:

- **Temperature units (4 checks, finding CRC-001-NEX).** The files declare kelvin; crc-sdk 0.11.1 refuses
  them. This is the defect found on 10 November, now recorded by a check.
- **File versions (1 check, new finding CRC-012-NEX).** NASA serves files of version 2.0 for this model
  (uploaded 1 July 2025). crc-sdk accepts 1.0, 1.1 and 1.2 only, so 2.0 cannot be requested and the
  default is the oldest version. No 1.2 file exists for the files checked.

What is not checked: the temperature statistics at the installed version, because the recipes fail
before returning anything.

## The temperature recipes on the fixed clone

Because the installed version cannot return temperature values, the same request was also sent to the
local clone that carries the fix (`~/work/crc/forks/crc-sdk`, uncommitted). All four cases agree with
the recomputation on every cell. Those four checks are labelled "fixed clone", carry that label in their
version field, and do not count towards any step's outcome: the step stays "not checked" for the
released version. This is also evidence that the fix is right, beyond the tests written for it.

## What the exploration shows

| Question | Answer in the Texas box |
| --- | --- |
| Do versions 1.0 and 1.1 give different one-day rainfall extremes? | Yes, slightly: 15 of 2,158 cells in 2014 (at most 0.08 mm), 42 cells in 2050 (at most 0.84 mm) |
| Does version 2.0 differ from 1.1 for rainfall? | No |
| Does version 2.0 differ from 1.0 for maximum temperature? | No |
| Which licence do the files state? | CC-BY-SA 4.0 in version 1.0; CC-BY 4.0 in 1.1; NASA states the archive is CC0. crc-sdk keeps both and warns, as documented |
| Do the files carry a checksum through crc-sdk? | No, as documented. The reference side downloads each file whole and records its SHA-256 |

## What the confirmation rests on

- **On NASA's files:** file naming, the identity check, the area selection for a 44 by 53 cell box, fill
  values (174 ocean cells), the rainfall conversion, both rainfall statistics, row order and labels.
- **On constructed files only:** the 90 per cent line (NASA's cells have every day or none), a missing
  day in the time axis, a 365-day calendar in a leap year, a cell centre exactly on the edge of the box.
- **Not run:** a box narrower than one cell, a box across the 180 degree meridian, `strict_licence`,
  other models and members, the scenarios ssp126, ssp245 and ssp370.

## What was built

| Piece | Where |
| --- | --- |
| Reference reader (whole file, h5py, rules in plain Python per cell) | `src/data_source_check/reference/nex.py` |
| crc-sdk side, one process per request, optionally against another copy of crc-sdk | `src/data_source_check/adapters/crc/nex.py` |
| The assessment | `src/data_source_check/assessments/nex.py` |
| Transformation statement (15 steps) | `src/data_source_check/sources/crc_sdk/nex-gddp-cmip6.toml` |
| Records | `site/validation/data/records/nex-gddp-cmip6.json` |
| Numeric tolerance in the comparison (stated per check; 1e-9 here, largest difference seen 0) | `src/data_source_check/core/compare.py` |

## Checks of the tool itself

| Check | Result |
| --- | --- |
| `just test` | 162 passed (70 in `tests/validation/`) |
| `just lint` | Clean |
| Deliberate faults: five reference rules, each broken on its own | Each ends as `differs` |
| Second run from stored answers | Identical records apart from run times |
| Page in headless Chrome | 16 of 16 checks |

## Departures from the plan

- Every cell of the box was compared, not sampled cells.
- File version 1.2 could not be covered: NASA has none for these files. Version 2.0 was found instead.
  What it changes is in NASA's technical note, kept in `docs/validation/references/nex-gddp-cmip6-v2/`
  (added 2026-11-12, after this report): a correction release, with tasmax and tasmin reprocessed in full.
- The reference reader opens the file with h5py; crc-sdk uses h5netcdf, which sits on the same HDF5
  library. The two share decompression and nothing above it. No reader independent of HDF5 is installed.
- crc-sdk keeps no cache for this source, so the tool stores the rows crc-sdk returned; a run without
  `--live` compares those stored rows.

## Limits

- One model, one member, one region, two years. A `confirmed` outcome says nothing about other models'
  calendars or grids.
- The cache holds 2.6 GB under `data/cache/validation/nex-gddp-cmip6/` (git-ignored).

## Open for your review

1. **The assessment** and its sign-off.
2. **CRC-012-NEX** (version 2.0): wording, and whether it is an observation or a doc-code difference.
3. **Fixed-clone checks.** Is it right to show them on the page at all before the fix is released?
4. **Which model next.** One model is thin for a source with 35. A second with a 360-day or no-leap
   calendar would test the calendar rules on real files.
