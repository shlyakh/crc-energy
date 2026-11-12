# Drafting note: ERA5 reanalysis extremes (`era5`)

Drafted by an agent with the skill `draft-source-assessment` on 2026-11-12. Not reviewed. Numbers
are copied from the draft records `data/cache/validation/drafts/records/era5.json` (run of
2026-11-12T15:08:28Z, crc-sdk 0.11.1, crc-framework 0.6.0) unless another file is named.

## What was compared

| Item | Number |
| --- | --- |
| Store | `wb2-1p5` (1.5 degree, WeatherBench2), the Texas box: 8 by 10 = 80 grid cells |
| Recipes and year | `rx1day`, `rx5day`, 2021, each with and without `land_only` |
| Objects in the reference copy | 1,123 (1,102 hourly chunks), 896,960,865 bytes |
| Annual cell values recomputed | 302 (80, 71, 80, 71) |
| Annual values compared (4 columns per row) | 1,208; differ: 0; largest difference 0.0 |
| Hourly values compared bit for bit (3 chunks per variable, seed 20261112) | 1,393,920; differ: 0 |
| Items of the store compared (address, axes, array metadata, recipe tables) | 17; differ: 0 |
| Checks | 9: 8 confirmed, 1 differs (`coverage[wb2-1p5]`) |
| Statement steps | 21: 13 confirmed, 2 differ (`version`, `years`), 6 not checked |

A second run from the caches (`build era5 --draft` without `--live`) gave the same checks apart
from `run_at`, the same exploration and the same headline.

### How the two sides meet (read this before trusting the table)

Every chunk of this store covers the globe (8 hours by 240 by 121 values), so one variable-year
is about 0.9 GB whatever the box. crc-sdk keeps no hourly data and refuses a
request of fewer than four years, so asking it over the network would have moved about four times
that again. The draft therefore works in two parts:

1. `store` and `hours`: crc-sdk's own handle to the real store (zarr over gcsfs) against the
   reference copy: axes, array metadata, and three seeded chunks per variable, bit for bit.
2. `annual`: crc-sdk reduces 2021 through `HazardDataset.era5(...).annual_extremes()` while its
   store address is pointed at the folder of the reference copy (`adapters/crc/era5.py`,
   `_store_at`). Both sides read the same checksummed bytes. crc-sdk is asked for 2018 to 2021;
   the copy holds the hours of 2021 only, zarr reads the absent chunks as NaN, and crc-sdk returns
   no row for 2018 to 2020 (recorded as `rows_for_years_not_in_the_copy`: 0).

This is my construction, not something the skill describes; a reviewer may prefer a run over the
network for four years (about 3.6 GB of traffic for one rainfall recipe).

Layers the two sides share: the publisher's bytes, and Python's float arithmetic. Not shared:
transport (urllib over HTTPS against gcsfs), Zarr metadata reading (json against zarr), chunk
decoding (a Blosc container and LZ4 block decoder written in `reference/era5.py` against
numcodecs and c-blosc), and every rule. The decoder is tested against numcodecs on constructed
arrays and on two objects cut from the publisher's store. The reference uses no numpy.

## Candidate findings

