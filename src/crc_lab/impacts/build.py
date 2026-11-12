# ruff: noqa: E501
"""``python -m crc_lab.impacts.build``: hail loss per Texas solar plant from the v0 curves (Phase 5).

Reads the Phase 4 plant table and the hail reports, applies ``pv_plant_hail_v0`` to every report
in each plant's circle, and writes the loss table, its card, the explorer fields and the report.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from crc_lab import PINNED
from crc_lab.assets import exposure, regional
from crc_lab.assets.build import mounting, reporting_rates
from crc_lab.curves import annual_maxima as am_mod
from crc_lab.curves import fit
from crc_lab.curves.sensitivity import CITIES
from crc_lab.impacts import annual, crc_adapter
from crc_lab.impacts import hail_curves as hc
from lab_common.texas import write_json_atomic

GLASS_GLASS_FROM_YEAR = (
    2021  # spec: 2.0 mm glass-glass "for tracker plants built from about 2021" [I]
)
# Footprints measured on MRMS radar swaths of 30 mm or more in Texas (docs/reports/4-radar-hail.md)
FOOTPRINT_VARIANTS_KM2 = (16.0, 61.0)


def plant_parameters(r: dict[str, Any]) -> dict[str, Any]:
    """Curve arguments for one plant, with the reason for each in words."""
    defaults = hc.load()["curves"]["pv_plant_hail_v0"]["defaults"]
    mount = mounting(r)
    year = r["year"]
    glass = (
        "glass_glass_2.0"
        if year is not None and year >= GLASS_GLASS_FROM_YEAR
        else "glass_backsheet_3.2"
    )
    thin_film = bool(r["thin_film_cdte"]) or "thin-film" in (r["uspvdb_module_tech"] or "")
    notes = []
    if thin_film:
        notes.append("thin-film modules: the spec has no table for them; the year rule is used")
    if mount == "fixed-tilt":
        tilt = r["tilt_deg"]
        if tilt is None:
            tilt, basis = 0.0, "fixed tilt, angle not reported: taken as flat"
        else:
            basis = f"fixed tilt {tilt:g} degrees, always at that angle"
        return {
            "glass_class": glass,
            "stow_tilt_deg": float(tilt),
            "p_stow": 1.0,
            "tracker": False,
            "stow_basis": basis,
            "notes": notes,
        }
    if mount is None:
        notes.append("mounting not reported: treated as a tracker")
    return {
        "glass_class": glass,
        "stow_tilt_deg": float(defaults["stow_tilt_deg"]),
        "p_stow": float(defaults["p_stow"]),
        "tracker": True,
        "stow_basis": f"tracker, stows to {defaults['stow_tilt_deg']:g} degrees with chance {defaults['p_stow']:g} (placeholders)",
        "notes": notes,
    }


def curve_arguments(
    params: dict[str, Any], override: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Arguments for ``pv_plant_hail``; stow overrides apply to trackers only."""
    args = {k: params[k] for k in ("glass_class", "stow_tilt_deg", "p_stow")}
    for key, value in (override or {}).items():
        if key in ("stow_tilt_deg", "p_stow") and not params["tracker"]:
            continue
        if key != "footprint_km2":
            args[key] = value
    return args


VARIANTS: list[tuple[str, dict[str, Any]]] = [
    ("Defaults", {}),
    ("Trackers never stow (p_stow 0)", {"p_stow": 0.0}),
    ("Trackers stow half the time (p_stow 0.5)", {"p_stow": 0.5}),
    ("Trackers stow 95% of the time", {"p_stow": 0.95}),
    ("Stow angle 50 degrees", {"stow_tilt_deg": 50.0}),
    ("Stow angle 75 degrees", {"stow_tilt_deg": 75.0}),
    ("Module cost share 0.30", {"module_cost_share": 0.30}),
    ("Module cost share 0.50", {"module_cost_share": 0.50}),
    ("Every plant 2.0 mm glass-glass", {"glass_class": "glass_glass_2.0"}),
    ("Every plant 3.2 mm glass and backsheet", {"glass_class": "glass_backsheet_3.2"}),
    *[(f"Footprint {a:g} km² per report", {"footprint_km2": a}) for a in FOOTPRINT_VARIANTS_KM2],
]


def money(v: float) -> str:
    return f"${v / 1e6:,.2f} million" if abs(v) >= 1e6 else f"${v:,.0f}"


