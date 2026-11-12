"""``python -m crc_lab.curves.build``: annual maxima, curves, cards, cities, sensitivity, site."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
from crc_sdk.types import SourceProvenance

from crc_lab.curves import annual_maxima as am_mod
from crc_lab.curves import fit, sensitivity
from lab_common.horizons import write_horizon_files
from lab_common.texas import intersecting_cells, texas_boundary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=Path("data/storm-events/events.parquet"))
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--out", type=Path, default=Path("data/curves"))
    parser.add_argument("--site", type=Path, default=Path("site/data/hazards"))
    parser.add_argument("--start", type=int, default=am_mod.FIRST_FULL_YEAR)
    parser.add_argument("--sensitivity", action="store_true")
    parser.add_argument(
        "--verify", action="store_true", help="compare shipped values with for_assets"
    )
    parser.add_argument("--note", type=Path, default=Path("docs/reports/3-curves-sensitivity.md"))
    args = parser.parse_args(argv)
    started = time.time()

    card = json.loads(args.events.with_suffix(".card.json").read_text())
    provenance = SourceProvenance(
        provider="NOAA NCEI",
        dataset="Storm Events Database (bulk CSV), Texas, cleaned by crc-lab",
        version=f"snapshot {card['retrieved_at'][:10]}",
        uri=card["source_url"],
        licence=card["licence"],
        attribution=card["attribution"],
        retrieved_at=card["retrieved_at"],
    )
    con = duckdb.connect()
    boundary = texas_boundary(args.cache)
    cells = intersecting_cells(boundary.wkb, 5)
    window = am_mod.Window(args.start, am_mod.last_complete_year(str(args.events), con))
    am = am_mod.annual_maxima(str(args.events), cells, window, con)
    am_summary = am_mod.summary(am)
    args.out.mkdir(parents=True, exist_ok=True)
    pq.write_table(am, args.out / "annual-maxima.parquet")
    print(
        f"annual maxima: {am.num_rows} cell-years, window {window.start}-{window.end}; {am_summary}"
    )

    variant = fit.Variant()
    for hazard in fit.HAZARDS:
        path = args.out / f"{hazard}.parquet"
        diagnostics = args.out / f"{hazard}.diagnostics.parquet"
        _, warns = fit.fit_hazard(
            am, hazard, window, variant, provenance, path, diagnostics=diagnostics
        )
        card_out = fit.data_card(hazard, window, variant, provenance, path, am_summary, warns)
        card_out["cities"] = fit.evaluate_points(path, sensitivity.CITIES)
        fit.write_json(args.out / f"{hazard}.card.json", card_out)
        print(f"{hazard}: {card_out['curve_kinds']}")
        write_horizon_files(
            path,
            hazard,
            {5: cells},
            args.site,
            horizons=(window.end,),
            pathway=fit.PATHWAY,
            release=f"crc-lab curves from NOAA Storm Events, {provenance.version}",
        )
        if args.verify:
            check = fit.verify_shipped(path, args.site / hazard / f"{window.end}.json")
            card_out["verification"] = check
            fit.write_json(args.out / f"{hazard}.card.json", card_out)
            status = "ok" if not check["mismatches"] else f"{len(check['mismatches'])} MISMATCHES"
            n, c = check["values_checked"], check["cells"]
            print(f"verify {hazard}: {n} values, {c} cells: {status}")
    if args.sensitivity:
        work = args.out / "sensitivity"
        work.mkdir(exist_ok=True)
        results = sensitivity.run(am, window.end, provenance, work)
        fit.write_json(work / "results.json", results)
        args.note.write_text(sensitivity.markdown(results))
        print(f"sensitivity: {len(results['variants'])} variants -> {args.note}")
    print(f"{time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
