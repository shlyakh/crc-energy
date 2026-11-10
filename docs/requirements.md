# crc-energy requirements

Status: **draft for review** · 2026-11-09 · pinned to `crc-sdk==0.11.1`, `crc-framework==0.6.0`

This document answers one question for every component of the system: is it Climate Risk Commons (CRC) as shipped,
something outside CRC, or an extension of CRC? Steps and schedule are in
[implementation-plan.md](implementation-plan.md).

## 1. Scope

`crc-energy` estimates **present-day** physical climate risk for energy-infrastructure assets, starting with
transmission lines and towers and with substations.

In scope for the first phase:

- hazard curves from reanalysis and observations (ERA5, NOAA stations), written in CRC's canonical hazard contract;
- impact (fragility and derating) functions for transmission and distribution (T&D) assets, in CRC's impact form;
- a hierarchical asset model (tower → span → line → network) that flattens to CRC's asset portfolio;
- portfolio aggregation with spatial dependence, giving AEP, OEP, VaR, CVaR and PML;
- a validation harness for the CRC functions the system relies on.

Out of scope for the first phase:

- CMIP-based projections. CRC Open (CMIP6, SSP5-8.5 only, no historical baseline) comes back later as a labelled
  stress case (H7).
- Network topology and cascade modelling (CLIMADA petals already does this [R15]).
- Generation-asset vulnerability (OS-Climate physrisk [R16] and PNNL GODEEEP [R17] cover it).
- Non-weather outage causes. For scale: about one in five major US outage events in 2000–2023 was not
  weather-related [R20]; they are excluded and results must never be presented as total outage risk.

## 2. Classification rule

| Tag | Meaning | Test |
| --- | --- | --- |
| **USE** | A `crc-sdk` / `crc-framework` API, contract or dataset called without modification | If CRC disappeared, this would have to be rewritten |
| **OUTSIDE** | External data, libraries, hosting or domain knowledge; not meant to become CRC | CRC neither provides it nor should; it joins CRC through a USE interface |
| **EXTEND** | New data in a CRC contract, a new definition in a CRC mechanism, or new functionality on CRC types | Could be proposed upstream, or needs CRC's types to exist |
| **GAP** | Needed, absent from CRC's open release, and the design is still open | Listed in section 9 |

## 3. The CRC surface available

Verified by reading the installed wheels, a clone of `crc-framework-rs` [R3] and all 20 pipelines in crc-docs [R1].

| Layer | API | What it gives | Used by crc-docs examples |
| --- | --- | --- | --- |
| Data plans | `crc_sdk.workflows.HazardDataset.era5(recipe, store=)`, `.crc_open()`, `IBTrACSPlan`, NOAA / USGS / ECCC plans; `crc_sdk.providers.*` | Lazy fetch plans: `.for_area()`, `.years()` / `.horizons()`, `.cache()` | Nearly all |
| Canonicalization | `BlockExtremaPolicy`, `.canonicalize()`, `.annual_extremes()`; `read_hazard_dataset`, `write_hazard_dataset`, `write_annual_extremes` | Raw grids → annual extremes on H3 cells → canonical rows keyed (hazard_name, horizon, pathway, cell_index, source_id) | ERA5 route; 3 pipelines |
| Fitting | `crc_sdk.fitting.fit_distribution(sample, "genextreme", method="lmoments")`, `Distribution.quantiles(q)`, `curve_parameters_from_row(row).to_distribution()` | L-moment fits; curve evaluation with non-exceedance q = 1 − 1/T | 1 pipeline + primer |
| Asset evaluation | `plan.for_assets(table).return_periods([...]).write_parquet()`, `AssetPortfolio` | Points or H3 cells → curve values; asset schema is `asset_id` + location + passthrough columns | CRC Open route |
| Geometry | `crc_sdk.geometry.{h3, admin, coverage, vector, pmtiles}` | H3 indexing, PMTiles builds (tippecanoe) | 2 pipelines |
| Impacts | `crc_sdk.impacts`: `ImpactRegistry`, `PiecewiseLinearImpact`, `SigmoidImpact`, `LinearImpact`, `CallableImpact`, `ImpactExpression`, calibration checks; framework impact schema v1.0.0 with content hashes [R4] | Response functions as versioned definitions; expectation E[f(X)] | 1 pipeline |
| Risk core | `crc_framework.generate_microscores`, `compute_spanning_set`, `compute_risk` | VaR/CVaR over a product of **independent** binary outcomes, with per-factor attribution | **None** |
| Question pattern | `SKILL.md` + notebook + pipeline → `summary.json` | Agent-facing packaging | All 5 questions |

