"""NEX-GDDP-CMIP6 annual extremes recomputed from NASA's NetCDF files.

The whole file is downloaded and checksummed (crc-sdk reads it by range requests and keeps no
checksum). It is opened with h5py; crc-sdk opens it with h5netcdf, which sits on the same
HDF5 library, so the two sides share the decompression but nothing above it. Attributes,
the calendar, the selection of grid cells and every rule that turns a year of daily values
into one annual value are applied here in plain Python, one grid cell at a time.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ARCHIVE = "https://nex-gddp-cmip6.s3.us-west-2.amazonaws.com/NEX-GDDP-CMIP6"
USER_AGENT = "data-source-check"
#: recipe -> (variable, unit the file must declare, unit of the result)
RECIPES = {
    "txx": ("tasmax", "K", "degC"),
    "tnn": ("tasmin", "K", "degC"),
    "rx1day": ("pr", "kg m-2 s-1", "mm/day"),
    "rx5day": ("pr", "kg m-2 s-1", "mm"),
}


@dataclass(frozen=True)
class Rules:
    """The rules as crc-sdk's documentation and code state them."""

    kelvin_offset: float = -273.15
    seconds_per_day: float = 86400.0
    minimum_valid_fraction: float = 0.9
    window_days: int = 5  # rx5day
    half_cell_margin: bool = (
        True  # a cell is selected when the box, grown by half a cell, holds its centre
    )


def url(variable: str, model: str, scenario: str, member: str, grid: str, year: int,
        version: str) -> str:  # fmt: skip
    suffix = "" if version == "1.0" else f"_v{version}"
    name = f"{variable}_day_{model}_{scenario}_{member}_{grid}_{year}{suffix}.nc"
    return f"{ARCHIVE}/{model}/{scenario}/{member}/{variable}/{name}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def status(address: str) -> int:
    request = Request(address, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=60) as response:
            return int(response.status)
    except HTTPError as error:
        return int(error.code)


