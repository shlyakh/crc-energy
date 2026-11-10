# ruff: noqa: E501  (SQL, SVG templates and report text read better on one line)
"""First attempt at a reporting-bias correction for hail reports (plan-hail-exposure.md, section 2).

Reports follow people and roads. The model separates a *true* hail-day rate, assumed constant
inside a coarse region, from a *reporting rate* that rises with population and road density:

    observed hail days in cell i  ~  Poisson(years x true_rate[region(i)] x reporting_rate_i)
    reporting_rate_i = floor + (1 - floor) x (1 - exp(-(b_pop x pop_i + b_road x road_i)))

``pop_i`` is people per km2 and ``road_i`` km of primary and secondary road per km2. The form is
Potvin et al. (2019, doi:10.1175/WAF-D-18-0137.1) turned to rise toward 1; their paper was not
re-read here and no tornado parameter is reused. The true rate per region has a closed-form
maximum-likelihood value given the reporting rates, so only (floor, b_pop, b_road) are searched.

Identifying assumption: inside one region (an H3 resolution-3 cell, about 12,000 km2) hail
climate is the same everywhere, so any difference between its cells that lines up with people
or roads is reporting. Nothing but that assumption separates the two.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy import optimize

TRACTS_URL = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_48_tract_500k.zip"
POP_URL = "https://www2.census.gov/geo/docs/reference/cenpop2020/tract/CenPop2020_Mean_TR48.txt"
ROADS_URL = "https://www2.census.gov/geo/tiger/TIGER2024/PRISECROADS/tl_2024_48_prisecroads.zip"
SOURCES = {"tracts": TRACTS_URL, "population": POP_URL, "roads": ROADS_URL}
LICENCE = "U.S. Census Bureau: public domain"
PROJECTION = "EPSG:3083"  # Texas Centric Albers Equal Area, metres
START = 1996
MODELS = ("none", "population", "roads", "both")


# ---------- pure functions (tested offline) ----------
def reporting_rate(
    pop: np.ndarray, road: np.ndarray, floor: float, b_pop: float, b_road: float
) -> np.ndarray:
    """A rate in [floor, 1] that rises with population and road density."""
    return floor + (1.0 - floor) * (
        1.0 - np.exp(-(b_pop * np.asarray(pop) + b_road * np.asarray(road)))
    )


def profile_true_rates(
    counts: np.ndarray, rho: np.ndarray, region: np.ndarray, years: float, n_regions: int
) -> np.ndarray:
    """Poisson maximum-likelihood true rate per region given the reporting rates."""
    num = np.bincount(region, weights=counts, minlength=n_regions)
    den = years * np.bincount(region, weights=rho, minlength=n_regions)
    return np.divide(num, den, out=np.zeros(n_regions), where=den > 0)


def poisson_loglik(counts: np.ndarray, mean: np.ndarray) -> float:
    """Poisson log-likelihood without the factorial term (constant across models)."""
    safe = np.maximum(mean, 1e-12)
    return float(np.sum(counts * np.log(safe) - safe))


def _unpack(theta: np.ndarray, model: str) -> tuple[float, float, float]:
    floor = 1.0 / (1.0 + math.exp(-min(max(theta[0], -50.0), 50.0)))
    theta = np.clip(theta, -50.0, 50.0)
    if model == "population":
        return floor, math.exp(theta[1]), 0.0
    if model == "roads":
        return floor, 0.0, math.exp(theta[1])
    return floor, math.exp(theta[1]), math.exp(theta[2])


@dataclass(frozen=True)
class Fit:
    model: str
    floor: float
    b_pop: float
    b_road: float
    loglik: float
    true_rates: np.ndarray


def fit(
    counts: np.ndarray,
    pop: np.ndarray,
    road: np.ndarray,
    region: np.ndarray,
    years: float,
    model: str = "both",
) -> Fit:
    """Maximum likelihood for one model; ``none`` means everyone reports (rate 1 everywhere)."""
    n_regions = int(region.max()) + 1
    if model == "none":
        rho = np.ones(len(counts))
        lam = profile_true_rates(counts, rho, region, years, n_regions)
        return Fit(model, 1.0, 0.0, 0.0, poisson_loglik(counts, years * lam[region] * rho), lam)

    def negative(theta: np.ndarray) -> float:
        floor, b_pop, b_road = _unpack(theta, model)
        rho = reporting_rate(pop, road, floor, b_pop, b_road)
        lam = profile_true_rates(counts, rho, region, years, n_regions)
        return -poisson_loglik(counts, years * lam[region] * rho)

    scale_pop = 1.0 / max(float(np.median(pop[pop > 0])) if np.any(pop > 0) else 1.0, 1e-9)
    scale_road = 1.0 / max(float(np.median(road[road > 0])) if np.any(road > 0) else 1.0, 1e-9)
    starts = []
    for f0 in (-2.0, 0.0):
        for mult in (0.1, 1.0, 5.0):
            if model == "population":
                starts.append([f0, math.log(mult * scale_pop)])
            elif model == "roads":
                starts.append([f0, math.log(mult * scale_road)])
            else:
                starts.append([f0, math.log(mult * scale_pop), math.log(mult * scale_road)])
    best = min(
        (
            optimize.minimize(
                negative,
                np.array(s),
                method="Nelder-Mead",
                options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 4000},
            )
            for s in starts
        ),
        key=lambda r: r.fun,
    )
    floor, b_pop, b_road = _unpack(best.x, model)
    rho = reporting_rate(pop, road, floor, b_pop, b_road)
    return Fit(
        model,
        floor,
        b_pop,
        b_road,
        -float(best.fun),
        profile_true_rates(counts, rho, region, years, n_regions),
    )


def area_weighted(
    values: np.ndarray,
    source_area: np.ndarray,
    overlap_area: np.ndarray,
    target: np.ndarray,
    n_targets: int,
) -> np.ndarray:
    """Spread each source's value over targets in proportion to overlap area / source area."""
    share = np.divide(
        overlap_area, source_area, out=np.zeros(len(overlap_area)), where=source_area > 0
    )
    return np.bincount(target, weights=values * share, minlength=n_targets)


