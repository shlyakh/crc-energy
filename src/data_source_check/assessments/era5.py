"""ERA5: exploration, and verification of crc-sdk's annual extremes against the publisher's store.

Draft. One store (``wb2-1p5``, the 1.5 degree WeatherBench2 copy), the Texas box (80 grid
cells), the rainfall recipes ``rx1day`` and ``rx5day`` for 2021, with and without the land
mask. Every chunk of the year covers the globe, so one variable-year is about 0.9 GB whatever
the box; that is why one variable and one year were taken.

How the two sides meet. The reference reader downloads the store's objects whole and
checksums them. crc-sdk refuses a request of fewer than four years and keeps no hourly data,
so asking it over the network would move four times those bytes again. Instead:

1. crc-sdk's own handle to the real store is compared with the reference copy on the axes,
   the array metadata and a seeded sample of chunks, bit for bit (checks ``store``, ``hours``);
2. crc-sdk then reduces the year from the reference copy, through ``HazardDataset.era5`` with
   its store address pointed at the copy's folder (checks ``annual``). It is asked for four
   years; the copy holds the hours of the compared years only, so the others give no row.

The fitted curve is not assessed here.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from ..adapters.crc import era5 as framework
from ..core import compare
from ..core.records import CheckRecord
from ..reference import era5 as reference

SOURCE = "era5"
SEED = 20261112
STORE = "wb2-1p5"
BOUNDS = (-106.645646, 25.837377, -93.508292, 36.500704)  # Texas, as in the data explorer
RECIPES = ("rx1day", "rx5day")
YEARS_ASKED = (2018, 2019, 2020, 2021)  # crc-sdk refuses fewer than four years
YEARS_COMPARED = (2021,)
PROBE_YEARS = tuple(range(1957, 2025))
SAMPLE_CHUNKS = 3
COLUMNS = ("year", "latitude", "longitude", "value")
COMMON_STEPS = ("area", "missing", "completeness", "cache", "output")
KIND_STEPS = {
    "rain": ("units-rain", "day-rain", "statistic-rain"),
    "temperature": ("units-temperature", "day-temperature", "statistic-temperature"),
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", text.lower()).strip("-")


class _Answers:
    """crc-sdk's answers, stored so that a run without the network gives the same records."""

    def __init__(self, folder: Path, *, live: bool) -> None:
        self.folder, self.live = folder, live

    def get(self, name: str, ask: Callable[[], Any]) -> Any:
        path = self.folder / f"{_slug(name)}.json"
        if self.live:
            self.folder.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(ask()), encoding="utf-8")
            temporary.replace(path)
        elif not path.exists():
            raise FileNotFoundError(f"no stored crc-sdk answer for {name}; run with --live")
        return json.loads(path.read_text(encoding="utf-8"))


def _span(accepted: dict[str, str]) -> list[int]:
    years = sorted(int(year) for year, error in accepted.items() if not error)
    return [years[0], years[-1]] if years else [0, 0]


