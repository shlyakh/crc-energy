# Drafting note: NOAA CO-OPS extreme water levels (`noaa-water-levels`)

Draft by an agent (skill `draft-source-assessment`), 2026-11-12. Not reviewed. crc-sdk 0.11.1,
crc-framework 0.6.0. Entry point `NOAAExtremeWaterLevelPlan`.

Every number below is copied from one of two record files or from the probe file named beside it:

- **draft records**: `data/cache/validation/drafts/records/noaa-water-levels.json`, the second live
  run (2026-11-12T15:01Z) and its re-run from caches, which gave the same records apart from run times.
- **first run**: `data/cache/validation/noaa-water-levels/first-run/records.json`, the caches of the
  first live run (responses retrieved 2026-11-12T14:57:35Z to 14:57:59Z) evaluated again, offline, with
  the final code. The two runs differ, and the difference is the main thing to review (candidate 1).

## What was compared

Sample: all 10 stations NOAA lists with state TX, 14 of the other 116 drawn with seed 20261112
(126 listed), and one station id that NOAA does not list (8770475). 25 stations, three responses each.

| | Draft records (second live run) | First run |
| --- | --- | --- |
| Stations asked | 25 | 25 |
| Delivered by both sides | 23 | 23 |
| Refused by both sides | 2 | 2 |
| Responses compared byte for byte | 69 | 69 |
| Responses with a different SHA-256 | 0 | 3 |
| Values compared, crc-sdk's tables against the rules applied to the responses it cached (levels 5,566; annuals 10,290; info 920) | 16,776 | 16,776 |
| of which differ | 0 | 0 |
| Values compared against the reference side's own download | 16,776 | 16,776 |
| of which differ | 0 | 187 (levels 59, annuals 128), at 2 stations; largest difference 0.05 |
| Checks: confirmed / differs / not checked | 11 / 0 / 0 | 9 / 2 / 0 |
| Steps: confirmed / differs / not checked | 11 / 0 / 3 | 9 / 2 / 3 |

Checks that differ in the first run: `bytes`, `second-download`. Steps that differ in the first run:
`bytes`, `one-answer`. Steps not checked in both: `limits`, `snapshot`, `reuse`.

How the comparison is built, because it is not the ibtracs pattern: the value checks (`levels`,
`annuals`, `info`) apply the reference reader to the responses **as crc-sdk cached them**; whether those
are NOAA's bytes is the separate check `bytes` (SHA-256 against an independent download). The check
`second-download` compares crc-sdk's values with the reference side's own download. I split it this way
after the first run, when NOAA gave the two sides different answers within the same second.

## Candidate findings

1. **NOAA answers the same address with two different bodies; crc-sdk delivers whichever it got.**
   - Documentation: `docs/sources/observations.md:20-23` says these services are mutable and tells the
     user to keep the cache and replay offline with the recorded SHA-256. Nothing says one request can
     return rounded values.
   - Data: in the first run 3 of 69 responses differed between the two sides (8727520 annuals,
     8770613 levels and annuals). Read by hand at 8770613, levels, first entry: one body has
     `"lower90CI": 0.21`, the other `0.2`; second entry `"level": 0.44` against `0.4`. One body carries
     two or three decimals, the other one decimal. Both sides received each kind at least once, so it
     is not the User-Agent. 187 delivered values differ, by at most 0.05 (metres).
   - Probe (`data/cache/validation/noaa-water-levels/look/repeat-probe.json`, 15:01:44Z to 15:02:01Z):
     the same annuals address asked 60 times gave two bodies, 56 times one and 4 times the other
     (2,273 and 2,211 bytes); the levels address asked 60 times gave one body.
   - Code: one request per address, no comparison (`crc_sdk/workflows/_noaa.py:39-52`).
   - Reproduced: yes (first run, and the probe). Not reproduced in the second live run (0 of 69).
   - Not shown: that a pinned `sha256` makes a refresh fail when the other body arrives (read in
     `_noaa.py:52` only). I do not know the cause on NOAA's side.

2. **A station NOAA lists with the product is refused: 8778490 Port Mansfield, TX.**
   - Data: NOAA's list includes it; its levels address answers HTTP 200 with
     `{"errorMsg": "The MSL datum is not currently available for this product.", "errorCode": 400}`.
   - Code: crc-sdk raises `ValueError("NOAA station, metric units or datum missing or mismatched")`
     (`crc_sdk/workflows/noaa_water_levels.py:295-301`); NOAA's message is not passed on. Nothing is cached.
   - Documentation: silent.
   - Reproduced: yes, in both runs (check `acceptance`). 1 of the 10 Texas stations listed.

3. **A station without the product is refused with a message about metadata.**
   - Data: 8770475 answers HTTP 200 with an empty station list (`"count": 0`).
   - Code: `ValueError("NOAA station metadata missing or mismatched")` (`noaa_water_levels.py:274-282`).
   - Documentation: silent on which stations have the product (`docs/sources/observations.md:32`).
   - Reproduced: yes, in both runs.

