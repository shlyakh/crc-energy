# ruff: noqa: E501  (long policy strings and SQL read better on one line)
"""C2 and C3: pool neighbouring cells, fit curves through ``HazardDataset.from_table``.

Pooling rule (recorded in the data card): a cell's sample is the union of the annual maxima of
every cell within ``k`` H3 rings of it (k=1: the cell and its six neighbours, 7 × years values).
This is "station-year" pooling: it keeps the per-year zeros, multiplies the sample size and
smooths the reporting noise of single cells. It also smooths real gradients over about
2k+1 cells (~35 km per ring at r5), which the sensitivity note quantifies.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import h3
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from crc_sdk.fitting import CDFColumnSchema, CDFCurveFitPolicy
from crc_sdk.types import SourceProvenance
from crc_sdk.types.dataset import TemporalWindow
from crc_sdk.workflows import HazardDataset

from crc_lab.curves.annual_maxima import GUST, GUST_UNIT, HAIL, HAIL_UNIT, Window

PATHWAY = "observed"
SOURCE_ID = "crc-lab-storm-events"
RETURN_PERIODS = (2, 5, 10, 20, 50, 100)
HAZARDS = {
    HAIL: {
        "column": "hail_mm",
        "unit": HAIL_UNIT,
        "semantics": "annual maximum reported hail size",
    },
    GUST: {
        "column": "gust_ms",
        "unit": GUST_UNIT,
        "semantics": "annual maximum reported thunderstorm wind (gust or sustained, measured or estimated)",
    },
}


@dataclass(frozen=True)
class Variant:
    """One way to build the curves; the default is the shipped one."""

    k: int = 1
    start: int = 1996
    family: str = "gumbel_r"
    name: str = field(default="default")

    @property
    def label(self) -> str:
        return f"k{self.k}-from{self.start}-{self.family}"


def pooled_samples(
    am: pa.Table, column: str, cells: list[int], window: Window, k: int
) -> list[list[float]]:
    """Per cell, the annual maxima of itself and its k-ring neighbours inside ``window``."""
    years = pc.field("year") >= window.start
    sub = am.filter(years)
    by_cell: dict[int, list[float]] = {}
    for cell, value in zip(sub["cell"].to_pylist(), sub[column].to_pylist(), strict=True):
        by_cell.setdefault(cell, []).append(float(value))
    out = []
    for cell in cells:
        ring = [h3.str_to_int(c) for c in h3.grid_disk(h3.int_to_str(cell), k)] if k else [cell]
        samples: list[float] = []
        for neighbour in ring:
            samples.extend(by_cell.get(neighbour, []))  # cells outside Texas contribute nothing
        out.append(samples)
    return out


def samples_table(am: pa.Table, hazard: str, window: Window, k: int, horizon: int) -> pa.Table:
    cells = sorted(set(am["cell"].to_pylist()))
    samples = pooled_samples(am, HAZARDS[hazard]["column"], cells, window, k)
    return pa.table(
        {
            "cell": pa.array(cells, pa.uint64()),
            "hazard": pa.array([hazard] * len(cells)),
            "horizon": pa.array([horizon] * len(cells), pa.int32()),
            "pathway": pa.array([PATHWAY] * len(cells)),
            "samples": pa.array(samples, pa.list_(pa.float64())),
        }
    )


def policy_for(
    hazard: str,
    window: Window,
    variant: Variant,
    provenance: SourceProvenance,
    diagnostics: Path | None,
) -> CDFCurveFitPolicy:
    spec = HAZARDS[hazard]
    return CDFCurveFitPolicy(
        h3_resolution=5,
        family=variant.family,
        fallback_families=("gumbel_r",) if variant.family != "gumbel_r" else (),
        value_unit=spec["unit"],
        value_semantics=spec["semantics"]
        + f"; k={variant.k} ring pooling; {window.start}-{window.end}",
        producer="crc-lab",
        source=provenance,
        source_id=SOURCE_ID,
        probability_semantics="annual_value_distribution",
        lower_bound=0.0,
        temporal_window=TemporalWindow(kind="window", start_year=window.start, end_year=window.end),
        parametric_failure_action="tabulated",
        on_fit_failure="skip",
        diagnostics=str(diagnostics) if diagnostics else None,
    )


def fit_hazard(
    am: pa.Table,
    hazard: str,
    window: Window,
    variant: Variant,
    provenance: SourceProvenance,
    output: Path,
    *,
    diagnostics: Path | None = None,
) -> tuple[HazardDataset, list[str]]:
    """Fit one hazard for one variant into ``output`` (canonical Parquet); return warnings."""
    horizon = window.end
    table = samples_table(am, hazard, window, variant.k, horizon)
    columns = CDFColumnSchema(
        cell="cell", hazard="hazard", horizon="horizon", pathway="pathway", samples="samples"
    )
    plan = HazardDataset.from_table(
        table, columns=columns, policy=policy_for(hazard, window, variant, provenance, diagnostics)
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        dataset = plan.materialize(output)
    return dataset, [str(w.message) for w in caught]


def evaluate_points(
    dataset_path: Path, points: list[dict[str, Any]], return_periods=RETURN_PERIODS
) -> list[dict[str, Any]]:
    """``for_assets`` at named points (lon/lat), one row per point with value_rpN columns."""
    assets = pa.table(
        {
            "asset_id": [p["name"] for p in points],
            "longitude": [p["lon"] for p in points],
            "latitude": [p["lat"] for p in points],
        }
    )
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "eval.parquet"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            HazardDataset.local(dataset_path).for_assets(assets).return_periods(
                list(return_periods)
            ).write_parquet(target)
        rows = pq.read_table(target).to_pylist()
    keep = ["asset_id", "hazard_name", "horizon"] + [f"value_rp{t}" for t in return_periods]
    return [{k: r.get(k) for k in keep} for r in rows]


def curve_kind_counts(dataset_path: Path) -> dict[str, int]:
    table = pq.read_table(dataset_path, columns=["curve_kind", "curve_type"])
    counts: dict[str, int] = {}
    for kind, family in zip(
        table["curve_kind"].to_pylist(), table["curve_type"].to_pylist(), strict=True
    ):
        key = f"{kind}:{family}" if kind in ("fitted", "hurdle") else kind
        counts[key] = counts.get(key, 0) + 1
    return counts


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
    with os.fdopen(fd, "w") as handle:
        json.dump(payload, handle, indent=1, default=str)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def data_card(
    hazard: str,
    window: Window,
    variant: Variant,
    provenance: SourceProvenance,
    dataset_path: Path,
    am_summary: dict[str, Any],
    warnings_: list[str],
) -> dict[str, Any]:
    spec = HAZARDS[hazard]
    return {
        "name": f"{hazard}: {spec['semantics']}, Texas, H3 r5",
        "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "source": provenance.model_dump(),
        "licence": provenance.licence,
        "attribution": provenance.attribution,
        "coverage": {
            "state": "Texas",
            "years": [window.start, window.end],
            "cells": am_summary["cells"],
        },
        "unit": spec["unit"],
        "horizon": window.end,
        "pathway": PATHWAY,
        "probability_semantics": "annual_value_distribution",
        "reduction_rule": (
            f"per cell and year the largest reported value; years without a report are zeros; an event counts in every "
            f"cell its point, path, county or zone touches; pooled over the cell and its {variant.k}-ring neighbours "
            f"(station-year pooling, {7 if variant.k == 1 else 19 if variant.k == 2 else 1} cells); fitted by crc-sdk "
            f"from the sorted samples ({variant.family}, lower bound 0, atom inferred from the zero plateau)"
        ),
        "curve_kinds": curve_kind_counts(dataset_path),
        "known_biases": [
            "Report-based: an empty cell may be unobserved, not calm. Reports follow people and roads.",
            "Sizes and speeds are mostly estimates (hail: compared with coins and balls; wind: estimated gusts).",
            "Pooling over neighbours smooths real gradients over about 35 km per ring.",
            "Coverage of all event types starts in 1996; reporting practice changed over the window.",
            "Regional screening: a cell is about 253 km².",
        ],
        "crc_sdk_warnings": warnings_,
    }


def verify_shipped(
    dataset_path: Path, shipped_json: Path, *, sample: int = 5, seed: int = 7
) -> dict[str, Any]:
    """The Phase 1 'done' test for these curves: shipped values equal ``for_assets`` at sampled cells."""
    import json
    import math
    import random

    shipped = json.loads(shipped_json.read_text())
    tabulated = shipped["kinds"].index("tabulated")
    candidates = [i for i, p in enumerate(shipped["params"]) if p[0] != tabulated]
    chosen = random.Random(seed).sample(candidates, min(sample, len(candidates)))
    assets = pa.table(
        {
            "asset_id": [f"cell-{i}" for i in chosen],
            "cell_index": pa.array([int(shipped["cells"][i], 16) for i in chosen], pa.uint64()),
        }
    )
    periods = shipped["return_periods"]
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "eval.parquet"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            HazardDataset.local(dataset_path).for_assets(assets).return_periods(
                periods
            ).write_parquet(target)
        rows = pq.read_table(target).to_pylist()
    index = {cell: i for i, cell in enumerate(shipped["cells"])}
    checked, mismatches = 0, []
    for row in rows:
        ours = shipped["values"][index[f"{row['cell_index']:x}"]]
        for rp, mine in zip(periods, ours, strict=True):
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
                        "cell": f"{row['cell_index']:x}",
                        "rp": rp,
                        "shipped": mine,
                        "for_assets": theirs,
                    }
                )
    return {
        "hazard": shipped["hazard"],
        "cells": len(chosen),
        "values_checked": checked,
        "mismatches": mismatches,
    }
