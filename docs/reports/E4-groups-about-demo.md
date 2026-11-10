# E4 report: source groups, About page and demo mode in explorer v2

Date: 2026-11-10 · branch `explorer-v2` (not merged) · follows [E3-time-and-extent.md](E3-time-and-extent.md) ·
awaiting review; Yuri is "ready to merge this soon".

## What was added

1. **Two source groups, as data.** `site/layers.json` has a `groups` list (id, title, badge text, one-line
   explanation, colour) and every source an `origin`:
   - **Reached through crc-sdk** (badge "crc-sdk", blue `#2a78d6`): IBTrACS, NOAA CO-OPS, GHCNh stations,
     ERA5 baseline, CRC Open.
   - **New in this project** (badge "new here", orange `#eb6834`): NOAA Storm Events reports and the hail and
     gust curves fitted from them.
   The two hues pass the palette validator together (colour-vision separation, contrast on the surface) and
   every badge carries its text label, so colour is never the only signal. The grouping shows in four places:
   the source list (group heading with badge and explanation, and a coloured left edge on each source card),
   the active source's header, the first line of the caveat panel, and a Group column in the Sources tab.
   Order: the crc-sdk group first, with IBTrACS still the default view; CRC Open stays labelled as
   RiskThinking.AI CMIP6-based projections and sits last in its group.
2. **About tab.** Built in the page from the registry and the data files at load time; no number is typed in.
   Sections: what this page is (crc-lab, Yuri Shlyakhter, repository link, demo button and recording);
   Climate Risk Commons and crc-sdk; the two groups with each source and its current counts; how to use it;
   what the numbers mean and do not mean; licences and attribution per source; versions and build; links to
   the reports.
3. **Demo mode.** "Play demo" in the header and on the About tab, or `?demo=1` in the URL. It drives the real
   page with a caption bar, a progress bar, Pause and Stop, and Escape to exit; afterwards it restores the
   default source, filters and view. Eight steps: cyclone tracks overview (3 s) → Harvey 2017 with its wind
   extent (4 s) → the storm played with reports and the timeline (7 s) → Storm reports with the March 2024 hail
   window (5 s) → hail curve layer with the cell of the highest 1-in-100-year value and its curve (4 s) → CRC
   Open as one source (3 s) → Sources tab (2 s) → end card (2 s). The tour's storm, window and curve layer are
   in the registry (`demo`). Files are preloaded first; a step whose file failed to load is skipped with a
   note in the caption. With `prefers-reduced-motion` the tour does not autoplay: each step shows its end state
   and waits for "Next".
4. **Recording.** `tools/record-demo.mjs` runs `?demo=1` in headless Chrome, takes JPEG screenshots with their
   real timestamps and lets ffmpeg (already on this machine, nothing installed) assemble them: `site/demo.webm`,
   VP9, 1280×800, 30.9 s, 1.0 MB, about 9 frames per second (software rendering). It is linked from the About
   tab and declared in the registry (`demo.video`), and `check_site` requires the file when declared.

## Checks

| # | Check | Result |
| --- | --- | --- |
| 1 | Groups and badges | Two group headings ("crc-sdk", "new here"); badge on the active source header and in the caveat panel; badges in the Sources tab. |
| 2 | About tab | Eight sections render; counts read from the files (e.g. 91 storms, seasons 1954–2024, 30 with wind radii; 166,214 reports, 107,549 with a point); versions and build date from the manifest. |
| 3 | `?demo=1` | Reaches the end card in **31.5 s** (two runs: 31,553 and 31,522 ms, including preloading), no console messages or errors; afterwards the demo bar is hidden, the Map tab and the default source are back, and switching source works. |
| 4 | Escape | Stops a running demo and restores the page. |
| 5 | Earlier checks | The whole smoke test still passes (sources, player, timeline, date window, curves, CRC Open, overlays); 32 tests; `ruff` clean; `just site` complete. |

## Not verified

- The demo under `prefers-reduced-motion` was not driven in the smoke test (the code path is simple: no
  animation, a Next button).
- Demo timing and the recording are from headless Chrome with software rendering on this Mac; a slow network
  would lengthen the preload, which the 30 s do not budget for beyond what was measured locally.
- The video was checked by looking at frames, not watched end to end in a browser.

## What merging explorer-v2 into main requires

- **Data in CI.** Main's Pages workflow builds CRC Open, Storm Events and the curves. This branch also needs
  `just sources`: IBTrACS (seconds, a 55 MB download), CO-OPS (seconds), GHCNh (about 4 minutes for the 40
  stations tried) and ERA5 (about 11 minutes uncached). Either add that step to the workflow (about 15 more
  minutes per deploy) or commit the small built files under `site/data/sources/` (about 0.6 MB) and rebuild
  them by hand when a source changes.
- **`demo.webm`** is committed under `site/` (1.0 MB) and must be re-recorded when the page changes
  (`node tools/record-demo.mjs <dir> <url>`), or dropped from the registry.
- **The `/v2/` preview** (branch `explorer-v2-site` and the copy step in main's workflow) becomes redundant.
- **Conflicts**: `site/app.js`, `site/index.html`, `site/layers.json` and `tools/` are rewritten here; main
  has not changed them since Phase 3 was merged into this branch, so the merge should be clean today.
- The events layer file is now 5.3 MB (was 2.6 MB) and its record layout changed; anything else reading
  `events.bin` must read the layout from `index.json`.

## Next iteration (deferred by Yuri 2026-11-10)

The five questions from the E3 round, verbatim, deferred by Yuri 2026-11-10:

1. Should reports fade after a while instead of staying on the map?
2. In storm mode, should reports be limited to those near the track or inside the 34 kt band, rather than all of Texas?
3. Is the Texas stretch plus one day the right player window, or should it span the whole shown track?
4. Should the outermost closed isobar or radius of maximum wind also be drawn, at least for the 16 storms that have radius of maximum wind but no 34 kt radii?
5. `events.bin` doubled to 5.3 MB. Is that acceptable, or should the unlocated events go in a separate file loaded only for the timeline?
