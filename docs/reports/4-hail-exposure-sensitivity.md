# Phase 4 note: sensitivity of hail at the asset (local report density)

Located hail reports 1996–2025: 39,624. Rule: grow a circle until it holds N reports, with a minimum and maximum radius; rate = reports / (area × years); annual chance at the point = 1 − exp(−rate × footprint). **The footprint (area hit per report) is a placeholder with no source.** Every number is computed by `just assets-sensitivity`.

## Across the Texas solar plants

| Rule (N, min–max radius km, footprint km²) | Too few reports | Radius km, median (p10–p90) | Reports per 100 km² per year, median (p10–p90) | Annual chance of ≥ 2 in hail, median (p10–p90) |
| --- | --- | --- | --- | --- |
| 30, 10–75, 25 | 0 of 187 | 14.2 (10.0–23.9) | 0.159 (0.056–0.598) | 0.0040 (0.0000–0.0158) |
| 100, 10–75, 25 (default) | 3 of 187 | 26.0 (13.8–39.4) | 0.159 (0.068–0.573) | 0.0038 (0.0009–0.0151) |
| 300, 10–75, 25 | 17 of 187 | 41.8 (25.1–73.9) | 0.182 (0.059–0.510) | 0.0043 (0.0010–0.0151) |
| 100, 0–75, 25 | 3 of 187 | 26.0 (13.8–39.4) | 0.159 (0.068–0.573) | 0.0038 (0.0009–0.0151) |
| 100, 25–75, 25 | 3 of 187 | 26.0 (25.0–39.4) | 0.159 (0.068–0.507) | 0.0038 (0.0008–0.0148) |
| 100, 10–75, 5 | 3 of 187 | 26.0 (13.8–39.4) | 0.159 (0.068–0.573) | 0.0008 (0.0002–0.0030) |
| 100, 10–75, 100 | 3 of 187 | 26.0 (13.8–39.4) | 0.159 (0.068–0.573) | 0.0152 (0.0037–0.0590) |

## At ten city centres: reports per 100 km² per year (radius km)

| City | N30-r10-75-A25 | N100-r10-75-A25 | N300-r10-75-A25 | N100-r0-75-A25 | N100-r25-75-A25 | N100-r10-75-A5 | N100-r10-75-A100 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Houston | 1.17 (10) | 1.17 (10) | 0.44 (27) | 2.70 (6) | 0.46 (25) | 1.17 (10) | 1.17 (10) |
| Dallas | 1.07 (10) | 1.07 (10) | 0.75 (21) | 1.15 (10) | 0.72 (25) | 1.07 (10) | 1.07 (10) |
| San Antonio | 1.29 (10) | 1.29 (10) | 0.71 (21) | 1.64 (8) | 0.64 (25) | 1.29 (10) | 1.29 (10) |
| Austin | 1.45 (10) | 1.45 (10) | 0.68 (22) | 1.65 (8) | 0.61 (25) | 1.45 (10) | 1.45 (10) |
| Fort Worth | 2.03 (10) | 2.03 (10) | 1.78 (13) | 7.51 (4) | 1.45 (25) | 2.03 (10) | 2.03 (10) |
| El Paso | 0.29 (10) | 0.14 (28) | 0.03 (75) | 0.14 (28) | 0.14 (28) | 0.14 (28) | 0.14 (28) |
| Amarillo | 5.28 (10) | 5.28 (10) | 5.28 (10) | 22.50 (3) | 1.77 (25) | 5.28 (10) | 5.28 (10) |
| Lubbock | 1.18 (10) | 1.18 (10) | 0.89 (19) | 1.37 (9) | 0.66 (25) | 1.18 (10) | 1.18 (10) |
| Corpus Christi | 0.30 (11) | 0.15 (27) | 0.06 (71) | 0.15 (27) | 0.15 (27) | 0.15 (27) | 0.15 (27) |
| Midland | 1.77 (10) | 1.77 (10) | 0.54 (24) | 2.90 (6) | 0.52 (25) | 1.77 (10) | 1.77 (10) |

## Reading

- With no minimum radius, city centres reach N inside a few kilometres and the rate measures where people live. The minimum radius pulls city rates down; it barely moves rural plants, whose circles are already wide.
- N trades noise for locality: 30 reports keep the circle small, 300 widen it and smooth the rate.
- The footprint scales the annual chance almost linearly while chances are small. It is the least known number here.
- Rates still follow reporting density. Compare neighbouring plants, not a remote plant with a suburban one.
