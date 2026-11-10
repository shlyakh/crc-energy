# ruff: noqa: E501
"""Hail days per year per Texas H3 r5 cell from four sources, for side-by-side comparison.

- ``reports``: days with at least one storm report of hail 1 inch or more in the cell (1996 on).
- ``reports_corrected``: the same divided by the fitted reporting rate (report 5).
- ``mrms``: days whose radar hail size (MESH, 24-hour maximum) reaches 30 mm anywhere in the cell.
- ``signatures``: days with a NEXRAD hail signature of 1.25 inches or more in the cell (1995 on).

A day is a calendar day in UTC for reports and signatures and 12 to 12 UTC for MRMS. The sources
measure different things over different periods; the point is to see where they agree.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import duckdb
import h3
import numpy as np
import pyarrow.parquet as pq

from crc_lab.explorer.texas import intersecting_cells, texas_boundary, write_json_atomic
from crc_lab.radar import analysis

MRMS_MM = 30.0
SIGNATURE_IN = 1.25
RES = 5


def reports_by_cell(bias: Path) -> dict[int, dict[str, float]]:
    t = pq.read_table(bias).to_pylist()
    years = 30
    return {
        r["cell"]: {
            "reports": r["severe_hail_days"] / years,
            "reporting_rate": r["reporting_rate"],
            "reports_corrected": r["severe_hail_days"] / years / r["reporting_rate"],
        }
        for r in t
    }


def mrms_by_cell(cache: Path, cells: set[int]) -> tuple[dict[int, float], dict[str, Any]]:
    files = analysis.day_files(cache)
    grid = analysis.grid_of(files[0])
    lookup: dict[tuple[int, int], int] = {}
    counts: dict[int, int] = {}
    for path in files:
        with np.load(path) as z:
            keep = z["tenths"] >= MRMS_MM * 10
            rows, cols = z["rows"][keep], z["cols"][keep]
        today: set[int] = set()
        for r, c in zip(rows.tolist(), cols.tolist(), strict=True):
            key = (r, c)
            cell = lookup.get(key)
            if cell is None:
                cell = h3.str_to_int(
                    h3.latlng_to_cell(
                        grid["lat0"] + r * grid["dlat"], grid["lon0"] + c * grid["dlon"], RES
                    )
                )
                lookup[key] = cell
            today.add(cell)
        for cell in today:
            if cell in cells:
                counts[cell] = counts.get(cell, 0) + 1
    years = len(files) / 365.25
    return {c: n / years for c, n in counts.items()}, {
        "days": len(files),
        "years": years,
        "first": files[0].stem,
        "last": files[-1].stem,
    }


def signatures_by_cell(
    cache: Path, cells: set[int]
) -> tuple[dict[int, float], dict[str, Any], list[dict[str, Any]]]:
    con = duckdb.connect()
    files = sorted(cache.glob("nx3hail_*.parquet"))
    counts: dict[int, int] = {}
    per_year = []
    for path in files:
        year = int(path.stem.split("_")[1])
        rows = con.execute(
            f"SELECT DISTINCT CAST(ztime AS DATE) AS d, round(lon, 2), round(lat, 2) FROM read_parquet('{path}') WHERE maxsize_in >= {SIGNATURE_IN} AND maxsize_in < 20"
        ).fetchall()
        seen: set[tuple[dt.date, int]] = set()
        for d, lon, lat in rows:
            cell = h3.str_to_int(h3.latlng_to_cell(lat, lon, RES))
            if cell in cells:
                seen.add((d, cell))
        for _, cell in seen:
            counts[cell] = counts.get(cell, 0) + 1
        total = con.execute(
            f"SELECT count(*), count(*) FILTER (WHERE maxsize_in >= {SIGNATURE_IN} AND maxsize_in < 20), count(DISTINCT wsr_id) FROM read_parquet('{path}')"
        ).fetchone()
        per_year.append(
            {
                "year": year,
                "rows_kept": total[0],
                "rows_ge_threshold": total[1],
                "radars": total[2],
                "cell_days": len(seen),
            }
        )
    years = len(files)
    return (
        {c: n / years for c, n in counts.items()},
        {"years": years, "first": files[0].stem[-4:], "last": files[-1].stem[-4:]},
        per_year,
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--bias", type=Path, default=Path("data/assets/reporting_bias.parquet"))
    parser.add_argument("--site", type=Path, default=Path("site/data/hail_compare"))
    parser.add_argument("--out", type=Path, default=Path("data/assets/hail_compare.json"))
    args = parser.parse_args(argv)
    cells = intersecting_cells(texas_boundary(args.cache).wkb, RES)
    rep = reports_by_cell(args.bias)
    mrms, mrms_meta = mrms_by_cell(args.cache / "mrms", cells)
    sig, sig_meta, per_year = signatures_by_cell(args.cache / "swdi", cells)
    order = sorted(cells)
    payload = {
        "unit": "hail days per year",
        "h3_resolution": RES,
        "cells": [f"{c:x}" for c in order],
        "sources": {
            "reports": {
                "title": "Storm reports, hail 1 inch or more",
                "period": "1996–2025",
                "values": [round(rep.get(c, {}).get("reports", 0.0), 4) for c in order],
            },
            "reports_corrected": {
                "title": "Storm reports, corrected for reporting bias",
                "period": "1996–2025",
                "values": [round(rep.get(c, {}).get("reports_corrected", 0.0), 4) for c in order],
            },
            "mrms": {
                "title": f"Radar hail size (MRMS MESH) {MRMS_MM:g} mm or more",
                "period": f"{mrms_meta['first'][:4]}–{mrms_meta['last'][:4]}",
                "values": [round(mrms.get(c, 0.0), 4) for c in order],
            },
            "signatures": {
                "title": f"Radar hail signatures (NEXRAD) {SIGNATURE_IN} inches or more",
                "period": f"{sig_meta['first']}–{sig_meta['last']}",
                "values": [round(sig.get(c, 0.0), 4) for c in order],
            },
        },
        "reporting_rate": [
            round(rep.get(c, {}).get("reporting_rate", float("nan")), 4) for c in order
        ],
        "signatures_per_year": per_year,
        "notes": "Sources measure different things over different periods. Reports need a person; radar sees everywhere but over-calls; signatures come from single radars and their coverage and algorithm changed over time.",
    }
    write_json_atomic(args.site / "cells.json", payload)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({k: v for k, v in payload.items() if k != "cells"}, default=str))
    v = {k: np.array(s["values"]) for k, s in payload["sources"].items()}
    summary = {
        k: [round(float(x), 3) for x in np.quantile(a, [0.1, 0.5, 0.9])] for k, a in v.items()
    }
    corr = {
        f"{a}~{b}": round(float(np.corrcoef(v[a], v[b])[0, 1]), 3) for a in v for b in v if a < b
    }
    print(
        json.dumps(
            {"quantiles": summary, "correlation": corr, "mrms": mrms_meta, "signatures": sig_meta},
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