def held_out(
    counts: np.ndarray,
    pop: np.ndarray,
    road: np.ndarray,
    region: np.ndarray,
    years: float,
    *,
    folds: int = 5,
    seed: int = 11,
) -> dict[str, float]:
    """Mean held-out Poisson log-likelihood per cell for each model (k-fold over cells)."""
    rng = np.random.default_rng(seed)
    fold = rng.integers(0, folds, len(counts))
    n_regions = int(region.max()) + 1
    totals = dict.fromkeys(MODELS, 0.0)
    for k in range(folds):
        train, test = fold != k, fold == k
        for model in MODELS:
            f = fit(counts[train], pop[train], road[train], region[train], years, model)
            rho_all = (
                np.ones(len(counts))
                if model == "none"
                else reporting_rate(pop, road, f.floor, f.b_pop, f.b_road)
            )
            lam = profile_true_rates(counts[train], rho_all[train], region[train], years, n_regions)
            # a region with no training cell falls back to the overall rate
            overall = counts[train].sum() / (years * rho_all[train].sum())
            lam = np.where(np.bincount(region[train], minlength=n_regions) > 0, lam, overall)
            totals[model] += poisson_loglik(counts[test], years * lam[region[test]] * rho_all[test])
    return {m: v / len(counts) for m, v in totals.items()}


def bootstrap(
    counts: np.ndarray,
    pop: np.ndarray,
    road: np.ndarray,
    region: np.ndarray,
    years: float,
    model: str,
    *,
    reps: int = 200,
    seed: int = 5,
) -> dict[str, Any]:
    """Cell bootstrap: resample cells with replacement, refit, keep parameters and per-cell rates."""
    rng = np.random.default_rng(seed)
    params, rhos = [], []
    for _ in range(reps):
        idx = rng.integers(0, len(counts), len(counts))
        f = fit(counts[idx], pop[idx], road[idx], region[idx], years, model)
        params.append((f.floor, f.b_pop, f.b_road))
        rhos.append(reporting_rate(pop, road, f.floor, f.b_pop, f.b_road))
    p, r = np.array(params), np.array(rhos)
    q = lambda a: [float(np.quantile(a, 0.05)), float(np.quantile(a, 0.95))]  # noqa: E731
    return {
        "reps": reps,
        "floor": q(p[:, 0]),
        "b_pop": q(p[:, 1]),
        "b_road": q(p[:, 2]),
        "rho_lo": np.quantile(r, 0.05, axis=0),
        "rho_hi": np.quantile(r, 0.95, axis=0),
    }


# ---------- data ----------
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(cache: Path) -> dict[str, dict[str, Any]]:
    """Download the three Census files once; return url, path, sha256 and retrieval time each."""
    directory = cache / "census"
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for key, url in SOURCES.items():
        target = directory / url.rsplit("/", 1)[1]
        if not target.exists():
            fd, tmp = tempfile.mkstemp(dir=directory, suffix=".part")
            os.close(fd)
            urllib.request.urlretrieve(url, tmp)
            os.replace(tmp, target)
            manifest.pop(key, None)
        if key not in manifest:
            manifest[key] = {
                "url": url,
                "file": target.name,
                "sha256": _sha256(target),
                "bytes": target.stat().st_size,
                "retrieved_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "licence": LICENCE,
            }
    manifest_path.write_text(json.dumps(manifest, indent=1))
    return manifest


