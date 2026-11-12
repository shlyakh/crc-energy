# Requirements: source validation project

Version 0.2, 2026-11-12. Method: [method.md](method.md). Plan: [plan.md](plan.md).

IDs use the prefix V. "Done" is marked when the phase report says so.

## General

| ID | Requirement | Phase | Done |
| --- | --- | --- | --- |
| V1 | An inventory lists every source the framework offers: entry points, kind, publisher, original, purpose, tier, status per assessment tier | V0 | yes |
| V2 | The inventory is checked against the installed framework: an entry point or option value with no entry is reported, and a test fails | V0 | yes |
| V3 | Records follow one versioned format; a record that omits evidence, versions or a reason is refused | V0 | yes |
| V4 | The page and the Markdown reports are generated from records only | V0 | yes (inventory and findings) |
| V5 | Findings are worded neutrally with documented, observed, consequence, evidence, basis and status; no grades | V0 | yes |
| V6 | An assessment is a draft until signed by a named person, and is shown as a draft | V0 | yes |
| V7 | The core and the reference readers import no framework; the project imports no other crc-lab project code; a test enforces it | V0 | yes |
| V8 | Every record carries the framework versions and the time of the run | V0 | yes |
| V9 | Nothing is reported upstream before Yuri has reviewed the draft; drafts are kept locally, uncommitted | V1 | yes |

## Per source (tiers 1 and 2)

Done for IBTrACS (V1), GHCNh (V2) and NEX-GDDP-CMIP6 (V3), all 2026-11-12: V10 to V17.

| ID | Requirement | Phase |
| --- | --- | --- |
| V10 | Exploration: counts, coverage, missing values and one map or chart per source | V1 to V3 |
| V11 | A transformation statement: every step with its code reference | V1 to V3 |
| V12 | An independent recomputation on a seeded sample, from the publisher's files, with a stated tolerance | V1 to V3 |
| V13 | Each statement step ends as confirmed, differs, not checked or not applicable | V1 to V3 |
| V14 | For each comparison, a test with a deliberately wrong reference rule ends as differs | V1 to V3 |
| V15 | Inputs are recorded with URL, checksum and retrieval time | V1 to V3 |
| V16 | A second run on unchanged inputs gives the same records apart from timestamps | V1 to V3 |
| V17 | Options exercised are recorded; options not exercised stay listed as not assessed | V1 to V3 |

## Monitoring and automation

| ID | Requirement | Phase |
| --- | --- | --- |
| V20 | Scheduled check (weekly, and on a pin change) for changed publisher files, versions and inventory gaps; a re-run compares records with the previous run | V4, done 2026-11-12 (workflow not yet pushed) |
| V21 | A re-run never publishes a changed assessment without review | V4, done 2026-11-12 |
| V22 | A drafting skill produces an unreviewed draft assessment for an unassessed source | V6, built 2026-11-12 (skill, draft folder, gate, acceptance by a person); trials in the V6 report |

## Structure

| ID | Requirement | Phase |
| --- | --- | --- |
| V30 | crc-lab holds separate projects, each with its own package, docs, reports and page, behind a landing page | V5, done 2026-11-12 (the map viewer, the data folder and the layer registry stay shared; hail documents were not moved) |
| V31 | Existing links keep working | V5, done 2026-11-12 (addresses with a tab are forwarded; the bare address now opens the landing page) |

## Validation (tier 3)

| ID | Requirement | Phase |
| --- | --- | --- |
| V40 | Criteria are written per kind of source, starting with climate projections | V7 |
| V41 | The fitting step is challenged: family, method, record length behind each fit | V7 |
| V42 | CRC Open is assessed by validation, since its inputs are not public | V7 |
