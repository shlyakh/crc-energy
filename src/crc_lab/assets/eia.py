# ruff: noqa: E501
"""Texas solar plant list from EIA (Form 860 and 860M) through Catalyst Cooperative's PUDL tables.

EIA is the fuller and fresher list (every generator of 1 MW or more, monthly); the USGS / Berkeley Lab
solar database (USPVDB) is joined in for array polygons and area. Plants are EIA plants: generators
with prime mover PV and status existing, summed per ``plant_id_eia``.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

PUDL = "https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop/nightly"
GENERATORS = f"{PUDL}/out_eia__yearly_generators.parquet"
SOLAR = f"{PUDL}/core_eia860__scd_generators_solar.parquet"
CITATION = "U.S. Energy Information Administration, Forms EIA-860 and EIA-860M, as processed by Catalyst Cooperative's Public Utility Data Liberation project (PUDL)"
LICENCE = (
    "EIA data: U.S. government work. PUDL: CC BY 4.0 (per PUDL documentation; not re-checked here)"
)


def _head(url: str) -> dict[str, str | None]:
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=60) as response:
        return {
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "bytes": response.headers.get("Content-Length"),
        }


def fetch(cache_dir: Path, *, state: str = "TX", refresh: bool = False) -> dict[str, Any]:
    """Extract the state's PV generators and solar schedule into small cached Parquet files."""
    directory = cache_dir / "eia"
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    gens, solar = (
        directory / f"generators_pv_{state}.parquet",
        directory / f"solar_schedule_{state}.parquet",
    )
    if manifest_path.exists() and gens.exists() and solar.exists() and not refresh:
        return json.loads(manifest_path.read_text())
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(
        f"""COPY (SELECT * FROM read_parquet('{GENERATORS}')
                  WHERE state = '{state}' AND prime_mover_code = 'PV'
                    AND report_date = (SELECT max(report_date) FROM read_parquet('{GENERATORS}')))
            TO '{gens}' (FORMAT PARQUET)"""
    )
    con.execute(
        f"""COPY (SELECT s.* FROM read_parquet('{SOLAR}') s
                  WHERE s.plant_id_eia IN (SELECT plant_id_eia FROM read_parquet('{gens}'))
                    AND s.report_date = (SELECT max(report_date) FROM read_parquet('{SOLAR}')))
            TO '{solar}' (FORMAT PARQUET)"""
    )
    manifest = {
        "citation": CITATION,
        "licence": LICENCE,
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "generators": {
            "url": GENERATORS,
            **_head(GENERATORS),
            "extract_sha256": hashlib.sha256(gens.read_bytes()).hexdigest(),
            "report_date": str(
                con.execute(f"SELECT max(report_date) FROM read_parquet('{gens}')").fetchone()[0]
            ),
        },
        "solar_schedule": {
            "url": SOLAR,
            **_head(SOLAR),
            "extract_sha256": hashlib.sha256(solar.read_bytes()).hexdigest(),
            "report_date": str(
                con.execute(f"SELECT max(report_date) FROM read_parquet('{solar}')").fetchone()[0]
            ),
        },
        "state": state,
    }
    manifest_path.write_text(json.dumps(manifest, indent=1))
    return manifest


