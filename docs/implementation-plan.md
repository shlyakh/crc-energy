# crc-energy implementation plan

Status: **draft for review** · 2026-11-09 · requirement IDs refer to [requirements.md](requirements.md)

The plan is a sequence of small deliverables, each ending in something public. The order follows dependencies: no
impact function before there is a present-day curve to apply it to, no aggregation before there are per-asset
losses, no validation report before there is a numerical oracle.

## Decisions this plan rests on

| Decision | Choice |
| --- | --- |
| Hazard source, phase 1 | ERA5 and station observations. No CMIP projections for now |
| Python and tooling | 3.12, `uv`, pinned `crc-sdk==0.11.1` and `crc-framework==0.6.0` |
| Rust | Read the core, write Python; propose Rust changes only after a Python version has proved the design |
| Dependence | Resampled ERA5 storm footprints as the primary method; Gaussian and Student-t copulas as brackets |
| Delivery | Static files on GitHub Pages (PMTiles + MapLibre). No hosted app |
| Reuse | CLIMADA for cyclone fields and cascades, physrisk and GODEEEP for generation, MapYourGrid for completeness, CGMES-LinkML and the Open Energy Ontology for vocabulary |
| Skills | Follow crc-docs' pattern (SKILL.md + notebook + pipeline → `summary.json`); add an output schema and evals |

## Deliverables at a glance

| # | Deliverable | Requirements | Effort | State |
| --- | --- | --- | --- | --- |
| D0 | Two animated explainers of CRC's data path | — | done | published in `docs/explainers/` |
| D1 | Present-day heat layer (ERA5 `txx`) in CRC's contract, with station check | H1a, H2, H3, H4, N1, N2 | 1 day | next |
| D2 | Heat-derating impact functions and CRC's independence risk reference | I2, I4, R1, R2, A1, A2 | 1 day | |
| D3 | Static map of substations coloured by D1–D2 results | O1, N3, N7 | half a day | |
| D4 | ERA5 gust layer and wind fragility | H1b, I1 | 2 days | |
| D5 | Storm footprints, dependence layer, network roll-up | H5, A3, R3–R7 | 3–5 days | |
| D6 | Conformance tests for the CRC functions used | V1, N8 | 2 days, alongside D4–D5 | |
| D7 | Asset schema with crosswalks; energy skills; benchmarks; validation report | A3–A6, O2, V2–V4 | later | |

Heat comes first because it is the only present-day hazard CRC's ERA5 provider supports today (`txx`). Wind needs a
new recipe, so it is D4, not D1.

## D1 — Present-day heat layer (one day)

Goal: per-cell annual-maximum temperature curves for one US state, written as a CRC canonical dataset that CRC's own
reader and asset evaluation accept, plus a comparison with station records.

1. **Set up (1 h).** `uv sync --all-extras --group dev`; `uv run pytest` (pin test passes).
2. **Fetch and reduce (2 h).** `HazardDataset.era5("txx", store="arco-0p25").for_area(bounds).years(1991, 2020)
   .cache(...)`, then `.canonicalize(policy=BlockExtremaPolicy.curated(h3_resolution=5, minimum_years=...))` and
   `.annual_extremes()`. Start with a small bounding box to learn the timings; crc-docs reports about 15 s per year
   per hazard on the coarse store. If r5 from a 0.25° grid (about 28 km) only repeats grid values across neighbouring
   cells, record that and consider r4.
3. **Fit (1 h).** `fit_distribution(sample, "genextreme", method="lmoments")` per cell; keep fit diagnostics; flag
   cells with too few years.
4. **Write the dataset (2 h).** `write_hazard_dataset` with full metadata: hazard name, unit (°C),
   `probability_semantics=annual_value_distribution`, return-period convention, `temporal_window`, source and code
   version. Read it back with `read_hazard_dataset`; evaluate ten test points with `for_assets`.
5. **Station check (1.5 h).** Twenty to fifty GHCNh / ISD stations in the state: annual maxima against the curve of
   the cell they sit in. Plot PIT histogram and count exceedances of the cell's 1-in-10 level. Expect stations to
   run hotter than a cell average; report the offset, do not hide it.
6. **Publish (0.5 h).** Notebook, `data/README.md` dataset card with the Copernicus attribution, short write-up.

Done when: CRC's reader loads the file unchanged; `for_assets` returns values; the station plot is in the repo.

Risks: download time on the 0.25° store (shrink the box); unknown arguments of `write_hazard_dataset` (read
`crc_sdk/connectors` first; budget an hour).

## D2 — Derating functions and the independence reference (one day)

1. **Assets.** Substations for the same state from the archived HIFLD file; a few hundred points; build an
   `AssetPortfolio`.
2. **Impact definitions.** Transformer loading-capacity loss and conductor ampacity loss as functions of ambient
   temperature, written with `PiecewiseLinearImpact` or `SigmoidImpact` and registered in an `ImpactRegistry`.
   Coefficients are parameters in one YAML file, each with its source. They are screening values from public
   secondary sources, not the IEEE standards themselves.