Three facts from this inventory shape the requirements:

1. **The ERA5 provider has four recipes only**: `txx`, `tnn`, `rx1day`, `rx5day`, on two stores (`arco-0p25`,
   `wb2-1p5`) that expose 2 m temperature and precipitation. **There is no wind or gust recipe.** Heat is USE; wind
   from ERA5 is an extension (H1b).
2. **The risk core assumes independence** and is not exercised by any public example. CRC's site lists a "patented
   multi-hazard correlation engine" as proprietary [R2]. Dependence is therefore an extension by design.
3. **CRC is alpha and moves fast**: `crc-framework` went 0.3.0 → 0.6.0 between 7 Oct and 4 Nov 2026, and 0.6.0
   changed empirical-law interpolation [R5]. Hence N1 and N8.

## 4. Requirements

Priority: P1 = first phase, P2 = second, P3 = roadmap.

### 4.1 Hazard data

| ID | Requirement | Tag | Depends on | P |
| --- | --- | --- | --- | --- |
| H1a | Annual-maximum daily-maximum 2 m temperature (`txx`) per H3 r5 cell for one region, 1991–2020, from ERA5 0.25° | USE | `HazardDataset.era5("txx", store="arco-0p25")`, `BlockExtremaPolicy`, `annual_extremes()` | P1 |
| H1b | Annual-maximum 10 m wind gust per cell from ERA5 | EXTEND | A new ERA5 recipe and store variable (candidate PR to crc-sdk), or xarray on ARCO-ERA5 / Earthmover's Icechunk ERA5 [R24] feeding `write_annual_extremes` | P1 |
| H2 | Fit a GEV per cell by L-moments | USE | `fit_distribution` | P1 |
| H3 | Publish fitted curves as canonical Parquet with `probability_semantics=annual_value_distribution`, `source_return_period_convention`, `temporal_window`, provenance | EXTEND (data in contract) | `write_hazard_dataset`; hazard schema 1.3 [R6] | P1 |
| H4 | Compare cell curves with NOAA ISD / GHCNh station annual maxima (PIT histogram, exceedance counts) | USE | `crc_sdk.providers.{isd, ghcnh}`, `fit_distribution` | P1 |
| H5 | Storm event set: 72-hour storm-maximum gust per cell, declustered, with annual frequency λ | EXTEND + GAP | Built on H1b data; CRC has no event-set contract (section 9) | P2 |
| H6 | Tropical-cyclone wind fields for Gulf and Atlantic assets | OUTSIDE | CLIMADA `TropCyclone` from IBTrACS; ERA5 under-resolves cyclone cores [R13] | P2 |
| H7 | CRC Open SSP5-8.5 curves as a stress case, labelled by approximate global-warming level | USE | `HazardDataset.crc_open()`; CC BY-NC 4.0; CPUC D.24-08-005 uses warming levels with SSP3-7.0 as reference [R21] | P3 |
| H8 | Hail annual maxima per cell from MRMS MESH, hurdle fit | EXTEND (data) | AWS Open Data MRMS; `hurdle_distribution` | P3 |

### 4.2 Assets and taxonomy

| ID | Requirement | Tag | Depends on | P |
| --- | --- | --- | --- | --- |
| A1 | Load substations and transmission lines with towers for one state or operator | OUTSIDE | Archived HIFLD (public domain, 2025-02-19 snapshot; HIFLD Open was deactivated 2025-08-26) [R18]; OSM `power=*` (ODbL) | P1 |
| A2 | Represent assets as a flat portfolio for curve evaluation | USE | `AssetPortfolio` | P1 |
| A3 | Hierarchical model: tower → span → line → network via `parent_id`; `asset_class`, `vulnerability_class`, `replacement_value`, loss channel | EXTEND (contract proposal) | LinkML schema emitting Pydantic and JSON Schema; flattens losslessly to A2 | P2 |
| A4 | Class vocabulary by import, not invention; crosswalk published as an SSSOM file | OUTSIDE → EXTEND | CGMES-as-LinkML (Netbeheer Nederland, Apache-2.0) [R22], Open Energy Ontology [R23], OSM tags, Hazus lifeline classes, OED occupancy, physrisk classes | P2 |
| A5 | Completeness check of asset coverage | OUTSIDE | MapYourGrid indicators and transmission length index [R19] | P2 |
| A6 | OED v4 export, validated by running through Oasis PiWind | OUTSIDE | ODS_Tools, oasislmf | P3 |

