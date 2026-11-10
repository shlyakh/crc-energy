# Requirements: hail impact functions v0 — solar, buildings, cars

Draft, 2026-11-10. Author: Yuri Shlyakhter, with Claude. Not yet scheduled as a phase.

## Purpose and status

This spec defines four first-approximation hail impact functions for implementation in CRC: one for solar
plants, two for buildings and one for cars. Each maps a hail diameter in millimetres to a damage ratio between
0 and 1. It is a handoff document for the Claude Code build in crc-lab.

These are v0 curves. They are good enough to wire the pipeline end to end and to produce order-of-magnitude
numbers. They are not calibrated to Texas losses, and two of them are engineering placeholders. The companion
research report ("Hail and Convective-Gust Damage Curves", 10 Nov 2026) holds the sources and the wider
catalog; curve ids such as PV-H-01 refer to it.

| Curve id | Asset | Output | Basis | Role |
| --- | --- | --- | --- | --- |
| `pv_plant_hail_v0` | Utility-scale solar plant | Damage ratio of plant value | Kiwa PVEL lab breakage rates by glass class, plus a stow adjustment | Baseline; likely an upper bound for unstowed modules |
| `bld_hail_swiss_v0` | Buildings | Damage ratio and fraction affected | Schmid et al. (2024), Swiss insurance claims | Baseline; likely a lower bound for Texas |
| `bld_hail_roof_v0` | Buildings, by roof cover | Damage ratio | Haag roof-damage onset sizes with a placeholder spread | Sensitivity; upper bound |
| `car_hail_swiss_v0` | Cars, general fleet | Damage ratio and fraction affected | Schmid et al. (2024), Swiss insurance claims | Baseline |
| `car_hail_open_lot_v0` | Cars with no shelter | Not defined in v0 | No open curve found | Open item; see last section |

Every number carries one of four tags:

- **[S]** stated in the source.
- **[I]** inference or calculation from source values.
- **[P]** placeholder with no source; must be replaced or supplied by the user.
- **[V]** read from a preprint or secondary rendering; verify against the primary source before release.

## Inputs and conventions

All four functions take one hazard input: `D`, the maximum hail diameter at the asset in millimetres. For the
first build this is the NOAA Storm Events hail magnitude converted with `D_mm = inches × 25.4`.

The two Swiss curves were calibrated on a radar product (MESHS, the MeteoSwiss maximum expected severe hail
size on a 1 km grid), not on observed stone size. v0 passes the Storm Events diameter into them unchanged
**[P]**. This is the largest known error in the spec; the last section explains its direction.

Rules that apply to every curve:

- Output is a damage ratio in [0, 1]: repair or replacement cost divided by the asset's replacement value.
- Curves are monotone non-decreasing in `D`. Inputs below the lowest knot or threshold return 0. Inputs above
  the highest knot return the last value.
- `D` must be finite and non-negative. Reject negative or missing values; do not silently return 0.
- Each curve carries metadata: `native_metric`, `calibration_region`, `confidence`, `source`. The JSON block
  below has them.

Three functional forms are used.

**Emanuel-type sigmoid** (Swiss curves), with threshold `v_thresh`, half-point `v_half` and scale `S`:

```latex
v_n = \frac{\max(D - v_{thresh},\,0)}{v_{half} - v_{thresh}}, \qquad f(D) = S\,\frac{v_n^{3}}{1 + v_n^{3}}
```

`f` tends to `S` for large `D`, and equals `S/2` at `D = v_half`.

**Piecewise linear** (solar breakage): linear interpolation between `(D, value)` knots, flat outside the knot
range.

**Lognormal CDF** (roof sensitivity), with median `theta` and log standard deviation `beta`:

```latex
F(D) = \Phi\!\left(\frac{\ln(D/\theta)}{\beta}\right), \qquad F(0) = 0
```

## Solar plant: `pv_plant_hail_v0`

Plant damage ratio is the module glass-breakage probability, adjusted for hail stow, times the share of plant
value that broken modules cost to replace. It has three steps.

