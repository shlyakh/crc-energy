# Explainers (D0): two animated pages on how CRC works

Two self-contained HTML pages, built as the first learning deliverable. Each is one file (inline SVG, CSS and
JavaScript, no external libraries, no build step) with play/pause, step buttons and arrow-key control.

They were planned as Claude "Motion" artifacts. That artifact type was not available on the account used, so they
were hand-built as animated pages with the same effect and published as ordinary artifacts; the source lives here.

| Page | File | What it animates | Built from |
| --- | --- | --- | --- |
| Anatomy of one CRC question | [`anatomy.html`](anatomy.html) | 14 steps following crc-docs' `pipelines/which_sites_are_most_at_risk.py` through its three routes (A: ERA5, B: CRC Open, C: CDT) to `summary.json`. Each step shows the exact call, the object returned, the data shape and the package it lives in, over five layers: input → provider → contract → curve → answer | The pipeline source (346 lines) read call by call; the crc-sdk 0.11.1 wheel; a clone of `crc-framework-rs` |
| Climate risk curves, animated | [`primer.html`](primer.html) | The five ideas of crc-docs' `notebooks/climate_risk_curves_primer.ipynb`: a curve as a die for one year; two 30-year records disagreeing at the rare end; 200 L-moment GEV fits scattering around the true 1-in-100; the chance of a rare day over a 30-year span; one recipe for 60+ hazards | The notebook's markdown and code cells |

## How they were made

1. Cloned `RiskThinking/crc-docs` and `RiskThinking/crc-framework-rs`; unpacked the `crc-sdk` and `crc-framework`
   wheels to read the real module layout.
2. Traced the pipeline: `read_sites` → `era5_answer`, `crc_open_answer`, `cdt_answer` → `write_atomic`. For each step
   recorded the API (`HazardDataset.era5` / `.crc_open`, `BlockExtremaPolicy`, `annual_extremes`, `fit_distribution`,
   `quantiles`, `for_assets`, `return_periods`, `velo_sdk.APIClient`) and the shape of what it returns.
3. Searched every pipeline and notebook in crc-docs for `compute_risk`, `generate_microscores` and `crc_framework`
   imports. None were found; that is the closing step of `anatomy.html`.
4. Reimplemented the primer's maths in the page (GEV quantile, Hosking L-moment fit, seeded sampling), so scenes 2–3
   are computed live and the re-roll button draws a new record.
5. Checked both pages in headless Chrome: no script errors; screenshots inspected.

## What is real and what is illustrative

- `anatomy.html`: calls, parameter names and data shapes are taken from the source. Code blocks are shortened, not
  executed. The partition count quoted for `tx_max` (83) comes from the saved output of crc-docs'
  `notebooks/sources/crc_open_hazards.ipynb`.
- `primer.html`: the curve is **synthetic** (GEV, location 40 mm, scale 12 mm, shape −0.08 in Hosking's convention),
  chosen to resemble a mid-latitude wettest-day curve. It is not a CRC Open curve. The six-hazard table in scene 5
  holds **illustrative values**, labelled as such on the page.

## What they established

- crc-docs' public examples use CRC as a data-access, canonicalization and curve-fitting toolkit. The risk core
  (`generate_microscores`, `compute_spanning_set`, `compute_risk`) ships in `crc-framework` but no public pipeline or
  notebook calls it.
- A no-CMIP route already exists in CRC's own code (route A: ERA5 → annual extremes → L-moment GEV → quantile).
- The three ways this project uses CRC map onto that trace: consume (routes A/B as they are), produce (new data in
  the canonical contract), extend (impact definitions, the risk core, a dependence layer).

## Reuse

- The step engine is generic: a new explainer is a new `steps[]` (or `scenes[]`) array plus an SVG.
- Planned third page: the impact path (definition → registry → evaluation → expectation), once D2 exists.
- `anatomy.html` is a candidate contribution to crc-docs, which has no architecture explainer.
