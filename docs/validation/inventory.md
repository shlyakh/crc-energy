# Inventory: crc-sdk sources

Generated 2026-11-12 by `python -m data_source_check.build` against crc-framework 0.6.0, crc-sdk 0.11.1.
Do not edit: change the files under `src/data_source_check/sources/` and rebuild.

## Sources

| Source | Kind | Tier | Exploration | Verification | Validation | Findings | Signed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CRC Open hosted release (`crc-open`) | pre-fitted release | 1 | not assessed | not assessed | not assessed | 1 | draft |
| ERA5 reanalysis extremes (`era5`) | fitted curves | 1 | in progress | in progress | not assessed | 1 | draft |
| IBTrACS tropical cyclone tracks (`ibtracs`) | pass-through | 1 | assessed | assessed | not assessed | 2 | draft |
| NOAA CO-OPS extreme water levels (`noaa-water-levels`) | pass-through | 1 | in progress | in progress | not assessed | 0 | draft |
| NOAA GHCNh station temperatures (`ghcnh`) | fitted curves | 1 | assessed | assessed | not assessed | 0 | draft |
| CMIP6 projections (native grids) (`cmip6`) | fitted curves | 2 | not assessed | not assessed | not assessed | 0 | draft |
| ECCC rainfall intensity-duration-frequency (`eccc-idf`) | fitted curves | 2 | not assessed | not assessed | not assessed | 0 | draft |
| JRC EDO soil moisture index (`jrc-edo`) | fitted curves | 2 | not assessed | not assessed | not assessed | 2 | draft |
| JRC flood hazard maps (GloFAS, EFAS) (`jrc-flood`) | fitted curves | 2 | not assessed | not assessed | not assessed | 1 | draft |
| NASA NEX-GDDP-CMIP6 projections (`nex-gddp-cmip6`) | annual samples | 2 | assessed | assessed | not assessed | 2 | draft |
| NOAA ISD station temperatures (`isd`) | fitted curves | 2 | not assessed | not assessed | not assessed | 0 | draft |
| OS-Climate hazard indicators (`os-climate`) | fitted curves | 2 | not assessed | not assessed | not assessed | 1 | draft |
| CHIRPS v3 monthly rainfall (`chirps`) | pass-through | 3 | not assessed | not assessed | not assessed | 0 | draft |
| ECCC daily climate observations (`eccc-daily`) | pass-through | 3 | not assessed | not assessed | not assessed | 0 | draft |
| ECCC HYDAT daily flow and level (`hydat`) | pass-through | 3 | not assessed | not assessed | not assessed | 0 | draft |
| Fields of The World field boundaries (`ftw-fields`) | pass-through | 3 | not assessed | not assessed | not assessed | 0 | draft |
| NOAA 2022 sea-level scenarios (`noaa-sea-level`) | pass-through | 3 | not assessed | not assessed | not assessed | 0 | draft |
| USDA Cropland Data Layer (`usda-cdl`) | pass-through | 3 | not assessed | not assessed | not assessed | 1 | draft |
| USGS daily streamflow (`usgs-streamflow`) | pass-through | 3 | not assessed | not assessed | not assessed | 0 | draft |
| Your own data (`own-data`) | user data | n/a | not assessed | not assessed | not assessed | 0 | draft |

## What crc-sdk offers that is not assessed

Every entry point found in the installed version has an inventory entry.

Sources with no assessment at any tier: 14 of 19.
Option values (recipes, datasets, versions) not yet assessed: 35.

## Findings

