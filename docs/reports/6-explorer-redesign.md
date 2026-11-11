# Phase 6 report: explorer redesign

Date: 2026-11-11. Plan and the decisions behind it: [plan-explorer-next.md](../plan-explorer-next.md). Live at
https://shlyakh.github.io/crc-lab/. The old page is removed (it is in git history up to commit 96ec37c); old
`/next/` links forward to the main address.

## What changed for a visitor

- **Two projects on one page**, switched at the top left: "Texas hail risk" (Risk, Hail evidence, Methods) and
  "Texas CRC data" (Data, About). The first is new work built on Climate Risk Commons; the second is an explorer
  of what crc-sdk already reaches.
- **Risk tab** (the page opens here): a ranked, sortable plant table; a map with plants sized by capacity and
  coloured in five classes; the selected plant's figures. Table, map and detail share one selection.
- **On every map**: a legend with numeric ranges, units and the data period; a scale bar; cursor coordinates;
  a hover box; a highlight on whatever is selected.
- **Selecting a plant** draws its array outline, its report circle (radius and report count labelled) and the
  hail reports inside it, sized by hail size.
- **"As reported / Bias-corrected" switch** recolours the map, re-sorts the table and updates the legend; the
  table and the detail always print both. Plants whose correction factor is above 5 are marked.
- **Plants under 20 MW are hidden by default** (74 of 250; Yuri's decision). The table head, the legend and the
  note under the table say so, and a selector shows them.
- **Plant detail**: headline figures, three charts (hail sizes in the circle, the plant's damage curve with its
  reports, hail days from four records), and the rest in collapsed groups with assumptions marked "placeholder"
  or "rule".
- **Methods**: how a report becomes a loss (five steps), the four damage curves with sliders for the two stow
  placeholders, the records used and the limits. **About** (CRC data): what is shown and everything crc-sdk
  reaches.
- **Tour**: seven steps through both projects, about 38 seconds, recorded as `site/demo.webm`.
- The address keeps the tab, source, plant, measure and switch, so a view can be linked.

## What changed in the code

- `site/` is now ES modules with no build step: `js/main.js`, `risk.js`, `charts.js`, `sources.js`, `views/`,
  `methods.js`, `demo.js`; `style.css` and `sources.css`. The old single `app.js` is gone; its view code was
  moved into `js/views/` largely as it was.
- `src/crc_lab/explorer/risk_layer.py` writes `plants.json` (numeric measures, class breaks computed once so
  the legend and the map agree, totals), `plants_detail.json` (report circles, reports, outlines, curves, hail
  days) and `curves.json` (the damage curves as values on a grid of stow settings). The page never computes a
  curve.
- `tools/smoke.mjs` is rewritten for the new page.

## Checks

- Smoke test, headless Chrome, 1440×900 and 1100×800: all checks pass (every source in both projects, one click
  per layer kind, legends carry numbers and units, table and map selection agree, the bias switch moves the
  totals to the Phase 5 figures, the default capacity filter and its notices, deep links, Methods sliders against
  the shipped curve values, the tour, the `/next/` forward), with no console message or script error.
- 91 offline tests pass, including tests of the data files against each other and against the curve module.
- The five-class colour ramp passes the palette validator (one hue, monotone lightness, light end visible).

## Not done or not verified

- Only headless Chrome with software rendering was used: no real GPU, Firefox, Safari or touch device.
- No phone layout (decided). Between 1000 and 1280 px the plant table hides the inactive column rather than
  becoming a drawer, the legend covers part of west Texas at the default view, and long source titles are cut.
- The tour is 38 seconds, not 30, and shows the comparison map rather than the 16 March 2024 hail day in the
  storm player. The recording was checked by frames, not watched end to end.
- A selected plant's name tag can sit on top of its map label.
- The "Also show" list in the source tabs still carries a stale "Solar farms, planned" entry from the registry.
- `docs/decisions.md` and `docs/hail-data-processing.md` do not yet describe Phase 5 or this redesign.
- The first CI run of stop 3 failed on a test that compared floats exactly across machines; fixed with a
  tolerance. The live site was not affected, since a failed run deploys nothing.

## Questions

1. Is 20 MW the right default threshold, or should it follow a definition (for example EIA's utility-scale)?
2. Should the tour be cut to 30 seconds, or is 38 acceptable?
3. Open questions 4 to 10 in [open-questions.md](../open-questions.md) are unchanged.

## Later adjustments (2026-11-11)

- The header is two rows: the two projects and the Tour button on top, the chosen project's tabs in a row of
  their own beneath (32 px). Before, projects and tabs shared one row.
- The tour's last step selects Hurricane Beryl 2024 in Texas CRC data and plays it in the storm player
  (the player's whole window, 87 hours at 12 h/s). The tour runs about 41 seconds; `site/demo.webm` was
  re-recorded and its frames checked.
