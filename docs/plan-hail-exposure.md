# Plan: better hail exposure at an asset — footprint, reporting bias, radar

Draft, 2026-11-10, for Yuri's review. Not scheduled; nothing here is built except the two items marked done.
It answers three requests: add hail event area and plant size; correct for over-reporting where people are,
until radar is added; and plan how to combine reports with radar.

Sources are from a literature search on 2026-11-10. Each line says whether the primary text was read. Numbers
taken from that search are leads until re-checked; the archive listings were re-listed from this repo.

## 1. Footprint and plant size

**Done 2026-11-10** (`assets/exposure.py`):

- The circle around a plant is clipped to Texas, because the event table holds no reports from Mexico, the Gulf
  or other states. Fifteen of 187 plants had under 90% of their circle inside Texas; the lowest is 36%.
- Plant size uses each plant's own array area from the solar database (median 2.4 km², largest 17.9 km²), not an
  average. A hit happens when a hail footprint and the plant, both treated as discs, overlap.

**Still a placeholder: the hail footprint, 25 km² per report.** What the literature gives:

| Evidence | Value | Source and how it was read |
| --- | --- | --- |
| One hailstreak, any hail size, Illinois dense networks 1967–68 | most are 10–21 km²; yearly means 25 and 56 km² | Changnon, Changnon and Hilberg 2009 atlas (primary text), restating Changnon 1970 (not opened) |
| Great Plains against Illinois | streaks longer and longer-lasting (mean length 15.3 against 10.8 miles) | same atlas; its width figures contradict its own table |
| Radar swath of severe hail (29 mm or more), MYRORSS 2000–2011 | area most often 50–100 km² (a mode, not a median) | Schlie et al. 2019 (primary text) |

So 25 km² sits at the low end of a defensible 20–100 km² range. Proposal: keep the default, show 20, 50 and
100 km² in the sensitivity note with these sources, and replace the placeholder with measured swath areas once
radar is in (section 3). Not found: any Texas-specific swath statistic.

Better still for US borders: extend the event table to Oklahoma, New Mexico, Arkansas and Louisiana, so only
Mexico and the Gulf need clipping.

## 2. Reporting bias from population and roads

**What is published.** Only one usable functional form was found, and it is for tornadoes:

- Potvin et al. 2019 (primary text): reported count ~ negative binomial with mean = reporting rate × true rate;
  reporting rate = floor + (1 − floor) × exp(−b × x), x a transform of log population density, set to 1 above a
  density threshold. Population density predicted best; road density was weaker. No fitted value of b was found
  in the text.
- Allen and Tippett 2015 (primary text): hail reports in the Texas Panhandle cluster on roads and towns while
  population is flat, and practice changed over time. So population alone is not enough: add roads and an era term.
- Wendt and Jirak 2021 (primary text): radar finds severe hail 2 to 4 times as often as Storm Data even in the
  populated plains, more where few people live. That is the size of the correction to expect.

**Proposed build (reports only, usable before radar).**

1. Grid Texas at about 10 km. Per cell and year: hail-day counts, and counts of days with 1 inch or more.
2. Covariates per cell: population density (GPWv4, open; 2000–2020 snapshots), road length or distance to a
   primary road (Census TIGER/Line), and an era term for reporting practice.
3. Fit Potvin's form to hail-day counts, with a smooth regional true rate. Estimate the floor and b; do not
   reuse tornado values.
4. Output a reporting rate per cell. Corrected local rate at a plant = observed rate ÷ reporting rate, with the
   interval from the fit. Show corrected and uncorrected side by side.
5. Check against radar where both exist: after correction, report-based hail-day frequency should approach the
   radar frequency in dense and sparse cells alike. Until radar is in, check against the SPC climatology pattern.

Done when: the fitted reporting rate is published per cell with its uncertainty, the ten-city and solar-plant
tables show before and after, and the Fort Bend plants no longer rank below city sites for reasons of
population alone.

Risk: without an independent truth, the true rate and the reporting rate are only separated by assuming hail
climate varies smoothly while reporting varies sharply. Radar removes that assumption, which is why this is an
interim step.

## 3. Combining reports and radar

**Data, listed from this repo on 2026-11-10.**

| Archive | Period | Notes |
| --- | --- | --- |
| MRMS on AWS (`noaa-mrms-pds`), `CONUS/MESH_Max_1440min_00.50/` | first folder 14 October 2020, to present | daily and sub-daily maxima of radar hail size (MESH), about 1 km, GRIB2, about 0.8 MB per file |
| MYRORSS reanalysis on AWS (`noaa-oar-myrorss-pds`) | year folders 1998–2011 | 0.01°; file layout not yet inspected |
| 2012 to October 2020 | no open archive found | Wendt and Jirak used an internal feed; Iowa State keeps "select" fields from 2014, hail not confirmed |

**What is known about radar against reports** (all primary text unless noted): a MESH of about 30 mm is the best
single discriminator of severe hail, with modest skill (Ortega 2018); MESH is built so that 75% of observed
sizes fall below it, so it overstates the typical stone (Wendt and Jirak 2021); in Switzerland the radar
false-alarm rate per cell falls from over 80% at 20 mm to 50% at larger sizes (Schmid et al. 2024). Radar tells
where and roughly how big; reports confirm that hail reached the ground and how big it actually was.

**Proposed design, in three steps.**

1. **Radar as footprint.** From daily-maximum MESH, mark cells at or above a threshold near 30 mm as hail-day
   cells. This gives hail-day frequency per cell that does not depend on who lives there, and measured swath
   areas for Texas to replace the placeholder in section 1. First test: 15–16 March 2024 over Fort Bend County,
   where the plant was destroyed and reports are thin.
2. **Reports calibrate radar.** In densely populated cells only, where a missing report is informative, estimate
   the chance that hail reached the ground given the radar value, and the distribution of reported size given
   radar size. Apply both everywhere. This follows Kopp et al. 2024, who verify radar only where people are.
3. **Joint model, later.** One model with latent hail occurrence, radar as predictor and a reporting
   probability from population and roads, after Greco et al. (Australia; workshop paper, journal version not
   opened). It unifies sections 2 and 3 and is the long-term target.

**Hazard metric.** Keep two named inputs, as the hail impact draft already requires: `hail_diameter_obs_mm`
(reports) and a radar metric (MESH). The Swiss damage curves were fitted to a radar metric, so they should be
fed the radar one; the lab-based solar curve needs an observed size, which step 2 supplies from radar.

**The 2012–2020 gap.** Options: use 1998–2011 plus 2020 on (about 20 years, with a hole); or build the curve
from reports corrected by section 2 and use radar only to calibrate. Decide after step 1 shows how much the two
radar periods differ.

Done when: radar hail-day frequency exists per cell for both periods; the Fort Bend event is reproduced; the
plant table shows report-based, bias-corrected and radar-based exposure side by side; and the footprint is a
measured Texas swath area.

## Decisions for Yuri

1. Order: reporting-bias correction first (reports only, faster), or go straight to radar step 1?
2. Footprint: keep 25 km² with the 20–100 km² range shown, or move the default to 50 km²?
3. Extend the event table to neighbouring states?
4. Accept the 2012–2020 radar gap, or look further for an archive?

## Not verified

Changnon 1970 itself; a median (not modal) radar swath area; any Texas swath statistics; the fitted b in Potvin
et al.; Murillo and Homeyer 2019 beyond thresholds quoted elsewhere; the MYRORSS file layout; licences of
LandScan, WorldPop and OpenStreetMap; whether radar saw large hail over Fighting Jays in March 2024.
