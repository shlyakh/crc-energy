"""S3: where each event is, and which H3 resolution-5 cells it touches.

Priority: the ``locations`` file points (a path when there are several), else ``BEGIN``/``END``
coordinates from ``details`` (a path when they differ), else the county (``cz_type`` C) or NWS
public forecast zone (``Z``) polygon, else nothing (marine zones, unmatched codes).
``geometry_kind`` records which. A path covers every cell it crosses
(``crc_sdk.geometry.vector.polyfill_wkb`` handles LineStrings); a polygon covers every cell that
intersects it.
"""

from __future__ import annotations

import os
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import shapely
from crc_sdk.geometry.vector import polyfill_wkb

COUNTY_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_county_500k.zip"
COUNTY_FILE = "cb_2024_us_county_500k"
ZONE_URL = "https://www.weather.gov/source/gis/Shapefiles/WSOM/z_16ap26.zip"
ZONE_FILE = "z_16ap26"
RESOLUTION = 5

KINDS = ("path", "point", "county", "zone", "none")


def fetch(url: str, target: Path) -> Path:
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".part")
        os.close(fd)
        urllib.request.urlretrieve(url, tmp)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    return target


@dataclass(frozen=True)
class Boundaries:
    """County and forecast-zone polygons for one state, keyed the way NCEI keys events."""

    counties: dict[int, bytes]  # cz_fips (county FIPS within the state) -> WKB
    zones: dict[int, bytes]  # cz_fips (zone number) -> WKB
    county_source: str
    zone_source: str


def load_boundaries(cache_dir: Path, *, state_fips: str = "48", state: str = "TX") -> Boundaries:
    county_zip = fetch(COUNTY_URL, cache_dir / "boundaries" / f"{COUNTY_FILE}.zip")
    zone_zip = fetch(ZONE_URL, cache_dir / "boundaries" / f"{ZONE_FILE}.zip")
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    counties = {
        int(fips): bytes(wkb)
        for fips, wkb in con.execute(
            f"SELECT COUNTYFP, ST_AsWKB(geom) "
            f"FROM ST_Read('/vsizip/{county_zip}/{COUNTY_FILE}.shp') WHERE STATEFP = ?",
            [state_fips],
        ).fetchall()
    }
    zones: dict[int, bytes] = {}
    for zone, wkb in con.execute(
        f"SELECT ZONE, ST_AsWKB(geom) FROM ST_Read('/vsizip/{zone_zip}/{ZONE_FILE}.shp') "
        "WHERE STATE = ?",
        [state],
    ).fetchall():
        key = int(zone)
        # a zone can be split into several polygons: union them
        zones[key] = shapely.to_wkb(
            shapely.union(shapely.from_wkb(zones[key]), shapely.from_wkb(bytes(wkb)))
            if key in zones
            else shapely.from_wkb(bytes(wkb))
        )
    return Boundaries(counties, zones, COUNTY_URL, ZONE_URL)


_LOCATION_COLUMNS = ("EVENT_ID", "LOCATION_INDEX", "LATITUDE", "LONGITUDE")
_EVENT_COLUMNS = ["event_id", "begin_lat", "begin_lon", "end_lat", "end_lon", "cz_type", "cz_fips"]


def read_locations(paths: list[Path]) -> dict[int, list[tuple[float, float]]]:
    """event_id -> ordered (lon, lat) points from the NCEI ``locations`` files."""
    points: dict[int, list[tuple[int, float, float]]] = {}
    for path in paths:
        table = pacsv.read_csv(
            path,
            convert_options=pacsv.ConvertOptions(
                column_types={
                    "EVENT_ID": pa.string(),
                    "LOCATION_INDEX": pa.string(),
                    "LATITUDE": pa.string(),
                    "LONGITUDE": pa.string(),
                },
                strings_can_be_null=True,
            ),
        )
        for row in table.select(
            ["EVENT_ID", "LOCATION_INDEX", "LATITUDE", "LONGITUDE"]
        ).to_pylist():
            try:
                event = int(row["EVENT_ID"])
                index = int(row["LOCATION_INDEX"])
                lat, lon = float(row["LATITUDE"]), float(row["LONGITUDE"])
            except (TypeError, ValueError):
                continue
            points.setdefault(event, []).append((index, lon, lat))
    return {e: [(lon, lat) for _, lon, lat in sorted(v)] for e, v in points.items()}


def event_geometry(
    row: dict[str, object], locations: dict[int, list[tuple[float, float]]], boundaries: Boundaries
) -> tuple[str, bytes | None]:
    """(geometry_kind, WKB) for one parsed event row."""
    pts = locations.get(int(row["event_id"])) if row["event_id"] is not None else None
    if not pts and row["begin_lat"] is not None and row["begin_lon"] is not None:
        pts = [(row["begin_lon"], row["begin_lat"])]
        if row["end_lat"] is not None and row["end_lon"] is not None:
            pts.append((row["end_lon"], row["end_lat"]))
    if pts:
        distinct = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
        if len(distinct) >= 2:
            return "path", shapely.to_wkb(shapely.LineString(distinct))
        return "point", shapely.to_wkb(shapely.Point(distinct[0]))
    fips = row["cz_fips"]
    if row["cz_type"] == "C" and fips in boundaries.counties:
        return "county", boundaries.counties[fips]
    if row["cz_type"] == "Z" and fips in boundaries.zones:
        return "zone", boundaries.zones[fips]
    return "none", None


def add_cells(
    events: pa.Table, locations: dict[int, list[tuple[float, float]]], boundaries: Boundaries
) -> pa.Table:
    """Append ``geometry_kind``, ``geometry_wkb`` and ``cells`` (list<uint64>, r5) to the table."""
    kinds, wkbs = [], []
    for row in events.select(
        ["event_id", "begin_lat", "begin_lon", "end_lat", "end_lon", "cz_type", "cz_fips"]
    ).to_pylist():
        kind, wkb = event_geometry(row, locations, boundaries)
        kinds.append(kind)
        wkbs.append(wkb)
    cells = polyfill_wkb(pa.array(wkbs, pa.binary()), RESOLUTION)
    # County and zone polygons are not repeated per event: cz_type/cz_fips name them.
    stored = [w if k in ("point", "path") else None for k, w in zip(kinds, wkbs, strict=True)]
    return (
        events.append_column("geometry_kind", pa.array(kinds, pa.string()))
        .append_column("geometry_wkb", pa.array(stored, pa.binary()))
        .append_column("cells", cells)
    )


def cell_count_summary(table: pa.Table) -> dict[str, object]:
    kinds = table.group_by("geometry_kind").aggregate([("event_id", "count")]).to_pylist()
    lengths = pc.list_value_length(table["cells"])
    return {
        "by_kind": {r["geometry_kind"]: r["event_id_count"] for r in kinds},
        "cells_per_event_max": pc.max(lengths).as_py() if table.num_rows else 0,
        "events_without_cells": pc.sum(pc.equal(pc.fill_null(lengths, 0), 0)).as_py()
        if table.num_rows
        else 0,
    }
