# Agent guide — crc-lab

Current work: a data explorer for Climate Risk Commons (CRC) data, Texas, and a hail-risk pipeline for solar
plants. Built: the explorer (source-centric, nine sources), NOAA Storm Events on H3 cells (Phase 2), hail and
gust curves (Phase 3), solar plants with value and hail exposure, reporting-bias model and radar (Phase 4),
hail impact functions v0 and loss per plant (Phase 5, 2026-11-10, awaiting review). One branch: `main`.

Since V5 (2026-11-12, `docs/validation/reports/V5-split-into-projects.md`) the site is one page per project
behind a landing page: `site/index.html` (landing; forwards addresses from before the split), `site/hail/`
("Texas hail risk": Risk, Hail evidence, Methods), `site/validation/` (assessments) with
`site/validation/explore/` ("Texas CRC data": an explorer of what crc-sdk already reaches; Texas data, About).
The hail tour ends on Beryl 2024 in the storm player, which is on the explorer page. Shared by the hail and
explorer pages: the map viewer and styles in `site/shared/`, the data under `site/data/`, and
`site/layers.json`, the registry of sources and layers (`groups`, `sources` with an `origin`, layers with a
`source_id`; origin `crc-lab` shows on the hail page, `crc-sdk` on the explorer). The Risk tab reads the
generated `site/data/assets/plants.json`, `plants_detail.json` and `curves.json`.

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

## Projects in this repository

crc-lab holds separate projects. Each has its own package and page; `tests/test_projects.py` keeps the
packages apart (`crc_lab` and `crc_data_explorer` may import `lab_common` only; `data_source_check` imports
none of them).

- **Texas hail risk**: package `src/crc_lab/`, page `site/hail/`, check `just site-hail`.
- **Texas CRC data explorer**: the map side of the validation project. Package `src/crc_data_explorer/`,
  page `site/validation/explore/`, check `just site-explorer`.
- **Shared**: `src/lab_common/` (version pins, Texas boundary and cells, atomic JSON writer, the
  horizon-file writer, site-check helpers), `site/shared/`, `site/data/`, `site/layers.json`.
- **Source validation** (started 2026-11-11): explores, verifies and validates the data sources of a
  climate-risk framework, crc-sdk first. Package `src/data_source_check/` (`core/` record format,
  inventory and comparison, `reference/` independent readers, `adapters/crc/` the only code that calls
  crc-sdk, `assessments/` one module per assessed source, `sources/crc_sdk/` one TOML file per source
  with its transformation statement, plus `findings.toml`), docs `docs/validation/` (`method.md`,
  `requirements.md` with IDs V1..., `plan.md`, generated `inventory.md` and `sources/<id>.md`,
  `reports/V<n>-*.md`, `references/` texts that are cited, each with checksum and passages: SR 26-2, NASA's NEX v2 note), page `site/validation/` (data
  and `data/records/<id>.json` committed), tests `tests/validation/`, `just validation` (offline
  rebuild), `just validation-assess <id>` (live run; caches under `data/cache/validation/`),
  `tools/smoke-validation.mjs`. Assessed so far: IBTrACS (V1), GHCNh (V2), NEX-GDDP-CMIP6 (V3; its
  temperature recipes are also run against the fixed clone `../forks/crc-sdk`, labelled as such).
  Monitoring (V4): `just validation-monitor` (HEAD requests; writes `docs/validation/monitoring.md`),
  `just validation-monitor-rerun` (stages a re-run), `just validation-accept <id>` (a person publishes
  it); `.github/workflows/validation-monitor.yml` runs weekly once pushed and never commits.
  Drafts (V6): the skill `.claude/skills/draft-source-assessment/` drafts an unassessed source;
  `just validation-brief <id>`, `just validation-draft <id>` (records to `data/cache/validation/drafts/`,
  never the page), `just validation-draft-check <id>` (gate), `just validation-draft-accept <id>` (a
  person publishes); notes in `docs/validation/drafts/`.
  Rules of its own: `core/` and `reference/` never import crc-sdk; the package imports nothing from
  `crc_lab`; the page and reports are generated from records, never typed; findings are worded neutrally
  (documented, observed, consequence) with no grades; an assessment is a draft until Yuri signs it;
  nothing is reported upstream until Yuri has reviewed the draft in `local/upstream-review.md`
  (git-ignored); phases V0 to V7 each end with a report and a stop.
- **Upstream contributions**: docs only (`docs/reports/u<n>-*.md`, `docs/plan-upstream-storm-events.md`);
  the code lives in `~/work/crc/forks/crc-sdk`. Nothing is pushed or opened upstream without Yuri's go.

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
- `src/lab_common/` — `texas.py` (boundary, cells, `write_json_atomic`), `horizons.py` (one JSON per horizon
  from a canonical Parquet), `site.py` (site-check helpers), `PINNED`
- `src/crc_data_explorer/` — data build of the Texas data explorer: `catalog.py` (E1), `hazards.py`
  (CRC Open hazards, `for_assets` check), `build.py` (`python -m crc_data_explorer.build`), `check_site.py`
- `src/crc_lab/storm_events/` — `plan.py` (S1 snapshot), `parse.py` (S2), `geometry.py` (S3 cells),
  `table.py` (S4 event table + data card), `compare.py` (S5), `explorer_layer.py` (S6),
  `build.py` (`python -m crc_lab.storm_events.build [--compare]`)
- `src/crc_data_explorer/sources.py`, `tracks.py` — files built through crc-sdk under `site/data/sources/`
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
- `site/` — static pages, no build step: `index.html` + `landing.css` (landing), `hail/` (`index.html`, `hail.js`
  shell, `risk.js` + `charts.js` Risk tab, `methods.js`, `demo.js` the tour), `validation/` (assessments page) and
  `validation/explore/` (`index.html`, `explore.js` shell, `about.js`, `tour.js` the tour's last part), `shared/`
  (`style.css` tokens and header, `sources.css`, `util.js`, `sources.js` + `views/` the map viewer used by Hail
  evidence and Texas data), `layers.json` (registry), `sources.json` (hand-written catalogue);
  `site/next/index.html` only forwards old links
- `src/crc_lab/risk_layer.py` — the Risk tab's data files (plants with measures and class breaks, report
  circles and outlines, damage curves as values); run by `just impacts`
- `tools/smoke.mjs` (`node tools/smoke.mjs <out dir> [url] [width] [height] [--no-demo]`; `url` is the site root; it
  covers the hail page, the explorer page, the landing page and old addresses), `tools/record-demo.mjs` —
  headless Chrome smoke test and tour recorder; `site/data/` is generated and git-ignored except `sources/`,
  `assets/` and `hail_compare/`
- `tests/` — pytest, offline; `test_pins.py` guards the pins, `test_explorer.py` the build helpers,
  `test_storm_events.py` the parser and cells on `tests/fixtures/` (a fixed 2024 sample), `test_curves.py`
  the annual maxima and pooling on a synthetic event table
- `justfile` — `just data`, `just verify`, `just storm-events`, `just storm-events-compare`, `just curves`,
  `just curves-sensitivity`, `just site` (= `site-hail`, `site-explorer`, `site-validation`), `just all`, `just serve`, `just up`, `just test`, `just lint`
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