| Id | Source | Kind | Finding | Basis | Status |
| --- | --- | --- | --- | --- | --- |
| CRC-001-NEX | nex-gddp-cmip6 | defect | Temperature recipes (txx, tnn) fail on real NEX files | reproduced | open |
| CRC-002-FWK | framework | doc-code difference | The 20-year minimum counts the years requested, not the years valid in each cell | code reading | open |
| CRC-003-JRC | jrc-flood | doc-code difference | JRC flood and EDO output files do not carry licence, attribution, retrieval time or checksum | code reading | open |
| CRC-004-EDO | jrc-edo | doc-code difference | EDO drought curves are labelled with the last year of the record, not the centre year | code reading | open |
| CRC-005-EDO | jrc-edo | observation | The EDO annual minimum has no completeness rule | code reading | open |
| CRC-006-ERA5 | era5 | observation | ERA5 values are converted without checking the unit the store declares | code reading | open |
| CRC-007-OPEN | crc-open | observation | retrieved_at in a CRC Open file is the time the file was written, not the time the data were downloaded | code reading | open |
| CRC-008-OSC | os-climate | doc-code difference | The OS-Climate licence is documented as read from layer metadata; no code that reads it was found | code reading | open |
| CRC-009-CDL | usda-cdl | observation | The Cropland Data Layer is read from a moving branch and its output records no provenance | code reading | open |
| CRC-010-IBT | ibtracs | defect | The subset "active" is accepted but NOAA has no file under that name | reproduced | open |
| CRC-011-IBT | ibtracs | observation | The snapshot's manifest has a terms address and a citation but no licence field; the batches carry no provenance | reproduced | open |
| CRC-012-NEX | nex-gddp-cmip6 | observation | NASA serves files of version 2.0, which cannot be requested | reproduced | open |

### CRC-001-NEX: Temperature recipes (txx, tnn) fail on real NEX files

- **Documented:** docs/sources/cmip6.md:5 says NEX uses the four recipes txx, tnn, rx1day and rx5day; line 36 says temperatures must be kelvin.
- **Observed:** The files declare kelvin, but h5netcdf returns the one-character unit as bytes (b'K') and the unit check compares its text form with 'K'. The call raises: 'tasmax' is published in "b'K'", but recipe 'txx' converts from 'K'. Precipitation is unaffected.
- **Consequence:** No temperature extremes can be read from NEX-GDDP-CMIP6 at this version.
- **Evidence:** crc_sdk/providers/cmip6.py:952; crc_sdk/workflows/nex.py:39-47; docs/reports/u1-nex-bytes-fix.md (crc-lab): real file headers, failing test, fix; check records nex-gddp-cmip6/units[txx ...] and units[tnn ...] (site/validation/data/records/nex-gddp-cmip6.json), run of 2026-11-12
- **Basis:** reproduced · **Status:** open · found 2026-11-10 at crc-sdk 0.11.1

### CRC-002-FWK: The 20-year minimum counts the years requested, not the years valid in each cell

- **Documented:** docs/sources/jrc.md:58: 'The curated policy fits the lower tail and requires at least 20 complete years.' The policy's own error message says it 'requires at least 20 complete years' (crc_sdk/workflows/blocks.py:126-129).
- **Observed:** validate_years compares the number of years in the request with minimum_years (crc_sdk/workflows/blocks.py:124-125). Each grid cell is then fitted when it has at least 4 valid annual values (MINIMUM_BLOCKS = 4, crc_sdk/connectors/blocks.py:60; minimum_blocks=4 in crc_sdk/providers/era5.py:566 and crc_sdk/providers/cmip6.py:1052). Station sources apply minimum_years per station.
- **Consequence:** A gridded curve can rest on far fewer years than the request suggests where data are missing; the number of years behind each cell's fit should be checked before use.
- **Evidence:** crc_sdk/workflows/blocks.py:124-129; crc_sdk/connectors/blocks.py:60; crc_sdk/providers/era5.py:566; crc_sdk/providers/cmip6.py:1052; docs/sources/jrc.md:58
- **Basis:** code reading · **Status:** open · found 2026-11-11 at crc-sdk 0.11.1

### CRC-003-JRC: JRC flood and EDO output files do not carry licence, attribution, retrieval time or checksum

- **Documented:** docs/data-licences.md:14-15: 'Every canonical file records source.licence, source.attribution, retrieved_at and checksum (schema 1.3), so outputs self-describe.'
- **Observed:** Those fields are written only when the curve source supplies a CurveSourceInfo (crc_sdk/connectors/adapters.py:309). The JRC and EDO modules define none; the JRC workflow only rewrites the uri (crc_sdk/workflows/jrc.py:521-534). Checksums of the cropped inputs are kept in the cache manifest, not in the output file. Applies to jrc-edo as well.
- **Consequence:** A JRC flood or EDO file, once moved away from its cache, does not say under which licence or from which bytes it was made.
- **Evidence:** docs/data-licences.md:14-15; crc_sdk/connectors/adapters.py:309; crc_sdk/workflows/jrc.py:521-534
- **Basis:** code reading · **Status:** open · found 2026-11-11 at crc-sdk 0.11.1

