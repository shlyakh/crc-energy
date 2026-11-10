# Radar hail data sources for Texas

Research note, 2026-11-10. Question: which radar-derived hail records exist for Texas, and what covers 2012 to
October 2020, where no open gridded archive was found at first. Compiled from a web and archive search; the
"Checked" column says what was actually done. Lines marked "from this repo" were read or listed by code here.

**Short answer.** Radar hail data exists for every year since 1995, but in three different forms. Gridded hail
size (MESH) is open for 1998–2011 and from August 2019 on. For 2012 to mid-2019 the open record is per-storm
hail signatures (points), or raw radar volumes from which a grid would have to be computed. The Storm Prediction
Center holds a private gridded archive for 2012–2019.

## Sources

| Source | Hail quantity | Period | Form | Access | Licence | Checked |
| --- | --- | --- | --- | --- | --- | --- |
| MRMS on AWS (`noaa-mrms-pds`) | MESH and its 30-minute to 24-hour maxima; also probability of severe hail, severe hail index, VIL | from 14 October 2020 | grid, 0.01°, GRIB2 | `CONUS/MESH_Max_1440min_00.50/YYYYMMDD/` | NOAA open data | **from this repo:** 1,903 daily files 2020-10-15 to 2025-12-31 decoded (`radar/mrms.py`) |
| Iowa State mtarchive, MRMS | MESH (2-minute) and 24-hour maximum | from about 20 August 2019 | grid, GRIB2 | `mtarchive.geol.iastate.edu/YYYY/MM/DD/mrms/ncep/MESH/` | open | listed by the search; 24-hour maximum present on some days and absent on others; before August 2019 only precipitation products |
| MYRORSS reanalysis (`noaa-oar-myrorss-pds`) | MESH and other multi-radar products | 1998–2011 | grid, 0.01° | S3, year folders | NOAA open data | **from this repo:** year folders listed; file layout not yet inspected |
| NCEI Severe Weather Data Inventory, `nx3hail` | per storm cell and radar scan: maximum expected size (inches), probability of hail, probability of severe hail | 1995 to present | points, yearly CSV | `ncei.noaa.gov/pub/data/swdi/database-csv/v2/hail-YYYY.csv.gz`; also a bounding-box web service | U.S. government (licence text not found) | **from this repo:** yearly files read and clipped to Texas (`radar/swdi.py`); 2015 holds 10.8 million rows nationally, 295,019 in the Texas box at 0.75 inch or more |
| NEXRAD Level II (`unidata-nexrad-level2`) | reflectivity volumes; no hail product | 1991 to present | per radar, every 5–10 minutes | S3 `YYYY/MM/DD/KXXX/` | open | listed by the search for one radar and day |
| NEXRAD Level III on Google Cloud (`gcp-public-data-nexrad-l3`) | hail index and VIL products | 1992 to present | daily tar per radar | Google Cloud Storage | open | one day's tar opened by the search (477 MB for one radar) |
| NEXRAD Level III on AWS (`unidata-nexrad-level3`) | same products | from March 2020 | per-product files | S3 | open | listed by the search; nothing for 2012–2019 |
| GridRad and GridRad-Severe (NCAR) | reflectivity, dual-polarisation; no MESH listed | hourly 1995–2017; severe days 2010–2023 | 3-D grid | NCAR data portal | CC BY 4.0 | documentation only |
| MYRORSS version 2 | "2012 – present" planned | not released as far as found | — | — | — | a 2020 poster only |
| Published MESH climatologies (Wendt and Jirak 2021; Murillo, Homeyer and Allen 2021; Cintineo et al. 2012) | hail-day frequencies | 2012–2019; 1995–2017; 2007–2010 | papers | no gridded download found | — | first paper opened; others from search results |
| pyhail (open source) | computes MESH from Level II volumes | — | Python | GitHub, MIT | — | README read |
| Commercial: CoreLogic/Cotality, Verisk, HailTrace, Interactive Hail Maps, Canopy Weather, Understory | hail swaths, verification, sensor networks | — | — | paid | commercial | not verified |

## What covers 2012 to October 2020

1. **Hail signatures (`nx3hail`) cover the whole gap, and all years since 1995.** They are the only ready-made
   radar hail record that does. Limits: points, not a grid; one algorithm per radar, so one storm appears from
   several radars and in many scans; early years carry missing values (−999) for size and probability; the
   archive notes that some sizes were rounded. This project pulls it as its own source.
2. **Iowa State's MESH grid covers about August 2019 to October 2020** and joins onto the AWS archive, with gaps
   in the daily maximum product.
3. **A MESH grid for 2012 to mid-2019 has to be computed** from Level II volumes (pyhail or WDSS-II), radar by
   radar. That is a large computation, not a download.
4. **The Storm Prediction Center has the 2012–2019 grid privately.** Wendt and Jirak state: "there is no formal
   archive of the data. MESH data in this project were obtained by archiving the SPC operational MESH feed". It
   could be requested.

## How this project uses them

- **MRMS 2020–2025** is the gridded radar reference: hail days at each plant, measured swath areas, and the
  check on the reporting-bias correction (`docs/reports/4-radar-hail.md`).
- **Hail signatures 1995–2025** are a separate long record for comparing hail-day frequency by cell against
  reports and against MRMS where they overlap.
- **MYRORSS 1998–2011** is the next candidate: it would extend gridded radar back by 14 years.

## Not verified

The units of the signature size field are taken as inches from typical values (0.5, 0.75, 1.0), not from a
format document; the licence text for the inventory; the status of MYRORSS version 2; whether Murillo et al.
published their grid; holdings at NSSL, the University of Oklahoma and Google Earth Engine; every commercial line.
