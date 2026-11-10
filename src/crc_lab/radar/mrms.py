# ruff: noqa: E501
"""MRMS MESH daily maxima over Texas from NOAA's open archive (AWS ``noaa-mrms-pds``).

One file per day: the 24-hour maximum valid at 12 UTC, which covers the convective day from
12 UTC the day before. Each file is decoded with cfgrib (the ``radar`` extra), clipped to a
Texas box and stored sparsely (only cells at or above ``KEEP_MM``), so the whole archive from
October 2020 is a few tens of megabytes. MESH is a radar estimate of maximum hail size, built
to exceed most observed sizes; it is not an observation.
"""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

BUCKET = "https://noaa-mrms-pds.s3.amazonaws.com"
PRODUCT = "MESH_Max_1440min_00.50"
FIRST_DAY = dt.date(2020, 10, 14)
BOX = (-107.0, 25.5, -93.0, 37.0)  # lon_min, lat_min, lon_max, lat_max: Texas with a margin
KEEP_MM = 19.0  # 0.75 inch; smaller values are dropped
VALID_HOUR = "120000"


def url_for(day: dt.date) -> str:
    stamp = day.strftime("%Y%m%d")
    return f"{BUCKET}/CONUS/{PRODUCT}/{stamp}/MRMS_{PRODUCT}_{stamp}-{VALID_HOUR}.grib2.gz"


def decode(grib_gz: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(lat, lon, values) for the Texas box; lon in -180..180, lat descending as in the file."""
    import xarray as xr

    fd, tmp = tempfile.mkstemp(suffix=".grib2")
    os.close(fd)
    try:
        with gzip.open(grib_gz) as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst)
        ds = xr.open_dataset(tmp, engine="cfgrib", backend_kwargs={"indexpath": ""})
        lat = ds.latitude.values
        lon = np.where(ds.longitude.values > 180, ds.longitude.values - 360, ds.longitude.values)
        jj = np.where((lat >= BOX[1]) & (lat <= BOX[3]))[0]
        ii = np.where((lon >= BOX[0]) & (lon <= BOX[2]))[0]
        values = ds[list(ds.data_vars)[0]].values[jj[0] : jj[-1] + 1, ii[0] : ii[-1] + 1]
        ds.close()
        return lat[jj], lon[ii], values
    finally:
        os.unlink(tmp)


def sparse_day(values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Row, column and value (tenths of mm, uint16) of cells at or above ``KEEP_MM``."""
    rows, cols = np.where(np.nan_to_num(values, nan=0.0) >= KEEP_MM)
    return (
        rows.astype(np.uint16),
        cols.astype(np.uint16),
        np.round(values[rows, cols] * 10).astype(np.uint16),
    )


def fetch_day(day: dt.date, cache: Path) -> dict[str, object]:
    """Download, decode and store one day; return its manifest entry (status ok | missing | error)."""
    out = cache / "days" / f"{day:%Y}" / f"{day:%Y%m%d}.npz"
    if out.exists():
        return {"day": day.isoformat(), "status": "cached"}
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out.parent, suffix=".grib2.gz")
    os.close(fd)
    try:
        try:
            urllib.request.urlretrieve(url_for(day), tmp)
        except urllib.error.HTTPError as error:
            return {"day": day.isoformat(), "status": "missing", "http": error.code}
        digest = hashlib.sha256(Path(tmp).read_bytes()).hexdigest()
        lat, lon, values = decode(Path(tmp))
        rows, cols, tenths = sparse_day(values)
        part = out.with_suffix(".part.npz")
        np.savez_compressed(
            part,
            rows=rows,
            cols=cols,
            tenths=tenths,
            shape=np.array(values.shape),
            lat0=lat[0],
            lon0=lon[0],
            dlat=lat[1] - lat[0],
            dlon=lon[1] - lon[0],
        )
        os.replace(part, out)
        return {
            "day": day.isoformat(),
            "status": "ok",
            "sha256": digest,
            "cells": int(len(rows)),
            "max_mm": float(np.nanmax(values)) if values.size else 0.0,
        }
    except Exception as error:  # noqa: BLE001 - one bad file must not stop the archive pull
        return {"day": day.isoformat(), "status": "error", "error": str(error)[:200]}
    finally:
        Path(tmp).unlink(missing_ok=True)


def fetch_range(
    start: dt.date, end: dt.date, cache: Path, *, workers: int = 4
) -> dict[str, object]:
    """Fetch every day in the range (processes in parallel); append results to ``manifest.jsonl``."""
    from concurrent.futures import ProcessPoolExecutor

    cache.mkdir(parents=True, exist_ok=True)
    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    counts: dict[str, int] = {}
    with (
        ProcessPoolExecutor(max_workers=workers) as pool,
        (cache / "manifest.jsonl").open("a") as log,
    ):
        for entry in pool.map(fetch_day, days, [cache] * len(days), chunksize=8):
            counts[entry["status"]] = counts.get(entry["status"], 0) + 1
            if entry["status"] != "cached":
                log.write(json.dumps(entry) + "\n")
                log.flush()
    return {
        "days": len(days),
        "counts": counts,
        "product": PRODUCT,
        "source": BUCKET,
        "box": BOX,
        "keep_mm": KEEP_MM,
    }


def load_day(path: Path) -> dict[str, np.ndarray]:
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=FIRST_DAY.isoformat())
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--cache", type=Path, default=Path("data/cache/mrms"))
    parser.add_argument("--workers", type=int, default=4)
    a = parser.parse_args()
    print(
        json.dumps(
            fetch_range(
                dt.date.fromisoformat(a.start),
                dt.date.fromisoformat(a.end),
                a.cache,
                workers=a.workers,
            )
        )
    )