4. **The documented common pattern does not fit this plan.**
   - Documentation: `docs/sources/observations.md:5` ("return source observations as Arrow batches"),
     `:15` (`for batch in plan.batches()`), `:17` (`sha256=source["sha256"]`). Line 22 allows "a
     year/name → digest mapping where noted" and line 32 says the checksum covers "each of three responses".
   - Code: the plan has no `batches()`; `prefetch()` returns `{station, levels, annuals}`, so
     `source["sha256"]` raises KeyError; `cache(dir, sha256="<digest>")` raises AttributeError
     (`noaa_water_levels.py:78-90`). It returns two Arrow tables and a dictionary.
   - Reproduced: yes, but by a one-off call of crc-sdk on the cache, not by a check in the records.

5. **The plan applies acceptance rules of its own.**
   - Documentation: `docs/sources/observations.md:6-7`: the adapters do not "apply a quality or
     completeness policy that the source does not define".
   - Code: `noaa_water_levels.py:271-338` refuses a station when, for example, a confidence bound lies on
     the wrong side of the level, a return period is below 1 or a probability repeats.
   - Read in the code; reproduced on constructed responses only (24 cases in the tests). On NOAA's data
     none of these fired in the sample.

6. **The datum label is spelled differently in the two tables.** `datum` is `MHHW` in the levels table
   and `datum_label` is `mhhw` in the annual table at all 23 stations read (exploration). crc-sdk passes
   both on (`noaa_water_levels.py:157-158, 238, 255`). Observation; reproduced.

7. **NOAA sends no ETag and no Last-Modified**: 0 of 69 manifests have either, and 0 reference
   downloads. `reuse` therefore has nothing to compare (step `reuse`, not checked). Observation; reproduced.

8. **The manifest has no licence field**: 0 of 69 manifests; it has `attribution` and `terms_url`
   (`_noaa.py:53-66`). `docs/data-licences.md:36` lists CO-OPS as a U.S. government work with attribution
   requested. Same shape as IBTrACS. Reproduced (check `provenance`).

For a user rather than as a finding: 11 of the 23 stations have years missing inside their annual
series (up to 23 at 8779748); the series are 33 to 129 years long, starting as early as 1897; 21 end in
2025, one in 2023, one in 2021. Every station has 22 levels, probabilities 0.99 to 0.01, all with both
bounds. At every station 9 of the 22 published return periods are not exactly 1/probability (rounded
labels, as the column name says).

## Steps not checked, and why

- `limits` (4 MiB, Content-Length): read in the code; NOAA's responses are a few kilobytes. No
  constructed test written.
- `snapshot` (three responses kept together; failed refresh keeps the old one): read in the code and in
  crc-sdk's own test.
- `reuse` (no question to NOAA when a snapshot is cached): read in the code.

Rules confirmed on constructed responses only: every refusal rule of step `refusals` except the two
that fired on NOAA's data (empty station list; levels response without the station id). Also on
constructed responses only: a missing confidence bound becoming null, a whole number where a decimal
is usual, a null trend.

## What I was unsure of

- **Which step a difference between two downloads belongs to.** I added the step `one-answer` and let
  `second-download` bear on it alone; `bytes` also differs then, and its note says it cannot tell
  crc-sdk altering bytes from NOAA answering differently. The reviewer may prefer another split.
- **The draft records show 11 of 11 confirmed, the first run does not.** A live run can come out either
  way. `draft check` reads only the draft records. Accepting the draft as it stands would publish the
  clean run; the first run's caches are kept so that it can be re-evaluated.
- **Independence of the parser.** Both sides parse JSON with Python's `json` module (the skill allows
  the standard library). The reference keeps numbers as `Decimal` and the comparison asks whether the
  shortest decimal of crc-sdk's float equals NOAA's decimal, so a rounding on crc-sdk's side would show.
- **`[assessed_options]` is empty.** crc-sdk enumerates no option for this source; the stations compared
  are in the records.
- `pinned-checksums` and `station-id` test crc-sdk's behaviour against a stated rule, not a
  recomputation from NOAA's data.
- Code references were taken from the clone `../upstream/crc-sdk` (the workflow file is identical to
  the installed one; `_noaa.py` and `_remote.py` were not diffed).
- Not tied to a line: nothing in the statement.

## What the sample leaves out

- 103 of the 126 listed stations.
- Low-water levels, monthly products and English units: crc-sdk never requests them.
- `reuse` and `refresh` over time; a response changed by NOAA between two runs.
- How often NOAA gives the rounded body, beyond the one probe.
- Whether NOAA's values are right.

## Bytes downloaded and caches

Measured: 1,694,603 bytes (first look 155,163; first run 359,535 reference and 221,546 crc-sdk; second
run 359,597 and 221,790; probe 376,972). Not measured: about 40 requests made by hand with curl while
looking at the API, a few kilobytes each.

- `data/cache/validation/noaa-water-levels/reference/` and `crc-sdk/`: the second live run
- `.../first-run/`: caches of the first run, `records-as-run.json` (as written by the earlier code,
  10 checks) and `records.json` (final code, offline)
- `.../look/`: the first responses read by hand, with `provenance.json`, and `repeat-probe.json`
- Test fixture: `tests/validation/fixtures/noaa_water_levels_sample.json` (28,401 bytes), cut from `look/`

The draft run was made with `build.assess_draft("noaa-water-levels", live=...)` called directly rather
than `python -m data_source_check.build noaa-water-levels --draft`, because that command also rewrites
`site/validation/data/inventory.json` and `docs/validation/inventory.md`, which another agent was
sharing at the time. The inventory has therefore not been regenerated with this source's statement.