1. **The 1.5 degree store ends a year earlier than documented and coded. Reproduced.**
   Documentation: `docs/sources/era5.md:39` gives the coverage of `wb2-1p5` as "1959–2022".
   Code: `crc_sdk/providers/era5.py:104-105` (`first_year=1959`, `last_final_year=2022`); the store
   has no `valid_time_stop` attribute, so the release is named `final-through-2022-12-31`
   (`era5.py:475-484, 494`). Data: the time axis has 552,264 hourly steps from 1959-01-01T00 to
   2021-12-31T23 (crc-sdk's own handle reads the same first and last step; check `store`).
   Check `coverage[wb2-1p5]`: crc-sdk accepts 1959-2022 for temperature and 1959-2021 for rainfall;
   the axis holds 1959-2021 and 1959-2020 complete. Read by hand: the last time chunk decoded in
   the test `test_the_decoder_reads_objects_cut_from_the_publishers_store` ends at hour 552,263
   after 1959-01-01, which is 2021-12-31T23.
   Consequences seen:
   - Asked for `txx` 2019 to 2022, crc-sdk raises no error and returns 0 rows for 2022 (0 hours of
     2022 are on the axis; `era5.py:423-425` skips an empty range). This ran against the reference
     copy; no chunk is needed for 2022, so the copy does not affect it.
   - For rainfall in 2021 the hour stamped 2022-01-01T00 is missing (8,759 of 8,760 hours), so 31
     December fails the 24-of-24 rule and every one of the 80 cells has 364 days. The annual
     values are computed without that day and agree with the reference, which applies the same
     rule. In this box it changes nothing: the 23 hours of that day sum to at most 11.6 mm, 0.70 of
     the cell's `rx1day`, and exceed it in 0 of 80 cells
     (`data/cache/validation/era5/probes/dec31-2021.json`).
2. **CRC-006-ERA5 (units not read): holds; the assumption is met on this store.**
   Check `units-declared[wb2-1p5]`: the store declares `K` and `m`, which is what the conversions
   assume. On a constructed store whose temperature declares `degC`, crc-sdk raises nothing and
   subtracts 273.15 all the same (test
   `test_a_unit_the_conversion_does_not_assume_is_not_noticed_by_crc_sdk`). Reproduced on a
   constructed store only.
3. **The cache key does not contain the release. Read, not reproduced.**
   Documentation: `docs/sources/era5.md:41-42`: "the cache is keyed by the final record's end
   date". Code: `crc_sdk/workflows/era5.py:149-167` hashes store, recipe, rule set, year, bounds
   and `land_only`; its docstring says the release "is provenance on the entry, not identity".
4. **A chunk the store does not hold is silently missing data. Observed on the reference copy.**
   No documentation line. zarr returns the fill value (NaN) for an absent chunk; crc-sdk has no
   line that counts chunks. The three years without chunks in the copy gave no row and no error.
   A year with up to 10 per cent of its days absent would still get a value (`completeness`).
5. **The documentation does not state the completeness rules.** `docs/sources/era5.md:43-45`
   says the daily maximum is "the largest of 24 instantaneous values"; the code accepts a day with
   18 of 24 hours (`era5.py:164, 176`), needs all 24 for rainfall (`era5.py:150-152`) and 90 per
   cent of the days (`era5.py:166`). Read; the thresholds were exercised on constructed files.
6. **Speed and size as documented against measured (minor).** `docs/sources/era5.md:39` says about
   30 s per variable-year, the module docstring (`era5.py:13-14`) about 15 s. The 1,095 rainfall
   chunks of 2021 are 895,054,982 bytes (summed from the listing of the reference copy).

## Steps not checked, and rules confirmed on constructed files only

- `units-temperature`, `day-temperature`, `statistic-temperature`: not run on the publisher's
  data (budget: one more variable-year, about 0.7 GB). Confirmed on constructed files only.
- `fit-years`, `fit`, `labels`: the fitted curve and its file belong to a later tier.
- Confirmed on real data only on one side of the line, the line itself on constructed files:
  `completeness` (every cell had 364 of 365 days), the 24-of-24 rule (fires for 31 December only),
  `missing` (no NaN in the box), `land-mask` (71 of 80 cells on land; a mask value of exactly 0.5
  on constructed files), `area` (the half-cell margin).
- `cache`: the 32-bit rounding is confirmed; the manifest and reuse of stored years were not run.
- `store`: `arco-0p25` was not opened.

## What I was unsure of

- Whether pointing crc-sdk at a copy of the store is acceptable for the `annual` checks (above).
- The `coverage` check books one cause against two steps (`version`, `years`).
- The hour stamped 00:00 "belongs to the day before" is taken from crc-sdk's code. That
  WeatherBench2's precipitation is in fact an accumulation over the hour ending at the stamp was
  not verified against the publisher's documentation.
- Not tied to a line of crc-sdk: the reading of an absent chunk as NaN (zarr), the anonymous
  access (gcsfs `token="anon"`, `era5.py:70-72`), and the order of summation inside numpy; the
  reference sums in time order and every value agreed exactly.
- `annual` checks list `completeness` and `missing` as steps they bear on, as the NEX example
  does; the outcome "confirmed" for those two is weaker than it reads.

## What the sample leaves out

Stores: `arco-0p25`. Recipes: `txx`, `tnn` on real data. Years: all but 2021; no leap year on real
data (2020 is in the constructed store). Areas: boxes narrower than a cell, at the 180 degree
meridian, outside Texas. crc-sdk's network path for whole years, its cache reuse, `land_only` on
the 0.25 degree store's time-varying mask, the fitted curves and the output file's labels.

## Bytes and caches

- Reference copy: `data/cache/validation/era5/reference/wb2-1p5/` (the store's own layout),
  listed with checksums in `data/cache/validation/era5/reference/wb2-1p5.provenance.json`:
  896,960,865 bytes in 1,123 objects.
- crc-sdk's stored answers: `data/cache/validation/era5/framework/`. In each live run crc-sdk
  read from the network the time axis, the coordinates and the six sampled chunks (4,266,476
  bytes of chunks). Three live runs were made.
- Before the reference existed, two chunks and six small objects were fetched with curl to look at
  the format; they are in the session's scratch folder, not in the cache.
- The first live run (15:01Z) gave the same nine outcomes and numbers. Afterwards only the way
  inputs are listed in the records was changed (a second run from caches listed more objects
  than the first); the first run's records were overwritten and are not kept.
