# Agent guide — crc-lab

Current work: a data explorer for Climate Risk Commons (CRC) data, Texas, and a hail-risk pipeline for solar
plants. Built: the explorer (source-centric, nine sources), NOAA Storm Events on H3 cells (Phase 2), hail and
gust curves (Phase 3), solar plants with value and hail exposure, reporting-bias model and radar (Phase 4),
hail impact functions v0 and loss per plant (Phase 5, 2026-11-10, awaiting review). One branch: `main`.

The explorer (redesigned in Phase 6, `docs/reports/6-explorer-redesign.md`) is one static page holding two
projects, switched in the top row (their tabs sit in a second row beneath; the tour ends on Beryl 2024 in the storm player): "Texas hail risk" (new work: Risk, Hail evidence, Methods) and "Texas CRC data"
(an explorer of what crc-sdk already reaches: Data, About). `site/layers.json` stays the registry of sources and
layers (`groups`, `sources` with an `origin`, layers with a `source_id`); the Risk tab reads the generated
`site/data/assets/plants.json`, `plants_detail.json` and `curves.json`.

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
- Damage curves: hail impact functions v0 are specified in `docs/requirements-hail-impact-v0.md` and built
  as Phase 5 (`src/crc_lab/impacts/`); every number there carries a source tag, and placeholders stay labelled as placeholders.

## Layout

- `docs/` — requirements, plan, reports (one per phase), primers, explainers, archive; `docs/research/` holds
  background research (web-sourced, unverified until checked; e.g. `solar-plant-data-sources.md`)
- `src/crc_lab/explorer/` — data build: `texas.py` (boundary, cells), `catalog.py` (E1), `hazards.py`
  (per-hazard files, `for_assets` check), `build.py` (`python -m crc_lab.explorer.build`), `check_site.py`
- `src/crc_lab/storm_events/` — `plan.py` (S1 snapshot), `parse.py` (S2), `geometry.py` (S3 cells),
  `table.py` (S4 event table + data card), `compare.py` (S5), `explorer_layer.py` (S6),
  `build.py` (`python -m crc_lab.storm_events.build [--compare]`)
- `src/crc_lab/explorer/sources.py`, `tracks.py` — files built through crc-sdk under `site/data/sources/`
  (IBTrACS tracks with wind radii, CO-OPS, GHCNh, ERA5 baseline)
- `src/crc_lab/curves/` — `annual_maxima.py` (C1), `fit.py` (C2 pooling, C3 `from_table`, cards, `for_assets`
  checks), `sensitivity.py`, `build.py` (`python -m crc_lab.curves.build [--sensitivity] [--verify]`)
- `src/crc_lab/assets/` — `solar.py` (USPVDB asset table), `value.py` (NREL ATB cost, `reference/`),
  `exposure.py` (hail at the asset by local report density), `real_estate.py` (Fort Bend comparison),
  `build.py` (`python -m crc_lab.assets.build [--sensitivity]`)
- `src/crc_lab/radar/` — `mrms.py` (MRMS hail size grid), `swdi.py` (NEXRAD hail signatures 1995 on), `analysis.py`,
  `build.py`, `compare_cells.py` (four-source hail days per cell); `src/crc_lab/decisions.py` (decisions document)
- `src/crc_lab/impacts/` — Phase 5: `hail_v0.json` (the spec's parameters), `hail_curves.py` (the four v0 curves; numpy only,
  no crc imports, liftable into crc-sdk), `annual.py` (events to a year's damage ratio, capped), `crc_adapter.py`
  (tabulated `ImpactExpression`s), `build.py` (`just impacts`: loss per plant, report 5, plant panel fields)
- `docs/algorithms.md` (every calculation: formula, averaging, parameters, weakness; update it when an algorithm
  changes), `docs/plan-radar-loss-and-buildings.md` (draft plan for Phases 7 and 8);
  `src/crc_lab/assets/regional.py` (bias correction per region, the third basis)
- `docs/handover-plan.md` (state at the pause of 2026-11-11, where CRC is used, upstream candidates, next stages)
- `docs/open-questions.md` (questions waiting for Yuri), `docs/plan-explorer-next.md` (explorer plan, draft)
- `docs/hail-data-processing.md`, `docs/decisions.md`, `docs/data-sources.md` — how hail is processed, what was
  chosen and why, and every data source
- `docs/sources-track/` — requirements and plan for the other crc-sdk sources (probes in `tools/probes/`)
- `site/` — the static explorer, no build step: `index.html`, `style.css` (tokens, Risk tab), `sources.css`, `js/`
  (ES modules: `main.js` shell and projects, `risk.js` + `charts.js` Risk tab, `sources.js` + `views/` the source tabs
  shared by Hail evidence and Data, `methods.js` Methods and About, `demo.js` the tour), `layers.json` (registry),
  `sources.json` (hand-written catalogue); `site/next/index.html` only forwards old links
- `src/crc_lab/explorer/risk_layer.py` — the Risk tab's data files (plants with measures and class breaks, report
  circles and outlines, damage curves as values); run by `just impacts`
- `tools/smoke.mjs` (`node tools/smoke.mjs <out dir> [url] [width] [height] [--no-demo]`), `tools/record-demo.mjs` —
  headless Chrome smoke test and tour recorder; `site/data/` is generated and git-ignored except `sources/`,
  `assets/` and `hail_compare/`
- `tests/` — pytest, offline; `test_pins.py` guards the pins, `test_explorer.py` the build helpers,
  `test_storm_events.py` the parser and cells on `tests/fixtures/` (a fixed 2024 sample), `test_curves.py`
  the annual maxima and pooling on a synthetic event table
- `justfile` — `just data`, `just verify`, `just storm-events`, `just storm-events-compare`, `just curves`,
  `just curves-sensitivity`, `just site`, `just all`, `just serve`, `just up`, `just test`, `just lint`
- `Dockerfile`, `Caddyfile`, `compose.yaml` — one container serving `site/` (E8); `.github/workflows/pages.yml`

Explorer conventions: curves are evaluated in Python at return periods 2–500 years and shipped as values
plus raw parameters; the page never re-implements a curve. Texas cells are those intersecting the state
polygon. Browser libraries are pinned by URL in `index.html` (h3-js before deck.gl; MapLibre as ESM).

## Releases and branches

- One branch: `main`. Side work happens in short-lived branches and is merged; no long-lived preview branches.
- `site/demo.webm` is re-recorded after each major release (`node tools/record-demo.mjs <work dir> <url>` against
  `just serve`), not on every change.
- `site/data/sources/` (IBTrACS, CO-OPS, GHCNh, ERA5 files built through crc-sdk) is committed; rebuild with
  `just sources` when fresher data is wanted or a pin changes. Everything else under `site/data/` is built in CI.
- Source groups in `site/layers.json`: "Reached through crc-sdk" and "Experimental new sources" (second).

## Checks

```sh
just test     # uv run pytest -q
just lint     # uv run ruff check src tests && uv run ruff format --check src tests
```
