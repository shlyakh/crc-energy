"""``python -m crc_lab.explorer.build``: rebuild every explorer data file (G5; ``just data``)."""

from __future__ import annotations

import argparse
import datetime as dt
import time
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from crc_sdk.workflows import HazardDataset

from crc_lab import PINNED
from crc_lab.explorer.catalog import write_catalog
from crc_lab.explorer.hazards import (
    HAZARDS,
    HORIZONS,
    RETURN_PERIODS,
    build_hazard,
    verify_against_for_assets,
)
from crc_lab.explorer.texas import (
    intersecting_cells,
    texas_boundary,
    write_geojson,
    write_json_atomic,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("site/data"))
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--hazards", nargs="+", default=list(HAZARDS))
    parser.add_argument("--horizons", nargs="+", type=int, default=list(HORIZONS))
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument(
        "--refresh", action="store_true", help="re-download materialized Parquet files"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="compare shipped values with for_assets at sampled cells",
    )
    parser.add_argument("--sample", type=int, default=5)
    args = parser.parse_args(argv)

    started = time.time()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    plan = HazardDataset.crc_open()
    catalog = plan.catalog()
    write_catalog(catalog, out / "catalog.json")
    print(f"catalog: {len(catalog.hazards)} hazards, release {catalog.release}")

    boundary = texas_boundary(args.cache)
    write_geojson(boundary, out / "texas.geojson")
    resolutions = sorted({catalog.hazards[h].h3_resolution for h in args.hazards})
    cells = {r: intersecting_cells(boundary.wkb, r) for r in resolutions}
    for r, c in cells.items():
        print(f"texas: {len(c)} cells intersect at r{r}")

    area_plan = plan.for_area(boundary.bounds)
    builds = []
    for hazard in args.hazards:
        build = build_hazard(
            area_plan,
            hazard,
            cells,
            out / "hazards",
            args.cache / "crc-open",
            horizons=tuple(args.horizons),
            workers=args.workers,
            refresh=args.refresh,
        )
        builds.append(build)
        print(
            f"{hazard}: r{build.h3_resolution}, rows/horizon {build.rows_per_horizon}, "
            f"kinds {build.kinds}, {build.seconds}s"
        )

    checks = []
    if args.verify:
        for hazard in args.hazards:
            check = verify_against_for_assets(
                area_plan,
                hazard,
                out / "hazards",
                sample=args.sample,
                horizons=tuple(args.horizons),
            )
            checks.append(check)
            status = "ok" if not check["mismatches"] else f"{len(check['mismatches'])} MISMATCHES"
            print(
                f"verify {hazard}: {check['values_checked']} values "
                f"at {len(check['cells'])} cells: {status}"
            )

    manifest = {
        "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "versions": {name: version(name) for name in PINNED},
        "release": catalog.release,
        "licence": catalog.licence,
        "attribution": catalog.attribution,
        "pathway": plan.pathway,
        "horizons": args.horizons,
        "return_periods": list(RETURN_PERIODS),
        "texas": {
            "boundary": boundary.source_url,
            "bounds": boundary.bounds,
            "rule": "cells intersecting the state polygon",
            "cells": {str(r): len(c) for r, c in cells.items()},
        },
        "hazards": [asdict(b) for b in builds],
        "verification": checks,
        "seconds": round(time.time() - started, 1),
    }
    write_json_atomic(out / "manifest.json", manifest, indent=1)
    print(f"manifest written; {manifest['seconds']}s total")
    failed = [c["hazard"] for c in checks if c["mismatches"]]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
