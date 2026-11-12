# Method: exploring, verifying and validating climate-risk data sources

Version 0.2, 2026-11-12. Draft: not yet reviewed by Yuri. (0.2: SR 26-2 kept in the repository and read in
full; review before anything is reported upstream; package renamed `data_source_check`.)

This is the method of the source validation project in crc-lab (package `data_source_check`, page
`site/validation/`). The first framework assessed is crc-sdk, the data layer of Climate Risk Commons. The
method and the record format are written so that another framework's sources can be assessed the same way.

## 1. What is assessed, and why

A climate-risk framework takes data from publishers (NOAA, NASA, ECMWF, JRC and others) and hands its
user something else: reformatted records, annual extremes, or fitted hazard curves on grid cells. A user
who builds a risk estimate on that output is relying on three things at once: the publisher's data, the
framework's processing, and the fit between the result and the user's purpose. This method takes them
apart.

The unit of assessment is a **source**: one publisher's dataset as reached through one framework entry
point, with the options that entry point offers (recipes, datasets, versions).

## 2. Three tiers

| Tier | Question | Evidence |
| --- | --- | --- |
| **Exploration** | What is there? | Counts, coverage in space and time, missing values, a map or chart |
| **Verification** | Does the framework deliver what the publisher published, changed only in the ways it states? | A transformation statement, and an independent recomputation of a sample from the publisher's files |
| **Validation** | Are the values and the fitted curves fit for a stated use? | Checks of plausibility, comparison with reference data, and challenge of the fitting choices |

Verification is about fidelity and can be settled: a value either matches the publisher's or it does not.
Validation is about fitness for a purpose and ends in a judgement with stated limits.

### Verification in two parts

1. **Transformation statement.** Every step the framework applies between the publisher's bytes and its
   output is written as one line with its code reference: selection, decoding, quality rules, unit
   conversion, aggregation in time, assignment to cells, fitting, renaming, provenance recorded.
2. **Independent recomputation.** A sample (stations, cells, storms, years) is drawn with a recorded seed;
   where the whole file can be compared cheaply, all of it is, and the record says so.
   The publisher's files are read by code that shares nothing with the framework, the stated steps are
   applied, and the result is compared with the framework's output within a stated tolerance.

Each step of the statement then carries one outcome:

| Outcome | Meaning |
| --- | --- |
| `confirmed` | The recomputation agrees with the framework within the tolerance |
| `differs` | It does not; a finding is opened |
| `not checked` | No check bears on this step yet; the record says why |
| `not applicable` | The step does not arise for this source |

A check that cannot fail proves nothing. Every comparison therefore has a test in which the reference rule
is deliberately wrong and the outcome must be `differs`.

## 3. Relation to model risk guidance (SR 26-2)

The structure follows the interagency *Supervisory Guidance on Model Risk Management* attached to Federal
Reserve letter SR 26-2 (17 April 2026), which replaced SR 11-7 and SR 21-8. It is guidance for banks
(most relevant above $30 billion in assets), it sets no enforceable standard, and it binds no one here. It
is used because its vocabulary is widely understood by people who rely on models. The letter and the
guidance are kept in [references/sr-26-2/](references/sr-26-2/README.md), with the page of each passage
used below.

| SR 26-2 | In this method |
| --- | --- |
| Model inventory | The inventory: every source with its entry points, kind, purpose, tier and status (`docs/validation/inventory.md`, generated) |
| Statement of purpose | `purpose` of each source: what the framework's own documentation says it is for |
| Materiality (purpose and exposure) | The tier of each source (section 4) |
| Conceptual soundness | Validation of the fitting step: family, method, record length, treatment of missing data |
| Outcomes analysis | Validation against reference data and published values |
| Ongoing monitoring | Scheduled re-runs; comparison of records between runs; detection of new sources and options |
| Documentation | Records, and the page and reports generated from them |
| Vendor and third-party products (data, parameters, models) | Each publisher's dataset is third-party data to the framework; the framework's output is third-party data to its user |
| Effective challenge | Each assessment is reviewed and signed by a named person; the reference code is independent of the framework |

Two limits of that mapping are stated here so they are not overlooked:

- **Not every source is a "model".** SR 26-2 defines a model as a complex quantitative method applying
  statistical, economic or financial theory, and excludes simple arithmetic and deterministic rule-based
  processing. A connector that downloads and reformats is data processing; it gets verification. The step
  that fits a distribution to annual extremes is a model in that sense; it gets validation. Each source
  record says which parts are which.
- **Generative and agentic AI are outside SR 26-2's scope.** Section 7 sets this project's own rule.

## 4. Materiality tiers

A tier orders the work; it is not a grade of quality.

| Tier | Rule |
| --- | --- |
| 1 | Feeds a crc-lab result today, or is the release most users of the framework consume |
| 2 | Reduced or fitted by the framework, but no crc-lab result depends on it yet |
| 3 | Passed through without fitting, and not used in crc-lab |

