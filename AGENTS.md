# Agent guide — crc-lab

Current work: a data explorer for Climate Risk Commons (CRC) data and a NOAA Storm Events source, for Texas.
Then hail and thunderstorm-gust hazard curves brought into CRC, and two asset sets (solar farms, real estate).

Read first:

- `docs/requirements.md` — what to build, with IDs
- `docs/implementation-plan.md` — phases, steps, and the test for "done" in each
- `docs/primers/event-sources-in-crc.md` — how event records relate to CRC's curves

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

- `docs/` — requirements, plan, primers, explainers, archive
- `src/crc_lab/` — package
- `tests/` — pytest; `test_pins.py` guards the pins

## Checks

```sh
uv sync --all-extras --group dev
uv run pytest -q
uv run ruff check src tests
```
