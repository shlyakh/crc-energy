# Candidate nuggets (kept for later)

Status: research output, 2026-11-10. Not yet a plan. Each candidate is one plain question, ends in an impact number,
has a present-day result from observations or reanalysis, uses public data, and fits in 80 hours. CRC Open
(SSP5-8.5) may appear only as a labelled stress panel. Details that were not checked against a primary source are
marked.

## Ranked list

| Rank | Question | Ground truth | New piece (could go upstream) | Hours |
| --- | --- | --- | --- | --- |
| 1 | How cold does it have to get before Texas power plants start failing? | Strong: ERCOT unit-level outage file for Winter Storm Uri; Elliott and Heather as out-of-sample checks | Calibrated cold-weather generator fragility as a CRC impact definition | ~70 |
| 2 | How rare was the cold behind ERCOT's winter peak record, and what would a 1-in-50 cold morning add? | Strong: ERCOT hourly load by weather zone | Demand-side impact (load uplift against temperature) | ~50 |
| 3 | How much line capacity does a 1-in-10 hottest day take away against the seasonal rating? | Weak: utility ratings are not public | Linear assets (a line as a set of H3 cells) | ~50 |
| 4 | How much gas-fired capacity does Texas lose on a 1-in-10 hottest afternoon? | Moderate to strong: EPA CAMPD hourly unit output | Gas-turbine ambient-derate impact | ~55 |
| 5 | How often does panel-breaking hail hit Texas solar farms? | Moderate: Fighting Jays, March 2024 | Hail provider (CRC Open has no hail) | ~75 |
| 6 | What does a 1-in-10 dry year cost in Columbia / BC hydropower? | Strong (US), moderate (BC): EIA-923 generation | Low-flow / annual-volume recipe | ~60 |
| 7 | How cold before Alberta load peaks and wind drops out? | Strong for load, moderate for wind: AESO hourly load | Wind-turbine cold cut-out impact | ~60 |
| 8 | How much freezing rain blacks out a million customers? | Moderate: Hydro-Québec April 2023; EAGLE-I county outages | Freezing-rain recipe from present-weather codes | ~80 |
| 9 | How often does heat cut US nuclear output? | Moderate: NRC daily reactor status | NRC status provider | ~65 |
| 10 | In a 1-in-10 bad year, how many customers in my county lose power at once? | Strong: EAGLE-I is the outcome | Historical consequence baseline | ~40 |
| 11 | How much rain floods a substation here? | Weak | none | ~45 |

Why cold and heat rank first: CRC's ERA5 provider has only `txx`, `tnn`, `rx1day` and `rx5day`. Wind questions need a
new gust recipe first.

## Top candidate in brief: Uri cold fragility

1. Join ERCOT's Uri outage file to EIA-860; place units on H3 cells.
2. Fit P(outage or derate) against each unit's February 2021 minimum temperature, by fuel type.
3. Encode the fit as a CRC impact definition.
4. Fit GEV to ERA5 `tnn` per cell; evaluate at 10, 25, 50 and 100 years.
5. Microscores and `compute_risk` for MW lost, stated as conditional on a regional cold event.
6. Check against Uri (in sample) and Elliott and Heather (out of sample).

First usable result at about 20 hours: a map of every ERCOT thermal unit by Uri temperature and outage status, with
a first fit.

Main weakness: per-unit causes are not public, so the curve mixes freezing with fuel-supply failures, and
weatherization since 2021 has shifted it. Present it as pre- against post-weatherization.

## Ideas that failed a filter

- Wildfire shutoffs against fire-weather days: needs wind and humidity recipes; over 80 hours.
- Hurricane wind damage to lines: needs a wind-field model on top of track data; over 80 hours.
- Substation storm-surge flooding: needs inundation modelling.
- Any "2050 grid risk" headline: depends on CMIP.

## Ground-truth data worth knowing

| Dataset | Use | Terms |
| --- | --- | --- |
| ERCOT Uri unit outage file (Feb 10–19, 2021) | cold fragility | ERCOT terms; reuse wording not verified |
| ERCOT hourly load archives | load against temperature | ERCOT terms; not verified |
| EPA CAMPD hourly unit output | heat derating | US federal |
| EIA-860, EIA-923, EIA-930 | plant inventory, generation, hourly demand | US federal |
| EAGLE-I county outages, 2014–2024, 15-minute | outage outcomes | CC BY 4.0 |
| NRC Power Reactor Status | nuclear derates | US federal |
| AESO hourly load, 2011–2024 | Alberta | disclaimer; terms not verified |

## Corrections and open checks from this research

- The report says an older crc-docs notebook (`portfolio_risk_metrics`) demonstrated `compute_risk`. It is not on
  crc-docs `main` as cloned on 2026-11-09 (the notebooks folder has the five questions and the primer). Safer claim
  for any pitch: first use of impacts and `compute_risk` on real energy assets with an observation-fitted impact.
- CRC Open horizons: the 63-hazard notebook output shows 5-year steps including 2025 and 2030; confirm before
  quoting a horizon list.
- Engineering coefficients (gas-turbine %/°C, ampacity %/°C, hail breakage size) are literature priors; show ranges.
- Several event figures (Heather peak load has four published values) need a primary source before use.

## Skill notes

Follow crc-docs: one question per skill; `SKILL.md` plus `scripts/`; the pipeline writes `summary.json`. Add what
theirs lack: a JSON Schema for the output and an eval set of 10–15 prompts (in scope, out of region, "what about
2080?", missing data, licence question, °F/°C trap, "is this a forecast?").
