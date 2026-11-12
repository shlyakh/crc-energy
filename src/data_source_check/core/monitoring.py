"""Monitoring: has anything an assessment rests on changed since it was run?

Pure functions over records. Three things can make an assessment stale: the publisher changed
a file it read, the framework version changed, or the framework now offers something the
inventory does not cover. A second run can then be compared with the first, check by check.
Nothing here publishes anything: a re-run is staged for a person to review.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def recorded_inputs(records: dict[str, Any]) -> list[dict[str, Any]]:
    """Every publisher file an assessment read, once, with what was known about it."""
    seen: dict[str, dict[str, Any]] = {}
    for item in records.get("files", ()):
        if item.get("url"):
            seen.setdefault(item["url"], dict(item))
    for check in records["checks"]:
        for item in check.get("inputs", ()):
            url = item.get("url", "")
            if url.startswith("http") and " " not in url and "etag" in item:
                seen.setdefault(url, {"missing": False} | dict(item))
    return [seen[url] for url in sorted(seen)]


def classify(recorded: dict[str, Any], now: dict[str, Any]) -> str:
    """``unchanged``, ``changed``, ``gone`` or ``appeared`` for one file.

    ``now`` is the answer to a HEAD request: ``status`` and, when served, ``etag`` and
    ``last_modified``. A file is unchanged when its ETag is; Last-Modified is the fallback.
    """
    was_missing = bool(recorded.get("missing"))
    served = now.get("status") == 200
    if was_missing:
        return "appeared" if served else "unchanged"
    if not served:
        return "gone"
    if recorded.get("etag") and now.get("etag"):
        return "unchanged" if recorded["etag"] == now["etag"] else "changed"
    return "unchanged" if recorded.get("last_modified") == now.get("last_modified") else "changed"


def source_state(
    records: dict[str, Any],
    heads: dict[str, dict[str, Any]],
    installed: dict[str, str],
) -> dict[str, Any]:
    """Whether one source's assessment still stands, and why not."""
    inputs = recorded_inputs(records)
    moved = []
    unreachable = []
    for item in inputs:
        now = heads.get(item["url"])
        if now is None or now.get("status") not in (200, 404):
            unreachable.append(item["url"])
            continue
        kind = classify(item, now)
        if kind != "unchanged":
            moved.append(
                {
                    "url": item["url"],
                    "change": kind,
                    "was": item.get("last_modified"),
                    "now": now.get("last_modified"),
                }
            )
    was = {name: str(version).split(" ")[0] for name, version in records["versions"].items()}
    versions_changed = {
        name: {"assessed": was.get(name), "installed": version}
        for name, version in installed.items()
        if was.get(name) != version
    }
    reasons = []
    if moved:
        reasons.append(f"the publisher changed {len(moved)} of {len(inputs)} files")
    if versions_changed:
        listed = (
            f"{name} {v['assessed']} to {v['installed']}" for name, v in versions_changed.items()
        )
        reasons.append("the framework version changed: " + ", ".join(listed))
    return {
        "source": records["source"],
        "assessed_at": records["run_at"],
        "files": len(inputs),
        "files_changed": moved,
        "files_unreachable": unreachable,
        "versions_changed": versions_changed,
        "stale": bool(reasons),
        "reasons": reasons,
    }


def diff_records(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """What a second run changed: outcomes that moved, checks that came or went, numbers."""
    before = {check["check"]: check for check in old["checks"]}
    after = {check["check"]: check for check in new["checks"]}
    moved = [
        {"check": name, "was": before[name]["outcome"], "now": after[name]["outcome"]}
        for name in sorted(before.keys() & after.keys())
        if before[name]["outcome"] != after[name]["outcome"]
    ]
    numbers = [
        {
            "check": name,
            "was": before[name].get("summary", ""),
            "now": after[name].get("summary", ""),
        }
        for name in sorted(before.keys() & after.keys())
        if before[name]["outcome"] == after[name]["outcome"]
        and before[name].get("summary") != after[name].get("summary")
    ]  # fmt: skip
    return {
        "source": new["source"],
        "outcomes_changed": moved,
        "newly_differing": [m["check"] for m in moved if m["now"] == "differs"],
        "summaries_changed": numbers,
        "checks_added": sorted(after.keys() - before.keys()),
        "checks_removed": sorted(before.keys() - after.keys()),
    }


def needs_attention(states: Iterable[dict[str, Any]], gaps: dict[str, Any]) -> bool:
    return (
        any(state["stale"] for state in states)
        or bool(gaps["unclaimed_symbols"])
        or bool(gaps["new_options"])
    )


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Monitoring report",
        "",
        f"Run {report['run_at']} against "
        + ", ".join(f"{k} {v}" for k, v in sorted(report["installed"].items()))
        + ". Generated by `python -m data_source_check.monitor`; do not edit.",
        "",
        "Needs attention." if report["needs_attention"] else "Nothing has changed.",
        "",
        "| Source | Assessed | Files checked | Changed at the publisher | Framework changed "
        "| State |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for state in report["sources"]:
        lines.append(
            f"| {state['source']} | {state['assessed_at'][:10]} | {state['files']} | "
            f"{len(state['files_changed'])} | {'yes' if state['versions_changed'] else 'no'} | "
            f"{'stale: ' + '; '.join(state['reasons']) if state['stale'] else 'current'} |"
        )
    gaps = report["gaps"]
    lines += [
        "",
        f"- Entry points with no inventory entry: {len(gaps['unclaimed_symbols'])}"
        + (f" ({', '.join(gaps['unclaimed_symbols'])})" if gaps["unclaimed_symbols"] else ""),
        f"- Option values new upstream: {len(gaps['new_options'])}",
        f"- Files that could not be reached: "
        f"{sum(len(s['files_unreachable']) for s in report['sources'])}",
    ]
    for state in report["sources"]:
        if state["files_changed"]:
            lines += ["", f"## {state['source']}: files changed at the publisher", ""]
            lines += ["| File | Change | Last modified then | Last modified now |",
                      "| --- | --- | --- | --- |"]  # fmt: skip
            lines += [
                f"| {item['url'].rsplit('/', 1)[-1]} | {item['change']} | {item['was'] or ''} | "
                f"{item['now'] or ''} |"
                for item in state["files_changed"][:40]
            ]
            if len(state["files_changed"]) > 40:
                lines.append(f"| and {len(state['files_changed']) - 40} more | | | |")
    for diff in report.get("reruns", ()):
        lines += ["", f"## {diff['source']}: re-run against the previous records", ""]
        if not (diff["outcomes_changed"] or diff["checks_added"] or diff["checks_removed"]):
            lines.append("Every check has the same outcome as before.")
        for moved in diff["outcomes_changed"]:
            lines.append(f"- `{moved['check']}`: {moved['was']} to **{moved['now']}**")
        for name in diff["checks_added"]:
            lines.append(f"- `{name}`: new check")
        for name in diff["checks_removed"]:
            lines.append(f"- `{name}`: no longer run")
        if diff["summaries_changed"]:
            count = len(diff["summaries_changed"])
            lines += [
                "",
                f"Numbers moved in {count} checks whose outcome did not change (for example "
                "more rows in a file that grew).",
            ]
        lines += [
            "",
            f"The re-run is staged in `{diff['staged']}` and is not published. Review it, "
            f"then accept it with `just validation-accept {diff['source']}`.",
        ]
    return "\n".join(lines) + "\n"
