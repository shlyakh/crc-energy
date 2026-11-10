# ruff: noqa: E501  (SQL and SVG templates read better on one line)
"""S5: compare NCEI direct against the Source Cooperative (Earth Genome) copy, for Texas.

Produces the seven tables of requirements section 4.1 and three density maps (SVG), as a
Markdown report. Everything is computed from the two cached snapshots; nothing is typed in.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import duckdb
import shapely

COPY_URL = "https://data.source.coop/earthgenome/storm-events-db/events.parquet"
COPY_README = "https://data.source.coop/earthgenome/storm-events-db/README.md"
STATE = "TEXAS"
BIN_DEG = 0.25


def copy_type_slug(event_type: str) -> str:
    """NCEI 'Thunderstorm Wind' -> copy 'thunderstorm-wind' (the README's convention)."""
    return (
        event_type.lower().replace(" ", "-").replace("(typhoon)", "").strip("-").replace("--", "-")
    )


def load(con: duckdb.DuckDBPyConnection, events: Path, copy: Path) -> None:
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute(
        f"""CREATE TABLE ncei AS
        WITH e AS (SELECT *, ST_GeomFromWKB(geometry_wkb) AS geom FROM read_parquet('{events}'))
        SELECT *,
               CASE WHEN geom IS NULL THEN NULL
                    WHEN ST_GeometryType(geom) = 'LINESTRING' THEN ST_X(ST_StartPoint(geom))
                    ELSE ST_X(geom) END AS lon0,
               CASE WHEN geom IS NULL THEN NULL
                    WHEN ST_GeometryType(geom) = 'LINESTRING' THEN ST_Y(ST_StartPoint(geom))
                    ELSE ST_Y(geom) END AS lat0
        FROM e"""
    )
    con.execute(
        f"""CREATE TABLE sc AS
        SELECT * EXCLUDE (geometry), geometry AS geom,
               CASE WHEN geometry IS NULL THEN NULL ELSE ST_X(geometry) END AS lon,
               CASE WHEN geometry IS NULL THEN NULL ELSE ST_Y(geometry) END AS lat
        FROM read_parquet('{copy}') WHERE state = '{STATE}'"""
    )


def q(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    rel = con.execute(sql)
    cols = [d[0] for d in rel.description]
    return [dict(zip(cols, row, strict=True)) for row in rel.fetchall()]


def table_md(rows: list[dict[str, Any]], limit: int | None = None) -> str:
    if not rows:
        return "_no rows_\n"
    cols = list(rows[0])
    out = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in rows[: limit or len(rows)]:
        out.append("| " + " | ".join(_cell(row[c], c) for c in cols) + " |")
    if limit and len(rows) > limit:
        out.append(f"\n_{len(rows) - limit} more rows not shown_")
    return "\n".join(out) + "\n"


_PLAIN = ("year", "event_id", "ncei_latest_year", "copy_latest_year", "lon", "lat")


def _cell(value: Any, column: str = "") -> str:
    if value is None:
        return "–"
    if column in _PLAIN:
        return str(value)
    if isinstance(value, float):
        return f"{value:,.3f}".rstrip("0").rstrip(".") if abs(value) < 1e6 else f"{value:,.0f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value).replace("|", "\\|")


def comparisons(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    out: dict[str, Any] = {}
    # 1. counts by year and type
    out["counts_by_year"] = q(
        con,
        """WITH n AS (SELECT year, count(*) ncei FROM ncei GROUP BY 1),
                c AS (SELECT year, count(*) sc_n FROM sc GROUP BY 1)
           SELECT coalesce(n.year, c.year) AS year, coalesce(ncei, 0) ncei, coalesce(sc_n, 0) copy_count,
                  coalesce(ncei, 0) - coalesce(sc_n, 0) AS difference
           FROM n FULL OUTER JOIN c USING (year) ORDER BY 1""",
    )
    out["counts_by_type"] = q(
        con,
        """WITH n AS (SELECT event_type, count(*) ncei FROM ncei GROUP BY 1),
                c AS (SELECT event_type, count(*) sc_n FROM sc GROUP BY 1)
           SELECT coalesce(n.event_type, c.event_type) AS type_name, coalesce(ncei, 0) ncei, coalesce(sc_n, 0) copy_count
           FROM n FULL OUTER JOIN c ON lower(replace(n.event_type, ' ', '-')) = c.event_type
           ORDER BY ncei DESC, copy_count DESC""",
    )
    # 2. presence by event id
    out["only_ncei"] = q(
        con,
        """SELECT year, event_type, count(*) events FROM ncei
           WHERE event_id NOT IN (SELECT event_id FROM sc) GROUP BY 1, 2 ORDER BY 1, 2""",
    )
    out["only_copy"] = q(
        con,
        """SELECT year, event_type, count(*) events FROM sc
           WHERE event_id NOT IN (SELECT event_id FROM ncei) GROUP BY 1, 2 ORDER BY 1, 2""",
    )
    out["presence"] = q(
        con,
        """SELECT (SELECT count(*) FROM ncei) ncei_events, (SELECT count(*) FROM sc) copy_events,
                  (SELECT count(*) FROM ncei WHERE event_id IN (SELECT event_id FROM sc)) matched_events,
                  (SELECT count(*) FROM ncei WHERE event_id NOT IN (SELECT event_id FROM sc)) only_ncei,
                  (SELECT count(*) FROM sc WHERE event_id NOT IN (SELECT event_id FROM ncei)) only_copy""",
    )
    # 3. matched: distance between locations; centroid share
    con.execute(
        """CREATE TABLE m AS
           SELECT n.event_id, n.year, n.event_type, n.geometry_kind, n.lon0, n.lat0, n.geom AS ngeom,
                  c.lon, c.lat, c.geom AS cgeom, n.cz_type, n.cz_fips,
                  n.hail_size_in, n.wind_knots, n.magnitude AS nmag, n.magnitude_type AS nmagt,
                  c.magnitude AS cmag, c.magnitude_type AS cmagt,
                  n.damage_property_usd, n.damage_property_raw, n.damage_property_flag, c.damage_property AS cdamage,
                  n.damage_crops_usd, c.damage_crops AS ccrops,
                  n.begin_utc, n.begin_local, c.begin_ts
           FROM ncei n JOIN sc c USING (event_id)"""
    )
    out["distance"] = q(
        con,
        """SELECT geometry_kind,
                  count(*) events,
                  count(*) FILTER (WHERE lon IS NULL) copy_no_geometry,
                  count(*) FILTER (WHERE lon0 IS NOT NULL AND lon IS NOT NULL AND abs(lon - lon0) < 1e-6 AND abs(lat - lat0) < 1e-6) same_point,
                  round(quantile_cont(ST_Distance_Sphere(ST_Point(lon0, lat0), ST_Point(lon, lat)) / 1000, 0.5), 2) median_km,
                  round(max(ST_Distance_Sphere(ST_Point(lon0, lat0), ST_Point(lon, lat)) / 1000), 1) max_km
           FROM m GROUP BY 1 ORDER BY events DESC""",
    )
    out["centroid_share"] = q(
        con,
        """WITH k AS (
             SELECT m.*, coalesce(cp.geom, zp.geom) AS polygon
             FROM m LEFT JOIN county_polygons cp ON m.geometry_kind = 'county' AND cp.fips = m.cz_fips
                    LEFT JOIN zone_polygons zp ON m.geometry_kind = 'zone' AND zp.zone = m.cz_fips)
           SELECT count(*) matched_events,
                  count(*) FILTER (WHERE geometry_kind IN ('county', 'zone')) ncei_without_point,
                  count(*) FILTER (WHERE geometry_kind IN ('county', 'zone') AND lon IS NOT NULL) copy_gave_a_point_for_these,
                  round(100.0 * count(*) FILTER (WHERE geometry_kind IN ('county', 'zone') AND lon IS NOT NULL) / count(*), 1) share_percent,
                  count(*) FILTER (WHERE geometry_kind IN ('county', 'zone') AND lon IS NOT NULL AND polygon IS NOT NULL AND ST_Within(ST_Point(lon, lat), polygon)) copy_point_inside_ncei_polygon,
                  count(*) FILTER (WHERE geometry_kind IN ('county', 'zone') AND lon IS NOT NULL AND polygon IS NOT NULL AND NOT ST_Within(ST_Point(lon, lat), polygon)) copy_point_outside_ncei_polygon
           FROM k""",
    )
    # 4. magnitude and type
    out["magnitude"] = q(
        con,
        """SELECT event_type, count(*) matched_events,
                  count(nmag) ncei_has_magnitude, count(cmag) copy_has_magnitude,
                  count(*) FILTER (WHERE nmag IS NOT NULL AND cmag IS NOT NULL AND abs(nmag - cmag) < 1e-3) equal_magnitude,
                  count(nmagt) ncei_has_type, count(cmagt) copy_has_type,
                  count(*) FILTER (WHERE nmagt IS NOT NULL AND nmagt = cmagt) equal_type
           FROM m WHERE event_type IN ('Hail', 'Thunderstorm Wind') GROUP BY 1""",
    )
    out["magnitude_examples"] = q(
        con,
        """SELECT event_id, year, event_type, nmag AS ncei_magnitude, cmag AS copy_magnitude, nmagt AS ncei_type, cmagt AS copy_type
           FROM m WHERE event_type IN ('Hail', 'Thunderstorm Wind') AND nmag IS NOT NULL AND cmag IS NOT NULL AND abs(nmag - cmag) >= 1e-3
           ORDER BY abs(nmag - cmag) DESC LIMIT 10""",
    )
    # 5. damage
    out["damage"] = q(
        con,
        """SELECT damage_property_flag AS ncei_parse,
                  count(*) events,
                  count(cdamage) copy_not_null,
                  count(*) FILTER (WHERE damage_property_usd IS NOT NULL AND cdamage IS NOT NULL AND abs(damage_property_usd - cdamage) < 0.5) equal,
                  count(*) FILTER (WHERE damage_property_usd IS NULL AND cdamage = 0) ncei_null_copy_zero,
                  count(*) FILTER (WHERE damage_property_usd IS NOT NULL AND cdamage IS NOT NULL AND abs(damage_property_usd - cdamage) >= 0.5) different
           FROM m GROUP BY 1 ORDER BY events DESC""",
    )
    out["damage_examples"] = q(
        con,
        """SELECT event_id, year, event_type, damage_property_raw AS ncei_raw, damage_property_usd AS ncei_usd, cdamage AS copy_usd
           FROM m WHERE damage_property_usd IS NOT NULL AND cdamage IS NOT NULL AND abs(damage_property_usd - cdamage) >= 0.5
           ORDER BY abs(damage_property_usd - cdamage) DESC LIMIT 10""",
    )
    # 6. county code vs coordinates
    con.execute(
        """CREATE TABLE county AS SELECT * FROM ncei WHERE cz_type = 'C' AND geometry_kind IN ('point', 'path')"""
    )
    out["county_conflicts"] = q(
        con,
        """WITH j AS (
             SELECT n.event_id, n.year, n.event_type, n.cz_fips, n.cz_name, n.lon0, n.lat0,
                    ST_Within(ST_Point(n.lon0, n.lat0), b.geom) AS inside
             FROM county n LEFT JOIN county_polygons b ON b.fips = n.cz_fips)
           SELECT count(*) county_events_with_points,
                  count(*) FILTER (WHERE inside IS NULL) county_polygon_missing,
                  count(*) FILTER (WHERE inside = false) point_outside_its_county,
                  round(100.0 * count(*) FILTER (WHERE inside = false) / count(*), 2) percent_outside
           FROM j""",
    )
    out["county_conflicts_copy"] = q(
        con,
        """WITH j AS (
             SELECT n.event_id, n.lon0, n.lat0, ST_Within(ST_Point(n.lon0, n.lat0), b.geom) AS inside
             FROM county n LEFT JOIN county_polygons b ON b.fips = n.cz_fips)
           SELECT count(*) conflicting_events,
                  count(*) FILTER (WHERE c.lon IS NULL) copy_dropped_geometry,
                  count(*) FILTER (WHERE c.lon IS NOT NULL AND abs(c.lon - j.lon0) < 1e-6 AND abs(c.lat - j.lat0) < 1e-6) copy_kept_ncei_point,
                  count(*) FILTER (WHERE c.lon IS NOT NULL AND (abs(c.lon - j.lon0) >= 1e-6 OR abs(c.lat - j.lat0) >= 1e-6)) copy_moved_point
           FROM j LEFT JOIN sc c USING (event_id) WHERE inside = false""",
    )
    out["county_conflict_examples"] = q(
        con,
        """WITH j AS (
             SELECT n.event_id, n.year, n.event_type, n.cz_name, n.lon0, n.lat0,
                    ST_Within(ST_Point(n.lon0, n.lat0), b.geom) AS inside
             FROM county n LEFT JOIN county_polygons b ON b.fips = n.cz_fips)
           SELECT event_id, year, event_type, cz_name, round(lon0, 3) lon, round(lat0, 3) lat
           FROM j WHERE inside = false ORDER BY year DESC, event_id LIMIT 8""",
    )
    # 7. latest date
    out["latest"] = q(
        con,
        """SELECT (SELECT CAST(max(begin_utc) AT TIME ZONE 'UTC' AS VARCHAR) FROM ncei) ncei_latest_begin_utc,
                  (SELECT CAST(max(begin_ts) AS VARCHAR) FROM sc) copy_latest_begin_ts,
                  (SELECT max(year) FROM ncei) ncei_latest_year, (SELECT max(year) FROM sc) copy_latest_year""",
    )
    # time convention check: does the copy's begin_ts equal NCEI local or UTC?
    out["time_convention"] = q(
        con,
        """SELECT count(*) matched_events,
                  count(*) FILTER (WHERE begin_ts = CAST(begin_local AS TIMESTAMP)) copy_equals_ncei_local,
                  count(*) FILTER (WHERE begin_ts = CAST(strftime(begin_utc AT TIME ZONE 'UTC', '%Y-%m-%d %H:%M:%S') AS TIMESTAMP)) copy_equals_utc
           FROM m WHERE begin_ts IS NOT NULL AND begin_local IS NOT NULL""",
    )
    return out


def load_polygons(
    con: duckdb.DuckDBPyConnection, counties: dict[int, bytes], zones: dict[int, bytes]
) -> None:
    con.execute("CREATE TABLE county_polygons (fips INTEGER, geom GEOMETRY)")
    con.executemany(
        "INSERT INTO county_polygons SELECT ?, ST_GeomFromWKB(?)",
        [(fips, wkb) for fips, wkb in counties.items()],
    )
    con.execute("CREATE TABLE zone_polygons (zone INTEGER, geom GEOMETRY)")
    con.executemany(
        "INSERT INTO zone_polygons SELECT ?, ST_GeomFromWKB(?)",
        [(zone, wkb) for zone, wkb in zones.items()],
    )


def density_svg(
    points: list[tuple[float, float]],
    outline: list[list[tuple[float, float]]],
    title: str,
    *,
    missing: list[tuple[float, float]] | None = None,
) -> str:
    """A 0.1-degree bin density map with the Texas outline; log colour scale."""
    lon0, lon1, lat0, lat1 = -106.7, -93.4, 25.7, 36.6
    w, h = 720, 600
    sx = w / (lon1 - lon0)
    sy = h / (lat1 - lat0)
    bins: dict[tuple[int, int], int] = {}
    for lon, lat in points:
        if lon0 <= lon <= lon1 and lat0 <= lat <= lat1:
            key = (int((lon - lon0) / BIN_DEG), int((lat - lat0) / BIN_DEG))
            bins[key] = bins.get(key, 0) + 1
    top = math.log1p(max(bins.values())) if bins else 1.0
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h + 30}" width="{w}" height="{h + 30}" font-family="Helvetica, Arial, sans-serif">',
        f'<rect width="{w}" height="{h + 30}" fill="#faf9f6"/>',
        f'<text x="12" y="20" font-size="14" font-weight="600" fill="#2a2a28">{title}</text>',
        f'<text x="{w - 12}" y="20" font-size="11" text-anchor="end" fill="#7a7976">{len(points):,} events in {BIN_DEG}° bins; darker = more (log scale)</text>',
        '<g transform="translate(0,30)">',
    ]
    bw, bh = BIN_DEG * sx, BIN_DEG * sy
    for (i, j), n in bins.items():
        t = math.log1p(n) / top
        light = 93 - 58 * t
        parts.append(
            f'<rect x="{i * bw:.1f}" y="{h - (j + 1) * bh:.1f}" width="{bw:.2f}" height="{bh:.2f}" fill="oklch({light:.0f}% {0.12 + 0.05 * t:.2f} 235)"/>'
        )
    for ring in outline:
        d = " ".join(f"{(lon - lon0) * sx:.1f},{h - (lat - lat0) * sy:.1f}" for lon, lat in ring)
        parts.append(f'<polyline points="{d}" fill="none" stroke="#2a2a28" stroke-width="1.2"/>')
    for lon, lat in missing or []:
        if lon0 <= lon <= lon1 and lat0 <= lat <= lat1:
            parts.append(
                f'<circle cx="{(lon - lon0) * sx:.1f}" cy="{h - (lat - lat0) * sy:.1f}" r="2.5" fill="none" stroke="#eb6834" stroke-width="1"/>'
            )
    parts.append("</g></svg>")
    return "\n".join(parts)


def texas_outline(geojson: Path) -> list[list[tuple[float, float]]]:
    geometry = shapely.from_geojson(
        json.dumps(json.loads(geojson.read_text())["features"][0]["geometry"])
    )
    rings = []
    polygons = geometry.geoms if geometry.geom_type == "MultiPolygon" else [geometry]
    for polygon in polygons:
        rings.append([(x, y) for x, y in polygon.exterior.coords])
    return rings


def write_report(
    results: dict[str, Any],
    con: duckdb.DuckDBPyConnection,
    outline: list[list[tuple[float, float]]],
    report: Path,
    figures: Path,
    *,
    copy_meta: dict[str, Any],
    ncei_card: dict[str, Any],
) -> None:
    figures.mkdir(parents=True, exist_ok=True)
    maps = []
    for name, where, title in (
        ("all", "TRUE", "All Texas events with a point or path (NCEI)"),
        ("hail", "event_type = 'Hail'", "Hail reports (NCEI)"),
        ("wind", "event_type = 'Thunderstorm Wind'", "Thunderstorm wind reports (NCEI)"),
    ):
        points = con.execute(
            f"SELECT lon0, lat0 FROM ncei WHERE lon0 IS NOT NULL AND {where}"
        ).fetchall()
        missing = con.execute(
            f"SELECT lon0, lat0 FROM ncei WHERE lon0 IS NOT NULL AND {where} AND event_id NOT IN (SELECT event_id FROM sc)"
        ).fetchall()
        svg = density_svg(points, outline, title, missing=missing)
        path = figures / f"storm-events-{name}.svg"
        _write(path, svg)
        maps.append((title, path.relative_to(report.parent).as_posix(), len(points), len(missing)))
    md = [
        "# Phase 2 report: Storm Events two-source comparison, Texas",
        "",
        f"NCEI snapshot retrieved {ncei_card.get('retrieved_at')}; Source Cooperative copy `events.parquet` "
        f"(Last-Modified {copy_meta.get('last_modified')}, SHA-256 `{copy_meta.get('sha256', '')[:16]}…`, "
        f"{copy_meta.get('bytes', 0) / 1e6:.0f} MB). Matching on NOAA's `event_id`. State filter: `TEXAS` in both.",
        "",
        "## 1. Event counts",
        "",
        "By year (NCEI direct, copy, difference):",
        "",
        table_md(results["counts_by_year"]),
        "By event type (NCEI name against the copy's slug):",
        "",
        table_md(results["counts_by_type"]),
        "## 2. Present in one, missing in the other",
        "",
        table_md(results["presence"]),
        "Only in NCEI, by year and type:",
        "",
        table_md(results["only_ncei"], limit=40),
        "Only in the copy, by year and type:",
        "",
        table_md(results["only_copy"], limit=40),
        "## 3. Matched events: location",
        "",
        "Distance between NCEI's first point and the copy's point, by how NCEI located the event "
        "(`path`/`point` have coordinates; `county`/`zone` do not, so the copy's point there is a centroid):",
        "",
        table_md(results["distance"]),
        table_md(results["centroid_share"]),
        "## 4. Magnitude and magnitude type (hail, thunderstorm wind)",
        "",
        "The copy stores magnitude as float32, so values are compared to 0.001:",
        "",
        table_md(results["magnitude"]),
        "Largest disagreements in magnitude among matched hail and wind events:",
        "",
        table_md(results["magnitude_examples"]),
        "## 5. Damage fields",
        "",
        "NCEI strings parsed here as number × K/M/B; the copy ships integers (null NCEI strings appear as 0 in the copy):",
        "",
        table_md(results["damage"]),
        "Largest disagreements among matched, parsed values:",
        "",
        table_md(results["damage_examples"]),
        "## 6. County code against coordinates",
        "",
        "County-located events whose NCEI point falls outside that county's Census polygon:",
        "",
        table_md(results["county_conflicts"]),
        "What the copy did with those events:",
        "",
        table_md(results["county_conflicts_copy"]),
        table_md(results["county_conflict_examples"]),
        "## 7. Latest date covered",
        "",
        table_md(results["latest"]),
        "## Time convention",
        "",
        "Whether the copy's `begin_ts` equals NCEI's local standard time (as printed in the file) or UTC:",
        "",
        table_md(results["time_convention"]),
        "## Maps",
        "",
    ]
    for title, rel, n, miss in maps:
        md.append(
            f"**{title}** — {n:,} events; orange rings mark the {miss:,} not in the copy.\n\n![{title}]({rel})\n"
        )
    md += ["## Conclusion", "", *conclusion(results), ""]
    _write(report, "\n".join(md))


def conclusion(r: dict[str, Any]) -> list[str]:
    """Plain statements derived from the tables above (numbers are not typed in)."""
    p = r["presence"][0]
    years_diff = [row for row in r["counts_by_year"] if row["difference"] != 0]
    latest = r["latest"][0]
    cen = r["centroid_share"][0]
    mag = {row["event_type"]: row for row in r["magnitude"]}
    dmg = {row["ncei_parse"]: row for row in r["damage"]}
    cc = r["county_conflicts"][0]
    ccc = r["county_conflicts_copy"][0]
    tc = r["time_convention"][0]
    dist = {row["geometry_kind"]: row for row in r["distance"]}
    same = sum(dist[k]["same_point"] for k in ("point", "path") if k in dist)
    located = sum(dist[k]["events"] for k in ("point", "path") if k in dist)
    slug_gaps = [
        row["type_name"]
        for row in r["counts_by_type"]
        if row["ncei"] == 0 or row["copy_count"] == 0
    ]
    out = [
        f"- **Same events.** {p['matched_events']:,} of {p['ncei_events']:,} NCEI Texas events are in the copy by `event_id`; "
        f"nothing is in the copy only. The {p['only_ncei']:,} NCEI-only events are all in "
        f"{', '.join(str(row['year']) for row in years_diff) or 'no year'}: the copy lags "
        f"(latest `begin_ts` {latest['copy_latest_begin_ts']}, NCEI {latest['ncei_latest_begin_utc']} UTC).",
        f"- **Same points where NCEI has them.** {same:,} of {located:,} located events carry the identical first coordinate in the copy "
        f"(paths keep only their first point). For the {cen['ncei_without_point']:,} county- and zone-located events "
        f"({cen['share_percent']}% of matched) the copy supplies a centroid, which lies inside the NCEI polygon in "
        f"{cen['copy_point_inside_ncei_polygon']:,} cases; those points are areas, not places.",
        f"- **Magnitudes agree.** Hail: {mag['Hail']['equal_magnitude']:,} of {mag['Hail']['ncei_has_magnitude']:,} equal; "
        f"thunderstorm wind: {mag['Thunderstorm Wind']['equal_magnitude']:,} of {mag['Thunderstorm Wind']['ncei_has_magnitude']:,}, "
        f"with `magnitude_type` present and equal for {mag['Thunderstorm Wind']['equal_type']:,} wind events "
        f"(NCEI itself has no type for the rest). The copy stores magnitude as float32.",
        f"- **Damage parsed the same way.** {dmg.get('ok', {}).get('equal', 0):,} parsed values equal to the dollar; "
        f"the {dmg.get('empty', {}).get('events', 0):,} empty NCEI strings are 0 in the copy, so the copy cannot distinguish 'no damage' from 'not reported'.",
        f"- **Times are local standard time, not UTC.** The copy's `begin_ts` equals NCEI's printed local time for "
        f"{tc['copy_equals_ncei_local']:,} of {tc['matched_events']:,} events and UTC for {tc['copy_equals_utc']:,}; "
        f"it carries no offset. This table converts with `CZ_TIMEZONE`.",
        f"- **County code against coordinates.** {cc['point_outside_its_county']:,} of {cc['county_events_with_points']:,} county-located "
        f"events ({cc['percent_outside']}%) have a point outside that county's Census polygon; the copy kept the NCEI point for "
        f"{ccc['copy_kept_ncei_point']:,}, dropped geometry for {ccc['copy_dropped_geometry']:,}, moved none. Neither source resolves them.",
        f"- **Naming.** Type slugs differ from NCEI names only for {', '.join(slug_gaps) if slug_gaps else 'no type'}.",
        "",
        "**What the copy can be used for:** quick maps and counts of events up to its cutoff, with the same magnitudes and damage "
        "as NCEI. **What it cannot be used for:** UTC-aware timing, paths and multi-point events, telling unreported from zero "
        "damage, anything after its last monthly update, and any county/zone event as a precise location. "
        "This project therefore builds from NCEI direct and keeps the copy as a cross-check.",
    ]
    return out


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def run(
    events: Path,
    copy: Path,
    counties: dict[int, bytes],
    zones: dict[int, bytes],
    texas_geojson: Path,
    report: Path,
    figures: Path,
    *,
    copy_meta: dict[str, Any],
    ncei_card: dict[str, Any],
) -> dict[str, Any]:
    con = duckdb.connect()
    load(con, events, copy)
    load_polygons(con, counties, zones)
    results = comparisons(con)
    write_report(
        results,
        con,
        texas_outline(texas_geojson),
        report,
        figures,
        copy_meta=copy_meta,
        ncei_card=ncei_card,
    )
    return results
