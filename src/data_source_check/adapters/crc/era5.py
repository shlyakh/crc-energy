"""ERA5 as crc-sdk delivers it. The only place that calls ``HazardDataset.era5``.

Every function returns plain Python values. ``annual`` can point crc-sdk at a local folder
that holds a copy of the store's objects (``store_copy``) instead of the network: crc-sdk's
own code then reads, with zarr, the very bytes the reference reader checksummed. Its store
address is replaced for the length of that call and nothing else is changed.
"""

from __future__ import annotations

import tempfile
import threading
import warnings
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

VALUE_COLUMNS = ("year", "latitude", "longitude", "value")
_LOCK = threading.Lock()


@contextmanager
def _store_at(name: str, folder: Path | None):  # noqa: ANN202
    """Within the block, crc-sdk's store ``name`` is read from ``folder`` (None: unchanged)."""
    from crc_sdk.providers import era5

    if folder is None:
        yield
        return
    with _LOCK:
        original = era5.ERA5_STORES[name]
        era5.ERA5_STORES[name] = replace(original, url=str(folder), storage_options={})
        try:
            yield
        finally:
            era5.ERA5_STORES[name] = original


def _stamp(value: Any) -> str:
    return str(value)[:19]


def facts(store: str) -> dict[str, Any]:
    """What crc-sdk states about a store, and what it reads from it when it opens it."""
    from crc_sdk.providers.era5 import ERA5_RECIPES, ERA5Provider, era5_store

    declared = era5_store(store)
    provider = ERA5Provider(declared)
    group = provider.group
    coverage = provider.coverage()
    times = provider.times
    arrays = {}
    for name in sorted({*declared.variables.values(), declared.land_sea_mask or ""} - {""}):
        array = group[name]
        arrays[name] = {
            "dims": list(array.attrs.get("_ARRAY_DIMENSIONS", ())),
            "shape": [int(n) for n in array.shape],
            "chunks": [int(n) for n in array.chunks],
            "dtype": str(array.dtype.str),
        }
    return {
        "store": declared.name,
        "url": declared.url,
        "variables": dict(declared.variables),
        "recipe_variables": {
            name: declared.variables[recipe.variable] for name, recipe in ERA5_RECIPES.items()
        },
        "recipe_units": {name: recipe.unit for name, recipe in ERA5_RECIPES.items()},
        "version": provider.resolve_version("latest"),
        "first_year": coverage.first_year,
        "last_final_date": str(coverage.last_final_date),
        "group_attributes": sorted(dict(group.attrs)),
        "time_count": int(times.size),
        "time_first": _stamp(times[0]),
        "time_last": _stamp(times[-1]),
        "latitude": [float(v) for v in group[declared.lat_name][:]],
        "longitude": [float(v) for v in group[declared.lon_name][:]],
        "arrays": arrays,
    }


def accepted_years(store: str, recipe: str, years: Sequence[int]) -> dict[str, str]:
    """For each year, "" when crc-sdk accepts it for the recipe, else the error it raises."""
    from crc_sdk.providers.era5 import ERA5Provider, era5_recipe, era5_store

    provider = ERA5Provider(era5_store(store))
    out = {}
    for year in years:
        try:
            provider.check_years([year], era5_recipe(recipe))
            out[str(year)] = ""
        except ValueError as error:
            out[str(year)] = str(error)
    return out


def hours(store: str, variable: str, first: int, count: int) -> dict[str, Any]:
    """``count`` time steps of one array from position ``first``, through crc-sdk's own handle.

    The values are returned as the hexadecimal text of little-endian 32-bit floats in the
    array's own axis order, so that they can be compared bit for bit.
    """
    import numpy as np
    from crc_sdk.providers.era5 import ERA5Provider, era5_store

    provider = ERA5Provider(era5_store(store))
    array = provider.group[variable]
    block = np.asarray(array[first : first + count])
    return {
        "variable": variable,
        "first": first,
        "count": int(block.shape[0]),
        "shape": [int(n) for n in block.shape],
        "dtype": str(array.dtype.str),
        "values_hex": np.ascontiguousarray(block, dtype="<f4").tobytes().hex(),
    }


def annual(recipe: str, store: str, bounds: Sequence[float], years: Sequence[int], *,
           land_only: bool = False, store_copy: Path | None = None) -> dict[str, Any]:  # fmt: skip
    """The rows of ``annual_extremes()`` for one recipe, area and list of years.

    crc-sdk's own cache of annual files is a temporary folder, so every call reduces the
    hourly values again.
    """
    import crc_sdk
    from crc_sdk.workflows import BlockExtremaPolicy, HazardDataset

    out: dict[str, Any] = {
        "request": {"recipe": recipe, "store": store, "bounds": list(bounds),
                    "years": list(years), "land_only": land_only,
                    "read_from": "a local copy of the store's objects" if store_copy
                    else "the network"},
        "crc_sdk_version": getattr(crc_sdk, "__version__", ""),
        "rows": [], "columns": [], "error": "", "error_type": "", "warnings": [],
    }  # fmt: skip
    try:
        with (
            warnings.catch_warnings(record=True) as caught,
            tempfile.TemporaryDirectory(prefix="data-source-check-era5-") as scratch,
            _store_at(store, store_copy),
        ):
            warnings.simplefilter("always")
            plan = (
                HazardDataset.era5(recipe, store=store)
                .for_area(tuple(bounds), land_only=land_only)
                .years(list(years))
                .cache(scratch, mode="reuse")
                .canonicalize(policy=BlockExtremaPolicy.curated(minimum_years=len(years)))
            )
            table = plan.annual_extremes()
            out["columns"] = list(table.schema.names)
            columns = {name: table.column(name).to_pylist() for name in VALUE_COLUMNS}
            out["rows"] = [list(row) for row in zip(*columns.values(), strict=True)]
        out["warnings"] = sorted({f"{w.category.__name__}: {w.message}" for w in caught})
    except Exception as error:  # the error is the result: it is recorded, not hidden
        out["error"], out["error_type"] = str(error), type(error).__name__
    return out