def build_cells(events: Path, cache: Path, end: int) -> dict[str, np.ndarray]:
    """Per Texas r5 cell: hail days, population density, road density, region index."""
    import duckdb
    import h3
    import pyarrow as pa
    import shapely

    from crc_lab.explorer.texas import intersecting_cells, texas_boundary

    boundary = texas_boundary(cache)
    cells = sorted(intersecting_cells(boundary.wkb, 5))
    hexes = [h3.int_to_str(c) for c in cells]
    polygons = [shapely.Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(h)]) for h in hexes]
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    con.register(
        "cell_src",
        pa.table(
            {
                "cell": pa.array(cells, pa.uint64()),
                "i": pa.array(range(len(cells)), pa.int32()),
                "wkb": pa.array([shapely.to_wkb(p) for p in polygons], pa.binary()),
            }
        ),
    )
    con.execute(
        f"CREATE TABLE cells AS SELECT cell, i, ST_Transform(ST_GeomFromWKB(wkb), 'EPSG:4326', '{PROJECTION}', always_xy := true) AS geom FROM cell_src"
    )
    con.execute("CREATE INDEX cells_idx ON cells USING RTREE (geom)")
    area_km2 = np.array(
        [r[0] for r in con.execute("SELECT ST_Area(geom) / 1e6 FROM cells ORDER BY i").fetchall()]
    )

    # hail days: a local calendar day with at least one located report touching the cell
    days = con.execute(
        f"""WITH r AS (SELECT unnest(cells) AS cell, substr(begin_local, 1, 10) AS day, hail_size_mm
                       FROM read_parquet('{events}') WHERE event_type = 'Hail' AND year BETWEEN {START} AND {end}
                         AND geometry_kind IN ('point', 'path'))
            SELECT c.i, count(DISTINCT r.day), count(DISTINCT r.day) FILTER (WHERE r.hail_size_mm >= 25.4)
            FROM cells c LEFT JOIN r USING (cell) GROUP BY 1 ORDER BY 1"""
    ).fetchall()
    hail_days = np.array([d[1] for d in days], dtype=float)
    severe_days = np.array([d[2] for d in days], dtype=float)

    census = cache / "census"
    con.execute(
        f"CREATE TABLE pop AS SELECT STATEFP || COUNTYFP || TRACTCE AS geoid, POPULATION AS population FROM read_csv('{census / 'CenPop2020_Mean_TR48.txt'}', header = true, all_varchar = true)"
    )
    con.execute(f"""CREATE TABLE tracts AS SELECT GEOID AS geoid, ST_Transform(geom, 'EPSG:4269', '{PROJECTION}', always_xy := true) AS geom
                    FROM ST_Read('/vsizip/{census / "cb_2020_48_tract_500k.zip"}/cb_2020_48_tract_500k.shp')""")
    rows = con.execute(
        """SELECT c.i, CAST(p.population AS DOUBLE), ST_Area(t.geom), ST_Area(ST_Intersection(t.geom, c.geom))
           FROM tracts t JOIN pop p USING (geoid) JOIN cells c ON ST_Intersects(t.geom, c.geom)"""
    ).fetchall()
    arr = np.array(rows, dtype=float)
    people = area_weighted(arr[:, 1], arr[:, 2], arr[:, 3], arr[:, 0].astype(int), len(cells))
    matched = con.execute(
        "SELECT count(*), sum(CAST(p.population AS BIGINT)) FROM tracts t JOIN pop p USING (geoid)"
    ).fetchone()

    con.execute(f"""CREATE TABLE roads AS SELECT RTTYP, MTFCC, ST_Transform(geom, 'EPSG:4269', '{PROJECTION}', always_xy := true) AS geom
                    FROM ST_Read('/vsizip/{census / "tl_2024_48_prisecroads.zip"}/tl_2024_48_prisecroads.shp')""")
    road_rows = con.execute(
        "SELECT c.i, sum(ST_Length(ST_Intersection(r.geom, c.geom))) / 1000 FROM roads r JOIN cells c ON ST_Intersects(r.geom, c.geom) GROUP BY 1"
    ).fetchall()
    road_km = np.zeros(len(cells))
    for i, km in road_rows:
        road_km[i] = km or 0.0

    parents = [h3.cell_to_parent(h, 3) for h in hexes]
    names = sorted(set(parents))
    region = np.array([names.index(p) for p in parents])
    centres = np.array([h3.cell_to_latlng(h) for h in hexes])
    return {
        "cell": np.array(cells, dtype=np.uint64),
        "hex": np.array(hexes),
        "lat": centres[:, 0],
        "lon": centres[:, 1],
        "area_km2": area_km2,
        "hail_days": hail_days,
        "severe_days": severe_days,
        "population": people,
        "pop_density": people / area_km2,
        "road_km": road_km,
        "road_density": road_km / area_km2,
        "region": region,
        "region_names": np.array(names),
        "tracts_matched": np.array([matched[0]]),
        "population_matched": np.array([matched[1]]),
    }