The tiers are provisional and are Yuri's to change. "User data" entry points have no tier.

## 5. Check categories

Categories follow the Copernicus C3S quality assessments, with one added for tier 2.

| Category | Typical check |
| --- | --- |
| completeness | Coverage in space and time; share of missing values; years behind each fit |
| consistency | Units, calendars, internal relations (a daily maximum not below the minimum) |
| extremes | Plausible range of extremes; behaviour of the fitted tail |
| resolution | Native grid against delivered cells; what a cell value represents |
| timeliness | Lag behind the publisher; whether files are rewritten in place |
| uncertainty | What spread or confidence is available, and whether it is carried through |
| validation | Agreement with independent reference data |
| fidelity | Agreement with the publisher's original (tier 2) |

Range, step and neighbour tests follow common practice for climate station data (WMO guidance on quality
control). The specific criteria for tier 3 are written per kind of source when that tier starts, beginning
with climate projections.

## 6. Records, findings and sign-off

Everything shown on the page or in a report is generated from records; nothing is typed into a report by
hand. The format is defined in `src/data_source_check/core/records.py` (schema `data_source_check/0.1`).

- **Source**: an inventory entry, with its transformation statement once written.
- **Check record**: one run of one check: method, inputs with checksums, sample and seed, tolerance,
  result, outcome, versions of the framework, time of the run.
- **Finding**: something a user of the source should know.

Findings are worded neutrally: what the documentation says, what the code or the data shows, and the
consequence. There are no scores or grades.

| Field | Values |
| --- | --- |
| Kind | `defect` (the framework fails or returns wrong values), `doc-code difference`, `observation` |
| Basis | `reproduced` (shown on data or by a failing test), `code reading` (read in the code, not yet shown on data) |
| Status | `open`, `reported upstream`, `fixed` (with the version), `by design` (the maintainers confirm it is intended) |

**Reporting upstream.** Nothing is sent to a framework's maintainers (issue, pull request or message) until
Yuri has reviewed the draft. Drafts are kept for him in `local/upstream-review.md`, which is not committed.
A finding's status stays `open` until he sends it. A finding stays visible after it is fixed, with the
version that fixed it.

**Publication.** Findings are public for now, on the page and in this repository. Yuri may later keep
them on a branch or release them privately; the records do not depend on where they are shown.

**Sign-off.** An assessment is a draft until `reviewed_by` and `reviewed_on` are filled. The page marks
drafts as drafts.

## 7. Use of AI agents

- Checks are deterministic code. The outcome of a check is decided by the comparison and its tolerance,
  never by a language model.
- An agent may draft a transformation statement, a reference reader, a comparison or proposed criteria.
  Drafts are marked unreviewed until a named person signs them.
- Reference code written with an agent's help is reviewed like any other and must pass the
  deliberate-fault test.
- An agent's draft follows the skill `draft-source-assessment`. The source file names the drafter
  (`drafted_by`). The draft's records are written to a folder outside the page and reach the page only
  when a person runs `just validation-draft-accept <id>`. A deterministic gate
  (`just validation-draft-check <id>`) says whether a draft is complete; it does not say whether the
  framework is right. A draft adds no finding: it lists candidates in its note for the person to enter.

## 8. Independence

- `data_source_check/reference/` reads the publishers' files and must not import the framework under test.
- `data_source_check/core/` must not import any framework.
- The project imports nothing from crc-lab's other projects.

A test enforces all three (`tests/validation/test_data_source_check_inventory.py`).

## 9. Monitoring

Assessments are re-run on a schedule and whenever the pinned framework version changes (phase V4). A
re-run compares its records with the previous run: publisher file changed, values moved, check newly
failing. The detector lists entry points and option values the framework offers that the inventory does
not cover. A re-run reports; it does not publish a changed assessment without review.

## 10. What this method does not claim

- It is not a certification of any framework or dataset.
- A `confirmed` outcome covers the sample, the options and the framework version in the record, no more.
- Verification says nothing about whether the publisher's data are right.

## Sources of the method

Read in full from the original, and kept in this repository (Yuri has not yet checked the readings):

- Federal Reserve, FDIC and OCC, SR 26-2, *Revised Guidance on Model Risk Management*, 17 April 2026, with
  its attachment: <https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm>; copies and the
  passages used in [references/sr-26-2/](references/sr-26-2/README.md)

Opened in the original by the research pass, not re-read since:

- Copernicus C3S quality assessment notebooks (assessment categories):
  <https://github.com/ecmwf-projects/c3s2-eqc-quality-assessment>

Consulted through summaries only, and to be re-read before they are cited for anything specific: WMO-No.
1269 (quality control of station data), ISO 19157-1:2023 (data quality elements), BCBS 239 and the ECB
guide on risk data aggregation, PRA SS1/23 (model risk principles).
