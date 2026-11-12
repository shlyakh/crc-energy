# Report U1: fix for NEX-GDDP-CMIP6 temperature recipes in crc-sdk

Date: 2026-11-11 · crc-sdk `main` at `9c56bb0` (0.11.1) · h5netcdf 1.8.2, h5py 3.16.0

**Status: sent on 2026-11-12 as pull request [#42](https://github.com/RiskThinking/crc-sdk/pull/42) from the fork
`shlyakh/crc-sdk`, branch `fix/nex-bytes-attributes`. The sections below describe the state before sending.**
A second small fix went with it: [#43](https://github.com/RiskThinking/crc-sdk/pull/43), IBTrACS subset `active`
(finding CRC-010-IBT), branch `fix/ibtracs-active-subset`.
This is the first, deliberately small, contribution to upstream. The Storm Events adapter follows later
([plan-upstream-storm-events.md](../plan-upstream-storm-events.md)).

## What was wrong

`HazardDataset.nex_gddp_cmip6("txx", ...)` and `"tnn"` fail on every real NEX file with

```
'tasmax' is published in "b'K'", but recipe 'txx' converts from 'K'; the conversion would be wrong
```

Precipitation (`rx1day`, `rx5day`) works. crc-sdk's documentation says NEX supports all four recipes
(`docs/sources/cmip6.md`, line 5) and that temperatures must be kelvin, which the files are. So this is a
bug, not a usage error. Upstream's docs example, notebook, pipeline and test all use precipitation only,
which is why it was not seen.

## Cause, confirmed

| Check | Result |
| --- | --- |
| Header of the real `tasmax` and `tasmin` files (ACCESS-CM2, historical, 2014) | `units` is `np.bytes_(b'K')` |
| Header of the real `pr` file | `units` is the text `'kg m-2 s-1'` |
| Other attributes on those files | Text, except `time.axis` (`b'T'`), which crc-sdk does not read |
| h5netcdf source (`attrs.py`) | Fixed-length strings are decoded only when longer than one character, on purpose |
| crc-sdk (`providers/cmip6.py`, `check_variable`) | Wraps the attribute in `str()`, which turns `b'K'` into the text `b'K'` |

A one-character unit is the whole story: `K` stays bytes, anything longer is decoded.

## The fix

Working copy: `~/work/crc/forks/crc-sdk`, branch `fix/nex-bytes-attributes`, uncommitted. Two files,
94 lines added, 7 removed.

- `crc_sdk/workflows/nex.py`: a private helper `_text_attrs` decodes byte-string attributes to text. The
  two small wrappers that hand NEX attributes to the shared CMIP6 code (`_Array`, `_Group`) use it, and
  the missing-units check now reads through the same wrapper.
- `crc_sdk/providers/cmip6.py` is untouched. The native CMIP6 path reads Zarr, where attributes are
  already text.
- No public API change, no version bump.

## Tests added (`tests/test_nex.py`, offline)

The new fixture stores `units` as a one-character fixed-length string, as the real archive does.

| Test | Before the fix | After |
| --- | --- | --- |
| `txx` on kelvin stored as `b"K"`: 300 K gives 26.85 degC | Failed with the message above | Passes |
| `tnn` on the same: 270 K gives -3.15 degC | Failed | Passes |
| A wrong unit stored as `b"C"` is still rejected, with a readable `'C'` in the message | Failed (message showed `b'C'`) | Passes |
| Missing `units` is still rejected | Passed | Passes |

## Check results

| Check | Baseline (before any change) | With the fix |
| --- | --- | --- |
| `pytest` (four raster test files left out, see below) | 729 passed, 1 failed | 733 passed, 1 failed |
| `mypy` | Clean | Clean |
| `ruff check`, `ruff format --check` | Clean | Clean |

The one failure and the four files left out are the same before and after and are not related: `rasterio`
cannot load on this Mac (missing `libx265`, the problem recorded in report S1). Upstream's CI on Linux
will run them.

Live run, the call that failed in report S1 (Austin box, 2014, ACCESS-CM2 historical):

| Recipe | Rows | Unit | Range | Time |
| --- | --- | --- | --- | --- |
| `txx` | 16 | degC | 44.09 to 45.14 | 48 s |
| `tnn` | 16 | degC | -10.02 to -4.98 | 48 s |

These are one model's values for its own year 2014, not observations. The earlier failure took 455 s; the
difference in time was not investigated.

## Draft pull request text

Title: `fix(nex): accept one-character unit attributes (temperature recipes failed on real files)`

> `HazardDataset.nex_gddp_cmip6("txx" | "tnn", ...)` fails on real NEX files with
> `'tasmax' is published in "b'K'", but recipe 'txx' converts from 'K'`.
>
> h5netcdf decodes fixed-length string attributes only when they are longer than one character, so the
> kelvin unit `K` arrives as `bytes` and `str()` renders it as `b'K'`. Precipitation is unaffected
> (`kg m-2 s-1` is decoded), which is why the existing test, notebook and pipeline pass.
>
> This decodes byte-string attributes in the NEX adapter's `_Array` and `_Group` wrappers, so the shared
> CMIP6 checks see text. `providers/cmip6.py` is unchanged; the same guard could live in
> `check_variable` if you prefer it there.
>
> Tests: a fixture with `units` stored as a one-character fixed-length string; `txx` and `tnn` now return
> values, a wrong one-character unit is still rejected with a readable message, and missing units still
> raise. Checked against the real ACCESS-CM2 historical 2014 files for `tasmax` and `tasmin`. With the
> fix, every temperature value in a Texas box (8,632 values, two years) equals an independent
> recomputation from NASA's files.
>
> While testing on real files we noticed NASA now serves `v2.0` files, which the version check refuses;
> happy to open a separate issue.

## Waiting for Yuri

1. Read the diff (`git -C ~/work/crc/forks/crc-sdk diff`) and the draft text above.
2. Say go to commit, create the fork `shlyakh/crc-sdk`, push the branch and open the pull request. Creating
   the fork was blocked by the session's permission settings, so it needs either an explicit go-ahead or
   doing by hand (`gh repo fork RiskThinking/crc-sdk --clone=false`).
3. Things to know: crc-sdk is AGPL-3.0-or-later with copyright held by Riskthinking.AI and no contributor
   agreement.

After the pull request is open: note it in `CHANGELOG-upstream.md`; when a release carries the fix, raise
the pin and update the NEX row in `docs/sources-track/requirements.md`.