def assess(
    cache: Path,
    *,
    live: bool,
    versions: dict[str, str],
    rules: reference.Rules | None = None,
    log: Callable[[str], None] = lambda _: None,
    store: str = STORE,
    bounds: Sequence[float] = BOUNDS,
    recipes: Sequence[str] = RECIPES,
    years_asked: Sequence[int] = YEARS_ASKED,
    years_compared: Sequence[int] = YEARS_COMPARED,
    probe_years: Sequence[int] = PROBE_YEARS,
    sample_chunks: int = SAMPLE_CHUNKS,
) -> dict[str, Any]:
    """The records of one run. ``rules`` overrides the reference rules (for fault tests)."""
    rules = rules or reference.Rules()
    copy = reference.Copy(store, cache, live=live)
    answers = _Answers(cache / "framework", live=live)
    checks: list[CheckRecord] = []

    def make(check: str, category: str, method: str, agrees: bool | None,
             **more: Any) -> None:  # fmt: skip
        checks.append(compare.record(source=SOURCE, check=check, tier="verification",
                                     category=category, method=method, agrees=agrees,
                                     versions=versions, **more))  # fmt: skip

    # ------------------------------------------------------------------ the store itself
    log("reference: metadata and axes")
    group = {"zgroup": copy.text(".zgroup"), "attributes": copy.text(".zattrs", optional=True)}
    time = reference.time_axis(copy)
    latitude = reference.axis_values(copy, "latitude")
    longitude = reference.axis_values(copy, "longitude")
    variables = sorted({reference.RECIPES[recipe][0] for recipe in reference.RECIPES})
    metas = {name: reference.array_meta(copy, name) for name in [*variables, reference.LAND_MASK]}
    copy.fetch([reference.chunk_key(metas[reference.LAND_MASK])])
    # metadata objects, the axes and the land mask: everything but the hourly chunks
    small = (".z", "time/", "latitude/", "longitude/", f"{reference.LAND_MASK}/",
             *[f"{name}/.z" for name in variables])  # fmt: skip

    log("crc-sdk: the store as it opens it")
    facts = answers.get(f"facts {store}", lambda: framework.facts(store))
    differences: dict[str, Any] = {}

    def differ(name: str, ours: Any, theirs: Any) -> None:
        if ours != theirs:
            differences[name] = {"reference": ours, "framework": theirs}

    differ("address", reference.STORES[store], facts["url"])
    differ("time steps", len(time["hours"]), facts["time_count"])
    differ("first time step", time["first"], facts["time_first"])
    differ("last time step", time["last"], facts["time_last"])
    differ("latitude", latitude, facts["latitude"])
    differ("longitude", longitude, facts["longitude"])
    for name, meta in metas.items():
        differ(f"array {name}", {k: meta[k] for k in ("dims", "shape", "chunks", "dtype")},
               facts["arrays"].get(name))  # fmt: skip
    for recipe, (variable, _, unit, _) in reference.RECIPES.items():
        differ(f"variable of {recipe}", variable, facts["recipe_variables"].get(recipe))
        differ(f"unit of {recipe}", unit, facts["recipe_units"].get(recipe))
    compared = 6 + len(metas) + 2 * len(reference.RECIPES)
    make(
        f"store[{store}]", "consistency",
        "The store as crc-sdk states and opens it (address, time axis, latitudes, longitudes, "
        "array names, dimensions, shapes, types, the array and unit of each recipe) against "
        "the same read from the store's metadata objects by the reference reader.",
        not differences,
        result={"items_compared": compared, "items_differing": len(differences),
                "differences": differences, "time_steps": len(time["hours"]),
                "grid": [len(latitude), len(longitude)]},
        inputs=({"role": "reference download", **copy.provenance(*small)},
                {"role": "crc-sdk (zarr over gcsfs, anonymous)", "url": facts["url"]}),
        tolerance={"values": "exact equality"}, steps=("store", "time-axis", "variable"),
    )  # fmt: skip

    # ------------------------------------------------------------------ a sample of chunks
    year_chunks: dict[str, list[int]] = {}
    for name in variables:
        length = metas[name]["chunks"][0]
        held = time["index"]
        year_chunks[name] = sorted({
            held[hour] // length
            for year in years_compared
            for hour in range(reference.hours_of(time, _first_hour(year)),
                              reference.hours_of(time, _first_hour(year + 1)))
            if hour in held
        })  # fmt: skip
    for name in variables:
        meta = metas[name]
        length = meta["chunks"][0]
        per_step = meta["chunks"][1] * meta["chunks"][2]
        chosen = compare.sample(year_chunks[name], sample_chunks, SEED)
        log(f"hours: {name}, chunks {chosen}")
        copy.fetch(reference.chunk_key(meta, number) for number in chosen)
        values = differing = 0
        for number in chosen:
            ours = reference.chunk_bytes(copy, meta, number)
            got = answers.get(
                f"hours {name} {number}",
                lambda v=name, n=number, size=length: framework.hours(store, v, n * size, size),
            )
            theirs = bytes.fromhex(got["values_hex"])
            size = got["count"] * per_step * 4
            if ours is None or len(theirs) != size:
                differing += per_step * length
                continue
            values += size // 4
            if ours[:size] != theirs:
                differing += sum(1 for at in range(0, size, 4)
                                 if ours[at : at + 4] != theirs[at : at + 4])  # fmt: skip
        make(
            f"hours[{name}]", "fidelity",
            "A seeded sample of the array's chunks within the compared years: every hourly "
            "value of the globe as crc-sdk's own handle returns it from the network, against "
            "the same chunk downloaded whole and decoded by the reference reader, bit for bit.",
            (differing == 0) if values else None,
            result={"chunks": chosen, "values_compared": values, "values_differing": differing},
            inputs=({"role": "reference download",
                     **copy.provenance(*[reference.chunk_key(meta, n) for n in chosen])},
                    {"role": "crc-sdk (zarr over gcsfs, anonymous)", "url": facts["url"]}),
            sample={"chunks": len(chosen), "of": len(year_chunks[name]), "seed": SEED,
                    "years": list(years_compared)},
            tolerance={"values": "identical bits"}, steps=("store", "variable"),
        )  # fmt: skip

    # ------------------------------------------------------------------ years offered
    log("coverage: years crc-sdk accepts against the time axis")
    probes = {"temperature": "txx", "rain": "rx1day"}
    accepted = {
        kind: answers.get(f"accepted {recipe}",
                          lambda r=recipe: framework.accepted_years(store, r, probe_years))
        for kind, recipe in probes.items()
    }  # fmt: skip
    held_span = {
        kind: list(reference.complete_years(time, interval_end=kind == "rain" and
                                            rules.interval_end_stamps))
        for kind in probes
    }  # fmt: skip
    accepted_span = {kind: _span(accepted[kind]) for kind in probes}
    beyond = [year for year in probe_years
              if accepted["temperature"].get(str(year)) == ""
              and year > held_span["temperature"][1]]  # fmt: skip
    empty_year: dict[str, Any] = {}
    if beyond:
        asked = [*range(beyond[0] - len(years_asked) + 1, beyond[0] + 1)]
        got = answers.get(
            f"annual txx {asked[0]}-{asked[-1]} beyond the time axis",
            lambda: framework.annual("txx", store, bounds, asked, store_copy=copy.root),
        )
        empty_year = {
            "year": beyond[0],
            "hours_of_that_year_on_the_time_axis": sum(
                1 for hour in range(reference.hours_of(time, _first_hour(beyond[0])),
                                    reference.hours_of(time, _first_hour(beyond[0] + 1)))
                if hour in time["index"]),
            "crc_sdk_error": f"{got['error_type']}: {got['error']}"[:300] if got["error"] else "",
            "rows_for_that_year": sum(1 for row in got["rows"] if row[0] == beyond[0]),
        }  # fmt: skip
    make(
        f"coverage[{store}]", "completeness",
        "The years crc-sdk accepts for a temperature and for a rainfall recipe (each year from "
        f"{probe_years[0]} to {probe_years[-1]} is offered to its own check) against the years "
        "of which the store's time axis holds every hour (for rainfall: every hour that closes "
        "a day of the year, which includes 00:00 of the next 1 January). Where crc-sdk accepts "
        "a year the axis does not hold, it is asked for that year and the outcome is recorded.",
        accepted_span == held_span,
        result={"accepted_by_crc_sdk": accepted_span, "complete_on_the_time_axis": held_span,
                "time_axis": [time["first"], time["last"]], "release_name": facts["version"],
                "last_final_date_in_crc_sdk": facts["last_final_date"],
                "store_attributes": sorted(group["attributes"]), "year_beyond": empty_year},
        inputs=({"role": "reference download", **copy.provenance("time/")},
                {"role": "crc-sdk (zarr over gcsfs, anonymous)", "url": facts["url"]}),
        tolerance={"years": "identical first and last year"}, steps=("version", "years"),
    )  # fmt: skip

    # ------------------------------------------------------------------ units declared
    declared = {name: metas[name]["attrs"].get("units") for name in variables}
    assumed = {reference.RECIPES[r][0]: reference.RECIPES[r][1] for r in reference.RECIPES}
    make(
        f"units-declared[{store}]", "consistency",
        "The unit each array declares in the store (its `units` attribute) against the unit "
        "crc-sdk's conversion assumes (kelvin for 2 m temperature, metres for precipitation).",
        declared == assumed,
        result={"declared_in_the_store": declared, "assumed_by_crc_sdk": assumed},
        inputs=({"role": "reference download", **copy.provenance(*small)},),
        tolerance={"unit": "identical text"}, steps=("units-declared",),
    )  # fmt: skip

    # ------------------------------------------------------------------ annual values
    cases = []
    for recipe in recipes:
        variable, _, unit, kind = reference.RECIPES[recipe]
        for land_only in (False, True):
            name = (f"{recipe} {'-'.join(str(y) for y in years_compared)} "
                    f"{'land only' if land_only else 'all cells'}")  # fmt: skip
            log(f"annual: {name}")
            ours: list[list[Any]] = []
            seen: dict[str, Any] = {}
            for year in years_compared:
                seen = reference.annual_rows(copy, recipe, year, bounds, land_only=land_only,
                                             rules=rules, time=time)  # fmt: skip
                ours += [[row[c] for c in COLUMNS] for row in seen.pop("rows")]
                mine = [row[3] for row in ours if row[0] == year]
                cases.append({"case": f"{recipe} {year} {name.split(' ', 2)[2]}", "unit": unit,
                              "rows": len(mine), "lowest": min(mine, default=None),
                              "highest": max(mine, default=None),
                              **{k: v for k, v in seen.items()
                                 if k not in ("lat", "lon", "unit")}})  # fmt: skip
            got = answers.get(
                f"annual {name}",
                lambda r=recipe, land=land_only: framework.annual(
                    r, store, bounds, years_asked, land_only=land, store_copy=copy.root),
            )  # fmt: skip
            theirs = [row for row in got["rows"] if row[0] in years_compared]
            other = len(got["rows"]) - len(theirs)
            result = compare.compare_rows(COLUMNS, ours, theirs)
            result |= {"cells_in_box": seen.get("cells"), "rows_for_years_not_in_the_copy": other,
                       "crc_sdk_error": f"{got['error_type']}: {got['error']}"[:300]
                       if got["error"] else "", "years_asked": list(years_asked)}  # fmt: skip
            make(
                f"annual[{name}]", "fidelity",
                "Every grid cell of the box: the annual value recomputed in plain Python from "
                "the downloaded chunks, against the rows `annual_extremes()` returns when "
                "crc-sdk reads the same downloaded chunks, in order. crc-sdk is asked for "
                f"{years_asked[0]} to {years_asked[-1]} (it refuses fewer than four years); the "
                "copy holds the hours of the compared years only, so it must return no row for "
                "the others.",
                (compare.rows_agree(result) and other == 0 and not got["error"])
                if result["values_compared"] or got["error"] else None,
                result=result,
                inputs=({"role": "reference download",
                         **copy.provenance(*[reference.chunk_key(metas[variable], n)
                                             for n in year_chunks[variable]], *small)},
                        {"role": "crc-sdk, reading the reference copy",
                         "url": str(copy.root.name)}),
                sample={"cells": "all in the box", "bounds": list(bounds),
                        "years": list(years_compared), "land_only": land_only},
                tolerance={"values": "exact equality", "order": "identical"},
                steps=COMMON_STEPS + KIND_STEPS[kind] + (("land-mask",) if land_only else ()),
                note="" if result["values_compared"] or got["error"] else "no cell to compare",
            )  # fmt: skip

    total = copy.provenance("")
    hourly = copy.provenance(*[f"{name}/" for name in variables])
    return present({
        "source": SOURCE,
        "versions": dict(versions),
        "run_at": compare.now(),
        "selection": {"store": store, "bounds": list(bounds), "years_asked": list(years_asked),
                      "years_compared": list(years_compared), "seed": SEED},
        "options_assessed": {"recipe": sorted(recipes), "store": [store]},
        "checks": [check.to_dict() for check in checks],
        "exploration": {
            "cases": cases,
            "store": {"address": reference.STORES[store], "time_first": time["first"],
                      "time_last": time["last"], "time_steps": len(time["hours"]),
                      "time_units": time["units"], "calendar": time["calendar"],
                      "latitudes": len(latitude), "longitudes": len(longitude),
                      "units_declared": declared,
                      "chunks": {name: metas[name]["chunks"] for name in variables}},
            # everything the copy holds, which may be more than this run read
            "copy": {"objects": total["objects"], "bytes": total["bytes"],
                     "objects_not_in_the_store": total["objects_missing"],
                     "hourly_chunks": hourly["objects"]},
        },
    })  # fmt: skip