**Step 1. Breakage probability by glass class.** Piecewise linear in `D`. Lab results from the Kiwa PVEL Hail
Stress Sequence (research report PV-H-01, PV-H-02).

| D (mm) | `glass_glass_2.0` (2.0 mm / 2.0 mm glass-glass) | Tag |
| --- | --- | --- |
| 25 | 0.00 | [I] qualification-test size, taken as no breakage |
| 35 | 0.18 | [S] |
| 40 | 0.50 | [I] mean of 0.57 (2023) and 0.43 (2026) |
| 45 | 0.61 | [S] |
| 50 | 0.89 | [S] |
| 60 | 1.00 | [I] extrapolated |

| D (mm) | `glass_backsheet_3.2` (3.2 mm tempered glass / backsheet) | Tag |
| --- | --- | --- |
| 40 | 0.00 | [I] |
| 45 | 0.035 | [I] midpoint of 0% and a 7% pooled figure |
| 50 | 0.38 | [I] mean of 0.34, 0.39 and 0.40 |
| 55 | 0.55 | [I] extrapolated |
| 65 | 0.87 | [I] extrapolated |
| 80 | 1.00 | [I] extrapolated |

Above 50 mm the 3.2 mm table has no data. Its upper knots are the 2.0 mm curve stretched in diameter by a
factor of 1.31, the factor that reproduces 0.38 at 50 mm. Default glass class: `glass_glass_2.0` for tracker
plants built from about 2021, `glass_backsheet_3.2` for older plants **[I]**.

**Step 2. Stow adjustment.** A tilted module receives less normal impact energy. v0 uses the elastic model:
energy scales with cos² of the tilt, and single-stone kinetic energy scales with diameter to the power 3.5.
That gives an effective diameter:

```latex
D_{eff} = D \cdot (\cos \alpha)^{2/3.5}
```

where α is the stow tilt from horizontal. The multiplier is 0.758 at 52°, 0.673 at 60° and 0.462 at 75°. This
assumes vertical hail fall and no wind.

Stow is a two-state mixture, because a stow command can fail:

```latex
P_{plant}(D) = p_{stow}\,P_{break}(D_{eff}) + (1 - p_{stow})\,P_{break}(D)
```

For fixed-tilt plants set `p_stow = 1` and α to the fixed tilt.

**Step 3. Damage ratio.**

```latex
MDR_{plant}(D) = c_{module} \cdot P_{plant}(D)
```

| Parameter | Meaning | v0 default | Tag |
| --- | --- | --- | --- |
| `glass_class` | Which breakage table to use | `glass_glass_2.0` | [I] |
| `stow_tilt_deg` | Hail stow angle α | 60 | [P]; vendors range from 50 to 75 |
| `p_stow` | Probability the plant is stowed when hail arrives | 0.8 | [P] |
| `module_cost_share` | Cost to replace all modules, with labour, as a share of plant value | 0.40 | [P]; no open source found |
| `stow_energy_factor` | Optional override for cos²α, to test the inelastic correction | none | Sensitivity only |

Two cautions on direction of error:

- **Unstowed modules: likely too high.** The lab fires 11 stones of the stated size at each module. In a
  storm, the reported diameter is the largest stone and most stones are smaller.
- **Stowed modules: evidence conflicts.** At Fort Bend in March 2024, 2.0 mm glass-glass modules stowed at 52°
  had no damage under radar-estimated hail of 40 to 100 mm. This curve gives 0.40 at 50.8 mm and 0.98 at 76 mm
  for the same case. Against that, kWh Analytics reports the elastic model understates delivered energy at
  steep angles when wind is present. Treat stowed results as a range, not a number.

## Buildings: `bld_hail_swiss_v0` and `bld_hail_roof_v0`

Buildings get two curves that bracket the answer: a published Swiss claims curve as the low baseline and a
roof-cover engineering curve as the high sensitivity. Report both; the gap between them is the honest
uncertainty in v0.

**Baseline: `bld_hail_swiss_v0`.** Emanuel-type sigmoids from Schmid et al. (2024), NHESS 24, 847–872,
calibrated on about 250,000 Swiss building claims (research report BLD-H-01, BLD-H-02). Licence CC BY 4.0.

