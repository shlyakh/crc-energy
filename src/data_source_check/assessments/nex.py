"""NEX-GDDP-CMIP6: exploration, and verification of crc-sdk's annual extremes against NASA's files.

One model and member (ACCESS-CM2, r1i1p1f1), the Texas box, one historical year and one
scenario year, the four recipes and every file version NASA serves for them. Every grid cell
of the box is recomputed from the whole downloaded file.

At crc-sdk 0.11.1 the temperature recipes fail (finding CRC-001-NEX). Their values are therefore
also compared against a local clone that carries the fix; those checks are labelled and do
not count towards the outcome of any statement step.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..adapters.crc import nex as framework
from ..core import compare
from ..core.records import CheckRecord
from ..reference import nex as reference

SOURCE = "nex-gddp-cmip6"
BOUNDS = (-106.645646, 25.837377, -93.508292, 36.500704)  # Texas, as in the data explorer
MODEL, MEMBER, GRID = "ACCESS-CM2", "r1i1p1f1", "gn"
PERIODS = (("historical", 2014), ("ssp585", 2050))
ACCEPTED_VERSIONS = ("1.0", "1.1", "1.2")  # what crc-sdk accepts (workflows/nex.py)
PROBED_VERSIONS = ("1.0", "1.1", "1.2", "2.0")
TOLERANCE = 1e-9
COLUMNS = ("year", "latitude", "longitude", "value")
ANNUAL_STEPS = ("files", "identity", "time", "area", "missing", "completeness", "output")
RECIPE_STEPS = {
    "rx1day": ("units-rain", "statistic-rain"),
    "rx5day": ("units-rain", "statistic-rain"),
    "txx": (),
    "tnn": (),
}


def cases() -> list[dict[str, Any]]:
    out = []
    for scenario, year in PERIODS:
        for recipe in ("rx1day", "rx5day", "txx", "tnn"):
            out.append({"recipe": recipe, "scenario": scenario, "year": year, "version": "1.0"})
        out.append({"recipe": "rx1day", "scenario": scenario, "year": year, "version": "1.1"})
    out.append({"recipe": "rx5day", "scenario": "historical", "year": 2014, "version": "1.1"})
    return out


def label(case: dict[str, Any]) -> str:
    return f"{case['recipe']} {case['scenario']} {case['year']} v{case['version']}"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", text.lower())


Runner = Callable[..., None]


def _request(case: dict[str, Any], bounds: Sequence[float]) -> dict[str, Any]:
    return case | {"model": MODEL, "member": MEMBER, "grid": GRID, "bounds": list(bounds)}


def _address(case: dict[str, Any]) -> str:
    variable = reference.RECIPES[case["recipe"]][0]
    return reference.url(variable, MODEL, case["scenario"], MEMBER, GRID, case["year"],
                         case["version"])  # fmt: skip


def _framework(
    case: dict[str, Any], folder: Path, *, live: bool, source: Path | None,
    bounds: Sequence[float], runner: Runner,
) -> dict:  # fmt: skip
    """crc-sdk's stored answer for a case; asked for only when it is not stored yet."""
    import json

    path = folder / f"{_slug(label(case))}.json"
    if not path.exists():
        if not live:
            raise FileNotFoundError(f"no stored crc-sdk answer for {label(case)}; run with --live")
        runner(_request(case, bounds), path, crc_sdk_source=source)
    return json.loads(path.read_text(encoding="utf-8"))