def _first_hour(year: int) -> datetime:
    return datetime(year, 1, 1)


def _summary(check: dict[str, Any]) -> str:
    result = check["result"]
    if "rows_reference" in result:
        text = (
            f"{compare.number(result['rows_reference'])} cells with a value of "
            f"{compare.number(result['cells_in_box'])} in the box, against "
            f"{compare.number(result['rows_framework'])}; "
            f"{compare.number(result['values_compared'])} values compared, "
            f"{compare.number(result['values_differing'])} differ; largest difference "
            f"{result['largest_difference']:.1e}; rows for years not in the copy: "
            f"{result['rows_for_years_not_in_the_copy']}"
        )
        return text + (f"; crc-sdk raises: {result['crc_sdk_error'][:120]}"
                       if result["crc_sdk_error"] else "")  # fmt: skip
    if "chunks" in result:
        return (
            f"{len(result['chunks'])} chunks, {compare.number(result['values_compared'])} hourly "
            f"values compared, {compare.number(result['values_differing'])} differ"
        )
    if "items_compared" in result:
        names = ", ".join(result["differences"]) or "none"
        return (
            f"{result['items_compared']} items compared, {result['items_differing']} differ "
            f"({names}); {compare.number(result['time_steps'])} time steps, grid "
            f"{result['grid'][0]} by {result['grid'][1]}"
        )
    if "accepted_by_crc_sdk" in result:
        ours, theirs = result["complete_on_the_time_axis"], result["accepted_by_crc_sdk"]
        text = "; ".join(
            f"{kind}: crc-sdk accepts {theirs[kind][0]}-{theirs[kind][1]}, the time axis holds "
            f"{ours[kind][0]}-{ours[kind][1]} complete"
            for kind in sorted(ours)
        )
        beyond = result["year_beyond"]
        if beyond:
            text += (
                f"; asked for {beyond['year']}: {beyond['rows_for_that_year']} rows, "
                + (f"error {beyond['crc_sdk_error'][:80]}" if beyond["crc_sdk_error"]
                   else "no error")
            )  # fmt: skip
        return text
    if "declared_in_the_store" in result:
        return "; ".join(
            f"{name}: the store declares {unit!r}, crc-sdk assumes "
            f"{result['assumed_by_crc_sdk'][name]!r}"
            for name, unit in sorted(result["declared_in_the_store"].items())
        )
    return check.get("note", "")