### 4.3 Impact functions

| ID | Requirement | Tag | Depends on | P |
| --- | --- | --- | --- | --- |
| I1 | Wind fragility: line/span piecewise-linear (0.01 below 30 m/s, 1 at 60 m/s); HV substation lognormal (θ = 30 m/s, β = 0.25, slight damage); tower collapse 29–37 m/s. Each declares averaging period and gust factor | EXTEND (definitions) | `PiecewiseLinearImpact`, `SigmoidImpact` or `CallableImpact` in an `ImpactRegistry`; parameters from [R9][R10][R11] | P1 |
| I2 | Heat derating for transformers and overhead conductors, as a derating channel | EXTEND (definitions) | Expectation E[f(X)] on a monotone response; coefficients from public secondary sources because IEEE C57.91 / 738 are paywalled | P1 |
| I3 | Substation flood depth–damage (Hazus classes; non-functional near 4 ft above grade) | EXTEND (definitions) | Needs a flood hazard layer first | P3 |
| I4 | Evaluate impacts against per-cell hazard distributions | USE | `ImpactExpression`, framework expectation / pushforward | P1 |

### 4.4 Aggregation and metrics

| ID | Requirement | Tag | Depends on | P |
| --- | --- | --- | --- | --- |
| R1 | Reference VaR/CVaR under CRC's independence assumption | USE | `generate_microscores` → `compute_risk` | P1 |
| R2 | Per-asset loss distributions | USE + EXTEND | CRC quantile functions; sampling in Python | P1 |
| R3 | Dependence, primary method: resampled ERA5 storm footprints mapped onto CRC marginals through G(x) = 1 + ln F(x)/λ, with Poisson or negative-binomial annual counts | EXTEND (functionality) | H5; numpy / xarray | P2 |
| R4 | Dependence, brackets: Gaussian copula (no tail dependence) and Student-t copula (tail dependence everywhere) on annual-maximum ranks, with distance-decay correlation | EXTEND (functionality) | scipy `multivariate_t`; pyvinecopulib for checks | P2 |
| R5 | Publish χ and χ̄ against distance before choosing any parametric model | EXTEND | European gust footprints show asymptotic independence at range [R12]; always-dependent models overstate joint extremes [R14] | P2 |
| R6 | Roll-up along A3 (a line fails if any tower or span fails) with attribution by line | EXTEND | networkx | P2 |
| R7 | AEP, OEP, VaR/CVaR and PML at 1-in-100, 200 and 250, with confidence intervals from bootstrapping historical seasons | EXTEND | OEP only from event-based models, never from annual-maximum copulas | P2 |
| R8 | Correlated spanning set in the Rust core | EXTEND (upstream) | Only if R3–R7 prove the design and Python is too slow | P3 |

### 4.5 Outputs

| ID | Requirement | Tag | Depends on | P |
| --- | --- | --- | --- | --- |
| O1 | Static map of assets coloured by hazard quantile: PMTiles + MapLibre on GitHub Pages | USE + OUTSIDE | `crc_sdk.geometry.pmtiles`; no server | P1 |
| O2 | Two energy question-skills in crc-docs form, plus a JSON Schema for `summary.json` and an eval set | USE + EXTEND | crc-docs pattern | P2 |
| O3 | Client-side curve evaluation | USE | `@climateriskcommons/crc-framework` (WASM, alpha) | P3 |

### 4.6 Validation

| ID | Requirement | Tag | Depends on | P |
| --- | --- | --- | --- | --- |
| V1 | Numerical oracle: property tests (quantile monotone, CDF∘quantile ≈ identity, VaR ≤ CVaR) and reference checks against scipy and lmoments3 | EXTEND (tests) | Hypothesis; CRC's own conformance suite is "in development" [R2] | P1 |
| V2 | Station comparison (H4) as a repeatable job | USE | providers + fitting | P2 |
| V3 | Same assets through physrisk and CLIMADA | OUTSIDE | benchmarking | P3 |
| V4 | Validation report following SR 26-2: intended use and materiality, conceptual soundness, outcomes analysis, ongoing monitoring | OUTSIDE (method) | SR 26-2 replaced SR 11-7 on 2026-04-17 [R7]; start as a short model card | P3 |