def assess(
    cache: Path,
    *,
    live: bool,
    versions: dict[str, str],
    fixed_clone: Path | None = None,
    rules: reference.Rules | None = None,
    todo: list[dict[str, Any]] | None = None,
    bounds: tuple[float, float, float, float] = BOUNDS,
    runner: Runner = framework.annual,
    log: Callable[[str], None] = lambda _: None,
) -> dict[str, Any]:
    """The records of one run. ``rules`` overrides the reference rules (for fault tests)."""
    todo = cases() if todo is None else todo
    missing_case = {"recipe": "rx1day", "scenario": "historical", "year": 2014, "version": "1.2"}

    log("reference: files")
    addresses = sorted({_address(case) for case in todo})
    with ThreadPoolExecutor(max_workers=4) as pool:
        files = dict(zip(addresses, pool.map(
            lambda a: reference.download(a, cache / "reference", live=live), addresses),
            strict=True))  # fmt: skip

    log("crc-sdk: installed version")
    with ThreadPoolExecutor(max_workers=4) as pool:
        pinned = list(pool.map(
            lambda c: _framework(c, cache / "framework" / "installed", live=live, source=None,
                                 bounds=bounds, runner=runner),
            [*todo, missing_case]))  # fmt: skip
    absent = pinned.pop()
    failing = [case for case, got in zip(todo, pinned, strict=True) if got["error"]]
    fixed: dict[str, dict] = {}
    if fixed_clone is not None and failing:
        log("crc-sdk: local clone with the fix")
        with ThreadPoolExecutor(max_workers=4) as pool:
            answers = pool.map(
                lambda c: _framework(c, cache / "framework" / "fixed-clone", live=live,
                                     source=fixed_clone, bounds=bounds, runner=runner),
                failing)  # fmt: skip
            fixed = {label(case): got for case, got in zip(failing, answers, strict=True)}

    checks: list[CheckRecord] = []
    boxes: dict[str, dict[str, Any]] = {}
    summaries: list[dict[str, Any]] = []

    def one(case: dict[str, Any], got: dict[str, Any]) -> None:
        name = label(case)
        log(f"compare: {name}")
        address = _address(case)
        provenance = files[address]
        variable, source_unit, unit = reference.RECIPES[case["recipe"]]
        inputs = (
            {"role": "reference download", **{k: provenance.get(k) for k in
             ("url", "sha256", "retrieved_at", "etag", "last_modified", "bytes")}},
            {"role": "crc-sdk answer (range requests)", "url": address},
        )  # fmt: skip
        if address not in boxes:
            boxes[address] = reference.read_box(Path(provenance["path"]), variable, bounds,
                                                case["year"], rules)  # fmt: skip
        box = boxes[address]
        ours = reference.annual_rows(box, case["recipe"], case["year"], rules)
        expected = [[row[c] for c in COLUMNS] for row in ours]
        cells = len(box["lat"]) * len(box["lon"])
        summaries.append({
            "case": name, "file": address.rsplit("/", 1)[-1],
            "file_version": box["attrs"].get("version"),
            "licence_in_file": box["attrs"].get("cmip6_license"),
            "calendar": box["calendar"], "days": len(box["day_offsets"]),
            "cells_in_box": cells, "cells_with_a_value": len(ours),
            "lowest": min((row["value"] for row in ours), default=None),
            "highest": max((row["value"] for row in ours), default=None), "unit": unit,
            "units_in_file": box["variable_attrs"].get("units"),
        })  # fmt: skip

        def make(check: str, category: str, method: str, agrees: bool | None, *,
                 answer: dict = got, **more: Any) -> CheckRecord:  # fmt: skip
            used = dict(versions)
            if "fixed-clone" in check:
                used["crc-sdk"] = f"{versions['crc-sdk']} with the fix of CRC-001-NEX (local clone)"
            return compare.record(
                source=SOURCE, check=f"{check}[{name}]", tier="verification", category=category,
                method=method, agrees=agrees, versions=used, inputs=inputs, **more,
            )  # fmt: skip

        def annual(check: str, answer: dict, steps: tuple[str, ...], where: str) -> CheckRecord:
            result = compare.compare_rows(COLUMNS, expected, answer["rows"], tolerance=TOLERANCE)
            result |= {"cells_in_box": cells, "crc_sdk_path": answer["crc_sdk_path"]}
            return make(
                check, "fidelity",
                f"Every grid cell of the box: the annual value recomputed in Python from the "
                f"whole NASA file, against the rows {where} returns, in order.",
                compare.rows_agree(result) if result["values_compared"] else None,
                result=result, sample={"cells": "all in the box", "bounds": list(bounds)},
                tolerance={"numbers": f"within {TOLERANCE}", "order": "identical"},
                steps=steps, note="" if result["values_compared"] else "no cell to compare",
            )  # fmt: skip

        if got["error"]:
            declared = box["variable_attrs"].get("units")
            checks.append(make(
                "units", "consistency",
                "The unit the file declares against the unit crc-sdk requires for the recipe; "
                "a file that declares the required unit must be accepted.",
                declared != source_unit,  # refusing is right only if the file's unit is wrong
                result={"unit_in_file": declared, "unit_required": source_unit,
                        "crc_sdk_error": f"{got['error_type']}: {got['error']}"[:400]},
                tolerance={"unit": "identical text"}, steps=("units-temperature",),
            ))  # fmt: skip
            if name in fixed:
                checks.append(annual("annual-fixed-clone", fixed[name], (),
                                     "the local clone with the fix"))  # fmt: skip
            return
        checks.append(annual("annual", got, ANNUAL_STEPS + RECIPE_STEPS[case["recipe"]],
                             "crc-sdk"))  # fmt: skip
        labels = got["labels"]
        wanted = {
            "unit": [unit], "recipe": [case["recipe"]], "model": [MODEL],
            "scenario": [case["scenario"]], "member": [MEMBER], "version": [case["version"]],
            "calendar": [reference.calendar_name(box["calendar"])], "source_url": [address],
            "archive_licence": ["CC0-1.0"],
            "original_model_licence": [box["attrs"].get("cmip6_license")],
        }  # fmt: skip
        wrong = {key: labels.get(key) for key, value in wanted.items() if labels.get(key) != value}
        warned = any("RestrictiveLicenceWarning" in text for text in got["warnings"])
        checks.append(make(
            "labels", "consistency",
            "The labels on crc-sdk's rows against the request and the file's own attributes: "
            "unit, recipe, model, scenario, member, version, calendar, address, both licences; "
            "and whether a warning is raised when the file's licence is not CC0.",
            not wrong and warned == (box["attrs"].get("cmip6_license") != "CC0-1.0")
            and "attribution" in labels and "retrieved_at" in labels,
            result={"labels_wrong": wrong, "licence_in_file": box["attrs"].get("cmip6_license"),
                    "licence_warning_raised": warned,
                    "has_checksum_column": any("sha" in c or "checksum" in c
                                               for c in got["columns"]),
                    "columns": got["columns"]},
            tolerance={"labels": "identical text"}, steps=("labels", "licence"),
        ))  # fmt: skip

    for case, got in zip(todo, pinned, strict=True):
        one(case, got)

    # A version NASA does not have must fail, not be replaced by another.
    checks.append(compare.record(
        source=SOURCE, check="missing-version", tier="verification", category="fidelity",
        method=f"Ask crc-sdk for {label(missing_case)}, which NASA does not have (HTTP 404): "
        "crc-sdk must raise and return no rows.",
        agrees=bool(absent["error"]) and not absent["rows"], versions=versions,
        inputs=({"role": "crc-sdk answer", "url": _address(missing_case)},),
        result={"crc_sdk_error": f"{absent['error_type']}: {absent['error']}"[:300],
                "rows_returned": len(absent["rows"])},
        tolerance={"behaviour": "an error and no rows"}, steps=("versions",),
    ))  # fmt: skip

    served = _versions_served(cache, live=live)
    extra = sorted({v for row in served for v, code in row["status"].items()
                    if code == 200 and v not in ACCEPTED_VERSIONS})  # fmt: skip
    checks.append(compare.record(
        source=SOURCE, check="versions-served", tier="verification", category="completeness",
        method="For each variable and year assessed, ask NASA (HEAD) for file versions "
        f"{', '.join(PROBED_VERSIONS)} and compare with the versions crc-sdk accepts.",
        agrees=not extra, versions=versions,
        inputs=({"role": "publisher listing (HEAD)", "url": reference.ARCHIVE},),
        result={"accepted_by_crc_sdk": list(ACCEPTED_VERSIONS), "probed": list(PROBED_VERSIONS),
                "served_but_not_accepted": extra, "by_file": served},
        tolerance={"versions": "every version served can be requested"},
        steps=("versions-offered",),
    ))  # fmt: skip

    return present({
        "source": SOURCE,
        "versions": dict(versions),
        "run_at": compare.now(),
        "selection": {"model": MODEL, "member": MEMBER, "grid": GRID, "bounds": list(bounds),
                      "periods": [list(p) for p in PERIODS]},
        "options_assessed": {
            "recipe": sorted({c["recipe"] for c, got in zip(todo, pinned, strict=True)
                              if not got["error"]}),
            "scenario": sorted({c["scenario"] for c in todo}),
            "version": sorted({c["version"] for c in todo}),
        },
        "fixed_clone": str(fixed_clone) if fixed else "",
        "checks": [check.to_dict() for check in checks],
        "exploration": {"cases": summaries, "versions_served": served,
                        "version_differences": _version_differences(cache, rules)},
    })  # fmt: skip


