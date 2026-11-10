# Phase 4 note: radar hail at the solar plants

MRMS radar hail size (MESH), 24-hour maximum valid at 12 UTC, 2020-10-15 to 2025-12-31: 1,903 days (5.2 years) from NOAA's open archive. A radar hail day at a plant is a day whose maximum over the plant's array area reaches the threshold. Every number is computed by `python -m crc_lab.radar.build`.

MESH is a radar estimate built to exceed most observed sizes; it says where hail probably fell and roughly how big, not what reached the ground. Five years is a short record: a plant with no radar hail day in it is not hail-free.

## Across the 250 plants

| Measure | 10th percentile | Median | 90th percentile |
| --- | --- | --- | --- |
| Radar hail days per year over the plant, MESH 30 mm or more | 0.00 | 0.19 | 0.58 |
| Radar hail days per year over the plant, MESH 50 mm or more | 0.00 | 0.00 | 0.19 |
| Radar hail days per year at a point, averaged over 25 km, 30 mm or more | 0.04 | 0.18 | 0.34 |
| Radar hail days per year at a point, averaged over 25 km, 50 mm or more | 0.00 | 0.02 | 0.05 |
| Report-based hits per year, hail 1 inch or more (footprint 25 km²) | 0.020 | 0.057 | 0.128 |
| Report-based hits per year, hail 2 inches or more | 0.0014 | 0.0073 | 0.0214 |
| Radar (30 mm, 25 km average) ÷ report-based (1 inch) | 0.8 | 2.7 | 6.7 |
| Radar (30 mm, 25 km average) ÷ report-based, bias-corrected (1 inch) | 0.4 | 0.9 | 1.9 |
| Radar (50 mm, 25 km average) ÷ report-based (2 inches) | 0.2 | 2.7 | 11.0 |

Plants with no radar hail day over them in the period: 90 at 30 mm, 198 at 50 mm.

## Measured swath areas in the Texas box

Connected areas at or above the threshold on one day, of at least five grid cells (about 5 km²).

| Threshold | Swaths | 25th percentile km² | Median km² | 75th percentile km² | 90th percentile km² | Mean km² |
| --- | --- | --- | --- | --- | --- | --- |
| 30 mm | 18,844 | 8.1 | 16.0 | 43.6 | 122.7 | 59.1 |
| 50 mm | 4,477 | 7.7 | 14.6 | 33.9 | 76.6 | 34.8 |

The 25 km² footprint used for report-based exposure sits between the median and the mean of these.

## Fort Bend County plants

| Plant | Radar days 30 mm or more | Radar days 50 mm or more | Largest radar size over the plant (mm) | On | Report-based annual chance, 2 inches or more |
| --- | --- | --- | --- | --- | --- |
| Bronson | 0 | 0 | 26.3 | 2024-05-14 | 0.0020 |
| Fighting Jays Solar Project | 1 | 1 | 105.1 | 2024-03-16 | 0.0037 |
| Fort Bend Solar LLC | 0 | 0 | 26.3 | 2024-05-14 | 0.0031 |
| Old 300 Solar Center, LLC | 3 | 0 | 48.6 | 2024-03-16 | 0.0019 |
| Cutlass Solar II | 1 | 1 | 80.6 | 2024-03-16 | 0.0042 |
| Cutlass Solar 1 LLC | 1 | 1 | 52.9 | 2024-03-16 | 0.0034 |

## Highest radar exposure (50 mm or more, local average)

| Plant | County | MW AC | Radar days per year, 50 mm, local | Largest over the plant (mm) | Report-based annual chance, 2 inches or more |
| --- | --- | --- | --- | --- | --- |
| IP Radian, LLC | Brown | 320 | 0.11 | 61.5 | 0.0126 |
| Lumina II Solar Project | Scurry | 327 | 0.08 | 62.7 | 0.0080 |
| TX Pasadena 10585 Red Bluff Road Solar | Harris | 2 | 0.08 | 23.0 | 0.0045 |
| OCI Alamo 4, LLC | Kinney | 40 | 0.07 | 61.1 | 0.0038 |
| OCI Alamo 5 LLC | Uvalde | 100 | 0.07 | 46.3 | 0.0053 |
