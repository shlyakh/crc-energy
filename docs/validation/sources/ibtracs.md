# IBTrACS tropical cyclone tracks: assessment

Generated from the records of the run of 2026-11-12T23:31:55Z against crc-framework 0.6.0, crc-sdk 0.11.1. **Draft: not yet reviewed.**
Do not edit: change the source file or re-run the assessment and rebuild.

- **Purpose (the framework's documentation):** Best-track points of tropical cyclones by basin, as published, for inspection. Not asset winds or return-period curves.
- **Publisher:** NOAA NCEI · https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv
- **Entry points:** `IBTrACSPlan`
- **Status:** exploration assessed, verification assessed, validation not assessed
- **Options, subset:** assessed ALL, EP, NA, NI, SA, SI, SP, WP, last3years, since1980; not assessed active

## Exploration

### What is in the publisher's files

Counted from NOAA's files by the reference reader.

| File | Rows | Storms | Seasons | Columns | Values missing | Last modified by publisher |
| --- | --- | --- | --- | --- | --- | --- |
| ALL | 730,608 | 13,635 | 1842 to 2027 | 174 | 82.4 % | Thu, 12 Nov 2026 10:05:57 GMT |
| EP | 101,582 | 1,735 | 1876 to 2026 | 174 | 80.5 % | Thu, 12 Nov 2026 10:06:01 GMT |
| NA | 128,186 | 2,312 | 1851 to 2026 | 174 | 85.0 % | Thu, 12 Nov 2026 10:06:08 GMT |
| NI | 62,910 | 1,861 | 1842 to 2026 | 174 | 84.5 % | Thu, 12 Nov 2026 10:06:10 GMT |
| SA | 119 | 3 | 2004 to 2011 | 174 | 84.4 % | Thu, 12 Nov 2026 10:06:10 GMT |
| SI | 171,095 | 2,890 | 1848 to 2027 | 174 | 82.9 % | Thu, 12 Nov 2026 10:06:18 GMT |
| SP | 77,223 | 1,258 | 1897 to 2027 | 174 | 82.0 % | Thu, 12 Nov 2026 10:06:36 GMT |
| WP | 249,317 | 4,258 | 1884 to 2026 | 174 | 80.2 % | Thu, 12 Nov 2026 10:06:46 GMT |
| last3years | 25,013 | 411 | 2023 to 2027 | 174 | 77.8 % | Thu, 12 Nov 2026 10:06:02 GMT |
| since1980 | 312,394 | 5,017 | 1980 to 2027 | 174 | 79.8 % | Thu, 12 Nov 2026 10:06:32 GMT |

Longitudes in NOAA's files are not wrapped to -180..180 (values up to 266.9 occur where a track crosses the date line); crc-sdk passes them through as strings. SEASON runs to 2027 because southern-hemisphere seasons are labelled by their second year. About four values in five are missing: most columns belong to one agency each.

## What the framework does (transformation statement)

| Step | What crc-sdk does | Code | Outcome |
| --- | --- | --- | --- |
| address | Requests `<root>/ibtracs.<subset>.list.v04r01.csv`, with the subset spelled exactly as one of the eleven names crc-sdk accepts. | crc_sdk/workflows/ibtracs.py:27-41, 70-71 | **differs** |
| bytes | Saves the response unchanged as `source.csv` and records its SHA-256. A download shorter than the announced length is refused. | crc_sdk/workflows/ibtracs.py:113-128, 154 | **confirmed** |
| header | Reads line 1 as column names and line 2 as units. Requires the columns SID, SEASON and ISO_TIME. The units go to the manifest only; they are not in the data. | crc_sdk/workflows/ibtracs.py:129-147, 167-168 | **confirmed** |
| columns | Keeps every column, in the file's order, under NOAA's names. | crc_sdk/workflows/ibtracs.py:169, 193 | **confirmed** |
| strings | Delivers every value as a string. Nothing is parsed into a number or a date, and no unit is converted. | crc_sdk/workflows/ibtracs.py:198-200 | **confirmed** |
| trim | Removes leading and trailing whitespace from every value. | crc_sdk/workflows/ibtracs.py:215-218 | **confirmed** |
| null | Turns a value that is empty after trimming into null. NOAA marks a missing value with a single space. | crc_sdk/workflows/ibtracs.py:233-241 | **confirmed** |
| rows | Keeps every data row in the file's order. Rows are not dropped, merged, sorted or de-duplicated. | crc_sdk/workflows/ibtracs.py:171-183, 191-212 | **confirmed** |
| storms | `for_storms(ids)` keeps the rows whose SID is in the list. These are track points, not complete storms across basin files. | crc_sdk/workflows/ibtracs.py:73-77, 219-222 | **confirmed** |
| seasons | `years(a, b)` keeps the rows whose SEASON, read as an integer, lies in a..b inclusive. SEASON is NOAA's season label, not the calendar year of the point. | crc_sdk/workflows/ibtracs.py:79-82, 223-231 | **confirmed** |
| provenance | Writes a manifest beside the snapshot with the address, version, subset, SHA-256, retrieval time, ETag, Last-Modified, units, a terms address and a citation. The batches themselves carry no metadata. | crc_sdk/workflows/ibtracs.py:139-155 | **confirmed** |
| reuse | In `reuse` mode (the default) a cached snapshot is served without asking NOAA whether the file has changed. NOAA rewrites these files in place. | crc_sdk/workflows/_remote.py:91-115; docs/sources/observations.md:42 | **not checked**. Read in the code, not shown on data: showing it needs NOAA to change a file between two runs. Left to monitoring (phase V4). |

## Checks

### address

For every subset name crc-sdk accepts, request the address crc-sdk builds (HEAD) and record NOAA's answer; list the CSV files in NOAA's directory. Steps: address. Tolerance: http_status: 200 for every subset.

| Check | Outcome | Result |
| --- | --- | --- |
| address | differs | 10 of 11 accepted names are served by the publisher; not served: active (HTTP 404) |

### bytes

SHA-256 of the file crc-sdk cached against SHA-256 of an independent download of the same address; and against the checksum crc-sdk wrote in its manifest. Steps: bytes. Tolerance: bytes: identical.

| Check | Outcome | Result |
| --- | --- | --- |
| bytes[ALL] | confirmed | 333,271,989 bytes; SHA-256 b67770d3d12e… on both sides |
| bytes[EP] | confirmed | 47,312,133 bytes; SHA-256 9e74f5e88338… on both sides |
| bytes[NA] | confirmed | 57,593,323 bytes; SHA-256 666681be5b12… on both sides |
| bytes[NI] | confirmed | 27,907,168 bytes; SHA-256 137d896f68f8… on both sides |
| bytes[SA] | confirmed | 56,442 bytes; SHA-256 34ba989f7051… on both sides |
| bytes[SI] | confirmed | 77,976,781 bytes; SHA-256 e1af4a4927a5… on both sides |
| bytes[SP] | confirmed | 35,689,127 bytes; SHA-256 cd20fa2b45ed… on both sides |
| bytes[WP] | confirmed | 114,737,486 bytes; SHA-256 83bf4b39a266… on both sides |
| bytes[last3years] | confirmed | 11,849,967 bytes; SHA-256 deb60be5fd2b… on both sides |
| bytes[since1980] | confirmed | 145,369,034 bytes; SHA-256 2200fc253d53… on both sides |

### header

Line 1 of NOAA's file against the column names and order crc-sdk yields; the type of every column; line 2 against the units in crc-sdk's manifest. Steps: header, columns, strings. Tolerance: names: identical, in order; units: identical.

| Check | Outcome | Result |
| --- | --- | --- |
| header[ALL] | confirmed | 174 columns, 145 with a unit; types: string |
| header[EP] | confirmed | 174 columns, 145 with a unit; types: string |
| header[NA] | confirmed | 174 columns, 145 with a unit; types: string |
| header[NI] | confirmed | 174 columns, 145 with a unit; types: string |
| header[SA] | confirmed | 174 columns, 145 with a unit; types: string |
| header[SI] | confirmed | 174 columns, 145 with a unit; types: string |
| header[SP] | confirmed | 174 columns, 145 with a unit; types: string |
| header[WP] | confirmed | 174 columns, 145 with a unit; types: string |
| header[last3years] | confirmed | 174 columns, 145 with a unit; types: string |
| header[since1980] | confirmed | 174 columns, 145 with a unit; types: string |

### values

Every data row of NOAA's file, read with Python's csv module, trimmed, empty values made null, against every row crc-sdk yields, in order, value by value. Steps: columns, strings, trim, null, rows. Tolerance: values: exact equality of strings; null equals null only.

| Check | Outcome | Result |
| --- | --- | --- |
| values[ALL] | confirmed | 730,608 rows against 730,608; 127,125,792 values compared, 0 differ |
| values[EP] | confirmed | 101,582 rows against 101,582; 17,675,268 values compared, 0 differ |
| values[NA] | confirmed | 128,186 rows against 128,186; 22,304,364 values compared, 0 differ |
| values[NI] | confirmed | 62,910 rows against 62,910; 10,946,340 values compared, 0 differ |
| values[SA] | confirmed | 119 rows against 119; 20,706 values compared, 0 differ |
| values[SI] | confirmed | 171,095 rows against 171,095; 29,770,530 values compared, 0 differ |
| values[SP] | confirmed | 77,223 rows against 77,223; 13,436,802 values compared, 0 differ |
| values[WP] | confirmed | 249,317 rows against 249,317; 43,381,158 values compared, 0 differ |
| values[last3years] | confirmed | 25,013 rows against 25,013; 4,352,262 values compared, 0 differ |
| values[since1980] | confirmed | 312,394 rows against 312,394; 54,356,556 values compared, 0 differ |

### storm-filter

for_storms(ids) against the same selection made on NOAA's file: rows whose SID is in the list, whose SEASON is in the inclusive range, in file order. Steps: storms. Tolerance: values: exact equality of strings; null equals null only.

| Check | Outcome | Result |
| --- | --- | --- |
| storm-filter[ALL] | confirmed | 1,333 rows against 1,333; 231,942 values compared, 0 differ |
| storm-filter[EP] | confirmed | 1,400 rows against 1,400; 243,600 values compared, 0 differ |
| storm-filter[NA] | confirmed | 1,474 rows against 1,474; 256,476 values compared, 0 differ |
| storm-filter[NI] | confirmed | 926 rows against 926; 161,124 values compared, 0 differ |
| storm-filter[SA] | confirmed | 119 rows against 119; 20,706 values compared, 0 differ |
| storm-filter[SI] | confirmed | 1,281 rows against 1,281; 222,894 values compared, 0 differ |
| storm-filter[SP] | confirmed | 1,548 rows against 1,548; 269,352 values compared, 0 differ |
| storm-filter[WP] | confirmed | 1,519 rows against 1,519; 264,306 values compared, 0 differ |
| storm-filter[last3years] | confirmed | 1,351 rows against 1,351; 235,074 values compared, 0 differ |
| storm-filter[since1980] | confirmed | 1,646 rows against 1,646; 286,404 values compared, 0 differ |

### season-filter

years(a, b) against the same selection made on NOAA's file: rows whose SID is in the list, whose SEASON is in the inclusive range, in file order. Steps: seasons. Tolerance: values: exact equality of strings; null equals null only.

| Check | Outcome | Result |
| --- | --- | --- |
| season-filter[ALL] | confirmed | 172,641 rows against 172,641; 30,039,534 values compared, 0 differ |
| season-filter[EP] | confirmed | 35,353 rows against 35,353; 6,151,422 values compared, 0 differ |
| season-filter[NA] | confirmed | 26,952 rows against 26,952; 4,689,648 values compared, 0 differ |
| season-filter[NI] | confirmed | 23,159 rows against 23,159; 4,029,666 values compared, 0 differ |
| season-filter[SA] | confirmed | 96 rows against 96; 16,704 values compared, 0 differ |
| season-filter[SI] | confirmed | 39,966 rows against 39,966; 6,954,084 values compared, 0 differ |
| season-filter[SP] | confirmed | 40,832 rows against 40,832; 7,104,768 values compared, 0 differ |
| season-filter[WP] | confirmed | 121,980 rows against 121,980; 21,224,520 values compared, 0 differ |
| season-filter[last3years] | confirmed | 12,979 rows against 12,979; 2,258,346 values compared, 0 differ |
| season-filter[since1980] | confirmed | 79,050 rows against 79,050; 13,754,700 values compared, 0 differ |

### both-filters

for_storms(ids).years(a, b) against the same selection made on NOAA's file: rows whose SID is in the list, whose SEASON is in the inclusive range, in file order. Steps: storms, seasons. Tolerance: values: exact equality of strings; null equals null only.

| Check | Outcome | Result |
| --- | --- | --- |
| both-filters[ALL] | confirmed | 98 rows against 98; 17,052 values compared, 0 differ |
| both-filters[EP] | confirmed | 325 rows against 325; 56,550 values compared, 0 differ |
| both-filters[NA] | confirmed | 165 rows against 165; 28,710 values compared, 0 differ |
| both-filters[NI] | confirmed | 114 rows against 114; 19,836 values compared, 0 differ |
| both-filters[SA] | confirmed | 119 rows against 119; 20,706 values compared, 0 differ |
| both-filters[SI] | confirmed | 115 rows against 115; 20,010 values compared, 0 differ |
| both-filters[SP] | confirmed | 159 rows against 159; 27,666 values compared, 0 differ |
| both-filters[WP] | confirmed | 200 rows against 200; 34,800 values compared, 0 differ |
| both-filters[last3years] | confirmed | 1,351 rows against 1,351; 235,074 values compared, 0 differ |
| both-filters[since1980] | confirmed | 1,079 rows against 1,079; 187,746 values compared, 0 differ |

### provenance

Fields of the manifest crc-sdk writes beside the snapshot, and the metadata attached to the batches it yields. Steps: provenance. Tolerance: fields: all present and non-empty; no batch metadata, as stated.

| Check | Outcome | Result |
| --- | --- | --- |
| provenance[ALL] | confirmed | 8 of 8 stated fields present; licence field: no; batch metadata: none |
| provenance[EP] | confirmed | 8 of 8 stated fields present; licence field: no; batch metadata: none |
| provenance[NA] | confirmed | 8 of 8 stated fields present; licence field: no; batch metadata: none |
| provenance[NI] | confirmed | 8 of 8 stated fields present; licence field: no; batch metadata: none |
| provenance[SA] | confirmed | 8 of 8 stated fields present; licence field: no; batch metadata: none |
| provenance[SI] | confirmed | 8 of 8 stated fields present; licence field: no; batch metadata: none |
| provenance[SP] | confirmed | 8 of 8 stated fields present; licence field: no; batch metadata: none |
| provenance[WP] | confirmed | 8 of 8 stated fields present; licence field: no; batch metadata: none |
| provenance[last3years] | confirmed | 8 of 8 stated fields present; licence field: no; batch metadata: none |
| provenance[since1980] | confirmed | 8 of 8 stated fields present; licence field: no; batch metadata: none |

## Inputs

| Role | File | SHA-256 | Retrieved |
| --- | --- | --- | --- |
| reference download | ibtracs.ALL.list.v04r01.csv | b67770d3d12eae605d7bc0ef393d0c2164fd2180a76785b29bc9b5eec7d0fd5f | 2026-11-12T23:28:34Z |
| crc-sdk snapshot | ibtracs.ALL.list.v04r01.csv | b67770d3d12eae605d7bc0ef393d0c2164fd2180a76785b29bc9b5eec7d0fd5f | 2026-11-12T23:28:47.038675+00:00 |
| reference download | ibtracs.EP.list.v04r01.csv | 9e74f5e88338bde0a56a3378b7c1572aea3c08dd3087a9922c9e06ff25023af6 | 2026-11-12T23:29:45Z |
| crc-sdk snapshot | ibtracs.EP.list.v04r01.csv | 9e74f5e88338bde0a56a3378b7c1572aea3c08dd3087a9922c9e06ff25023af6 | 2026-11-12T23:29:47.849492+00:00 |
| reference download | ibtracs.NA.list.v04r01.csv | 666681be5b12caf5bad7a511bae5f6e5fa8b03789f7f6dd00ee2f0aaa41c2c97 | 2026-11-12T23:29:58Z |
| crc-sdk snapshot | ibtracs.NA.list.v04r01.csv | 666681be5b12caf5bad7a511bae5f6e5fa8b03789f7f6dd00ee2f0aaa41c2c97 | 2026-11-12T23:30:00.572174+00:00 |
| reference download | ibtracs.NI.list.v04r01.csv | 137d896f68f8dd12d365ec646d77b6e32128770847ac8ef37e1d0f662ac34915 | 2026-11-12T23:30:11Z |
| crc-sdk snapshot | ibtracs.NI.list.v04r01.csv | 137d896f68f8dd12d365ec646d77b6e32128770847ac8ef37e1d0f662ac34915 | 2026-11-12T23:30:12.905968+00:00 |
| reference download | ibtracs.SA.list.v04r01.csv | 34ba989f7051026707d2df9ca59070b1d4a2b5acf22f8f24a489fd2dd9ffd081 | 2026-11-12T23:30:18Z |
| crc-sdk snapshot | ibtracs.SA.list.v04r01.csv | 34ba989f7051026707d2df9ca59070b1d4a2b5acf22f8f24a489fd2dd9ffd081 | 2026-11-12T23:30:18.205625+00:00 |
| reference download | ibtracs.SI.list.v04r01.csv | e1af4a4927a5ae27625ddcb4ef3ad4180fe0854e94a91a5ce963b847fe478122 | 2026-11-12T23:30:21Z |
| crc-sdk snapshot | ibtracs.SI.list.v04r01.csv | e1af4a4927a5ae27625ddcb4ef3ad4180fe0854e94a91a5ce963b847fe478122 | 2026-11-12T23:30:23.980892+00:00 |
| reference download | ibtracs.SP.list.v04r01.csv | cd20fa2b45ed73f5a7bd5815a429c39336979fb40beff03b8b303c7ee17ebe3c | 2026-11-12T23:30:39Z |
| crc-sdk snapshot | ibtracs.SP.list.v04r01.csv | cd20fa2b45ed73f5a7bd5815a429c39336979fb40beff03b8b303c7ee17ebe3c | 2026-11-12T23:30:40.716530+00:00 |
| reference download | ibtracs.WP.list.v04r01.csv | 83bf4b39a266b327a80ad2e6a701afb730f3ed7e47cf07891ce207551950e569 | 2026-11-12T23:30:51Z |
| crc-sdk snapshot | ibtracs.WP.list.v04r01.csv | 83bf4b39a266b327a80ad2e6a701afb730f3ed7e47cf07891ce207551950e569 | 2026-11-12T23:30:55.826485+00:00 |
| reference download | ibtracs.last3years.list.v04r01.csv | deb60be5fd2b744c9ee45cac15b9efb060548ec73cf830ac7b53ddb7b340b3b5 | 2026-11-12T23:31:16Z |
| crc-sdk snapshot | ibtracs.last3years.list.v04r01.csv | deb60be5fd2b744c9ee45cac15b9efb060548ec73cf830ac7b53ddb7b340b3b5 | 2026-11-12T23:31:17.421072+00:00 |
| reference download | ibtracs.since1980.list.v04r01.csv | 2200fc253d536d7cdc60baef766c8c64c54ebbcd0cdb91bfe182d249cdf236f7 | 2026-11-12T23:31:24Z |
| crc-sdk snapshot | ibtracs.since1980.list.v04r01.csv | 2200fc253d536d7cdc60baef766c8c64c54ebbcd0cdb91bfe182d249cdf236f7 | 2026-11-12T23:31:30.395220+00:00 |

## Findings

| Id | Kind | Finding | Basis | Status |
| --- | --- | --- | --- | --- |
| CRC-010-IBT | defect | The subset "active" is accepted but NOAA has no file under that name | reproduced | reported upstream |
| CRC-011-IBT | observation | The snapshot's manifest has a terms address and a citation but no licence field; the batches carry no provenance | reproduced | open |

Details are in [the inventory](../inventory.md#findings).

## What this does not cover

- A `confirmed` outcome holds for these files, these options and crc-framework 0.6.0, crc-sdk 0.11.1.
- Verification says nothing about whether the publisher's values are right.
- Validation (fitness for a stated use) is not assessed.
