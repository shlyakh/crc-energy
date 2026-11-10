"""S6: the event table as a compact binary layer for the explorer, with times (explorer v2).

One 32-byte record per event, sorted by begin time: lon, lat (float32; NaN for county/zone
events, which have no point but belong on the timeline), year (uint16), type code (uint8),
magnitude (float32; hail inches or wind knots, NaN otherwise), event_id (uint32),
damage_property_usd (float32, NaN when not given), begin and end (uint32 minutes since
1950-01-01T00:00Z; 0 when the time could not be resolved). ``index.json`` names the type
codes and the record layout.

``python -m crc_lab.storm_events.explorer_layer`` rebuilds the layer from the event table
without touching the NCEI snapshot.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

RECORD = struct.Struct("<ffHBxfIfII")  # 32 bytes, little-endian, one pad byte after the type code
EPOCH = datetime(1950, 1, 1, tzinfo=UTC)
FIELDS = [
    {"name": "lon", "type": "float32", "offset": 0},
    {"name": "lat", "type": "float32", "offset": 4},
    {"name": "year", "type": "uint16", "offset": 8},
    {"name": "type", "type": "uint8", "offset": 10},
    {"name": "magnitude", "type": "float32", "offset": 12},
    {"name": "event_id", "type": "uint32", "offset": 16},
    {"name": "damage_usd", "type": "float32", "offset": 20},
    {"name": "begin_min", "type": "uint32", "offset": 24},
    {"name": "end_min", "type": "uint32", "offset": 28},
]


def minutes_since_epoch(when: datetime | None) -> int:
    """UTC datetime -> whole minutes since 1950-01-01T00:00Z; 0 for unknown or earlier."""
    if when is None:
        return 0
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0, int((when - EPOCH).total_seconds() // 60))


def first_point(wkb: bytes | None) -> tuple[float, float]:
    if wkb is None:
        return float("nan"), float("nan")
    import shapely

    geom = shapely.from_wkb(wkb)
    point = shapely.get_point(geom, 0) if geom.geom_type == "LineString" else geom
    return point.x, point.y


def pack_events(rows: list[dict[str, Any]], code: dict[str, int]) -> bytes:
    """Rows (already sorted by begin time) to packed records."""
    nan = float("nan")
    buf = bytearray()
    for r in rows:
        located = r["geometry_kind"] in ("point", "path")
        lon, lat = first_point(r["geometry_wkb"]) if located else (nan, nan)
        begin = minutes_since_epoch(r["begin_utc"])
        end = max(begin, minutes_since_epoch(r["end_utc"])) if begin else 0
        buf += RECORD.pack(
            lon,
            lat,
            r["year"],
            code[r["event_type"]],
            r["magnitude"] if r["magnitude"] is not None else nan,
            r["event_id"],
            r["damage_property_usd"] if r["damage_property_usd"] is not None else nan,
            begin,
            end,
        )
    return bytes(buf)


def write_layer(events: pa.Table, out_dir: Path, card: dict[str, Any]) -> dict[str, Any]:
    events = events.sort_by([("begin_utc", "ascending"), ("event_id", "ascending")])
    types = sorted(set(events["event_type"].to_pylist()))
    code = {t: i for i, t in enumerate(types)}
    columns = [
        "event_id",
        "year",
        "event_type",
        "magnitude",
        "damage_property_usd",
        "geometry_kind",
        "geometry_wkb",
        "begin_utc",
        "end_utc",
    ]
    rows = events.select(columns).to_pylist()
    rows.sort(key=lambda r: (minutes_since_epoch(r["begin_utc"]), r["event_id"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_bytes(out_dir / "events.bin", pack_events(rows, code))
    located = events.filter(pc.is_in(events["geometry_kind"], pa.array(["point", "path"])))
    by_type = located.group_by("event_type").aggregate([("event_id", "count")]).to_pylist()
    all_by_type = events.group_by("event_type").aggregate([("event_id", "count")]).to_pylist()
    index = {
        "record_bytes": RECORD.size,
        "fields": FIELDS,
        "time_epoch": "1950-01-01T00:00:00Z",
        "time_unit": "minutes",
        "sorted_by": "begin_min",
        "types": types,
        "counts": {r["event_type"]: r["event_id_count"] for r in by_type},
        "counts_all": {r["event_type"]: r["event_id_count"] for r in all_by_type},
        "records": len(rows),
        "events": located.num_rows,
        "events_without_point": events.num_rows - located.num_rows,
        "events_with_duration": sum(
            1 for r in rows if r["begin_utc"] and r["end_utc"] and r["end_utc"] > r["begin_utc"]
        ),
        "years": [int(pc.min(events["year"]).as_py()), int(pc.max(events["year"]).as_py())],
        "magnitude_units": {"Hail": "inches", "Thunderstorm Wind": "knots"},
        "source": card["source"],
        "licence": card["licence"],
        "attribution": card["attribution"],
        "retrieved_at": card["retrieved_at"],
        "built_at": card["built_at"],
        "known_biases": card["known_biases"],
    }
    fd, tmp = tempfile.mkstemp(dir=out_dir, suffix=".part")
    with os.fdopen(fd, "w") as handle:
        json.dump(index, handle, separators=(",", ":"))
    os.chmod(tmp, 0o644)
    os.replace(tmp, out_dir / "index.json")
    return index


def _write_bytes(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    import pyarrow.parquet as pq

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=Path("data/storm-events/events.parquet"))
    parser.add_argument("--site", type=Path, default=Path("site/data/storm-events"))
    args = parser.parse_args(argv)
    card = json.loads(args.events.with_suffix(".card.json").read_text())
    index = write_layer(pq.read_table(args.events), args.site, card)
    size = (args.site / "events.bin").stat().st_size
    print(
        f"{index['records']} records ({index['events']} located, "
        f"{index['events_with_duration']} with a duration), {size / 1e6:.1f} MB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
