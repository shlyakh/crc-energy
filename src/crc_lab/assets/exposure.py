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
from pathlib import Path

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


def load_reports(events: str, start: int, end: int, extra: str | Path | None = None) -> Reports:
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
    if extra is not None and Path(extra).exists():
        rows += con.execute(
            f"SELECT lon, lat, hail_size_mm FROM read_parquet('{extra}') WHERE year BETWEEN {start} AND {end}"
        ).fetchall()
    data = np.asarray(rows, dtype=np.float64).reshape(-1, 3)
    return Reports(data[:, 0], data[:, 1], data[:, 2], start, end)


NEIGHBOURS = {"OKLAHOMA": "OK", "NEW MEXICO": "NM", "ARKANSAS": "AR", "LOUISIANA": "LA"}


def build_neighbour_hail(
    detail_paths: dict[int, Path], out: Path, start: int, end: int
) -> dict[str, int]:
    """Located hail reports in the states bordering Texas, from the cached NCEI details files.

    Only what the exposure needs (first point, size, year): the full cleaned event table stays
    Texas-only. With these, a circle near the state line counts reports on both sides.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    from crc_lab.storm_events import parse

    rows: list[dict[str, object]] = []
    for year in range(start, end + 1):
        if year not in detail_paths:
            continue
        table = parse.parse_details(detail_paths[year], states=tuple(NEIGHBOURS))
        for r in table.to_pylist():
            if (
                r["event_type"] == parse.HAIL
                and r["begin_lat"] is not None
                and r["begin_lon"] is not None
                and r["hail_size_mm"] is not None
            ):
                rows.append(
                    {
                        "state": r["state"],
                        "year": r["year"],
                        "lon": r["begin_lon"],
                        "lat": r["begin_lat"],
                        "hail_size_mm": r["hail_size_mm"],
                        "event_id": r["event_id"],
                    }
                )
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), out, compression="zstd")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return counts


def reporting_region(
    tiger_zip: Path, states: tuple[str, ...] = ("TX", "OK", "NM", "AR", "LA")
) -> object:
    """Union of the state polygons that the report set covers (Census cartographic boundaries)."""
    import shapely

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    name = tiger_zip.stem
    placeholders = ", ".join("?" for _ in states)
    rows = con.execute(
        f"SELECT ST_AsWKB(geom) FROM ST_Read('/vsizip/{tiger_zip}/{name}.shp') WHERE STUSPS IN ({placeholders})",
        list(states),
    ).fetchall()
    return shapely.union_all([shapely.from_wkb(bytes(r[0])) for r in rows])


def distances_km(lon: float, lat: float, reports: Reports) -> np.ndarray:
    """Great-circle distance from one point to every report."""
    p1, p2 = math.radians(lat), np.radians(reports.lat)
    dlat, dlon = p2 - p1, np.radians(reports.lon - lon)
    a = np.sin(dlat / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


def clipped_fraction(lon: float, lat: float, radius_km: float, region: object | None) -> float:
    """Share of the circle that lies inside ``region`` (a shapely geometry in lon/lat), 1 if none.

    Reports exist only where the event table covers: not in Mexico, the Gulf or other states. A
    circle that crosses the edge has less reporting area than pi r^2, so the rate must use the
    clipped area. Uses a local equal-distance projection centred on the point.
    """
    if region is None:
        return 1.0
    import shapely
    from shapely import affinity

    kx, ky = 111.32 * math.cos(math.radians(lat)), 110.57
    circle = affinity.scale(
        shapely.Point(lon, lat).buffer(1.0, quad_segs=32), radius_km / kx, radius_km / ky
    )
    inside = shapely.intersection(circle, region)
    return float(inside.area / circle.area) if circle.area else 1.0


def hit_area_km2(footprint_km2: float, plant_area_km2: float) -> float:
    """Area in which a hail footprint's centre must fall to touch the plant.

    Both are treated as discs of the stated areas: pi (r_footprint + r_plant)^2. A larger plant
    is a larger target; with a zero-area plant this is just the footprint.
    """
    r_f, r_p = math.sqrt(footprint_km2 / math.pi), math.sqrt(max(plant_area_km2, 0.0) / math.pi)
    return math.pi * (r_f + r_p) ** 2


def at_point(
    lon: float,
    lat: float,
    reports: Reports,
    rule: Rule | None = None,
    *,
    region: object | None = None,
    plant_area_km2: float = 0.0,
) -> dict[str, object]:
    """The local hail description at one point under ``rule``."""
    rule = rule or Rule()
    d = distances_km(lon, lat, reports)
    order = np.argsort(d)
    reach = float(d[order[rule.n_target - 1]]) if len(d) >= rule.n_target else math.inf
    radius = min(max(reach, rule.min_radius_km), rule.max_radius_km)
    inside = d <= radius
    n = int(inside.sum())
    fraction = clipped_fraction(lon, lat, radius, region)
    area = math.pi * radius**2 * fraction
    sizes = reports.size_mm[inside]
    rate = n / (area * reports.years)
    hit = hit_area_km2(rule.footprint_km2, plant_area_km2)
    out: dict[str, object] = {
        "rule": rule.label,
        "radius_km": round(radius, 2),
        "radius_to_n_km": None if math.isinf(reach) else round(reach, 2),
        "reports_in_radius": n,
        "flag": "ok" if reach <= rule.max_radius_km else "too_few_reports",
        "window": [reports.start, reports.end],
        "circle_share_inside_region": round(fraction, 3),
        "reporting_area_km2": round(area, 1),
        "report_rate_per_100km2_year": round(rate * 100, 4),
        "size_median_mm": round(float(np.median(sizes)), 1) if n else None,
        "size_p90_mm": round(float(np.quantile(sizes, 0.9)), 1) if n else None,
        "size_max_mm": round(float(sizes.max()), 1) if n else None,
        "footprint_km2_placeholder": rule.footprint_km2,
        "plant_area_km2": round(plant_area_km2, 3),
        "hit_area_km2": round(hit, 2),
    }
    for threshold in THRESHOLDS_MM:
        rate_t = float((sizes >= threshold).sum()) / (area * reports.years)
        key = f"{threshold / 25.4:g}in"
        out[f"rate_ge_{key}_per_100km2_year"] = round(rate_t * 100, 4)
        # Poisson: chance that at least one footprint of this size touches the plant in a year
        out[f"annual_prob_ge_{key}"] = round(1 - math.exp(-rate_t * hit), 5)
    return out


def rule_dict(rule: Rule) -> dict[str, object]:
    return asdict(rule) | {"label": rule.label, "footprint_is_placeholder": True}