| Output | v_thresh (mm) | v_half (mm) | S | Tag |
| --- | --- | --- | --- | --- |
| Damage ratio (damage / total building value) | 20.0 | 73.9 | 0.00147 | [V] |
| Fraction of buildings affected | 8.6 | 66.9 | 0.118 | [V] |

Use the damage-ratio curve for loss. The fraction-affected curve is for claim counts only; do not multiply the
two.

This curve saturates at a damage ratio of 0.15%. That is low for Texas for two reasons. The Swiss stock has
tile roofs, not asphalt shingles. And the curve is averaged over every building in a radar cell, including the
many cells where radar indicated hail and none fell.

**Sensitivity: `bld_hail_roof_v0`.** Probability that the roof needs replacement, times the roof's share of
building value:

```latex
MDR_{roof}(D) = c_{roof} \cdot \Phi\!\left(\frac{\ln(D/\theta)}{\beta}\right)
```

| Roof class | Damage onset (mm) | theta (mm) | beta | Tag |
| --- | --- | --- | --- | --- |
| `asphalt_3tab` | 25.4 | 38.3 | 0.25 | Onset [S] Haag; theta [I]; beta [P] |
| `asphalt_laminated` | 31.75 | 47.9 | 0.25 | Onset [S] Haag; theta [I]; beta [P] |

The Haag sizes are where functional damage begins, not where half of roofs fail. v0 sets the onset as the 5th
percentile, so `theta = onset × exp(1.645 × beta)`. The spread `beta = 0.25` has no source.

| Parameter | Meaning | v0 default | Tag |
| --- | --- | --- | --- |
| `roof_class` | Which row to use | `asphalt_laminated` | [I] |
| `roof_cost_share` | Roof replacement cost as a share of building replacement value | 0.10 | [P] |

This curve assumes hail of size `D` actually fell on the building, ignores roof age, and covers roofs only. It
omits siding, windows and rooftop equipment. Other roof covers (metal, tile, membrane) are not defined in v0.

## Cars: `car_hail_swiss_v0`

Cars get one curve in v0: the Schmid et al. (2024) sigmoids, calibrated on more than 50,000 claims from one
Swiss motor insurer (research report CAR-H-01, CAR-H-02). Licence CC BY 4.0.

| Output | v_thresh (mm) | v_half (mm) | S | Tag |
| --- | --- | --- | --- | --- |
| Damage ratio (damage / total insured car value) | 13.7 | 53.3 | 0.00396 | [V] |
| Fraction of cars affected | 8.1 | 55.0 | 0.046 | [V] |

The curve applies to a general fleet located by registered address. It already contains the chance that a car
is garaged or somewhere else when hail falls, so it saturates at a damage ratio of about 0.4%.

Do not use it for cars known to be in the open, such as dealership lots, rental lots or port storage. It will
understate their damage by a wide margin, and v0 has no curve for them. The only open anchors are thresholds:
dents begin near 20 mm and glass breaks near 40 to 50 mm (Hohl et al. 2002).

## Machine-readable parameters

This block is the single source of parameters for the implementation; save it as a data file in the repo and
load curves from it. If a table above disagrees with it, the block wins.

