"""ERA5 annual extremes recomputed from a public Zarr copy, object by object.

crc-sdk opens the store with zarr over gcsfs and lets numcodecs (c-blosc) decompress each
chunk. Here every object is downloaded whole over HTTPS and checksummed, the Zarr version 2
metadata is read as JSON, and the chunks are decoded by the Blosc container and LZ4 block
decoder written below, with the standard library only. The two sides therefore share the
publisher's bytes and nothing else. The time axis, the selection of grid cells, the daily
aggregation and the annual statistic are applied in plain Python, one grid cell at a time.

The downloaded objects keep the store's own layout under ``<cache>/reference/<store>/``, so
that folder is also a readable Zarr copy of exactly the bytes that were checksummed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import tempfile
import threading
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

USER_AGENT = "data-source-check"
HTTPS = "https://storage.googleapis.com/"
#: store name -> the address crc-sdk states for it (crc_sdk/providers/era5.py:88-107)
STORES = {
    "wb2-1p5": (
        "gs://weatherbench2/datasets/era5/"
        "1959-2022-1h-240x121_equiangular_with_poles_conservative.zarr"
    ),
}
#: recipe -> (array in the store, unit the conversion assumes, unit of the result, kind)
RECIPES = {
    "txx": ("2m_temperature", "K", "degC", "temperature"),
    "tnn": ("2m_temperature", "K", "degC", "temperature"),
    "rx1day": ("total_precipitation", "m", "mm/day", "rain"),
    "rx5day": ("total_precipitation", "m", "mm", "rain"),
}
LAND_MASK = "land_sea_mask"
HOURS_PER_DAY = 24  # the stores are hourly
DOWNLOAD_WORKERS = 16


@dataclass(frozen=True)
class Rules:
    """The rules as crc-sdk's code states them (see the statement in the source file)."""

    kelvin_offset: float = -273.15
    metres_to_mm: float = 1000.0
    #: rain is stamped at the end of its hour: the stamp, less one hour, gives its day
    interval_end_stamps: bool = True
    day_fraction_temperature: float = 0.75  # 18 of 24 hours
    day_fraction_rain: float = 1.0  # all 24 hours
    year_fraction: float = 0.9
    window_days: int = 5  # rx5day
    half_cell_margin: bool = True  # the box, grown by half a cell, must hold the cell's centre
    land_threshold: float = 0.5
    float32_output: bool = True  # crc-sdk keeps each year's values as 32-bit floats


# --------------------------------------------------------------------------- download