def pct(v: float | None, digits: int = 3) -> str:
    return "n/a" if v is None else f"{100 * v:.{digits}f}%"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--events", type=Path, default=Path("data/storm-events/events.parquet"))
    parser.add_argument("--assets", type=Path, default=Path("data/assets"))
    parser.add_argument("--site", type=Path, default=Path("site/data/assets/solar_tx.geojson"))
    parser.add_argument("--report", type=Path, default=Path("docs/reports/5-hail-impact.md"))
    args = parser.parse_args(argv)
    started = time.time()

    rows = pq.read_table(args.assets / "solar_tx.parquet").to_pylist()
    radar_path = args.assets / "radar_plants.parquet"
    radar = (
        {r["asset_id"]: r for r in pq.read_table(radar_path).to_pylist()}
        if radar_path.exists()
        else {}
    )
    window = am_mod.Window(
        am_mod.FIRST_FULL_YEAR, am_mod.last_complete_year(str(args.events), duckdb.connect())
    )
    reports = exposure.load_reports(
        str(args.events), window.start, window.end, args.events.parent / "hail_neighbours.parquet"
    )
    region = exposure.reporting_region(args.cache / "cb_2024_us_state_500k.zip")
    rule = exposure.Rule()
    pv = hc.load()["curves"]["pv_plant_hail_v0"]
    share_default = pv["defaults"]["module_cost_share"]

    out: list[dict[str, Any]] = []
    local: list[
        dict[str, Any]
    ] = []  # per plant: sizes and the rate per km2, for the sensitivity runs
    bias_path = args.assets / "reporting_bias.parquet"
    regions = regional.build(bias_path, reports) if bias_path.exists() else None
    for r in rows:
        sizes, radius, _, fraction = exposure.local_reports(
            r["longitude"], r["latitude"], reports, rule, region=region
        )
        area = math.pi * radius**2 * fraction
        per_km2_year = len(sizes) / (area * reports.years)
        plant_area = (r["area_m2"] or 0) / 1e6
        touch_rate = per_km2_year * exposure.hit_area_km2(rule.footprint_km2, plant_area)
        params = plant_parameters(r)
        ratio = hc.pv_plant_hail(sizes, **curve_arguments(params))
        damage = np.outer(ratio, annual.covered_shares(plant_area, rule.footprint_km2)).ravel()
        rr = r["hail_reporting_rate"]
        plain = annual.annual_loss(touch_rate, damage)
        fixed = annual.annual_loss(touch_rate / rr, damage) if rr else None
        value = r["value_usd"]
        # regional variant: the region's corrected rate and its pooled report sizes, no circle
        reg = regions.at(r["longitude"], r["latitude"]) if regions else None
        wide = None
        if reg is not None and reg.reports:
            ratio_r = hc.pv_plant_hail(reg.sizes_mm, **curve_arguments(params))
            shares = annual.covered_shares(plant_area, rule.footprint_km2)
            wide = annual.annual_loss(
                reg.rate_per_km2_year * exposure.hit_area_km2(rule.footprint_km2, plant_area),
                np.outer(ratio_r, shares).ravel(),
            )
            hit = exposure.hit_area_km2(rule.footprint_km2, plant_area)
            rate_2in = reg.rate_per_km2_year * float((reg.sizes_mm >= 50.8).mean())
            p2in_regional = 1 - math.exp(-rate_2in * hit)
        local.append(
            {
                "sizes": sizes,
                "per_km2_year": per_km2_year,
                "params": params,
                "value": value,
                "rr": rr,
            }
        )
        out.append(
            {
                "asset_id": r["asset_id"],
                "glass_class": params["glass_class"],
                "stow_tilt_deg": params["stow_tilt_deg"],
                "p_stow": params["p_stow"],
                "stow_basis": params["stow_basis"],
                "assumption_notes": "; ".join(params["notes"]) or None,
                "module_cost_share": share_default,
                "damage_ratio_at_2in": float(hc.pv_plant_hail(50.8, **curve_arguments(params))),
                "reports_in_circle": len(sizes),
                "reports_that_damage": int((ratio > 0).sum()),
                "mean_damage_ratio_per_report": float(ratio.mean()) if len(ratio) else 0.0,
                "touching_events_per_year": touch_rate,
                "expected_annual_damage_ratio": plain.expected,
                "expected_annual_damage_ratio_uncapped": plain.expected_uncapped,
                "chance_damage_1pct_or_more": plain.chance_at_least(0.01),
                "damage_ratio_exceeded_1_in_100": plain.exceeded_with_chance(0.01),
                "expected_annual_loss_usd": plain.expected * value,
                "expected_annual_damage_ratio_corrected": fixed.expected if fixed else None,
                "expected_annual_damage_ratio_corrected_uncapped": fixed.expected_uncapped
                if fixed
                else None,
                "chance_damage_1pct_or_more_corrected": fixed.chance_at_least(0.01)
                if fixed
                else None,
                "damage_ratio_exceeded_1_in_100_corrected": fixed.exceeded_with_chance(0.01)
                if fixed
                else None,
                "expected_annual_loss_usd_corrected": fixed.expected * value if fixed else None,
                "region": reg.name if reg else None,
                "region_reports": reg.reports if reg else None,
                "region_cells": reg.cells if reg else None,
                "region_mean_reporting_rate": reg.mean_reporting_rate if reg else None,
                "region_rate_per_100km2_year": reg.rate_per_km2_year * 100 if reg else None,
                "expected_annual_damage_ratio_regional": wide.expected if wide else None,
                "damage_ratio_exceeded_1_in_100_regional": wide.exceeded_with_chance(0.01)
                if wide
                else None,
                "expected_annual_loss_usd_regional": wide.expected * value if wide else None,
                "annual_prob_ge_2in_regional": p2in_regional if wide else None,
            }
        )

    # identity check: expected damage = report rate x footprint x mean damage ratio, whatever the plant's size
    for o, loc in zip(out, local, strict=True):
        direct = loc["per_km2_year"] * rule.footprint_km2 * o["mean_damage_ratio_per_report"]
        assert math.isclose(
            o["expected_annual_damage_ratio_uncapped"], direct, rel_tol=5e-3, abs_tol=1e-9
        ), (o["asset_id"], direct)

    def portfolio(override: dict[str, Any]) -> tuple[float, float]:
        """Expected annual loss in dollars, uncorrected and bias-corrected (uncapped expectation)."""
        footprint = override.get("footprint_km2", rule.footprint_km2)
        plain = fixed = 0.0
        for loc in local:
            ratio = hc.pv_plant_hail(loc["sizes"], **curve_arguments(loc["params"], override))
            eal = (
                loc["per_km2_year"]
                * footprint
                * (float(ratio.mean()) if len(ratio) else 0.0)
                * loc["value"]
            )
            plain += eal
            fixed += eal / loc["rr"] if loc["rr"] else 0.0
        return plain, fixed

    sensitivity = [
        {"name": name, "override": override, "usd": portfolio(override)}
        for name, override in VARIANTS
    ]
    total_value = sum(r["value_usd"] for r in rows)
    total = sum(o["expected_annual_loss_usd"] for o in out)
    total_fixed = sum(o["expected_annual_loss_usd_corrected"] or 0 for o in out)
    total_regional = sum(o["expected_annual_loss_usd_regional"] or 0 for o in out)
    total_uncapped = sum(
        o["expected_annual_damage_ratio_uncapped"] * r["value_usd"]
        for o, r in zip(out, rows, strict=True)
    )
    total_fixed_uncapped = sum(
        (o["expected_annual_damage_ratio_corrected_uncapped"] or 0) * r["value_usd"]
        for o, r in zip(out, rows, strict=True)
    )

    # buildings and cars at the ten cities: a point asset, so every touching footprint covers it
    city_rows = [{"longitude": c["lon"], "latitude": c["lat"]} for c in CITIES]
    city_hail = []
    cities = []
    for c in CITIES:
        sizes, radius, _, fraction = exposure.local_reports(
            c["lon"], c["lat"], reports, rule, region=region
        )
        rate = len(sizes) / (math.pi * radius**2 * fraction * reports.years) * rule.footprint_km2
        city_hail.append({"radius_km": radius})
        cities.append(
            {
                "name": c["name"],
                "reports": len(sizes),
                "radius_km": radius,
                "footprints_per_year": rate,
                "bld_swiss": rate * float(hc.bld_hail_swiss(sizes).mean()),
                "bld_roof_laminated": rate * float(hc.bld_hail_roof(sizes).mean()),
                "bld_roof_3tab": rate
                * float(hc.bld_hail_roof(sizes, roof_class="asphalt_3tab").mean()),
                "car_swiss": rate * float(hc.car_hail_swiss(sizes).mean()),
            }
        )
    for c, rr in zip(
        cities,
        reporting_rates(args.assets / "reporting_bias.parquet", city_rows, city_hail),
        strict=True,
    ):
        c["reporting_rate"] = rr

    expressions = crc_adapter.expressions()
    card = {
        "name": "Expected annual hail loss at Texas solar plants, hail impact functions v0",
        "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "versions": {name: version(name) for name in PINNED},
        "curve": hc.metadata("pv_plant_hail_v0"),
        "parameters_file": "src/crc_lab/impacts/hail_v0.json",
        "defaults": pv["defaults"],
        "placeholders": pv["placeholders"] + ["footprint_km2"],
        "exposure": exposure.rule_dict(rule) | {"window": [window.start, window.end]},
        "rules": {
            "glass_class": f"2.0 mm glass-glass for plants first online in {GLASS_GLASS_FROM_YEAR} or later, 3.2 mm glass and backsheet before",
            "stow": "trackers and plants with no mounting reported: the spec's stow mixture; fixed tilt: the reported tilt, always",
            "events": "every located hail report in the plant's circle is one possible event; it reaches the plant with chance hit area / circle area",
            "partial_cover": "plant and footprint are discs; an event damages the covered share of the plant",
            "year": "damage ratios of a year's events are added and capped at 1",
            "bias_corrected": "the event rate divided by the fitted reporting rate around the plant (report 5); sizes unchanged",
            "bias_corrected_regional": "no circle: reports in the plant's model region (H3 resolution-3 parent) / (years x sum of reporting rate x cell area); sizes of all the region's reports",
        },
        "totals": {
            "plants": len(rows),
            "value_usd": total_value,
            "expected_annual_loss_usd": total,
            "expected_annual_loss_usd_corrected": total_fixed,
            "expected_annual_loss_usd_regional": total_regional,
        },
        "crc_expressions": {
            k: {
                x: v[x]
                for x in ("points", "exact", "max_abs_gap", "definition_hash", "monotonicity")
            }
            for k, v in expressions.items()
        },
        "known_limits": [
            "Three curve defaults (stow angle, stow chance, module cost share) and the footprint are placeholders with no source.",
            "Lab breakage rates are applied to the largest reported stone, which overstates damage to unstowed modules.",
            "Report-based hail: the rate follows where people report; the bias-corrected figure is a first model, shown beside it.",
            "A report's size is assumed over its whole footprint.",
            "Value is a benchmark cost per kW times capacity, not the plant's insured value.",
        ],
    }
    table = pa.Table.from_pylist(out)
    pq.write_table(
        table.replace_schema_metadata({b"crc_lab.impacts.card": json.dumps(card).encode()}),
        args.assets / "solar_tx_hail_loss.parquet",
        compression="zstd",
    )
    fit.write_json(args.assets / "solar_tx_hail_loss.card.json", card)
    fit.write_json(
        args.assets / "hail_v0_crc_expressions.json",
        {
            k: json.loads(v["expression"].to_json())
            | {
                "crc_lab_metadata": v["metadata"],
                "exact": v["exact"],
                "max_abs_gap": v["max_abs_gap"],
            }
            for k, v in expressions.items()
        },
    )

    if args.site.exists():
        collection = json.loads(args.site.read_text())
        by_id = {o["asset_id"]: o for o in out}
        for feature in collection["features"]:
            o = by_id.get(feature["properties"]["asset_id"])
            if not o:
                continue
            fixed_ok = o["expected_annual_damage_ratio_corrected"] is not None
            feature["properties"] |= {
                "loss_curve": "pv_plant_hail_v0 (first approximation; stow angle, stow chance, module cost share and footprint are placeholders)",
                "loss_glass_class": o["glass_class"].replace("_", " "),
                "loss_stow": o["stow_basis"],
                "loss_notes": o["assumption_notes"],
                "loss_damage_ratio_if_2in_hail": round(o["damage_ratio_at_2in"], 4),
                "loss_expected_annual_damage_ratio": round(o["expected_annual_damage_ratio"], 6),
                "loss_expected_annual": money(o["expected_annual_loss_usd"]),
                "loss_damage_ratio_exceeded_1_in_100": round(
                    o["damage_ratio_exceeded_1_in_100"], 4
                ),
                "loss_expected_annual_damage_ratio_bias_corrected": round(
                    o["expected_annual_damage_ratio_corrected"], 6
                )
                if fixed_ok
                else None,
                "loss_expected_annual_bias_corrected": money(
                    o["expected_annual_loss_usd_corrected"]
                )
                if fixed_ok
                else None,
                "loss_damage_ratio_exceeded_1_in_100_bias_corrected": round(
                    o["damage_ratio_exceeded_1_in_100_corrected"], 4
                )
                if fixed_ok
                else None,
            }
        write_json_atomic(args.site, collection)

    args.report.write_text(
        markdown(
            rows,
            out,
            radar,
            cities,
            sensitivity,
            expressions,
            card,
            window,
            len(reports.lon),
            (total_uncapped, total_fixed_uncapped),
        )
    )
    print(
        f"hail loss: {len(out)} plants, expected annual loss {money(total)} (bias-corrected {money(total_fixed)}) of {money(total_value)}; {time.time() - started:.0f}s"
    )
    return 0


