# Report V0: method, record format and inventory

Date: 2026-11-11 · crc-sdk 0.11.1, crc-framework 0.6.0 · awaiting review

Phase V0 of the [plan](../plan.md) is built. No source is assessed yet: this phase sets up the method, the
record format, the inventory and the page that later phases fill. Nothing is committed or pushed.

## What was built

| Piece | Where | What it does |
| --- | --- | --- |
| Method | [method.md](../method.md) | Three tiers, the verification procedure, the mapping to SR 26-2, tiers of materiality, check categories, findings and sign-off, the rule for AI agents |
| Requirements | [requirements.md](../requirements.md) | IDs V1 to V42 by phase |
| Record format | `src/data_source_check/core/records.py` | Source, transformation step, check record, finding; refuses records without evidence, versions or a reason |
| Inventory | `src/data_source_check/sources/crc_sdk/*.toml` | 20 entries: 19 sources and "your own data" |
| Detector | `src/data_source_check/adapters/crc/enumerate.py`, `core/inventory.py` | Reads what the installed crc-sdk offers and lists what the inventory does not cover |
| Findings | `src/data_source_check/sources/crc_sdk/findings.toml` | 9 findings known before any check is run |
| Build | `just validation` | Writes `site/validation/data/inventory.json` and [inventory.md](../inventory.md); no network |
| Page | `site/validation/` | Inventory with details per source, findings, what is not yet assessed |

## The inventory

| Tier | Sources |
| --- | --- |
| 1 (in use here, or the main release) | CRC Open, ERA5, IBTrACS, NOAA CO-OPS extreme water levels, NOAA GHCNh |
| 2 (reduced or fitted, not relied on here) | CMIP6, ECCC IDF, JRC EDO, JRC flood, NEX-GDDP-CMIP6, NOAA ISD, OS-Climate |
| 3 (passed through, not used here) | CHIRPS, ECCC daily, HYDAT, Fields of The World, NOAA sea-level scenarios, USDA CDL, USGS streamflow |

By kind: 9 pass-through, 8 fitted curves, 1 annual samples (NEX), 1 pre-fitted release (CRC Open), 1 user
data.

The tier rule and the tier of each source are my proposal and are yours to change.

## The detector

Run against the installed crc-sdk 0.11.1:

| Check | Result |
| --- | --- |
| Entry points found (constructors of `HazardDataset` and `AgriculturalLayer`, exported plans) with no inventory entry | 0 |
| Option values in crc-sdk's own tables that the inventory does not list | 0 |
| Option tables that could not be read | 0 |
| Sources with no assessment | 19 of 19 |
| Option values (recipes, datasets, versions) not assessed | 56 |

A test fails if a crc-sdk upgrade adds an entry point or an option value that the inventory does not know.

Limits of the detector:

- crc-sdk has no registry of sources. The detector reads three places and would miss a source added in a
  fourth (OS-Climate, for example, is reached through `crc_sdk.providers`, not through a plan or a
  constructor).
- Some option lists are hard-coded upstream and cannot be read: NEX scenarios and file versions, ECCC IDF
  versions, the station recipes. They are listed in the inventory by hand.

## Findings entered

All at crc-sdk 0.11.1, all `open`, none reported upstream yet.

| Id | Source | Kind | Finding | Basis |
| --- | --- | --- | --- | --- |
| CRC-001-NEX | NEX-GDDP-CMIP6 | defect | Temperature recipes fail on real files | reproduced |
| CRC-002-FWK | all gridded | doc-code difference | The 20-year minimum counts years requested; a cell is fitted with as few as 4 | code reading |
| CRC-003-JRC | JRC flood, EDO | doc-code difference | Output files lack licence, attribution, retrieval time, checksum | code reading |
| CRC-004-EDO | JRC EDO | doc-code difference | Curves labelled with the last year, not the centre year | code reading |
| CRC-005-EDO | JRC EDO | observation | Annual minimum has no completeness rule | code reading |
| CRC-006-ERA5 | ERA5 | observation | Values converted without checking the declared unit | code reading |
| CRC-007-OPEN | CRC Open | observation | `retrieved_at` is the time the file was written | code reading |
| CRC-008-OSC | OS-Climate | doc-code difference | Licence documented as read from metadata; no such code found | code reading |
| CRC-009-CDL | USDA CDL | observation | Read from a moving branch; no provenance in the output | code reading |

Each has its file and line in [inventory.md](../inventory.md). I read every cited line myself. Eight of the
nine rest on reading the code and are not yet shown on data; CRC-008-OSC rests on a search of one file only.
The research pass listed a few more candidates that I left out because I had not read the lines or could
not call them a disagreement (JRC flood's horizon of 0, the NEX plan having no `explain()`, the flood
policy not using the censored fit its docs recommend).

## Checks

| Check | Result |
| --- | --- |
| `just test` | 129 passed (37 of them new, in `tests/validation/`) |
| `just lint` | Clean |
| Import rules (core and reference import no framework; nothing imports `crc_lab`) | Pass |
| Page in headless Chrome, 1440 and 390 wide (`tools/smoke-validation.mjs`) | 10 of 10 checks, no console messages |
| Existing site check (`just site`) | Unchanged: complete, 18 layers |

## Departures from the plan

- The plan said versions would come from `crc_lab.PINNED`. They are read from the installed packages
  instead, so that the package imports nothing from `crc_lab`.
- The existing `tools/smoke.mjs` was not extended; the validation page has its own small script, so the
  two projects' checks stay separate.
- Source files are TOML (read with the standard library), one per source.

## Open for your review

1. **Method.** Is the split between verification and validation, and the mapping to SR 26-2 in section 3
   of the method, what you had in mind? The framework readings come from the research pass; you may want
   to check SR 26-2 yourself before it is cited outside this repository.
2. **Tiers.** The rule in section 4 of the method and the tier of each source.
3. **Name.** `sourcecheck` was the working name (renamed `data_source_check` on 2026-11-12).
4. **Findings.** They are on the page as soon as this is pushed (the repository and the page are public).
   You chose to publish neutrally and report upstream; nothing has been reported yet. Say if any should
   wait or be reworded before the push.
5. **Deployment.** `site/validation/` is committed data and deploys with the existing workflow at
   `/validation/`; no workflow change was made. The page's "Method" and "Inventory as text" links point to
   the files on GitHub and work once pushed.

## Next: V1, IBTrACS

Exploration, the transformation statement, and the independent recomputation from NOAA's file, which sets
the pattern for the other pass-through sources. Not started.