## 5. Extensions as contributions

| Extension | Kind | Lands | Accepted when |
| --- | --- | --- | --- |
| ERA5 gust recipe (H1b) | provider addition | PR to crc-sdk | `HazardDataset.era5("<gust>")` returns annual extremes with correct units and averaging period documented |
| ERA5 present-day layer (H3) | data in contract | Release here; proposal for dataset onboarding | `read_hazard_dataset` loads it; `for_assets` evaluates it; station comparison published |
| T&D impact definitions (I1, I2) | definitions | A `crc-energy` impact pack, or PR to the impact registry | Stable content hashes; unit tests reproduce published parameters |
| Hierarchical asset schema (A3, A4) | contract proposal | JSON Schema in CRC's style | Two real networks represented; flattens to `AssetPortfolio` |
| Dependence layer (R3–R7) | functionality | `crc_energy.aggregate` | Reproduces `compute_risk` under independence; simulated annual maxima reproduce each cell's curve |
| Conformance tests (V1) | tests | PR to crc-framework-rs | Green on 0.6.0 |

## 6. Outside dependencies and licences

| Dependency | Role | Licence |
| --- | --- | --- |
| ERA5 (ARCO-ERA5; Earthmover Icechunk copy) | hazard source | Copernicus licence, attribution |
| NOAA ISD, GHCNh | observations | US public domain |
| Archived HIFLD | asset locations | public domain |
| OpenStreetMap `power=*` | asset geometry with towers | ODbL: publish code and OSM-derived tiles; do not redistribute merged OSM + hazard tables |
| PNNL-33587, wind-fragility database, EPRI READi, Hazus | curve parameters | public; check each record |
| scipy, pyvinecopulib, networkx, xarray | maths | BSD / MIT |
| tippecanoe, MapLibre, pmtiles.js, GitHub Pages | delivery | open |
| CLIMADA, physrisk, Oasis PiWind | cyclone fields, benchmarks, export check | GPL-3.0 / Apache-2.0 / BSD |

`crc-sdk` and `crc-framework` are AGPL-3.0-or-later: anything that imports them and is distributed or served must
publish its source. CRC Open data is CC BY-NC 4.0 and stays out of commercial output.

## 7. Non-functional requirements

| ID | Requirement |
| --- | --- |
| N1 | Pin both CRC packages; record versions and impact-registry revision in every output (`tests/test_pins.py`) |
| N2 | Every hazard dataset declares probability semantics, return-period convention, temporal window and provenance; every wind impact declares averaging period and gust factor |
| N3 | Results on r5 cells (average 252.9 km²) are labelled regional screening, not asset-level risk [R25] |
| N4 | Damage, derating and liability are separate fields and are never summed unlabelled |
| N5 | Licence boundaries of section 6 are enforced in what is published |
| N6 | One `uv` lock, seeded simulations, atomic writes, notebooks runnable in CI |
| N7 | Public outputs are static files only |
| N8 | `CHANGELOG-upstream.md` plus a CI run of V1 on each new CRC release |

## 8. Hazard priority by asset class (basis for scope)

| Asset class | 1st | 2nd | 3rd | Evidence |
| --- | --- | --- | --- | --- |
| Transmission lines and towers | Wind (cyclone tail; convective frequency) | Ice with wind | Wildfire (liability, shutoffs) | Weather caused 80% of major US outages 2000–2023; of those, severe weather 58%, winter 23%, tropical cyclones 14% [R20] |
| Distribution lines and poles | Convective wind with tree fall | Winter storms | Cyclone wind | [R20] |
| Substations, coastal | Storm surge and coastal flood | River and rain flood | Cyclone wind | Sandy, Harvey event reports |
| Substations, interior | Convective wind, lightning | Ice | River flood; heat on transformers | — |
| Thermal generation, gas supply | Extreme cold | Heat and cooling water | Flood | 61.8 GW lost in Uri, 90.5 GW in Elliott [R26] |
| Utility PV | Hail | Wind | Wildfire smoke, flood | Hail is 73% of insured PV losses by value [R27] |

First-phase scope follows the first three rows. The full 19-row table is in the plan document.

## 9. Open questions

