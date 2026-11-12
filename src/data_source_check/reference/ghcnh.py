"""GHCNh annual temperature extremes recomputed from NOAA's per-station, per-year files.

Two readers, neither of which uses the framework or pyarrow (the framework's parser):

- ``read_psv``: NOAA's pipe-separated file, with the standard library only;
- ``read_parquet``: NOAA's Parquet file, through DuckDB's own Parquet reader, returning plain
  Python rows. (crc-sdk also uses DuckDB, but to aggregate batches it parsed with pyarrow;
  the SQL here only selects columns.)

Every rule that turns hourly reports into an annual value is applied in Python in
``annual_row``. The rules are an argument so that a test can make one deliberately wrong.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import tempfile
from calendar import isleap
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = "https://noaa-ghcnh-pds.s3.amazonaws.com/hourly/access/by-year"
USER_AGENT = "data-source-check"
COLUMNS = (
    "STATION",
    "DATE",
    "LATITUDE",
    "LONGITUDE",
    "ELEVATION",
    "temperature",
    "temperature_Quality_Code",
    "temperature_Source_Code",
)
#: (station, time text, latitude, longitude, elevation, temperature, quality code, source code)
Report = tuple[Any, Any, Any, Any, Any, Any, Any, Any]


@dataclass(frozen=True)
class Rules:
    """The rules as crc-sdk's documentation and code state them (defaults)."""

    quality_codes: tuple[str, ...] = ("", "1", "5")
    #: source codes for which quality code "5" is accepted
    sources_for_5: tuple[str, ...] = ("313", "314", "315", "322", "335", "343", "344", "346")
    #: source codes for which quality code "1" is accepted
    sources_for_1: tuple[str, ...] = (
        "313", "314", "315", "322", "335", "343", "344", "346",
        "220", "221", "222", "223", "347", "348",
    )  # fmt: skip
    lowest: float = -93.2
    highest: float = 61.8
    hours_per_day: int = 18  # ceil(24 * 0.75)
    day_fraction: float = 0.9
    day_offset_hours: int = 0  # days are UTC
    missing_elevation: float = -999.9
    coordinate_tolerance: float = 0.05


def url(station: str, year: int, kind: str) -> str:
    return f"{ROOT}/{year}/{kind}/GHCNh_{station}_{year}.{kind}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(station: str, year: int, kind: str, cache_dir: Path, *, live: bool) -> dict[str, Any]:
    """Fetch one station-year file, or reuse the cached copy. A 404 is recorded, not raised."""
    folder = cache_dir / kind
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"GHCNh_{station}_{year}.{kind}"
    sidecar = folder / f"GHCNh_{station}_{year}.json"
    if sidecar.exists() and (
        not live or path.exists() or json.loads(sidecar.read_text())["missing"]
    ):
        record = json.loads(sidecar.read_text(encoding="utf-8"))
        if not record["missing"] and sha256(path) != record["sha256"]:
            raise RuntimeError(f"cached reference copy of {path.name} has changed on disk")
        return record | {"path": str(path)}
    if not live:
        raise FileNotFoundError(f"no cached reference copy of {path.name}; run with --live")
    address = url(station, year, kind)
    record: dict[str, Any] = {
        "url": address,
        "retrieved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "missing": False,
    }
    fd, name = tempfile.mkstemp(dir=folder, prefix="download-", suffix=".tmp")
    temp = Path(name)
    try:
        try:
            request = Request(address, headers={"User-Agent": USER_AGENT})
            with os.fdopen(fd, "wb") as target, urlopen(request, timeout=300) as response:
                while chunk := response.read(1 << 20):
                    target.write(chunk)
                record["etag"] = response.headers.get("ETag")
                record["last_modified"] = response.headers.get("Last-Modified")
            record["bytes"] = temp.stat().st_size
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


def _number(text: str) -> float | None:
    text = text.strip()
    return float(text) if text else None


def read_psv(path: Path) -> Iterator[Report]:
    """Reports from NOAA's pipe-separated file (standard library only)."""
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.reader(source, delimiter="|")
        head = next(reader)
        index = [head.index(name) for name in COLUMNS]
        for row in reader:
            station, time, lat, lon, elevation, value, quality, code = (row[i] for i in index)
            yield (
                station,
                time,
                _number(lat),
                _number(lon),
                _number(elevation),
                _number(value),
                quality,
                code,
            )


