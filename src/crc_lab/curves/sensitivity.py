# ruff: noqa: E501
"""C2: how much the curves depend on the pooling ring, the start year and the family."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
from crc_sdk.types import SourceProvenance

from crc_lab.curves import fit
from crc_lab.curves.annual_maxima import Window

CITIES = [
    {"name": n, "lon": lo, "lat": la}
    for n, lo, la in [
        ("Houston", -95.37, 29.76),
        ("Dallas", -96.80, 32.78),
        ("San Antonio", -98.49, 29.42),
        ("Austin", -97.74, 30.27),
        ("Fort Worth", -97.33, 32.75),
        ("El Paso", -106.49, 31.76),
        ("Amarillo", -101.83, 35.22),
        ("Lubbock", -101.86, 33.58),
        ("Corpus Christi", -97.40, 27.80),
        ("Midland", -102.08, 32.00),
    ]
]
VARIANTS = [
    fit.Variant(k=0, start=1996, family="gumbel_r", name="no pooling"),
    fit.Variant(k=1, start=1996, family="gumbel_r", name="default"),
    fit.Variant(k=2, start=1996, family="gumbel_r", name="two rings"),
    fit.Variant(k=1, start=2005, family="gumbel_r", name="from 2005"),
    fit.Variant(k=1, start=1996, family="genextreme", name="GEV"),
]
SHOW = (10, 50, 100)


def run(am: pa.Table, end: int, provenance: SourceProvenance, work: Path) -> dict[str, Any]:
    """Fit every variant for both hazards; return city values and curve-kind counts per variant."""
    out: dict[str, Any] = {"cities": CITIES, "return_periods": list(SHOW), "variants": []}
    for variant in VARIANTS:
        entry: dict[str, Any] = {
            "name": variant.name,
            "label": variant.label,
            "k": variant.k,
            "start": variant.start,
            "family": variant.family,
            "hazards": {},
        }
        for hazard in fit.HAZARDS:
            path = work / f"{hazard}-{variant.label}.parquet"
            _, warns = fit.fit_hazard(
                am, hazard, Window(variant.start, end), variant, provenance, path
            )
            rows = fit.evaluate_points(path, CITIES, return_periods=SHOW)
            entry["hazards"][hazard] = {
                "kinds": fit.curve_kind_counts(path),
                "warnings": warns,
                "cities": {r["asset_id"]: [r[f"value_rp{t}"] for t in SHOW] for r in rows},
            }
        out["variants"].append(entry)
    return out


def markdown(results: dict[str, Any]) -> str:
    """One table per hazard and return period: cities × variants, plus curve kinds per variant."""
    lines = ["# Phase 3 note: sensitivity of the hail and gust curves", ""]
    lines.append(
        "Values at ten city centres (the cell containing the point), from `for_assets`, for each way of building the "
        "curves. The default is one ring of pooling (7 cells), window 1996–end, Gumbel with a zero atom. "
        "Units: hail mm, gust m/s. Every number is computed by the build (`just curves-sensitivity`)."
    )
    lines.append("")
    names = [v["name"] for v in results["variants"]]
    for hazard, unit in (("hail_size", "mm"), ("thunderstorm_gust", "m/s")):
        for i, period in enumerate(results["return_periods"]):
            lines.append(f"## {hazard}, 1 in {period} years ({unit})")
            lines.append("")
            lines.append("| City | " + " | ".join(names) + " |")
            lines.append("| --- | " + " | ".join("---" for _ in names) + " |")
            for city in results["cities"]:
                row = []
                for v in results["variants"]:
                    value = v["hazards"][hazard]["cities"].get(city["name"], [None] * 3)[i]
                    row.append("–" if value is None else f"{value:.1f}")
                lines.append(f"| {city['name']} | " + " | ".join(row) + " |")
            lines.append("")
        kinds = sorted({k for v in results["variants"] for k in v["hazards"][hazard]["kinds"]})
        lines.append(f"### Curve kinds, {hazard}")
        lines.append("")
        lines.append("| Variant | " + " | ".join(kinds) + " |")
        lines.append("| --- | " + " | ".join("---" for _ in kinds) + " |")
        for v in results["variants"]:
            lines.append(
                f"| {v['name']} | "
                + " | ".join(str(v["hazards"][hazard]["kinds"].get(k, 0)) for k in kinds)
                + " |"
            )
        lines.append("")
    lines.append("## Reading")
    lines.append("")
    lines.append(
        "- **No pooling** leaves single cells with few non-zero years: more `point_mass`/`tabulated` rows and noisier tails.\n"
        "- **Two rings** (19 cells) smooths more; compare the city spread against the default.\n"
        "- **From 2005** uses 21 years instead of 30: shows how much the early, sparser years matter.\n"
        "- **GEV** adds a shape parameter; with 30 (pooled: 210) samples and large zero shares the shape is poorly constrained, "
        "which is why Gumbel is the default."
    )
    lines.append("")
    return "\n".join(lines)
