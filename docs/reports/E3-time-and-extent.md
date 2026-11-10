# E3 report: time and storm extent in explorer v2

Date: 2026-11-10 · branch `explorer-v2` (not merged) · follows [E2-explorer-v2.md](E2-explorer-v2.md) ·
awaiting review.

## What was added

1. **Wind extent (swaths).** `tracks.py` now carries, per track point, NOAA's quadrant radii of 34, 50 and
   64 kt winds (NE, SE, SW, NW; nautical miles), the radius of maximum wind and the radius of the outermost
   closed isobar, null where IBTrACS has none, and per storm the number of fixes with each measure. The page
   draws the three bands along the track of the selected storm (or of every shown storm when eight or fewer
   match the filters): one hue, three strengths, asymmetric by quadrant with a cosine interpolation between
   quadrant centres, hourly steps interpolated between the 3-hourly fixes. Overlapping rings do not pile up:
   the bands are drawn with a "max" blend on premultiplied colour, so the picture is a union. Toggle "Show
   wind extent". A storm without radii keeps its line and the panel says "no wind-radius estimate in IBTrACS
   for this storm"; no width is derived from intensity.
2. **Storm player.** Selecting a storm opens a time bar under the map: play/pause, speed (1 to 24 storm-hours
   per second), a slider and a UTC clock. The window is the storm's stretch over the Texas box plus one day
   either side, kept inside the shown track. A marker moves along the track (linear interpolation between
   fixes) with the 34/50/64 kt outlines at that moment; the wind chart in the panel gets a cursor. Storm
   Events reports whose begin time falls in the window appear on the map when the clock passes them and stay,
   coloured by event type with the fixed colours.
3. **Timeline strip.** Under the player: one row per event type in the window (hail and thunderstorm wind
   always), a tick for an instant report and a bar for one with a duration, hail taller and darker with size
   (0.5 to 4 in) and wind with speed (40 to 100 kt), county/zone reports dashed or hollow, the storm's time over
   Texas shaded, the clock as a cursor. Hover gives type, time, duration and magnitude; clicking a mark opens
   the report (and pans to it when it has a point); clicking empty space moves the clock.
   It works without a storm: on the Storm reports source, "Explore a date window" takes a start date and 1 to
   14 days (default 2024-03-14, 3 days, the Fort Bend hail); the type checkboxes choose the rows.
4. **Events layer with times.** `storm_events/explorer_layer.py` writes 32-byte records sorted by begin time,
   with begin and end as minutes since 1950-01-01 UTC, and now includes county/zone events (no point; timeline
   only). `python -m crc_lab.storm_events.explorer_layer` rebuilds it from the event table.

## Numbers

| Item | Value |
| --- | --- |
| Storms with 34 kt radii | 30 of 91, from Allison 2001 to Francine 2024 |
| Storms with 64 kt radii / radius of maximum wind / outermost closed isobar | 14 / 46 / 30 |
| `ibtracs.json` | 223 KB before, 354 KB now (52 KB gzipped) |
| `events.bin` | 2.6 MB (107,549 located, 24 bytes) before; 5.3 MB now (166,214 records, 32 bytes; 1.7 MB gzipped) |
| Reports with a duration (end after begin), all types | 74,976 of 166,214 |
| Harvey 2017 window (2017-08-24 09:00 to 08-31 06:00 UTC) | 213 reports in 9 rows; 142 located ones on the map by the end |
| Hail example (2024-03-14, 3 days) | 80 reports: 61 hail, 19 thunderstorm wind |

Timings, headless Chrome with software WebGL against a local server: first view 94 ms after scripts load;
selecting Harvey 105 ms including the first load of the 5.3 MB events file; timeline render 0.4–1.0 ms;
a player frame costs 0.15–0.19 ms of script, and the page held 18–32 frames per second while playing with
reports on (software rendering; a real GPU should do better and was not measured). No script errors or
console messages across the whole smoke run; 32 tests pass; `ruff` clean; `just site` complete.

## Limits

- Radii are US agency (NHC) estimates of the farthest reach of each wind threshold in a quadrant; the bands
  overstate the area with those winds and are not damage footprints. They exist only from 2001.
- Between fixes everything is linearly interpolated, including radii; a quadrant with no value counts as zero.
- Report times are NCEI local standard time converted to UTC (Phase 2); many reports carry rounded times.
- The timeline draws at most 6,000 marks and says so when it cuts.
- In storm mode every report in Texas in the window is shown, whether or not the storm caused it.
- The player is measured only under software rendering; nothing was measured from the public URL.

## Next iteration

The five open questions from this round were deferred by Yuri on 2026-11-10; they are listed verbatim in
[E4-groups-about-demo.md](E4-groups-about-demo.md#next-iteration-deferred-by-yuri-2026-11-10).
