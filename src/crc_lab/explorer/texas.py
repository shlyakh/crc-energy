"""Texas boundary and the H3 cells that intersect it.

The boundary is the Census TIGER cartographic file ``cb_2024_us_state_500k``
(public domain). Cells are selected with ``crc_sdk.geometry.vector.polyfill_wkb``,
whose polygon mode keeps every cell that overlaps the polygon (decided
2026-11-10: intersecting, not centre-inside, so the borders are covered).
"""

from __future__ import annotations

import json
import os
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pyarrow as pa
import shapely
from crc_sdk.geometry.vector import polyfill_wkb

TIGER_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_500k.zip"
TIGER_FILE = "cb_2024_us_state_500k"
STATE = "TX"


@dataclass(frozen=True)
class Boundary:
    """One state's boundary as WKB, with its bounding box (lon_min, lat_min, lon_max, lat_max)."""

    name: str
    wkb: bytes
    bounds: tuple[float, float, float, float]
    source_url: str

    @property
    def geometry(self) -> shapely.Geometry:
        return shapely.from_wkb(self.wkb)


def fetch_tiger(cache_dir: Path) -> Path:
    """Download the TIGER state file once; return the zip path."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{TIGER_FILE}.zip"
    if not target.exists():
        fd, tmp = tempfile.mkstemp(dir=cache_dir, suffix=".part")
        os.close(fd)
        urllib.request.urlretrieve(TIGER_URL, tmp)
        os.replace(tmp, target)
    return target


def texas_boundary(cache_dir: Path) -> Boundary:
    """Read the Texas polygon from the TIGER zip (DuckDB spatial, no extra Python deps)."""
    zip_path = fetch_tiger(cache_dir)
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    row = con.execute(
        f"SELECT NAME, ST_AsWKB(geom) FROM ST_Read('/vsizip/{zip_path}/{TIGER_FILE}.shp') "
        "WHERE STUSPS = ?",
        [STATE],
    ).fetchone()
    if row is None:
        raise RuntimeError(f"{STATE} not found in {zip_path}")
    wkb = bytes(row[1])
    bounds = shapely.from_wkb(wkb).bounds
    return Boundary(
        name=row[0], wkb=wkb, bounds=tuple(float(b) for b in bounds), source_url=TIGER_URL
    )


def intersecting_cells(wkb: bytes, resolution: int) -> set[int]:
    """H3 cells (unsigned integers) at ``resolution`` that overlap the polygon."""
    cells = polyfill_wkb(pa.array([wkb], pa.binary()), resolution, flatten=True)
    return set(cells.to_pylist())


def write_geojson(boundary: Boundary, path: Path, tolerance: float = 0.01) -> None:
    """Write a simplified outline for the map (tolerance in degrees)."""
    simplified = shapely.simplify(boundary.geometry, tolerance)
    feature = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": boundary.name, "source": boundary.source_url},
                "geometry": json.loads(shapely.to_geojson(simplified)),
            }
        ],
    }
    write_json_atomic(path, feature)


def write_json_atomic(path: Path, payload: object, **dumps: object) -> None:
    """Write JSON through a temporary file, then ``os.replace`` (AGENTS.md rule)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
    with os.fdopen(fd, "w") as handle:
        json.dump(payload, handle, separators=(",", ":"), **dumps)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