def _versions_served(cache: Path, *, live: bool) -> list[dict[str, Any]]:
    import json

    stored = cache / "versions-served.json"
    if stored.exists() and not live:
        return list(json.loads(stored.read_text(encoding="utf-8")))
    if not live:
        raise FileNotFoundError("no stored listing of versions; run with --live")
    out = []
    for scenario, year in PERIODS:
        for variable in ("tasmax", "tasmin", "pr"):
            status = {
                v: reference.status(reference.url(variable, MODEL, scenario, MEMBER, GRID, year, v))
                for v in PROBED_VERSIONS
            }
            out.append({"variable": variable, "scenario": scenario, "year": year,
                        "status": status})  # fmt: skip
    cache.mkdir(parents=True, exist_ok=True)
    stored.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def _version_differences(cache: Path, rules: reference.Rules | None) -> list[dict[str, Any]]:
    """How the annual values differ between file versions already downloaded (reference only)."""
    out = []
    for scenario, year in PERIODS:
        for recipe in ("rx1day", "txx"):
            variable = reference.RECIPES[recipe][0]
            rows = {}
            for version in PROBED_VERSIONS:
                address = reference.url(variable, MODEL, scenario, MEMBER, GRID, year, version)
                path = cache / "reference" / address.rsplit("/", 1)[-1]
                if path.exists():
                    box = reference.read_box(path, variable, BOUNDS, year, rules)
                    rows[version] = {
                        (r["latitude"], r["longitude"]): r["value"]
                        for r in reference.annual_rows(box, recipe, year, rules)
                    }
            base = rows.get("1.0")
            for version, values in rows.items():
                if version == "1.0" or base is None:
                    continue
                shared = sorted(set(base) & set(values))
                gaps = [abs(base[k] - values[k]) for k in shared]
                out.append({
                    "recipe": recipe, "scenario": scenario, "year": year, "version": version,
                    "cells": len(shared), "cells_differing": sum(1 for g in gaps if g > TOLERANCE),
                    "largest_difference": max(gaps, default=0.0),
                    "cells_only_in_one": len(set(base) ^ set(values)),
                })  # fmt: skip
    return out


