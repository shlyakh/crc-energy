# Primer: how an event source can be used in CRC

Written for the Storm Events work. Based on reading crc-sdk `main` (commit of 2026-11-04) and crc-docs.

## The short version

CRC's contract holds **curves**: for a place, a hazard and a period, a distribution of an annual value ("the
largest hail in a year here"). An event source holds **records**: "on this date, at this place, hail of this size
fell and did this much damage". Records are not curves. CRC can carry records, but only as plain tables; turning
them into curves is a separate, explicit step, and CRC gives you the tools for that step.

## Two tiers inside CRC

| Tier | What it is | Examples in crc-sdk | What you get back |
| --- | --- | --- | --- |
| Observation plans | Lazy, cached, checksummed access to someone else's records | `IBTrACSPlan` (cyclone tracks), `USGSStreamflowPlan`, `ECCCDailyPlan`, `HYDATDailyPlan`, NOAA water levels, station providers | Tables of records, source columns kept |
| Hazard datasets | Fitted curves per H3 cell in the canonical format | `HazardDataset.crc_open()`, `.era5(...)`, and anything brought in with `.from_table()`, `.from_zarr()`, `.from_raster()` | Rows keyed by hazard, horizon, pathway, cell and source, which `for_assets(...)` can evaluate |

CRC is explicit that the first tier is not the second. The cyclone-track module opens with "best-track
observations, not hazard curves", and the documentation says track points "are not asset winds or return-period
curves".

`IBTrACSPlan` is the pattern to copy for Storm Events. It names a remote file, caches a byte snapshot, records a
SHA-256 and a manifest, and offers `explain()` (what would be fetched), `prefetch()` and `batches()` (the records).
It can replay offline from the recorded checksum, because NOAA updates such files in place.

## Four ways to use an event source

**1. As a record table (tier one).** Fetch, clean, place on H3 cells, publish. Useful alone: filter, count, map.
Nothing in CRC's curve contract applies yet. This is P2 of the plan.

**2. As hazard curves (tier two).** Reduce events to one number per cell per year, then fit:

- *Annual maximum magnitude* (largest hail size, strongest gust). Years with no event are real zeros, so the
  distribution has a spike at zero and a tail above it. CRC has a hurdle distribution for exactly this shape.
- *Annual count* of events above a threshold ("days with hail of 1.75 inches or more"). This gives a rate; the
  chance of at least one in a year follows from it.

Either result enters CRC through its route for outside data: `HazardDataset.from_table(...)` with a fit policy
that states the unit, the meaning of the value, the source, and `probability_semantics`. From then on it behaves
like any CRC hazard: `for_assets(...)`, return periods, impact functions, `compute_risk`.

What must be declared, because CRC cannot know it:

- the semantics: these are annual-value distributions built from reports, not physical measurements on a grid;
- the reduction rule: which events, which years, how neighbouring cells were pooled;
- the observation bias: reports follow people, so an empty cell may be unobserved.

**3. As ground truth.** Keep the records as they are and use them to check a curve or a damage estimate from
another source: did the 15 March 2024 hail in Fort Bend County fall in the tail of the hail curve there? This needs
no CRC contract, only a join on cell and date.

**4. As an event set for joint losses.** One storm hits many assets at once. To capture that, each simulated year
must contain whole events, not independent per-cell draws. CRC has no contract for this and its risk function
assumes independence. Any use of events this way lives outside CRC for now, and a schema for it is an open design
question.

## What CRC does not have for events

- No event-table schema (event id, type, start, end, cells, magnitude, magnitude type, damage).
- No notion of an event footprint or a path across cells.
- No occurrence view of loss (largest single event in a year).
- No hail, gust, lightning or ice-accretion hazard in CRC Open.

## What this means for Storm Events

1. Build it as an observation plan with a cleaned record table (use 1).
2. Derive hail and gust curves and bring them in through `from_table` (use 2).
3. Keep the record table as the check for everything built later (use 3).
4. Leave joint-loss event sets (use 4) for a later phase; propose the schema once the table exists.
