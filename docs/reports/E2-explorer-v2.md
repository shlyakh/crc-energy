# E2 report: explorer v2, source-centric, IBTrACS first

Date: 2026-11-10 · branch `explorer-v2` (not merged) · crc-sdk 0.11.1 · crc-framework 0.6.0 · awaiting review.
Request: "redo the explorer; explore other sources, starting with IBTrACS; show the RiskThinking CMIP data as
one of the sources, not as the main source."

## What changed

- **The top-level choice is the source, not the hazard.** The left panel lists seven sources, each with a
  one-line description, a status pill (loaded / prototype) and its licence. Selecting one shows its own
  controls, its caveats and its click panel. The page is "Texas climate data explorer"; CRC's name sits on the
  CRC Open source and in the attribution. The default source is IBTrACS.
- **Registry v2** (`site/layers.json`): a top-level `sources` list (id, title, provider, short, returns,
  coverage, licence, status, caveats) and a `source_id` on every layer. It is still the only place a source or
  layer is declared; `check_site` fails if a layer names an undeclared source.
- **"Also show"** replaces the layer toggles: any non-cell layer (tracks, reports, stations) can be drawn over
  the active source, e.g. cyclone tracks over CRC Open cells. Cell layers show one at a time, through their source.
- **Sources tab** (was Catalogue): a table of the sources in the explorer (provider, what it returns,
  coverage, licence, status) and the planned ones; then CRC Open's 63 hazards; then the other sources crc-sdk
  reaches.
- Kept: no build step, pinned CDN libraries, the hazard-cells code path, the click panel and chart, the
  `points-binary` Storm Events layer, the generic `points` layer kind, the smoke test (rewritten to walk every
  source: `node tools/smoke.mjs <out> [url]`).

## The sources

| Source | Shows | Status | Size |
| --- | --- | --- | --- |
| Tropical cyclone tracks (IBTrACS) | 91 storms, tracks coloured by wind or category, storm list and filters, along-track wind chart | loaded | 223 KB |
| Storm reports (NOAA Storm Events, Phase 2) | 107,549 located reports, type and year filters, NCEI link | loaded | 2.6 MB |
| Hail and gust curves from storm reports (Phase 3) | two cell layers, horizon 2025 | loaded | 2 files |
| Coastal water levels (NOAA CO-OPS) | 9 stations, 22 published levels each, station list | prototype | 9 KB |
| Airport station temperatures (GHCNh) | 8 stations with a crc-sdk GEV curve | prototype | 5 KB |
| ERA5 reanalysis baseline | hottest day 1991–2020 on 1,439 r4 cells | prototype | 181 KB |
| CRC Open climate projections (RiskThinking.AI, CMIP6-based, SSP5-8.5) | eight hazards on cells, three horizons, 63 listed | loaded | 14.5 MB |

## IBTrACS, the worked example

- **Data** (`src/crc_lab/explorer/tracks.py`, built by `just sources`): the North Atlantic basin file through
  `IBTrACSPlan` (SHA-256, retrieval time and the Schreck et al. 2024 citation carried into the file and the
  manifest). Kept: storms with a best-track point inside the Texas box, seasons 1950–2025. Result: **91 storms,
  first season 1954, last 2024, 3,872 track points, 223 KB**, built in 1.1 s from the cached snapshot. The
  sources track had 54 storms for 1980–2024; going back to 1950 adds 37.
- Tracks are clipped to a Gulf box (110°W–75°W, 14°N–45°N), wider than before, so the approach is visible.
- Per point: position, wind (WMO agency wind where present, else the US agency wind; all 91 storms have wind),
  pressure, NOAA's Saffir-Simpson category, time, nature.
- **Page**: line segments coloured by wind on one sequential ramp (20–140 kt) or by category; filters for
  season range, name and minimum peak wind; a storm list; clicking a track or a list row highlights the storm
  and opens a panel with season, peak wind (whole shown track and over Texas), lowest pressure, category, time
  over Texas and a wind-along-track chart with the Texas stretch shaded. Hover gives storm, time and wind.
- 17 storms reach 110 kt on the shown track, among them Carla 1961, Celia 1970, Allen 1980, Rita 2005, Ike 2008,
  Harvey 2017 and Beryl 2024.

## Checks

| # | Check | Result |
| --- | --- | --- |
| 1 | Smoke test over every source, headless Chrome, local server | No script errors, no console messages. First view (IBTrACS) **100 ms** after scripts load; track filters 5–19 ms; Storm Events 182 ms on first load, 6 ms to filter; CO-OPS 14 ms; GHCNh 43 ms; ERA5 32 ms; hail/gust curves 10 ms; CRC Open 13 ms, river flood 48 ms; tracks over cells 7 ms. |
| 2 | Clicks | Harvey 2017 from the list: panel and chart; a CO-OPS station from the list: 22 levels and chart; a CRC Open cell: curve and table. |
| 3 | Sources tab | 10 rows (7 sources, 3 planned), 63 hazards, 12 other crc-sdk sources. |
| 4 | `just site` | Complete: 16 layers, 18.2 MB of data. |
| 5 | Lint and tests | `ruff` clean; 30 tests pass offline (new: storm records; registry sources). |

## Merges

- `origin/sources-track` into `explorer-v2`: conflicts in `AGENTS.md`, `justfile`, `site/app.js`,
  `site/layers.json`, all "keep both" (Storm Events `points-binary` beside `points`/`lines`; both targets).
- `origin/main` at Phase 3 (d828d41): conflicts in `site/app.js` (kept v2, which already handles per-layer
  horizons and caveats), `site/layers.json` (kept v2 and added `hail_size` and `thunderstorm_gust` under a new
  source `storm_curves`), `tests/test_explorer.py` and `justfile` (`all: data storm-events curves sources site`).

## Not done

- The GeoJSON `lines` kind has no layer now (IBTrACS moved to its own `tracks` kind); the code path is gone
  from the page and can return when a line source needs it.
- CO-OPS, GHCNh and ERA5 were not expanded; they only gained source entries, lists and caveats.
- The source list is tall: on a 900-pixel screen the active source's controls start below seven cards. A
  compact list or a selector is a quick follow-up if it bothers.
- The Phase 3 layer files were copied from the main checkout for the smoke test, not rebuilt here.
- Not deployed; Pages still serves main. The Pages workflow on this branch would also need `just sources`
  (ERA5 takes about 11 minutes uncached).
- E7 was measured against a local server only.