```json
{
  "schema": "hail-impact-curves/v0",
  "as_of": "2026-11-10",
  "hazard_input": {"name": "hail_diameter_obs_mm", "unit": "mm", "source_v0": "NOAA Storm Events hail magnitude (inches x 25.4)"},
  "curves": {
    "pv_plant_hail_v0": {
      "asset": "solar_plant",
      "output": "damage_ratio",
      "form": "stow_mixture_of_piecewise_linear",
      "native_metric": "lab ice-ball diameter, normal incidence, 11 impacts per module",
      "calibration_region": "laboratory",
      "confidence": "lab points stated; extrapolation, stow model and cost share inferred or placeholder",
      "source": "Kiwa PVEL PV Module Reliability Scorecards 2023, 2024, 2026 (Hail Stress Sequence)",
      "break_probability": {
        "glass_glass_2.0": [[25, 0.0], [35, 0.18], [40, 0.50], [45, 0.61], [50, 0.89], [60, 1.0]],
        "glass_backsheet_3.2": [[40, 0.0], [45, 0.035], [50, 0.38], [55, 0.55], [65, 0.87], [80, 1.0]]
      },
      "stow": {"model": "elastic", "d_eff": "D * cos(stow_tilt_deg)^(2/3.5)", "ke_diameter_exponent": 3.5},
      "defaults": {"glass_class": "glass_glass_2.0", "stow_tilt_deg": 60, "p_stow": 0.8, "module_cost_share": 0.40},
      "placeholders": ["stow_tilt_deg", "p_stow", "module_cost_share"]
    },
    "bld_hail_swiss_v0": {
      "asset": "building",
      "form": "emanuel_sigmoid",
      "exponent": 3,
      "native_metric": "MESHS (MeteoSwiss radar), 1 km daily maximum",
      "calibration_region": "Switzerland",
      "confidence": "published; parameters to verify against final Table 2",
      "source": "Schmid et al. 2024, NHESS 24, 847-872, doi:10.5194/nhess-24-847-2024, CC BY 4.0",
      "damage_ratio": {"v_thresh": 20.0, "v_half": 73.9, "scale": 0.00147},
      "fraction_affected": {"v_thresh": 8.6, "v_half": 66.9, "scale": 0.118}
    },
    "bld_hail_roof_v0": {
      "asset": "building",
      "output": "damage_ratio",
      "form": "scaled_lognormal_cdf",
      "native_metric": "hail diameter at the roof",
      "calibration_region": "United States (engineering thresholds)",
      "confidence": "onset sizes stated; theta inferred; beta and cost share placeholder",
      "source": "Haag Engineering onset thresholds via Smith 2013 (IIBEC)",
      "roof_classes": {
        "asphalt_3tab": {"onset_mm": 25.4, "theta": 38.3, "beta": 0.25},
        "asphalt_laminated": {"onset_mm": 31.75, "theta": 47.9, "beta": 0.25}
      },
      "defaults": {"roof_class": "asphalt_laminated", "roof_cost_share": 0.10},
      "placeholders": ["beta", "roof_cost_share"]
    },
    "car_hail_swiss_v0": {
      "asset": "car_general_fleet",
      "form": "emanuel_sigmoid",
      "exponent": 3,
      "native_metric": "MESHS (MeteoSwiss radar), 1 km daily maximum",
      "calibration_region": "Switzerland",
      "confidence": "published; parameters to verify against final Table 2",
      "source": "Schmid et al. 2024, NHESS 24, 847-872, doi:10.5194/nhess-24-847-2024, CC BY 4.0",
      "damage_ratio": {"v_thresh": 13.7, "v_half": 53.3, "scale": 0.00396},
      "fraction_affected": {"v_thresh": 8.1, "v_half": 55.0, "scale": 0.046}
    }
  }
}
```

## Test vectors

The implementation is correct when it reproduces these values to a relative tolerance of 1% (absolute 1e-6
near zero). They were computed from the formulas and parameters above. Hail sizes are the standard Storm
Events reference sizes.

**Solar.** Columns three to five are breakage probabilities; the last is `pv_plant_hail_v0` at defaults
(2.0 mm glass-glass, 60° stow, `p_stow` 0.8, cost share 0.40).

| Hail size | D (mm) | 2.0 glass-glass, flat | 3.2 backsheet, flat | 2.0 glass-glass, stowed 60° | Plant damage ratio at defaults |
| --- | --- | --- | --- | --- | --- |
| 1.00 in | 25.40 | 0.0072 | 0.0000 | 0.0000 | 0.0006 |
| 1.25 in | 31.75 | 0.1215 | 0.0000 | 0.0000 | 0.0097 |
| 1.50 in | 38.10 | 0.3784 | 0.0000 | 0.0115 | 0.0340 |
| 1.75 in | 44.45 | 0.5979 | 0.0312 | 0.0884 | 0.0761 |
| 2.00 in | 50.80 | 0.8988 | 0.4072 | 0.1653 | 0.1248 |
| 2.50 in | 63.50 | 1.0000 | 0.8220 | 0.5601 | 0.2592 |
| 2.75 in | 69.85 | 1.0000 | 0.9120 | 0.7223 | 0.3111 |
| 3.00 in | 76.20 | 1.0000 | 0.9671 | 0.9041 | 0.3693 |
| 4.00 in | 101.60 | 1.0000 | 1.0000 | 1.0000 | 0.4000 |

