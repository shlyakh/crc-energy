# Report V1: IBTrACS

Date: 2026-11-12 · crc-sdk 0.11.1, crc-framework 0.6.0 · awaiting review

Phase V1 of the [plan](../plan.md) is built: the first source is explored and verified against its
publisher. The assessment itself is generated from records and is in
[sources/ibtracs.md](../sources/ibtracs.md); this report covers what was built, what was found and what
needs your decision. Nothing is committed, pushed or sent upstream.

## Your review comments on V0, and what was done

| Comment | Done |
| --- | --- |
| Keep SR 26-2 in the repository | Letter and attachment downloaded from the Federal Reserve into [references/sr-26-2/](../references/sr-26-2/README.md), with checksums and a table of the passages the method uses, by page. I read the attachment in full; the mapping in the method stands, with two corrections: the letter also supersedes SR 21-8, and it is "most relevant" above $30 billion in assets rather than "for large banks". |
| Tiers are as you had in mind | No change. |
| Name `data_source_check` | Package, tests, record schema and documents renamed. |
| Findings public for now; no pull requests yet; review privately first | The method now says nothing is sent upstream before your review. Drafts are in `local/upstream-review.md`, which is git-ignored. |

## Result

crc-sdk delivers NOAA's IBTrACS files as it says it does, in the ten subsets NOAA serves.

| Measure | Value |
| --- | --- |
| Files compared | 10 (ALL, since1980, last3years and seven basins) |
| Values compared one by one, whole files | 323,350,290 |
| Values that differ | 0 |
| Checks | 71: 70 confirmed, 1 differs |
| Statement steps | 12: 10 confirmed, 1 differs, 1 not checked |

- **Differs:** the subset `active`. crc-sdk accepts the name, but NOAA's file is spelled `ACTIVE`, so
  the request fails with 404 (finding CRC-010-IBT, a defect, reproduced).
- **Not checked:** that a cached file is served without asking NOAA whether it changed. This is read in
  the code; showing it needs NOAA to change a file between two runs, which belongs to monitoring (V4).
- **Observation:** the snapshot's manifest has a citation and a terms address but no licence field, and
  the data batches carry no provenance (CRC-011-IBT).

Things a user of this source should know, from the exploration:

- About four values in five are missing; NOAA writes a missing value as one space, and crc-sdk turns
  it into null. No other value was changed by the trimming.
- Longitudes are not wrapped to -180..180 (up to 266.9). SEASON runs to 2027.
- Everything is a string. Units are only in the manifest.

## What was built

| Piece | Where |
| --- | --- |
| Reference reader (standard library only; no crc-sdk, no pyarrow) | `src/data_source_check/reference/ibtracs.py` |
| crc-sdk side | `src/data_source_check/adapters/crc/ibtracs.py` |
| Comparison, seeded sampling, check records, step outcomes | `src/data_source_check/core/compare.py` |
| The assessment (7 checks per file, 1 on addresses) | `src/data_source_check/assessments/ibtracs.py` |
| Transformation statement (12 steps with code references) | `src/data_source_check/sources/crc_sdk/ibtracs.toml` |
| Records of the run | `site/validation/data/records/ibtracs.json` |
| Generated assessment | [sources/ibtracs.md](../sources/ibtracs.md) |
| Page: an assessment block per source | `site/validation/` |
| Commands | `just validation-assess ibtracs` (live), `just validation` (offline rebuild) |

Step outcomes are not typed: each is derived from the checks that bear on the step. The build refuses a
step left unchecked without a reason.

## Checks of the tool itself

| Check | Result |
| --- | --- |
| `just test` | 139 passed (47 in `tests/validation/`) |
| `just lint` | Clean |
| Deliberate fault: reference rule without trimming, and without empty-to-null | Each ends as `differs` on the value and filter checks |
| Deliberate fault: one changed value in the file | `bytes` and `values` end as `differs` |
| Second run on unchanged inputs | Identical records apart from run times |
| Import rules | Pass; the reference side also may not import pyarrow |
| Page in headless Chrome, 1440 and 390 wide | 16 of 16 checks, no console messages |

The tests run offline on a 34-row excerpt of NOAA's file (three storms), served to both sides through a
fake download.

## Departures from the plan

- The plan said a seeded sample of storms and one whole season. Whole files were compared instead,
  because it takes seconds. The seed (20261111) only picks the 25 storms and the season ranges used to
  exercise the two filters.
- All ten served subsets were assessed, not only the North Atlantic.
- No map: the exploration has a table and a chart of storms per season. The track map already exists in
  the Texas data explorer.

## Limits

- The reference reader and crc-sdk both trust NOAA's file; this says nothing about the best tracks
  themselves.
- The local caches hold 1.6 GB under `data/cache/validation/` (git-ignored).
- The filters were exercised on one seeded draw per file, not exhaustively.
- `batch_size`, the `expected_sha256` argument and the `refresh` and `offline` modes were used but not
  tested as behaviours of their own.

## Open for your review

1. **The assessment.** Read [sources/ibtracs.md](../sources/ibtracs.md) or the page. If you agree, I
   record your sign-off (`reviewed_by`, `reviewed_on`) and the draft mark goes away.
2. **CRC-010-IBT and CRC-011-IBT.** Wording, and whether CRC-010-IBT is a "defect" in your terms.
3. **Upstream.** `local/upstream-review.md` lists every finding with a proposed form and a line for your
   decision. Nothing moves without it.
4. **Statement format.** This is the pattern for the other pass-through sources (CHIRPS, ECCC daily,
   HYDAT, USGS, sea level). Say if steps should be finer or coarser.

## Next: V2, GHCNh

Stations to fitted curves: the quality rules, the 18-hour and 90 per cent completeness rules, annual
extremes recomputed from NOAA's by-year files. Not started.