### CRC-004-EDO: EDO drought curves are labelled with the last year of the record, not the centre year

- **Documented:** docs/design-decisions.md:28-30: for a window, 'horizon = centre year (start + end) // 2'. docs/sources/cmip6.md:42: 'horizon is the window centre'.
- **Observed:** The EDO provider sets the year of its record to max(years) (crc_sdk/providers/jrc_edo.py:217).
- **Consequence:** An EDO file and an ERA5 or CMIP6 file built over the same years would carry different horizons and would not join on the row key.
- **Evidence:** crc_sdk/providers/jrc_edo.py:217; docs/design-decisions.md:28-30
- **Basis:** code reading · **Status:** open · found 2026-11-11 at crc-sdk 0.11.1

### CRC-005-EDO: The EDO annual minimum has no completeness rule

- **Documented:** crc_sdk/connectors/blocks.py:20-30 states the convention for block statistics: a block needs a minimum fraction of valid days.
- **Observed:** The EDO annual value is np.nanmin over whatever ten-day values exist in the year (crc_sdk/providers/jrc_edo.py:255), so one valid value makes a year.
- **Consequence:** A year with most of its record missing still contributes an annual minimum to the fit.
- **Evidence:** crc_sdk/providers/jrc_edo.py:250-255; crc_sdk/connectors/blocks.py:20-30
- **Basis:** code reading · **Status:** open · found 2026-11-11 at crc-sdk 0.11.1

### CRC-006-ERA5: ERA5 values are converted without checking the unit the store declares

- **Observed:** The CMIP6 and NEX readers refuse a variable whose units attribute differs from the recipe's (crc_sdk/providers/cmip6.py:946-958). The ERA5 provider reads a units attribute only for the time axis (crc_sdk/providers/era5.py:244) and applies the kelvin and metre conversions unconditionally.
- **Consequence:** If a store changed its units, ERA5 values would be converted wrongly without an error.
- **Evidence:** crc_sdk/providers/era5.py:244; crc_sdk/providers/cmip6.py:946-958
- **Basis:** code reading · **Status:** open · found 2026-11-11 at crc-sdk 0.11.1

### CRC-007-OPEN: retrieved_at in a CRC Open file is the time the file was written, not the time the data were downloaded

- **Documented:** docs/data-licences.md:20-21: 'the retrieval date and checksum are the audit trail.'
- **Observed:** When a selection is materialised, retrieved_at is set to the current time (crc_sdk/workflows/crc_open.py:600), also when the partitions come from a warm cache.
- **Consequence:** The field cannot be used to tell when the release was actually fetched.
- **Evidence:** crc_sdk/workflows/crc_open.py:588-604
- **Basis:** code reading · **Status:** open · found 2026-11-11 at crc-sdk 0.11.1

### CRC-008-OSC: The OS-Climate licence is documented as read from layer metadata; no code that reads it was found

- **Documented:** docs/data-licences.md:38: 'OS-Climate layers | Read from layer metadata | Per layer'.
- **Observed:** A search of crc_sdk/providers/os_climate.py for licence handling finds none. Only that file was searched.
- **Consequence:** An OS-Climate output file may carry no licence.
- **Evidence:** docs/data-licences.md:38; crc_sdk/providers/os_climate.py (search for 'licen': no match)
- **Basis:** code reading · **Status:** open · found 2026-11-11 at crc-sdk 0.11.1

### CRC-009-CDL: The Cropland Data Layer is read from a moving branch and its output records no provenance

- **Documented:** docs/development.md:25-26: 'Every adapter records licence, attribution, retrieval time and checksums in canonical metadata or its cache manifest.'
- **Observed:** The request defaults to branch 'main' of the Source Cooperative repository, not a fixed snapshot (crc_sdk/connectors/agriculture.py:100). Rows carry a source path only.
- **Consequence:** Two runs of the same request can return different data with nothing in the output to show it.
- **Evidence:** crc_sdk/connectors/agriculture.py:96-101; docs/development.md:25-26
- **Basis:** code reading · **Status:** open · found 2026-11-11 at crc-sdk 0.11.1

