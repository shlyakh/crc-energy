"""``python -m crc_lab.risk_layer``: files behind the explorer's Risk tab.

Reads the Phase 4 plant table, the Phase 5 loss table and the radar plant table, and writes two
committed files under ``site/data/assets/``:

- ``plants.json``: one compact numeric record per plant, the map measures with their class breaks
  (so the legend, the map and the reports use the same ranges), totals and data periods;
- ``plants_detail.json``: per plant, the report circle, the reports inside it, the array outline
  and the plant's damage curve as values (curves are never computed in the browser).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow.parquet as pq

from crc_lab.assets import exposure, solar
from crc_lab.curves import annual_maxima as am_mod
from crc_lab.impacts import hail_curves as hc
from crc_lab.impacts.build import curve_arguments, plant_parameters
from lab_common.texas import write_json_atomic

NICE = (1.0, 1.5, 2.0, 3.0, 5.0, 7.0)
CURVE_GRID_MM = [float(x) for x in np.arange(0.0, 112.5, 2.5)]
OUTLINE_TOLERANCE_DEG = 0.0004  # about 40 m
FACTOR_WARNING = 5.0
# Fields of the plant GeoJSON (Phases 4 and 5) carried into the collapsed detail groups
MORE = (
    "capacity_MW_DC", "first_online", "balancing_authority", "mounting", "module", "bifacial",
    "polygon", "plant_area_km2", "location_source", "value_basis",
    "hail_reports_per_100km2_per_year", "hail_size_median_mm", "hail_size_p90_mm",
    "hail_size_largest_mm", "hail_hit_area_km2", "hail_flag", "reporting_rate_fitted",
    "annual_chance_hail_1in_or_more", "annual_chance_hail_1in_or_more_bias_corrected",
    "radar_hail_days_30mm_or_more_over_plant", "radar_hail_days_50mm_or_more_over_plant",
    "gust_return_levels_ms", "loss_damage_ratio_if_2in_hail",
    "loss_damage_ratio_exceeded_1_in_100", "loss_damage_ratio_exceeded_1_in_100_bias_corrected",
)  # fmt: skip

# id, label, unit, multiplier to the display unit, fields per basis
# (reports as they are, bias-corrected per cell, bias-corrected per region)
MEASURES: list[dict[str, Any]] = [
    {
        "id": "loss_ratio",
        "label": "Expected hail loss, share of plant value",
        "unit": "% per year",
        "scale": 100.0,
        "fields": ["loss_ratio", "loss_ratio_c", "loss_ratio_r"],
    },
    {
        "id": "loss_usd",
        "label": "Expected hail loss",
        "unit": "$ million per year",
        "scale": 1e-6,
        "fields": ["loss_usd", "loss_usd_c", "loss_usd_r"],
    },
    {
        "id": "p2in",
        "label": "Annual chance of hail of 2 inches or more",
        "unit": "% per year",
        "scale": 100.0,
        "fields": ["p2in", "p2in_c", "p2in_r"],
    },
    {
        "id": "radar_days",
        "label": "Radar hail days, 30 mm or more, 25 km mean",
        "unit": "days per year",
        "scale": 1.0,
        "fields": ["radar_days", "radar_days", "radar_days"],
    },
]


def rnd(value: float | None, digits: int) -> float | None:
    return None if value is None else (round(value) if digits == 0 else round(value, digits))


def nice(value: float) -> float:
    """The nearest of 1, 1.5, 2, 3, 5, 7 times a power of ten."""
    if value <= 0:
        return 0.0
    exponent = math.floor(math.log10(value))
    candidates = [m * 10.0**e for e in (exponent, exponent + 1) for m in NICE]
    best = min(candidates, key=lambda c: abs(math.log(c / value)))
    return float(f"{best:.6g}")


def class_breaks(values: list[float], classes: int = 5) -> list[float]:
    """Rounded quantile breaks: up to ``classes - 1`` increasing round numbers inside the data."""
    data = np.asarray([v for v in values if v is not None and math.isfinite(v)], dtype=float)
    positive = data[data > 0]
    if positive.size == 0:
        return []
    quantiles = np.quantile(positive, [i / classes for i in range(1, classes)])
    breaks: list[float] = []
    for q in quantiles:
        b = nice(float(q))
        if (not breaks or b > breaks[-1]) and positive.min() < b < positive.max():
            breaks.append(b)
    return breaks


def outline(wkbs: list[bytes]) -> list[list[list[float]]]:
    """Exterior rings of the plant's array polygons, simplified, as [lon, lat] lists."""
    import shapely

    rings: list[list[list[float]]] = []
    for wkb in wkbs:
        geometry = shapely.simplify(shapely.from_wkb(wkb), OUTLINE_TOLERANCE_DEG)
        parts = getattr(geometry, "geoms", [geometry])
        for part in parts:
            if part.geom_type == "Polygon" and not part.is_empty:
                rings.append([[round(x, 5), round(y, 5)] for x, y in part.exterior.coords])
    return rings