def plants(cache_dir: Path, *, state: str = "TX") -> pa.Table:
    """One row per existing EIA PV plant: capacity summed over generators, with solar-schedule flags."""
    directory = cache_dir / "eia"
    con = duckdb.connect()
    return con.execute(
        f"""WITH g AS (SELECT * FROM read_parquet('{directory / f"generators_pv_{state}.parquet"}') WHERE operational_status = 'existing'),
                 s AS (SELECT plant_id_eia,
                              bool_or(uses_technology_single_axis_tracking) AS single_axis,
                              bool_or(uses_technology_fixed_tilt) AS fixed_tilt,
                              bool_or(uses_technology_dual_axis_tracking) AS dual_axis,
                              bool_or(uses_bifacial_panels) AS bifacial,
                              bool_or(uses_material_crystalline_silicon) AS crystalline_silicon,
                              bool_or(uses_material_thin_film_cdte) AS thin_film_cdte,
                              max(tilt_angle_deg) AS tilt_deg,
                              sum(standard_testing_conditions_capacity_mwdc) AS capacity_dc_mw
                       FROM read_parquet('{directory / f"solar_schedule_{state}.parquet"}') GROUP BY 1)
            SELECT 'eia-' || g.plant_id_eia AS asset_id, g.plant_id_eia AS eia_id,
                   any_value(g.plant_name_eia) AS name, any_value(g.county) AS county,
                   any_value(g.balancing_authority_code_eia) AS balancing_authority,
                   any_value(g.longitude) AS longitude, any_value(g.latitude) AS latitude,
                   sum(g.capacity_mw) AS capacity_ac_mw, count(*) AS generators,
                   min(g.generator_operating_date) AS first_operating_date,
                   max(g.generator_operating_date) AS last_operating_date,
                   year(min(g.generator_operating_date)) AS year,
                   any_value(g.data_maturity) AS data_maturity,
                   any_value(s.single_axis) AS single_axis, any_value(s.fixed_tilt) AS fixed_tilt, any_value(s.dual_axis) AS dual_axis,
                   any_value(s.bifacial) AS bifacial, any_value(s.crystalline_silicon) AS crystalline_silicon,
                   any_value(s.thin_film_cdte) AS thin_film_cdte, any_value(s.tilt_deg) AS tilt_deg,
                   any_value(s.capacity_dc_mw) AS capacity_dc_mw, any_value(s.plant_id_eia) IS NOT NULL AS in_solar_schedule
            FROM g LEFT JOIN s USING (plant_id_eia)
            GROUP BY g.plant_id_eia ORDER BY g.plant_id_eia"""
    ).to_arrow_table()


def join_uspvdb(eia: pa.Table, uspvdb: pa.Table) -> tuple[pa.Table, dict[str, Any]]:
    """Attach USPVDB polygons, area and mounting; estimate area for plants without a polygon."""
    con = duckdb.connect()
    con.register("e", eia)
    con.register("u", uspvdb)
    con.execute(
        """CREATE TABLE up AS SELECT eia_id, count(*) AS polygons, sum(area_m2) AS area_m2, sum(capacity_ac_mw) AS uspvdb_capacity_ac_mw,
                  min(year) AS uspvdb_year, any_value(axis) AS uspvdb_axis, any_value(module_tech) AS uspvdb_module_tech,
                  any_value(longitude) AS uspvdb_lon, any_value(latitude) AS uspvdb_lat, string_agg(asset_id, ',') AS uspvdb_ids
           FROM u WHERE eia_id IS NOT NULL GROUP BY 1"""
    )
    ratio = con.execute(
        "SELECT median(up.area_m2 / e.capacity_ac_mw) FROM e JOIN up USING (eia_id) WHERE e.capacity_ac_mw > 0 AND up.area_m2 > 0"
    ).fetchone()[0]
    table = con.execute(
        f"""SELECT e.*, up.polygons IS NOT NULL AS has_polygon, up.uspvdb_ids, up.uspvdb_capacity_ac_mw, up.uspvdb_year,
                   up.uspvdb_axis, up.uspvdb_module_tech, up.uspvdb_lon, up.uspvdb_lat,
                   coalesce(up.area_m2, e.capacity_ac_mw * {ratio}) AS area_m2,
                   CASE WHEN up.area_m2 IS NULL THEN 'estimated from capacity' ELSE 'USPVDB polygon' END AS area_source,
                   coalesce(up.uspvdb_lon, e.longitude) AS lon_used, coalesce(up.uspvdb_lat, e.latitude) AS lat_used,
                   CASE WHEN up.uspvdb_lon IS NOT NULL THEN 'USPVDB (imagery-verified)' ELSE 'EIA' END AS location_source
            FROM e LEFT JOIN up USING (eia_id) ORDER BY e.eia_id"""
    ).to_arrow_table()
    table = table.drop_columns(["longitude", "latitude"]).rename_columns(
        {"lon_used": "longitude", "lat_used": "latitude"}
    )
    return table, {"area_m2_per_mw_ac_median": ratio}


