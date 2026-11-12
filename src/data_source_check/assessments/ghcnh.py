"""GHCNh: exploration, and verification of crc-sdk's annual extremes against NOAA's files.

The population is the stations the Texas data explorer uses: the first forty ``USW`` stations
crc-sdk's catalogue selects in the Texas box, years 2000 to 2024. Every station-year NOAA
has a file for is recomputed from the Parquet file; a seeded subset is recomputed again from
NOAA's pipe-separated file with the standard library only.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..adapters.crc import ghcnh as framework
from ..core import compare
from ..core.records import CheckRecord
from ..reference import ghcnh as reference

SOURCE = "ghcnh"
SEED = 20261111
BOUNDS = (-106.645646, 25.837377, -93.508292, 36.500704)  # Texas, as in the data explorer
STATIONS = 40
YEARS = (2000, 2024)
MINIMUM_YEARS = 15  # the explorer's setting; crc-sdk's default is 20
PSV_SAMPLE = 8
RECIPES = {"temperature_max": "value_max", "temperature_min": "value_min"}
FAMILIES = {"temperature_max": "genextreme", "temperature_min": "gumbel_l"}
FIELDS = (
    "station",
    "year",
    "latitude",
    "longitude",
    "elevation",
    "valid_days",
    "expected_days",
    "accepted_reports",
    "reports",
    "value",
    "complete",
)
EXACT = {"values": "exact equality, numbers included"}
ANNUAL_STEPS = (
    "files",
    "columns",
    "time",
    "quality",
    "range",
    "units",
    "day",
    "valid-day",
    "valid-year",
    "annual-value",
    "location",
)


def _as_rows(table: Sequence[dict[str, Any]], value: str) -> list[list[Any]]:
    ordered = sorted(table, key=lambda row: (row["station"], row["year"]))
    return [[row[value] if name == "value" else row[name] for name in FIELDS] for row in ordered]


def _files_summary(role: str, files: Sequence[dict[str, Any]]) -> dict[str, Any]:
    present = [item for item in files if not item["missing"]]
    listing = "".join(sorted(f"{item['url']} {item['sha256']}\n" for item in present))
    return {
        "role": role,
        "url": f"{reference.ROOT} ({len(present)} files)",
        "sha256": hashlib.sha256(listing.encode()).hexdigest(),
        "retrieved_at": max((item["retrieved_at"] for item in files), default=""),
        "files": len(present),
        "files_absent_at_publisher": len(files) - len(present),
        "bytes": sum(item["bytes"] for item in present),
    }


def assess(
    cache: Path,
    sdk_cache: Path,
    *,
    live: bool,
    versions: dict[str, str],
    rules: reference.Rules | None = None,
    stations: Sequence[str] | None = None,
    names: dict[str, str] | None = None,
    years: tuple[int, int] = YEARS,
    minimum_years: int = MINIMUM_YEARS,
    psv_sample: int = PSV_SAMPLE,
    log: Callable[[str], None] = lambda _: None,
) -> dict[str, Any]:
    """The records of one run. ``rules`` overrides the reference rules (for fault tests)."""
    catalogue_size = None
    if stations is None:
        listed = framework.catalogue(BOUNDS, sdk_cache, live=live)
        catalogue_size = len(listed)
        chosen = [row for row in listed if row["station"].startswith("USW")][:STATIONS]
        stations = [row["station"] for row in chosen]
        names = {row["station"]: row["name"] for row in chosen}
    names = names or {}
    span = range(years[0], years[1] + 1)
    jobs = [(station, year) for station in stations for year in span]

    log(f"reference: {len(jobs)} station-years from Parquet")
    with ThreadPoolExecutor(max_workers=8) as pool:
        files = list(
            pool.map(
                lambda job: reference.download(*job, "parquet", cache / "reference", live=live),
                jobs,
            )
        )
    ours = [
        reference.station_year(
            station, year, "parquet", cache / "reference", live=False, rules=rules
        )[0]
        for station, year in jobs
    ]
    failed = sorted({row["station"] for row in ours if row["error"]})
    parquet_input = _files_summary("reference download (Parquet)", files)

    with_file = [
        (row["station"], row["year"])
        for row in ours
        if row["reports"] and row["station"] not in failed
    ]
    picked = compare.sample(with_file, psv_sample, SEED)
    log(f"reference: {len(picked)} station-years from pipe-separated files")
    psv_rows, psv_files = [], []
    for station, year in picked:
        row, provenance = reference.station_year(
            station, year, "psv", cache / "reference", live=live, rules=rules
        )
        psv_rows.append(row)
        psv_files.append(provenance)
    psv_input = _files_summary("reference download (pipe-separated)", psv_files)

    checks: list[CheckRecord] = []
    curves_at: dict[str, dict[str, Any]] = {}
    for recipe, value in RECIPES.items():
        log(f"crc-sdk: {recipe}")
        theirs, errors = framework.annual(recipe, stations, years, sdk_cache, live=live)
        sdk_input = {
            "role": "crc-sdk annual table",
            "url": reference.ROOT,
            "retrieved_at": compare.now() if live else "",
        }
        kept = [row for row in ours if row["station"] not in failed]
        result = compare.compare_rows(FIELDS, _as_rows(kept, value), _as_rows(theirs, "value"))
        result |= {
            "stations": len(stations),
            "station_years": len(jobs),
            "station_years_with_a_file": sum(1 for item in files if not item["missing"]),
            "complete_years_reference": sum(1 for row in kept if row["complete"]),
            "stations_refused_reference": failed,
            "stations_refused_framework": sorted(errors),
        }
        checks.append(
            compare.record(
                source=SOURCE,
                check=f"annual[{recipe}]",
                tier="verification",
                category="fidelity",
                method="Every station-year: the annual value and its audit counts recomputed in "
                "Python from NOAA's Parquet file (read without crc-sdk or pyarrow), against "
                "crc-sdk's annual_extremes() table, field by field.",
                agrees=(compare.rows_agree(result) and failed == sorted(errors))
                if result["values_compared"]
                else None,
                versions=versions,
                inputs=(parquet_input, sdk_input),
                result=result,
                sample={"stations": "all " + str(len(stations)), "years": list(years)},
                tolerance=EXACT,
                steps=ANNUAL_STEPS,
                note="" if result["values_compared"] else "no station-year to compare",
            )
        )

        keys = set(picked)
        expected = _as_rows(psv_rows, value)
        got = _as_rows([row for row in theirs if (row["station"], row["year"]) in keys], "value")
        result = compare.compare_rows(FIELDS, expected, got)
        checks.append(
            compare.record(
                source=SOURCE,
                check=f"second-format[{recipe}]",
                tier="verification",
                category="fidelity",
                method="A seeded sample of station-years recomputed from NOAA's pipe-separated "
                "file with the standard library only, against crc-sdk's annual_extremes() table.",
                agrees=compare.rows_agree(result) if result["values_compared"] else None,
                versions=versions,
                inputs=(psv_input, sdk_input),
                result=result,
                sample={"seed": SEED, "station_years": [list(key) for key in picked]},
                tolerance=EXACT,
                steps=ANNUAL_STEPS,
                note="" if result["values_compared"] else "no station-year to compare",
            )
        )

        complete = Counter(row["station"] for row in kept if row["complete"])
        should = sorted(s for s in stations if complete[s] >= minimum_years)
        if should:
            try:
                made = framework.curves(
                    recipe,
                    [s for s in stations if s not in failed],
                    years,
                    sdk_cache,
                    cache / f"curves-{recipe}.parquet",
                    minimum_years=minimum_years,
                    live=live,
                )
            except ValueError as error:  # crc-sdk refuses a station the reference kept
                made = {"stations": [], "families": [], "refused": str(error)}
            curves_at[recipe] = made
            checks.append(
                compare.record(
                    source=SOURCE,
                    check=f"curve-stations[{recipe}]",
                    tier="verification",
                    category="completeness",
                    method="Stations that receive a fitted curve from crc-sdk against the stations "
                    "whose recomputed series has at least the minimum number of complete years; "
                    "and the distribution family named in the output.",
                    agrees=made["stations"] == should and made["families"] == [FAMILIES[recipe]],
                    versions=versions,
                    inputs=(parquet_input, sdk_input),
                    result={
                        "minimum_years": minimum_years,
                        "stations_expected": should,
                        "stations_with_a_curve": made["stations"],
                        "families": made["families"],
                        "family_expected": FAMILIES[recipe],
                        "refused_by_framework": made.get("refused", ""),
                    },
                    tolerance={"stations": "identical sets", "family": "as documented"},
                    steps=("minimum-years", "family"),
                )
            )
            wanted = {
                "licence": "CC0-1.0",
                "unit": "degC",
                "probability_semantics": "annual_exceedance",
            }
            have = {
                key: bool(made.get(key))
                for key in ("licence", "attribution", "retrieved_at", "checksum", "uri")
            }
            checks.append(
                compare.record(
                    source=SOURCE,
                    check=f"provenance[{recipe}]",
                    tier="verification",
                    category="consistency",
                    method="Licence, attribution, retrieval time, checksum, unit and probability "
                    "convention in the metadata of the curve file crc-sdk writes.",
                    agrees=all(have.values()) and all(made.get(k) == v for k, v in wanted.items()),
                    versions=versions,
                    inputs=(sdk_input,),
                    result={
                        "fields_present": have,
                        "tail": made.get("tail"),
                        **{key: made.get(key) for key in wanted},
                    },
                    tolerance={"fields": "all present; licence, unit and convention as documented"},
                    steps=("provenance", "units"),
                )
            )
        else:
            for name, steps in (
                ("curve-stations", ("minimum-years", "family")),
                ("provenance", ("provenance", "units")),
            ):
                checks.append(
                    compare.record(
                        source=SOURCE,
                        check=f"{name}[{recipe}]",
                        tier="verification",
                        category="completeness",
                        method="Curve file written by crc-sdk.",
                        agrees=None,
                        versions=versions,
                        steps=steps,
                        note=f"no station has {minimum_years} complete years in this selection",
                    )
                )

    excluded: Counter[str] = Counter()
    for row in ours:
        excluded.update(row["excluded"])
    by_station = []
    for station in stations:
        mine = [row for row in ours if row["station"] == station]
        have = [row["year"] for row in mine if row["reports"]]
        by_station.append(
            {
                "station": station,
                "name": names.get(station, ""),
                "first_year": min(have, default=None),
                "last_year": max(have, default=None),
                "years_with_a_file": len(have),
                "complete_years": sum(1 for row in mine if row["complete"]),
                "reports": sum(row["reports"] for row in mine),
                "accepted_reports": sum(row["accepted_reports"] for row in mine),
                "refused": next((row["error"] for row in mine if row["error"]), ""),
            }
        )
    reports = sum(item["reports"] for item in by_station)
    exploration = {
        "selection": {
            "bounds": list(BOUNDS),
            "rule": f"first {len(stations)} USW stations of crc-sdk's "
            "catalogue selection for the box",
            "stations_in_catalogue_selection": catalogue_size,
            "years": list(years),
            "minimum_years": minimum_years,
        },
        "stations": by_station,
        "station_years": len(jobs),
        "station_years_with_a_file": sum(1 for item in files if not item["missing"]),
        "station_years_complete": sum(item["complete_years"] for item in by_station),
        "reports": reports,
        "accepted_reports": sum(item["accepted_reports"] for item in by_station),
        "excluded_by_rule": dict(sorted(excluded.items())),
        "stations_with_minimum_years": sum(
            1 for item in by_station if item["complete_years"] >= minimum_years
        ),
        "stations_with_20_years": sum(1 for item in by_station if item["complete_years"] >= 20),
        "framework_rules": framework.defaults(),
        "curves": curves_at,
    }
    return present(
        {
            "source": SOURCE,
            "seed": SEED,
            "versions": dict(versions),
            "run_at": compare.now(),
            "recipes_assessed": sorted(RECIPES),
            "checks": [check.to_dict() for check in checks],
            "exploration": exploration,
            "files": [
                {
                    key: item.get(key)
                    for key in (
                        "url",
                        "sha256",
                        "etag",
                        "last_modified",
                        "bytes",
                        "missing",
                        "retrieved_at",
                    )
                }
                for item in [*files, *psv_files]
            ],
        }
    )


def _summary(check: dict[str, Any]) -> str:
    result = check["result"]
    if "values_compared" in result:
        text = compare.rows_summary(result).replace(" rows ", " station-years ", 1)
        if "station_years_with_a_file" in result:
            text += (
                f"; {compare.number(result['station_years_with_a_file'])} have a file, "
                f"{compare.number(result['complete_years_reference'])} are complete"
            )
        return text
    if "stations_expected" in result:
        return (
            f"{len(result['stations_with_a_curve'])} stations with a curve, "
            f"{len(result['stations_expected'])} expected at {result['minimum_years']} complete "
            f"years; family {', '.join(result['families'])}"
        )
    if "fields_present" in result:
        fields = result["fields_present"]
        return (
            f"{sum(fields.values())} of {len(fields)} provenance fields present; licence "
            f"{result['licence']}; unit {result['unit']}; {result['probability_semantics']}"
        )
    return check.get("note", "")


def present(run: dict[str, Any]) -> dict[str, Any]:
    """Add what the page and the report show: summaries, headline numbers, tables, a chart."""
    for check in run["checks"]:
        check["summary"] = _summary(check)
    explored = run["exploration"]
    selection = explored["selection"]
    annual = [c["result"] for c in run["checks"] if c["check"].startswith("annual[")]
    count = compare.tally(run["checks"])
    run["headline"] = [
        [explored["reports"], "hourly reports read from the publisher"],
        [explored["station_years"], "station-years recomputed"],
        [sum(r["values_differing"] for r in annual), "values that differ"],
        [f"{count.get('confirmed', 0)} of {len(run['checks'])}", "checks confirmed"],
        [count.get("differs", 0), "checks that differ"],
    ]
    reports = explored["reports"] or 1
    run["tables"] = [
        {
            "title": "From stations to curves",
            "note": f"Selection: {selection['rule']}, years {selection['years'][0]} to "
            f"{selection['years'][1]}. Counted from NOAA's files by the reference reader.",
            "head": ["Stage", "Count"],
            "rows": [
                [
                    "Stations crc-sdk's catalogue selects in the box",
                    selection["stations_in_catalogue_selection"] or "not counted",
                ],
                ["Stations assessed", len(explored["stations"])],
                ["Station-years requested", explored["station_years"]],
                ["Station-years NOAA has a file for", explored["station_years_with_a_file"]],
                ["Station-years complete (enough valid days)", explored["station_years_complete"]],
                [
                    f"Stations with at least {selection['minimum_years']} complete years "
                    "(the explorer's setting)",
                    explored["stations_with_minimum_years"],
                ],
                [
                    "Stations with at least 20 complete years (crc-sdk's default)",
                    explored["stations_with_20_years"],
                ],
            ],
        },
        {
            "title": "Hourly reports and the rules that exclude them",
            "note": "A rule with no row excluded nothing in these files.",
            "head": ["Reports", "Count", "Share"],
            "rows": [
                ["All reports", explored["reports"], "100 %"],
                [
                    "Accepted",
                    explored["accepted_reports"],
                    f"{100 * explored['accepted_reports'] / reports:.2f} %",
                ],
                *[
                    [f"Excluded: {reason}", n, f"{100 * n / reports:.4f} %"]
                    for reason, n in explored["excluded_by_rule"].items()
                ],
            ],
        },
        {
            "title": "Stations",
            "note": "",
            "head": [
                "Station",
                "Name",
                "First year",
                "Last year",
                "Years with a file",
                "Complete years",
                "Reports",
                "Accepted",
            ],
            "rows": [
                [
                    item["station"],
                    item["name"],
                    str(item["first_year"] or ""),
                    str(item["last_year"] or ""),
                    item["years_with_a_file"],
                    item["complete_years"],
                    item["reports"],
                    f"{100 * item['accepted_reports'] / item['reports']:.1f} %"
                    if item["reports"]
                    else "",
                ]
                for item in explored["stations"]
            ],
        },
    ]
    run["chart"] = {
        "title": "Complete years per station",
        "unit": "complete years",
        "x": "Station",
        "select": "",
        "default": "all",
        "series": {
            "all": [[item["station"], item["complete_years"]] for item in explored["stations"]]
        },
    }
    return run
