# Agent guide — crc-energy

Present-day physical climate risk for energy infrastructure (transmission lines and towers, substations) on
Climate Risk Commons (CRC). First phase uses reanalysis and observations (ERA5, NOAA ISD/GHCNh), not CMIP
projections; CRC Open (SSP5-8.5) is a later, labelled stress case.

Companion documents (Claude docs): plan, requirements (USE / OUTSIDE / EXTEND per component), explainers note.

## Rules

- Pin `crc-sdk==0.11.1` and `crc-framework==0.6.0`; record both plus the impact-registry revision in every output.
- Every hazard dataset declares `probability_semantics`, `source_return_period_convention`, `temporal_window`, provenance.
- Every wind impact definition declares averaging period and gust factor.
- Label r5-cell results "regional screening" (cell ≈ 253 km²).
- Keep three loss channels separate: damage, derating, liability.
- Licences: crc-* are AGPL-3.0-or-later; CRC Open is CC BY-NC 4.0 (no commercial use); OSM is ODbL (publish code and OSM-derived tiles, not merged OSM+hazard tables).
- Write outputs atomically (temp file, then `os.replace`). English everywhere.

## Layout

- `docs/explainers/` — animated HTML explainers (D0): `anatomy.html`, `primer.html`
- `src/crc_energy/` — package (hazard layer, impacts, aggregate, schema — to come)
- `tests/` — pytest + Hypothesis; `test_pins.py` guards the pins
- `CHANGELOG-upstream.md` — crc releases watched and their effect here

## Checks

```sh
uv sync --all-extras --group dev
uv run pytest -q
uv run ruff check src tests
```