def radar_hail_days(
    mrms_days: Path, cells: np.ndarray, first_year: int, last_year: int, threshold_mm: float = 29.0
) -> np.ndarray | None:
    """Per cell, days with any radar pixel (MRMS daily-maximum MESH) at or above the threshold.

    Reads the sparse daily files written by ``crc_lab.radar.mrms`` (rows, cols, tenths of mm on a
    regular lat/lon grid). Returns None when no files exist.
    """
    import h3

    files = sorted(
        f for y in range(first_year, last_year + 1) for f in (mrms_days / str(y)).glob("*.npz")
    )
    if not files:
        return None
    index = {int(c): i for i, c in enumerate(cells)}
    lookup: dict[tuple[int, int], int] = {}
    counts = np.zeros(len(cells))
    for f in files:
        d = np.load(f)
        keep = d["tenths"] >= threshold_mm * 10
        hit: set[int] = set()
        lat0, lon0, dlat, dlon = (
            float(d["lat0"]),
            float(d["lon0"]),
            float(d["dlat"]),
            float(d["dlon"]),
        )
        for r, c in zip(d["rows"][keep].tolist(), d["cols"][keep].tolist(), strict=True):
            i = lookup.get((r, c))
            if i is None:
                i = index.get(
                    h3.str_to_int(h3.latlng_to_cell(lat0 + r * dlat, lon0 + c * dlon, 5)), -1
                )
                lookup[(r, c)] = i
            if i >= 0:
                hit.add(i)
        counts[list(hit)] += 1
    return counts


