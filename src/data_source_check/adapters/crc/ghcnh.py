"""GHCNh as crc-sdk delivers it. The only place that calls ``HazardDataset.ghcnh``."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _plan(recipe: str, cache_dir: Path, *, live: bool, workers: int = 8) -> Any:
    from crc_sdk.workflows import HazardDataset

    return (
        HazardDataset.ghcnh(recipe)
        .cache(cache_dir, mode="reuse" if live else "offline")
        .execution(workers=workers)
    )


def defaults() -> dict[str, Any]:
    """The rule values crc-sdk holds, for the record (the reference keeps its own copy)."""
    from crc_sdk.providers import ghcnh

    quality = ghcnh.GHCNhCompleteness()
    return {
        "minimum_hour_fraction": quality.minimum_hour_fraction,
        "minimum_day_fraction": quality.minimum_day_fraction,
        "quality_codes": list(quality.quality_codes),
        "sources_for_5": list(ghcnh.ISD_SOURCES),
        "sources_for_1": list(ghcnh.GOOD_SOURCES),
        "version": ghcnh.VERSION,
        "licence": ghcnh.LICENCE,
    }


def catalogue(bounds: Sequence[float], cache_dir: Path, *, live: bool) -> list[dict[str, Any]]:
    """Stations crc-sdk selects for a box (metadata only)."""
    return list(
        _plan("temperature_max", cache_dir, live=live).for_area(bounds).stations().to_pylist()
    )


def annual(
    recipe: str, stations: Sequence[str], years: tuple[int, int], cache_dir: Path, *, live: bool
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """crc-sdk's annual QA table, one call per station; a station that raises is reported."""
    rows: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for station in stations:
        plan = _plan(recipe, cache_dir, live=live).for_stations([station]).years(*years)
        try:
            rows += plan.annual_extremes().to_pylist()
        except ValueError as error:
            errors[station] = str(error)
    return rows, errors


def curves(
    recipe: str,
    stations: Sequence[str],
    years: tuple[int, int],
    cache_dir: Path,
    output: Path,
    *,
    minimum_years: int,
    live: bool,
) -> dict[str, Any]:
    """Fit and write the curves; return the stations that received one and the file's metadata."""
    from crc_sdk.connectors import read_hazard_dataset, read_hazard_metadata
    from crc_sdk.workflows import BlockExtremaPolicy

    plan = (
        _plan(recipe, cache_dir, live=live)
        .for_stations(list(stations))
        .years(*years)
        .canonicalize(policy=BlockExtremaPolicy.curated(minimum_years=minimum_years))
    )
    plan.materialize(output)
    table = read_hazard_dataset(output).to_pylist()
    meta = read_hazard_metadata(output)
    source = meta.source
    return {
        "stations": sorted(str(row["source_id"]).split(":")[-1] for row in table),
        "families": sorted({str(row.get("curve_type")) for row in table}),
        "kinds": sorted({str(row.get("curve_kind")) for row in table}),
        "unit": meta.value_unit,
        "tail": meta.return_period_tail,
        "probability_semantics": meta.probability_semantics,
        "licence": getattr(source, "licence", None),
        "attribution": getattr(source, "attribution", None),
        "retrieved_at": str(getattr(source, "retrieved_at", "") or ""),
        "checksum": getattr(source, "checksum", None),
        "uri": str(getattr(source, "uri", ""))[:120],
    }