**Buildings.** Roof columns use `roof_cost_share` 0.10.

| Hail size | D (mm) | Swiss damage ratio | Swiss fraction affected | Roof, 3-tab | Roof, laminated |
| --- | --- | --- | --- | --- | --- |
| 0.75 in | 19.05 | 0 | 0.0007 | 0.0003 | 0.0000 |
| 1.00 in | 25.40 | 1.477e-06 | 0.0028 | 0.0050 | 0.0006 |
| 1.25 in | 31.75 | 1.507e-05 | 0.0070 | 0.0227 | 0.0050 |
| 1.50 in | 38.10 | 5.363e-05 | 0.0135 | 0.0492 | 0.0180 |
| 1.75 in | 44.45 | 1.255e-04 | 0.0223 | 0.0724 | 0.0383 |
| 2.00 in | 50.80 | 2.312e-04 | 0.0324 | 0.0871 | 0.0593 |
| 2.50 in | 63.50 | 5.065e-04 | 0.0537 | 0.0978 | 0.0870 |
| 2.75 in | 69.85 | 6.493e-04 | 0.0634 | 0.0992 | 0.0934 |
| 4.00 in | 101.60 | 1.141e-03 | 0.0947 | 0.1000 | 0.0999 |

At 2 inches the two building curves differ by a factor of about 250. That gap is expected; see the last
section.

**Cars.**

| Hail size | D (mm) | Swiss damage ratio | Swiss fraction affected |
| --- | --- | --- | --- |
| 0.75 in | 19.05 | 9.741e-06 | 0.0006 |
| 1.00 in | 25.40 | 9.957e-05 | 0.0022 |
| 1.25 in | 31.75 | 3.426e-04 | 0.0052 |
| 1.50 in | 38.10 | 7.507e-04 | 0.0095 |
| 1.75 in | 44.45 | 1.263e-03 | 0.0146 |
| 2.00 in | 50.80 | 1.787e-03 | 0.0198 |
| 2.50 in | 63.50 | 2.635e-03 | 0.0286 |
| 2.75 in | 69.85 | 2.932e-03 | 0.0320 |
| 4.00 in | 101.60 | 3.628e-03 | 0.0408 |

Extra checks: every curve returns 0 at `D = 0`; each Swiss curve returns exactly `scale / 2` at `D = v_half`;
the stow multiplier is 0.7579 at 52°, 0.6730 at 60° and 0.4619 at 75°. As a cross-check against the source,
the paper's empirical values at 60 mm are about 5% of buildings affected and a building damage ratio near
0.05%; the fitted curves give 4.8% and 0.043%.

## Wiring into CRC

Implement all four curves as plain Python callables first, tested against the vectors above, then map them
onto CRC's impact types where they fit. The CRC details below come from the research report's reading of the
repos, not from running the code; confirm each against the pinned crc-sdk version before relying on it.

| Curve | Likely CRC form | Check first |
| --- | --- | --- |
| `bld_hail_swiss_v0`, `car_hail_swiss_v0` | `SigmoidImpact` if its formula is the Emanuel cubic form; otherwise a callable | The exact formula behind `SigmoidImpact`; a logistic sigmoid is not equivalent |
| `pv_plant_hail_v0`, step 1 only | `PiecewiseLinearImpact` on the knot table | How knots and out-of-range inputs are specified |
| `pv_plant_hail_v0`, full | Callable, because of the stow mixture and per-asset glass class | Whether asset columns reach the callable through the context argument |
| `bld_hail_roof_v0` | Callable, with `roof_class` from asset context | Same context question |

Implementation tasks, in order:

