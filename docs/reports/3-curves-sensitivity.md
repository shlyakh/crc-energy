# Phase 3 note: sensitivity of the hail and gust curves

Values at ten city centres (the cell containing the point), from `for_assets`, for each way of building the curves. The default is one ring of pooling (7 cells), window 1996–end, Gumbel with a zero atom. Units: hail mm, gust m/s. Every number is computed by the build (`just curves-sensitivity`).

## hail_size, 1 in 10 years (mm)

| City | no pooling | default | two rings | from 2005 | GEV |
| --- | --- | --- | --- | --- | --- |
| Houston | 42.3 | 39.6 | 37.6 | 37.3 | 39.1 |
| Dallas | 47.2 | 63.4 | 62.3 | 55.2 | 62.8 |
| San Antonio | 53.1 | 56.1 | 47.2 | 53.8 | 54.0 |
| Austin | 61.7 | 50.1 | 47.7 | 52.5 | 49.3 |
| Fort Worth | 63.3 | 55.6 | 60.0 | 53.2 | 55.6 |
| El Paso | 20.0 | 31.4 | 28.1 | 32.9 | 32.9 |
| Amarillo | 67.6 | 61.2 | 55.3 | 55.3 | 60.8 |
| Lubbock | 80.8 | 68.6 | 62.6 | 71.6 | 68.3 |
| Corpus Christi | 31.6 | 23.8 | 23.4 | 23.8 | 23.9 |
| Midland | 64.2 | 54.7 | 49.7 | 57.6 | 54.0 |

## hail_size, 1 in 50 years (mm)

| City | no pooling | default | two rings | from 2005 | GEV |
| --- | --- | --- | --- | --- | --- |
| Houston | 56.9 | 55.2 | 54.1 | 51.5 | 55.8 |
| Dallas | 69.0 | 93.6 | 90.6 | 79.4 | 94.2 |
| San Antonio | 75.3 | 83.0 | 70.0 | 80.2 | 85.0 |
| Austin | 85.4 | 72.7 | 71.1 | 75.2 | 73.6 |
| Fort Worth | 83.4 | 76.4 | 84.3 | 73.4 | 76.3 |
| El Paso | 33.1 | 45.7 | 42.5 | 47.0 | 45.5 |
| Amarillo | 89.5 | 84.1 | 78.5 | 72.7 | 85.0 |
| Lubbock | 112.5 | 96.1 | 90.6 | 101.4 | 96.9 |
| Corpus Christi | 46.1 | 40.4 | 44.7 | 43.0 | 40.6 |
| Midland | 84.3 | 77.2 | 71.6 | 83.4 | 77.9 |

## hail_size, 1 in 100 years (mm)

| City | no pooling | default | two rings | from 2005 | GEV |
| --- | --- | --- | --- | --- | --- |
| Houston | 63.1 | 61.7 | 60.9 | 57.4 | 63.3 |
| Dallas | 78.0 | 106.2 | 102.4 | 89.5 | 107.8 |
| San Antonio | 84.5 | 94.2 | 79.4 | 91.2 | 99.9 |
| Austin | 95.3 | 82.1 | 80.7 | 84.7 | 84.4 |
| Fort Worth | 91.9 | 85.1 | 94.5 | 81.9 | 84.9 |
| El Paso | 38.0 | 51.4 | 47.9 | 52.6 | 49.3 |
| Amarillo | 98.7 | 93.8 | 88.1 | 80.0 | 95.6 |
| Lubbock | 126.0 | 107.7 | 102.2 | 113.9 | 109.3 |
| Corpus Christi | 51.9 | 46.3 | 52.2 | 49.5 | 46.2 |
| Midland | 92.7 | 86.5 | 80.6 | 94.1 | 88.4 |

### Curve kinds, hail_size

| Variant | hurdle:genextreme | hurdle:gumbel_r | point_mass | tabulated |
| --- | --- | --- | --- | --- |
| no pooling | 0 | 2314 | 228 | 24 |
| default | 0 | 2531 | 14 | 21 |
| two rings | 0 | 2556 | 0 | 10 |
| from 2005 | 0 | 2504 | 50 | 12 |
| GEV | 2548 | 4 | 14 | 0 |

## thunderstorm_gust, 1 in 10 years (m/s)