3. **Evaluate.** Expected capacity loss per asset from the D1 curves.
4. **Run CRC's risk core.** `generate_microscores` → `compute_risk(levels=[0.95, 0.99])` on a small set of assets.
   This is the first public use of that function; write down exactly what its inputs and outputs mean, and where
   independence enters.
5. **Record the limit.** Branch count grows as 2^n; note the largest n that runs.

Done when: per-asset expected derating and a VaR/CVaR table exist, with a paragraph on what the independence
assumption does to them.

## D3 — Static screening map (half a day)

1. Join D1 quantiles and D2 results to substations; write GeoJSON.
2. Build `assets.pmtiles` and `cells.pmtiles` with `crc_sdk.geometry.pmtiles`.
3. One `index.html`: MapLibre, pmtiles.js, attribute selector, legend, click popup.
4. Caveat panel on the page: ERA5 1991–2020; cell size; "regional screening, not asset-level risk"; versions.
5. Serve from GitHub Pages. If OSM geometry is used, publish the tiles under ODbL and do not publish a merged table.

## D4 — Gust layer and wind fragility (two days)

1. **Gust recipe.** Read `crc_sdk/providers/era5.py` (`ERA5Recipe`, `ERA5Store`). Add a 10 m gust variable and an
   annual-maximum recipe; if the stores lack the variable, read ARCO-ERA5 or Earthmover's Icechunk copy with xarray
   and feed `write_annual_extremes`. Open an issue or PR upstream.
2. **Fit and write** as in D1. Declare the averaging period: ERA5 gust is a 3-second-equivalent gust at 10 m.
3. **Station check for wind.** This is where ERA5's underestimation of extremes will show; quantify it.
4. **Fragility.** Line, tower and substation wind curves (I1) as impact definitions; each states the intensity
   measure it expects. Verify each parameter against its original paper before use.
5. **Region.** Choose a region without tropical cyclones first. Cyclone regions need CLIMADA wind fields (H6).

## D5 — Footprints, dependence and roll-up (three to five days)

1. **Network.** One operator's lines and towers from OSM; `tower → span → line → network` with `parent_id`; map
   assets to unique cells (dependence is modelled on cells, not assets).
2. **Event set.** Per-cell 98th-percentile gust; flag hours when many cells exceed it; decluster into 72-hour events;
   footprint = per-cell maximum in the window. Estimate λ and test for clustering.
3. **Map onto CRC curves.** Rank-transform footprints per cell; convert with G(x) = 1 + ln F(x)/λ using CRC quantile
   functions. Check: simulated annual maxima reproduce each cell's curve.
4. **Simulate.** 10⁵ years in chunks; Poisson or negative-binomial counts; resample footprints; apply fragilities.
5. **Brackets.** Same portfolio with a Gaussian and a Student-t copula on annual-maximum ranks, and with CRC's
   independent `compute_risk` where n allows.
6. **Diagnostics first.** χ and χ̄ against distance for the data and each model. Decide nothing before these exist.
7. **Outputs.** AEP and OEP curves, VaR/CVaR and PML at 1-in-100/200/250 by line and network; intervals from
   bootstrapping historical seasons.

Known limits to state in the result: about 45 seasons of reliable data (1979 onward); no storm larger than the
largest observed; every tower in a cell shares one hazard value.

## D6 — Conformance tests (alongside D4–D5)

- Hypothesis properties for the functions actually used: quantile monotone; CDF and quantile inverse; VaR ≤ CVaR;
  `compute_risk` with one factor equals that factor's quantile.
- References: L-moment GEV fits against `lmoments3` and scipy; expectations against `scipy.integrate.quad`.
- A CI job that reruns them when a new CRC release appears; results logged in `CHANGELOG-upstream.md`.

## Learning track

| When | Read | Why |
| --- | --- | --- |
| Before D1 | `docs/explainers/anatomy.html`; crc-docs `AGENTS.md`; `crc_sdk/providers/era5.py`; `crc_sdk/connectors` writers | D1 uses exactly this path |
| Before D2 | `crc_sdk/impacts/`; `crc_framework/metrics/{microscores,spanning,risk}.py`; `docs/impact-contracts.md` in crc-framework-rs | D2 is the first use of impacts and risk |
| During D4–D6 | Rust Book ch. 1–10, 13; then `crates/core/src/metrics.rs` (197 lines), `risk.rs` (487), `distribution/lmoments.rs` | The oracle in D6 must reproduce these |
| Later | PyO3 guide; `impact/` modules | Before any upstream PR to the core |

## Later work (not scheduled)

Asset schema and SSSOM crosswalk (A3–A4); cyclone regions via CLIMADA (H6); hail from MRMS (H8); ice accretion;
CRC Open as a labelled stress case (H7); one-to-three-year forecast-conditioned heat, after a hindcast skill test;
energy question-skills with evals (O2); physrisk and CLIMADA benchmarks (V3); SR 26-2-structured validation report
(V4), starting as a one-page model card.

## Rules for every deliverable

Pin and record versions. Declare probability semantics and intensity measures. Label cell-level results as regional
screening. Keep damage, derating and liability apart. Publish what was not verified.