def download(address: str, cache_dir: Path, *, live: bool) -> dict[str, Any]:
    """Fetch one file whole, or reuse the cached copy. A 404 is recorded, not raised."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / address.rsplit("/", 1)[-1]
    sidecar = path.with_suffix(".json")
    if sidecar.exists():
        record = json.loads(sidecar.read_text(encoding="utf-8"))
        if record["missing"] or path.exists():
            if not record["missing"] and path.stat().st_size != record["bytes"]:
                raise RuntimeError(f"cached reference copy of {path.name} has changed on disk")
            return record | {"path": str(path)}
    if not live:
        raise FileNotFoundError(f"no cached reference copy of {path.name}; run with --live")
    record: dict[str, Any] = {
        "url": address,
        "retrieved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "missing": False,
    }
    fd, name = tempfile.mkstemp(dir=cache_dir, prefix="download-", suffix=".tmp")
    temp = Path(name)
    try:
        try:
            request = Request(address, headers={"User-Agent": USER_AGENT})
            with os.fdopen(fd, "wb") as target, urlopen(request, timeout=600) as response:
                while chunk := response.read(1 << 20):
                    target.write(chunk)
                record["etag"] = response.headers.get("ETag")
                record["last_modified"] = response.headers.get("Last-Modified")
                length = response.headers.get("Content-Length")
            record["bytes"] = temp.stat().st_size
            if length is not None and int(length) != record["bytes"]:
                raise RuntimeError(f"incomplete download of {path.name}")
            record["sha256"] = sha256(temp)
            os.replace(temp, path)
        except HTTPError as error:
            if error.code != 404:
                raise
            record["missing"] = True
    finally:
        temp.unlink(missing_ok=True)
    sidecar.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return record | {"path": str(path)}


def _text(value: Any) -> str:
    """An attribute as text, whatever form the HDF5 layer hands it over in."""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if hasattr(value, "tolist"):
        value = value.tolist()
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
    return str(value)


#: CF calendar names that mean the same thing (for dates after 1582)
CALENDAR_ALIASES = {
    "standard": "proleptic_gregorian",
    "gregorian": "proleptic_gregorian",
    "365_day": "noleap",
    "366_day": "all_leap",
}


def calendar_name(calendar: str) -> str:
    """One name per calendar, so that aliases compare equal."""
    return CALENDAR_ALIASES.get(calendar, calendar)


def _days_in_year(calendar: str, year: int) -> int:
    if calendar in ("noleap", "365_day"):
        return 365
    if calendar == "360_day":
        return 360
    if calendar in ("all_leap", "366_day"):
        return 366
    if calendar in ("standard", "gregorian", "proleptic_gregorian"):
        return 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
    raise ValueError(f"calendar {calendar!r} is not handled by the reference reader")


def _day_number(calendar: str, year: int, month: int, day: int) -> int:
    """Days since year 1, January 1, in the given calendar."""
    if calendar in ("standard", "gregorian", "proleptic_gregorian"):
        return date(year, month, day).toordinal() - 1
    if calendar == "360_day":
        return (year - 1) * 360 + (month - 1) * 30 + (day - 1)
    lengths = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if calendar in ("all_leap", "366_day"):
        lengths[1] = 29
    return (year - 1) * sum(lengths) + sum(lengths[: month - 1]) + (day - 1)


def read_box(path: Path, variable: str, bounds: tuple[float, float, float, float],
             year: int, rules: Rules | None = None) -> dict[str, Any]:  # fmt: skip
    """The file's attributes and, for the grid cells the box selects, a year of daily values."""
    import h5py

    rules = rules or Rules()
    with h5py.File(path, "r") as file:
        attrs = {key: _text(value) for key, value in file.attrs.items()}
        data = file[variable]
        var_attrs = {
            key: _text(value)
            for key, value in data.attrs.items()
            if key not in ("DIMENSION_LIST", "REFERENCE_LIST")
        }
        dims = [_text(file[ref[0]].name).lstrip("/") for ref in data.attrs["DIMENSION_LIST"]]
        if dims != ["time", "lat", "lon"]:
            raise ValueError(f"{path.name}: dimensions are {dims}, expected time, lat, lon")
        lat = [float(v) for v in file["lat"][:]]
        lon = [float(v) for v in file["lon"][:]]
        time = file["time"]
        calendar = _text(time.attrs["calendar"])
        time_units = _text(time.attrs["units"])
        stamps = [float(v) for v in time[:]]
        fills = set()
        for key in ("_FillValue", "missing_value"):
            if key in data.attrs:
                fills.update(float(v) for v in data.attrs[key].reshape(-1))
        half_lat = abs(lat[1] - lat[0]) / 2 if rules.half_cell_margin else 0.0
        half_lon = abs(lon[1] - lon[0]) / 2 if rules.half_cell_margin else 0.0
        lon180 = [((v + 180.0) % 360.0) - 180.0 for v in lon]
        west, south, east, north = bounds
        rows = [i for i, v in enumerate(lat) if south - half_lat <= v <= north + half_lat]
        cols = sorted(
            (j for j, v in enumerate(lon180) if west - half_lon <= v <= east + half_lon),
            key=lambda j: lon180[j],
        )
        if not rows or not cols:
            raise ValueError("the box selects no grid cell")
        if cols != list(range(cols[0], cols[-1] + 1)) or rows != list(range(rows[0], rows[-1] + 1)):
            raise ValueError("the reference reader handles a box that does not cross the seam")
        block = data[:, rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]
        dtype = str(data.dtype)
        values = block.astype("float64").tolist()  # the stored float32 values, exactly

    if not time_units.startswith("days since "):
        raise ValueError(f"{path.name}: time units are {time_units!r}")
    origin = time_units.removeprefix("days since ").split()[0]
    oy, om, od = (int(part) for part in origin.split("-"))
    start = _day_number(calendar, year, 1, 1)
    offsets = [math.floor(_day_number(calendar, oy, om, od) + stamp) - start for stamp in stamps]
    return {
        "attrs": attrs,
        "variable_attrs": var_attrs,
        "dtype": dtype,
        "calendar": calendar,
        "days_expected": _days_in_year(calendar, year),
        "day_offsets": offsets,  # position of each time step within the year, 0 = January 1
        "lat": [lat[i] for i in rows],
        "lon": [lon180[j] for j in cols],
        "fills": sorted(fills),
        "values": values,  # [time][row][column]
        "grid": {"rows": len(lat), "columns": len(lon), "step_lat": abs(lat[1] - lat[0]),
                 "step_lon": abs(lon[1] - lon[0])},
    }  # fmt: skip


def annual_value(series: list[float | None], recipe: str, days_expected: int,
                 rules: Rules | None = None) -> float | None:  # fmt: skip
    """One grid cell's year of daily values (None = missing), reduced as the recipe states."""
    rules = rules or Rules()
    valid = sum(1 for value in series if value is not None)
    needed = max(1, math.ceil(rules.minimum_valid_fraction * days_expected - 1e-9))
    if valid < needed:
        return None
    if recipe in ("txx", "tnn"):
        converted = [None if v is None else v + rules.kelvin_offset for v in series]
    else:
        converted = [None if v is None else v * rules.seconds_per_day for v in series]
    if recipe == "rx5day":
        width = rules.window_days
        if len(converted) < width:
            return None
        sums = []
        for first in range(len(converted) - width + 1):
            window = converted[first : first + width]
            if None not in window:
                total = 0.0
                for value in window:  # summed in order
                    total += value  # type: ignore[operator]
                sums.append(total)
        return max(sums) if sums else None
    present = [value for value in converted if value is not None]
    return min(present) if recipe == "tnn" else max(present)


def annual_rows(box: dict[str, Any], recipe: str, year: int,
                rules: Rules | None = None) -> list[dict[str, Any]]:  # fmt: skip
    """One row per grid cell that has an annual value, ordered south to north, west to east."""
    fills = set(box["fills"])
    expected = box["days_expected"]
    out = []
    for i, lat in enumerate(box["lat"]):
        for j, lon in enumerate(box["lon"]):
            series: list[float | None] = [None] * expected
            for step, offset in enumerate(box["day_offsets"]):
                value = box["values"][step][i][j]
                if 0 <= offset < expected and value not in fills and math.isfinite(value):
                    series[offset] = value
            value = annual_value(series, recipe, expected, rules)
            if value is not None:
                out.append({"year": year, "latitude": lat, "longitude": lon, "value": value})
    return out
