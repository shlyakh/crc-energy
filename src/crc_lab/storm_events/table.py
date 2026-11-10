"""S4: one Parquet event table for Texas with a documented schema and a data card."""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from crc_lab import PINNED
from crc_lab.storm_events import geometry, parse
from crc_lab.storm_events.plan import CITATION, TERMS_URL, StormEventsPlan

STATE = "TEXAS"
STATE_FIPS = "48"
STATE_CODE = "TX"

KNOWN_BIASES = [
    "Reports follow people and roads: an empty cell may be unobserved, not calm.",
    "Coverage by type changed: tornado only 1950-54; tornado, thunderstorm wind and hail 1955-95; "
    "all event types from 1996.",
    "Hail size and wind speed are mostly estimates by the public and spotters (see `source` and "
    "`wind_measure`); sizes cluster on familiar objects (1.00, 1.75 inches).",
    "Before the mid-1990s most events carry county or zone locations, not points.",
    "Times are NCEI local standard time converted with the zone's standard offset; daylight "
    "saving is not applied by NCEI's files, so summer times may be one hour off true local time.",
    "Damage figures are NWS estimates in the dollars of the event year, parsed from K/M/B strings.",
    "NCEI re-creates yearly files in place; the snapshot manifest (SHA-256 per file) pins what "
    "this table was built from.",
]


def read_fatality_counts(paths: list[Path]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for path in paths:
        table = pacsv.read_csv(
            path, convert_options=pacsv.ConvertOptions(column_types={"EVENT_ID": pa.string()})
        )
        for value in table["EVENT_ID"].to_pylist():
            try:
                event = int(value)
            except (TypeError, ValueError):
                continue
            counts[event] = counts.get(event, 0) + 1
    return counts


def build_events(
    plan: StormEventsPlan, cache_dir: Path, *, progress: bool = False
) -> tuple[pa.Table, dict[str, Any]]:
    """Parse every cached yearly file for the state; attach cells and fatality counts."""
    paths = plan.paths()
    years = sorted({year for (_, year) in paths})
    boundaries = geometry.load_boundaries(cache_dir / "storm-events")
    locations = geometry.read_locations([paths[k] for k in sorted(paths) if k[0] == "locations"])
    fatalities = read_fatality_counts([paths[k] for k in sorted(paths) if k[0] == "fatalities"])
    parts = []
    for year in years:
        key = ("details", year)
        if key not in paths:
            continue
        table = parse.parse_details(paths[key], states=(STATE,))
        if progress:
            print(f"{year}: {table.num_rows} {STATE} events")
        parts.append(table)
    events = pa.concat_tables(parts)
    events = geometry.add_cells(events, locations, boundaries)
    counts = pa.array([fatalities.get(e, 0) for e in events["event_id"].to_pylist()], pa.int32())
    events = events.append_column("fatality_records", counts)
    events = events.sort_by([("begin_utc", "ascending"), ("event_id", "ascending")])
    card = data_card(events, plan, boundaries, years)
    return events, card


def data_card(
    events: pa.Table, plan: StormEventsPlan, boundaries: geometry.Boundaries, years: list[int]
) -> dict[str, Any]:
    manifest = plan.read_manifest()
    by_type = events.group_by("event_type").aggregate([("event_id", "count")]).to_pylist()
    by_kind = events.group_by("geometry_kind").aggregate([("event_id", "count")]).to_pylist()
    flags = {
        name: {
            r[name]: r["event_id_count"]
            for r in events.group_by(name).aggregate([("event_id", "count")]).to_pylist()
        }
        for name in ("time_flag", "damage_property_flag", "damage_crops_flag", "wind_measure")
    }
    begin = events["begin_utc"]
    return {
        "name": f"NOAA Storm Events, {STATE.title()}, cleaned and placed on H3 resolution-5 cells",
        "source": CITATION,
        "source_url": "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/",
        "terms_url": TERMS_URL,
        "licence": "U.S. government work; NOAA asks for attribution",
        "attribution": "NOAA National Centers for Environmental Information, Storm Events Database",
        "retrieved_at": manifest.get("retrieved_at"),
        "files": {
            k: {"name": v["name"], "sha256": v["sha256"], "bytes": v["bytes"]}
            for k, v in manifest.get("files", {}).items()
        },
        "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "versions": {name: version(name) for name in PINNED},
        "coverage": {
            "state": STATE,
            "years": [years[0], years[-1]] if years else None,
            "first_event_utc": str(pc.min(begin).as_py()) if events.num_rows else None,
            "latest_event_utc": str(pc.max(begin).as_py()) if events.num_rows else None,
            "events": events.num_rows,
        },
        "events_by_type": {r["event_type"]: r["event_id_count"] for r in by_type},
        "geometry_by_kind": {r["geometry_kind"]: r["event_id_count"] for r in by_kind},
        "flags": flags,
        "boundaries": {"counties": boundaries.county_source, "zones": boundaries.zone_source},
        "h3_resolution": geometry.RESOLUTION,
        "schema": {field.name: str(field.type) for field in events.schema},
        "column_notes": parse.COLUMN_DOCS
        | {
            "geometry_kind": "path | point | county | zone | none: what the cells were made from",
            "geometry_wkb": "the point or path used (WKB, WGS84); null for county and zone "
            "events, whose polygon is named by cz_type and cz_fips",
            "cells": "H3 r5 cells the geometry touches (every cell a path crosses)",
            "fatality_records": "rows in NCEI's fatalities file for this event",
        },
        "known_biases": KNOWN_BIASES,
    }


def write_events(events: pa.Table, card: dict[str, Any], output: Path) -> None:
    """Atomic Parquet + JSON data card beside it."""
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = dict(events.schema.metadata or {})
    metadata[b"crc_lab.storm_events.card"] = json.dumps(card).encode()
    table = events.replace_schema_metadata(metadata)
    fd, tmp = tempfile.mkstemp(dir=output.parent, suffix=".part")
    os.close(fd)
    pq.write_table(table, tmp, compression="zstd")
    os.chmod(tmp, 0o644)
    os.replace(tmp, output)
    card_path = output.with_suffix(".card.json")
    fd, tmp = tempfile.mkstemp(dir=output.parent, suffix=".part")
    with os.fdopen(fd, "w") as handle:
        json.dump(card, handle, indent=1)
    os.chmod(tmp, 0o644)
    os.replace(tmp, card_path)
