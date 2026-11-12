"""NOAA CO-OPS extreme water levels read from NOAA's API with the standard library only.

This is the independent side of the comparison: it must not import the framework under
test. Numbers are kept as the decimals NOAA wrote (``decimal.Decimal``), never as binary
floats, so that the comparison can ask whether the framework's float is NOAA's number.
The rules of the transformation statement are an argument (``Rules``) so that a test can
make one of them deliberately wrong.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ENDPOINT = "https://api.tidesandcurrents.noaa.gov/dpapi/prod/webapi/product.json"
USER_AGENT = "data-source-check"
RESOURCES = ("station", "levels", "annuals")

#: Columns of the two tables, as the statement names them, with their types.
LEVEL_COLUMNS = (
    ("station_id", "string"),
    ("station_name", "string"),
    ("longitude", "double"),
    ("latitude", "double"),
    ("datum", "string"),
    ("datum_epoch", "string"),
    ("annual_exceedance_probability", "double"),
    ("published_return_period_years", "double"),
    ("water_level_m", "double"),
    ("lower_90ci_m", "double"),
    ("upper_90ci_m", "double"),
)
ANNUAL_COLUMNS = (
    ("station_id", "string"),
    ("year", "int32"),
    ("detrended_extreme_m", "double"),
    ("datum_label", "string"),
    ("datum_epoch", "string"),
    ("reference_notice", "string"),
)


@dataclass(frozen=True)
class Rules:
    """What the statement says crc-sdk does. A test changes one field to break one rule."""

    station_id_digits: int = 7  # a station id is exactly this many digits 0-9
    units: str = "metric"  # the units asked for in every request
    level_type: str = "high"  # the levelType asked for (levels and annuals)
    required_units: str = "meters"  # the units a response must state
    level_group: str = "GEV_HI"  # the group of the levels response that is delivered
    refuse_without_levels: bool = True  # a station with no entry in that group is refused
    datum_labels_ignore_case: bool = True  # MHHW and mhhw count as the same label
    bounds_must_bracket: bool = True  # lower bound <= level <= upper bound, when present
    levels_datum_from: str = "levels"  # the response whose datum label the levels table shows
    annuals_datum_from: str = "annuals"  # the same for the annual table
    epoch_field: str = "epoch"  # the station field delivered as the datum epoch
    bounds: tuple[str, str] = ("lower90CI", "upper90CI")  # NOAA's fields for the two bounds


DEFAULT = Rules()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def index_url() -> str:
    """NOAA's list of every station that has the product."""
    return f"{ENDPOINT}?name=extremewaterlevels&units=metric"


def url(station: str, resource: str, rules: Rules = DEFAULT) -> str:
    """The address of one of the three responses, written out by hand."""
    base = f"{ENDPOINT}?name=extremewaterlevels&station={station}&units={rules.units}"
    if resource == "station":
        return base
    if resource == "levels":
        return f"{base}&details=exceedancelevels&levelType={rules.level_type}"
    if resource == "annuals":
        return f"{base}&extremeType=annuals&levelType={rules.level_type}"
    raise ValueError(f"unknown resource {resource!r}")


