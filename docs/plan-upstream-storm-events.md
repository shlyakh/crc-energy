# Plan (saved, not started): Storm Events adapter for crc-sdk, hail as questions

Saved 2026-11-11 from the planning session on upstream contributions. Nothing here is started. The first
upstream pull request is the smaller NEX-GDDP-CMIP6 fix (report `reports/u1-nex-bytes-fix.md`); this plan
follows it. Working copy for upstream work: `~/work/crc/forks/crc-sdk`.

## Context

Before Phase 7 (loss from radar hail), Yuri wants to know what it takes to move the NOAA Storm Events
source and the hail impact functions into Climate Risk Commons, and whether to contribute now or wait for
radar data and a fuller impact library.

What the review of upstream found:

- **There is no "data commons" to add a dataset to.** CRC Open is a hosted release that Riskthinking.AI
  publishes itself. The home for Storm Events is a source adapter in crc-sdk: code that fetches NCEI files
  on the user's machine. The closest template is `IBTrACSPlan` (also NOAA NCEI event data).
- **The impact library is compiled Rust** in crc-framework-rs with 13 hard-coded factors. No hail factor,
  no millimetre unit alias, no solar or energy asset class (asset type is a free-text `building_type`), no
  uncertainty field. Adding a factor is a coordinated Rust and SDK change. The alternative is portable
  impact definitions (JSON, `published` provenance), which need no framework change.