def present(run: dict[str, Any]) -> dict[str, Any]:
    """Add what the page and the report show: summaries, headline numbers, tables."""
    for check in run["checks"]:
        check["summary"] = _summary(check)
    count = compare.tally(run["checks"])
    annual = [c["result"] for c in run["checks"] if c["check"].startswith("annual[")]
    hours = [c["result"] for c in run["checks"] if c["check"].startswith("hours[")]
    explored = run["exploration"]
    run["headline"] = [
        [sum(r["rows_reference"] for r in annual), "annual cell values recomputed"],
        [sum(r["values_differing"] for r in annual), "annual values that differ"],
        [sum(r["values_compared"] for r in hours), "hourly values compared bit for bit"],
        [f"{count.get('confirmed', 0)} of {len(run['checks'])}", "checks confirmed"],
        [count.get("differs", 0), "checks that differ"],
    ]
    fmt = lambda v: "" if v is None else f"{v:.2f}"  # noqa: E731
    store = explored["store"]
    run["tables"] = [
        {
            "title": "What was read",
            "note": f"Store {run['selection']['store']}, the Texas box. Counted from the "
            "downloaded chunks by the reference reader.",
            "head": ["Case", "Cells in box", "Cells with a value", "Days in year",
                     "Hours expected", "Hours on the time axis", "Days with a value (lowest)",
                     "Lowest", "Highest", "Unit"],
            "rows": [
                [c["case"], c["cells"], c["rows"], c["days_in_year"], c["hours_expected"],
                 c["hours_on_the_time_axis"], c["days_valid_lowest"], fmt(c["lowest"]),
                 fmt(c["highest"]), c["unit"]]
                for c in explored["cases"]
            ],
        },
        {
            "title": "The store",
            "note": "Read from the store's metadata objects and its time axis.",
            "head": ["Item", "Value"],
            "rows": [
                ["Address", store["address"]],
                ["First time step", store["time_first"]],
                ["Last time step", store["time_last"]],
                ["Time steps", store["time_steps"]],
                ["Time units, calendar", f"{store['time_units']}, {store['calendar']}"],
                ["Grid", f"{store['latitudes']} latitudes by {store['longitudes']} longitudes"],
                *[[f"Unit declared for {name}", unit]
                  for name, unit in sorted(store["units_declared"].items())],
                ["Objects in the reference copy", explored["copy"]["objects"]],
                ["Bytes in the reference copy", explored["copy"]["bytes"]],
            ],
        },
    ]  # fmt: skip
    return run
