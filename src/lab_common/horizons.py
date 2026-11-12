"""One compact JSON file per horizon from a canonical hazard Parquet (shared by the projects).

Each file holds, per cell, the curve evaluated by crc-sdk at fixed return periods
(``curve_quantiles``) plus the raw curve parameters. The browser never
re-implements a curve (decided 2026-11-10).
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
from crc_sdk.connectors import read_hazard_dataset, read_hazard_metadata
from crc_sdk.workflows.distributions import (
    curve_parameters_from_row,
    curve_quantiles,
    return_periods_to_probabilities,
)

from lab_common.texas import write_json_atomic

RETURN_PERIODS: tuple[int, ...] = (2, 5, 10, 20, 50, 100, 200, 500)
KINDS: tuple[str, ...] = ("fitted", "hurdle", "point_mass", "tabulated", "no_data")
SIGNIFICANT_DIGITS = 6


@dataclass
class HazardBuild:
    """What one hazard's build produced, for the manifest and the report."""

    hazard: str
    parquet: str
    unit: str
    tail: str
    h3_resolution: int
    horizons: list[int]
    cells_in_texas: int
    rows_per_horizon: dict[int, int] = field(default_factory=dict)
    kinds: dict[str, int] = field(default_factory=dict)
    families: dict[str, int] = field(default_factory=dict)
    no_data_reasons: dict[str, int] = field(default_factory=dict)
    outside_tabulated_support: int = 0
    warnings: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    seconds: float = 0.0


def evaluate(
    table: pa.Table,
    rows: list[dict[str, Any]],
    probabilities: tuple[float, ...],
    *,
    workers: int | None,
) -> tuple[list[tuple[float | None, ...]], int]:
    """``curve_quantiles`` for the table, except tabulated curves, which crc-sdk refuses to
    evaluate outside their knots (``ValueError``). Those are evaluated knot-wise: a
    probability outside the tabulated support gives null. Returns the values and the
    number of such nulls.
    """
    tabulated = [i for i, row in enumerate(rows) if row["curve_kind"] == "tabulated"]
    if not tabulated:
        return curve_quantiles(table, probabilities, max_workers=workers or os.cpu_count()), 0
    keep = pa.array([i for i in range(len(rows)) if i not in set(tabulated)], pa.int64())
    bulk = iter(
        curve_quantiles(table.take(keep), probabilities, max_workers=workers or os.cpu_count())
    )
    outside = 0
    values: list[tuple[float | None, ...]] = []
    for row in rows:
        if row["curve_kind"] != "tabulated":
            values.append(next(bulk))
            continue
        knots = row["curve_probabilities"]
        low, high = min(knots), max(knots)
        inside = [p for p in probabilities if low <= p <= high]
        found = (
            dict(
                zip(
                    inside,
                    curve_parameters_from_row(row).to_distribution().quantiles(inside),
                    strict=True,
                )
            )
            if inside
            else {}
        )
        values.append(tuple(float(found[p]) if p in found else None for p in probabilities))
        outside += len(probabilities) - len(inside)
    return values, outside


def _round(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    if value == 0:
        return 0.0
    return float(f"{value:.{SIGNIFICANT_DIGITS}g}")


def _params(row: dict[str, Any]) -> list[Any]:
    """Raw curve description: kind code, type (family or no-data reason), then numbers."""
    kind = row["curve_kind"]
    out: list[Any] = [KINDS.index(kind), row["curve_type"]]
    if kind in ("fitted", "hurdle"):
        out += [
            _round(row["curve_location"]),
            _round(row["curve_scale"]),
            _round(row["curve_shape"]),
        ]
    if kind == "hurdle":
        out += [_round(row["curve_atom_probability"]), _round(row["curve_atom_location"])]
    if kind == "point_mass":
        out += [_round(row["curve_location"])]
    if kind == "tabulated":
        out += [len(row["curve_probabilities"] or [])]
    return out


def write_horizon_files(
    parquet: Path,
    hazard: str,
    cells_by_resolution: dict[int, set[int]],
    out_dir: Path,
    *,
    horizons: tuple[int, ...],
    pathway: str,
    release: str,
    return_periods: tuple[int, ...] = RETURN_PERIODS,
    workers: int | None = None,
    result: HazardBuild | None = None,
) -> HazardBuild:
    """One JSON per horizon from any canonical Parquet (CRC Open or curves built here)."""
    meta = read_hazard_metadata(parquet)
    resolution = meta.h3_resolution
    cells = cells_by_resolution[resolution]
    table = read_hazard_dataset(parquet)
    table = table.filter(pc.is_in(table["cell_index"], pa.array(sorted(cells), pa.uint64())))
    table = table.filter(
        pc.is_in(table["horizon"], pa.array(list(horizons), table["horizon"].type))
    )
    probabilities = return_periods_to_probabilities(return_periods, tail=meta.return_period_tail)
    result = result or HazardBuild(
        hazard=hazard,
        parquet=str(parquet),
        unit=meta.value_unit,
        tail=meta.return_period_tail,
        h3_resolution=resolution,
        horizons=list(horizons),
        cells_in_texas=len(cells),
    )
    for horizon in horizons:
        part = table.filter(pc.equal(table["horizon"], horizon)).sort_by("cell_index")
        rows = part.to_pylist()
        values, outside = evaluate(part, rows, probabilities, workers=workers)
        result.outside_tabulated_support += outside
        payload = {
            "hazard": hazard,
            "horizon": horizon,
            "pathway": pathway,
            "release": release,
            "unit": meta.value_unit,
            "value_semantics": meta.value_semantics,
            "tail": meta.return_period_tail,
            "probability_semantics": meta.probability_semantics,
            "h3_resolution": resolution,
            "return_periods": list(return_periods),
            "probabilities": [float(p) for p in probabilities],
            "kinds": list(KINDS),
            "cells": [f"{row['cell_index']:x}" for row in rows],
            "values": [[_round(v) for v in per_cell] for per_cell in values],
            "params": [_params(row) for row in rows],
        }
        path = out_dir / hazard / f"{horizon}.json"
        write_json_atomic(path, payload)
        result.files.append(str(path.relative_to(out_dir.parent)))
        result.rows_per_horizon[horizon] = len(rows)
        for row in rows:
            result.kinds[row["curve_kind"]] = result.kinds.get(row["curve_kind"], 0) + 1
            if row["curve_kind"] in ("fitted", "hurdle"):
                result.families[row["curve_type"]] = result.families.get(row["curve_type"], 0) + 1
            if row["curve_kind"] == "no_data":
                reason = row["curve_type"]
                result.no_data_reasons[reason] = result.no_data_reasons.get(reason, 0) + 1
    return result