def _summary(check: dict[str, Any]) -> str:
    result = check["result"]
    if "values_compared" in result:
        return (
            f"{compare.number(result['rows_reference'])} cells with a value of "
            f"{compare.number(result['cells_in_box'])} in the box, against "
            f"{compare.number(result['rows_framework'])}; "
            f"{compare.number(result['values_differing'])} values differ; largest difference "
            f"{result['largest_difference']:.1e}"
        )
    if "unit_in_file" in result:
        return (
            f"the file declares {result['unit_in_file']!r}, the recipe requires "
            f"{result['unit_required']!r}; crc-sdk raises: {result['crc_sdk_error'][:160]}"
        )
    if "labels_wrong" in result:
        return (
            f"{len(result['labels_wrong'])} labels wrong; licence in the file "
            f"{result['licence_in_file']}; warning raised: "
            f"{'yes' if result['licence_warning_raised'] else 'no'}; checksum column: "
            f"{'yes' if result['has_checksum_column'] else 'no'}"
        )
    if "rows_returned" in result:
        return f"crc-sdk raises ({result['crc_sdk_error'][:120]}); {result['rows_returned']} rows"
    if "served_but_not_accepted" in result:
        extra = ", ".join(result["served_but_not_accepted"]) or "none"
        return f"served by NASA but not accepted by crc-sdk: {extra}"
    return check.get("note", "")