def regional_section(
    rows: list[dict[str, Any]], out: list[dict[str, Any]], card: dict[str, Any]
) -> list[str]:
    """Report section comparing the per-cell and the regional bias correction."""
    have = [
        (r, o)
        for r, o in zip(rows, out, strict=True)
        if o["expected_annual_damage_ratio_regional"] is not None
        and o["expected_annual_damage_ratio_corrected"]
    ]
    if not have:
        return []
    t = card["totals"]
    plain = np.array([o["expected_annual_damage_ratio"] for _, o in have])
    local = np.array([o["expected_annual_damage_ratio_corrected"] for _, o in have])
    wide = np.array([o["expected_annual_damage_ratio_regional"] for _, o in have])
    ratio = wide / local

    def spread(v: np.ndarray) -> str:
        return f"{pct(float(np.quantile(v, 0.1)))} / {pct(float(np.median(v)))} / {pct(float(np.quantile(v, 0.9)))}"

    def rank_corr(a: np.ndarray, b: np.ndarray) -> float:
        ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
        return float(np.corrcoef(ra, rb)[0, 1])

    regions = {o["region"] for _, o in have}
    moved = sorted(
        have,
        key=lambda x: (
            -abs(
                math.log(
                    (x[1]["expected_annual_damage_ratio_regional"] or 1e-12)
                    / x[1]["expected_annual_damage_ratio_corrected"]
                )
            )
        ),
    )[:8]
    return [
        "## Bias correction: per cell or per region (tried 2026-11-11)",
        "",
        "Two ways to correct for reporting, both from the same reporting-bias model:",
        "",
        "- **Per cell (local).** Keep the plant's circle; divide its report rate by the mean fitted reporting rate of the cells in the circle.",
        "- **Per region.** Drop the circle. Use the plant's model region (an H3 resolution-3 cell, about 12,000 km²): rate = reports in the region ÷ (years × sum over its cells of reporting rate × cell area). Report sizes are pooled over the region. Every plant in a region gets the same hail rate and size mix; only its glass type, mounting and area differ.",
        "",
        "| Basis | Portfolio loss per year | Share of value | Damage ratio per year, 10th / 50th / 90th percentile of plants |",
        "| --- | --- | --- | --- |",
        f"| Reports as they are | {money(t['expected_annual_loss_usd'])} | {pct(t['expected_annual_loss_usd'] / t['value_usd'])} | {spread(plain)} |",
        f"| Corrected per cell | {money(t['expected_annual_loss_usd_corrected'])} | {pct(t['expected_annual_loss_usd_corrected'] / t['value_usd'])} | {spread(local)} |",
        f"| Corrected per region | {money(t['expected_annual_loss_usd_regional'])} | {pct(t['expected_annual_loss_usd_regional'] / t['value_usd'])} | {spread(wide)} |",
        "",
        f"- The plants fall in {len(regions)} regions. Regional ÷ per-cell loss: median {float(np.median(ratio)):.2f}, 10th to 90th percentile {float(np.quantile(ratio, 0.1)):.2f} to {float(np.quantile(ratio, 0.9)):.2f}.",
        f"- The spread between plants narrows: 90th ÷ 10th percentile of the damage ratio is {float(np.quantile(local, 0.9) / np.quantile(local, 0.1)):.1f} per cell and {float(np.quantile(wide, 0.9) / np.quantile(wide, 0.1)):.1f} per region.",
        f"- Rank agreement between the two (Spearman): {rank_corr(local, wide):.2f}; between reports as they are and per region: {rank_corr(plain, wide):.2f}.",
        "",
        "Plants that move most between the two corrections:",
        "",
        "| Plant (county) | MW | Reports as they are | Per cell | Per region | Reports in region | Region mean reporting rate |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *[
            f"| {r['name']} ({r['county']}) | {r['capacity_ac_mw']:,.0f} | {pct(o['expected_annual_damage_ratio'])} | {pct(o['expected_annual_damage_ratio_corrected'])} | {pct(o['expected_annual_damage_ratio_regional'])} | {o['region_reports']:,} | {pct(o['region_mean_reporting_rate'], 0)} |"
            for r, o in moved
        ],
        "",
        "What the regional value gains and loses: it does not depend on how many reports happen to lie near the plant, so it is steadier and cannot be driven by one town; but it assumes hail climate is uniform over about 110 km, and it erases real differences inside a region. Regions at the state border hold only their Texas cells.",
        "",
    ]


