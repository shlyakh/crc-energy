"""E3/E4: one compact JSON file per hazard and horizon for the Texas cells.

Each file holds, per cell, the curve evaluated by crc-sdk at fixed return periods
(``curve_quantiles``) plus the raw curve parameters. The browser never
re-implements a curve (decided 2026-11-10).
"""

from __future__ import annotations

import math
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
from crc_sdk.connectors import read_hazard_dataset, read_hazard_metadata
from crc_sdk.workflows.crc_open import CRCOpenPlan
from crc_sdk.workflows.distributions import (
    curve_parameters_from_row,
    curve_quantiles,
    return_periods_to_probabilities,
)

from crc_lab.explorer.texas import write_json_atomic

RETURN_PERIODS: tuple[int, ...] = (2, 5, 10, 20, 50, 100, 200, 500)
HORIZONS: tuple[int, ...] = (2030, 2050, 2080)
HAZARDS: tuple[str, ...] = (
    "tx_max",
    "tn_min",
    "rx1day",
    "rflood",
    "wind_max_daily_max",
    "fwi",
    "spei",
    "hot_days",
)
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


def materialize(
    plan: CRCOpenPlan, hazard: str, cache_dir: Path, *, refresh: bool
) -> tuple[Path, list[str]]:
    """Materialize one hazard's canonical Parquet for the plan's area, every horizon.

    The file is reused when present; ``refresh`` downloads again. All horizons are
    kept so any subset can be built from the cache.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{hazard}.parquet"
    notes: list[str] = []
    if target.exists() and not refresh:
        return target, notes
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan.hazards([hazard]).materialize(target)
    notes.extend(str(w.message) for w in caught)
    return target, notes


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


def build_hazard(
    plan: CRCOpenPlan,
    hazard: str,
    cells_by_resolution: dict[int, set[int]],
    out_dir: Path,
    cache_dir: Path,
    *,
    horizons: tuple[int, ...] = HORIZONS,
    return_periods: tuple[int, ...] = RETURN_PERIODS,
    workers: int | None = None,
    refresh: bool = False,
) -> HazardBuild:
    import time

    started = time.time()
    parquet, notes = materialize(plan, hazard, cache_dir, refresh=refresh)
    meta = read_hazard_metadata(parquet)
    resolution = meta.h3_resolution
    cells = cells_by_resolution[resolution]
    table = read_hazard_dataset(parquet)
    table = table.filter(pc.is_in(table["cell_index"], pa.array(sorted(cells), pa.uint64())))
    table = table.filter(
        pc.is_in(table["horizon"], pa.array(list(horizons), table["horizon"].type))
    )
    probabilities = return_periods_to_probabilities(return_periods, tail=meta.return_period_tail)
    result = HazardBuild(
        hazard=hazard,
        parquet=str(parquet),
        unit=meta.value_unit,
        tail=meta.return_period_tail,
        h3_resolution=resolution,
        horizons=list(horizons),
        cells_in_texas=len(cells),
        warnings=notes,
    )
    for horizon in horizons:
        part = table.filter(pc.equal(table["horizon"], horizon)).sort_by("cell_index")
        rows = part.to_pylist()
        values, outside = evaluate(part, rows, probabilities, workers=workers)
        result.outside_tabulated_support += outside
        payload = {
            "hazard": hazard,
            "horizon": horizon,
            "pathway": plan.pathway,
            "release": plan.release,
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
            key = "families" if row["curve_kind"] in ("fitted", "hurdle") else None
            if key:
                result.families[row["curve_type"]] = result.families.get(row["curve_type"], 0) + 1
            if row["curve_kind"] == "no_data":
                result.no_data_reasons[row["curve_type"]] = (
                    result.no_data_reasons.get(row["curve_type"], 0) + 1
                )
    result.seconds = round(time.time() - started, 1)
    return result


def verify_against_for_assets(
    plan: CRCOpenPlan,
    hazard: str,
    out_dir: Path,
    *,
    sample: int = 5,
    horizons: tuple[int, ...] = HORIZONS,
    return_periods: tuple[int, ...] = RETURN_PERIODS,
    seed: int = 7,
) -> dict[str, Any]:
    """The Phase 1 'done' test: shipped values equal ``for_assets`` at sampled cells."""
    import json
    import random
    import tempfile

    import pyarrow.parquet as pq

    first = json.loads((out_dir / hazard / f"{horizons[0]}.json").read_text())
    rng = random.Random(seed)
    tabulated_kind = first["kinds"].index("tabulated")
    candidates = [i for i, p in enumerate(first["params"]) if p[0] != tabulated_kind]
    chosen = rng.sample(candidates, min(sample, len(candidates)))
    cell_ids = [int(first["cells"][i], 16) for i in chosen]
    assets = pa.table(
        {"asset_id": [f"cell-{i}" for i in chosen], "cell_index": pa.array(cell_ids, pa.uint64())}
    )
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "eval.parquet"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            (
                plan.hazards([hazard])
                .horizons(list(horizons))
                .for_assets(assets)
                .select(horizons=list(horizons), pathways=[plan.pathway])
                .return_periods(list(return_periods))
                .write_parquet(target)
            )
        evaluated = pq.read_table(target).to_pylist()
    checked = 0
    mismatches: list[dict[str, Any]] = []
    for horizon in horizons:
        shipped = json.loads((out_dir / hazard / f"{horizon}.json").read_text())
        index = {cell: i for i, cell in enumerate(shipped["cells"])}
        for row in evaluated:
            if row["horizon"] != horizon:
                continue
            cell = f"{row['cell_index']:x}"
            ours = shipped["values"][index[cell]]
            for rp, mine in zip(return_periods, ours, strict=True):
                theirs = row[f"value_rp{rp}"]
                checked += 1
                if theirs is None and mine is None:
                    continue
                if (
                    theirs is None
                    or mine is None
                    or not math.isclose(theirs, mine, rel_tol=1e-5, abs_tol=1e-6)
                ):
                    mismatches.append(
                        {
                            "cell": cell,
                            "horizon": horizon,
                            "rp": rp,
                            "shipped": mine,
                            "for_assets": theirs,
                        }
                    )
    return {
        "hazard": hazard,
        "cells": [f"{c:x}" for c in cell_ids],
        "values_checked": checked,
        "mismatches": mismatches,
    }
