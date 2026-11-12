# NASA NEX-GDDP-CMIP6 projections: assessment

Generated from the records of the run of 2026-11-12T04:51:25Z against crc-framework 0.6.0, crc-sdk 0.11.1. **Draft: not yet reviewed.**
Do not edit: change the source file or re-run the assessment and rebuild.

- **Purpose (the framework's documentation):** Annual extremes from bias-adjusted, downscaled daily model output at 0.25 degree, one model and member at a time.
- **Publisher:** NASA NCCS · https://nex-gddp-cmip6.s3.us-west-2.amazonaws.com/NEX-GDDP-CMIP6
- **Entry points:** `HazardDataset.nex_gddp_cmip6`
- **Status:** exploration assessed, verification assessed, validation not assessed
- **Options, recipe:** assessed rx1day, rx5day; not assessed tnn, txx
- **Options, scenario:** assessed historical, ssp585; not assessed ssp126, ssp245, ssp370
- **Options, version:** assessed 1.0, 1.1; not assessed 1.2

## Exploration

### What was read

Model ACCESS-CM2, member r1i1p1f1, the Texas box. Counted from NASA's files by the reference reader.

| Case | File version | Licence in the file | Calendar | Days | Cells in box | Cells with a value | Lowest | Highest | Unit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rx1day historical 2014 v1.0 | 1.0 | CC-BY-SA 4.0 | proleptic_gregorian | 365 | 2,332 | 2,158 | 12.74 | 78.99 | mm/day |
| rx5day historical 2014 v1.0 | 1.0 | CC-BY-SA 4.0 | proleptic_gregorian | 365 | 2,332 | 2,158 | 32.48 | 178.75 | mm |
| txx historical 2014 v1.0 | 1.0 | CC-BY-SA 4.0 | proleptic_gregorian | 365 | 2,332 | 2,158 | 27.32 | 46.68 | degC |
| tnn historical 2014 v1.0 | 1.0 | CC-BY-SA 4.0 | proleptic_gregorian | 365 | 2,332 | 2,158 | -34.46 | 1.78 | degC |
| rx1day historical 2014 v1.1 | 1.1 | CC-BY 4.0 | proleptic_gregorian | 365 | 2,332 | 2,158 | 12.74 | 78.99 | mm/day |
| rx1day ssp585 2050 v1.0 | 1.0 | CC-BY-SA 4.0 | proleptic_gregorian | 365 | 2,332 | 2,158 | 11.96 | 101.60 | mm/day |
| rx5day ssp585 2050 v1.0 | 1.0 | CC-BY-SA 4.0 | proleptic_gregorian | 365 | 2,332 | 2,158 | 25.83 | 261.72 | mm |
| txx ssp585 2050 v1.0 | 1.0 | CC-BY-SA 4.0 | proleptic_gregorian | 365 | 2,332 | 2,158 | 30.23 | 51.23 | degC |
| tnn ssp585 2050 v1.0 | 1.0 | CC-BY-SA 4.0 | proleptic_gregorian | 365 | 2,332 | 2,158 | -32.21 | 8.82 | degC |
| rx1day ssp585 2050 v1.1 | 1.1 | CC-BY 4.0 | proleptic_gregorian | 365 | 2,332 | 2,158 | 11.96 | 101.60 | mm/day |
| rx5day historical 2014 v1.1 | 1.1 | CC-BY 4.0 | proleptic_gregorian | 365 | 2,332 | 2,158 | 32.48 | 178.75 | mm |

### File versions NASA serves

HTTP status of each version's address. crc-sdk accepts 1.0, 1.1, 1.2.

| Variable | Scenario | Year | v1.0 | v1.1 | v1.2 | v2.0 |
| --- | --- | --- | --- | --- | --- | --- |
| tasmax | historical | 2014 | served | no (404) | no (404) | served |
| tasmin | historical | 2014 | served | no (404) | no (404) | served |
| pr | historical | 2014 | served | served | no (404) | served |
| tasmax | ssp585 | 2050 | served | no (404) | no (404) | served |
| tasmin | ssp585 | 2050 | served | no (404) | no (404) | served |
| pr | ssp585 | 2050 | served | served | no (404) | served |

### Do the file versions give different annual values?

Annual values from each later version against version 1.0, in the box (reference reader only; crc-sdk is not involved).

| Recipe | Scenario | Year | Version | Cells | Cells that differ | Largest difference |
| --- | --- | --- | --- | --- | --- | --- |
| rx1day | historical | 2014 | 1.1 | 2,158 | 15 | 0.081 |
| rx1day | historical | 2014 | 2.0 | 2,158 | 15 | 0.081 |
| txx | historical | 2014 | 2.0 | 2,158 | 0 | 0 |
| rx1day | ssp585 | 2050 | 1.1 | 2,158 | 42 | 0.843 |
| rx1day | ssp585 | 2050 | 2.0 | 2,158 | 42 | 0.843 |
| txx | ssp585 | 2050 | 2.0 | 2,158 | 0 | 0 |

Assessed on one model and member (ACCESS-CM2, r1i1p1f1), the Texas box (2,332 grid cells, 2,158 on land), 2014 of the historical run and 2050 of ssp585. The scenario and version lists are hard-coded upstream and are not read by the detector. Each result is one model and one member, not an ensemble. Ocean cells carry no value. The licence written in the files differs by version (CC-BY-SA 4.0 in 1.0, CC-BY 4.0 in 1.1) while NASA states the archive is CC0.

## What the framework does (transformation statement)

| Step | What crc-sdk does | Code | Outcome |
| --- | --- | --- | --- |
| files | Reads one NetCDF file per variable, model, scenario, member and year from NASA's archive on AWS, by range requests. Nothing is cached and no checksum is taken. | crc_sdk/workflows/nex.py:33, 90-100, 139-141; docs/sources/cmip6.md:75-77 | **confirmed** |
| versions | Reads exactly the file version asked for (1.0 has no suffix in the file name; later ones end in `_v<version>`). A version NASA does not have fails; another is never substituted. | crc_sdk/workflows/nex.py:96, 130-132; docs/sources/cmip6.md:73-74 | **confirmed** |
| versions-offered | Accepts the file versions 1.0, 1.1 and 1.2. | crc_sdk/workflows/nex.py:84-85 | **differs** |
| identity | Checks that the file's own attributes name the model, scenario, member and version that were asked for. | crc_sdk/workflows/nex.py:142-153 | **confirmed** |
| licence | Reads the model licence written in the file and keeps it beside NASA's archive licence (CC0-1.0). Warns when the file's licence is not CC0; refuses it when `strict_licence` is set. | crc_sdk/workflows/nex.py:154-165, 227-229 | **confirmed**. The warning was seen on every file read. `strict_licence=True` was not run. |
| units-rain | Requires precipitation to be declared in kg m-2 s-1 and multiplies it by 86,400 to give millimetres per day. | crc_sdk/providers/cmip6.py:606, 636-660, 952; crc_sdk/workflows/nex.py:179-183 | **confirmed** |
| units-temperature | Requires temperature to be declared in kelvin (K) and subtracts 273.15 to give degrees Celsius. | crc_sdk/providers/cmip6.py:603, 611-634, 952; crc_sdk/workflows/nex.py:179-183 | **differs** |
| time | Requires the daily time axis to be strictly increasing and to lie within the requested year, in the file's own calendar, and places each day by its date. | crc_sdk/workflows/nex.py:184-194; crc_sdk/providers/cmip6.py:813-828 | **confirmed**. The files read use the proleptic Gregorian calendar with 365 days and no gap. Other calendars and gaps were exercised only in the offline tests. |
| area | Selects the grid cells whose centres lie inside the box grown by half a cell on every side, with longitudes brought to -180..180 and ordered west to east. A box narrower than one cell is widened to two cells. | crc_sdk/connectors/blocks.py:175-234 | **confirmed**. Confirmed for a box of 44 by 53 cells. A box narrower than one cell and a box across the 180 degree meridian were not run. |
| missing | Treats the file's fill value as missing. | crc_sdk/providers/cmip6.py:762, 823-825, 835-866 | **confirmed** |
| completeness | Gives a grid cell a value only when at least 90 per cent of the year's days are present. | crc_sdk/providers/cmip6.py:621; crc_sdk/connectors/blocks.py:454-455, 484 | **confirmed**. In NASA's files a cell has either every day or none (ocean), so the 90 per cent line itself was crossed only in the offline tests. |
| statistic-rain | `rx1day` is the largest daily value of the year. `rx5day` is the largest sum over five consecutive days that lie within the year; windows do not reach into the neighbouring years. | crc_sdk/providers/cmip6.py:636-660; crc_sdk/connectors/blocks.py:467-483 | **confirmed** |
| statistic-temperature | `txx` is the highest daily maximum of the year and `tnn` the lowest daily minimum. | crc_sdk/providers/cmip6.py:611-634; crc_sdk/connectors/blocks.py:479-483 | **not checked**. Cannot be checked at crc-sdk 0.11.1, where both recipes fail (CRC-001-NEX). On a local clone that carries the fix, every cell agrees with the recomputation (checks `annual-fixed-clone`); that is not a statement about a released version. |
| output | Returns one row per grid cell that has a value, at the cell's centre, south to north and west to east. No distribution is fitted. | crc_sdk/workflows/nex.py:202-232 | **confirmed** |
| labels | Labels every row with the unit, recipe, model, scenario, member, grid, version, calendar (under one name per calendar: `365_day` is written `noleap`), the file's address, the retrieval time, both licences and an attribution. | crc_sdk/workflows/nex.py:211-231 | **confirmed** |

## Checks

### annual

Every grid cell of the box: the annual value recomputed in Python from the whole NASA file, against the rows crc-sdk returns, in order. Steps: files, identity, time, area, missing, completeness, output, units-rain, statistic-rain. Tolerance: numbers: within 1e-09; order: identical.

| Check | Outcome | Result |
| --- | --- | --- |
| annual[rx1day historical 2014 v1.0] | confirmed | 2,158 cells with a value of 2,332 in the box, against 2,158; 0 values differ; largest difference 0.0e+00 |
| annual[rx5day historical 2014 v1.0] | confirmed | 2,158 cells with a value of 2,332 in the box, against 2,158; 0 values differ; largest difference 0.0e+00 |
| annual[rx1day historical 2014 v1.1] | confirmed | 2,158 cells with a value of 2,332 in the box, against 2,158; 0 values differ; largest difference 0.0e+00 |
| annual[rx1day ssp585 2050 v1.0] | confirmed | 2,158 cells with a value of 2,332 in the box, against 2,158; 0 values differ; largest difference 0.0e+00 |
| annual[rx5day ssp585 2050 v1.0] | confirmed | 2,158 cells with a value of 2,332 in the box, against 2,158; 0 values differ; largest difference 0.0e+00 |
| annual[rx1day ssp585 2050 v1.1] | confirmed | 2,158 cells with a value of 2,332 in the box, against 2,158; 0 values differ; largest difference 0.0e+00 |
| annual[rx5day historical 2014 v1.1] | confirmed | 2,158 cells with a value of 2,332 in the box, against 2,158; 0 values differ; largest difference 0.0e+00 |

### labels

The labels on crc-sdk's rows against the request and the file's own attributes: unit, recipe, model, scenario, member, version, calendar, address, both licences; and whether a warning is raised when the file's licence is not CC0. Steps: labels, licence. Tolerance: labels: identical text.

| Check | Outcome | Result |
| --- | --- | --- |
| labels[rx1day historical 2014 v1.0] | confirmed | 0 labels wrong; licence in the file CC-BY-SA 4.0; warning raised: yes; checksum column: no |
| labels[rx5day historical 2014 v1.0] | confirmed | 0 labels wrong; licence in the file CC-BY-SA 4.0; warning raised: yes; checksum column: no |
| labels[rx1day historical 2014 v1.1] | confirmed | 0 labels wrong; licence in the file CC-BY 4.0; warning raised: yes; checksum column: no |
| labels[rx1day ssp585 2050 v1.0] | confirmed | 0 labels wrong; licence in the file CC-BY-SA 4.0; warning raised: yes; checksum column: no |
| labels[rx5day ssp585 2050 v1.0] | confirmed | 0 labels wrong; licence in the file CC-BY-SA 4.0; warning raised: yes; checksum column: no |
| labels[rx1day ssp585 2050 v1.1] | confirmed | 0 labels wrong; licence in the file CC-BY 4.0; warning raised: yes; checksum column: no |
| labels[rx5day historical 2014 v1.1] | confirmed | 0 labels wrong; licence in the file CC-BY 4.0; warning raised: yes; checksum column: no |

### units

The unit the file declares against the unit crc-sdk requires for the recipe; a file that declares the required unit must be accepted. Steps: units-temperature. Tolerance: unit: identical text.

| Check | Outcome | Result |
| --- | --- | --- |
| units[txx historical 2014 v1.0] | differs | the file declares 'K', the recipe requires 'K'; crc-sdk raises: ValueError: 'tasmax' is published in "b'K'", but recipe 'txx' converts from 'K'; the conversion would be wrong |
| units[tnn historical 2014 v1.0] | differs | the file declares 'K', the recipe requires 'K'; crc-sdk raises: ValueError: 'tasmin' is published in "b'K'", but recipe 'tnn' converts from 'K'; the conversion would be wrong |
| units[txx ssp585 2050 v1.0] | differs | the file declares 'K', the recipe requires 'K'; crc-sdk raises: ValueError: 'tasmax' is published in "b'K'", but recipe 'txx' converts from 'K'; the conversion would be wrong |
| units[tnn ssp585 2050 v1.0] | differs | the file declares 'K', the recipe requires 'K'; crc-sdk raises: ValueError: 'tasmin' is published in "b'K'", but recipe 'tnn' converts from 'K'; the conversion would be wrong |

### annual-fixed-clone

Every grid cell of the box: the annual value recomputed in Python from the whole NASA file, against the rows the local clone with the fix returns, in order. Steps: . Tolerance: numbers: within 1e-09; order: identical.

| Check | Outcome | Result |
| --- | --- | --- |
| annual-fixed-clone[txx historical 2014 v1.0] | confirmed | 2,158 cells with a value of 2,332 in the box, against 2,158; 0 values differ; largest difference 0.0e+00 |
| annual-fixed-clone[tnn historical 2014 v1.0] | confirmed | 2,158 cells with a value of 2,332 in the box, against 2,158; 0 values differ; largest difference 0.0e+00 |
| annual-fixed-clone[txx ssp585 2050 v1.0] | confirmed | 2,158 cells with a value of 2,332 in the box, against 2,158; 0 values differ; largest difference 0.0e+00 |
| annual-fixed-clone[tnn ssp585 2050 v1.0] | confirmed | 2,158 cells with a value of 2,332 in the box, against 2,158; 0 values differ; largest difference 0.0e+00 |

### missing-version

Ask crc-sdk for rx1day historical 2014 v1.2, which NASA does not have (HTTP 404): crc-sdk must raise and return no rows. Steps: versions. Tolerance: behaviour: an error and no rows.

| Check | Outcome | Result |
| --- | --- | --- |
| missing-version | confirmed | crc-sdk raises (FileNotFoundError: https://nex-gddp-cmip6.s3.us-west-2.amazonaws.com/NEX-GDDP-CMIP6/ACCESS-CM2/historical/r1i1p1f1/pr/pr); 0 rows |

### versions-served

For each variable and year assessed, ask NASA (HEAD) for file versions 1.0, 1.1, 1.2, 2.0 and compare with the versions crc-sdk accepts. Steps: versions-offered. Tolerance: versions: every version served can be requested.

| Check | Outcome | Result |
| --- | --- | --- |
| versions-served | differs | served by NASA but not accepted by crc-sdk: 2.0 |

## Inputs

| Role | File | SHA-256 | Retrieved |
| --- | --- | --- | --- |
| reference download | pr_day_ACCESS-CM2_historical_r1i1p1f1_gn_2014.nc | 50fe17b1b7faff5a385742eb4ccc1733251a37990ddf8e1d406ab9d0b25afdfa | 2026-11-12T04:37:44Z |
| crc-sdk answer (range requests) | pr_day_ACCESS-CM2_historical_r1i1p1f1_gn_2014.nc |  |  |
| reference download | tasmax_day_ACCESS-CM2_historical_r1i1p1f1_gn_2014.nc | 847806acd3790326d7cd62e68c5488dd6fbb1b5785d5deaad58affe43825cc72 | 2026-11-12T04:37:44Z |
| crc-sdk answer (range requests) | tasmax_day_ACCESS-CM2_historical_r1i1p1f1_gn_2014.nc |  |  |
| reference download | tasmin_day_ACCESS-CM2_historical_r1i1p1f1_gn_2014.nc | d1e0011ca0fd83b37a33640ac66a5e1ef7ffb5a75c7b1dc737a6f9822bc30bfc | 2026-11-12T04:37:44Z |
| crc-sdk answer (range requests) | tasmin_day_ACCESS-CM2_historical_r1i1p1f1_gn_2014.nc |  |  |
| reference download | pr_day_ACCESS-CM2_historical_r1i1p1f1_gn_2014_v1.1.nc | 0419d8861af018b5dd9a2aa2b77acd07f4ff5f7fc6d9b25d29432ca1b73c2333 | 2026-11-12T04:37:44Z |
| crc-sdk answer (range requests) | pr_day_ACCESS-CM2_historical_r1i1p1f1_gn_2014_v1.1.nc |  |  |
| reference download | pr_day_ACCESS-CM2_ssp585_r1i1p1f1_gn_2050.nc | ac8d265c83b962d87cac74d15851a0895caf075c61c8a47d1f41befca43b6529 | 2026-11-12T04:38:55Z |
| crc-sdk answer (range requests) | pr_day_ACCESS-CM2_ssp585_r1i1p1f1_gn_2050.nc |  |  |
| reference download | tasmax_day_ACCESS-CM2_ssp585_r1i1p1f1_gn_2050.nc | 92f77b3e5f95f71dc79c4638295db401bd3ac460113b96c1246ca41a3f5abc5d | 2026-11-12T04:38:13Z |
| crc-sdk answer (range requests) | tasmax_day_ACCESS-CM2_ssp585_r1i1p1f1_gn_2050.nc |  |  |
| reference download | tasmin_day_ACCESS-CM2_ssp585_r1i1p1f1_gn_2050.nc | ac4c70727bdc0b183b2765d53c6fe642097adb37067f0a308fb5bf6dc5caebe4 | 2026-11-12T04:38:35Z |
| crc-sdk answer (range requests) | tasmin_day_ACCESS-CM2_ssp585_r1i1p1f1_gn_2050.nc |  |  |
| reference download | pr_day_ACCESS-CM2_ssp585_r1i1p1f1_gn_2050_v1.1.nc | 26c959a88b8cca29a1bb3fcae5cc11832d215789f7a8ec2b681a857e53164108 | 2026-11-12T04:38:57Z |
| crc-sdk answer (range requests) | pr_day_ACCESS-CM2_ssp585_r1i1p1f1_gn_2050_v1.1.nc |  |  |
| crc-sdk answer | pr_day_ACCESS-CM2_historical_r1i1p1f1_gn_2014_v1.2.nc |  |  |
| publisher listing (HEAD) | NEX-GDDP-CMIP6 |  |  |

## Findings

| Id | Kind | Finding | Basis | Status |
| --- | --- | --- | --- | --- |
| CRC-001-NEX | defect | Temperature recipes (txx, tnn) fail on real NEX files | reproduced | open |
| CRC-012-NEX | observation | NASA serves files of version 2.0, which cannot be requested | reproduced | open |

Details are in [the inventory](../inventory.md#findings).

## What this does not cover

- A `confirmed` outcome holds for these files, these options and crc-framework 0.6.0, crc-sdk 0.11.1.
- Verification says nothing about whether the publisher's values are right.
- Validation (fitness for a stated use) is not assessed.