def markdown(
    rows: list[dict[str, Any]],
    out: list[dict[str, Any]],
    radar: dict[str, dict[str, Any]],
    cities: list[dict[str, Any]],
    sensitivity: list[dict[str, Any]],
    expressions: dict[str, dict[str, Any]],
    card: dict[str, Any],
    window: am_mod.Window,
    n_reports: int,
    uncapped: tuple[float, float],
) -> str:
    d = card["defaults"]
    t = card["totals"]
    pairs = list(zip(rows, out, strict=True))
    ead = [o["expected_annual_damage_ratio"] for o in out]
    ead_c = [
        o["expected_annual_damage_ratio_corrected"]
        for o in out
        if o["expected_annual_damage_ratio_corrected"] is not None
    ]
    n_gg = sum(1 for o in out if o["glass_class"] == "glass_glass_2.0")
    n_fixed = sum(1 for o in out if o["p_stow"] == 1.0)
    n_assumed = sum(
        1 for o in out if o["assumption_notes"] and "mounting not reported" in o["assumption_notes"]
    )
    n_thin = sum(1 for o in out if o["assumption_notes"] and "thin-film" in o["assumption_notes"])
    n_flat = sum(1 for o in out if "not reported: taken as flat" in o["stow_basis"])
    mult = [
        o["expected_annual_damage_ratio_corrected"] / o["expected_annual_damage_ratio"]
        for o in out
        if o["expected_annual_damage_ratio_corrected"] and o["expected_annual_damage_ratio"] > 0
    ]
    zero = sum(1 for o in out if o["reports_that_damage"] == 0)
    base, base_c = sensitivity[0]["usd"]

    def q(values: list[float], p: float) -> float:
        return float(np.quantile(values, p))

    def plant_row(r: dict[str, Any], o: dict[str, Any]) -> str:
        rad = radar.get(r["asset_id"], {})
        biggest = (
            f"{rad['radar_max_mm']:.0f} mm on {rad['radar_max_day']}"
            if rad.get("radar_max_mm")
            else "none"
        )
        return (
            f"| {r['name']} ({r['county']}) | {r['capacity_ac_mw']:,.0f} | {r['year']} | {o['glass_class'].replace('glass_', '').replace('_', ' ')} | "
            f"{'fixed' if o['p_stow'] == 1.0 else 'tracker'} | {pct(o['expected_annual_damage_ratio'])} | {money(o['expected_annual_loss_usd'])} | "
            f"{pct(o['expected_annual_damage_ratio_corrected'])} | {money(o['expected_annual_loss_usd_corrected'] or 0)} | {biggest} |"
        )

    head = "| Plant (county) | MW AC | Year | Glass | Mounting | Damage ratio per year | Loss per year | Bias-corrected ratio | Bias-corrected loss | Largest radar hail over the plant, 2020–2025 |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    top = sorted(pairs, key=lambda x: -(x[1]["expected_annual_loss_usd_corrected"] or 0))[:10]
    fort_bend = [x for x in pairs if x[0]["county"] == "Fort Bend"]
    lines = [
        "# Phase 5 report: hail impact functions v0 and hail loss at Texas solar plants",
        "",
        f"Built {card['built_at'][:10]} with crc-sdk {card['versions']['crc-sdk']} and crc-framework {card['versions']['crc-framework']}. Every number below is written by `python -m crc_lab.impacts.build` (`just impacts`).",
        "",
        "**These are first-approximation numbers.** The curves are the v0 curves of [the spec](../requirements-hail-impact-v0.md). Four inputs have no source and are placeholders: "
        f"the stow angle ({d['stow_tilt_deg']}°), the chance a tracker is stowed when hail arrives ({d['p_stow']}), the modules' share of plant value ({d['module_cost_share']}) "
        f"and the area hit per hail report ({card['exposure']['footprint_km2']:g} km²). The sensitivity table shows how far each moves the result.",
        "",
        "## Result",
        "",
        f"- The {t['plants']} plants are worth {money(t['value_usd'])} at benchmark cost. Expected hail loss is **{money(t['expected_annual_loss_usd'])} a year from reports as they are "
        f"({pct(t['expected_annual_loss_usd'] / t['value_usd'])} of value) and {money(t['expected_annual_loss_usd_corrected'])} a year after the reporting-bias correction ({pct(t['expected_annual_loss_usd_corrected'] / t['value_usd'])})**.",
        f"- Per plant, the expected annual damage ratio has median {pct(statistics.median(ead))} (10th to 90th percentile {pct(q(ead, 0.1))} to {pct(q(ead, 0.9))}); "
        f"bias-corrected, median {pct(statistics.median(ead_c))} ({pct(q(ead_c, 0.1))} to {pct(q(ead_c, 0.9))}).",
        *(
            [
                f"- {zero} plants have no report in their circle large enough to damage their modules, so their loss is zero. That is a statement about the report record, not about the sky."
            ]
            if zero
            else []
        ),
        f"- The correction multiplies a plant's loss by {q(mult, 0.5):.1f} at the median and by up to {max(mult):.1f}. The largest factors are in thinly populated country, where the fitted reporting rate is lowest and least certain.",
        f"- The cap at full loss changes almost nothing: without it the totals would be {money(uncapped[0])} and {money(uncapped[1])}.",
        "",
        "## What was built",
        "",
        "- `src/crc_lab/impacts/hail_v0.json`: the spec's parameter block, unchanged (a test compares the two).",
        "- `src/crc_lab/impacts/hail_curves.py`: a validating loader, the three functional forms and the four curves. It imports only numpy and the standard library, so it can be offered to crc-sdk with the data file and tests.",
        "- `src/crc_lab/impacts/annual.py`: from events at an asset to a year's damage ratio (events added, capped at full loss).",
        "- `src/crc_lab/impacts/crc_adapter.py`: the curves as crc-sdk impact expressions.",
        "- `src/crc_lab/impacts/build.py`: loss per plant, this report, `data/assets/solar_tx_hail_loss.parquet` with its card, and the loss fields on the explorer's plant panel.",
        "- `tests/test_impacts.py`: every test vector in the spec, the extra checks, monotonicity and bounds on a grid from 0 to 150 mm, rejection of bad input, and the annual-loss rule against a simulation.",
        "",
        "## How loss at a plant is computed",
        "",
        f"1. **Events.** The plant's circle from Phase 4 (grown to {card['exposure']['n_target']} reports, {card['exposure']['min_radius_km']:g} to {card['exposure']['max_radius_km']:g} km, clipped to the five-state reporting region) holds the located hail reports of {window.start}–{window.end} ({n_reports:,} in the region). Each report is one possible event with its own size.",
        f"2. **Reaching the plant.** A report stands for hail of that size over {card['exposure']['footprint_km2']:g} km². The plant is a disc of its array area. The event touches the plant with chance hit area ÷ circle area, and damages the share of the plant the footprint covers.",
        "3. **Damage.** `pv_plant_hail_v0` turns the report's size into a damage ratio, with the plant's glass class and mounting (rules below).",
        "4. **A year.** Events arrive at random (Poisson). The damage ratios of a year's events are added and capped at 1.",
        "5. **Bias-corrected.** The same, with the event rate divided by the fitted reporting rate around the plant ([report 5](5-reporting-bias.md)). Sizes are not changed.",
        "",
        "One consequence of step 2 is checked in the build for every plant: the expected damage ratio equals report rate × footprint × mean damage ratio and does not depend on the plant's size. A larger plant is hit more often, but each hit covers a smaller share of it.",
        "",
        "Per-plant rules:",
        "",
        f"- **Glass class** (the spec's rule): 2.0 mm glass-glass for plants first online in {GLASS_GLASS_FROM_YEAR} or later ({n_gg} plants), 3.2 mm glass and backsheet before ({len(out) - n_gg}). {n_thin} plants have thin-film modules, for which the spec has no table; they follow the same rule and are marked.",
        f"- **Stow.** Trackers use the spec's mixture: stowed at {d['stow_tilt_deg']}° with chance {d['p_stow']}, flat otherwise. {n_fixed} fixed-tilt plants use their reported tilt all the time ({n_flat} of them report no tilt and are taken as flat). {n_assumed} plants report no mounting, nearly all from 2025–2026, and are treated as trackers.",
        "",
        "## Plants with the largest bias-corrected loss",
        "",
        head,
        *[plant_row(r, o) for r, o in top],
        "",
        "## Fort Bend County",
        "",
        "Fort Bend is where the hailstorm of 16 March 2024 damaged the Fighting Jays plant. The spec notes that stowed 2.0 mm glass-glass modules in the county came through radar-estimated hail of 40 to 100 mm undamaged, which this curve would not predict.",
        "",
        head,
        *[plant_row(r, o) for r, o in sorted(fort_bend, key=lambda x: -x[0]["capacity_ac_mw"])],
        "",
        "The report-based loss here is small because few large-hail reports lie near these plants; the radar column shows what the reports miss. A loss from radar hail is not computed: the spec keeps observed size and radar size as separate inputs, and v0 has no curve keyed to radar size.",
        "",
        *regional_section(rows, out, card),
        "## Sensitivity of the portfolio total",
        "",
        "Expected annual loss over all plants (the cap is left out here; it moves the total by less than the rounding).",
        "",
        "| Variant | From reports | × default | Bias-corrected | × default |",
        "| --- | --- | --- | --- | --- |",
        *[
            f"| {s['name']} | {money(s['usd'][0])} | {s['usd'][0] / base:.2f} | {money(s['usd'][1])} | {s['usd'][1] / base_c:.2f} |"
            for s in sensitivity
        ],
        "",
        "Module cost share and footprint scale the loss in proportion. Stow settings touch trackers only.",
        "",
        "## Buildings and cars: expected annual damage per $100,000 of value",
        "",
        "There is no building or car asset set yet, so these are the four curves at the ten city centres, for a single building or car there. Regional screening only. City centres are where reports are densest, so the uncorrected figures are the least biased here; the last column is the fitted reporting rate.",
        "",
        "| City | Reports in circle | Buildings, Swiss claims curve | Buildings, roof curve (laminated) | Buildings, roof curve (3-tab) | Cars, Swiss fleet curve | Fitted reporting rate |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *[
            f"| {c['name']} | {c['reports']} | ${c['bld_swiss'] * 1e5:,.2f} | ${c['bld_roof_laminated'] * 1e5:,.0f} | ${c['bld_roof_3tab'] * 1e5:,.0f} | ${c['car_swiss'] * 1e5:,.2f} | {pct(c['reporting_rate'], 0)} |"
            for c in cities
        ],
        "",
        f"The two building curves differ by a factor of {statistics.median(c['bld_roof_laminated'] / c['bld_swiss'] for c in cities if c['bld_swiss'] > 0):,.0f} at the median city. The spec expects this: the Swiss curve is averaged over every building in a radar cell and is a lower bound; the roof curve assumes hail of the reported size fell on the roof and is an upper bound. The gap is the uncertainty in v0, and both are reported as a range.",
        "",
        "## The curves in CRC",
        "",
        "Checked against the pins: crc-framework's sigmoid is a logistic, not the Emanuel cubic; the impact context carries no glass class, stow or roof class; CRC has no hail factor. So each curve is built as a tabulated `ImpactExpression` with exposure variable `hail_diameter_obs_mm` (mm) and impact metric `damage_ratio`. The solar curves are exact (their knots); the others are sampled every millimetre to 150 mm.",
        "",
        "| Expression | Points | Exact | Largest gap to the callable | Monotonicity |",
        "| --- | --- | --- | --- | --- |",
        *[
            f"| `{k}` | {v['points']} | {'yes' if v['exact'] else 'sampled'} | {v['max_abs_gap']:.1e} | {v['monotonicity']} |"
            for k, v in expressions.items()
        ],
        "",
        "The definitions with their hashes are in `data/assets/hail_v0_crc_expressions.json`. Their provenance is \"user defined\": a published origin needs a source record in CRC's registry, which these curves do not have. Loss was not computed through CRC's return-level path, as the spec asks: the curves are applied to each event and losses are aggregated afterwards.",
        "",
        "## Not done, and limits",
        "",
        "- No hazard factor was registered inside crc-sdk: that is an upstream change. The expressions carry the variable name, so a hail factor added later must match it.",
        '- The Swiss parameters are still tagged "verify against the paper\'s final Table 2"; the paper was not opened in this phase.',
        "- Cars in the open have no curve.",
        "- Lab breakage is applied to the largest reported stone, which overstates damage to unstowed modules; storm reports miss hail away from people, which understates the rate. The two errors do not cancel in any known way.",
        "- A report's size is assumed over the whole 25 km² footprint.",
        "- Report sizes cluster at reference objects (1.00, 1.75, 2.75 inches), so the size distribution is coarse.",
        "- `docs/decisions.md` and `docs/hail-data-processing.md` do not yet describe this step.",
        "",
        "## Questions for review",
        "",
        "1. Glass class by year treats every plant before 2021 as 3.2 mm glass and backsheet, which is the stronger module. Is that the intent, or should older plants be run both ways?",
        "2. Thin-film plants follow the year rule for lack of a table. Leave them in, or report them apart?",
        "3. Should the next step be a loss from radar hail (needs a decision on feeding radar size into these curves), or a building asset set for Fort Bend?",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