# ---------- outputs ----------
def hex_map_svg(
    hexes: np.ndarray,
    values: np.ndarray,
    title: str,
    top: float,
    outline: list[list[tuple[float, float]]],
) -> str:
    """Cells coloured by a rate, one hue light to dark, shared ``top`` so two maps compare."""
    import h3

    lon0, lon1, lat0, lat1 = -106.9, -93.3, 25.6, 36.7
    w, h = 720, 600
    sx, sy = w / (lon1 - lon0), h / (lat1 - lat0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h + 34}" font-family="Helvetica, Arial, sans-serif">',
        f'<rect width="{w}" height="{h + 34}" fill="#faf9f6"/>',
        f'<text x="12" y="20" font-size="14" font-weight="600" fill="#2a2a28">{title}</text>',
        f'<text x="{w - 12}" y="20" font-size="11" text-anchor="end" fill="#7a7976">darker = more; scale 0 to {top:.1f} hail days per year</text>',
        '<g transform="translate(0,30)">',
    ]
    for hx, v in zip(hexes, values, strict=True):
        t = min(1.0, max(0.0, v / top)) ** 0.5
        pts = " ".join(
            f"{(lon - lon0) * sx:.1f},{h - (lat - lat0) * sy:.1f}"
            for lat, lon in h3.cell_to_boundary(str(hx))
        )
        parts.append(
            f'<polygon points="{pts}" fill="oklch({95 - 60 * t:.0f}% {0.03 + 0.13 * t:.2f} 330)"/>'
        )
    for ring in outline:
        d = " ".join(f"{(lon - lon0) * sx:.1f},{h - (lat - lat0) * sy:.1f}" for lon, lat in ring)
        parts.append(f'<polyline points="{d}" fill="none" stroke="#2a2a28" stroke-width="1.2"/>')
    parts.append("</g></svg>")
    return "\n".join(parts)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def run(
    events: Path,
    cache: Path,
    out: Path,
    report: Path,
    plants: Path | None,
    *,
    reps: int = 200,
    mrms: Path | None = None,
) -> dict[str, Any]:
    import duckdb
    import h3
    import pyarrow as pa
    import pyarrow.parquet as pq
    import shapely

    from crc_lab.curves.annual_maxima import last_complete_year
    from crc_lab.curves.sensitivity import CITIES
    from crc_lab.explorer.texas import texas_boundary

    manifest = fetch(cache)
    end = last_complete_year(str(events), duckdb.connect())
    years = float(end - START + 1)
    c = build_cells(events, cache, end)
    y, pop, road, region = c["hail_days"], c["pop_density"], c["road_density"], c["region"]

    fits = {m: fit(y, pop, road, region, years, m) for m in MODELS}
    cv = held_out(y, pop, road, region, years)
    best = max((m for m in MODELS if m != "none"), key=lambda m: cv[m])
    chosen = fits[best]
    boot = bootstrap(y, pop, road, region, years, best, reps=reps)
    rho = reporting_rate(pop, road, chosen.floor, chosen.b_pop, chosen.b_road)
    observed = y / years
    corrected = observed / rho
    smooth = chosen.true_rates[region]
    mean = years * smooth * rho
    dispersion = float(
        np.sum((y - mean) ** 2 / np.maximum(mean, 1e-9)) / (len(y) - len(c["region_names"]) - 3)
    )

    # the same model on days with hail of 1 inch or more
    severe = fit(c["severe_days"], pop, road, region, years, best)

    table = pa.table(
        {
            "cell": pa.array(c["cell"], pa.uint64()),
            "hail_days": y,
            "severe_hail_days": c["severe_days"],
            "pop_density_km2": pop,
            "road_km_per_km2": road,
            "region": c["region_names"][region],
            "observed_hail_days_per_year": observed,
            "reporting_rate": rho,
            "reporting_rate_p05": boot["rho_lo"],
            "reporting_rate_p95": boot["rho_hi"],
            "corrected_hail_days_per_year": corrected,
            "corrected_p05": observed / boot["rho_hi"],
            "corrected_p95": observed / boot["rho_lo"],
            "region_true_rate_per_year": smooth,
        }
    )
    out.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out / "reporting_bias.parquet", compression="zstd")

    index = {int(cell): i for i, cell in enumerate(c["cell"])}

    def at(lon: float, lat: float) -> dict[str, float] | None:
        i = index.get(h3.str_to_int(h3.latlng_to_cell(lat, lon, 5)))
        if i is None:
            return None
        return {
            "pop_density": float(pop[i]),
            "road_density": float(road[i]),
            "observed": float(observed[i]),
            "reporting_rate": float(rho[i]),
            "rate_lo": float(boot["rho_lo"][i]),
            "rate_hi": float(boot["rho_hi"][i]),
            "corrected": float(corrected[i]),
            "factor": float(1 / rho[i]),
            "region_true_rate": float(smooth[i]),
        }

    cities = {city["name"]: at(city["lon"], city["lat"]) for city in CITIES}
    plant_rows: list[dict[str, Any]] = []
    if plants is not None and plants.exists():
        for r in pq.read_table(
            plants, columns=["name", "county", "longitude", "latitude", "capacity_ac_mw"]
        ).to_pylist():
            v = at(r["longitude"], r["latitude"])
            if v:
                plant_rows.append(r | v)
    factors = np.array([p["factor"] for p in plant_rows]) if plant_rows else np.array([])

    # checks against the published pattern (regions by latitude and longitude boxes)
    def box_mean(values: np.ndarray, lon0: float, lon1: float, lat0: float, lat1: float) -> float:
        m = (c["lon"] >= lon0) & (c["lon"] <= lon1) & (c["lat"] >= lat0) & (c["lat"] <= lat1)
        return float(values[m].mean())

    boxes = {
        "Panhandle": (-103.1, -100.0, 34.0, 36.6),
        "North Texas": (-98.5, -95.5, 32.0, 34.0),
        "Coast": (-98.0, -94.0, 26.0, 29.6),
        "Far west": (-106.7, -103.5, 29.5, 32.0),
    }
    pattern = {
        k: {
            "observed": box_mean(observed, *b),
            "corrected": box_mean(corrected, *b),
            "region_true_rate": box_mean(smooth, *b),
            "pop_density": box_mean(pop, *b),
        }
        for k, b in boxes.items()
    }
    sparse = pop < np.quantile(pop, 0.25)
    dense = pop > np.quantile(pop, 0.9)

    radar: dict[str, Any] | None = None
    if mrms is not None and mrms.exists():
        y0, y1 = (
            2021,
            end,
        )  # complete calendar years in the MRMS archive (it starts 14 October 2020)
        counts_radar = radar_hail_days(mrms, c["cell"], y0, y1)
        if counts_radar is not None:
            con = duckdb.connect()
            con.register(
                "cell_list",
                pa.table(
                    {
                        "cell": pa.array(c["cell"], pa.uint64()),
                        "i": pa.array(range(len(y)), pa.int32()),
                    }
                ),
            )
            rows = con.execute(
                f"""WITH r AS (SELECT unnest(cells) AS cell, substr(begin_local, 1, 10) AS day FROM read_parquet('{events}')
                               WHERE event_type = 'Hail' AND year BETWEEN {y0} AND {y1} AND geometry_kind IN ('point', 'path') AND hail_size_mm >= 25.4)
                    SELECT l.i, count(DISTINCT r.day) FROM cell_list l LEFT JOIN r USING (cell) GROUP BY 1 ORDER BY 1"""
            ).fetchall()
            n = float(y1 - y0 + 1)
            rep = np.array([r[1] for r in rows], dtype=float) / n
            rad = counts_radar / n
            rho_s = reporting_rate(pop, road, severe.floor, severe.b_pop, severe.b_road)
            groups = {
                "densest tenth of cells": dense,
                "middle": ~dense & ~sparse,
                "sparsest quarter of cells": sparse,
                "all cells": np.ones(len(y), bool),
            }
            radar = {
                "years": [y0, y1],
                "threshold_mm": 29.0,
                "groups": {
                    k: {
                        "cells": int(m.sum()),
                        "radar_days_per_year": float(rad[m].mean()),
                        "reported_days_per_year": float(rep[m].mean()),
                        "corrected_days_per_year": float((rep[m] / rho_s[m]).mean()),
                        "radar_over_reported": float(rad[m].sum() / max(rep[m].sum(), 1e-9)),
                        "radar_over_corrected": float(
                            rad[m].sum() / max((rep[m] / rho_s[m]).sum(), 1e-9)
                        ),
                        "fitted_factor_median": float(np.median(1 / rho_s[m])),
                    }
                    for k, m in groups.items()
                },
                "correlation_radar_reported": float(np.corrcoef(rad, rep)[0, 1]),
                "correlation_radar_corrected": float(np.corrcoef(rad, rep / rho_s)[0, 1]),
                "pattern_radar": {k: box_mean(rad, *b) for k, b in boxes.items()},
            }

    figures = report.parent / "figures"
    boundary = texas_boundary(cache).geometry
    geoms = boundary.geoms if boundary.geom_type == "MultiPolygon" else [boundary]
    outline = [list(shapely.simplify(g, 0.02).exterior.coords) for g in geoms]
    top = float(np.quantile(corrected, 0.98))
    _write(
        figures / "reporting-bias-observed.svg",
        hex_map_svg(
            c["hex"],
            observed,
            "Hail days per year from reports, as observed, 1996–" + str(end),
            top,
            outline,
        ),
    )
    _write(
        figures / "reporting-bias-corrected.svg",
        hex_map_svg(
            c["hex"],
            corrected,
            "Hail days per year, divided by the fitted reporting rate",
            top,
            outline,
        ),
    )
    _write(
        figures / "reporting-bias-rate.svg",
        hex_map_svg(c["hex"], rho * top, "Fitted reporting rate (full scale = 1.0)", top, outline),
    )

    results = {
        "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "window": [START, end],
        "cells": len(y),
        "regions": len(c["region_names"]),
        "sources": manifest,
        "tracts_matched": int(c["tracts_matched"][0]),
        "population_matched": int(c["population_matched"][0]),
        "population_in_cells": float(c["population"].sum()),
        "road_km_in_cells": float(c["road_km"].sum()),
        "hail_days_total": float(y.sum()),
        "cells_with_no_hail_day": int((y == 0).sum()),
        "fits": {
            m: {"floor": f.floor, "b_pop": f.b_pop, "b_road": f.b_road, "loglik": f.loglik}
            for m, f in fits.items()
        },
        "held_out_loglik_per_cell": cv,
        "chosen": best,
        "bootstrap": {k: boot[k] for k in ("reps", "floor", "b_pop", "b_road")},
        "dispersion": dispersion,
        "severe_fit": {"floor": severe.floor, "b_pop": severe.b_pop, "b_road": severe.b_road},
        "reporting_rate": {
            "min": float(rho.min()),
            "p10": float(np.quantile(rho, 0.1)),
            "median": float(np.median(rho)),
            "p90": float(np.quantile(rho, 0.9)),
            "max": float(rho.max()),
        },
        "correction_factor": {
            "sparsest_quarter_median": float(np.median(1 / rho[sparse])),
            "densest_tenth_median": float(np.median(1 / rho[dense])),
            "all_median": float(np.median(1 / rho)),
        },
        "covariates": {
            "pop_density_quantiles": [float(np.quantile(pop, q)) for q in (0.1, 0.5, 0.9, 0.99)],
            "road_density_quantiles": [float(np.quantile(road, q)) for q in (0.1, 0.5, 0.9, 0.99)],
            "correlation_pop_road": float(np.corrcoef(np.log1p(pop), road)[0, 1]),
        },
        "pattern": pattern,
        "radar_check": radar,
        "cities": cities,
        "plants": {
            "n": len(plant_rows),
            "factor_p10_median_p90": [float(np.quantile(factors, q)) for q in (0.1, 0.5, 0.9)]
            if len(factors)
            else None,
            "fort_bend": [p for p in plant_rows if p["county"] == "Fort Bend"],
        },
    }
    (out / "reporting_bias.json").write_text(json.dumps(results, indent=1, default=str))
    _write(report, markdown(json.loads(json.dumps(results, default=str))))
    return results


