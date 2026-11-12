"""NOAA extreme water levels as crc-sdk delivers them.

The only place that calls ``NOAAExtremeWaterLevelPlan``. Everything returned is plain Python.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

RESOURCES = ("station", "levels", "annuals")


def _plan(station: str, cache_dir: Path, mode: str, sha256: Mapping[str, str] | None = None) -> Any:
    from crc_sdk.workflows import NOAAExtremeWaterLevelPlan

    return NOAAExtremeWaterLevelPlan.for_station(station).cache(cache_dir, mode=mode, sha256=sha256)


def accepts(station: str) -> bool:
    """Whether crc-sdk takes this text as a station id (no request is made)."""
    from crc_sdk.workflows import NOAAExtremeWaterLevelPlan

    try:
        NOAAExtremeWaterLevelPlan.for_station(station)
    except ValueError:
        return False
    return True


def urls(station: str, cache_dir: Path) -> dict[str, str]:
    """The three addresses crc-sdk says it requests (``explain()``; no request is made)."""
    return dict(_plan(station, cache_dir, "reuse").explain()["urls"])


def snapshot(station: str, cache_dir: Path, *, live: bool) -> dict[str, Any]:
    """Fetch (``live``: crc-sdk's ``refresh`` mode) or reuse the three responses.

    Returns ``{"refused": message}`` when crc-sdk raises ValueError, otherwise the manifest
    and the path of each cached response.
    """
    plan = _plan(station, cache_dir, "refresh" if live else "offline")
    try:
        manifests = plan.prefetch()
    except ValueError as error:
        folder = cache_dir / "noaa-extreme-water-levels" / station
        return {
            "refused": str(error),
            "responses_cached": len(list(folder.rglob("source.json"))) if folder.exists() else 0,
        }
    offline = _plan(station, cache_dir, "offline")
    return {
        "manifests": {name: dict(manifests[name]) for name in RESOURCES},
        "paths": {name: str(offline._directory(name) / "source.json") for name in RESOURCES},
    }


def _table(table: Any) -> dict[str, Any]:
    metadata = table.schema.metadata
    return {
        "columns": list(table.schema.names),
        "types": [str(field.type) for field in table.schema],
        "metadata": {k.decode(): v.decode() for k, v in metadata.items()} if metadata else None,
        "rows": [list(row.values()) for row in table.to_pylist()],
    }


def tables(station: str, cache_dir: Path) -> dict[str, Any]:
    """The two tables and the info dictionary crc-sdk gives, from its cache only."""
    plan = _plan(station, cache_dir, "offline")
    return {
        "levels": _table(plan.source_levels()),
        "annuals": _table(plan.annual_extremes()),
        "info": dict(plan.source_info()),
    }


def pinned(station: str, cache_dir: Path, sha256: Mapping[str, str]) -> str | None:
    """None when crc-sdk serves the cached responses under these digests, else its error."""
    try:
        _plan(station, cache_dir, "offline", sha256).source_levels()
    except RuntimeError as error:
        return str(error)
    return None