### CRC-010-IBT: The subset "active" is accepted but NOAA has no file under that name

- **Documented:** crc_sdk/workflows/ibtracs.py:28-41 lists "active" among the eleven accepted subsets; the error message for any other spelling names it as valid. docs/sources/observations.md:29 documents basin subsets only.
- **Observed:** crc-sdk requests .../ibtracs.active.list.v04r01.csv and NOAA answers 404. NOAA's directory holds ibtracs.ACTIVE.list.v04r01.csv (capitals). IBTrACSPlan("active", ...).prefetch() raises HTTPError 404; IBTrACSPlan("ACTIVE", ...) is refused as an invalid subset. The other ten names are served.
- **Consequence:** Currently active storms cannot be read through IBTrACSPlan at this version. The other subsets are unaffected.
- **Evidence:** crc_sdk/workflows/ibtracs.py:28-41; crc_sdk/workflows/ibtracs.py:70-71; check record ibtracs/address (site/validation/data/records/ibtracs.json), run of 2026-11-12
- **Basis:** reproduced · **Status:** open · found 2026-11-12 at crc-sdk 0.11.1

### CRC-011-IBT: The snapshot's manifest has a terms address and a citation but no licence field; the batches carry no provenance

- **Documented:** AGENTS.md (crc-sdk) asks contributors to 'record licence, attribution, retrieval time and checksums for every source'. docs/data-licences.md:36 lists IBTrACS as a U.S. government work with attribution requested.
- **Observed:** The manifest written beside the snapshot holds url, version, subset, sha256, retrieved_at, etag, last_modified, units, terms_url and citation (crc_sdk/workflows/ibtracs.py:139-153). It has no licence field. The Arrow batches returned by batches() have no schema metadata, so the provenance travels only in the cache directory.
- **Consequence:** A user who passes the batches on must copy the citation and terms from the manifest or from prefetch(); nothing in the data carries them.
- **Evidence:** crc_sdk/workflows/ibtracs.py:139-153; check records ibtracs/provenance[*] (site/validation/data/records/ibtracs.json), run of 2026-11-12
- **Basis:** reproduced · **Status:** open · found 2026-11-12 at crc-sdk 0.11.1

### CRC-012-NEX: NASA serves files of version 2.0, which cannot be requested

- **Documented:** docs/sources/cmip6.md:73: 'File revisions 1.0, 1.1 and 1.2 are selected explicitly'. crc_sdk/workflows/nex.py:84-85 refuses any other version.
- **Observed:** For ACCESS-CM2 r1i1p1f1, NASA's archive holds files ending in _v2.0.nc for tasmax, tasmin and pr, in both years checked (historical 2014, ssp585 2050). They were uploaded on 1 July 2025 and carry the attribute version = '2.0'. No version 1.2 file exists for these; version 1.1 exists for pr only. In the Texas box the annual one-day rainfall from 2.0 equals that from 1.1 and differs from 1.0 in 15 of 2,158 cells in 2014 (by at most 0.08 mm) and 42 cells in 2050 (by at most 0.84 mm); the annual maximum temperature from 2.0 equals that from 1.0.
- **Consequence:** A user cannot read NASA's latest revision through crc-sdk, and the default (1.0) is the oldest. The differences seen here are small; other models, variables and regions were not compared. NASA's technical note for version 2.0 (31 May 2025, section 4.3) states that tasmax and tasmin were reprocessed in their entirety with a corrected observational reference (an artifact over central Canada) and that values were swapped in grid cells where the maximum was below the minimum; that anomalously large pr values in cells with an extremely small daily climatology were adjusted; and that bounds were applied to hurs, huss, rlds and sfcWind. These corrections are in version 2.0 only.
- **Evidence:** crc_sdk/workflows/nex.py:84-85; docs/sources/cmip6.md:73-74; NASA technical note for version 2.0, sections 3.2.2.1 and 4.3 (docs/validation/references/nex-gddp-cmip6-v2/README.md); check record nex-gddp-cmip6/versions-served (site/validation/data/records/nex-gddp-cmip6.json), run of 2026-11-12
- **Basis:** reproduced · **Status:** open · found 2026-11-12 at crc-sdk 0.11.1
