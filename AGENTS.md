# Agent guide — crc-lab

Current work: a data explorer for Climate Risk Commons (CRC) data, Texas, with eight CRC Open hazards
(Phase 1). Deferred until that is reviewed: a NOAA Storm Events source, hail and thunderstorm-gust curves,
and two asset sets (solar farms, real estate).

Read first:

- `docs/requirements.md` — what to build, with IDs
- `docs/implementation-plan.md` — phases, steps, and the test for "done" in each
- `docs/primers/event-sources-in-crc.md` — how event records relate to CRC's curves (Phases 2–3)

Reference clones, read-only, pinned to the versions this repo uses (see `../README.md`):

- `../upstream/crc-sdk/` (v0.11.1) — `docs/README.md` indexes every page; `docs/concepts.md` for plans, the
  canonical dataset and probability conventions; `docs/sources/crc-open.md` for the release layout;
  `crc_sdk/workflows/*.py` docstrings are the parameter reference.
- `../upstream/crc-docs/` — notebooks, pipelines, and the five end-user skills under `.agents/skills/`
  (the pattern for any skill this repo ships later; not needed for building the explorer).
- `../upstream/crc-framework-rs/` (v0.6.0) — the Rust numerical core; reference only.

Earlier scope (energy infrastructure, ERA5 layers, dependence) is in `docs/archive/` and is not current.

## Rules

- Work one phase at a time. Stop after each phase for review. Write a short report in `docs/reports/`.
- Never invent a number. If a data source cannot be reached, say so and stop.
- Pin `crc-sdk` and `crc-framework`; record versions in every output. Log upstream changes in `CHANGELOG-upstream.md`.
- Every dataset gets a data card: source, date fetched, licence, coverage, known biases.
- Curves built from storm reports say so: an empty cell may be unobserved.
- Label cell-level results "regional screening" (a cell is about 253 km²).
- Licences: crc-* code is AGPL-3.0-or-later; CRC Open data is CC BY-NC 4.0 (non-commercial, with attribution);
  NOAA and USGS data ask for attribution.
- Write outputs atomically (temp file, then `os.replace`). English everywhere.
- Damage curves are out of scope here; they are being researched separately.

## Layout

- `docs/` — requirements, plan, reports (one per phase), primers, explainers, archive
- `src/crc_lab/` — package
- `tests/` — pytest; `test_pins.py` guards the pins
- `justfile` — `just setup`, `just test`, `just lint`; data and site targets arrive with Phase 1

## Checks

```sh
just test     # uv run pytest -q
just lint     # uv run ruff check src tests && uv run ruff format --check src tests
```