1. Add the JSON block as a data file and a loader that validates it (knots strictly increasing in `D`, values
   in [0, 1], `v_half > v_thresh`).
2. Write the three functional forms and the four curve callables. Keep them free of CRC imports so they can be
   tested alone.
3. Add tests from the test vectors, plus monotonicity and bounds checks on a fine grid from 0 to 150 mm.
4. Register the curves with CRC using `value_semantics="damage ratio"`, and carry `native_metric` and
   `confidence` through as metadata.
5. Add a hail hazard factor named `hail_diameter_obs_mm`, kept distinct from any future radar metric, so a
   curve cannot be fed the wrong metric unnoticed.

Two design points to settle with the hazard build:

- **Event losses, not return levels.** The report says CRC applies an impact to each return-period level of a
  fitted distribution. For hail, apply the curves to each Storm Events event at each asset and aggregate
  losses afterwards. Hail is tail-heavy and spatially clustered, so the transform of a return level is not the
  expected loss.
- **Zero-heavy hazard.** Most asset-years have no hail. The report notes CRC requires an explicit hurdle
  policy for such hazards and will not infer the point mass at zero.

## Known weaknesses and next iteration

The hazard metric mismatch outweighs every other error in v0, and it pushes the Swiss curves low. A Storm
Events report means hail of that size was seen at a point. A radar cell value is an estimate that is wrong
more than half the time at the grid-cell level in the Swiss data. Feeding observed sizes into radar-calibrated
curves therefore understates damage where hail is confirmed.

| Weakness | Direction of error | What would replace it |
| --- | --- | --- |
| Storm Events diameter used as MESHS | Swiss curves too low | Schmid et al. (2025) curve keyed to crowdsourced observed hail size (BLD-H-03); parameters not yet extracted |
| Swiss building stock and roofs | Too low for asphalt-shingle regions | A US claims-calibrated curve; none is open today |
| Roof curve spread and cost share are placeholders | Unknown; treat as upper bound | Haag's full threshold table by roof cover; IBHS test data; a sourced roof cost share |
| Lab breakage applied to maximum stone size | Too high for unstowed modules | Field outcomes, for example the NREL DuraMAT hail forensics data |
| Elastic stow model, no wind | Conflicting evidence | A sourced inelastic correction; joint hail and gust input |
| Module cost share and `p_stow` are placeholders | Unknown | Plant cost breakdowns; tracker vendor reliability data |
| No curve for cars in the open | Missing | Hohl et al. (2002) kinetic-energy curve or a US insurer study |
| Schmid parameters tagged [V] | Possible transcription error | Check against the paper's final Table 2 |

Open decisions before the build:

- [ ] Accept the placeholder defaults (`p_stow` 0.8, stow 60°, module cost share 0.40, roof cost share 0.10),
      or supply your own.
- [ ] Decide whether the explorer shows the building baseline, the sensitivity, or both as a range.
- [ ] Decide whether curve data ships in crc-lab or in a separate CC BY 4.0 data repo, given CRC's AGPL
      licence.

## Sources

All taken through the research report of 10 Nov 2026; the primary pages were not re-opened for this spec.

- [Schmid et al. (2024), NHESS 24, 847–872](https://nhess.copernicus.org/articles/24/847/2024/): building and
  car sigmoids.
- [Kiwa PVEL scorecard, Hail Stress Sequence](https://scorecard.pvel.com/hail-stress-sequence/): module
  breakage rates by glass class.
- [Smith (2013), IIBEC](https://iibec.org/wp-content/uploads/2013-02-smith.pdf): Haag roof-damage onset sizes.
- [kWh Analytics Solar Risk Assessment 2025](https://kwhanalytics.com/wp-content/uploads/2025/06/Solar-Risk-Assessment-2025.pdf):
  stow field evidence and the inelastic correction.
- [Schmid et al. (2025), Meteorological Applications](https://rmets.onlinelibrary.wiley.com/doi/10.1002/met.70059):
  observed-size building curve, next extraction target.
- [RiskThinking/crc-sdk](https://github.com/RiskThinking/crc-sdk): impact transforms and contracts.
