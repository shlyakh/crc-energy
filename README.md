# crc-energy

Present-day physical climate risk for energy infrastructure — transmission lines and towers, substations, later
generation — built on [Climate Risk Commons](https://climateriskcommons.org/) (CRC): an ERA5-based hazard layer in
CRC's canonical contract, T&D impact functions in CRC's impact-contract form, a dependence-aware aggregation layer
(event footprints, with copula brackets) giving AEP/OEP/VaR/CVaR/PML, and an independent validation harness.

Status: D0 done (explainers below). The current plan is in `docs/plan.md` once merged; earlier requirements are in `docs/archive/`.

## Explainers (D0)

Two self-contained animated pages; open them in a browser or from GitHub Pages:

- `docs/explainers/anatomy.html` — **Anatomy of one CRC question**: `which_sites_are_most_at_risk.py` traced call by
  call through its three routes, with object and data shape at each step. Closing finding: no public crc-docs example
  calls `compute_risk`.
- `docs/explainers/primer.html` — **Climate risk curves, animated**: the five ideas of crc-docs' curves primer, with
  the sampling and L-moment GEV fitting running live in the page.

## What is used from CRC, what is outside, what extends it

| Zone | Contents |
| --- | --- |
| USE (CRC as shipped) | `HazardDataset` plans and canonicalization, `fit_distribution` → quantiles, `AssetPortfolio` evaluation, impact contracts, `compute_risk` (as the independence reference), `geometry.pmtiles` |
| OUTSIDE | ERA5, NOAA ISD/GHCNh, MRMS, HIFLD (archived), OSM `power=*`, fragility literature (PNNL-33587, Zenodo wind-fragility DB, Hazus, EPRI READi), scipy/pyvinecopulib/networkx, MapLibre/PMTiles hosting |
| EXTEND | ERA5 present-day hazard layer in the canonical contract; energy impact definitions; hierarchical asset schema (LinkML + SSSOM crosswalk to CIM/OEO/OSM/OED/Hazus/physrisk); dependence layer; conformance tests; skill additions |

## Setup

```sh
uv sync --all-extras --group dev
uv run pytest -q
```

Pinned: `crc-sdk==0.11.1`, `crc-framework==0.6.0` (see `CHANGELOG-upstream.md`).

## Licence

AGPL-3.0-or-later (inherits from `crc-framework` / `crc-sdk`). CRC Open data, when used, is CC BY-NC 4.0 and
is excluded from any commercial output. OSM-derived geometry is ODbL.