def compare(eia: pa.Table, uspvdb: pa.Table) -> dict[str, Any]:
    """What differs between the two lists: newer plants, or corrections?"""
    con = duckdb.connect()
    con.register("e", eia)
    con.register("u", uspvdb)
    con.execute(
        "CREATE TABLE up AS SELECT eia_id, sum(capacity_ac_mw) mw, min(year) yr, any_value(name) uname, any_value(longitude) lon, any_value(latitude) lat FROM u GROUP BY 1"
    )
    one = lambda sql: con.execute(sql).fetchall()  # noqa: E731
    out: dict[str, Any] = {
        "eia": one("SELECT count(*), round(sum(capacity_ac_mw)) FROM e")[0],
        "uspvdb": one("SELECT count(*), round(sum(mw)) FROM up")[0],
        "matched": one(
            "SELECT count(*), round(sum(e.capacity_ac_mw)), round(sum(up.mw)) FROM e JOIN up USING (eia_id)"
        )[0],
        "eia_only_by_first_year": one(
            "SELECT year, count(*), round(sum(capacity_ac_mw)) FROM e WHERE eia_id NOT IN (SELECT eia_id FROM up) GROUP BY 1 ORDER BY 1 DESC"
        ),
        "eia_only_before_2025": one(
            "SELECT name, county, year, capacity_ac_mw FROM e WHERE eia_id NOT IN (SELECT eia_id FROM up) AND year < 2025 ORDER BY year"
        ),
        "uspvdb_only": one(
            "SELECT up.eia_id, uname, yr, mw FROM up WHERE eia_id NOT IN (SELECT eia_id FROM e)"
        ),
        "capacity_differs": one(
            "SELECT count(*) FILTER (WHERE abs(e.capacity_ac_mw - up.mw) > 0.05 * e.capacity_ac_mw), count(*) FROM e JOIN up USING (eia_id)"
        )[0],
        "capacity_examples": one(
            "SELECT e.name, e.capacity_ac_mw, up.mw, e.generators FROM e JOIN up USING (eia_id) WHERE abs(e.capacity_ac_mw - up.mw) > 0.05 * e.capacity_ac_mw ORDER BY abs(e.capacity_ac_mw - up.mw) DESC LIMIT 8"
        ),
        "year_differs": one(
            "SELECT count(*) FILTER (WHERE e.year <> up.yr), count(*) FILTER (WHERE abs(e.year - up.yr) > 1), count(*) FROM e JOIN up USING (eia_id)"
        )[0],
        "year_examples": one(
            "SELECT e.name, e.year, up.yr FROM e JOIN up USING (eia_id) WHERE abs(e.year - up.yr) > 1 ORDER BY abs(e.year - up.yr) DESC LIMIT 8"
        ),
        "location_km": one("""SELECT round(quantile_cont(d, 0.5), 2), round(quantile_cont(d, 0.9), 2), round(max(d), 1), count(*) FILTER (WHERE d > 5)
                              FROM (SELECT 111.2 * sqrt(pow(e.latitude - up.lat, 2) + pow((e.longitude - up.lon) * cos(radians(e.latitude)), 2)) d FROM e JOIN up USING (eia_id) WHERE e.latitude IS NOT NULL)""")[
            0
        ],
        "by_balancing_authority": one(
            "SELECT balancing_authority, count(*), round(sum(capacity_ac_mw)) FROM e GROUP BY 1 ORDER BY 2 DESC"
        ),
        "solar_schedule": one(
            "SELECT count(*) FILTER (WHERE in_solar_schedule), count(*) FILTER (WHERE single_axis), count(*) FILTER (WHERE bifacial), count(*) FILTER (WHERE crystalline_silicon), count(*) FILTER (WHERE thin_film_cdte), count(*) FROM e"
        )[0],
        "missing_coordinates": one("SELECT count(*) FROM e WHERE latitude IS NULL")[0][0],
    }
    return out
