"""NOAA CO-OPS extreme water levels: exploration, and verification of crc-sdk's
``NOAAExtremeWaterLevelPlan`` against NOAA's API.

Draft (skill ``draft-source-assessment``); not reviewed.

The stations are taken from NOAA's own list of stations with the product: every station in
Texas and a seeded sample of the others, plus station ids known to have no product. For each
station the reference side downloads the three responses and applies the statement's rules;
the framework side asks crc-sdk. Every value of every sampled station is compared.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..adapters.crc import noaa_water_levels as framework
from ..core import compare
from ..core.io import write_json_atomic
from ..reference import noaa_water_levels as reference
from ..reference.noaa_water_levels import Rules

SOURCE = "noaa-water-levels"
SEED = 20261112
#: stations drawn with the seed from those outside Texas (all Texas stations are taken)
ELSEWHERE = 14
#: water-level stations seen by hand (2026-11-12) to have no extreme-water-level product
NOT_PUBLISHED = ("8770475",)
#: texts offered to crc-sdk as a station id; only the first is one
STATION_ID_CASES = (
    "8771450",
    "877145",
    "87714500",
    "877145a",
    " 8771450",
    "8771450\n",
    "８７７１４５０",  # seven full-width digits
    "",
)
MANIFEST_KEYS = (
    "url",
    "station_id",
    "resource",
    "sha256",
    "retrieved_at",
    "attribution",
    "source_documentation",
    "terms_url",
)
EXACT = {
    "values": "exact: the shortest decimal that identifies crc-sdk's float equals the decimal "
    "NOAA wrote; strings identical; null equals null only"
}
RESOURCES = reference.RESOURCES


def canon(value: Any) -> Any:
    """Numbers as decimal text (NOAA's decimal, or the shortest decimal of a float)."""
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, float):
        value = Decimal(repr(value))
    if isinstance(value, int | Decimal):
        return format(Decimal(value).normalize(), "f")
    if isinstance(value, dict):
        return {key: canon(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [canon(item) for item in value]
    raise TypeError(f"unexpected value {value!r}")


def _flat(info: dict[str, Any]) -> list[list[Any]]:
    """An info dictionary as rows of (field, value), the station entry spread out."""
    rows = [[f"station.{key}", canon(value)] for key, value in sorted(info["station"].items())]
    rows += [[key, canon(value)] for key, value in sorted(info.items()) if key != "station"]
    return rows


def _add(total: dict[str, Any], station: str, result: dict[str, Any]) -> None:
    for key in ("rows_reference", "rows_framework", "values_compared", "values_differing"):
        total[key] = total.get(key, 0) + result[key]
    for name, count in result["columns_differing"].items():
        total.setdefault("columns_differing", {})
        total["columns_differing"][name] = total["columns_differing"].get(name, 0) + count
    total.setdefault("columns_differing", {})
    total.setdefault("examples", [])
    room = compare.MAX_EXAMPLES - len(total["examples"])
    total["examples"] += [{"station": station} | example for example in result["examples"][:room]]
    total["stations"] = total.get("stations", 0) + 1


def _second_download(pairs: dict[str, dict[str, tuple[list[Any], list[Any]]]]) -> dict[str, Any]:
    """Values of the reference side's own download against crc-sdk's, with the largest gap."""
    compared = differing = other_length = 0
    largest = Decimal(0)
    by_table: dict[str, int] = {}
    affected: set[str] = set()
    examples: list[dict[str, Any]] = []
    for station, tables in pairs.items():
        for table, (ours, theirs) in tables.items():
            if len(ours) != len(theirs):
                other_length += 1
                affected.add(station)
                continue
            for number, (a_row, b_row) in enumerate(zip(canon(ours), canon(theirs), strict=True)):
                for position, (a, b) in enumerate(zip(a_row, b_row, strict=True)):
                    compared += 1
                    if a == b:
                        continue
                    differing += 1
                    by_table[table] = by_table.get(table, 0) + 1
                    affected.add(station)
                    try:
                        largest = max(largest, abs(Decimal(a) - Decimal(b)))
                    except (ArithmeticError, TypeError, ValueError):
                        pass
                    if len(examples) < compare.MAX_EXAMPLES:
                        examples.append(
                            {
                                "station": station,
                                "table": table,
                                "row": number,
                                "position": position,
                                "reference": a,
                                "framework": b,
                            }
                        )
    return {
        "stations": len(pairs),
        "values_compared": compared,
        "values_differing": differing,
        "values_differing_by_table": dict(sorted(by_table.items())),
        "stations_with_a_difference": sorted(affected),
        "tables_of_other_length": other_length,
        "largest_difference_between_numbers": format(largest.normalize(), "f"),
        "examples": examples,
    }


def _input(role: str, provenance: dict[str, Any]) -> dict[str, Any]:
    keys = ("url", "sha256", "retrieved_at", "bytes", "status")
    return {"role": role} | {key: provenance[key] for key in keys if key in provenance}


def choose(index: dict[str, Any], elsewhere: int) -> dict[str, Any]:
    """The stations compared: all of Texas, and a seeded sample of the rest of NOAA's list."""
    entries = index.get("ExtremeWaterLevels") or []
    texas = sorted(e["stationId"] for e in entries if e.get("state") == "TX")
    rest = [e["stationId"] for e in entries if e.get("state") != "TX"]
    drawn = compare.sample(rest, elsewhere, SEED)
    return {
        "seed": SEED,
        "listed": len(entries),
        "texas": texas,
        "elsewhere": drawn,
        "rule": f"every listed station with state TX, and {elsewhere} of the others drawn with "
        "the seed",
    }


def _framework_side(
    station: str, sdk_cache: Path, stored: dict[str, Any], *, live: bool
) -> dict[str, Any]:
    """What crc-sdk did for a station; a refusal seen live is replayed from the cache."""
    if not live and station in stored:
        return dict(stored[station])
    theirs = framework.snapshot(station, sdk_cache, live=live)
    if "refused" in theirs:
        stored[station] = theirs
    else:
        stored.pop(station, None)
    return theirs


def assess(
    cache: Path,
    *,
    live: bool,
    versions: dict[str, str],
    rules: Rules | None = None,
    log: Callable[[str], None] = lambda _: None,
    not_published: Sequence[str] = NOT_PUBLISHED,
    elsewhere: int = ELSEWHERE,
) -> dict[str, Any]:
    """The records of one run. ``rules`` overrides the reference rules (for fault tests)."""
    rules = rules or Rules()
    ref_cache, sdk_cache = cache / "reference", cache / "crc-sdk"
    refusals_file = cache / "framework-refusals.json"
    stored: dict[str, Any] = (
        json.loads(refusals_file.read_text(encoding="utf-8")) if refusals_file.exists() else {}
    )

    log("list of stations")
    index_file = reference.fetch(reference.index_url(), ref_cache / "index.json", live=live)
    if index_file["status"] != 200:
        raise RuntimeError(f"NOAA answers {index_file['status']} for its list of stations")
    index = reference.parse(Path(index_file["path"]))
    chosen = choose(index, elsewhere)
    listed = {entry["stationId"] for entry in index.get("ExtremeWaterLevels") or []}
    probes = sorted(station for station in not_published if station not in listed)
    stations = sorted(chosen["texas"] + chosen["elsewhere"])
    sample = chosen | {"not_listed": probes}

    inputs = [_input("NOAA list of stations", index_file)]
    side: dict[str, dict[str, Any]] = {}
    unreadable: dict[str, dict[str, int]] = {}
    for station in stations + probes:
        log(f"{station}: responses")
        ours = reference.download_station(station, ref_cache, live=live, rules=rules)
        inputs += [_input(f"reference download, {name}", ours[name]) for name in RESOURCES]
        if any(ours[name]["status"] != 200 for name in RESOURCES):
            unreadable[station] = {name: ours[name]["status"] for name in RESOURCES}
            continue
        payloads = {name: reference.parse(Path(ours[name]["path"])) for name in RESOURCES}
        side[station] = {
            "ours": ours,
            "payloads": payloads,
            "predicted": reference.refusal(payloads, station, rules),
            "theirs": _framework_side(station, sdk_cache, stored, live=live),
        }
    if live:
        write_json_atomic(refusals_file, stored)
    both = [s for s, d in side.items() if d["predicted"] is None and "refused" not in d["theirs"]]
    delivered = [s for s, d in side.items() if "refused" not in d["theirs"]]
    got = {station: framework.tables(station, sdk_cache) for station in delivered}
    #: the responses as crc-sdk cached them, read by the reference reader
    cached = {
        station: {
            name: reference.parse(Path(side[station]["theirs"]["paths"][name]))
            for name in RESOURCES
        }
        for station in delivered
    }
    nothing = "no station was delivered by both sides"

    def make(
        check: str, category: str, method: str, agrees: bool | None, **more: Any
    ) -> dict[str, Any]:
        return compare.record(
            source=SOURCE,
            check=check,
            tier="verification",
            category=category,
            method=method,
            agrees=agrees,
            versions=versions,
            inputs=inputs,
            **more,
        ).to_dict()

    checks = []

    cases = {
        text: {
            "reference": reference.valid_station_id(text, rules),
            "framework": framework.accepts(text),
        }
        for text in STATION_ID_CASES
    }
    wrong = sorted(text for text, case in cases.items() if case["reference"] != case["framework"])
    checks.append(
        make(
            "station-id",
            "consistency",
            "Constructed texts offered as a station id: accepted by the stated rule (exactly "
            "seven digits 0-9) against accepted by crc-sdk.",
            not wrong,
            result={
                "texts": len(cases),
                "accepted_by_both": sum(c["reference"] and c["framework"] for c in cases.values()),
                "refused_by_both": sum(
                    not c["reference"] and not c["framework"] for c in cases.values()
                ),
                "disagreements": wrong,
            },
            sample={"texts": list(STATION_ID_CASES)},
            tolerance={"decision": "the same for every text"},
            steps=("station-id",),
        )
    )

    compared = differing = 0
    examples: list[dict[str, Any]] = []
    for station in side:
        stated = framework.urls(station, sdk_cache)
        manifests = side[station]["theirs"].get("manifests", {})
        for name in RESOURCES:
            ours_url = reference.url(station, name, rules)
            for origin, theirs_url in (
                ("explain()", stated.get(name)),
                ("manifest", manifests[name].get("url") if manifests else ours_url),
            ):
                if origin == "manifest" and not manifests:
                    continue
                compared += 1
                if theirs_url != ours_url:
                    differing += 1
                    if len(examples) < compare.MAX_EXAMPLES:
                        examples.append(
                            {
                                "station": station,
                                "resource": name,
                                "from": origin,
                                "reference": ours_url,
                                "framework": theirs_url,
                            }
                        )
    checks.append(
        make(
            "requests",
            "fidelity",
            "The three addresses written out from the statement against those crc-sdk states "
            "(explain()) and those it recorded in its manifests, for every station.",
            (differing == 0) if compared else None,
            result={
                "addresses_compared": compared,
                "addresses_differing": differing,
                "examples": examples,
            },
            sample=sample,
            tolerance={"addresses": "identical strings"},
            steps=("requests",),
            note="" if compared else "no station could be read",
        )
    )

    compared = differing = size = 0
    examples = []
    for station in delivered:
        theirs = side[station]["theirs"]
        for name in RESOURCES:
            ours = side[station]["ours"][name]
            file_sha = reference.sha256(Path(theirs["paths"][name]))
            compared += 1
            size += ours["bytes"]
            if not ours["sha256"] == file_sha == theirs["manifests"][name].get("sha256"):
                differing += 1
                if len(examples) < compare.MAX_EXAMPLES:
                    examples.append(
                        {
                            "station": station,
                            "resource": name,
                            "reference": ours["sha256"],
                            "framework_file": file_sha,
                            "framework_manifest": theirs["manifests"][name].get("sha256"),
                        }
                    )
    checks.append(
        make(
            "bytes",
            "fidelity",
            "SHA-256 of each response crc-sdk cached against SHA-256 of an independent download "
            "of the same address, and against the checksum crc-sdk wrote in its manifest.",
            (differing == 0) if compared else None,
            result={
                "responses_compared": compared,
                "responses_differing": differing,
                "bytes": size,
                "examples": examples,
            },
            sample=sample,
            tolerance={"bytes": "identical"},
            steps=("bytes",),
            note="" if compared else "crc-sdk delivered no station",
        )
    )

    disagreements = sorted(
        s for s, d in side.items() if (d["predicted"] is None) != ("refused" not in d["theirs"])
    )
    refused = {
        s: {
            "reference": d["predicted"],
            "framework": d["theirs"].get("refused"),
            "responses_cached_by_framework": d["theirs"].get("responses_cached"),
            "publisher_error": {
                name: payload["errorMsg"]
                for name, payload in d["payloads"].items()
                if isinstance(payload, dict) and "errorMsg" in payload
            },
        }
        for s, d in side.items()
        if d["predicted"] is not None or "refused" in d["theirs"]
    }
    left_behind = sorted(
        s for s, r in refused.items() if r["responses_cached_by_framework"] not in (None, 0)
    )
    checks.append(
        make(
            "acceptance",
            "consistency",
            "For every station: delivered or refused according to the stated rules applied to "
            "NOAA's three responses, against delivered or refused (ValueError) by crc-sdk; and "
            "whether crc-sdk kept a response of a station it refused.",
            (not disagreements and not left_behind) if side else None,
            result={
                "stations": len(side),
                "delivered_by_both": len(both),
                "refused_by_both": sum(
                    1 for r in refused.values() if r["reference"] and r["framework"]
                ),
                "disagreements": disagreements,
                "refused": refused,
                "responses_kept_after_refusal": left_behind,
                "reference_could_not_read": unreadable,
            },
            sample=sample,
            tolerance={"decision": "the same for every station; nothing cached after a refusal"},
            steps=("refusals",),
            note="" if side else "no station could be read",
        )
    )

    wanted = {
        "levels": (
            [n for n, _ in reference.LEVEL_COLUMNS],
            [t for _, t in reference.LEVEL_COLUMNS],
        ),
        "annuals": (
            [n for n, _ in reference.ANNUAL_COLUMNS],
            [t for _, t in reference.ANNUAL_COLUMNS],
        ),
    }
    mismatched = sorted(
        f"{station}/{name}"
        for station in delivered
        for name, (columns, types) in wanted.items()
        if got[station][name]["columns"] != columns or got[station][name]["types"] != types
    )
    checks.append(
        make(
            "columns",
            "consistency",
            "Names, order and types of the columns of the two tables crc-sdk gives against the "
            "eleven and six columns of the statement.",
            (not mismatched) if delivered else None,
            result={
                "tables_compared": 2 * len(delivered),
                "tables_differing": len(mismatched),
                "differing": mismatched[: compare.MAX_EXAMPLES],
                "level_columns": wanted["levels"][0],
                "level_types": wanted["levels"][1],
                "annual_columns": wanted["annuals"][0],
                "annual_types": wanted["annuals"][1],
            },
            sample=sample,
            tolerance={"names": "identical, in order", "types": "identical"},
            steps=("levels", "annuals", "numbers"),
            note="" if delivered else "crc-sdk delivered no station",
        )
    )

    tables: tuple[tuple[str, str, Callable[..., list[list[Any]]], tuple[str, ...], str], ...] = (
        (
            "levels",
            "levels",
            reference.level_rows,
            ("levels", "numbers"),
            "Every row of source_levels() against the rows built by the statement from the "
            "station and levels responses as crc-sdk cached them (whether those are NOAA's bytes "
            "is the check 'bytes'), in NOAA's order, value by value.",
        ),
        (
            "annuals",
            "annuals",
            reference.annual_rows,
            ("annuals", "numbers"),
            "Every row of annual_extremes() against the rows built by the statement from the "
            "station and annuals responses as crc-sdk cached them (whether those are NOAA's "
            "bytes is the check 'bytes'), in NOAA's order, value by value.",
        ),
    )
    for check, name, build, steps, method in tables:
        total: dict[str, Any] = {}
        for station in both:
            ours_rows = canon(build(cached[station], station, rules))
            theirs_rows = canon(got[station][name]["rows"])
            _add(total, station, compare.compare_rows(wanted[name][0], ours_rows, theirs_rows))
        checks.append(
            make(
                check,
                "fidelity",
                method,
                compare.rows_agree(total) if total.get("values_compared") else None,
                result=total,
                sample=sample | {"rows": "all", "columns": "all"},
                tolerance=EXACT,
                steps=steps,
                note="" if total.get("values_compared") else nothing,
            )
        )

    total = {}
    for station in both:
        ours_rows = _flat(reference.info(cached[station]))
        _add(
            total,
            station,
            compare.compare_rows(["field", "value"], ours_rows, _flat(got[station]["info"])),
        )
    checks.append(
        make(
            "info",
            "fidelity",
            "Every field of source_info() against the same field of the responses as crc-sdk "
            "cached them: the whole station entry, the datum and units of the levels response, "
            "and the trend, its units and dates and the notice of the annuals response.",
            compare.rows_agree(total) if total.get("values_compared") else None,
            result=total,
            sample=sample | {"fields": "all"},
            tolerance=EXACT,
            steps=("info",),
            note="" if total.get("values_compared") else nothing,
        )
    )

    second = _second_download(
        {
            station: {
                "levels": (
                    reference.level_rows(side[station]["payloads"], station, rules),
                    got[station]["levels"]["rows"],
                ),
                "annuals": (
                    reference.annual_rows(side[station]["payloads"], station, rules),
                    got[station]["annuals"]["rows"],
                ),
                "info": (
                    _flat(reference.info(side[station]["payloads"])),
                    _flat(got[station]["info"]),
                ),
            }
            for station in both
        }
    )
    checks.append(
        make(
            "second-download",
            "fidelity",
            "Every value of the two tables and of source_info() against the same value built by "
            "the statement from the reference side's own download of the same three addresses, "
            "made within seconds of crc-sdk's.",
            (second["values_differing"] == 0 and second["tables_of_other_length"] == 0)
            if second["values_compared"]
            else None,
            result=second,
            sample=sample | {"rows": "all", "columns": "all"},
            tolerance=EXACT,
            steps=("one-answer",),
            note="" if second["values_compared"] else nothing,
        )
    )

    manifests = [side[s]["theirs"]["manifests"][name] for s in delivered for name in RESOURCES]
    incomplete = sum(1 for m in manifests if any(m.get(key) in (None, "") for key in MANIFEST_KEYS))
    with_metadata = sorted(
        f"{s}/{name}"
        for s in delivered
        for name in ("levels", "annuals")
        if got[s][name]["metadata"] is not None
    )
    checks.append(
        make(
            "provenance",
            "consistency",
            "Fields of the manifest crc-sdk writes beside each response, and the metadata "
            "attached to the tables it gives; the ETag and Last-Modified NOAA sent to either side.",
            (incomplete == 0 and not with_metadata) if manifests else None,
            result={
                "manifests": len(manifests),
                "manifests_missing_a_stated_field": incomplete,
                "fields_required": list(MANIFEST_KEYS),
                "manifests_with_a_licence_field": sum(
                    1 for m in manifests if any("licen" in key.lower() for key in m)
                ),
                "manifests_with_an_etag": sum(1 for m in manifests if m.get("etag")),
                "manifests_with_last_modified": sum(1 for m in manifests if m.get("last_modified")),
                "reference_downloads_with_etag_or_last_modified": sum(
                    1
                    for d in side.values()
                    for name in RESOURCES
                    if d["ours"][name].get("etag") or d["ours"][name].get("last_modified")
                ),
                "tables_with_metadata": with_metadata,
            },
            sample=sample,
            tolerance={"fields": "all present and non-empty; no table metadata, as stated"},
            steps=("provenance",),
            note="" if manifests else "crc-sdk delivered no station",
        )
    )

    served = refused_wrong = 0
    messages: set[str] = set()
    for station in delivered:
        digests = {name: side[station]["theirs"]["manifests"][name]["sha256"] for name in RESOURCES}
        served += framework.pinned(station, sdk_cache, digests) is None
        message = framework.pinned(station, sdk_cache, digests | {"levels": "0" * 64})
        refused_wrong += message is not None
        messages |= {message} if message else set()
    checks.append(
        make(
            "pinned-checksums",
            "consistency",
            "The cached responses asked for again with the three recorded SHA-256 digests "
            "(expected: served), then with the digest of the levels response replaced by 64 "
            "zeros (expected: RuntimeError).",
            (served == refused_wrong == len(delivered)) if delivered else None,
            result={
                "stations": len(delivered),
                "served_with_recorded_digests": int(served),
                "refused_with_a_wrong_digest": int(refused_wrong),
                "messages": sorted(messages),
            },
            sample=sample,
            tolerance={"decision": "served with the recorded digests, refused with a wrong one"},
            steps=("pinned-checksums",),
            note="" if delivered else "crc-sdk delivered no station",
        )
    )

    log("exploration")
    explored = {
        station: reference.explore_station(side[station]["payloads"], rules)
        for station in sorted(side)
        if side[station]["predicted"] is None
    }
    return present(
        {
            "source": SOURCE,
            "seed": SEED,
            "versions": dict(versions),
            "run_at": compare.now(),
            "sample": sample,
            "checks": checks,
            "exploration": {
                "index": reference.explore_index(index) | {"file": _input("list", index_file)},
                "stations": explored,
            },
        }
    )


def _summary(check: dict[str, Any]) -> str:
    result = check["result"]
    if not result:
        return check.get("note", "")
    name = check["check"]
    if name == "station-id":
        return (
            f"{result['texts']} texts: {result['accepted_by_both']} accepted by both, "
            f"{result['refused_by_both']} refused by both, "
            f"{len(result['disagreements'])} decided differently"
        )
    if name == "requests":
        return (
            f"{compare.number(result['addresses_compared'])} addresses compared, "
            f"{result['addresses_differing']} differ"
        )
    if name == "bytes":
        return (
            f"{result['responses_compared']} responses, {compare.number(result['bytes'])} bytes; "
            f"{result['responses_differing']} with a different SHA-256"
        )
    if name == "acceptance":
        return (
            f"{result['stations']} stations: {result['delivered_by_both']} delivered by both, "
            f"{result['refused_by_both']} refused by both, "
            f"{len(result['disagreements'])} decided differently"
        )
    if name == "columns":
        return (
            f"{result['tables_compared']} tables, {result['tables_differing']} with other columns "
            f"or types; {len(result['level_columns'])} and {len(result['annual_columns'])} columns"
        )
    if name == "second-download":
        return (
            f"{result['stations']} stations; {compare.number(result['values_compared'])} values "
            f"compared, {compare.number(result['values_differing'])} differ at "
            f"{len(result['stations_with_a_difference'])} stations; largest difference between "
            f"numbers {result['largest_difference_between_numbers']}"
        )
    if "values_compared" in result:
        return f"{result['stations']} stations; " + compare.rows_summary(result)
    if name == "provenance":
        return (
            f"{result['manifests']} manifests, {result['manifests_missing_a_stated_field']} "
            f"missing a stated field; with an ETag: {result['manifests_with_an_etag']}; with "
            f"Last-Modified: {result['manifests_with_last_modified']}; licence field: "
            f"{result['manifests_with_a_licence_field']}; tables with metadata: "
            f"{len(result['tables_with_metadata'])}"
        )
    if name == "pinned-checksums":
        return (
            f"{result['stations']} stations: {result['served_with_recorded_digests']} served with "
            f"the recorded digests, {result['refused_with_a_wrong_digest']} refused with a wrong "
            "one"
        )
    return check.get("note", "")


def present(run: dict[str, Any]) -> dict[str, Any]:
    """Add what the page and the report show: summaries, headline numbers, tables, a chart."""
    for check in run["checks"]:
        check["summary"] = _summary(check)
    values = [
        c["result"]
        for c in run["checks"]
        if "values_compared" in c["result"] and c["check"] != "second-download"
    ]
    count = compare.tally(run["checks"])
    index, stations = run["exploration"]["index"], run["exploration"]["stations"]
    series = {f"{station} {e['name']}": e.pop("annual_series") for station, e in stations.items()}
    run["headline"] = [
        [len(stations), f"stations read, of {index['stations']} NOAA lists"],
        [sum(r["values_compared"] for r in values), "values compared one by one"],
        [sum(r["values_differing"] for r in values), "values that differ"],
        [f"{count.get('confirmed', 0)} of {len(run['checks'])}", "checks confirmed"],
        [count.get("differs", 0), "checks that differ"],
    ]
    run["tables"] = [
        {
            "title": "The stations read",
            "note": "Counted from NOAA's responses by the reference reader. Levels are in metres "
            "above the datum named; the annual series is detrended by NOAA.",
            "head": [
                "Station",
                "Name",
                "State",
                "Datum",
                "Epoch",
                "Levels",
                "Years",
                "First",
                "Last",
                "Years missing between",
                "Trend (mm/yr)",
            ],
            "rows": [
                [
                    station,
                    e["name"],
                    e["state"],
                    e["datum_levels"],
                    e["epoch"],
                    e["levels"],
                    e["years"],
                    e["first_year"],
                    e["last_year"],
                    e["years_missing_between"],
                    e["trend"] if e["trend"] is not None else "",
                ]
                for station, e in stations.items()
            ],
        },
        {
            "title": "Stations with the product, by state",
            "note": "From NOAA's list of stations, as NOAA labels the state.",
            "head": ["State", "Stations"],
            "rows": [[state, number] for state, number in index["by_state"].items()],
        },
    ]
    if series:
        galveston = [name for name in series if name.startswith("8771450")]
        run["chart"] = {
            "title": "Highest water level of each year, detrended by NOAA",
            "unit": "m",
            "x": "Year",
            "select": "Station",
            "default": galveston[0] if galveston else next(iter(series)),
            "series": series,
        }
    return run