def fetch(address: str, path: Path, *, live: bool) -> dict[str, Any]:
    """Download ``address`` to ``path`` (``live``) or reuse the cached copy; return its provenance.

    An HTTP error is recorded (``status``), not raised; the record then has no ``path``.
    """
    sidecar = path.with_name(path.stem + ".meta.json")
    if not live:
        if not sidecar.exists():
            raise FileNotFoundError(f"no cached reference copy of {address}; run with --live")
        record = json.loads(sidecar.read_text(encoding="utf-8"))
        if record["status"] != 200:
            return record
        if not path.exists() or sha256(path) != record["sha256"]:
            raise RuntimeError(f"cached reference copy {path} is missing or has changed on disk")
        return record | {"path": str(path)}
    path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(address, headers={"User-Agent": USER_AGENT})
    record: dict[str, Any] = {
        "url": address,
        "retrieved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        with urlopen(request, timeout=120) as response:
            raw = response.read()
            headers = response.headers
            record |= {
                "status": int(getattr(response, "status", 200)),
                "etag": headers.get("ETag"),
                "last_modified": headers.get("Last-Modified"),
                "content_length": headers.get("Content-Length"),
            }
    except HTTPError as error:
        record["status"] = int(error.code)
        _write(sidecar, (json.dumps(record, indent=1, sort_keys=True) + "\n").encode())
        return record
    if record["content_length"] is not None and int(record["content_length"]) != len(raw):
        raise RuntimeError(f"incomplete download of {address}")
    _write(path, raw)
    record |= {"bytes": len(raw), "sha256": sha256(path)}
    _write(sidecar, (json.dumps(record, indent=1, sort_keys=True) + "\n").encode())
    return record | {"path": str(path)}


def _write(path: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(dir=path.parent, prefix="download-", suffix=".tmp")
    with os.fdopen(fd, "wb") as target:
        target.write(data)
    os.replace(name, path)


def parse(path: Path) -> Any:
    """The JSON document, with every number that has a decimal point kept as a ``Decimal``."""
    return json.loads(path.read_bytes().decode("utf-8"), parse_float=Decimal)


def download_station(
    station: str, cache_dir: Path, *, live: bool, rules: Rules = DEFAULT
) -> dict[str, dict[str, Any]]:
    """Provenance of the three responses of one station."""
    return {
        resource: fetch(
            url(station, resource, rules), cache_dir / station / f"{resource}.json", live=live
        )
        for resource in RESOURCES
    }


def valid_station_id(text: str, rules: Rules = DEFAULT) -> bool:
    return len(text) == rules.station_id_digits and all(c in "0123456789" for c in text)


def _number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, Decimal) and value.is_finite()


def _text(value: Any) -> bool:
    return isinstance(value, str) and value != ""


def refusal(payloads: dict[str, Any], station: str, rules: Rules = DEFAULT) -> str | None:
    """Why the statement says this station is refused, or None when it is delivered.

    The three responses are judged in the order they are requested; the first rule that
    fails gives the reason.
    """
    listed = payloads["station"]
    entries = listed.get("ExtremeWaterLevels") if isinstance(listed, dict) else None
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        return "station: not exactly one station listed"
    entry = entries[0]
    if entry.get("stationId") != station:
        return "station: another station id"
    lon, lat = entry.get("longitude"), entry.get("latitude")
    if not (_number(lon) and _number(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        return "station: coordinates missing or out of range"
    if not _text(entry.get("epoch")):
        return "station: no epoch"
    for resource in ("levels", "annuals"):
        payload = payloads[resource]
        if not isinstance(payload, dict):
            return f"{resource}: not an object"
        if payload.get("stationId") != station:
            return f"{resource}: no station id, or another one"
        if payload.get("units") != rules.required_units:
            return f"{resource}: units are not {rules.required_units}"
        if not _text(payload.get("datum")):
            return f"{resource}: no datum"
        if resource == "levels":
            reason = _levels_refusal(payload, rules)
        else:
            reason = _annuals_refusal(payload)
        if reason:
            return reason
    a, b = payloads["levels"]["datum"], payloads["annuals"]["datum"]
    if (a.upper() != b.upper()) if rules.datum_labels_ignore_case else (a != b):
        return "datum labels of levels and annuals differ"
    return None


def _levels_refusal(payload: dict[str, Any], rules: Rules) -> str | None:
    group = payload.get(rules.level_group)
    rows = group.get("exceedanceLevels") if isinstance(group, dict) else None
    if not isinstance(rows, list) or not rows:
        return (
            f"levels: no {rules.level_group} exceedance levels"
            if (rules.refuse_without_levels)
            else None
        )
    low_name, high_name = rules.bounds
    seen: set[Any] = set()
    for row in rows:
        p, period, level = row.get("probability"), row.get("returnPeriod"), row.get("level")
        if not _number(p) or not 0 < p <= 1 or p in seen:
            return "levels: probability missing, out of (0, 1] or repeated"
        if not _number(period) or period < 1:
            return "levels: return period missing or below 1"
        if not _number(level):
            return "levels: level missing"
        low, high = row.get(low_name), row.get(high_name)
        for bound in (low, high):
            if bound is not None and not _number(bound):
                return "levels: confidence bound is not a number"
        if rules.bounds_must_bracket and (
            (low is not None and low > level) or (high is not None and high < level)
        ):
            return "levels: confidence bound on the wrong side of the level"
        seen.add(p)
    return None


def _annuals_refusal(payload: dict[str, Any]) -> str | None:
    if not _text(payload.get("notice")):
        return "annuals: no notice"
    if payload.get("trend") is not None and not _number(payload["trend"]):
        return "annuals: trend is not a number"
    rows = payload.get("extremes")
    if not isinstance(rows, list):
        return "annuals: no list of extremes"
    for row in rows:
        year = row.get("year")
        if isinstance(year, bool) or not isinstance(year, int) or not _number(row.get("value")):
            return "annuals: a year is not an integer or a value is not a number"
    return None


def level_rows(payloads: dict[str, Any], station: str, rules: Rules = DEFAULT) -> list[list[Any]]:
    """The rows the statement says ``source_levels()`` gives, in NOAA's order."""
    entry = payloads["station"]["ExtremeWaterLevels"][0]
    group = payloads["levels"].get(rules.level_group) or {}
    low_name, high_name = rules.bounds
    return [
        [
            station,
            entry.get("stationName"),
            entry.get("longitude"),
            entry.get("latitude"),
            payloads[rules.levels_datum_from]["datum"],
            entry.get(rules.epoch_field),
            row["probability"],
            row["returnPeriod"],
            row["level"],
            row.get(low_name),
            row.get(high_name),
        ]
        for row in group.get("exceedanceLevels") or []
    ]


def annual_rows(payloads: dict[str, Any], station: str, rules: Rules = DEFAULT) -> list[list[Any]]:
    """The rows the statement says ``annual_extremes()`` gives, in NOAA's order."""
    entry = payloads["station"]["ExtremeWaterLevels"][0]
    annuals = payloads["annuals"]
    return [
        [
            station,
            row["year"],
            row["value"],
            payloads[rules.annuals_datum_from]["datum"],
            entry.get(rules.epoch_field),
            annuals["notice"],
        ]
        for row in annuals["extremes"]
    ]


def info(payloads: dict[str, Any]) -> dict[str, Any]:
    """What the statement says ``source_info()`` gives."""
    levels, annuals = payloads["levels"], payloads["annuals"]
    return {
        "station": payloads["station"]["ExtremeWaterLevels"][0],
        "datum": levels["datum"],
        "units": levels["units"],
        "trend": annuals.get("trend"),
        "trend_units": annuals.get("trendUnits"),
        "trend_start_date": annuals.get("trendStartDate"),
        "trend_end_date": annuals.get("trendEndDate"),
        "annual_notice": annuals.get("notice"),
    }


def explore_index(payload: dict[str, Any]) -> dict[str, Any]:
    """Counts that describe NOAA's list of stations with the product."""
    entries = payload.get("ExtremeWaterLevels") or []
    return {
        "stations": len(entries),
        "count_stated": payload.get("count"),
        "by_state": dict(sorted(Counter(str(e.get("state")) for e in entries).items())),
        "by_epoch": dict(sorted(Counter(str(e.get("epoch")) for e in entries).items())),
        "longitude_range": _span(e.get("longitude") for e in entries),
        "latitude_range": _span(e.get("latitude") for e in entries),
    }


def _span(values: Any) -> list[str | None]:
    numbers = [v for v in values if _number(v)]
    return [str(min(numbers)), str(max(numbers))] if numbers else [None, None]


def explore_station(payloads: dict[str, Any], rules: Rules = DEFAULT) -> dict[str, Any]:
    """Counts that describe one station's three responses (a delivered station)."""
    entry = payloads["station"]["ExtremeWaterLevels"][0]
    levels, annuals = payloads["levels"], payloads["annuals"]
    rows = (levels.get(rules.level_group) or {}).get("exceedanceLevels") or []
    extremes = annuals.get("extremes") or []
    years = [row["year"] for row in extremes]
    other_groups = sorted(
        name for name, value in levels.items() if name.startswith("GEV_") and value is not None
    )
    low_name, high_name = rules.bounds
    return {
        "name": entry.get("stationName"),
        "state": entry.get("state"),
        "epoch": entry.get("epoch"),
        "datum_levels": levels.get("datum"),
        "datum_annuals": annuals.get("datum"),
        "units": levels.get("units"),
        "levels": len(rows),
        "levels_without_a_bound": sum(
            1 for row in rows if row.get(low_name) is None or row.get(high_name) is None
        ),
        "probability_range": _span(row.get("probability") for row in rows),
        "return_period_range": _span(row.get("returnPeriod") for row in rows),
        "level_range_m": _span(row.get("level") for row in rows),
        "return_periods_not_one_over_probability": sum(
            1 for row in rows if row["returnPeriod"] * row["probability"] != 1
        ),
        "groups_present": other_groups,
        "years": len(years),
        "first_year": min(years) if years else None,
        "last_year": max(years) if years else None,
        "years_missing_between": (max(years) - min(years) + 1 - len(set(years))) if years else 0,
        "years_repeated": len(years) - len(set(years)),
        "years_in_order": years == sorted(years),
        "extreme_range_m": _span(row.get("value") for row in extremes),
        "trend": None if annuals.get("trend") is None else str(annuals["trend"]),
        "trend_units": annuals.get("trendUnits"),
        "trend_start_date": annuals.get("trendStartDate"),
        "trend_end_date": annuals.get("trendEndDate"),
        "annual_series": [[row["year"], float(row["value"])] for row in extremes],
    }
