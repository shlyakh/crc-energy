"""IBTrACS read from NOAA's CSV files with the standard library only.

This is the independent side of the comparison: it must not import the framework under
test, nor pyarrow, which the framework uses to parse the same file. The rules applied to
each value are arguments so that a test can make one of them deliberately wrong.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = (
    "https://www.ncei.noaa.gov/data/"
    "international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv"
)
USER_AGENT = "data-source-check"

Row = list[str | None]


def url(subset: str) -> str:
    """The file name as crc-sdk's documentation and NOAA's directory both spell it."""
    return f"{ROOT}/ibtracs.{subset}.list.v04r01.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def status(subset: str) -> int:
    """HTTP status of a HEAD request for the subset's file."""
    request = Request(url(subset), method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=60) as response:
            return int(response.status)
    except HTTPError as error:
        return int(error.code)


def directory_listing() -> list[str]:
    """File names in NOAA's CSV directory (from its HTML index)."""
    request = Request(f"{ROOT}/", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        html = response.read().decode("utf-8", "replace")
    names = []
    for part in html.split('href="')[1:]:
        name = part.split('"', 1)[0]
        if name.endswith(".csv"):
            names.append(name)
    return sorted(set(names))


def download(subset: str, cache_dir: Path, *, live: bool) -> dict[str, Any]:
    """Fetch the subset's file (``live``) or reuse the cached copy; return its provenance."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{subset}.csv"
    sidecar = cache_dir / f"{subset}.json"
    if not live:
        if not (path.exists() and sidecar.exists()):
            raise FileNotFoundError(
                f"no cached reference copy of IBTrACS {subset}; run with --live"
            )
        record = json.loads(sidecar.read_text(encoding="utf-8"))
        if sha256(path) != record["sha256"]:
            raise RuntimeError(f"cached reference copy of IBTrACS {subset} has changed on disk")
        return record | {"path": str(path)}
    request = Request(url(subset), headers={"User-Agent": USER_AGENT})
    fd, name = tempfile.mkstemp(dir=cache_dir, prefix="download-", suffix=".tmp")
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as target, urlopen(request, timeout=300) as response:
            while chunk := response.read(1 << 20):
                target.write(chunk)
            headers = response.headers
            record = {
                "url": url(subset),
                "retrieved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "etag": headers.get("ETag"),
                "last_modified": headers.get("Last-Modified"),
                "content_length": headers.get("Content-Length"),
            }
        record["bytes"] = temp.stat().st_size
        if (
            record["content_length"] is not None
            and int(record["content_length"]) != record["bytes"]
        ):
            raise RuntimeError(f"incomplete download of IBTrACS {subset}")
        record["sha256"] = sha256(temp)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    sidecar.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return record | {"path": str(path)}


def header(path: Path) -> tuple[list[str], list[str]]:
    """Column names (first line) and units (second line)."""
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.reader(source)
        return next(reader), next(reader)


def rows(path: Path, *, trim: bool = True, empty_as_null: bool = True) -> Iterator[Row]:
    """Data rows in file order, after the two rules crc-sdk states.

    ``trim``: leading and trailing whitespace is removed from every value.
    ``empty_as_null``: a value that is then empty becomes ``None``.
    """
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.reader(source)
        next(reader)
        next(reader)
        for raw in reader:
            values: Iterable[str] = (value.strip() for value in raw) if trim else raw
            yield [None if empty_as_null and value == "" else value for value in values]


def select(
    data: Iterable[Row],
    columns: Sequence[str],
    *,
    storm_ids: Sequence[str] | None = None,
    seasons: tuple[int, int] | None = None,
) -> Iterator[Row]:
    """Rows of the given storms (by ``SID``) and of seasons in an inclusive range."""
    sid, season = columns.index("SID"), columns.index("SEASON")
    wanted = set(storm_ids) if storm_ids is not None else None
    for row in data:
        if wanted is not None and row[sid] not in wanted:
            continue
        if seasons is not None:
            value = row[season]
            if value is None or not seasons[0] <= int(value) <= seasons[1]:
                continue
        yield row


def explore(path: Path) -> dict[str, Any]:
    """Counts that describe one file: size, coverage in time and space, missing values."""
    columns, units = header(path)
    index = {name: position for position, name in enumerate(columns)}
    missing = [0] * len(columns)
    widths: Counter[int] = Counter()
    storms_by_season: dict[int, set[str]] = {}
    points_by_season: Counter[int] = Counter()
    track_types: Counter[str] = Counter()
    basins: Counter[str] = Counter()
    storms: set[str] = set()
    trimmed = total = blank_season = 0
    first_time = last_time = None
    lat_range = [None, None]
    lon_range = [None, None]
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.reader(source)
        next(reader)
        next(reader)
        for raw in reader:
            total += 1
            widths[len(raw)] += 1
            for position, value in enumerate(raw[: len(columns)]):
                stripped = value.strip()
                if stripped != value:
                    trimmed += 1
                if stripped == "":
                    missing[position] += 1
            if len(raw) != len(columns):
                continue
            sid = raw[index["SID"]].strip()
            storms.add(sid)
            season = raw[index["SEASON"]].strip()
            if season == "":
                blank_season += 1
            else:
                storms_by_season.setdefault(int(season), set()).add(sid)
                points_by_season[int(season)] += 1
            if "TRACK_TYPE" in index:
                track_types[raw[index["TRACK_TYPE"]].strip()] += 1
            if "BASIN" in index:
                basins[raw[index["BASIN"]].strip()] += 1
            time = raw[index["ISO_TIME"]].strip()
            if time:
                first_time = time if first_time is None or time < first_time else first_time
                last_time = time if last_time is None or time > last_time else last_time
            for name, span in (("LAT", lat_range), ("LON", lon_range)):
                text = raw[index[name]].strip() if name in index else ""
                if text:
                    number = float(text)
                    span[0] = number if span[0] is None or number < span[0] else span[0]
                    span[1] = number if span[1] is None or number > span[1] else span[1]
    seasons = sorted(storms_by_season)
    return {
        "rows": total,
        "columns": len(columns),
        "storms": len(storms),
        "seasons": [seasons[0], seasons[-1]] if seasons else None,
        "first_time": first_time,
        "last_time": last_time,
        "lat_range": lat_range,
        "lon_range": lon_range,
        "rows_with_wrong_field_count": total - widths.get(len(columns), 0),
        "rows_with_blank_season": blank_season,
        "values_with_outer_whitespace": trimmed,
        "values_empty_after_trim": sum(missing),
        "values_total": total * len(columns),
        "track_types": dict(sorted(track_types.items())),
        "basins": dict(sorted(basins.items())),
        "storms_by_season": [[season, len(storms_by_season[season])] for season in seasons],
        "points_by_season": [[season, points_by_season[season]] for season in seasons],
        "missing_by_column": [
            {"column": name, "unit": unit.strip(), "missing": count}
            for name, unit, count in zip(columns, units, missing, strict=True)
        ],
    }


def storm_seasons(path: Path) -> dict[str, int]:
    """Season of each storm (``SID``), from the first row that carries one."""
    columns, _ = header(path)
    sid, season = columns.index("SID"), columns.index("SEASON")
    out: dict[str, int] = {}
    for row in rows(path):
        if row[sid] is not None and row[season] is not None and row[sid] not in out:
            out[row[sid]] = int(row[season])  # type: ignore[arg-type,index]
    return out