def present(run: dict[str, Any]) -> dict[str, Any]:
    """Add what the page and the report show: summaries, headline numbers, tables."""
    for check in run["checks"]:
        check["summary"] = _summary(check)
    count = compare.tally(run["checks"])
    annual = [c["result"] for c in run["checks"] if c["check"].startswith("annual[")]
    with_fix = [c["result"] for c in run["checks"] if c["check"].startswith("annual-fixed")]
    explored = run["exploration"]
    run["headline"] = [
        [sum(r["rows_reference"] for r in annual), "cell values compared, installed version"],
        [sum(r["values_differing"] for r in annual), "values that differ"],
        [sum(r["rows_reference"] for r in with_fix), "cell values compared with the fix"],
        [f"{count.get('confirmed', 0)} of {len(run['checks'])}", "checks confirmed"],
        [count.get("differs", 0), "checks that differ"],
    ]
    fmt = lambda v: "" if v is None else f"{v:.2f}"  # noqa: E731
    run["tables"] = [
        {
            "title": "What was read",
            "note": f"Model {run['selection']['model']}, member {run['selection']['member']}, "
            "the Texas box. Counted from NASA's files by the reference reader.",
            "head": ["Case", "File version", "Licence in the file", "Calendar", "Days",
                     "Cells in box", "Cells with a value", "Lowest", "Highest", "Unit"],
            "rows": [
                [c["case"], c["file_version"], c["licence_in_file"], c["calendar"], c["days"],
                 c["cells_in_box"], c["cells_with_a_value"], fmt(c["lowest"]),
                 fmt(c["highest"]), c["unit"]]
                for c in explored["cases"]
            ],
        },
        {
            "title": "File versions NASA serves",
            "note": "HTTP status of each version's address. crc-sdk accepts "
            f"{', '.join(ACCEPTED_VERSIONS)}.",
            "head": ["Variable", "Scenario", "Year", *[f"v{v}" for v in PROBED_VERSIONS]],
            "rows": [
                [row["variable"], row["scenario"], str(row["year"]),
                 *["served" if row["status"][v] == 200 else f"no ({row['status'][v]})"
                   for v in PROBED_VERSIONS]]
                for row in explored["versions_served"]
            ],
        },
        {
            "title": "Do the file versions give different annual values?",
            "note": "Annual values from each later version against version 1.0, in the box "
            "(reference reader only; crc-sdk is not involved).",
            "head": ["Recipe", "Scenario", "Year", "Version", "Cells", "Cells that differ",
                     "Largest difference"],
            "rows": [
                [d["recipe"], d["scenario"], str(d["year"]), d["version"], d["cells"],
                 d["cells_differing"], f"{d['largest_difference']:.3g}"]
                for d in explored["version_differences"]
            ],
        },
    ]  # fmt: skip
    return run
