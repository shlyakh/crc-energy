# ruff: noqa: E501
"""NEXRAD Level-III hail signatures from NCEI's Severe Weather Data Inventory (``nx3hail``), 1995 on.

One row per storm cell per radar volume scan: time (UTC), position, radar, probability of hail
and of severe hail, and the algorithm's maximum expected size in inches. These are points from a
single-radar algorithm, not a grid: the same storm is seen by several radars and many scans.
The yearly national files are 100-200 MB; only the Texas box at or above ``KEEP_IN`` is kept.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import tempfile
import urllib.request
from pathlib import Path

ROOT = "https://www.ncei.noaa.gov/pub/data/swdi/database-csv/v2"
BOX = (-107.0, 25.5, -93.0, 37.0)
KEEP_IN = 0.75  # inches; smaller signatures are dropped
FIRST_YEAR = 1995


def fetch_year(year: int, cache: Path) -> dict[str, object]:
    """Download one national yearly file, keep the Texas box, write Parquet; return a manifest entry."""
    import duckdb

    out = cache / f"nx3hail_{year}.parquet"
    if out.exists():
        return {"year": year, "status": "cached"}
    cache.mkdir(parents=True, exist_ok=True)
    url = f"{ROOT}/hail-{year}.csv.gz"
    fd, tmp = tempfile.mkstemp(dir=cache, suffix=".csv.gz")
    os.close(fd)
    try:
        urllib.request.urlretrieve(url, tmp)
        digest = hashlib.sha256()
        with open(tmp, "rb") as handle:
            while chunk := handle.read(1 << 20):
                digest.update(chunk)
        size = os.path.getsize(tmp)
        con = duckdb.connect()
        part = out.with_suffix(".part")
        con.execute(
            f"""COPY (SELECT strptime(ztime, '%Y%m%d%H%M%S') AS ztime, lon, lat, wsr_id, sevprob, prob, maxsize_in
                      FROM read_csv('{tmp}', header=false, skip=3, columns={{'ztime': 'VARCHAR', 'lon': 'DOUBLE', 'lat': 'DOUBLE', 'wsr_id': 'VARCHAR', 'cell_id': 'VARCHAR', 'range': 'VARCHAR', 'azimuth': 'VARCHAR', 'sevprob': 'INTEGER', 'prob': 'INTEGER', 'maxsize_in': 'DOUBLE'}}, ignore_errors=true)
                      WHERE lon BETWEEN {BOX[0]} AND {BOX[2]} AND lat BETWEEN {BOX[1]} AND {BOX[3]} AND maxsize_in >= {KEEP_IN})
                TO '{part}' (FORMAT PARQUET, COMPRESSION ZSTD)"""
        )
        rows = con.execute(f"SELECT count(*) FROM read_parquet('{part}')").fetchone()[0]
        os.replace(part, out)
        return {
            "year": year,
            "status": "ok",
            "url": url,
            "sha256": digest.hexdigest(),
            "bytes": size,
            "rows_kept": rows,
            "retrieved_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        }
    except Exception as error:  # noqa: BLE001
        return {"year": year, "status": "error", "error": str(error)[:300]}
    finally:
        Path(tmp).unlink(missing_ok=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, default=FIRST_YEAR)
    parser.add_argument("--end", type=int, default=2025)
    parser.add_argument("--cache", type=Path, default=Path("data/cache/swdi"))
    a = parser.parse_args()
    a.cache.mkdir(parents=True, exist_ok=True)
    with (a.cache / "manifest.jsonl").open("a") as log:
        for y in range(a.start, a.end + 1):
            entry = fetch_year(y, a.cache)
            print(json.dumps(entry), flush=True)
            if entry["status"] != "cached":
                log.write(json.dumps(entry) + "\n")
                log.flush()
