"""S2: parse the NCEI ``details`` files into one typed Arrow table.

Hail and thunderstorm wind are cleaned fully (size in inches and mm; wind in knots and m/s with
measured/estimated and gust/sustained from ``MAGNITUDE_TYPE``); every other event type passes
through with the shared columns. Times become UTC from NCEI's local standard time plus the
``CZ_TIMEZONE`` offset. Damage strings such as ``10.00K`` become dollars; anything unparseable
stays null with the raw string kept and a flag set, never guessed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv

HAIL = "Hail"
THUNDERSTORM_WIND = "Thunderstorm Wind"
INCH_MM = 25.4
KNOT_MS = 0.514444

# NCEI codes: EG estimated gust, MG measured gust, ES estimated sustained, MS measured sustained
MAGNITUDE_TYPES = {
    "EG": ("estimated", "gust"),
    "MG": ("measured", "gust"),
    "ES": ("estimated", "sustained"),
    "MS": ("measured", "sustained"),
}
_DAMAGE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([KkMmBbHh]?)\s*$")
_MULTIPLIER = {"": 1.0, "H": 100.0, "K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0}
_TZ = re.compile(r"([+-]?\d{1,2})\s*$")

SCHEMA = pa.schema(
    [
        ("event_id", pa.int64()),
        ("episode_id", pa.int64()),
        ("year", pa.int32()),
        ("state", pa.string()),
        ("state_fips", pa.int32()),
        ("event_type", pa.string()),
        ("cz_type", pa.string()),
        ("cz_fips", pa.int32()),
        ("cz_name", pa.string()),
        ("wfo", pa.string()),
        ("begin_utc", pa.timestamp("s", tz="UTC")),
        ("end_utc", pa.timestamp("s", tz="UTC")),
        ("begin_local", pa.string()),
        ("tz_label", pa.string()),
        ("tz_offset_hours", pa.float64()),
        ("time_flag", pa.string()),
        ("injuries_direct", pa.int32()),
        ("injuries_indirect", pa.int32()),
        ("deaths_direct", pa.int32()),
        ("deaths_indirect", pa.int32()),
        ("damage_property_usd", pa.float64()),
        ("damage_property_raw", pa.string()),
        ("damage_property_flag", pa.string()),
        ("damage_crops_usd", pa.float64()),
        ("damage_crops_raw", pa.string()),
        ("damage_crops_flag", pa.string()),
        ("source", pa.string()),
        ("magnitude", pa.float64()),
        ("magnitude_type", pa.string()),
        ("hail_size_in", pa.float64()),
        ("hail_size_mm", pa.float64()),
        ("wind_knots", pa.float64()),
        ("wind_ms", pa.float64()),
        ("wind_measure", pa.string()),
        ("wind_kind", pa.string()),
        ("flood_cause", pa.string()),
        ("tor_f_scale", pa.string()),
        ("tor_length_mi", pa.float64()),
        ("tor_width_yd", pa.float64()),
        ("begin_lat", pa.float64()),
        ("begin_lon", pa.float64()),
        ("end_lat", pa.float64()),
        ("end_lon", pa.float64()),
        ("event_narrative", pa.string()),
        ("file_name", pa.string()),
    ]
)

COLUMN_DOCS = {
    "event_id": "NCEI EVENT_ID, the key shared by details, locations and fatalities",
    "begin_utc": "BEGIN_YEARMONTH/DAY/TIME read as local standard time, shifted by tz_offset_hours",
    "tz_offset_hours": "from CZ_TIMEZONE: the number when present (CST-6 -> -6), else the standard "
    "offset of the bare label (CST -> -6, as in the older files); null when unknown",
    "time_flag": "ok | no_timezone | bad_time",
    "damage_property_usd": "DAMAGE_PROPERTY as dollars: number plus K/M/B (and H = hundred)",
    "damage_property_flag": "ok | empty | unparsed",
    "hail_size_in": "MAGNITUDE for Hail events (inches to the hundredth, NCEI format)",
    "wind_knots": "MAGNITUDE for Thunderstorm Wind events (knots, NCEI format)",
    "wind_measure": "measured | estimated, from MAGNITUDE_TYPE (EG, MG, ES, MS)",
    "wind_kind": "gust | sustained, from MAGNITUDE_TYPE",
    "begin_lat": "BEGIN_LAT as given; county and zone events have none",
    "file_name": "the NCEI file the row came from (creation date is in the name)",
}


def parse_damage(raw: str | None) -> tuple[float | None, str]:
    """``'10.00K'`` -> (10000.0, 'ok'); '' -> (None, 'empty'); junk -> (None, 'unparsed')."""
    if raw is None or raw.strip() == "":
        return None, "empty"
    match = _DAMAGE.match(raw)
    if not match:
        return None, "unparsed"
    number, suffix = match.group(1), match.group(2).upper()
    return float(number) * _MULTIPLIER[suffix], "ok"


# Standard offsets for the bare labels in the older files ("CST", "PST"), hours east of UTC.
_LABEL_OFFSETS = {
    "UTC": 0.0,
    "GMT": 0.0,
    "AST": -4.0,
    "EST": -5.0,
    "EDT": -4.0,
    "CST": -6.0,
    "CDT": -5.0,
    "MST": -7.0,
    "MDT": -6.0,
    "PST": -8.0,
    "PDT": -7.0,
    "AKST": -9.0,
    "AKDT": -8.0,
    "HST": -10.0,
    "SST": -11.0,
    "GST": 10.0,
    "CHST": 10.0,
}


def parse_tz_offset(label: str | None) -> float | None:
    """``'CST-6'`` -> -6.0; ``'GST10'`` -> 10.0; ``'CST'`` -> -6.0 (label table); else None."""
    if not label:
        return None
    text = label.strip().upper()
    match = _TZ.search(text)
    if match:
        return float(match.group(1))
    return _LABEL_OFFSETS.get(text)


def local_to_utc(
    yearmonth: str | None, day: str | None, hhmm: str | None, offset: float | None
) -> tuple[datetime | None, str | None, str]:
    """Return (utc, local ISO string, flag) from NCEI's split date fields."""
    try:
        year, month = int(yearmonth[:4]), int(yearmonth[4:6])
        d = int(day)
        t = int(hhmm) if hhmm not in (None, "") else 0
        hour, minute = divmod(t, 100)
        if hour > 23 or minute > 59:  # a few rows carry 2400-style times
            raise ValueError
        local = datetime(year, month, d, hour, minute)
    except (TypeError, ValueError):
        return None, None, "bad_time"
    if offset is None:
        return None, local.isoformat(), "no_timezone"
    return (local - timedelta(hours=offset)).replace(tzinfo=UTC), local.isoformat(), "ok"


