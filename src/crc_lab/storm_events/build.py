"""``python -m crc_lab.storm_events.build``: snapshot, event table, explorer layer, comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from crc_lab.storm_events import compare, explorer_layer, geometry, table
from crc_lab.storm_events.plan import StormEventsPlan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--out", type=Path, default=Path("data/storm-events"))
    parser.add_argument("--site", type=Path, default=Path("site/data/storm-events"))
    parser.add_argument("--mode", choices=["reuse", "offline", "refresh"], default="reuse")
    parser.add_argument("--years", nargs=2, type=int, default=None, metavar=("START", "END"))
    parser.add_argument("--compare", action="store_true", help="run the two-source comparison (S5)")
    parser.add_argument(
        "--report", type=Path, default=Path("docs/reports/2-storm-events-comparison.md")
    )
    args = parser.parse_args(argv)

    started = time.time()
    plan = StormEventsPlan(args.cache, mode=args.mode)
    if args.years:
        plan = plan.between(*args.years)
    manifest = plan.prefetch(progress=True)
    print(f"snapshot: {len(manifest['files'])} files")

    events, card = table.build_events(plan, args.cache, progress=False)
    output = args.out / "events.parquet"
    table.write_events(events, card, output)
    print(f"events: {events.num_rows} rows -> {output} ({output.stat().st_size / 1e6:.1f} MB)")
    print(f"geometry: {card['geometry_by_kind']}")

    index = explorer_layer.write_layer(events, args.site, card)
    print(
        f"explorer layer: {index['events']} points, {index['events_without_point']} without a point"
    )

    if args.compare:
        copy = args.cache / "storm-events" / "sourcecoop" / "events.parquet"
        if not copy.exists():
            print(f"copy missing: {copy}; download it first")
            return 1
        meta_path = copy.with_suffix(".meta.json")
        if meta_path.exists():
            copy_meta = json.loads(meta_path.read_text())
        else:
            digest = hashlib.sha256()
            with copy.open("rb") as handle:
                while chunk := handle.read(1 << 20):
                    digest.update(chunk)
            copy_meta = {
                "sha256": digest.hexdigest(),
                "bytes": copy.stat().st_size,
                "url": compare.COPY_URL,
            }
            headers = copy.with_name("headers.txt")
            if headers.exists():
                for line in headers.read_text().splitlines():
                    if line.lower().startswith("last-modified:"):
                        copy_meta["last_modified"] = line.split(":", 1)[1].strip()
            meta_path.write_text(json.dumps(copy_meta, indent=1))
        boundaries = geometry.load_boundaries(args.cache / "storm-events")
        results = compare.run(
            output,
            copy,
            boundaries.counties,
            boundaries.zones,
            Path("site/data/texas.geojson"),
            args.report,
            args.report.parent / "figures",
            copy_meta=copy_meta,
            ncei_card=card,
        )
        print(f"comparison: {results['presence']}")
        (args.out / "comparison.json").write_text(json.dumps(results, indent=1, default=str))
    print(f"{time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