- **No contribution process is documented.** In practice the team works by pull request (41 PRs, 0 issues),
  one maintainer merges a source adapter about once a week, and outside PRs exist (#41 is open now).
- **crc-lab readiness:** `storm_events/plan.py` and `parse.py` are generic; `table.py`, `compare.py` and the
  boundary defaults are Texas-locked. The hail curves are liftable code, but carry placeholders (stow,
  cost share, footprint), unverified Swiss parameters, and have no validation against observed losses.

Decisions from the interview:

| Question | Decision |
| --- | --- |
| Goal | Early design feedback from the maintainers, not completeness |
| First step | One small adapter PR to `RiskThinking/crc-sdk`; hail goes in as questions, not code |
| Adapter scope | Raw plan only (NOAA columns as strings), upgraded later if CRC adds richer event types |
| Hail questions | Hail hazard factor; home for cited curves and asset attributes; event-based annual loss |
| Held back | Report-based hazard curves and the bias correction, until radar (Phase 7) gives evidence |
| Sequencing | PR first as its own short phase with report and review; then Phase 7 starts without waiting |

So the answer to "should I wait": no for Storm Events (it fits their pattern today), yes for the curves as
code (they need upstream design decisions first, which the PR asks for).

## Work

### 1. Set up a working copy (no change to `upstream/`, which stays the read-only pin)

- Fork `RiskThinking/crc-sdk` to `shlyakh/crc-sdk` (no fork exists yet; `gh` is logged in as `shlyakh`).
- Clone to `~/work/crc/forks/crc-sdk`, branch `feat/storm-events-plan` from the current upstream `main`
  (not from the 0.11.1 pin: upstream moves weekly).
- Read `docs/development.md` and check for a changelog convention before writing code.

### 2. Write the adapter in the fork

New file `crc_sdk/workflows/storm_events.py`, modelled line for line on
`crc_sdk/workflows/ibtracs.py`, with the snapshot logic ported from
`crc-lab/src/crc_lab/storm_events/plan.py`.

- `StormEventsPlan(cache_dir, mode="reuse", expected_sha256=None)`; frozen dataclass; modes
  `reuse | offline | refresh`.
- Selectors return a new plan: `.years(start, end)` (not before 1950), `.for_states([...])`,
  `.for_event_types([...])`. Filters match NOAA's own `STATE` and `EVENT_TYPE` strings.
- `explain()` does no I/O: directory URL, file-name pattern, selection, and a note that NCEI rewrites files
  in place.
- `prefetch()`: read the NCEI directory listing, take the newest creation date per year and file type
  (`details`, `locations`, `fatalities`), download each `.csv.gz`, record per file URL, SHA-256, size, ETag,
  Last-Modified, retrieval time, terms URL and citation. `expected_sha256` is a mapping of file name to
  digest (the per-year form their docs already describe).
- `batches(file="details", batch_size=4096)`: Arrow batches, NOAA column names, every column a string,
  empty fields as null. No unit conversion, no time-zone handling, no cells.
- Reuse upstream helpers in `crc_sdk/workflows/_remote.py`: `cached_snapshot`, `check_expected_sha256`,
  `file_checksum`, `http_request`, `write_manifest` (and `manifest_lock` if several files are written).
- Carry over the known file defect from crc-lab report 2 (the 1997 details file has one row with unescaped
  quotes): either parse it or fail with a clear message, and say which in the docs.

Other files in the fork:

- `crc_sdk/workflows/__init__.py`: export `StormEventsPlan` in `__all__`.
- `tests/test_storm_events.py`: offline, same shape as `tests/test_ibtracs.py` (monkeypatched opener; a
  small gzip fixture built in the test): snapshot and filtered batches, newest-file choice from a listing,
  missing and mismatched snapshots, invalid arguments.
- `docs/sources/observations.md`: one table row and one "Interpretation limits" bullet, taken from
  `KNOWN_BIASES` in `crc-lab/src/crc_lab/storm_events/table.py` (reports follow people and roads; type
  coverage changed in 1955 and 1996; sizes are mostly estimates; times are local standard time; damage is
  nominal; files are rewritten in place).
- `docs/data-licences.md`, `docs/README.md`, `README.md`: add Storm Events where IBTrACS is listed.

Not in this PR: typed columns, geometry and H3 cells, the Source Cooperative comparison, any crc-docs
notebook (offered as a follow-up in the PR text).

### 3. Checks

In the fork:

```sh
uv sync --all-extras
uv run pytest -q
uv run mypy
uv run ruff check . && uv run ruff format --check .
```

One live check, run by hand and not added to the test suite: `prefetch()` and `batches()` for 2024, then
compare the count of Texas hail rows and the Fort Bend event 1158847 (2.75 in) with crc-lab's
`data/storm-events/events.parquet`. Then a replay with `mode="offline"` and the recorded digests.

### 4. Report and stop for review (in crc-lab)

- `docs/reports/u1-storm-events-adapter.md`: what was built, check results, the live comparison, and the
  full draft of the PR description.
- PR description, kept short: what the adapter does and what it deliberately does not; a link to the live
  explorer as the use case; then three questions:
  1. Would you accept hail size as a hazard factor (observed diameter in mm; radar-estimated size as a
     separate factor later)?
  2. Where should cited damage curves live (portable impact definitions in crc-sdk or crc-docs, or the
     compiled registry), and where do asset attributes such as glass type, stow and roof class belong?
  3. Is an event-based annual loss step (each event through the curve, a year's events added and capped)
     wanted, planned, or out of scope?
- **Stop.** Nothing is pushed and no PR is opened until Yuri has read the report and says go.

### 5. After the go-ahead

- Rebase on upstream `main`, push the branch to the fork, open the PR against `RiskThinking/crc-sdk`.
- In crc-lab: add the PR link to `docs/handover-plan.md` (Stage D) and `docs/open-questions.md`; leave
  `storm_events/plan.py` in place until the adapter is merged and the pin is raised, then switch to the
  upstream plan, rerun `just all`, compare numbers and log it in `CHANGELOG-upstream.md`.
- Start Phase 7 without waiting. Until the maintainers answer question 1, Phase 7 keeps the provisional
  factor names `hail_diameter_obs_mm` and `hail_mesh_mm`.

## Things to know before starting

- crc-sdk is AGPL-3.0-or-later with copyright held by Riskthinking.AI, and there is no CLA or DCO. The
  contribution stays under AGPL with Yuri as author of his commits; the company also sells a commercial
  product (CDT). Worth a moment's thought, not a blocker.
- There is no record of how quickly outside PRs are answered. If there is no reply, nothing in crc-lab
  depends on it.
- Not started by this plan: checking the Swiss curve parameters, replacing placeholders, recasting the
  curves as portable definitions. Those wait for the maintainers' answers and for Phase 7.

## Verification

- The four fork checks pass, including the new offline test.
- The live 2024 comparison matches crc-lab's event table (row count for Texas hail, event 1158847).
- Offline replay with recorded digests returns the same batches.
- `just test` and `just lint` in crc-lab still pass (crc-lab code is unchanged apart from docs).
