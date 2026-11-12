# Report V4: monitoring

Date: 2026-11-12 · crc-sdk 0.11.1, crc-framework 0.6.0 · awaiting review

Phase V4 of the [plan](../plan.md) is built. Nothing is committed or pushed, so the scheduled workflow
is not active yet.

## What it does

`just validation-monitor` answers one question per assessed source: does the assessment still stand?

| Reason an assessment goes stale | How it is detected |
| --- | --- |
| The publisher changed a file the assessment read | A HEAD request for every recorded file; the ETag is compared (Last-Modified where there is no ETag). A file that disappeared, or one that was absent and has appeared, also counts |
| The framework version changed | The installed crc-sdk and crc-framework against the versions in the records |
| The framework offers something new | The detector from V0: entry points and option values with no inventory entry |

It writes [monitoring.md](../monitoring.md) and `site/validation/data/monitor.json`, shows the state in
each assessment block on the page, and exits with an error when something needs attention.

First run, 2026-11-12: 1,026 files asked in 7 seconds; all three sources current.

## Re-runs are staged, not published

`just validation-monitor-rerun` re-runs each stale source from scratch into a staging folder, with a
fresh download cache, and compares the new records with the published ones check by check: outcomes
that moved, checks added or removed, numbers that changed. The published records, the page and the
generated reports are not touched. After reading the report, a person publishes the re-run with
`just validation-accept <source>`; the assessment is then a draft again until signed.

## Schedule

`.github/workflows/validation-monitor.yml` runs the monitor every Monday, on a change to
`pyproject.toml` or `uv.lock` on `main`, and on demand. It makes HEAD requests only, puts the report in
the run summary, and fails when something is stale. It has read-only permission and commits nothing. A
re-run of a stale source stays a local step, because it downloads several gigabytes and, for NEX, uses
the local fixed clone.

## Decision on pandera and pointblank

Not adopted. The checks so far compare two computations of the same thing, value by value; neither
library does that, and the record format already carries what a report needs. They are schema and
range validators, which is the work of the validation tier. The question is put again at V7.

## Checks of the tool itself

| Check | Result |
| --- | --- |
| `just test` | 168 passed (76 in `tests/validation/`) |
| `just lint` | Clean |
| A changed, vanished or newly appeared file, and a version change, are each reported | Pass |
| An unreachable file is listed but does not make an assessment stale | Pass |
| A monitoring run and a staged re-run leave the published records byte-identical | Pass |
| Page in headless Chrome | 16 of 16 checks |

## Limits

- The staged re-run was tested with a stand-in for the assessment, not by a real multi-gigabyte re-run:
  no source was stale.
- A HEAD request sees a changed file, not a changed value. IBTrACS is rewritten in place often, so its
  assessment will be reported stale most weeks; the re-run then shows whether any outcome moved.
- GitHub will send a failure notice for a stale source. If weekly notices for IBTrACS are noise, the
  workflow can report without failing for publisher changes and fail only for version changes and gaps.
- `monitor.json` on the page is the state at the last local run, not live.

## Open for your review

1. **Activation.** The workflow starts running once this is pushed. Say if it should wait.
2. **Noise.** Whether a publisher change alone should fail the scheduled run (see Limits).
3. **Cadence.** Weekly, as planned.

## Where the plan stands

V0 to V4 are built. Next in the plan: V5 (split crc-lab into projects with a landing page), V6 (drafting
agent for new sources), V7 (validation). Not started.