def address(store: str, key: str) -> str:
    return HTTPS + STORES[store].removeprefix("gs://") + "/" + key


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Copy:
    """A checksummed local copy of the objects of one store that the reference has read."""

    def __init__(self, store: str, cache: Path, *, live: bool) -> None:
        self.store = store
        self.root = cache / "reference" / store
        self.listing = cache / "reference" / f"{store}.provenance.json"
        self.live = live
        self._lock = threading.Lock()
        self.records: dict[str, dict[str, Any]] = {}
        if self.listing.exists():
            self.records = json.loads(self.listing.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self.listing.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.listing.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.records, indent=0, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, self.listing)

    def _one(self, key: str) -> dict[str, Any]:
        path = self.root / key
        known = self.records.get(key)
        if known is not None and (known["missing"] or path.exists()):
            if not known["missing"] and path.stat().st_size != known["bytes"]:
                raise RuntimeError(f"cached reference copy of {key} has changed on disk")
            return known
        if not self.live:
            raise FileNotFoundError(f"no cached reference copy of {key}; run with --live")
        url = address(self.store, key)
        record: dict[str, Any] = {
            "url": url,
            "retrieved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "missing": False,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=120) as response:
                data = response.read()
                record["etag"] = response.headers.get("ETag")
                record["last_modified"] = response.headers.get("Last-Modified")
                length = response.headers.get("Content-Length")
            if length is not None and int(length) != len(data):
                raise RuntimeError(f"incomplete download of {key}")
            record["bytes"] = len(data)
            record["sha256"] = sha256_bytes(data)
            fd, name = tempfile.mkstemp(dir=path.parent, prefix="download-", suffix=".tmp")
            with os.fdopen(fd, "wb") as target:
                target.write(data)
            os.replace(name, path)
        except HTTPError as error:
            if error.code != 404:
                raise
            record["missing"] = True  # recorded, not raised
        with self._lock:
            self.records[key] = record
        return record

    def fetch(self, keys: Iterable[str]) -> list[dict[str, Any]]:
        """Download the objects not yet in the copy (or find them there); one record each."""
        keys = list(keys)
        before = len(self.records)
        if len(keys) > 4:
            with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
                out = list(pool.map(self._one, keys))
        else:
            out = [self._one(key) for key in keys]
        if len(self.records) != before:
            self._save()
        return out

    def read(self, key: str) -> bytes | None:
        """The bytes of one object, or None when the store does not hold it (HTTP 404)."""
        record = self.fetch([key])[0]
        return None if record["missing"] else (self.root / key).read_bytes()

    def text(self, key: str, *, optional: bool = False) -> Any:
        """A JSON object of the store. Attribute objects are optional in Zarr version 2."""
        data = self.read(key)
        if data is None:
            if optional:
                return {}
            raise FileNotFoundError(f"the store has no {key}")
        return json.loads(data)

    def provenance(self, *prefixes: str) -> dict[str, Any]:
        """The objects read whose keys start with one of ``prefixes``, as one input of a check."""
        rows = sorted((k, r) for k, r in self.records.items() if k.startswith(prefixes))
        held = [(k, r) for k, r in rows if not r["missing"]]
        lines = "".join(f"{k} {r['sha256']}\n" for k, r in held)
        stamps = [r["retrieved_at"] for _, r in rows]
        return {
            "url": address(self.store, prefixes[0] if len(prefixes) == 1 else ""),
            "keys_starting_with": list(prefixes),
            "objects": len(held),
            "objects_missing": len(rows) - len(held),
            "bytes": sum(r["bytes"] for _, r in held),
            "sha256": sha256_bytes(lines.encode()),
            "sha256_of": "the lines '<object key> <sha256 of the object>' in key order",
            "retrieved_at": max(stamps, default=None),
            "listing": self.listing.name,
        }


# --------------------------------------------------------------------------- decoding


def lz4_block(source: bytes, size: int) -> bytes:
    """One LZ4 block, decoded as the LZ4 block format describes it."""
    out = bytearray()
    at, end = 0, len(source)
    while at < end:
        token = source[at]
        at += 1
        run = token >> 4
        if run == 15:
            while True:
                more = source[at]
                at += 1
                run += more
                if more != 255:
                    break
        out += source[at : at + run]
        at += run
        if at >= end:
            break  # the last sequence holds literals only
        offset = source[at] | (source[at + 1] << 8)
        at += 2
        length = token & 15
        if length == 15:
            while True:
                more = source[at]
                at += 1
                length += more
                if more != 255:
                    break
        length += 4
        start = len(out) - offset
        if offset == 0 or start < 0:
            raise ValueError("corrupt LZ4 block")
        if offset >= length:
            out += out[start : start + length]
        else:  # the match overlaps what it writes: the pattern repeats
            piece = bytes(out[start:])
            out += (piece * (length // offset + 1))[:length]
    if len(out) != size:
        raise ValueError(f"LZ4 block decoded to {len(out)} bytes, expected {size}")
    return bytes(out)


def blosc_decode(chunk: bytes) -> bytes:
    """A Blosc (version 1 container) buffer holding LZ4 streams, byte-shuffled or not."""
    _version, _lz, flags, typesize, nbytes, blocksize, cbytes = struct.unpack_from(
        "<BBBBIII", chunk
    )
    if cbytes != len(chunk):
        raise ValueError(f"Blosc header states {cbytes} bytes, the object has {len(chunk)}")
    if flags & 0x02:  # stored without compression
        return chunk[16 : 16 + nbytes]
    if flags >> 5 != 1 or flags & 0x04:
        raise ValueError("the reference reader handles LZ4 with byte shuffle only")
    blocks = -(-nbytes // blocksize)
    out = bytearray()
    for number, at in enumerate(struct.unpack_from(f"<{blocks}I", chunk, 16)):
        size = min(blocksize, nbytes - number * blocksize)
        split = not flags & 0x10 and size == blocksize and typesize > 1
        streams = typesize if split else 1
        each = size // streams
        block = bytearray()
        for _ in range(streams):
            (packed,) = struct.unpack_from("<i", chunk, at)
            at += 4
            piece = chunk[at : at + packed]
            block += piece if packed == each else lz4_block(piece, each)
            at += packed
        if flags & 0x01 and typesize > 1:  # undo the byte shuffle
            count = size // typesize
            plain = bytearray(size)
            for byte in range(typesize):
                plain[byte : count * typesize : typesize] = block[byte * count : (byte + 1) * count]
            plain[count * typesize :] = block[count * typesize :]
            block = plain
        out += block
    if len(out) != nbytes:
        raise ValueError("Blosc buffer decoded to the wrong length")
    return bytes(out)


FORMATS = {"<f4": "f", "<f8": "d", "<i8": "q", "<i4": "i"}


def array_meta(copy: Copy, name: str) -> dict[str, Any]:
    """The Zarr version 2 metadata of one array, checked for what this reader can decode."""
    meta = copy.text(f"{name}/.zarray")
    attrs = copy.text(f"{name}/.zattrs", optional=True)
    compressor = meta.get("compressor") or {}
    if (
        meta.get("zarr_format") != 2
        or meta.get("order") != "C"
        or meta.get("filters")
        or meta.get("dtype") not in FORMATS
        or compressor.get("id") != "blosc"
        or compressor.get("cname") != "lz4"
    ):
        raise ValueError(f"{name}: an encoding the reference reader does not handle: {meta}")
    return {
        "name": name,
        "shape": list(meta["shape"]),
        "chunks": list(meta["chunks"]),
        "dtype": meta["dtype"],
        "fill_value": meta.get("fill_value"),
        "dims": list(attrs.get("_ARRAY_DIMENSIONS", ())),
        "attrs": {k: v for k, v in attrs.items() if k != "_ARRAY_DIMENSIONS"},
    }


def chunk_key(meta: dict[str, Any], first: int = 0) -> str:
    """The object holding chunk ``first`` along the first axis (the other axes have one chunk)."""
    if any(meta["shape"][axis] > meta["chunks"][axis] for axis in range(1, len(meta["shape"]))):
        raise ValueError(f"{meta['name']}: more than one chunk along an axis other than the first")
    return f"{meta['name']}/" + ".".join([str(first)] + ["0"] * (len(meta["shape"]) - 1))


def chunk_bytes(copy: Copy, meta: dict[str, Any], first: int = 0) -> bytes | None:
    raw = copy.read(chunk_key(meta, first))
    return None if raw is None else blosc_decode(raw)


def axis_values(copy: Copy, name: str) -> list[Any]:
    """A one-dimensional array, whole."""
    meta = array_meta(copy, name)
    code = FORMATS[meta["dtype"]]
    (length,), (step,) = meta["shape"], meta["chunks"]
    out: list[Any] = []
    for number in range(-(-length // step)):
        data = chunk_bytes(copy, meta, number)
        if data is None:
            raise FileNotFoundError(f"the store has no chunk {number} of {name}")
        out += struct.unpack(f"<{len(data) // struct.calcsize(code)}{code}", data)
    return out[:length]


def time_axis(copy: Copy) -> dict[str, Any]:
    """The time axis as whole hours since its origin; refuses anything but hourly integers."""
    meta = array_meta(copy, "time")
    units = str(meta["attrs"].get("units", ""))
    if not units.startswith("hours since "):
        raise ValueError(f"time units are {units!r}; the reference reader handles hours")
    origin = datetime.fromisoformat(units.removeprefix("hours since ").strip())
    hours = axis_values(copy, "time")
    return {
        "units": units,
        "calendar": meta["attrs"].get("calendar"),
        "origin": origin,
        "hours": hours,
        "index": {hour: position for position, hour in enumerate(hours)},
        "first": (origin + timedelta(hours=hours[0])).isoformat(),
        "last": (origin + timedelta(hours=hours[-1])).isoformat(),
    }


def hours_of(time: dict[str, Any], moment: datetime) -> int:
    return int((moment - time["origin"]) / timedelta(hours=1))


def complete_years(time: dict[str, Any], *, interval_end: bool) -> tuple[int, int]:
    """First and last calendar year of which the time axis holds every hour.

    For a quantity stamped at the end of its hour, the year also needs 00:00 of the next
    1 January, and does not need 00:00 of its own.
    """
    shift = 1 if interval_end else 0
    held = time["index"]
    first_year = (time["origin"] + timedelta(hours=time["hours"][0])).year
    last_year = (time["origin"] + timedelta(hours=time["hours"][-1])).year
    good = []
    for year in range(first_year, last_year + 1):
        start = hours_of(time, datetime(year, 1, 1)) + shift
        stop = hours_of(time, datetime(year + 1, 1, 1)) + shift
        if all(hour in held for hour in range(start, stop)):
            good.append(year)
    return (good[0], good[-1]) if good else (0, 0)


# --------------------------------------------------------------------------- cells


def select_cells(lat: Sequence[float], lon: Sequence[float],
                 bounds: Sequence[float], rules: Rules) -> dict[str, Any]:  # fmt: skip
    """Rows and columns of the grid cells the box selects, columns ordered west to east."""
    west, south, east, north = bounds
    half_lat = abs(lat[1] - lat[0]) / 2 if rules.half_cell_margin else 0.0
    half_lon = abs(lon[1] - lon[0]) / 2 if rules.half_cell_margin else 0.0
    lon180 = [((value + 180.0) % 360.0) - 180.0 for value in lon]
    if west - half_lon <= -180.0 or east + half_lon >= 180.0:
        raise ValueError("the reference reader does not handle a box at the 180 degree meridian")
    rows = [i for i, value in enumerate(lat) if south - half_lat <= value <= north + half_lat]
    cols = sorted(
        (j for j, value in enumerate(lon180) if west - half_lon <= value <= east + half_lon),
        key=lambda j: lon180[j],
    )
    if len(rows) < 2 or len(cols) < 2:
        raise ValueError("the reference reader handles a box of at least two cells each way")
    return {"rows": rows, "cols": cols, "lat": [lat[i] for i in rows],
            "lon": [lon180[j] for j in cols]}  # fmt: skip


def _positions(meta: dict[str, Any], lat_name: str = "latitude",
               lon_name: str = "longitude") -> tuple[int, int]:  # fmt: skip
    """Number of values one step along longitude and latitude skips, within one time step."""
    dims = meta["dims"]
    if dims[-2:] == [lon_name, lat_name]:
        return meta["chunks"][-1], 1
    if dims[-2:] == [lat_name, lon_name]:
        return 1, meta["chunks"][-1]
    raise ValueError(f"{meta['name']}: dimensions are {dims}")


def land_mask(copy: Copy, cells: dict[str, Any], rules: Rules) -> list[list[bool]]:
    """Whether each selected cell counts as land: mask value at or above the threshold."""
    meta = array_meta(copy, LAND_MASK)
    if len(meta["dims"]) != 2:
        raise ValueError("the reference reader handles a land mask without a time axis")
    data = chunk_bytes(copy, meta)
    if data is None:
        raise FileNotFoundError("the store has no land mask")
    code = FORMATS[meta["dtype"]]
    values = struct.unpack(f"<{len(data) // struct.calcsize(code)}{code}", data)
    lon_step, lat_step = _positions(meta)
    return [
        [values[j * lon_step + i * lat_step] >= rules.land_threshold for j in cells["cols"]]
        for i in cells["rows"]
    ]


def read_hours(copy: Copy, variable: str, positions: Sequence[int],
               cells: dict[str, Any]) -> dict[int, list[list[float | None]]]:  # fmt: skip
    """Hourly values of the selected cells at the given positions of the time axis.

    ``[row][column]`` per position; None where the value is not finite. A chunk the store
    does not hold reads as the array's fill value, as Zarr defines it.
    """
    meta = array_meta(copy, variable)
    if meta["dims"][0] != "time" or meta["dtype"] != "<f4":
        raise ValueError(f"{variable}: dimensions {meta['dims']}, type {meta['dtype']}")
    fill = meta["fill_value"]
    if fill not in ("NaN", None):
        raise ValueError(f"{variable}: fill value {fill!r} is not handled")
    lon_step, lat_step = _positions(meta)
    per_step = meta["chunks"][1] * meta["chunks"][2]
    length = meta["chunks"][0]
    wanted: dict[int, list[int]] = {}
    for position in positions:
        wanted.setdefault(position // length, []).append(position)
    copy.fetch(chunk_key(meta, number) for number in sorted(wanted))
    out: dict[int, list[list[float | None]]] = {}
    for number, members in sorted(wanted.items()):
        data = chunk_bytes(copy, meta, number)
        for position in members:
            if data is None:
                out[position] = [[None] * len(cells["cols"]) for _ in cells["rows"]]
                continue
            base = (position - number * length) * per_step
            grid = []
            for i in cells["rows"]:
                row: list[float | None] = []
                for j in cells["cols"]:
                    at = 4 * (base + j * lon_step + i * lat_step)
                    (value,) = struct.unpack_from("<f", data, at)
                    row.append(value if math.isfinite(value) else None)
                grid.append(row)
            out[position] = grid
    return out


# --------------------------------------------------------------------------- reduction


def _needed(fraction: float, expected: int) -> int:
    return max(1, math.ceil(fraction * expected - 1e-9))


def to_float32(value: float) -> float:
    return float(struct.unpack("<f", struct.pack("<f", value))[0])


def daily_value(samples: Sequence[float | None], recipe: str, rules: Rules) -> float | None:
    """One day's hourly samples (already converted, in time order; None = missing)."""
    kind = RECIPES[recipe][3]
    fraction = rules.day_fraction_rain if kind == "rain" else rules.day_fraction_temperature
    valid = [value for value in samples if value is not None]
    if len(valid) < _needed(fraction, HOURS_PER_DAY):
        return None
    if kind == "rain":
        total = 0.0
        for value in valid:  # summed in time order
            total += value
        return total
    return max(valid) if recipe == "txx" else min(valid)


def annual_value(days: Sequence[float | None], recipe: str, rules: Rules) -> float | None:
    """A year of daily values (None = no value for the day), reduced as the recipe states."""
    valid = [value for value in days if value is not None]
    if len(valid) < _needed(rules.year_fraction, len(days)):
        return None
    if recipe == "rx5day":
        width = rules.window_days
        sums = []
        for first in range(len(days) - width + 1):
            window = days[first : first + width]
            if None not in window:
                total = 0.0
                for value in window:
                    total += value  # type: ignore[operator]
                sums.append(total)
        value = max(sums) if sums else None
    else:
        value = min(valid) if recipe == "tnn" else max(valid)
    if value is not None and rules.float32_output:
        value = to_float32(value)
    return value


def annual_rows(copy: Copy, recipe: str, year: int, bounds: Sequence[float], *,
                land_only: bool = False, rules: Rules | None = None,
                time: dict[str, Any] | None = None) -> dict[str, Any]:  # fmt: skip
    """One row per selected grid cell that has an annual value, in the store's row order.

    Also returns what the year looked like: the days each cell had, and the hours read.
    """
    rules = rules or Rules()
    variable, _, unit, kind = RECIPES[recipe]
    time = time or time_axis(copy)
    cells = select_cells(axis_values(copy, "latitude"), axis_values(copy, "longitude"),
                         bounds, rules)  # fmt: skip
    shift = 1 if kind == "rain" and rules.interval_end_stamps else 0
    start = hours_of(time, datetime(year, 1, 1))
    day_count = (datetime(year + 1, 1, 1) - datetime(year, 1, 1)).days
    scale, offset = (rules.metres_to_mm, 0.0) if kind == "rain" else (1.0, rules.kelvin_offset)
    per_day = HOURS_PER_DAY
    held = time["index"]
    stamps = [start + shift + hour for hour in range(day_count * per_day)]
    present = [hour for hour in stamps if hour in held]
    values = read_hours(copy, variable, [held[hour] for hour in present], cells)
    mask = land_mask(copy, cells, rules) if land_only else None

    rows = []
    days_valid: list[int] = []
    for r, lat in enumerate(cells["lat"]):
        for c, lon in enumerate(cells["lon"]):
            days: list[float | None] = []
            for day in range(day_count):
                samples = []
                for hour in range(per_day):
                    stamp = start + shift + day * per_day + hour
                    raw = values[held[stamp]][r][c] if stamp in held else None
                    samples.append(None if raw is None else raw * scale + offset)
                days.append(daily_value(samples, recipe, rules))
            days_valid.append(sum(1 for value in days if value is not None))
            value = annual_value(days, recipe, rules)
            if value is not None and (mask is None or mask[r][c]):
                rows.append({"year": year, "latitude": lat, "longitude": lon, "value": value})
    return {
        "rows": rows,
        "unit": unit,
        "cells": len(cells["lat"]) * len(cells["lon"]),
        "cells_on_land": None if mask is None else sum(sum(row) for row in mask),
        "lat": cells["lat"],
        "lon": cells["lon"],
        "days_in_year": day_count,
        "hours_expected": len(stamps),
        "hours_on_the_time_axis": len(present),
        "days_valid_lowest": min(days_valid),
        "days_valid_highest": max(days_valid),
    }
