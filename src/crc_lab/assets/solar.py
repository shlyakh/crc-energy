"""A1: Texas solar plants from the USGS / Berkeley Lab solar database (USPVDB) as a CRC asset table.

CRC defines only the shape of an asset table (an id and a location; other columns pass
through), so this is a loader, not a CRC source. The download is cached with its SHA-256.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import duckdb
import pyarrow as pa

URL = "https://energy.usgs.gov/uspvdb/assets/data/uspvdbGeoJSON.zip"
CITATION = (
    "Fujita, K.S., et al., United States Large-Scale Solar Photovoltaic Database (USPVDB), "
    "U.S. Geological Survey and Lawrence Berkeley National Laboratory data release"
)
LICENCE = "U.S. government work (public domain); attribution requested"
STATE = "TX"

COLUMNS = {
    "case_id": "case_id",
    "eia_id": "eia_id",
    "p_name": "name",
    "p_county": "county",
    "xlong": "longitude",
    "ylat": "latitude",
    "p_cap_ac": "capacity_ac_mw",
    "p_cap_dc": "capacity_dc_mw",
    "p_year": "year",
    "p_axis": "axis",
    "p_tech_sec": "module_tech",
    "p_tilt": "tilt_deg",
    "p_azimuth": "azimuth_deg",
    "p_battery": "battery",
    "p_area": "area_m2",
    "p_type": "site_type",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(cache_dir: Path, *, refresh: bool = False) -> dict[str, Any]:
    """Download the GeoJSON zip once; return its manifest (url, sha256, release file name)."""
    directory = cache_dir / "uspvdb"
    directory.mkdir(parents=True, exist_ok=True)
    target, manifest_path = directory / "uspvdbGeoJSON.zip", directory / "manifest.json"
    if target.exists() and manifest_path.exists() and not refresh:
        manifest = json.loads(manifest_path.read_text())
        if manifest["sha256"] != _sha256(target):
            raise RuntimeError("USPVDB cache checksum mismatch; refresh it explicitly")
        return manifest
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".part")
    request = Request(URL, headers={"User-Agent": "crc-lab (+https://github.com/shlyakh/crc-lab)"})
    with os.fdopen(fd, "wb") as handle, urlopen(request, timeout=300) as response:
        while chunk := response.read(1 << 20):
            handle.write(chunk)
        last_modified = response.headers.get("Last-Modified")
    os.replace(tmp, target)
    with zipfile.ZipFile(target) as archive:
        names = [n for n in archive.namelist() if n.endswith(".geojson")]
    manifest = {
        "url": URL,
        "sha256": _sha256(target),
        "bytes": target.stat().st_size,
        "last_modified": last_modified,
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "release_file": names[0] if names else None,
        "citation": CITATION,
        "licence": LICENCE,
    }
    manifest_path.write_text(json.dumps(manifest, indent=1))
    return manifest


def load(cache_dir: Path, manifest: dict[str, Any], *, state: str = STATE) -> pa.Table:
    """One row per plant: ``asset_id``, location, capacity, year, mounting, boundary (WKB)."""
    path = f"/vsizip/{cache_dir / 'uspvdb' / 'uspvdbGeoJSON.zip'}/{manifest['release_file']}"
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    select = ", ".join(f"{src} AS {dst}" for src, dst in COLUMNS.items())
    return con.execute(
        f"""SELECT 'uspvdb-' || case_id AS asset_id, {select}, ST_AsWKB(geom) AS geometry_wkb
            FROM ST_Read('{path}') WHERE p_state = ? ORDER BY case_id""",
        [state],
    ).to_arrow_table()
