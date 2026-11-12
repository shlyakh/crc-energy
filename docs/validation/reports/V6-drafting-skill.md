# V6: a skill that drafts the assessment of a new source

Built 2026-11-12. Nothing committed, pushed or sent upstream. Both trial drafts are unreviewed and
neither is published on the page.

## Result

A fresh agent, given only the skill and a source id, produced a complete draft assessment in about
20 minutes for each of two sources. Both drafts pass the gate, their tests and lint. Each found things
worth a person's attention. The trials also showed five faults in my skill and tooling, now fixed.

| | NOAA water levels (pass-through) | ERA5 (fitted curves) |
| --- | --- | --- |
| Statement steps | 14 | 21 |
| Sample | 25 stations (all 10 in Texas, 14 others by seed, 1 unlisted) | Rainfall recipes `rx1day`, `rx5day`, store `wb2-1p5`, Texas box (80 cells), 2021 |
| Checks | 11: 11 confirmed | 9: 8 confirmed, 1 differs |
| Values compared, crc-sdk against the independent recomputation | 16,776; 0 differ | 1,208 annual and 1,393,920 hourly; 0 differ |
| Steps | 11 confirmed, 3 not checked | 13 confirmed, 2 differ, 6 not checked |
| Offline tests | 45 pass | 35 pass |
| Downloaded | 1.7 MB | 897 MB |
| Candidate findings in the note | 8 | 6 |
| Agent's working time | 17 minutes | 24 minutes |

The numbers are the agents' own, copied from their draft records and notes. I re-ran the tests, lint
and the gate and read both notes; I did not re-derive their findings.

## What the drafts found (candidates, for you to judge)

**NOAA water levels** (`docs/validation/drafts/noaa-water-levels.md`)

- NOAA sometimes answers the same address with two different bodies, one rounded to one decimal. In
  the first live run 3 of 69 responses differed between the two downloads (187 values, at most
  0.05 m); in the second run none did. Asked 60 times, one address gave the rounded body 4 times.
  crc-sdk asks once and delivers what it received.
- A listed Texas station (8778490 Port Mansfield) is refused by crc-sdk with a message about a
  mismatch; NOAA's own answer says the datum is not available for the product.
- The documented common pattern (`plan.batches()`, `source["sha256"]`) does not fit this plan.
- The documentation says no quality policy is applied; the code has acceptance rules of its own.
  None fired on the sample.

**ERA5** (`docs/validation/drafts/era5.md`)

- The store `wb2-1p5` ends on 31 December 2021; the documentation and the code say 2022. A request
  for 2022 is accepted and returns no rows and no error. This is the one check that differs.
- The earlier finding CRC-006-ERA5 (units are not read) holds on a constructed store: with a store
  that declares degrees Celsius, crc-sdk subtracts 273.15 anyway. The real store declares what
  crc-sdk assumes.
- The cache key does not contain the release, although the documentation says it is keyed by the
  record's end date (code reading only).
- A chunk absent from the store is read as missing data without an error.

**One design choice in the ERA5 draft needs your decision.** A chunk of this store covers the globe,
and crc-sdk refuses fewer than four years, so its smallest request over the network is about 3.6 GB.
The agent instead pointed crc-sdk at a checksummed local copy of the publisher's chunks for the
annual comparison, and separately checked crc-sdk's own handle to the real store against that copy
on a seeded sample. The skill now describes this as allowed; you may prefer a full run over the network.

## What was built

| Piece | Where |
| --- | --- |
| The skill | `.claude/skills/draft-source-assessment/SKILL.md` |
| Brief, gate and acceptance | `src/data_source_check/draft.py` (`just validation-brief`, `validation-draft-check`, `validation-draft-accept`) |
| Draft run: records go to a folder outside the page | `python -m data_source_check.build <id> --draft` (`just validation-draft`) |
| Who drafted | New field `drafted_by` in the source file, shown on the page and in the inventory |
| The two trial drafts | `reference/`, `adapters/crc/`, `assessments/` and tests for `era5` and `noaa_water_levels` (3,106 lines), notes in `docs/validation/drafts/` |
| One paragraph on drafts | `docs/validation/method.md`, section 7 |

How a draft stays a draft:

- Its records are written to `data/cache/validation/drafts/` and reach the page only when a person
  runs `just validation-draft-accept <id>`.
- The gate refuses a draft that claims to be assessed or reviewed.
- The skill forbids adding findings; candidates go in the note.
- On the page both sources now show "in progress", with their drafter named.

## What the trials showed was wrong, and what I changed

| Fault | Fix |
| --- | --- |
| A draft run also rebuilt the inventory and the page data | It now stops after writing the draft records |
| Two inventory tests assumed ERA5 would stay unassessed | They no longer depend on its state |
| The skill gave the wrong shapes for the headline and tables of a record | Corrected from the code |
| The skill required `assessed_options` where a source has no options | Now only where options exist |
| No guidance for a publisher that answers inconsistently, for a framework that keeps no source bytes, for object stores, or for a shared decoder | Added, from what the two agents had to work out |

## Checks of the result

| Check | Result |
| --- | --- |
| `just test` | 269 passed (14 new for the gate and the draft folder; 80 written by the two agents) |
| `just lint` | Clean |
| `just site` | Three checks pass |
| Assessments page in headless Chrome | 17 of 17 checks |
| Gate on both drafts | Complete |
| A draft run leaves the published records untouched | Tested |

## Limits

- **The gate checks form, not substance.** It does not run the draft's tests, compare the live and
  the cache run, or check the numbers in the note. Both agents said so. A draft that passes still
  needs a person to read the reference code.
- **A lucky run can look clean.** The NOAA draft's published-looking result is the second run, which
  agreed; the first did not. The note tells both, because the skill now requires it.
- **ERA5 temperature recipes ran on a constructed store only**, and the fit is not checked (a later tier).
- **The examples are the real specification and are long.** Both agents spent about a third of their
  time reading them. A short skeleton of the four files would cut that; not written.
- **Two agents in one working tree collided once** (the inventory tests), and my edits to the skill
  reached the second agent mid-run. A later trial should run one at a time.
- Caches grew to 5.8 GB.

## Open for your review

1. **The two drafts.** Read the notes; accept, change or discard each. Accepting publishes the records;
   you then sign.
2. **The candidates.** Which become findings. Two look strongest to me: the ERA5 store ending in 2021
   against a documented 2022, and the NOAA station refused with a misleading message.
3. **The ERA5 construction** (local copy for the annual comparison): acceptable, or run over the network.
4. **The method paragraph** on drafts: keep, change or remove.
5. **Showing drafts as "in progress" on the public page** before you have looked at them.

## Where the plan stands

V0 to V6 are built. V7 (validation tier) needs your first criteria for climate projections and is not
started.
