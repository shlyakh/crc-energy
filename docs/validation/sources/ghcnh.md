# NOAA GHCNh station temperatures: assessment

Generated from the records of the run of 2026-11-12T04:34:47Z against crc-framework 0.6.0, crc-sdk 0.11.1. **Draft: not yet reviewed.**
Do not edit: change the source file or re-run the assessment and rebuild.

- **Purpose (the framework's documentation):** Annual extremes of hourly station temperature, fitted per station, as a local check on gridded curves.
- **Publisher:** NOAA NCEI · https://noaa-ghcnh-pds.s3.amazonaws.com/hourly/access/by-year
- **Entry points:** `HazardDataset.ghcnh`
- **Status:** exploration assessed, verification assessed, validation not assessed
- **Options, recipe:** assessed temperature_max, temperature_min; not assessed none

## Exploration

### From stations to curves

Selection: first 40 USW stations of crc-sdk's catalogue selection for the box, years 2000 to 2024. Counted from NOAA's files by the reference reader.

| Stage | Count |
| --- | --- |
| Stations crc-sdk's catalogue selects in the box | 699 |
| Stations assessed | 40 |
| Station-years requested | 1,000 |
| Station-years NOAA has a file for | 592 |
| Station-years complete (enough valid days) | 427 |
| Stations with at least 15 complete years (the explorer's setting) | 8 |
| Stations with at least 20 complete years (crc-sdk's default) | 0 |

### Hourly reports and the rules that exclude them

A rule with no row excluded nothing in these files.

| Reports | Count | Share |
| --- | --- | --- |
| All reports | 13,885,491 | 100 % |
| Accepted | 13,703,240 | 98.69 % |
| Excluded: no temperature | 174,166 | 1.2543 % |
| Excluded: outside the physical range | 7 | 0.0001 % |
| Excluded: quality code not accepted | 8,078 | 0.0582 % |

### Stations

| Station | Name | First year | Last year | Years with a file | Complete years | Reports | Accepted |
| --- | --- | --- | --- | --- | --- | --- | --- |
| USW00000127 | BEEVILLE MUNI AP | 2007 | 2024 | 18 | 13 | 433,029 | 98.9 % |
| USW00000129 | HEREFORD MUNI AP | 2007 | 2024 | 18 | 16 | 448,189 | 99.4 % |
| USW00000130 | PLEASANTON MUNI AP | 2007 | 2024 | 18 | 17 | 445,569 | 99.4 % |
| USW00000134 | KICKAPOO DOWNTOWN AP | 2007 | 2024 | 18 | 15 | 434,266 | 99.3 % |
| USW00000137 | ANGEL FIRE AP | 2008 | 2024 | 17 | 16 | 437,893 | 99.8 % |
| USW00000166 | LAGO VISTA RUSTY ALLEN AP | 2008 | 2024 | 17 | 15 | 414,066 | 99.8 % |
| USW00000172 | STAN STAMPER MUNI AP | 2012 | 2024 | 13 | 7 | 283,064 | 99.7 % |
| USW00000175 | RUSK COUNTY AP | 2008 | 2024 | 17 | 13 | 396,482 | 99.5 % |
| USW00000176 | STEPHENS COUNTY AP | 2008 | 2024 | 17 | 16 | 413,350 | 99.9 % |
| USW00000177 | CASTROVILLE MUNI AIRPORT | 2013 | 2024 | 12 | 8 | 286,720 | 98.1 % |
| USW00000181 | ZAPATA COUNTY AP | 2008 | 2024 | 17 | 12 | 400,840 | 99.6 % |
| USW00000188 | HOUSTON DUNN HELISTOP | 2008 | 2024 | 17 | 12 | 387,224 | 99.8 % |
| USW00000208 | HOUSTON EXECUTIVE AP | 2009 | 2024 | 16 | 14 | 386,976 | 97.1 % |
| USW00000209 | BOWIE MUNI AP | 2013 | 2024 | 12 | 11 | 303,444 | 99.8 % |
| USW00000213 | PAMPA MESA VISTA AP | 2009 | 2024 | 16 | 9 | 387,369 | 98.1 % |
| USW00000214 | STIGLER REGIONAL AP | 2009 | 2024 | 16 | 12 | 374,971 | 98.6 % |
| USW00000215 | CLARENCE E PAGE MUNI AP | 2009 | 2024 | 16 | 13 | 372,096 | 99.5 % |
| USW00000223 | HOUSTON SOUTHWEST AP | 2009 | 2024 | 16 | 13 | 397,371 | 99.6 % |
| USW00000225 | HORSESHOE BAY RESORT AP | 2009 | 2024 | 16 | 15 | 399,038 | 99.8 % |
| USW00000229 | LAMPASAS AP | 2009 | 2024 | 16 | 10 | 354,386 | 99.7 % |
| USW00000230 | AUSTIN EXECUTIVE AP | 2009 | 2024 | 16 | 14 | 390,321 | 98.9 % |
| USW00000239 | OZONA MUNI AP | 2009 | 2024 | 16 | 13 | 381,040 | 100.0 % |
| USW00000246 | E BREAKS OIL PLATFORM | 2009 | 2022 | 14 | 2 | 260,614 | 95.7 % |
| USW00000247 | GUNNISON OIL PLATFORM | 2009 | 2024 | 16 | 8 | 354,281 | 92.9 % |
| USW00000255 | SABINE OIL PLATFORM | 2010 | 2019 | 10 | 2 | 178,203 | 97.0 % |
| USW00000259 | GALVESTON 424 OIL PLATFORM | 2010 | 2016 | 7 | 1 | 106,325 | 98.6 % |
| USW00000260 | HIGH IS 376 | 2010 | 2020 | 11 | 3 | 244,388 | 92.5 % |
| USW00000262 | MUSTANG IS A85A | 2010 | 2020 | 11 | 6 | 237,922 | 97.6 % |
| USW00000263 | BOERNE STAGE FIELD AP | 2013 | 2024 | 12 | 11 | 303,415 | 99.4 % |
| USW00000270 | FAITH RCH AP | 2010 | 2024 | 15 | 7 | 313,231 | 96.0 % |
| USW00000272 | BOOMVANG SPAR OIL PLATFORM | 2010 | 2024 | 15 | 7 | 345,175 | 98.5 % |
| USW00000276 | COLEMAN MUNI AP | 2010 | 2024 | 15 | 14 | 365,044 | 99.9 % |
| USW00000306 | HIGH IS 179 OIL PLATFORM | 2010 | 2020 | 11 | 6 | 228,984 | 97.4 % |
| USW00000308 | N PADRE IS | 2010 | 2014 | 5 | 2 | 88,484 | 98.8 % |
| USW00000313 | BEAUMONT MUNI AP | 2011 | 2024 | 14 | 9 | 350,602 | 97.9 % |
| USW00000349 | ANDREWS COUNTY AP | 2013 | 2024 | 12 | 10 | 298,309 | 99.7 % |
| USW00000351 | CAMERON MUNI AP | 2012 | 2024 | 13 | 11 | 328,174 | 98.9 % |
| USW00000357 | HAMILTON MUNI AP | 2008 | 2024 | 17 | 14 | 426,836 | 99.9 % |
| USW00000362 | GATESVILLE MUNI AP | 2004 | 2024 | 21 | 17 | 504,758 | 98.8 % |
| USW00000364 | THOMAS P STAFFORD AP | 2007 | 2024 | 18 | 13 | 423,042 | 97.9 % |

Assessed on the stations the Texas data explorer uses: the first forty USW stations in the Texas box, 2000 to 2024. These are small airports whose records begin around 2005, so 592 of 1,000 station-years have a file, 8 stations reach 15 complete years and none reaches crc-sdk's default of 20. Days are UTC days: in Texas a UTC day runs from the local evening to the next. The values are extremes of sampled hourly temperature, not of an instrument's daily maximum and minimum.

## What the framework does (transformation statement)

| Step | What crc-sdk does | Code | Outcome |
| --- | --- | --- | --- |
| files | Reads one Parquet file per station and year, `<root>/<year>/parquet/GHCNh_<station>_<year>.parquet`. A file NOAA does not have (HTTP 404) gives a year with no value; other errors stop the run. | crc_sdk/providers/ghcnh.py:143-158 | **confirmed** |
| columns | Reads eight columns by range requests tied to the file's ETag: STATION, DATE, LATITUDE, LONGITUDE, ELEVATION, temperature and its quality and source codes. Hourly files are not kept. | crc_sdk/providers/ghcnh.py:35-44, 162-168 | **confirmed** |
| time | Reads DATE as a timestamp and keeps the reports of the requested station whose timestamp falls in the requested year. A report whose DATE cannot be read is dropped. | crc_sdk/providers/ghcnh.py:107; crc_sdk/providers/stations.py:31-33 | **confirmed** |
| quality | Uses a temperature when its quality code is blank, or is 1 from one of fourteen listed source codes, or is 5 from one of eight listed source codes. Any other code excludes the report's value. | crc_sdk/providers/ghcnh.py:45-46, 55, 110-120 | **confirmed**. In these files the excluded reports carried other quality codes. No report had code 1 or 5 from an unlisted source, so on NOAA's data the source lists were not put to the test; the offline tests exercise them on constructed files. |
| range | Uses a temperature only if it is a finite number between -93.2 and 61.8 degrees Celsius inclusive. | crc_sdk/providers/ghcnh.py:121-122 | **confirmed** |
| units | Takes the temperature in degrees Celsius as published. No unit is converted; the output is labelled degC. | crc_sdk/providers/ghcnh.py:123; crc_sdk/workflows/stations.py:654 | **confirmed** |
| day | Groups reports by UTC calendar day. For each day it counts all reports, the accepted reports and the distinct clock hours that hold an accepted report, and takes the lowest and highest accepted temperature. | crc_sdk/providers/stations.py:34-42 | **confirmed** |
| valid-day | Counts a day as valid when at least 18 distinct hours hold an accepted report (three quarters of 24, rounded up). Several reports in one hour count once. | crc_sdk/workflows/stations.py:518-523 | **confirmed** |
| valid-year | Counts a year as complete when at least 90 per cent of its days are valid (329 of 365, 330 of 366). | crc_sdk/workflows/stations.py:524-527 | **confirmed** |
| annual-value | For a complete year, takes the highest daily maximum (`temperature_max`) or the lowest daily minimum (`temperature_min`) over the valid days only. An incomplete year has no value. Values on days that are not valid are ignored. | crc_sdk/workflows/stations.py:528-533 | **confirmed** |
| location | Places the station at the lowest latitude and lowest longitude reported in the year, with the lowest reported elevation (-999.9 read as missing). Refuses a station whose coordinates move by more than 0.05 degrees within a year. | crc_sdk/providers/ghcnh.py:108-109; crc_sdk/workflows/stations.py:499-517 | **confirmed**. No station in these files moved or lacked coordinates, so the refusal was not seen on NOAA's data; the offline tests exercise it on constructed files. |
| minimum-years | Fits a curve for a station only when it has at least the policy's minimum of complete years (20 by default; 15 in the Texas data explorer). The minimum is applied per station. | crc_sdk/workflows/stations.py:616-621, 670 | **confirmed** |
| family | Fits a generalized extreme value distribution to annual maxima and a lower-tail Gumbel distribution to annual minima, both by L-moments. | crc_sdk/workflows/stations.py:301-303; docs/sources/stations.md:67-68 | **confirmed**. Confirmed here: the family named in the output. The fit itself (parameters, method, behaviour on short records) is not checked; it belongs to validation (phase V7). |
| provenance | Writes the licence (CC0-1.0), an attribution text, the latest retrieval time, a checksum over the cached daily files and the request into the curve file's metadata. | crc_sdk/workflows/stations.py:657-667; crc_sdk/providers/ghcnh.py:25-30 | **confirmed** |

## Checks

### annual

Every station-year: the annual value and its audit counts recomputed in Python from NOAA's Parquet file (read without crc-sdk or pyarrow), against crc-sdk's annual_extremes() table, field by field. Steps: files, columns, time, quality, range, units, day, valid-day, valid-year, annual-value, location. Tolerance: values: exact equality, numbers included.

| Check | Outcome | Result |
| --- | --- | --- |
| annual[temperature_max] | confirmed | 1,000 station-years against 1,000; 11,000 values compared, 0 differ; 592 have a file, 427 are complete |
| annual[temperature_min] | confirmed | 1,000 station-years against 1,000; 11,000 values compared, 0 differ; 592 have a file, 427 are complete |

### second-format

A seeded sample of station-years recomputed from NOAA's pipe-separated file with the standard library only, against crc-sdk's annual_extremes() table. Steps: files, columns, time, quality, range, units, day, valid-day, valid-year, annual-value, location. Tolerance: values: exact equality, numbers included.

| Check | Outcome | Result |
| --- | --- | --- |
| second-format[temperature_max] | confirmed | 8 station-years against 8; 88 values compared, 0 differ |
| second-format[temperature_min] | confirmed | 8 station-years against 8; 88 values compared, 0 differ |

### curve-stations

Stations that receive a fitted curve from crc-sdk against the stations whose recomputed series has at least the minimum number of complete years; and the distribution family named in the output. Steps: minimum-years, family. Tolerance: family: as documented; stations: identical sets.

| Check | Outcome | Result |
| --- | --- | --- |
| curve-stations[temperature_max] | confirmed | 8 stations with a curve, 8 expected at 15 complete years; family genextreme |
| curve-stations[temperature_min] | confirmed | 8 stations with a curve, 8 expected at 15 complete years; family gumbel_l |

### provenance

Licence, attribution, retrieval time, checksum, unit and probability convention in the metadata of the curve file crc-sdk writes. Steps: provenance, units. Tolerance: fields: all present; licence, unit and convention as documented.

| Check | Outcome | Result |
| --- | --- | --- |
| provenance[temperature_max] | confirmed | 5 of 5 provenance fields present; licence CC0-1.0; unit degC; annual_exceedance |
| provenance[temperature_min] | confirmed | 5 of 5 provenance fields present; licence CC0-1.0; unit degC; annual_exceedance |

## Inputs

| Role | File | SHA-256 | Retrieved |
| --- | --- | --- | --- |
| reference download (Parquet) | by-year (592 files) | 0f445170ef39f1b6557ff6180c85111faf3fb394817bc6a07a3ab70852954cbf | 2026-11-12T04:23:27Z |
| crc-sdk annual table | by-year |  |  |
| reference download (pipe-separated) | by-year (8 files) | 335618cc39cb4e85a4ec7009f9383981ffa475fbe3989302893ac7c34df01522 | 2026-11-12T04:24:04Z |

## Findings

None.

## What this does not cover

- A `confirmed` outcome holds for these files, these options and crc-framework 0.6.0, crc-sdk 0.11.1.
- Verification says nothing about whether the publisher's values are right.
- Validation (fitness for a stated use) is not assessed.
