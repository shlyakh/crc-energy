# ruff: noqa: E501
"""``python -m crc_lab.assets.build``: solar asset table, value, hail exposure, return levels, explorer file."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from crc_lab import PINNED
from crc_lab.assets import eia, exposure, solar, value
from crc_lab.curves import annual_maxima as am_mod
from crc_lab.curves import fit
from crc_lab.curves.sensitivity import CITIES
from crc_lab.explorer.texas import texas_boundary, write_json_atomic

RETURN_PERIODS = (2, 5, 10, 20, 50, 100)
SENSITIVITY_RULES = [
    exposure.Rule(n_target=30),
    exposure.Rule(),
    exposure.Rule(n_target=300),
    exposure.Rule(min_radius_km=0.0),
    exposure.Rule(min_radius_km=25.0),
    exposure.Rule(footprint_km2=20.0),
    exposure.Rule(footprint_km2=50.0),
    exposure.Rule(footprint_km2=100.0),
]


def mounting(r: dict[str, Any]) -> str | None:
    if r["single_axis"]:
        return "single-axis"
    if r["dual_axis"]:
        return "dual-axis"
    if r["fixed_tilt"]:
        return "fixed-tilt"
    return r["uspvdb_axis"]


def module(r: dict[str, Any]) -> str | None:
    if r["crystalline_silicon"]:
        return "crystalline silicon"
    if r["thin_film_cdte"]:
        return "thin-film CdTe"
    return r["uspvdb_module_tech"]


def return_levels(assets: pa.Table, curves_dir: Path) -> dict[str, dict[str, list[float | None]]]:
    """C4: hail and gust return levels at each plant from the Phase 3 curves (``for_assets``)."""
    points = [
        {"name": a, "lon": lo, "lat": la}
        for a, lo, la in zip(
            assets["asset_id"].to_pylist(),
            assets["longitude"].to_pylist(),
            assets["latitude"].to_pylist(),
            strict=True,
        )
    ]
    out: dict[str, dict[str, list[float | None]]] = {}
    for hazard in fit.HAZARDS:
        path = curves_dir / f"{hazard}.parquet"
        if not path.exists():
            continue
        for row in fit.evaluate_points(path, points, return_periods=RETURN_PERIODS):
            out.setdefault(row["asset_id"], {})[hazard] = [
                row[f"value_rp{t}"] for t in RETURN_PERIODS
            ]
    return out


def sensitivity(
    assets: list[dict[str, Any]], reports: exposure.Reports, region: object
) -> dict[str, Any]:
    """Each rule at the ten cities and summarised over the plants."""
    results: dict[str, Any] = {"rules": [], "cities": CITIES}
    for rule in SENSITIVITY_RULES:
        plants = [
            exposure.at_point(
                a["longitude"],
                a["latitude"],
                reports,
                rule,
                region=region,
                plant_area_km2=(a["area_m2"] or 0) / 1e6,
            )
            for a in assets
        ]
        cities = {
            c["name"]: exposure.at_point(c["lon"], c["lat"], reports, rule, region=region)
            for c in CITIES
        }
        radius = [p["radius_km"] for p in plants]
        rate = [p["report_rate_per_100km2_year"] for p in plants]
        prob = [p["annual_prob_ge_2in"] for p in plants]
        results["rules"].append(
            {
                "rule": exposure.rule_dict(rule),
                "plants": {
                    "n": len(plants),
                    "too_few_reports": sum(1 for p in plants if p["flag"] != "ok"),
                    "radius_km_median": statistics.median(radius),
                    "radius_km_p10_p90": [
                        statistics.quantiles(radius, n=10)[0],
                        statistics.quantiles(radius, n=10)[8],
                    ],
                    "rate_per_100km2_year_median": statistics.median(rate),
                    "rate_per_100km2_year_p10_p90": [
                        statistics.quantiles(rate, n=10)[0],
                        statistics.quantiles(rate, n=10)[8],
                    ],
                    "annual_prob_ge_2in_median": statistics.median(prob),
                    "annual_prob_ge_2in_p10_p90": [
                        statistics.quantiles(prob, n=10)[0],
                        statistics.quantiles(prob, n=10)[8],
                    ],
                },
                "cities": {
                    k: {
                        x: v[x]
                        for x in (
                            "radius_km",
                            "reports_in_radius",
                            "report_rate_per_100km2_year",
                            "annual_prob_ge_1in",
                            "annual_prob_ge_2in",
                            "flag",
                        )
                    }
                    for k, v in cities.items()
                },
            }
        )
    return results


def sensitivity_markdown(results: dict[str, Any], window: am_mod.Window, n_reports: int) -> str:
    lines = [
        "# Phase 4 note: sensitivity of hail at the asset (local report density)",
        "",
        f"Located hail reports {window.start}–{window.end}: {n_reports:,}. Rule: grow a circle until it holds N reports, "
        "with a minimum and maximum radius; rate = reports / (area × years); annual chance at the point = "
        "1 − exp(−rate × footprint). **The footprint (area hit per report) is a placeholder with no source.** "
        "Every number is computed by `just assets-sensitivity`.",
        "",
        "## Across the Texas solar plants",
        "",
        "| Rule (N, min–max radius km, footprint km²) | Too few reports | Radius km, median (p10–p90) | Reports per 100 km² per year, median (p10–p90) | Annual chance of ≥ 2 in hail, median (p10–p90) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in results["rules"]:
        rule, p = r["rule"], r["plants"]
        name = (
            f"{rule['n_target']}, {rule['min_radius_km']:g}–{rule['max_radius_km']:g}, {rule['footprint_km2']:g}"
            + (" (default)" if rule["label"] == exposure.Rule().label else "")
        )
        lines.append(
            f"| {name} | {p['too_few_reports']} of {p['n']} | {p['radius_km_median']:.1f} ({p['radius_km_p10_p90'][0]:.1f}–{p['radius_km_p10_p90'][1]:.1f}) | "
            f"{p['rate_per_100km2_year_median']:.3f} ({p['rate_per_100km2_year_p10_p90'][0]:.3f}–{p['rate_per_100km2_year_p10_p90'][1]:.3f}) | "
            f"{p['annual_prob_ge_2in_median']:.4f} ({p['annual_prob_ge_2in_p10_p90'][0]:.4f}–{p['annual_prob_ge_2in_p10_p90'][1]:.4f}) |"
        )
    lines += ["", "## At ten city centres: reports per 100 km² per year (radius km)", ""]
    labels = [r["rule"]["label"] for r in results["rules"]]
    lines += [
        "| City | " + " | ".join(labels) + " |",
        "| --- | " + " | ".join("---" for _ in labels) + " |",
    ]
    for city in results["cities"]:
        cells = [
            f"{r['cities'][city['name']]['report_rate_per_100km2_year']:.2f} ({r['cities'][city['name']]['radius_km']:.0f})"
            for r in results["rules"]
        ]
        lines.append(f"| {city['name']} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Reading",
        "",
        "- With no minimum radius, city centres reach N inside a few kilometres and the rate measures where people live. "
        "The minimum radius pulls city rates down; it barely moves rural plants, whose circles are already wide.",
        "- N trades noise for locality: 30 reports keep the circle small, 300 widen it and smooth the rate.",
        "- The footprint scales the annual chance almost linearly while chances are small. It is the least known number here.",
        "- Rates still follow reporting density. Compare neighbouring plants, not a remote plant with a suburban one.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--events", type=Path, default=Path("data/storm-events/events.parquet"))
    parser.add_argument("--curves", type=Path, default=Path("data/curves"))
    parser.add_argument("--out", type=Path, default=Path("data/assets"))
    parser.add_argument("--site", type=Path, default=Path("site/data/assets"))
    parser.add_argument("--sensitivity", action="store_true")
    parser.add_argument(
        "--note", type=Path, default=Path("docs/reports/4-hail-exposure-sensitivity.md")
    )
    args = parser.parse_args(argv)
    started = time.time()

    manifest = solar.fetch(args.cache)
    uspvdb = solar.load(args.cache, manifest)
    eia_manifest = eia.fetch(args.cache)
    eia_plants = eia.plants(args.cache)
    comparison = eia.compare(eia_plants, uspvdb)
    assets, join_info = eia.join_uspvdb(eia_plants, uspvdb)
    no_location = assets.filter(pc.is_null(assets["latitude"])).num_rows
    assets = assets.filter(pc.is_valid(assets["latitude"]))
    occ, cost = value.cost_per_kw()
    assets = value.add_value(assets, occ)
    print(
        f"solar: {assets.num_rows} Texas plants from EIA ({eia_manifest['generators']['report_date']}), {no_location} dropped without coordinates; OCC {occ} $/kW ({cost['cost_year']})"
    )

    window = am_mod.Window(
        am_mod.FIRST_FULL_YEAR, am_mod.last_complete_year(str(args.events), duckdb.connect())
    )
    neighbours = args.events.parent / "hail_neighbours.parquet"
    if not neighbours.exists():
        from crc_lab.storm_events.plan import StormEventsPlan

        plan = StormEventsPlan(args.cache, mode="offline")
        details = {y: path for (kind, y), path in plan.paths().items() if kind == "details"}
        counts = exposure.build_neighbour_hail(details, neighbours, window.start, window.end)
        print(f"neighbour hail reports: {counts}")
    reports = exposure.load_reports(str(args.events), window.start, window.end, neighbours)
    rule = exposure.Rule()
    rows = assets.to_pylist()
    texas_boundary(args.cache)  # ensures the Census state file is cached
    region = exposure.reporting_region(args.cache / "cb_2024_us_state_500k.zip")
    hail = [
        exposure.at_point(
            r["longitude"],
            r["latitude"],
            reports,
            rule,
            region=region,
            plant_area_km2=(r["area_m2"] or 0) / 1e6,
        )
        for r in rows
    ]
    levels = return_levels(assets, args.curves)

    flat = {
        "hail_radius_km": [h["radius_km"] for h in hail],
        "hail_reports_in_radius": [h["reports_in_radius"] for h in hail],
        "hail_circle_share_in_region": [h["circle_share_inside_region"] for h in hail],
        "hail_hit_area_km2": [h["hit_area_km2"] for h in hail],
        "hail_flag": [h["flag"] for h in hail],
        "hail_report_rate_per_100km2_year": [h["report_rate_per_100km2_year"] for h in hail],
        "hail_size_median_mm": [h["size_median_mm"] for h in hail],
        "hail_size_p90_mm": [h["size_p90_mm"] for h in hail],
        "hail_size_max_mm": [h["size_max_mm"] for h in hail],
        "hail_annual_prob_ge_1in": [h["annual_prob_ge_1in"] for h in hail],
        "hail_annual_prob_ge_2in": [h["annual_prob_ge_2in"] for h in hail],
    }
    table = assets
    for name, values in flat.items():
        table = table.append_column(name, pa.array(values))
    args.out.mkdir(parents=True, exist_ok=True)
    card = {
        "name": "Texas utility-scale solar plants with replacement value and local hail exposure",
        "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "versions": {name: version(name) for name in PINNED},
        "assets": {
            "plant_list": {"source": eia.CITATION, "licence": eia.LICENCE} | eia_manifest,
            "polygons": {"source": solar.CITATION, "licence": solar.LICENCE}
            | {
                k: manifest[k]
                for k in ("url", "sha256", "release_file", "last_modified", "retrieved_at")
            },
            "join": join_info
            | {
                "with_polygon": sum(1 for r in rows if r["has_polygon"]),
                "area_estimated_from_capacity": sum(1 for r in rows if not r["has_polygon"]),
                "dropped_without_coordinates": no_location,
            },
            "comparison": comparison,
        },
        "value": cost
        | {
            "rule": "value_usd = capacity_ac_mw x 1000 x occ_usd_per_kw; replacement cost today, the same cost year for every plant"
        },
        "hail_exposure": exposure.rule_dict(rule)
        | {
            "window": [window.start, window.end],
            "located_reports": int(len(reports.lon)),
            "region": "Texas, Oklahoma, New Mexico, Arkansas, Louisiana",
            "source": "NOAA NCEI Storm Events, cleaned by crc-lab (Phase 2); neighbouring states from the same snapshot",
        },
        "return_levels": "hail (mm) and gust (m/s) at the plant centroid from the Phase 3 curves via for_assets; return periods "
        + ", ".join(map(str, RETURN_PERIODS)),
        "counts": {
            "plants": assets.num_rows,
            "capacity_ac_mw": round(sum(r["capacity_ac_mw"] or 0 for r in rows), 1),
            "value_usd": round(sum(r["value_usd"] or 0 for r in rows)),
            "too_few_reports": sum(1 for h in hail if h["flag"] != "ok"),
        },
        "known_limits": [
            "Report-based hail: rates follow where people report. A minimum radius limits, but does not remove, that bias.",
            "The footprint that turns a report rate into a chance at the plant is a placeholder with no source.",
            "Value is a national benchmark cost per kW AC times capacity, not the plant's own cost or insured value.",
            "The circle counts reports in Texas and its four neighbouring states and is clipped to them: there are no reports from Mexico or the Gulf.",
            "Plants are EIA plants; most 2025-2026 plants have no polygon yet, so their area is estimated from capacity.",
            "A plant is a disc of its USPVDB array area; the chance of a hit uses a disc of footprint plus plant radius.",
        ],
    }
    pq.write_table(
        table.replace_schema_metadata({b"crc_lab.assets.card": json.dumps(card).encode()}),
        args.out / "solar_tx.parquet",
        compression="zstd",
    )
    fit.write_json(args.out / "solar_tx.card.json", card)

    features = []
    for r, h in zip(rows, hail, strict=True):
        lv = levels.get(r["asset_id"], {})
        props = {
            "label": f"{r['name']} ({r['county']} County)",
            "asset_id": r["asset_id"],
            "capacity_MW_AC": r["capacity_ac_mw"],
            "capacity_MW_DC": r["capacity_dc_mw"],
            "first_online": str(r["first_operating_date"])[:7]
            if r["first_operating_date"]
            else None,
            "balancing_authority": r["balancing_authority"],
            "mounting": mounting(r),
            "module": module(r),
            "bifacial": r["bifacial"],
            "polygon": "USPVDB" if r["has_polygon"] else "none yet (area estimated from capacity)",
            "replacement_value": f"${r['value_usd'] / 1e6:,.1f} million"
            if r["value_usd"] is not None
            else None,
            "value_basis": f"NREL ATB 2025 overnight capital cost {occ:,.0f} $/kW AC ({cost['cost_year']}) x capacity",
            "hail_reports_used": h["reports_in_radius"],
            "hail_radius_km": h["radius_km"],
            "hail_circle_share_inside_reporting_region": h["circle_share_inside_region"],
            "plant_area_km2": h["plant_area_km2"],
            "hail_hit_area_km2": h["hit_area_km2"],
            "hail_flag": h["flag"],
            "hail_reports_per_100km2_per_year": h["report_rate_per_100km2_year"],
            "hail_size_median_mm": h["size_median_mm"],
            "hail_size_p90_mm": h["size_p90_mm"],
            "hail_size_largest_mm": h["size_max_mm"],
            "annual_chance_hail_1in_or_more": h["annual_prob_ge_1in"],
            "annual_chance_hail_2in_or_more": h["annual_prob_ge_2in"],
            "footprint_km2_placeholder": h["footprint_km2_placeholder"],
            "gust_return_levels_ms": ", ".join(
                f"1 in {t}: {v:.1f}"
                for t, v in zip(RETURN_PERIODS, lv.get(fit.GUST, []), strict=False)
                if v is not None
            )
            or None,
        }
        if lv.get(fit.HAIL):
            props["curve"] = {
                "return_periods": list(RETURN_PERIODS),
                "values": lv[fit.HAIL],
                "unit": "mm",
                "note": "Largest reported hail of the year in the plant's cell, pooled with neighbours; a regional curve, not the plant's own.",
            }
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [r["longitude"], r["latitude"]]},
                "properties": props,
            }
        )
    write_json_atomic(
        args.site / "solar_tx.geojson", {"type": "FeatureCollection", "features": features}
    )
    write_json_atomic(args.site / "manifest.json", card)
    print(f"plants: {card['counts']}")

    if args.sensitivity:
        results = sensitivity(rows, reports, region)
        fit.write_json(args.out / "hail-exposure-sensitivity.json", results)
        args.note.write_text(sensitivity_markdown(results, window, len(reports.lon)))
        print(f"sensitivity: {len(results['rules'])} rules -> {args.note}")
    print(f"{time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
