# Phase 0 report: setup and checks

Date: 2026-11-10 · crc-sdk 0.11.1 · crc-framework 0.6.0 · CRC Open release `ssp585-global-2026-10-20-v1`

## What was done

- Repo renamed `crc-energy` → `crc-lab` (GitHub redirects the old URL); package `crc_lab`.
- Scope narrowed: Phase 1 (explorer, eight CRC Open hazards) is current; Phases 2–4 deferred until it is reviewed.
  README, requirements §1, implementation plan and AGENTS.md say so.
- `pyproject.toml` rewritten for the current scope: description; `dependence` extra (pyvinecopulib, networkx) and
  `lmoments3` dropped; ruff lint rules `E F I UP B`. Full dependency set resolves on Python 3.12 / macOS arm64.
- Added `CLAUDE.md` (imports `AGENTS.md` and the upstream crc-sdk agent guide), `.envrc` (direnv), `justfile`
  (`setup`, `test`, `lint`, `fix`, `data`, `site`, `all`), `docs/reports/`, `.claude/skills/` symlinks to the five
  crc-docs skills (git-ignored: machine-specific).
- Reference clones beside the repo: `../upstream/crc-sdk` (v0.11.1), `../upstream/crc-docs` (main),
  `../upstream/crc-framework-rs` (v0.6.0). Layout described in `../README.md`.
- Pins confirmed: both are the latest PyPI releases on 2026-11-10. Nothing to log in `CHANGELOG-upstream.md`.
- `just test`: 1 passed. `just lint`: clean.

## Checks

| # | Check | Answer |
| --- | --- | --- |
| 1 | Pins vs PyPI | crc-sdk 0.11.1 and crc-framework 0.6.0 are the latest. Pin test passes. |
| 2 | Hazards in the release | 63, as the requirements appendix says. Licence `CC-BY-NC-4.0`; attribution "Riskthinking.AI bias-corrected climate distributions". `excluded_hazards` is empty. |
| 3 | Horizons actually present | 2025–2090 in 5-year steps (14 horizons) for the seven r5 hazards; `rflood` runs to 2100 (16). The planned 2030, 2050 and 2080 all exist. |
| 4 | `curve_kind` per hazard, Texas bbox (table below) | **Mixed in every hazard.** Most rows are `hurdle` + `gumbel_r`, the rest `fitted` + `gumbel_r`; `rflood` is mostly `hurdle` + `genextreme` with `point_mass`, `tabulated`, `fitted` and `no_data` rows; `hot_days` has all five kinds. |
| 5 | Texas resolution-5 cell count | **2,384** cells with centre inside the state polygon, **2,564** intersecting it; the bounding box holds **5,118**. Source: Census TIGER `cb_2024_us_state_500k`. Average r5 cell 253 km². `rflood` is r7 (49 children per r5 cell), so about 117,000–126,000 cells. |
| 6 | Data volume per hazard | Texas bbox resolves to 4 r0 partitions, 13–16 MB and ~800,000 rows per r5 hazard (69 MB, 3.9 M rows for `rflood`); DuckDB reads them over HTTP in 1.3–3.8 s each. After clipping to Texas: ~2,384 cells × 14 horizons ≈ 33,000 rows per r5 hazard. |
| 7 | Browser library versions | Pin: `maplibre-gl` 6.16.0 (2026-10-25), `deck.gl` 9.4.0 (`@deck.gl/core`, `@deck.gl/geo-layers` for `H3HexagonLayer`, `@deck.gl/mapbox` for `MapboxOverlay`; 2026-09-05), `pmtiles` 4.5.0, `h3-js` 4.5.0. deck.gl 9 documents MapLibre support through `MapboxOverlay`; confirm with a smoke page as the first Phase 1 step. |
| 8 | Catalogue fields for E1 | `catalog().hazards[name]` is a `CRCHazard` with `unit`, `value_semantics`, `tail`, `h3_resolution`, `probability_semantics`, `notes`, `pooling`, `pathways`, `horizons`, `partitions`. Enough to generate the catalogue page without hand-written text. `no_data_reasons` lists the four reason codes. |
| 9 | Storm Events format; NSI access | Not checked: deferred with Phases 2 and 4. |

### Curve kinds by hazard (rows in the four Texas-bbox partitions, all horizons)

| Hazard | hurdle | fitted | point_mass | tabulated | no_data | Families |
| --- | --- | --- | --- | --- | --- | --- |
| tx_max | 510,068 | 289,906 | – | – | – | gumbel_r |
| tn_min | 658,982 | 140,992 | – | – | – | gumbel_r |
| rx1day | 669,899 | 130,075 | – | – | – | gumbel_r (1 genextreme) |
| rflood | 3,672,506 | 6,471 | 121,359 | 52,539 | 2,389 | genextreme |
| wind_max_daily_max | 687,915 | 112,059 | – | – | – | gumbel_r |
| fwi | – | 799,974 | – | – | – | gumbel_r |
| spei | 578,507 | 221,447 | – | – | 20 | gumbel_r |
| hot_days | 739,389 | 50,830 | 4,214 | 204 | 5,337 | gumbel_r, genextreme |

Counts cover the whole r0 partitions (far more than Texas); the mix inside Texas will differ, but every kind must be
handled. `rflood` carries the `CRCOpenWarning` "scenario-compatible SSP585-labelled curves; not independently fitted".

## Consequence for E4 (curve on click) — recommendation for Phase 1

The 2026-11-10 decision was "ship curve parameters to the browser; no API". Check 4 shows that reproducing the curves
in JavaScript means implementing Gumbel and GEV quantiles, the hurdle atom-plus-tail rule, point masses, tabulated
interpolation and five no-data reasons, then proving it equals crc-sdk. Cheaper and exact: have crc-sdk evaluate each
cell's curve at a fixed grid of return periods during the data build
(`crc_sdk.workflows.distributions.curve_quantiles(table, probabilities)`; `crc_sdk/workflows/tiling.py` already does
this per row for tiles) and ship those values. The browser then draws a polyline and interpolates; the "matches
`for_assets` at the cell centre" test holds by construction. The "no API" decision stands. Suggested grid: return
periods 2, 5, 10, 20, 50, 100, 200, 500. Decide at the start of Phase 1.

## Not done / for the user

- Claude Code asks once per project to approve the out-of-tree import `@../upstream/crc-sdk/AGENTS.md` in
  `CLAUDE.md`; accept it the first time `claude` starts in this folder.
- Push to GitHub (done by the setup session; check `git log origin/main`).

## Numbers behind this report

Scripts and outputs are not committed (scratch). The checks ran with `uv run python` inside this repo's environment,
reading CRC Open over HTTPS and the TIGER boundary from `www2.census.gov`.
