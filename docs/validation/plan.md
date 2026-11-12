# Plan: source validation project

Approved by Yuri on 2026-11-11. Copied from the planning session; progress is recorded in `reports/`.

## Context

Yuri wants crc-lab to hold several independent projects, and wants a new one: a detailed explorer of
crc-sdk's data connectors that (1) explores each source, (2) verifies it against the original and states
what crc-sdk does to the data, and (3) later validates that the data make sense and are used correctly.
New sources should be assessed semi-automatically and assessments re-run periodically. The long-term aim
is a formal validation tool for climate-risk frameworks in general.

Why it is worth doing (from this session's review of crc-sdk 0.11.1 and crc-lab):

- No crc-sdk test compares output with real source values; all use synthetic fixtures. crc-lab's own
  checks only confirm that the page matches crc-sdk.
- Many documented paths are never run upstream (ERA5 `tnn` and `rx5day`, three of four CMIP6 recipes, six
  of nine ECCC rainfall durations, NEX versions 1.1 and 1.2). The NEX temperature bug was found this way.
- Doc and code already disagree in places: the "at least 20 years" rule applies per request, and a grid
  cell is fitted with as few as 4 years; JRC flood and EDO files lack the licence and checksum the docs
  promise; ERA5 does not check source units; EDO's horizon is the last year, JRC's is 0.

Decisions from the interview:

| Question | Decision |
| --- | --- |
| Audience | Yuri first, before building on CRC; built to grow into a formal validation tool |
| Generality | CRC first, general by design: only the adapter that calls crc-sdk is CRC-specific |
| Repository | One repository, separate projects, each with its own package, docs, reports and page |
| First slice | IBTrACS (raw observations), GHCNh (stations to fitted curves), NEX-GDDP-CMIP6 (gridded) |
| Framework | SR 26-2 for structure and vocabulary; C3S and WMO practice for the checks |
| Tier 2 method | Written transformation statement plus an independent recompute on a seeded sample |
| Automation | Deterministic checks and a new-source detector first; an agent that drafts assessments later |
| Findings | Reported upstream and published in neutral wording with a status; no grades |
| Order | Tool first in its own folders; the split of the existing page comes after the first slice |
| Output | Machine-readable records; the page and the Markdown report are generated from them |

## Design

### Method (written down in V0 as `docs/validation/method.md`)

- **Three tiers.** Exploration; verification (does crc-sdk deliver what the publisher published, changed
  only in the ways stated); validation (are the values and the fitted curves fit for a stated use).
- **Where SR 26-2 applies.** Its model definition excludes deterministic data processing, so connectors
  get data verification; the distribution-fitting step is a model and gets validation (conceptual
  soundness, outcomes analysis). The method says so for each source. Borrowed from SR 26-2: an inventory,
  a statement of purpose per source, a materiality tier, ongoing monitoring, documentation, treatment of
  third-party data, review by a named person.
- **Check categories** from C3S: completeness, consistency, extremes, resolution, timeliness,
  uncertainty, validation; range and step tests from WMO practice.
- **Outcomes.** Each transformation step and check ends as `confirmed`, `differs`, `not checked` or
  `not applicable`. Each finding has a status: `open`, `reported upstream`, `fixed in <version>`,
  `by design`.
- **Sign-off.** A record is a draft until `reviewed_by` and `reviewed_on` are filled by Yuri.
- **Agents.** SR 26-2 leaves generative AI out of scope, so the rule is stated here: checks are
  deterministic code and decide the outcome; an agent may draft statements, reference code and criteria;
  a person reviews.
- Only framework texts read in the original are cited. SR 26-2 was read in full; the EBA, PRA, NGFS and
  ISO details from the research rest on secondary sources and are re-read before being cited.

### Layout (package `data_source_check`, named by Yuri 2026-11-12; first drafted as `sourcecheck`)

```
src/data_source_check/
  core/        records.py (record schema, versioned), inventory.py, compare.py (tolerances, sampling),
               report.py (Markdown from records), pagedata.py (page files from records)
  reference/   ibtracs.py, ghcnh.py, nex.py   independent readers; must not import crc_sdk
  adapters/crc/  enumerate.py (what crc-sdk offers), ibtracs.py, ghcnh.py, nex.py (calls crc-sdk)
  sources/     one file per source: purpose, tier, transformation statement (steps with code references)
  build.py     python -m data_source_check.build <source> [--live]
docs/validation/   method.md, requirements.md (IDs V1...), plan.md, inventory.md (generated), reports/
site/validation/   index.html, js/, data/ (generated records and page files)
tests/validation/  offline, on small fixtures
```

- No imports from the hail side (`assets`, `curves`, `impacts`, `radar`, `storm_events`) or from
  `crc_lab.explorer`; tiny helpers such as the atomic JSON writer are copied. A test enforces both this
  and the `reference/` rule, in the manner of the no-crc-imports guard in `tests/test_impacts.py`.
- Same `pyproject.toml` and environment as crc-lab for now. No new validation framework dependency in the
  first slice; pandera and pointblank are assessed in V4 once the record format has settled.

### Reused from what exists

- `src/crc_lab/storm_events/compare.py`: named comparisons, a conclusion generated from results, a "can
  be used for / cannot be used for" ending. The template for the generated report.
- `explorer/hazards.py` `verify_against_for_assets`: seeded sampling and `math.isclose` tolerances.
- `tools/probes/sources.py`: the crc-sdk calls for each source (starting point for the adapters).
- `explorer/tracks.py` `storm_records` and `site/js/views/` (`tracks.js`, `stations.js`, `charts.js`):
  the exploration views for storms and stations.
- crc-sdk's audit hooks: `prefetch()` manifests and `expected_sha256`, `annual_extremes()`, `explain()`,
  `metadata()` and `provenance()`, `curve_quantiles`.
- `crc_lab.PINNED` for versions in every record.

## Phases

Each ends with a report in `docs/validation/reports/` and a stop for review.

### V0. Method, records and inventory

- `method.md`, `requirements.md`, `plan.md` under `docs/validation/`.
- Record schema with tests. Inventory of all 20 crc-sdk sources (entry point, kind, publisher, purpose,
  tier, status `not assessed`), generated from `adapters/crc/enumerate.py`, which reads the
  `HazardDataset` constructors, `crc_sdk.workflows.__all__` and the recipe and dataset tables.
- Detector: any source or recipe crc-sdk offers that has no assessment is listed.
- Empty page at `site/validation/` showing the inventory. AGENTS.md gains a section for the project.
- The doc and code disagreements already known are entered as findings with status `open`, each with its
  file and line, and are not yet reported upstream.

### V1. IBTrACS (pass-through source)

- **Explore:** storms, points, years, columns, missing values; the existing track map.
- **Statement:** columns kept as strings, whitespace trimmed, empty to null, units row kept in the
  manifest, filters by storm and season.
- **Recompute:** download the same NCEI file with the standard library, parse it with `csv`, apply the
  stated rules, and compare with `IBTrACSPlan` batches: bytes (SHA-256), column set and order, row count,
  every value on a seeded sample of storms and all values for one season, both filters.
- Sets the pattern for the other pass-through sources.

### V2. GHCNh (stations to fitted curves)

- **Explore:** stations in the test area, record lengths, yield (why 40 stations gave 8 curves).
- **Statement:** columns read, quality-code rule, range limits, UTC day, 18 valid hours per day, 90 per
  cent of days per year, annual maximum or minimum, location rule, fit family and method.
- **Recompute:** for a seeded sample of stations, read NOAA's by-year files directly, apply the stated
  rules, and compare the annual extremes with crc-sdk's `annual_extremes()` table, for both
  `temperature_max` and `temperature_min`. Check that the stored curve reproduces its own samples at the
  policy's return periods.
- The fit itself (family choice, behaviour with short records) is marked `not checked` here and belongs
  to tier 3.

### V3. NEX-GDDP-CMIP6 (gridded projections)

- **Explore:** models, scenarios, versions and years offered; one year's field over the test area.
- **Statement:** file selection and version rule, attribute checks, unit conversion, completeness rule,
  annual statistic, pixel-centre output, licence handling.
- **Recompute:** for sampled pixels, read the NASA file directly and compute the annual value; compare.
  Cover all four recipes, one SSP year and file versions 1.1 and 1.2 where they exist.
- At the pinned crc-sdk the temperature recipes fail; that is recorded as a finding linked to the fix
  (`docs/reports/u1-nex-bytes-fix.md`), and the comparison for them is run against the fixed clone and
  labelled so.

### V4. Monitoring

- A scheduled workflow (weekly, and on a pin change) re-runs the live checks, compares records with the
  previous run (publisher file changed, values drifted, check newly failing) and lists unassessed
  sources. It reports; it does not publish a new assessment without review.
- Decide on pandera or pointblank for schema checks and the HTML report, from experience with V1 to V3.

### V5. Split crc-lab into projects

- Landing page linking to the projects; Texas hail risk on its own page; today's "Texas CRC data" tab
  folded into the validation tool; old links forwarded.
- Move `explorer/risk_layer.py` to the hail side; shared helpers (`texas.py`, the horizon-file writer)
  into a small common package; split `check_site.py`, the `justfile` and the Pages workflow by project.
- The storm player's use of hail-project storm reports is decided here.

### V6. Drafting agent for new sources

- A Claude Code skill that, for an unassessed source, drafts the source file (purpose, statement), the
  reference reader and the comparison, using V1 to V3 as examples. Drafts are marked unreviewed until
  signed. Tried first on one pass-through source and one fitted source.

### V7. Validation (tier 3)

- Criteria per source kind, starting with climate projections, where Yuri supplies the first criteria.
  Candidates from the research: physical range, internal consistency (maximum not below minimum),
  climatology against a reference, direction of change under a warming scenario, an independent fit as a
  challenge to crc-sdk's, record length behind each fit.
- CRC Open is assessed here: its inputs are not public, so it cannot have a tier 2 comparison.

Afterwards: the remaining sources in order of materiality; a second framework to test the generality;
moving the tool to its own repository.

## Parked, not part of this plan

- NEX fix: built and checked, uncommitted in `~/work/crc/forks/crc-sdk`; needs Yuri's go to commit,
  fork, push and open the pull request.
- Storm Events adapter: `docs/plan-upstream-storm-events.md`.
- Phase 7 (loss from radar hail).

## Verification

- `just test` and `just lint` pass; validation tests are offline on small fixtures.
- For each source a test with a deliberately wrong reference rule (for example a unit factor off by one
  step) must end as `differs`: a check that cannot fail proves nothing.
- The import-guard test passes (`reference/` has no crc-sdk import; the project has no hail-side import).
- Live run per source (`python -m data_source_check.build <source> --live`) writes records; the page and the
  report regenerate from them with no hand edits; a second run on unchanged inputs gives identical
  records apart from timestamps.
- The page is checked in headless Chrome (`tools/smoke.mjs` extended for `site/validation/`).
- The existing site and its build are unchanged until V5.
