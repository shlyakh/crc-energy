# V5: crc-lab split into projects

Built 2026-11-12. Nothing committed or pushed. A copy of the working tree from before this phase is at
`~/work/crc/backups/crc-lab-before-V5-2026-11-12.tgz` (45 MB, without caches and the environment).

## Result

The single page that held two projects is now three pages behind a landing page, and the Python code is
four packages that a test keeps apart.

| Address | What it is | Before |
| --- | --- | --- |
| `/` | Landing page: the projects, with links | The combined page |
| `/hail/` | Texas hail risk: Risk, Hail evidence, Methods | Project "Texas hail risk" on the combined page |
| `/validation/` | Source validation: inventory, assessments, findings | Unchanged address |
| `/validation/explore/` | Texas CRC data: Texas data, About | Project "Texas CRC data" on the combined page |

| Package | Project | May import |
| --- | --- | --- |
| `src/crc_lab/` | Texas hail risk (storm events, curves, plants, radar, impacts, risk layer) | `lab_common` |
| `src/crc_data_explorer/` | Texas CRC data explorer (was `crc_lab.explorer`) | `lab_common` |
| `src/data_source_check/` | Source validation | none of the others |
| `src/lab_common/` | Shared: version pins, Texas boundary and cells, file writers, site-check helpers | none of the others |

## What was done

- **Pages.** `site/hail/` and `site/validation/explore/` each have their own page and shell. The header
  of every page links to the landing page and to the other project.
- **Old addresses.** An address that carries a tab is forwarded with its state: `/#tab=risk&plant=…`
  goes to `/hail/`, `/#tab=crc&source=…` to `/validation/explore/`, and `/next/…` follows the same
  route. A tab asked of the wrong page is sent to the right one.
- **Tour.** It runs through the hail page and then moves to the explorer page for its last part
  (Hurricane Beryl 2024 in the storm player).
- **Assessments page.** Five sources (IBTrACS, NOAA water levels, GHCNh, ERA5, CRC Open) now link to
  their view on the map. The link is a new optional field `explorer` in the source file, so it comes
  from the records and is not typed into the page.
- **Python.** `explorer/risk_layer.py` moved to `crc_lab/risk_layer.py`. `texas.py` and the
  horizon-file writer moved to `lab_common`. The rest of `crc_lab.explorer` became `crc_data_explorer`.
- **Checks.** `just site` now runs three checks: `site-hail`, `site-explorer`, `site-validation`. Each
  covers its own page files, and the two map projects each cover the registry layers of their origin.
- **Workflow.** `.github/workflows/pages.yml` uses the new module names and runs the three checks.

## Decisions I took, for you to confirm

1. **The storm player keeps the hail project's storm reports.** It is on the explorer page and still
   draws the Storm Events layer built by the hail project, read from the shared data folder. The
   alternative is to drop the reports from the player; that would end the tour's last scene as it is.
2. **Shared parts stay shared.** The map viewer (`site/shared/`), the data folder (`site/data/`) and the
   layer registry (`site/layers.json`) serve both map pages. Splitting them would mean two copies of the
   viewer and changes to every build script. The registry's `origin` decides which page shows a source.
3. **The explorer's build code is its own package**, not part of `data_source_check`. That package may
   call crc-sdk only in `adapters/crc/` and imports nothing else from this repository; moving 1,200
   lines of crc-sdk calls into it would break both rules.
4. **The bare address opens the landing page.** It used to open the hail Risk tab. Addresses with a tab
   are forwarded.
5. **Names.** `crc_data_explorer`, `lab_common`, `/hail/`, `/validation/explore/`. All are easy to change now.

## Checks of the result

| Check | Result |
| --- | --- |
| `just test` | 175 passed (7 new: package import rules, site-check helper, forwarding code present) |
| `just lint` | Clean |
| `just site` | Three checks pass: hail 6 layers, explorer 13 layers, validation 3 assessed sources with records |
| Hail, explorer and landing pages in headless Chrome, 1440 wide (`tools/smoke.mjs`) | 205 of 205 checks, no console messages |
| Assessments page in headless Chrome (`tools/smoke-validation.mjs`) | 17 of 17 checks |
| Old addresses: plant, CRC source, wrong-page tab, `/next/` | Each forwards with its state (part of the 205) |
| Tour | Visits Risk, Hail evidence, Methods, then plays Beryl 2024 on the explorer page; no failed step |
| Same test at 390 wide, without the tour | 20 checks fail, the same 20 as on the copy from before the split |

The first browser run found one fault, since fixed: an old address pasted into an already open landing
page did not forward, because only the fragment changed.

## Not done, and limits

- **Phone width.** The two map pages were not built for a phone and fail the same 20 checks as before
  (sideways overflow, legend over the scale bar). The landing page and the assessments page fit.
- **The recorded tour** (`site/demo.webm`, shown in Methods) is the recording from before the split. It
  was not re-recorded.
- **Hail documents were not moved.** `docs/requirements.md`, `docs/reports/` and the rest stay where they
  are; only the validation project has its own folder (`docs/validation/`).
- **Older plans and reports** still name the old paths (`docs/handover-plan.md`,
  `docs/plan-explorer-next.md`, `docs/sources-track/`, phase reports). They describe the state at their
  date and were left. `AGENTS.md`, `docs/algorithms.md` and `docs/data-sources.md` are updated.
- **`README.md`** was already out of date before this phase (it describes Phase 1) and was not rewritten.
- **The Pages workflow was changed but not run.** It runs on push.
- **Data builds were not re-run.** The modules moved; the tests and the three site checks pass, and the
  build entry points import. A full `just all` needs the network and about an hour.
- `git mv` was used for the moves, so the renames are staged in the index. Nothing is committed.

## Open for your review

1. The five decisions above.
2. Whether hail documents should move to `docs/hail/`, to match `docs/validation/`.
3. Whether to re-record the tour now or after the next change to the pages.
4. `README.md`: I can rewrite it around the projects.

## Where the plan stands

V0 to V5 are built. Next: V6 (a drafting skill for an unassessed source; needs your choice of two
sources to try it on) and V7 (validation tier; needs your first criteria for climate projections).
