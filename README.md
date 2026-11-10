# crc-lab

A lab for working with [Climate Risk Commons](https://climateriskcommons.org/) (CRC) data, Texas first.

**Now:** a data explorer — a catalogue of what CRC Open holds, and a map of Texas with eight of its hazard
layers (hottest day, coldest night, wettest day, river flood, wind, fire weather, drought index, hot days).

**Coming, in this order, each after the previous is reviewed:**

1. NOAA Storm Events as a cleaned source on H3 cells, compared across two copies of the data.
2. Hail and thunderstorm-gust hazard curves derived from it and brought into CRC.
3. Asset sets: solar farms (energy) and real estate.

Status: requirements and plan agreed 2026-11-10; Phase 0 (setup) in progress. See `docs/requirements.md`
and `docs/implementation-plan.md`. Earlier scope is in `docs/archive/`.

## Explainers (D0)

Two self-contained animated pages; open them in a browser or from GitHub Pages:

- `docs/explainers/anatomy.html` — **Anatomy of one CRC question**: `which_sites_are_most_at_risk.py` traced call by
  call through its three routes, with object and data shape at each step. Closing finding: no public crc-docs example
  calls `compute_risk`.
- `docs/explainers/primer.html` — **Climate risk curves, animated**: the five ideas of crc-docs' curves primer, with
  the sampling and L-moment GEV fitting running live in the page.

## Setup

```sh
uv sync --all-extras --group dev
uv run pytest -q
```

Pinned: `crc-sdk==0.11.1`, `crc-framework==0.6.0` (see `CHANGELOG-upstream.md`).

## Licence

AGPL-3.0-or-later (inherits from `crc-framework` / `crc-sdk`). CRC Open data, when used, is CC BY-NC 4.0 and
is excluded from any commercial output. OSM-derived geometry is ODbL.
