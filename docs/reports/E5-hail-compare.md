# Explorer report E5: hail sources compared, and a grouped plant panel

Date: 2026-11-10 · branch `hail-compare-ui` · explorer side only. The data
(`site/data/hail_compare/cells.json`) is built by `crc_lab.radar.compare_cells` on main.

## What was built

- **A new source, "Hail days: sources compared"**, in the "Experimental new sources" group. It shows hail days
  per year in each of the 2,566 Texas cells from four records: storm reports of 1 inch or more (1996–2025), the
  same corrected for reporting bias, radar hail size of 30 mm or more (MRMS, 2020–2025), and radar hail
  signatures of 1.25 inches or more (NEXRAD, 1995–2025). The source card and the caveat panel say what each
  record is and that they measure different things.
- **A layer kind, `h3-compare`**, drawn with the same H3 cell layer as the hazard sources. Three views:
  - **One source.** A selector picks the record that colours the map. One sequential hue. By default all four
    share one scale (the 98th percentile of all values), so levels can be compared across sources; a checkbox
    scales each source to its own range to show the pattern inside one source.
  - **Swipe between two sources.** A draggable vertical line on the map: cells west of the line show one
    source, cells east of it the other, with a label on each side.
  - **Ratio of two sources.** Colour by the ratio on a log scale centred on "equal": two hues with a neutral
    grey midpoint, saturating at 16 times either way. Cells with no value in one source are grey, and the
    legend says how many cells have both.
- **Cell click.** A panel with the four values as bars (fixed order and colours, value labelled on each bar),
  a table of the same numbers, the fitted reporting rate and the cell id.
- **Signatures per year.** A small bar chart in the source panel from `signatures_per_year`, 1995–2025, with a
  note that the swings are partly the record itself.
- **Grouped plant panel.** The solar plant click panel is grouped under Plant, Value, Hail from reports, Hail
  from reports bias-corrected, Radar and Thunderstorm wind, with chances shown as percentages. The grouping is
  a `panel_groups` list on the layer in `site/layers.json`; any `points` layer without it keeps the plain list.

## Why swipe, and how it works

The split is done by colouring, not by clipping: each cell is coloured from the left or right source according
to whether its centre lies west or east of the line's longitude, which is read from the map at the line's
screen position. This needs one map, one deck.gl overlay and no extension, so it adds nothing to the pinned
libraries and cannot drift out of sync as two side-by-side maps could. The cost is a boundary that follows cell
edges (about 16 km) instead of a straight cut. The line follows the map when it is panned or zoomed.

## Checks

Headless Chrome, software rendering, local server (`node tools/smoke.mjs <dir> <url>`):

| Step | Result |
| --- | --- |
| Open the comparison source (first load of the cells file) | 170–207 ms |
| Switch the colouring source | 12–14 ms |
| Own-range scale on | 6–7 ms |
| Swipe view on | 10–18 ms |
| Ratio view | 8–11 ms |
| Divider dragged with the pointer | moved from 50% to 30% of the map width |
| Cell click | panel with 4 bars and a 4-row table |
| Plant click | 7 headings (Source plus six groups), 6 values as percentages, curve chart present |
| A station from another `points` layer | plain list, no headings |
| Whole run, including the 30-second demo | no console messages, no script errors |

47 tests pass (one new: the registry entry, its colours against the data file's sources, and every
`panel_groups` field present in the plant file). The site check is complete with 18 layers.

## Not done / not verified

- The demo was left alone. It already runs 31.6 s against a 30 ± 3 s target, so a comparison step would not fit
  without removing another.
- The About tab lists the new source through the registry (group, description, licence); it has no computed
  count line for it.
- Colours were chosen from the palette already used on the page; the palette validator was not re-run for the
  four bar colours as a set.
- Touch dragging of the divider was not tested, only the mouse.
- Timings are local, not from the public site.

## Questions

1. Is the shared scale the right default? On it, storm reports look almost empty beside radar, which is the
   honest picture but hides the reports' own pattern until the own-range box is ticked.
2. The ratio view defaults to whatever two sources are selected. Should it open on radar ÷ reports?
3. Should the comparison get a step in the demo, replacing the CRC Open step or the Sources tab step?