def read_parquet(path: Path) -> list[Report]:
    """Reports from NOAA's Parquet file, read by DuckDB into plain Python rows."""
    import duckdb

    with duckdb.connect() as con:
        columns = ", ".join(f'"{name}"' for name in COLUMNS)
        return con.execute(f"SELECT {columns} FROM read_parquet(?)", [str(path)]).fetchall()


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def accepted(value: Any, quality: Any, code: Any, rules: Rules) -> tuple[bool, str]:
    """Whether a report's temperature is used, and if not, the first rule that excludes it."""
    if value is None:
        return False, "no temperature"
    flag, source = _text(quality), _text(code)
    if flag not in rules.quality_codes:
        return False, "quality code not accepted"
    if flag == "1" and source not in rules.sources_for_1:
        return False, "quality code 1 from a source not accepted"
    if flag == "5" and source not in rules.sources_for_5:
        return False, "quality code 5 from a source not accepted"
    if not math.isfinite(value):
        return False, "not a finite number"
    if not rules.lowest <= value <= rules.highest:
        return False, "outside the physical range"
    return True, ""


def empty_row(station: str, year: int) -> dict[str, Any]:
    """The annual row for a station-year NOAA has no file for."""
    return {
        "station": station, "year": year, "latitude": None, "longitude": None,
        "elevation": None, "valid_days": 0, "expected_days": 366 if isleap(year) else 365,
        "accepted_reports": 0, "reports": 0, "value_max": None, "value_min": None,
        "complete": False, "error": "", "excluded": {},
    }  # fmt: skip


def annual_row(
    reports: Iterable[Report], station: str, year: int, rules: Rules | None = None
) -> dict[str, Any]:
    """One station-year reduced to its annual maximum and minimum, with the audit counts."""
    rules = rules or Rules()
    out = empty_row(station, year)
    days: dict[Any, dict[str, Any]] = {}
    lats: list[float] = []
    lons: list[float] = []
    elevations: list[float] = []
    excluded: Counter[str] = Counter()
    shift = timedelta(hours=rules.day_offset_hours)
    for name, time, lat, lon, elevation, value, quality, code in reports:
        if name != station or not time:
            continue
        try:
            moment = datetime.fromisoformat(str(time))
        except ValueError:
            continue
        if moment.year != year:
            continue
        moment += shift
        day = days.setdefault(
            moment.date(), {"reports": 0, "hours": set(), "values": [], "lat": False, "lon": False}
        )
        day["reports"] += 1
        if lat is not None:
            day["lat"] = True
            lats.append(lat)
        if lon is not None:
            day["lon"] = True
            lons.append(lon)
        if elevation is not None and elevation != rules.missing_elevation:
            elevations.append(elevation)
        ok, reason = accepted(value, quality, code, rules)
        if ok:
            day["values"].append(value)
            day["hours"].add(moment.replace(minute=0, second=0, microsecond=0))
        else:
            excluded[reason] += 1
    out["excluded"] = dict(sorted(excluded.items()))
    if not days:
        out["error"] = "no matching observations"
        return out
    out["reports"] = sum(day["reports"] for day in days.values())
    out["accepted_reports"] = sum(len(day["values"]) for day in days.values())
    if not all(day["lat"] and day["lon"] for day in days.values()):
        out["error"] = "missing coordinates"
        return out
    out["latitude"], out["longitude"] = min(lats), min(lons)
    out["elevation"] = min(elevations, default=None)
    if (
        not -90 <= out["latitude"] <= 90
        or not -180 <= out["longitude"] <= 180
        or max(lats) - min(lats) > rules.coordinate_tolerance
        or max(lons) - min(lons) > rules.coordinate_tolerance
    ):
        out["error"] = "invalid or moving coordinates"
        return out
    valid = [day for day in days.values() if len(day["hours"]) >= rules.hours_per_day]
    out["valid_days"] = len(valid)
    out["complete"] = len(valid) >= math.ceil(out["expected_days"] * rules.day_fraction)
    if out["complete"]:
        out["value_max"] = max(max(day["values"]) for day in valid)
        out["value_min"] = min(min(day["values"]) for day in valid)
    return out


def station_year(
    station: str, year: int, kind: str, cache_dir: Path, *, live: bool, rules: Rules | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The annual row recomputed from one file of the given kind, and the file's provenance."""
    provenance = download(station, year, kind, cache_dir, live=live)
    if provenance["missing"]:
        return empty_row(station, year), provenance
    path = Path(provenance["path"])
    reports = read_psv(path) if kind == "psv" else read_parquet(path)
    return annual_row(reports, station, year, rules), provenance
