# Phase 3 report: hail-size and thunderstorm-gust curves from Storm Events, in CRC

Date: 2026-11-10 · crc-sdk 0.11.1 · crc-framework 0.6.0 · NCEI snapshot 2026-11-10 · awaiting review before
Phase 4. Companion: [3-curves-sensitivity.md](3-curves-sensitivity.md) (C2, every number computed by the build).

## What was built

- **C1 annual maxima** (`src/crc_lab/curves/annual_maxima.py`): per Texas r5 cell (2,566) and year 1996–2025
  (the last complete year in the snapshot), the largest reported hail size (mm) and strongest reported
  thunderstorm wind (m/s), from the Phase 2 event table. An event counts in every cell it touches; years without a
  report are zeros. 76,980 cell-years; 72.9% of hail and 81.0% of gust cell-years are zero; the median cell has
  7 non-zero hail years and 4 non-zero gust years.
- **C2 pooling** (`fit.py`): a cell's sample is the union of the annual maxima of itself and its six H3
  neighbours (k=1, "station-year" pooling: 7 × 30 = 210 values, zeros kept). The rule is in the data card.
  The sensitivity note compares no pooling, two rings (19 cells), a 2005 start and a GEV family at ten cities.
- **C3 into CRC**: `HazardDataset.from_table(samples, columns=CDFColumnSchema(samples=...), policy=CDFCurveFitPolicy(...))`
  with family Gumbel, `lower_bound=0` (the zero plateau becomes a hurdle atom), `probability_semantics=
  "annual_value_distribution"`, a `TemporalWindow(1996, 2025)`, horizon 2025, pathway `observed`, and a
  `SourceProvenance` naming NOAA NCEI, the snapshot date and licence. Output: `data/curves/hail_size.parquet` and
  `thunderstorm_gust.parquet` (canonical schema 1.3, diagnostics sidecars). Read back with `HazardDataset.local`,
  evaluated with `for_assets` at ten city centres (table below).
- **C5 explorer**: both appear in the hazard selector like any CRC Open hazard, through two registry entries
  with their own horizon (2025, "observed window end") and caveat text; the per-horizon file writer was
  generalised to take any canonical Parquet (`explorer.hazards.write_horizon_files`).
- **C6 data cards**: `data/curves/*.card.json` (source, window, reduction rule, curve kinds, known biases,
  city values, verification). The explorer's caveat panel says "built from storm reports: an empty cell may be
  unobserved".
- `just curves`, `just curves-sensitivity`; in `just all` and the Pages workflow. 3 new offline tests.

## Checks (the plan's "done" tests)

| # | Check | Result |
| --- | --- | --- |
| 1 | Both datasets load through CRC's reader | **Yes**: `read_hazard_dataset` validates them; hail: 2,531 hurdle (Gumbel), 21 tabulated, 14 point-mass; gust: 2,515 hurdle, 22 tabulated, 29 point-mass. No `no_data` rows; crc-sdk raised no warnings. |
| 2 | `for_assets` returns values | **Yes**, at ten cities (below) and at five random cells per hazard: 80 shipped explorer values equal `for_assets`, 0 mismatches. |
| 3 | Both layers appear beside CRC Open's wind layer in the explorer | **Yes**: hazard switch 9–18 ms, no script errors; horizon selector shows the layer's own window end and returns to 2030/2050/2080 for CRC Open layers. |
| 4 | Sanity check against a published hail climatology | By eye against SPC's "mean number of hail > 1.00 inch days per year, 1986–2015" (`spc.noaa.gov/wcm/climo/newhail.png`): both put the maximum over the Panhandle, Lubbock and north Texas into Oklahoma, decreasing to the coast and far west. City values (1-in-10 hail, mm): Lubbock 69, Dallas 63, Amarillo 61, Fort Worth 56, San Antonio 56, Midland 55, Austin 50, Houston 40, El Paso 31, Corpus Christi 24. Same order as the SPC map's shading. |

