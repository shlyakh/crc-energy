"""IBTrACS as crc-sdk delivers it. The only place that calls ``IBTrACSPlan``."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any


def _plan(subset: str, cache_dir: Path, mode: str) -> Any:
    from crc_sdk.workflows import IBTrACSPlan

    return IBTrACSPlan(subset, cache_dir, mode=mode)


def url(subset: str, cache_dir: Path) -> str:
    """The address crc-sdk requests for a subset."""
    return str(_plan(subset, cache_dir, "reuse").url)


def snapshot(subset: str, cache_dir: Path, *, live: bool) -> dict[str, Any]:
    """Fetch (``live``: crc-sdk's ``refresh`` mode) or reuse the snapshot; return its manifest."""
    manifest = dict(_plan(subset, cache_dir, "refresh" if live else "offline").prefetch())
    manifest["path"] = str(cache_dir / "ibtracs" / "v04r01" / subset / "source.csv")
    return manifest


def table(
    subset: str,
    cache_dir: Path,
    *,
    storm_ids: Sequence[str] | None = None,
    seasons: tuple[int, int] | None = None,
) -> tuple[list[str], list[str], dict[str, Any] | None, Iterator[list[str | None]]]:
    """Column names, column types, schema metadata and the rows crc-sdk yields (cache only)."""
    plan = _plan(subset, cache_dir, "offline")
    if storm_ids is not None:
        plan = plan.for_storms(list(storm_ids))
    if seasons is not None:
        plan = plan.years(*seasons)
    batches = plan.batches()
    first = next(batches, None)
    if first is None:
        return [], [], None, iter(())
    names = list(first.schema.names)
    types = [str(field.type) for field in first.schema]
    metadata = dict(first.schema.metadata) if first.schema.metadata else None

    def rows() -> Iterator[list[str | None]]:
        batch = first
        while batch is not None:
            columns = [column.to_pylist() for column in batch.columns]
            yield from (list(values) for values in zip(*columns, strict=True))
            batch = next(batches, None)

    return names, types, metadata, rows()
