# Phase 4 note: sensitivity of hail at the asset (local report density)

Located hail reports 1996–2025: 77,485. Rule: grow a circle until it holds N reports, with a minimum and maximum radius; rate = reports / (area × years); annual chance at the point = 1 − exp(−rate × footprint). **The footprint (area hit per report) is a placeholder with no source.** Every number is computed by `just assets-sensitivity`.

## Across the Texas solar plants

| Rule (N, min–max radius km, footprint km²) | Too few reports | Radius km, median (p10–p90) | Reports per 100 km² per year, median (p10–p90) | Annual chance of ≥ 2 in hail, median (p10–p90) |
| --- | --- | --- | --- | --- |
| 30, 10–75, 25 | 0 of 250 | 14.0 (10.0–23.6) | 0.169 (0.059–0.519) | 0.0064 (0.0000–0.0218) |
| 100, 10–75, 25 (default) | 1 of 250 | 24.5 (15.0–39.0) | 0.178 (0.077–0.487) | 0.0073 (0.0014–0.0226) |
| 300, 10–75, 25 | 20 of 250 | 40.5 (26.4–70.6) | 0.195 (0.068–0.456) | 0.0076 (0.0023–0.0218) |
| 100, 0–75, 25 | 1 of 250 | 24.5 (15.0–39.0) | 0.178 (0.077–0.487) | 0.0073 (0.0014–0.0226) |
| 100, 25–75, 25 | 1 of 250 | 25.0 (25.0–39.0) | 0.177 (0.077–0.460) | 0.0070 (0.0014–0.0201) |
| 100, 10–75, 20 | 1 of 250 | 24.5 (15.0–39.0) | 0.178 (0.077–0.487) | 0.0061 (0.0011–0.0184) |
| 100, 10–75, 50 | 1 of 250 | 24.5 (15.0–39.0) | 0.178 (0.077–0.487) | 0.0127 (0.0027–0.0375) |
| 100, 10–75, 100 | 1 of 250 | 24.5 (15.0–39.0) | 0.178 (0.077–0.487) | 0.0214 (0.0051–0.0662) |

## At ten city centres: reports per 100 km² per year (radius km)

| City | N30-r10-75-A25 | N100-r10-75-A25 | N300-r10-75-A25 | N100-r0-75-A25 | N100-r25-75-A25 | N100-r10-75-A20 | N100-r10-75-A50 | N100-r10-75-A100 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Houston | 1.17 (10) | 1.17 (10) | 0.44 (27) | 2.70 (6) | 0.46 (25) | 1.17 (10) | 1.17 (10) | 1.17 (10) |
| Dallas | 1.07 (10) | 1.07 (10) | 0.75 (21) | 1.15 (10) | 0.72 (25) | 1.07 (10) | 1.07 (10) | 1.07 (10) |
| San Antonio | 1.29 (10) | 1.29 (10) | 0.71 (21) | 1.64 (8) | 0.64 (25) | 1.29 (10) | 1.29 (10) | 1.29 (10) |
| Austin | 1.45 (10) | 1.45 (10) | 0.68 (22) | 1.65 (8) | 0.61 (25) | 1.45 (10) | 1.45 (10) | 1.45 (10) |
| Fort Worth | 2.03 (10) | 2.03 (10) | 1.78 (13) | 7.51 (4) | 1.45 (25) | 2.03 (10) | 2.03 (10) | 2.03 (10) |
| El Paso | 0.68 (10) | 0.37 (23) | 0.07 (75) | 0.37 (23) | 0.33 (25) | 0.37 (23) | 0.37 (23) | 0.37 (23) |
| Amarillo | 5.28 (10) | 5.28 (10) | 5.28 (10) | 22.50 (3) | 1.77 (25) | 5.28 (10) | 5.28 (10) | 5.28 (10) |
| Lubbock | 1.18 (10) | 1.18 (10) | 0.89 (19) | 1.37 (9) | 0.66 (25) | 1.18 (10) | 1.18 (10) | 1.18 (10) |
| Corpus Christi | 0.59 (11) | 0.19 (27) | 0.09 (71) | 0.19 (27) | 0.19 (27) | 0.19 (27) | 0.19 (27) | 0.19 (27) |
| Midland | 1.77 (10) | 1.77 (10) | 0.54 (24) | 2.90 (6) | 0.52 (25) | 1.77 (10) | 1.77 (10) | 1.77 (10) |

## Reading

- With no minimum radius, city centres reach N inside a few kilometres and the rate measures where people live. The minimum radius pulls city rates down; it barely moves rural plants, whose circles are already wide.
- N trades noise for locality: 30 reports keep the circle small, 300 widen it and smooth the rate.
- The footprint scales the annual chance almost linearly while chances are small. It is the least known number here.
- Rates still follow reporting density. Compare neighbouring plants, not a remote plant with a suburban one.
