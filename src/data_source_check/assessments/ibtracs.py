"""IBTrACS: exploration, and verification of crc-sdk's ``IBTrACSPlan`` against NOAA's files.

For each subset the reference side downloads NOAA's file and reads it with the standard
library; the framework side asks crc-sdk for the same subset. Every value is compared, not
a sample; the seed only picks the storms and seasons used to exercise the two filters.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ..adapters.crc import ibtracs as framework
from ..core import compare
from ..core.records import CheckRecord
from ..reference import ibtracs as reference

SOURCE = "ibtracs"
SEED = 20261111
STORMS_SAMPLED = 25
MANIFEST_KEYS = (
    "url",
    "version",
    "subset",
    "sha256",
    "retrieved_at",
    "units",
    "terms_url",
    "citation",
)
EXACT = {"values": "exact equality of strings; null equals null only"}

Rules = dict[str, bool]


def _input(role: str, provenance: dict[str, Any]) -> dict[str, Any]:
    keys = ("url", "sha256", "retrieved_at", "etag", "last_modified", "bytes")
    return {"role": role} | {key: provenance.get(key) for key in keys if key in provenance}


def availability(
    subsets: Sequence[str], cache: Path, sdk_cache: Path, *, live: bool, versions: dict[str, str]
) -> tuple[CheckRecord, dict[str, int]]:
    """Does NOAA serve a file at the address crc-sdk builds for each subset it accepts?"""
    stored = cache / "availability.json"
    if live:
        listing = reference.directory_listing()
        found = {}
        for subset in subsets:
            address = framework.url(subset, sdk_cache)
            if address != reference.url(subset):
                raise RuntimeError(f"crc-sdk's address for {subset} is not the documented one")
            found[subset] = reference.status(subset)
        state = {"checked_at": compare.now(), "status": found, "publisher_files": listing}
        cache.mkdir(parents=True, exist_ok=True)
        stored.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    elif stored.exists():
        state = json.loads(stored.read_text(encoding="utf-8"))
    else:
        raise FileNotFoundError("no cached availability result; run with --live")
    status = {subset: state["status"][subset] for subset in subsets}
    missing = sorted(subset for subset, code in status.items() if code != 200)
    check = compare.record(
        source=SOURCE,
        check="address",
        tier="verification",
        category="fidelity",
        method="For every subset name crc-sdk accepts, request the address crc-sdk builds "
        "(HEAD) and record NOAA's answer; list the CSV files in NOAA's directory.",
        agrees=not missing,
        versions=versions,
        result={
            "subsets_accepted": len(status),
            "subsets_served": len(status) - len(missing),
            "not_served": {subset: status[subset] for subset in missing},
            "publisher_files": state["publisher_files"],
            "checked_at": state["checked_at"],
        },
        tolerance={"http_status": "200 for every subset"},
        steps=("address",),
    )
    return check, status


def assess_subset(
    subset: str,
    cache: Path,
    sdk_cache: Path,
    *,
    live: bool,
    versions: dict[str, str],
    rules: Rules | None = None,
    log: Callable[[str], None] = lambda _: None,
) -> tuple[list[CheckRecord], dict[str, Any]]:
    """All checks for one subset, and its exploration. ``rules`` overrides the reference rules."""
    rules = rules or {}
    ours = reference.download(subset, cache / "reference", live=live)
    theirs = framework.snapshot(subset, sdk_cache, live=live)
    ref_path = Path(ours["path"])
    inputs = (_input("reference download", ours), _input("crc-sdk snapshot", theirs))
    label = f"[{subset}]"

    def make(
        check: str, category: str, method: str, agrees: bool | None, **more: Any
    ) -> CheckRecord:
        return compare.record(
            source=SOURCE,
            check=f"{check}{label}",
            tier="verification",
            category=category,
            method=method,
            agrees=agrees,
            versions=versions,
            inputs=inputs,
            **more,
        )

    checks = []
    their_sha = reference.sha256(Path(theirs["path"]))
    checks.append(
        make(
            "bytes",
            "fidelity",
            "SHA-256 of the file crc-sdk cached against SHA-256 of an independent download of the "
            "same address; and against the checksum crc-sdk wrote in its manifest.",
            ours["sha256"] == their_sha == theirs.get("sha256"),
            result={
                "reference_sha256": ours["sha256"],
                "framework_file_sha256": their_sha,
                "framework_manifest_sha256": theirs.get("sha256"),
                "bytes": ours.get("bytes"),
            },
            tolerance={"bytes": "identical"},
            steps=("bytes",),
        )
    )

    log(f"{subset}: header")
    columns, units = reference.header(ref_path)
    names, types, metadata, _ = framework.table(subset, sdk_cache)
    duplicates = sorted({name for name in columns if columns.count(name) > 1})
    unit_map = dict(zip(columns, units, strict=True))
    checks.append(
        make(
            "header",
            "consistency",
            "Line 1 of NOAA's file against the column names and order crc-sdk yields; the type of "
            "every column; line 2 against the units in crc-sdk's manifest.",
            names == columns
            and set(types) == {"string"}
            and theirs.get("units") == unit_map
            and not duplicates,
            result={
                "columns_reference": len(columns),
                "columns_framework": len(names),
                "same_names_and_order": names == columns,
                "column_types": sorted(set(types)),
                "units_agree": theirs.get("units") == unit_map,
                "columns_with_a_unit": sum(1 for unit in units if unit.strip()),
                "duplicate_column_names": duplicates,
            },
            tolerance={"names": "identical, in order", "units": "identical"},
            steps=("header", "columns", "strings"),
        )
    )

    log(f"{subset}: every value")
    _, _, _, their_rows = framework.table(subset, sdk_cache)
    result = compare.compare_rows(columns, reference.rows(ref_path, **rules), their_rows)
    checks.append(
        make(
            "values",
            "fidelity",
            "Every data row of NOAA's file, read with Python's csv module, trimmed, empty values "
            "made null, against every row crc-sdk yields, in order, value by value.",
            compare.rows_agree(result) if result["values_compared"] else None,
            result=result,
            sample={"rows": "all", "columns": "all"},
            tolerance=EXACT,
            steps=("columns", "strings", "trim", "null", "rows"),
            note="" if result["values_compared"] else "the file has no data rows",
        )
    )

    log(f"{subset}: filters")
    seasons_of = reference.storm_seasons(ref_path)
    storms = compare.sample(seasons_of, STORMS_SAMPLED, SEED)
    spans = compare.sample(set(seasons_of.values()), 2, SEED)
    span = (spans[0], spans[-1]) if spans else None
    storm_span = (
        (min(seasons_of[s] for s in storms), min(seasons_of[s] for s in storms) + 20)
        if storms
        else None
    )
    cases: list[tuple[str, str, Sequence[str] | None, tuple[int, int] | None, tuple[str, ...]]] = [
        ("storm-filter", "for_storms(ids)", storms, None, ("storms",)),
        ("season-filter", "years(a, b)", None, span, ("seasons",)),
        ("both-filters", "for_storms(ids).years(a, b)", storms, storm_span, ("storms", "seasons")),
    ]
    for check, call, ids, years, steps in cases:
        if (ids is not None and not ids) or (check != "storm-filter" and years is None):
            checks.append(
                make(
                    check,
                    "fidelity",
                    f"{call} against the same selection made on NOAA's file.",
                    None,
                    steps=steps,
                    note="the file has no storms to select",
                )
            )
            continue
        _, _, _, selected = framework.table(subset, sdk_cache, storm_ids=ids, seasons=years)
        expected = reference.select(
            reference.rows(ref_path, **rules), columns, storm_ids=ids, seasons=years
        )
        result = compare.compare_rows(columns, expected, selected)
        checks.append(
            make(
                check,
                "fidelity",
                f"{call} against the same selection made on NOAA's file: rows whose SID is in the "
                "list, whose SEASON is in the inclusive range, in file order.",
                compare.rows_agree(result) if result["values_compared"] else None,
                result=result,
                sample={
                    "seed": SEED,
                    "storm_ids": list(ids) if ids is not None else None,
                    "seasons": list(years) if years is not None else None,
                },
                tolerance=EXACT,
                steps=steps,
                note="" if result["values_compared"] else "the selection is empty in this file",
            )
        )

    present = {key: key in theirs and theirs[key] not in (None, "") for key in MANIFEST_KEYS}
    checks.append(
        make(
            "provenance",
            "consistency",
            "Fields of the manifest crc-sdk writes beside the snapshot, and the metadata attached "
            "to the batches it yields.",
            all(present.values()) and metadata is None,
            result={
                "manifest_fields_present": present,
                "manifest_has_licence_field": any("licen" in key.lower() for key in theirs),
                "etag": theirs.get("etag"),
                "last_modified": theirs.get("last_modified"),
                "batch_schema_metadata": metadata,
            },
            tolerance={"fields": "all present and non-empty; no batch metadata, as stated"},
            steps=("provenance",),
        )
    )

    log(f"{subset}: exploration")
    exploration = reference.explore(ref_path)
    exploration["file"] = _input("reference download", ours)
    return checks, exploration


def assess(
    subsets: Sequence[str],
    offered: Sequence[str],
    cache: Path,
    sdk_cache: Path,
    *,
    live: bool,
    versions: dict[str, str],
    rules: Rules | None = None,
    log: Callable[[str], None] = lambda _: None,
) -> dict[str, Any]:
    """The records of one run: checks and exploration for the subsets NOAA serves."""
    address, status = availability(offered, cache, sdk_cache, live=live, versions=versions)
    checks = [address]
    exploration = {}
    skipped = {}
    for subset in subsets:
        if status.get(subset) != 200:
            skipped[subset] = f"NOAA answers {status.get(subset)} for this subset's address"
            continue
        made, explored = assess_subset(
            subset, cache, sdk_cache, live=live, versions=versions, rules=rules, log=log
        )
        checks += made
        exploration[subset] = explored
    return present(
        {
            "source": SOURCE,
            "seed": SEED,
            "versions": dict(versions),
            "run_at": compare.now(),
            "subsets_assessed": sorted(exploration),
            "subsets_skipped": skipped,
            "checks": [check.to_dict() for check in checks],
            "exploration": exploration,
        }
    )


def _summary(check: dict[str, Any]) -> str:
    result = check["result"]
    if "values_compared" in result:
        return compare.rows_summary(result)
    if "reference_sha256" in result:
        same = result["reference_sha256"] == result["framework_file_sha256"]
        return (
            f"{compare.number(result['bytes'])} bytes; SHA-256 {result['reference_sha256'][:12]}… "
            + ("on both sides" if same else f"differs from {result['framework_file_sha256'][:12]}…")
        )
    if "columns_reference" in result:
        return (
            f"{result['columns_reference']} columns, {result['columns_with_a_unit']} with a unit; "
            f"types: {', '.join(result['column_types'])}"
        )
    if "subsets_accepted" in result:
        missing = ", ".join(f"{k} (HTTP {v})" for k, v in result["not_served"].items()) or "none"
        return (
            f"{result['subsets_served']} of {result['subsets_accepted']} accepted names are "
            f"served by the publisher; not served: {missing}"
        )
    if "manifest_fields_present" in result:
        fields = result["manifest_fields_present"]
        return (
            f"{sum(fields.values())} of {len(fields)} stated fields present; licence field: "
            f"{'yes' if result['manifest_has_licence_field'] else 'no'}; batch metadata: "
            f"{result['batch_schema_metadata'] or 'none'}"
        )
    return check.get("note", "")


def present(run: dict[str, Any]) -> dict[str, Any]:
    """Add what the page and the report show: summaries, headline numbers, tables, a chart."""
    for check in run["checks"]:
        check["summary"] = _summary(check)
    values = [c["result"] for c in run["checks"] if c["check"].startswith("values[")]
    count = compare.tally(run["checks"])
    explored = run["exploration"]
    run["headline"] = [
        [len(explored), "publisher files read"],
        [sum(r["values_compared"] for r in values), "values compared one by one"],
        [sum(r["values_differing"] for r in values), "values that differ"],
        [f"{count.get('confirmed', 0)} of {len(run['checks'])}", "checks confirmed"],
        [count.get("differs", 0), "checks that differ"],
    ]
    run["tables"] = [
        {
            "title": "What is in the publisher's files",
            "note": "Counted from NOAA's files by the reference reader.",
            "head": [
                "File",
                "Rows",
                "Storms",
                "Seasons",
                "Columns",
                "Values missing",
                "Last modified by publisher",
            ],
            "rows": [
                [
                    name,
                    e["rows"],
                    e["storms"],
                    f"{e['seasons'][0]} to {e['seasons'][1]}" if e["seasons"] else "",
                    e["columns"],
                    f"{100 * e['values_empty_after_trim'] / e['values_total']:.1f} %"
                    if e["values_total"]
                    else "",
                    e["file"].get("last_modified") or "",
                ]
                for name, e in explored.items()
            ],
        }
    ]
    run["chart"] = {
        "title": "Storms per season",
        "unit": "storms",
        "x": "Season",
        "select": "File",
        "default": "ALL" if "ALL" in explored else next(iter(explored), ""),
        "series": {name: e["storms_by_season"] for name, e in explored.items()},
    }
    return run
