# ruff: noqa: E501
"""``python -m crc_lab.radar.build``: radar hail days at the plants, swath areas, and the note."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from crc_lab.radar import analysis, mrms

SMOOTH_KM = 25.0


def smoothed_rate(
    counts: np.ndarray,
    grid: dict[str, Any],
    lon: float,
    lat: float,
    years: float,
    radius_km: float = SMOOTH_KM,
) -> float:
    """Mean hail days per year over the cells within ``radius_km`` of the point."""
    r = int(round((lat - grid["lat0"]) / grid["dlat"]))
    c = int(round((lon - grid["lon0"]) / grid["dlon"]))
    hr = int(math.ceil(radius_km / (abs(grid["dlat"]) * 110.57)))
    hc = int(math.ceil(radius_km / (abs(grid["dlon"]) * 111.32 * math.cos(math.radians(lat)))))
    rr, cc = np.mgrid[-hr : hr + 1, -hc : hc + 1]
    dist = np.hypot(
        rr * abs(grid["dlat"]) * 110.57,
        cc * abs(grid["dlon"]) * 111.32 * math.cos(math.radians(lat)),
    )
    ri, ci = r + rr[dist <= radius_km], c + cc[dist <= radius_km]
    ok = (ri >= 0) & (ri < counts.shape[0]) & (ci >= 0) & (ci < counts.shape[1])
    return float(counts[ri[ok], ci[ok]].mean() / years) if ok.any() else float("nan")


def q(values: list[float], probs=(0.1, 0.5, 0.9)) -> list[float]:
    return [float(x) for x in np.quantile(np.asarray(values, dtype=float), probs)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/cache/mrms"))
    parser.add_argument("--plants", type=Path, default=Path("data/assets/solar_tx.parquet"))
    parser.add_argument("--out", type=Path, default=Path("data/assets/radar_plants.parquet"))
    parser.add_argument("--note", type=Path, default=Path("docs/reports/4-radar-hail.md"))
    args = parser.parse_args(argv)

    rows = pq.read_table(args.plants).to_pylist()
    plants = [
        {
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "area_km2": (r["area_m2"] or 0) / 1e6,
        }
        for r in rows
    ]
    res = analysis.analyse(args.cache, plants)
    years, grid = res["years"], res["grid"]
    t_lo, t_hi = analysis.THRESHOLDS_MM
    out_rows = []
    for i, r in enumerate(rows):
        out_rows.append(
            {
                "asset_id": r["asset_id"],
                "radar_days_ge_30mm": int(res["plant_days"][t_lo][i]),
                "radar_days_ge_50mm": int(res["plant_days"][t_hi][i]),
                "radar_days_per_year_ge_30mm": res["plant_days"][t_lo][i] / years,
                "radar_days_per_year_ge_50mm": res["plant_days"][t_hi][i] / years,
                "radar_local_rate_ge_30mm": smoothed_rate(
                    res["counts"][t_lo], grid, r["longitude"], r["latitude"], years
                ),
                "radar_local_rate_ge_50mm": smoothed_rate(
                    res["counts"][t_hi], grid, r["longitude"], r["latitude"], years
                ),
                "radar_max_mm": float(res["plant_max_mm"][i]),
                "radar_max_day": res["plant_max_day"][i],
            }
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "source": mrms.BUCKET,
        "product": mrms.PRODUCT,
        "first_day": res["first_day"],
        "last_day": res["last_day"],
        "days": res["days"],
        "years": years,
        "smoothing_km": SMOOTH_KM,
    }
    pq.write_table(
        pa.Table.from_pylist(out_rows).replace_schema_metadata(
            {b"crc_lab.radar": json.dumps(meta).encode()}
        ),
        args.out,
    )

    geojson = Path("site/data/assets/solar_tx.geojson")
    if geojson.exists():
        from lab_common.texas import write_json_atomic

        collection = json.loads(geojson.read_text())
        by_id = {o["asset_id"]: o for o in out_rows}
        for feature in collection["features"]:
            o = by_id.get(feature["properties"]["asset_id"])
            if o:
                feature["properties"] |= {
                    "radar_period": f"{res['first_day']} to {res['last_day']}",
                    "radar_hail_days_30mm_or_more_over_plant": o["radar_days_ge_30mm"],
                    "radar_hail_days_50mm_or_more_over_plant": o["radar_days_ge_50mm"],
                    "radar_hail_days_per_year_30mm_local_25km": round(
                        o["radar_local_rate_ge_30mm"], 3
                    ),
                    "radar_largest_size_over_plant_mm": round(o["radar_max_mm"], 1),
                    "radar_largest_size_day": o["radar_max_day"],
                }
        write_json_atomic(geojson, collection)

    # report-based figures on the same plants: annual chance of 1 inch or more -> rate of hits per year
    rep_rate = [-math.log(1 - r["hail_annual_prob_ge_1in"]) for r in rows]
    rep_rate2 = [-math.log(1 - r["hail_annual_prob_ge_2in"]) for r in rows]
    rad29 = [o["radar_days_per_year_ge_30mm"] for o in out_rows]
    rad50 = [o["radar_days_per_year_ge_50mm"] for o in out_rows]
    loc29 = [o["radar_local_rate_ge_30mm"] for o in out_rows]
    loc50 = [o["radar_local_rate_ge_50mm"] for o in out_rows]
    cor = [
        -math.log(1 - r["hail_annual_prob_ge_1in_corrected"])
        if r.get("hail_annual_prob_ge_1in_corrected") not in (None, 1.0)
        else None
        for r in rows
    ]
    ratio_cor = [a / b for a, b in zip(loc29, cor, strict=True) if b]
    ratio = [a / b for a, b in zip(loc29, rep_rate, strict=True) if b > 0]
    ratio2 = [a / b for a, b in zip(loc50, rep_rate2, strict=True) if b > 0]
    sw = {t: analysis.swath_summary(res["swath_areas_km2"][t]) for t in analysis.THRESHOLDS_MM}
    fb = [(r, o) for r, o in zip(rows, out_rows, strict=True) if r["county"] == "Fort Bend"]
    top = sorted(zip(rows, out_rows, strict=True), key=lambda x: -x[1]["radar_local_rate_ge_50mm"])[
        :5
    ]

    def f(v: float, d: int = 2) -> str:
        return f"{v:.{d}f}"

    lines = [
        "# Phase 4 note: radar hail at the solar plants",
        "",
        f"MRMS radar hail size (MESH), 24-hour maximum valid at 12 UTC, {res['first_day']} to {res['last_day']}: {res['days']:,} days "
        f"({years:.1f} years) from NOAA's open archive. A radar hail day at a plant is a day whose maximum over the plant's array "
        "area reaches the threshold. Every number is computed by `python -m crc_lab.radar.build`.",
        "",
        "MESH is a radar estimate built to exceed most observed sizes; it says where hail probably fell and roughly how big, "
        "not what reached the ground. Five years is a short record: a plant with no radar hail day in it is not hail-free.",
        "",
        f"## Across the {len(rows)} plants",
        "",
        "| Measure | 10th percentile | Median | 90th percentile |",
        "| --- | --- | --- | --- |",
        f"| Radar hail days per year over the plant, MESH 30 mm or more | {' | '.join(f(v) for v in q(rad29))} |",
        f"| Radar hail days per year over the plant, MESH 50 mm or more | {' | '.join(f(v) for v in q(rad50))} |",
        f"| Radar hail days per year at a point, averaged over {SMOOTH_KM:g} km, 30 mm or more | {' | '.join(f(v) for v in q(loc29))} |",
        f"| Radar hail days per year at a point, averaged over {SMOOTH_KM:g} km, 50 mm or more | {' | '.join(f(v) for v in q(loc50, (0.1, 0.5, 0.9)))} |",
        f"| Report-based hits per year, hail 1 inch or more (footprint 25 km²) | {' | '.join(f(v, 3) for v in q(rep_rate))} |",
        f"| Report-based hits per year, hail 2 inches or more | {' | '.join(f(v, 4) for v in q(rep_rate2))} |",
        f"| Radar (30 mm, {SMOOTH_KM:g} km average) ÷ report-based (1 inch) | {' | '.join(f(v, 1) for v in q(ratio))} |",
        f"| Radar (30 mm, {SMOOTH_KM:g} km average) ÷ report-based, bias-corrected (1 inch) | {' | '.join(f(v, 1) for v in q(ratio_cor))} |",
        f"| Radar (50 mm, {SMOOTH_KM:g} km average) ÷ report-based (2 inches) | {' | '.join(f(v, 1) for v in q(ratio2))} |",
        "",
        f"Plants with no radar hail day over them in the period: {sum(1 for v in rad29 if v == 0)} at 30 mm, {sum(1 for v in rad50 if v == 0)} at 50 mm.",
        "",
        "## Measured swath areas in the Texas box",
        "",
        "Connected areas at or above the threshold on one day, of at least five grid cells (about 5 km²).",
        "",
        "| Threshold | Swaths | 25th percentile km² | Median km² | 75th percentile km² | 90th percentile km² | Mean km² |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for t in analysis.THRESHOLDS_MM:
        s = sw[t]
        lines.append(
            f"| {t:g} mm | {s['n']:,} | {s['p25']:.1f} | {s['median']:.1f} | {s['p75']:.1f} | {s['p90']:.1f} | {s['mean']:.1f} |"
        )
    lines += [
        "",
        "The 25 km² footprint used for report-based exposure sits between the median and the mean of these.",
        "",
        "## Fort Bend County plants",
        "",
        "| Plant | Radar days 30 mm or more | Radar days 50 mm or more | Largest radar size over the plant (mm) | On | Report-based annual chance, 2 inches or more |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r, o in fb:
        lines.append(
            f"| {r['name']} | {o['radar_days_ge_30mm']} | {o['radar_days_ge_50mm']} | {o['radar_max_mm']:.1f} | {o['radar_max_day']} | {r['hail_annual_prob_ge_2in']:.4f} |"
        )
    lines += [
        "",
        "## Highest radar exposure (50 mm or more, local average)",
        "",
        "| Plant | County | MW AC | Radar days per year, 50 mm, local | Largest over the plant (mm) | Report-based annual chance, 2 inches or more |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r, o in top:
        lines.append(
            f"| {r['name']} | {r['county']} | {r['capacity_ac_mw']:.0f} | {o['radar_local_rate_ge_50mm']:.2f} | {o['radar_max_mm']:.1f} | {r['hail_annual_prob_ge_2in']:.4f} |"
        )
    lines.append("")
    args.note.write_text("\n".join(lines))
    print(
        json.dumps(
            {
                "days": res["days"],
                "years": round(years, 2),
                "swaths": sw,
                "ratio_29_vs_1in": q(ratio),
                "ratio_50_vs_2in": q(ratio2),
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