def build(
    cache: Path, events: Path, assets: Path, site: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = pq.read_table(assets / "solar_tx.parquet").to_pylist()
    loss = {
        r["asset_id"]: r for r in pq.read_table(assets / "solar_tx_hail_loss.parquet").to_pylist()
    }
    radar_table = pq.read_table(assets / "radar_plants.parquet")
    radar = {r["asset_id"]: r for r in radar_table.to_pylist()}
    window = am_mod.Window(
        am_mod.FIRST_FULL_YEAR, am_mod.last_complete_year(str(events), duckdb.connect())
    )
    reports = exposure.load_reports(
        str(events), window.start, window.end, events.parent / "hail_neighbours.parquet"
    )
    region = exposure.reporting_region(cache / "cb_2024_us_state_500k.zip")
    rule = exposure.Rule()
    polygons = {
        r["asset_id"]: r["geometry_wkb"]
        for r in solar.load(cache, solar.fetch(cache))
        .select(["asset_id", "geometry_wkb"])
        .to_pylist()
    }

    geojson = site / "solar_tx.geojson"
    props = (
        {
            f["properties"]["asset_id"]: f["properties"]
            for f in json.loads(geojson.read_text())["features"]
        }
        if geojson.exists()
        else {}
    )
    compare_path = site.parent / "hail_compare" / "cells.json"
    compare = json.loads(compare_path.read_text()) if compare_path.exists() else None
    cell_index = {c: i for i, c in enumerate(compare["cells"])} if compare else {}

    def hail_days(lat: float, lon: float) -> dict[str, Any] | None:
        """Hail days per year in the plant's cell from the four records of the comparison layer."""
        import h3

        i = (
            cell_index.get(h3.latlng_to_cell(lat, lon, compare["h3_resolution"]))
            if compare
            else None
        )
        if i is None:
            return None
        return {
            k: {"title": s["title"], "period": s["period"], "value": s["values"][i]}
            for k, s in compare["sources"].items()
        }

    plants: list[dict[str, Any]] = []
    detail: dict[str, Any] = {}
    for r in rows:
        o, rad = loss[r["asset_id"]], radar.get(r["asset_id"], {})
        params = plant_parameters(r)
        ratio_c = o["expected_annual_damage_ratio_corrected"]
        factor = (
            ratio_c / o["expected_annual_damage_ratio"]
            if ratio_c and o["expected_annual_damage_ratio"]
            else None
        )
        plants.append(
            {
                "id": r["asset_id"],
                "name": r["name"],
                "county": r["county"],
                "lon": round(r["longitude"], 5),
                "lat": round(r["latitude"], 5),
                "mw": r["capacity_ac_mw"],
                "year": r["year"],
                "mount": "tracker" if params["tracker"] else "fixed tilt",
                "glass": params["glass_class"],
                "value": round(r["value_usd"]),
                "loss_ratio": round(o["expected_annual_damage_ratio"], 6),
                "loss_ratio_c": None if ratio_c is None else round(ratio_c, 6),
                "loss_usd": round(o["expected_annual_loss_usd"]),
                "loss_usd_c": None
                if ratio_c is None
                else round(o["expected_annual_loss_usd_corrected"]),
                "loss_ratio_r": rnd(o["expected_annual_damage_ratio_regional"], 6),
                "loss_usd_r": rnd(o["expected_annual_loss_usd_regional"], 0),
                "p2in_r": rnd(o["annual_prob_ge_2in_regional"], 5),
                "region": o["region"],
                "thin_film": bool(r["thin_film_cdte"])
                or "thin-film" in (r["uspvdb_module_tech"] or ""),
                "factor": None if factor is None else round(factor, 2),
                "factor_warning": bool(factor is not None and factor > FACTOR_WARNING),
                "p2in": r["hail_annual_prob_ge_2in"],
                "p2in_c": r["hail_annual_prob_ge_2in_corrected"],
                "radar_days": None if not rad else round(rad["radar_local_rate_ge_30mm"], 3),
                "radar_max_mm": None
                if not rad or not rad["radar_max_mm"]
                else round(rad["radar_max_mm"]),
                "radar_max_day": rad.get("radar_max_day"),
                "radius_km": r["hail_radius_km"],
                "reports": o["reports_in_circle"],
                "polygon": bool(r["has_polygon"]),
            }
        )
        sizes, radius, _, fraction = exposure.local_reports(
            r["longitude"], r["latitude"], reports, rule, region=region
        )
        inside = exposure.distances_km(r["longitude"], r["latitude"], reports) <= radius
        ids = (r["uspvdb_ids"] or "").split(",")
        detail[r["asset_id"]] = {
            "circle": {
                "radius_km": round(radius, 2),
                "share_inside_region": round(fraction, 3),
                "reports": len(sizes),
            },
            "reports": [
                [round(float(x), 3), round(float(y), 3), round(float(s), 1)]
                for x, y, s in zip(
                    reports.lon[inside], reports.lat[inside], reports.size_mm[inside], strict=True
                )
            ],
            "outline": outline([polygons[i.strip()] for i in ids if i.strip() in polygons]),
            "curve": {
                "d_mm": CURVE_GRID_MM,
                "damage_ratio": [
                    round(float(v), 5)
                    for v in hc.pv_plant_hail(CURVE_GRID_MM, **curve_arguments(params))
                ],
            },
            "hail_days": hail_days(r["latitude"], r["longitude"]),
            "more": {k: props.get(r["asset_id"], {}).get(k) for k in MORE},
            "region": {
                "id": o["region"],
                "cells": o["region_cells"],
                "reports": o["region_reports"],
                "mean_reporting_rate": rnd(o["region_mean_reporting_rate"], 3),
                "rate_per_100km2_year": rnd(o["region_rate_per_100km2_year"], 4),
            },
            "stow_basis": params["stow_basis"],
            "notes": params["notes"],
        }

    measures = []
    for m in MEASURES:
        values = [p[f] * m["scale"] for p in plants for f in set(m["fields"]) if p[f] is not None]
        measures.append(
            m | {"breaks": class_breaks(values), "has_basis": m["fields"][0] != m["fields"][1]}
        )
    radar_meta = json.loads((radar_table.schema.metadata or {}).get(b"crc_lab.radar", b"{}"))
    radar_period = "–".join(
        dict.fromkeys(str(radar_meta[k])[:4] for k in ("first_day", "last_day") if k in radar_meta)
    )
    payload = {
        "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "periods": {"reports": f"{window.start}–{window.end}", "radar": radar_period},
        "rule": exposure.rule_dict(rule),
        "curve_defaults": hc.load()["curves"]["pv_plant_hail_v0"]["defaults"],
        "factor_warning_above": FACTOR_WARNING,
        "measures": measures,
        "totals": {
            "plants": len(plants),
            "mw": round(sum(p["mw"] for p in plants)),
            "value": sum(p["value"] for p in plants),
            "loss_usd": sum(p["loss_usd"] for p in plants),
            "loss_usd_c": sum(p["loss_usd_c"] or 0 for p in plants),
            "loss_usd_r": sum(p["loss_usd_r"] or 0 for p in plants),
        },
        "plants": plants,
    }
    return payload, detail


STOW_TILTS_DEG = (45, 50, 52, 55, 60, 65, 70, 75)
STOW_CHANCES = (0.0, 0.25, 0.5, 0.8, 0.95, 1.0)


def curves_payload() -> dict[str, Any]:
    """The four v0 curves as values for the Methods tab; the solar curve on a grid of stow settings.

    The page picks among these with its sliders; it never computes a curve.
    """
    doc = hc.load()
    pv = doc["curves"]["pv_plant_hail_v0"]
    grid = CURVE_GRID_MM

    def values(function: Any, **kwargs: Any) -> list[float]:
        return [float(f"{v:.6g}") for v in function(grid, **kwargs)]

    solar = {
        glass: {
            f"{tilt}|{chance:g}": values(
                hc.pv_plant_hail, glass_class=glass, stow_tilt_deg=tilt, p_stow=chance
            )
            for tilt in STOW_TILTS_DEG
            for chance in STOW_CHANCES
        }
        for glass in pv["break_probability"]
    }
    return {
        "schema": doc["schema"],
        "as_of": doc["as_of"],
        "d_mm": grid,
        "solar": {
            "meta": hc.metadata("pv_plant_hail_v0"),
            "defaults": pv["defaults"],
            "stow_tilts_deg": list(STOW_TILTS_DEG),
            "stow_chances": list(STOW_CHANCES),
            "break_probability_knots": pv["break_probability"],
            "plant": solar,
        },
        "buildings": {
            "swiss": {
                "meta": hc.metadata("bld_hail_swiss_v0"),
                "damage_ratio": values(hc.bld_hail_swiss),
            },
            "roof": {
                "meta": hc.metadata("bld_hail_roof_v0"),
                "defaults": doc["curves"]["bld_hail_roof_v0"]["defaults"],
                "asphalt_laminated": values(hc.bld_hail_roof, roof_class="asphalt_laminated"),
                "asphalt_3tab": values(hc.bld_hail_roof, roof_class="asphalt_3tab"),
            },
        },
        "cars": {
            "swiss": {
                "meta": hc.metadata("car_hail_swiss_v0"),
                "damage_ratio": values(hc.car_hail_swiss),
            }
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--events", type=Path, default=Path("data/storm-events/events.parquet"))
    parser.add_argument("--assets", type=Path, default=Path("data/assets"))
    parser.add_argument("--site", type=Path, default=Path("site/data/assets"))
    args = parser.parse_args(argv)
    payload, detail = build(args.cache, args.events, args.assets, args.site)
    write_json_atomic(args.site / "plants.json", payload)
    write_json_atomic(args.site / "plants_detail.json", detail)
    write_json_atomic(args.site / "curves.json", curves_payload())
    for m in payload["measures"]:
        print(f"{m['id']}: breaks {m['breaks']} {m['unit']}")
    sizes = [(args.site / n).stat().st_size // 1024 for n in ("plants.json", "plants_detail.json")]
    print(f"{len(payload['plants'])} plants; plants.json {sizes[0]} KB, detail {sizes[1]} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