| City | no pooling | default | two rings | from 2005 | GEV |
| --- | --- | --- | --- | --- | --- |
| Houston | 34.2 | 31.4 | 30.3 | 31.6 | 31.4 |
| Dallas | 32.3 | 34.2 | 34.4 | 33.7 | 34.4 |
| San Antonio | 35.5 | 32.6 | 31.2 | 32.6 | 33.2 |
| Austin | 33.9 | 31.7 | 30.8 | 32.6 | 32.4 |
| Fort Worth | 34.4 | 33.6 | 34.1 | 34.0 | 33.9 |
| El Paso | 0.0 | 29.0 | 27.6 | 28.8 | 30.4 |
| Amarillo | 37.6 | 35.5 | 33.5 | 35.9 | 35.8 |
| Lubbock | 36.7 | 35.9 | 34.6 | 36.1 | 35.6 |
| Corpus Christi | 31.0 | 31.5 | 30.2 | 31.8 | 31.7 |
| Midland | 37.2 | 33.2 | 31.7 | 33.8 | 33.2 |

## thunderstorm_gust, 1 in 50 years (m/s)

| City | no pooling | default | two rings | from 2005 | GEV |
| --- | --- | --- | --- | --- | --- |
| Houston | 40.1 | 35.9 | 34.6 | 35.9 | 35.8 |
| Dallas | 38.0 | 39.5 | 40.0 | 38.9 | 39.0 |
| San Antonio | 43.2 | 38.6 | 37.0 | 38.2 | 38.1 |
| Austin | 39.9 | 36.6 | 36.1 | 37.8 | 35.5 |
| Fort Worth | 39.5 | 38.4 | 39.5 | 39.0 | 37.4 |
| El Paso | 25.0 | 33.2 | 31.7 | 33.4 | 31.3 |
| Amarillo | 43.3 | 41.1 | 39.0 | 41.7 | 40.5 |
| Lubbock | 42.3 | 42.0 | 40.8 | 42.4 | 42.3 |
| Corpus Christi | 35.6 | 36.9 | 35.7 | 37.3 | 36.7 |
| Midland | 44.7 | 40.6 | 38.6 | 41.9 | 40.6 |

## thunderstorm_gust, 1 in 100 years (m/s)

| City | no pooling | default | two rings | from 2005 | GEV |
| --- | --- | --- | --- | --- | --- |
| Houston | 42.6 | 37.7 | 36.4 | 37.7 | 37.5 |
| Dallas | 40.5 | 41.8 | 42.4 | 41.0 | 40.7 |
| San Antonio | 46.5 | 41.1 | 39.4 | 40.4 | 39.7 |
| Austin | 42.5 | 38.7 | 38.2 | 39.9 | 36.3 |
| Fort Worth | 41.7 | 40.4 | 41.7 | 41.1 | 38.6 |
| El Paso | 29.9 | 34.9 | 33.2 | 35.2 | 31.3 |
| Amarillo | 45.7 | 43.4 | 41.3 | 44.0 | 42.2 |
| Lubbock | 44.6 | 44.5 | 43.3 | 45.0 | 45.4 |
| Corpus Christi | 37.6 | 39.1 | 37.9 | 39.6 | 38.6 |
| Midland | 47.8 | 43.7 | 41.3 | 45.2 | 43.6 |

### Curve kinds, thunderstorm_gust

| Variant | fitted:gumbel_r | hurdle:genextreme | hurdle:gumbel_r | point_mass | tabulated |
| --- | --- | --- | --- | --- | --- |
| no pooling | 2 | 0 | 2132 | 406 | 26 |
| default | 0 | 0 | 2515 | 29 | 22 |
| two rings | 0 | 0 | 2544 | 0 | 22 |
| from 2005 | 0 | 0 | 2497 | 59 | 10 |
| GEV | 0 | 2535 | 2 | 29 | 0 |

## Reading

- **No pooling** leaves single cells with few non-zero years: more `point_mass`/`tabulated` rows and noisier tails.
- **Two rings** (19 cells) smooths more; compare the city spread against the default.
- **From 2005** uses 21 years instead of 30: shows how much the early, sparser years matter.
- **GEV** adds a shape parameter; with 30 (pooled: 210) samples and large zero shares the shape is poorly constrained, which is why Gumbel is the default.
