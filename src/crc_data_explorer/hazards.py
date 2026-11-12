"""E3/E4: the Texas explorer's hazard files, built from CRC Open through crc-sdk.

The file format and the evaluation of curves are in ``lab_common.horizons``; this module
materializes each CRC Open hazard and checks shipped values against crc-sdk.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path
from typing import Any

import pyarrow as pa
from crc_sdk.connectors import read_hazard_metadata
from crc_sdk.workflows.crc_open import CRCOpenPlan

from lab_common.horizons import (
    KINDS,
    RETURN_PERIODS,
    SIGNIFICANT_DIGITS,
    HazardBuild,
    _params,
    _round,
    evaluate,
    write_horizon_files,
)

__all__ = [
    "HAZARDS", "HORIZONS", "KINDS", "RETURN_PERIODS", "SIGNIFICANT_DIGITS", "HazardBuild",
    "_params", "_round", "build_hazard", "evaluate", "materialize", "verify_against_for_assets",
    "write_horizon_files",
]  # fmt: skip

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
    result = HazardBuild(
        hazard=hazard,
        parquet=str(parquet),
        unit=meta.value_unit,
        tail=meta.return_period_tail,
        h3_resolution=meta.h3_resolution,
        horizons=list(horizons),
        cells_in_texas=len(cells_by_resolution[meta.h3_resolution]),
        warnings=notes,
    )
    write_horizon_files(
        parquet,
        hazard,
        cells_by_resolution,
        out_dir,
        horizons=horizons,
        pathway=plan.pathway,
        release=plan.release,
        return_periods=return_periods,
        workers=workers,
        result=result,
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
