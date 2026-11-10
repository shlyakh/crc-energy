# ruff: noqa: E501
"""Radar step 1: hail days per cell and per plant, and measured swath areas, from the MRMS daily files.

A radar hail day at a place is a day whose 24-hour maximum MESH there is at or above a
threshold. For a plant, "there" is the disc of the plant's array area around its centre.
Swaths are connected areas at or above the threshold on one day.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path
from typing import Any

import numpy as np

THRESHOLDS_MM = (
    30.0,
    50.0,
)  # 30 mm: the severe-hail discriminator (Ortega 2018), chosen 2026-11-10; and 2 inches


def day_files(cache: Path) -> list[Path]:
    return sorted((cache / "days").glob("*/*.npz"))


def grid_of(path: Path) -> dict[str, Any]:
    with np.load(path) as z:
        return {
            "shape": tuple(int(v) for v in z["shape"]),
            "lat0": float(z["lat0"]),
            "lon0": float(z["lon0"]),
            "dlat": float(z["dlat"]),
            "dlon": float(z["dlon"]),
        }


def cell_area_km2(grid: dict[str, Any]) -> np.ndarray:
    """Area of the cells in each row (km²)."""
    lats = grid["lat0"] + grid["dlat"] * np.arange(grid["shape"][0])
    return abs(grid["dlat"]) * 110.57 * abs(grid["dlon"]) * 111.32 * np.cos(np.radians(lats))


def analyse(
    cache: Path, plants: list[dict[str, Any]], *, min_swath_cells: int = 5
) -> dict[str, Any]:
    """One pass over the days: per-cell hail-day counts, per-plant hail days, swath areas."""
    from scipy import ndimage

    files = day_files(cache)
    grid = grid_of(files[0])
    rows_n, cols_n = grid["shape"]
    counts = {t: np.zeros(grid["shape"], dtype=np.uint16) for t in THRESHOLDS_MM}
    row_area = cell_area_km2(grid)
    # plant footprints as index windows with a circular mask
    masks = []
    for p in plants:
        r = int(round((p["latitude"] - grid["lat0"]) / grid["dlat"]))
        c = int(round((p["longitude"] - grid["lon0"]) / grid["dlon"]))
        radius_km = math.sqrt(max(p["area_km2"], 0.0) / math.pi)
        half = max(1, int(math.ceil(radius_km / 1.0)))
        rr, cc = np.mgrid[-half : half + 1, -half : half + 1]
        dist = np.hypot(
            rr * abs(grid["dlat"]) * 110.57,
            cc * abs(grid["dlon"]) * 111.32 * math.cos(math.radians(p["latitude"])),
        )
        keep = dist <= max(radius_km, 0.6)  # at least the cell under the centre
        masks.append((r, c, rr[keep], cc[keep]))
    plant_days = {t: np.zeros(len(plants), dtype=np.int32) for t in THRESHOLDS_MM}
    plant_max = np.zeros(len(plants), dtype=np.float32)
    plant_max_day = [None] * len(plants)
    swaths: dict[float, list[float]] = {t: [] for t in THRESHOLDS_MM}
    dense = np.zeros(grid["shape"], dtype=np.float32)
    first = last = None
    for path in files:
        day = dt.datetime.strptime(path.stem, "%Y%m%d").date()
        first, last = first or day, day
        with np.load(path) as z:
            r, c, v = (
                z["rows"].astype(np.int64),
                z["cols"].astype(np.int64),
                z["tenths"].astype(np.float32) / 10.0,
            )
        if not len(r):
            continue
        dense.fill(0.0)
        dense[r, c] = v
        for t in THRESHOLDS_MM:
            hit = dense >= t
            counts[t] += hit
            labels, n = ndimage.label(hit)
            if n:
                areas = ndimage.sum(
                    np.broadcast_to(row_area[:, None], grid["shape"]),
                    labels,
                    index=np.arange(1, n + 1),
                )
                sizes = ndimage.sum(hit, labels, index=np.arange(1, n + 1))
                swaths[t].extend(
                    float(a) for a, s in zip(areas, sizes, strict=True) if s >= min_swath_cells
                )
        for i, (pr, pc_, rr, cc) in enumerate(masks):
            ri, ci = pr + rr, pc_ + cc
            ok = (ri >= 0) & (ri < rows_n) & (ci >= 0) & (ci < cols_n)
            m = float(dense[ri[ok], ci[ok]].max()) if ok.any() else 0.0
            if m > plant_max[i]:
                plant_max[i], plant_max_day[i] = m, day.isoformat()
            for t in THRESHOLDS_MM:
                if m >= t:
                    plant_days[t][i] += 1
    years = len(files) / 365.25
    return {
        "grid": grid,
        "days": len(files),
        "first_day": first.isoformat(),
        "last_day": last.isoformat(),
        "years": years,
        "counts": counts,
        "plant_days": plant_days,
        "plant_max_mm": plant_max,
        "plant_max_day": plant_max_day,
        "swath_areas_km2": swaths,
    }


def swath_summary(areas: list[float]) -> dict[str, float]:
    a = np.asarray(areas)
    if not len(a):
        return {"n": 0}
    return {
        "n": int(len(a)),
        "p25": float(np.quantile(a, 0.25)),
        "median": float(np.median(a)),
        "p75": float(np.quantile(a, 0.75)),
        "p90": float(np.quantile(a, 0.9)),
        "mean": float(a.mean()),
        "max": float(a.max()),
    }