def markdown(r: dict[str, Any]) -> str:
    """The report, every number taken from ``results``."""
    f, cv, b = r["fits"], r["held_out_loglik_per_cell"], r["bootstrap"]
    rr, cf = r["reporting_rate"], r["correction_factor"]
    src = r["sources"]
    lines = [
        "# Report 5: a first reporting-bias correction for hail reports",
        "",
        f"Built {r['built_at'][:10]} on branch `reporting-bias`; a first attempt at section 2 of `docs/plan-hail-exposure.md`, for review. Every number below is written by `just reporting-bias` (`python -m crc_lab.assets.reporting_bias`).",
        "",
        "## What was built",
        "",
        f"- **Grid.** The {r['cells']:,} Texas H3 resolution-5 cells already used for the hazard layers and curves (about 253 km² each), so results line up with the rest of the project. A 10 km grid would be finer than most rural reporting.",
        f"- **Counts.** Hail days per cell, {r['window'][0]}–{r['window'][1]}: a local calendar day with at least one located hail report touching the cell. {r['hail_days_total']:,.0f} cell-days in all; {r['cells_with_no_hail_day']:,} cells have none. The same for hail of 1 inch or more.",
        f"- **Population.** 2020 Census tract populations ({r['tracts_matched']:,} tracts, {r['population_matched']:,} people) spread over cells by area of overlap; {r['population_in_cells']:,.0f} people land in the cells.",
        f"- **Roads.** Census TIGER/Line 2024 primary and secondary roads, length inside each cell: {r['road_km_in_cells']:,.0f} km in all.",
        "",
        "| Input | File | SHA-256 | Retrieved |",
        "| --- | --- | --- | --- |",
    ]
    for key in ("tracts", "population", "roads"):
        lines.append(
            f"| {key} | [{src[key]['file']}]({src[key]['url']}) | `{src[key]['sha256'][:16]}…` | {src[key]['retrieved_at'][:10]} |"
        )
    lines += [
        "",
        "All three are U.S. Census Bureau files, public domain. The Census API for the decennial count needs a key, so tract populations come from the Bureau's centers-of-population file instead. No raster population product is used (rasterio does not load on this machine).",
        "",
        "## Model",
        "",
        "    hail days in cell i ~ Poisson(years × true_rate[region of i] × reporting_rate_i)",
        "    reporting_rate_i = floor + (1 − floor) × (1 − exp(−(b_pop × people per km² + b_road × road km per km²)))",
        "",
        f"The form follows Potvin et al. (2019) for tornadoes, written so the rate rises toward 1; their paper was not re-read here and none of their parameters is used. The true rate is one value per H3 resolution-3 region ({r['regions']} regions, about 12,000 km² each) and has a closed-form best value given the reporting rates, so only the floor and the two slopes are searched.",
        "",
        "**Identifying assumption.** Inside one region, hail climate is the same in every cell. Any difference between cells of a region that lines up with people or roads is therefore counted as reporting. Nothing else separates true rate from reporting rate, and the densest cells are assumed to report every hail day.",
        "",
        "## Estimates",
        "",
        "| Model | floor | b_pop (per person/km²) | b_road (per km/km²) | Held-out log-likelihood per cell |",
        "| --- | --- | --- | --- | --- |",
    ]
    for m in MODELS:
        lines.append(
            f"| {m}{' (chosen)' if m == r['chosen'] else ''} | {f[m]['floor']:.3f} | {f[m]['b_pop']:.4f} | {f[m]['b_road']:.3f} | {cv[m]:.3f} |"
        )
    lines += [
        "",
        f"Five-fold held-out likelihood prefers **{r['chosen']}**. Bootstrap over cells ({b['reps']} resamples), 5th to 95th percentile: floor {b['floor'][0]:.3f}–{b['floor'][1]:.3f}, b_pop {b['b_pop'][0]:.4f}–{b['b_pop'][1]:.4f}, b_road {b['b_road'][0]:.2f}–{b['b_road'][1]:.2f}.",
        "",
        f"Counts are more variable than Poisson: the dispersion statistic is {r['dispersion']:.1f}, so these intervals are too narrow. For hail of 1 inch or more the same model gives floor {r['severe_fit']['floor']:.3f}, b_pop {r['severe_fit']['b_pop']:.4f}, b_road {r['severe_fit']['b_road']:.3f}.",
        "",
        f"Fitted reporting rate across cells: minimum {rr['min']:.3f}, 10th percentile {rr['p10']:.3f}, median {rr['median']:.3f}, 90th percentile {rr['p90']:.3f}, maximum {rr['max']:.3f}. Correction factor (1 ÷ reporting rate): median {cf['all_median']:.1f} over all cells, {cf['densest_tenth_median']:.2f} in the densest tenth, **{cf['sparsest_quarter_median']:.1f} in the sparsest quarter**.",
        "",
        "## Before and after",
        "",
        "Hail days per year in the cell holding each city centre:",
        "",
        "| City | People per km² | Road km per km² | Observed | Reporting rate | Corrected | Factor | Region true rate |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, v in r["cities"].items():
        if v:
            lines.append(
                f"| {name} | {v['pop_density']:,.0f} | {v['road_density']:.2f} | {v['observed']:.2f} | {v['reporting_rate']:.2f} | {v['corrected']:.2f} | {v['factor']:.2f} | {v['region_true_rate']:.2f} |"
            )
    pl = r["plants"]
    if pl["factor_p10_median_p90"]:
        q = pl["factor_p10_median_p90"]
        lines += [
            "",
            f"Solar plants ({pl['n']} from the current plant list): correction factor at the plant's cell, 10th percentile {q[0]:.1f}, **median {q[1]:.1f}**, 90th percentile {q[2]:.1f}.",
            "",
            "Fort Bend County plants:",
            "",
            "| Plant | People per km² | Road km per km² | Observed days/yr | Reporting rate (5–95%) | Corrected days/yr | Factor | Region true rate |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for p in pl["fort_bend"]:
            lines.append(
                f"| {p['name']} | {p['pop_density']:,.1f} | {p['road_density']:.3f} | {p['observed']:.2f} | {p['reporting_rate']:.3f} ({p['rate_lo']:.3f}–{p['rate_hi']:.3f}) | {p['corrected']:.2f} | {p['factor']:.1f} | {p['region_true_rate']:.2f} |"
            )
    pat = r["pattern"]
    lines += [
        "",
        "For a single cell the corrected value is noisy (a small count divided by a small rate); the region true rate is the steadier number.",
        "",
        "## Checks",
        "",
        "**Against the published pattern** (SPC: most hail over the Panhandle and north Texas, least on the coast and far west). Mean hail days per year per cell:",
        "",
        "| Area | People per km² | Observed | Corrected | Region true rate |",
        "| --- | --- | --- | --- | --- |",
    ]
    for k, v in pat.items():
        lines.append(
            f"| {k} | {v['pop_density']:.0f} | {v['observed']:.2f} | {v['corrected']:.2f} | {v['region_true_rate']:.2f} |"
        )
    lines += [
        "",
        f"As observed: Panhandle {pat['Panhandle']['observed']:.2f}, north Texas {pat['North Texas']['observed']:.2f}. After correction: Panhandle {pat['Panhandle']['corrected']:.2f}, north Texas {pat['North Texas']['corrected']:.2f}; coast {pat['Coast']['corrected']:.2f} and far west {pat['Far west']['corrected']:.2f} stay lowest.",
        "",
    ]
    rc = r.get("radar_check")
    if rc:
        lines += [
            f"**Against radar** (MRMS daily-maximum hail size, {rc['years'][0]}–{rc['years'][1]}; a radar hail day is any pixel in the cell at {rc['threshold_mm']:.0f} mm or more; reports are days with hail of 1 inch or more in the same years; the correction uses the 1-inch fit). Mean days per year per cell:",
            "",
            "| Cells | Count | Radar | Reported | Corrected | Radar ÷ reported | Radar ÷ corrected | Fitted factor, median |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for k, g in rc["groups"].items():
            lines.append(
                f"| {k} | {g['cells']:,} | {g['radar_days_per_year']:.2f} | {g['reported_days_per_year']:.2f} | {g['corrected_days_per_year']:.2f} | {g['radar_over_reported']:.1f} | {g['radar_over_corrected']:.2f} | {g['fitted_factor_median']:.1f} |"
            )
        lines += [
            "",
            f"Correlation across cells with radar: reported {rc['correlation_radar_reported']:.2f}, corrected {rc['correlation_radar_corrected']:.2f}. Radar by area: "
            + ", ".join(f"{k} {v:.2f}" for k, v in rc["pattern_radar"].items())
            + ".",
            "",
            "Read with care: a radar pixel at 29 mm is not a confirmed 1-inch stone on the ground (radar over-calls), and the radar day is a 24-hour window ending at a fixed hour, not the local calendar day.",
            "",
        ]
    else:
        lines += ["**Against radar:** not run; no MRMS files were present.", ""]
    lines += [
        "**Against Wendt and Jirak (2021)**, who found radar severe-hail hours 2 to 4 times Storm Data in the populated plains, more where few people live: the radar table above is this project's own ratio. Their figure is on an 80 km grid, where one report anywhere confirms the box; these cells are about 16 km across, so larger factors are expected and the two are not directly comparable. Nothing was tuned toward either number.",
        "",
        "## Maps",
        "",
        "![Observed](figures/reporting-bias-observed.svg)",
        "",
        "![Corrected](figures/reporting-bias-corrected.svg)",
        "",
        "![Reporting rate](figures/reporting-bias-rate.svg)",
        "",
        "## Limits",
        "",
        "- True rate and reporting rate are separated only by the assumption that hail climate is flat inside a region. Real gradients inside a region are read as reporting.",
        "- The densest cells are assumed to report every hail day. If they miss some, every corrected rate is too low by the same factor.",
        "- The floor is the reporting rate of a cell with no people and no primary road. It carries the largest corrections.",
        "- Poisson intervals are too narrow given the overdispersion; a negative binomial fit is the next step.",
        "- No era term: reporting practice changed over the window and population is a 2020 snapshot.",
        "- Reports from neighbouring states are not used here.",
        "- This corrects hail-day frequency, not reported size.",
        "",
        "## Questions for Yuri",
        "",
        "1. Use the per-cell corrected rate, or the smoother region true rate, when this feeds the plant exposure?",
        "2. Should the factor in empty cells be capped until radar calibrates it?",
        "3. Add an era term and a negative binomial likelihood first, or go straight to the joint model with radar?",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=Path("data/storm-events/events.parquet"))
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--out", type=Path, default=Path("data/assets"))
    parser.add_argument("--plants", type=Path, default=Path("data/assets/solar_tx.parquet"))
    parser.add_argument("--report", type=Path, default=Path("docs/reports/5-reporting-bias.md"))
    parser.add_argument("--reps", type=int, default=200)
    parser.add_argument(
        "--mrms",
        type=Path,
        default=Path("data/cache/mrms/days"),
        help="sparse daily MRMS files, if present",
    )
    args = parser.parse_args(argv)
    results = run(
        args.events, args.cache, args.out, args.report, args.plants, reps=args.reps, mrms=args.mrms
    )
    keep = (
        "cells",
        "regions",
        "fits",
        "held_out_loglik_per_cell",
        "chosen",
        "bootstrap",
        "dispersion",
        "reporting_rate",
        "correction_factor",
        "pattern",
    )
    print(json.dumps({k: results[k] for k in keep}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
