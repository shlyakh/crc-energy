# NEX-GDDP-CMIP6 version 2.0: NASA's technical note

A copy kept here so that finding CRC-012-NEX can be checked against the text it cites.

| File | What it is | SHA-256 |
| --- | --- | --- |
| `NEX-GDDP-CMIP6-v2-Tech_Note.pdf` | *NASA Earth Exchange Global Daily Downscaled Projections, version 2 (NEX-GDDP-CMIP6 v2.0)*, technical note (41 pages) | `5fbb928bb6b6731b48adbf898c0fd40531fdcd12d189fd0f2e1acc91d6f40bc1` |
| `NEX-GDDP-CMIP6-v2-Tech_Note.txt` | Text extracted with `pdftotext -layout`, for searching. The PDF is the reference. | |

- Published by the NASA Center for Climate Simulation. "Latest update: May 31, 2025" (title page).
- Source: <https://www.nccs.nasa.gov/wp-content/uploads/2025/06/NEX-GDDP-CMIP6-v2-Tech_Note.pdf>,
  linked as "tech note (v2 data)" from
  <https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6>.
  Downloaded 2026-11-12.
- A publication of a U.S. federal agency, reproduced unchanged.
- Only the text was read. The difference maps in section 4.3 (pages 9 to 30) were not examined.

## Passages the finding relies on

Section numbers are the note's own.

| Topic | Where | In short |
| --- | --- | --- |
| Version 1.1 | 4.1 | August 2023: tasmin for SSP1-2.6 and SSP3-7.0 fixed in some cells; TaiESM1 historical temperature replaced; hurs given an upper bound. February 2024: pr reprocessed "to address an overcorrection in climatologically dry areas". |
| Version 1.2 | 4.2 | The 1.1 tasmin fix reprocessed in full, with tas. |
| Version 2.0, tasmax and tasmin | 4.3.8, 4.3.9 | "re-processed in its entirety with the adjusted GMFD"; "values have been swapped in grid cells where tx<tn" |
| The adjusted reference | 3.2.2.1 | An artifact over central Canada (50-71°N, 257-260°E) in the reference temperature files was filled in; the adjusted files were "inadvertently not used in the v1.1 & v1.2 updates" to tasmin |
| Version 2.0, tas | 4.3.7 | Recalculated from the new tasmax and tasmin |
| Version 2.0, pr | 4.3.3 | Anomalously large values in cells with extremely small daily climatology "were adjusted in the v1.1 files" |
| Version 2.0, rsds | 4.3.5 | The same adjustment, in the 1.0 files |
| Version 2.0, hurs | 4.3.1 | Upper bound of 105% |
| Version 2.0, huss, rlds, sfcWind | 4.3.2, 4.3.4, 4.3.6 | Lower bound of 0.0 |
| Recommended use | 5.1 | "intended for use in scientific research only"; other uses "not recommended without consultation with a qualified expert" |
| Terms of use | 7 | Governed by the CMIP6 terms of use; the `cmip6_license` attribute of each file names the licence |