City values from `for_assets` (default curves; hail mm, gust m/s):

| City | hail 1 in 2 | 1 in 10 | 1 in 50 | 1 in 100 | gust 1 in 2 | 1 in 10 | 1 in 50 | 1 in 100 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Houston | 16.5 | 39.6 | 55.2 | 61.7 | 24.8 | 31.4 | 35.9 | 37.7 |
| Dallas | 24.2 | 63.4 | 93.6 | 106.2 | 27.4 | 34.2 | 39.5 | 41.8 |
| San Antonio | 18.0 | 56.1 | 83.0 | 94.2 | 0 | 32.6 | 38.6 | 41.1 |
| Austin | 17.3 | 50.1 | 72.7 | 82.1 | 0 | 31.7 | 36.6 | 38.7 |
| Fort Worth | 30.6 | 55.6 | 76.4 | 85.1 | 27.5 | 33.6 | 38.4 | 40.4 |
| El Paso | 0 | 31.4 | 45.7 | 51.4 | 0 | 29.0 | 33.2 | 34.9 |
| Amarillo | 33.4 | 61.2 | 84.1 | 93.8 | 28.1 | 35.5 | 41.1 | 43.4 |
| Lubbock | 34.7 | 68.6 | 96.1 | 107.7 | 27.7 | 35.9 | 42.0 | 44.5 |
| Corpus Christi | 0 | 23.8 | 40.4 | 46.3 | 0 | 31.5 | 36.9 | 39.1 |
| Midland | 17.0 | 54.7 | 77.2 | 86.5 | 0 | 33.2 | 40.6 | 43.7 |

A zero at 1-in-2 means the pooled sample has a report in fewer than half of its cell-years (the hurdle atom).

## What the sensitivity note shows

- Pooling changes 1-in-10 hail at a city by up to about 20 mm either way (Dallas 47 unpooled vs 63 pooled; Austin 62 vs
  50): single cells are noisy, and the ring is the main modelling choice. Two rings move values a further 0–9 mm.
- Starting in 2005 lowers Dallas and Amarillo (by 8 and 6 mm at 1-in-10) and raises El Paso, Austin and Midland:
  reporting density changed over the window.
- GEV and Gumbel agree within 1–2 mm at 1-in-10 and within 4 mm at 1-in-100 at most cities; the Gumbel default is
  kept because the GEV shape is poorly constrained by 210 mostly-zero samples (a probe fit gave shapes up to 1.7).
- Unpooled cells produce more point-mass and tabulated rows; pooled cells almost all fit.

## Decisions and caveats

- **Gumbel, not GEV**, as the default family (above). Both families are in the sensitivity run.
- **Gust uses every Thunderstorm Wind magnitude**: 14,136 estimated gusts, 5,742 measured gusts, 715 sustained
  values since 1996; 2,967 wind reports have no magnitude and do not count. The data card says so.
- **Horizon = 2025, pathway = `observed`**: CRC's canonical schema needs a horizon; the window end is used, and the
  `TemporalWindow` metadata holds 1996–2025. Comparing these with CRC Open's 2030–2080 projections is comparing
  an observed baseline with a scenario; the explorer's caveat panel says which is which.
- Reporting bias is not removed by pooling, only smoothed: cells along the Mexican border and in the Trans-Pecos
  have few reports and low curves that may reflect few observers, not few storms.
- Not done: no comparison with radar-based hail (MRMS) yet, which the plan lists for after this effort; no
  confidence intervals (crc-sdk's L-moment and least-squares fits do not provide them).

## For review

- Is k=1 pooling the right default, or should the shipped layer be the unpooled one with the ring as an option?
- Should the gust curve use estimated gusts only (dropping the few measured and sustained values), or keep all?
- Phase 4 (solar farms, real estate) can start from `for_assets` on these two datasets (requirement C4).
