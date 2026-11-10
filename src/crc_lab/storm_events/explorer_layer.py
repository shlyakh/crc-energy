"""S6: the event table as a compact binary point layer for the explorer.

One record per event with a point or path (its first point): lon, lat (float32), year (uint16),
type code (uint8), magnitude (float32; hail inches or wind knots, NaN otherwise), event_id
(uint32), damage_property_usd (float32, NaN when unparsed). ``index.json`` names the type codes
and the record layout. 163,000 events are about 3.5 MB, which deck.gl draws directly; PMTiles
are not needed at this size.
"""

from __future__ import annotations

import json
import os
import struct
import tempfile
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

RECORD = struct.Struct("<ffHBxfIf")  # 24 bytes, little-endian, one pad byte after the type code
FIELDS = [
    {"name": "lon", "type": "float32", "offset": 0},
    {"name": "lat", "type": "float32", "offset": 4},
    {"name": "year", "type": "uint16", "offset": 8},
    {"name": "type", "type": "uint8", "offset": 10},
    {"name": "magnitude", "type": "float32", "offset": 12},
    {"name": "event_id", "type": "uint32", "offset": 16},
    {"name": "damage_usd", "type": "float32", "offset": 20},
]


def write_layer(events: pa.Table, out_dir: Path, card: dict[str, Any]) -> dict[str, Any]:
    located = events.filter(pc.is_in(events["geometry_kind"], pa.array(["point", "path"])))
    types = sorted(set(located["event_type"].to_pylist()))
    code = {t: i for i, t in enumerate(types)}
    import shapely

    buf = bytearray()
    rows = located.select(
        ["event_id", "year", "event_type", "magnitude", "damage_property_usd", "geometry_wkb"]
    ).to_pylist()
    nan = float("nan")
    for r in rows:
        first = (
            shapely.get_point(shapely.from_wkb(r["geometry_wkb"]), 0)
            if shapely.from_wkb(r["geometry_wkb"]).geom_type == "LineString"
            else shapely.from_wkb(r["geometry_wkb"])
        )
        buf += RECORD.pack(
            first.x,
            first.y,
            r["year"],
            code[r["event_type"]],
            r["magnitude"] if r["magnitude"] is not None else nan,
            r["event_id"],
            r["damage_property_usd"] if r["damage_property_usd"] is not None else nan,
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_bytes(out_dir / "events.bin", bytes(buf))
    by_type = located.group_by("event_type").aggregate([("event_id", "count")]).to_pylist()
    index = {
        "record_bytes": RECORD.size,
        "fields": FIELDS,
        "types": types,
        "counts": {r["event_type"]: r["event_id_count"] for r in by_type},
        "events": len(rows),
        "events_without_point": events.num_rows - len(rows),
        "years": [int(pc.min(located["year"]).as_py()), int(pc.max(located["year"]).as_py())],
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
