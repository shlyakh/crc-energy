# Plan: explorer improvements after Phase 5

Draft for review, 2026-11-10. Nothing here is started. It is a list to choose from, not a commitment: mark
what you want, strike what you do not, add what is missing.

## Where the explorer stands

Nine sources in two groups, a map, a storm player with a timeline, a comparison map for four hail records, a
plant panel with value, hail, radar and (since Phase 5) loss, an About tab and a 30-second demo. It is a static
site with no build step, and that should not change.

It grew one feature at a time. Three problems are visible now:

1. **The controls are below the fold.** The source list fills the left column. On a 900-pixel-high window the
   controls and legend of the selected source sit under nine source cards and need scrolling to reach.
2. **The plant panel is a long list.** It has 7 groups and up to 46 lines. The two numbers a reader wants
   first, chance of damaging hail and expected loss, are in the middle.
3. **Loss cannot be seen on the map.** Phase 5 gives every plant an expected loss, but all plants are the same
   yellow dot. The answer to "which plants are most at risk" needs a click on each one.

## Proposed work, in suggested order

### Step 1. Make loss visible (about a day)

- **Size and colour the plants.** Dot area by capacity or value; colour by a chosen measure: expected loss in
  dollars, loss as a share of value, chance of 2-inch hail, radar hail days. One selector, one legend.
- **A switch between "reports as they are" and "bias-corrected"** that applies to the map colours and the
  panel together. You asked to see both; today they are two blocks of text.
- **A ranked plant table** beside the map: name, capacity, value, loss, sortable, click to fly to the plant.
- **A summary line**: plants shown, total value, total expected loss, under the current switch.

### Step 2. Rework the plant panel (about a day)

- **Headline first**: three or four large figures (value, chance of 2-inch hail a year, expected loss a year,
  largest radar hail seen), then the detail groups collapsed.
- **Assumptions in one place**: glass type, stow, cost share, footprint, each marked "placeholder" or
  "reported", so nobody reads a placeholder as a fact.
- **Small charts instead of lines of numbers**: the plant's hail-size distribution; the damage curve with the
  plant's reports marked on it; reports, corrected reports and radar as three bars.
- **Show the circle.** Draw the plant's report circle and the reports inside it on the map when the plant is
  selected. This is the clearest way to explain where the numbers come from.

### Step 3. Layout (about a day)

- **Compact source list**: one line per source with the group badge; the description opens on selection. The
  controls and legend of the selected source then fit on the first screen.
- **A link to the current view**: source, layer, plant, storm and switches kept in the address, so a view can
  be sent to someone. Today every visit starts at storm tracks.
- **Phone layout**: the side column becomes a bottom sheet. Swipe-line dragging by touch gets tested here.

### Step 4. Damage curves explained (half a day)

- **A curves page**: the four v0 curves drawn, with their knots, their source tags and the placeholders marked,
  built from the same data file as the code. A slider for stow angle and stow chance shows how the solar curve
  moves. This is the page to show someone who asks "where does the loss number come from".

### Step 5. Open items from earlier rounds (half a day in total)

- Comparison map: scale default, ratio default, demo step (questions 1 to 3 in
  [open questions](open-questions.md)).
- Storm player: fading reports, reports near the track only, window length, outer storm size, the events file
  size (question 10).
- About tab: a computed count line for the comparison source; the colour check for the four bar colours.
- Re-record the demo once, after the steps you choose are done.

### Later, each needing a decision first

- **Radar hail swaths in the storm window**: play a hail day and see the radar swath cross the plants, with
  the reports on top. Needs radar tiles small enough for a static site; the daily grids are too large to ship
  whole, so this would cover chosen days only (for example 16 March 2024).
- **Buildings** on the map, if a building asset set is built (question 9).
- **Scenario view**: "what if a 2-inch storm crosses this plant", using the damage curve directly, beside the
  annual figures.

## What would not change

- Static files, no build step, libraries pinned by address.
- Curves and losses computed in Python and shipped as values; the page never re-implements a curve.
- The registry (`site/layers.json`) stays the one place a source, layer or panel is declared.
- The smoke test walks every source after each change.

## Questions

1. Is the order right? Step 1 gives the most for the least work; step 3 fixes what is most awkward today.
2. For plant colours, which measure should be the default: loss in dollars, or loss as a share of value?
3. Is a phone layout wanted at all, or is this a desktop tool?
4. Should the curves page live in the explorer, or in `docs/` as a static report?