def _f(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _i(value: str | None) -> int | None:
    f = _f(value)
    return int(f) if f is not None else None


def read_raw(path: Path) -> pa.Table:
    """A details file as strings; empty fields become null."""
    return pacsv.read_csv(
        path,
        read_options=pacsv.ReadOptions(block_size=1 << 24),
        parse_options=pacsv.ParseOptions(newlines_in_values=True),
        convert_options=pacsv.ConvertOptions(
            column_types={name: pa.string() for name in _RAW_COLUMNS},
            strings_can_be_null=True,
            quoted_strings_can_be_null=False,
        ),
    )


_RAW_COLUMNS = (
    "BEGIN_YEARMONTH BEGIN_DAY BEGIN_TIME END_YEARMONTH END_DAY END_TIME EPISODE_ID EVENT_ID STATE "
    "STATE_FIPS YEAR MONTH_NAME EVENT_TYPE CZ_TYPE CZ_FIPS CZ_NAME WFO BEGIN_DATE_TIME "
    "CZ_TIMEZONE END_DATE_TIME INJURIES_DIRECT INJURIES_INDIRECT DEATHS_DIRECT DEATHS_INDIRECT "
    "DAMAGE_PROPERTY DAMAGE_CROPS SOURCE MAGNITUDE MAGNITUDE_TYPE FLOOD_CAUSE CATEGORY TOR_F_SCALE "
    "TOR_LENGTH TOR_WIDTH TOR_OTHER_WFO TOR_OTHER_CZ_STATE TOR_OTHER_CZ_FIPS TOR_OTHER_CZ_NAME "
    "BEGIN_RANGE BEGIN_AZIMUTH BEGIN_LOCATION END_RANGE END_AZIMUTH END_LOCATION BEGIN_LAT "
    "BEGIN_LON END_LAT END_LON EPISODE_NARRATIVE EVENT_NARRATIVE DATA_SOURCE"
).split()


def parse_rows(rows: Iterable[dict[str, str | None]], file_name: str) -> list[dict[str, object]]:
    out = []
    for r in rows:
        offset = parse_tz_offset(r.get("CZ_TIMEZONE"))
        begin_utc, begin_local, flag = local_to_utc(
            r.get("BEGIN_YEARMONTH"), r.get("BEGIN_DAY"), r.get("BEGIN_TIME"), offset
        )
        end_utc, _, _ = local_to_utc(
            r.get("END_YEARMONTH"), r.get("END_DAY"), r.get("END_TIME"), offset
        )
        prop_usd, prop_flag = parse_damage(r.get("DAMAGE_PROPERTY"))
        crop_usd, crop_flag = parse_damage(r.get("DAMAGE_CROPS"))
        event_type = (r.get("EVENT_TYPE") or "").strip()
        magnitude = _f(r.get("MAGNITUDE"))
        magnitude_type = (r.get("MAGNITUDE_TYPE") or "").strip() or None
        hail_in = magnitude if event_type == HAIL else None
        wind_kn = magnitude if event_type == THUNDERSTORM_WIND else None
        measure, kind = (
            MAGNITUDE_TYPES.get(magnitude_type or "", (None, None))
            if wind_kn is not None
            else (None, None)
        )
        out.append(
            {
                "event_id": _i(r.get("EVENT_ID")),
                "episode_id": _i(r.get("EPISODE_ID")),
                "year": _i(r.get("YEAR")),
                "state": (r.get("STATE") or "").strip() or None,
                "state_fips": _i(r.get("STATE_FIPS")),
                "event_type": event_type or None,
                "cz_type": (r.get("CZ_TYPE") or "").strip() or None,
                "cz_fips": _i(r.get("CZ_FIPS")),
                "cz_name": (r.get("CZ_NAME") or "").strip() or None,
                "wfo": (r.get("WFO") or "").strip() or None,
                "begin_utc": begin_utc,
                "end_utc": end_utc,
                "begin_local": begin_local,
                "tz_label": (r.get("CZ_TIMEZONE") or "").strip() or None,
                "tz_offset_hours": offset,
                "time_flag": flag,
                "injuries_direct": _i(r.get("INJURIES_DIRECT")),
                "injuries_indirect": _i(r.get("INJURIES_INDIRECT")),
                "deaths_direct": _i(r.get("DEATHS_DIRECT")),
                "deaths_indirect": _i(r.get("DEATHS_INDIRECT")),
                "damage_property_usd": prop_usd,
                "damage_property_raw": r.get("DAMAGE_PROPERTY"),
                "damage_property_flag": prop_flag,
                "damage_crops_usd": crop_usd,
                "damage_crops_raw": r.get("DAMAGE_CROPS"),
                "damage_crops_flag": crop_flag,
                "source": (r.get("SOURCE") or "").strip() or None,
                "magnitude": magnitude,
                "magnitude_type": magnitude_type,
                "hail_size_in": hail_in,
                "hail_size_mm": round(hail_in * INCH_MM, 2) if hail_in is not None else None,
                "wind_knots": wind_kn,
                "wind_ms": round(wind_kn * KNOT_MS, 2) if wind_kn is not None else None,
                "wind_measure": measure,
                "wind_kind": kind,
                "flood_cause": (r.get("FLOOD_CAUSE") or "").strip() or None,
                "tor_f_scale": (r.get("TOR_F_SCALE") or "").strip() or None,
                "tor_length_mi": _f(r.get("TOR_LENGTH")),
                "tor_width_yd": _f(r.get("TOR_WIDTH")),
                "begin_lat": _f(r.get("BEGIN_LAT")),
                "begin_lon": _f(r.get("BEGIN_LON")),
                "end_lat": _f(r.get("END_LAT")),
                "end_lon": _f(r.get("END_LON")),
                "event_narrative": r.get("EVENT_NARRATIVE"),
                "file_name": file_name,
            }
        )
    return out


def parse_details(path: Path, *, states: tuple[str, ...] | None = None) -> pa.Table:
    """One yearly details file as a typed table, optionally only some states (upper-case names)."""
    raw = read_raw(path)
    if states:
        import pyarrow.compute as pc

        raw = raw.filter(pc.is_in(pc.utf8_trim_whitespace(raw["STATE"]), pa.array(states)))
    rows = parse_rows(raw.to_pylist(), path.name)
    return pa.Table.from_pylist(rows, schema=SCHEMA)