1. **Event-set contract (GAP).** Store footprints with a small schema here, or propose an event-set contract upstream?
2. **Gust recipe.** PR to crc-sdk first, or build outside and upstream later?
3. **Impact packaging.** Separate pack referenced by digest, or PR into the registry? `docs/impact-contracts.md` in
   crc-framework-rs has not yet been read field by field.
4. **Region for D1.** Florida and the Gulf Coast need cyclone fields (H6) for wind; an interior region does not.
5. **Contribution channel.** crc-framework-rs has no CONTRIBUTING file; ask on CRC's Discord after D1 is public.

## 10. Not yet verified

- Fragility parameters in I1 are quoted from secondary compilations; check each against its original paper.
- Hazus depth–damage values and the 4 ft threshold are cited second-hand.
- ERA5 gust behaviour: extremes are underestimated and short-range dependence is smoothed [R13]; the effect on H1b and
  R3 is unmeasured until H4 is run for wind.
- SR 26-2 companion issuances (OCC, FDIC numbers) come from secondary sources only.

## References

- [R1] crc-docs — https://github.com/RiskThinking/crc-docs
- [R2] Climate Risk Commons — https://climateriskcommons.org/
- [R3] crc-framework-rs — https://github.com/RiskThinking/crc-framework-rs
- [R4] crc-framework v0.5.0 (impact schema v1.0.0) — https://github.com/RiskThinking/crc-framework-rs/releases/tag/v0.5.0
- [R5] crc-framework v0.6.0 — https://github.com/RiskThinking/crc-framework-rs/releases/tag/v0.6.0
- [R6] crc-sdk — https://github.com/RiskThinking/crc-sdk · https://pypi.org/project/crc-sdk/0.11.1/
- [R7] Federal Reserve SR 26-2 — https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm
- [R9] PNNL-33587, Fragility Functions Resource Report — https://www.pnnl.gov/main/publications/external/technical_reports/PNNL-33587.pdf
- [R10] Wind fragility database for electrical power infrastructure — https://zenodo.org/records/23399966
- [R11] Multi-hazard assessment of the US HV network — https://arxiv.org/pdf/2605.23053
- [R12] Dawkins & Stephenson 2018, NHESS 18:2933 — https://nhess.copernicus.org/articles/18/2933/2018/
- [R13] ERA5 extreme-wind evaluation (French coast), ASR 22:69 — https://asr.copernicus.org/articles/22/69/2025/asr-22-69-2025.html
- [R14] Huser, Opitz & Wadsworth 2024 — https://arxiv.org/html/2401.17430
- [R15] CLIMADA interdependent infrastructure model — https://www.sciencedirect.com/science/article/pii/S0951832023001096
- [R16] OS-Climate physrisk — https://physrisk.readthedocs.io/en/latest/api/physrisk.html
- [R17] PNNL GODEEEP — https://godeeep.pnnl.gov/resources/
- [R18] Archived HIFLD substations (DataLumos) — https://www.datalumos.org/datalumos/project/240591/version/V1/view
- [R19] MapYourGrid — https://github.com/open-energy-transition/MapYourGrid
- [R20] Climate Central, weather-related outages 2000–2023 — https://www.climatecentral.org/climate-matters/weather-related-power-outages-rising
- [R21] CPUC Decision 24-08-005 — https://docs.cpuc.ca.gov/PublishedDocs/Published/G000/M537/K988/537988980.docx
- [R22] CGMES as LinkML — https://linkml.io/linkml-registry/details/Netbeheer-Nederland_cgmes/
- [R23] Open Energy Ontology — https://openenergyplatform.org/ontology/oeo/
- [R24] Earthmover ERA5 on Icechunk — https://www.earthmover.io/blog/low-latency-era5-icechunk-marketplace
- [R25] GARP physical-risk vendor benchmarking study (summary) — https://climateandtech.com/en/resources/industry-reports/garp-physical-risk-vendor-benchmarking-study
- [R26] FERC–NERC reports on Winter Storms Uri and Elliott — https://www.ferc.gov/news-events/news/final-report-february-2021-freeze-underscores-winterization-recommendations · https://ferc.gov/sites/default/files/2023-09/Presentation%20-%20Elliott_F-R_Open_Mtg_(9-21-23).pdf
- [R27] kWh Analytics Solar Risk Assessment 2025 (summary) — https://taiyangnews.info/reports/kwh-analytics-7th-solar-risk-assessment
