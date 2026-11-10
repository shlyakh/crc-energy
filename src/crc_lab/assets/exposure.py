# ruff: noqa: E501
"""H1-H3: hail at an asset by local report density.

Around each asset a circle grows until it holds ``n_target`` located hail reports; a minimum
radius keeps a site near a town from inheriting the town's report density, and a maximum
radius flags sites with too few reports. Inside the circle the reports give the local size
distribution, and the count over the circle's area and the years gives a report rate per km²
per year (a nearest-neighbour density estimate).

A report is a point. Turning a rate of reports per km² into the chance that hail reached the
asset needs an area per report (``footprint_km2``): a placeholder with no source, stated in
every output and varied in the sensitivity note.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import duckdb
import numpy as np

EARTH_KM = 6371.0088
THRESHOLDS_MM = (25.4, 38.1, 50.8, 76.2)  # 1, 1.5, 2 and 3 inches


@dataclass(frozen=True)
class Rule:
    n_target: int = 100
    min_radius_km: float = 10.0
    max_radius_km: float = 75.0
    footprint_km2: float = 25.0  # placeholder [P]: area hit per report; no source

    @property
    def label(self) -> str:
        return f"N{self.n_target}-r{self.min_radius_km:g}-{self.max_radius_km:g}-A{self.footprint_km2:g}"


@dataclass(frozen=True)
class Reports:
    lon: np.ndarray
    lat: np.ndarray
    size_mm: np.ndarray
    start: int
    end: int

    @property
    def years(self) -> int:
        return self.end - self.start + 1


def load_reports(events: str, start: int, end: int) -> Reports:
    """Located hail reports (first point of a path) with a size, inside the window."""
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    rows = con.execute(
        f"""WITH e AS (SELECT hail_size_mm, ST_GeomFromWKB(geometry_wkb) AS g FROM read_parquet('{events}')
                       WHERE event_type = 'Hail' AND year BETWEEN {start} AND {end}
                         AND geometry_wkb IS NOT NULL AND hail_size_mm IS NOT NULL)
            SELECT CASE WHEN ST_GeometryType(g) = 'LINESTRING' THEN ST_X(ST_StartPoint(g)) ELSE ST_X(g) END,
                   CASE WHEN ST_GeometryType(g) = 'LINESTRING' THEN ST_Y(ST_StartPoint(g)) ELSE ST_Y(g) END,
                   hail_size_mm FROM e"""
    ).fetchall()
    data = np.asarray(rows, dtype=np.float64).reshape(-1, 3)
    return Reports(data[:, 0], data[:, 1], data[:, 2], start, end)


def distances_km(lon: float, lat: float, reports: Reports) -> np.ndarray:
    """Great-circle distance from one point to every report."""
    p1, p2 = math.radians(lat), np.radians(reports.lat)
    dlat, dlon = p2 - p1, np.radians(reports.lon - lon)
    a = np.sin(dlat / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


def at_point(
    lon: float, lat: float, reports: Reports, rule: Rule | None = None
) -> dict[str, object]:
    """The local hail description at one point under ``rule``."""
    rule = rule or Rule()
    d = distances_km(lon, lat, reports)
    order = np.argsort(d)
    reach = float(d[order[rule.n_target - 1]]) if len(d) >= rule.n_target else math.inf
    radius = min(max(reach, rule.min_radius_km), rule.max_radius_km)
    inside = d <= radius
    n = int(inside.sum())
    area = math.pi * radius**2
    sizes = reports.size_mm[inside]
    rate = n / (area * reports.years)
    out: dict[str, object] = {
        "rule": rule.label,
        "radius_km": round(radius, 2),
        "radius_to_n_km": None if math.isinf(reach) else round(reach, 2),
        "reports_in_radius": n,
        "flag": "ok" if reach <= rule.max_radius_km else "too_few_reports",
        "window": [reports.start, reports.end],
        "report_rate_per_100km2_year": round(rate * 100, 4),
        "size_median_mm": round(float(np.median(sizes)), 1) if n else None,
        "size_p90_mm": round(float(np.quantile(sizes, 0.9)), 1) if n else None,
        "size_max_mm": round(float(sizes.max()), 1) if n else None,
        "footprint_km2_placeholder": rule.footprint_km2,
    }
    for threshold in THRESHOLDS_MM:
        rate_t = float((sizes >= threshold).sum()) / (area * reports.years)
        key = f"{threshold / 25.4:g}in"
        out[f"rate_ge_{key}_per_100km2_year"] = round(rate_t * 100, 4)
        # Poisson: chance of at least one report-footprint of this size covering the point in a year
        out[f"annual_prob_ge_{key}"] = round(1 - math.exp(-rate_t * rule.footprint_km2), 5)
    return out


def rule_dict(rule: Rule) -> dict[str, object]:
    return asdict(rule) | {"label": rule.label, "footprint_is_placeholder": True}
