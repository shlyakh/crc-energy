"""Offline tests for the Storm Events parser, geometry and fetch plan (fixed 2024 sample)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pyarrow.compute as pc
import pytest
import shapely

from crc_lab.storm_events import geometry, parse
from crc_lab.storm_events.plan import StormEventsPlan, parse_listing

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DETAILS = FIXTURES / "storm_events_details_sample.csv"
LOCATIONS = FIXTURES / "storm_events_locations_sample.csv"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.00K", (10000.0, "ok")),
        ("0.00K", (0.0, "ok")),
        ("2.5M", (2500000.0, "ok")),
        ("1B", (1000000000.0, "ok")),
        ("5H", (500.0, "ok")),
        ("250", (250.0, "ok")),
        ("", (None, "empty")),
        (None, (None, "empty")),
        ("10.00X", (None, "unparsed")),
        ("K", (None, "unparsed")),
    ],
)
def test_parse_damage(raw: str | None, expected: tuple[float | None, str]) -> None:
    assert parse.parse_damage(raw) == expected


def test_tz_offset_and_utc() -> None:
    assert parse.parse_tz_offset("CST-6") == -6.0
    assert parse.parse_tz_offset("CDT-5") == -5.0
    assert parse.parse_tz_offset("GST10") == 10.0
    assert parse.parse_tz_offset("CST") == -6.0
    assert parse.parse_tz_offset("PST") == -8.0
    assert parse.parse_tz_offset("XYZ") is None
    utc, local, flag = parse.local_to_utc("202403", "16", "259", -6.0)
    assert (utc, local, flag) == (
        datetime(2024, 3, 16, 8, 59, tzinfo=UTC),
        "2024-03-16T02:59:00",
        "ok",
    )
    assert parse.local_to_utc("202403", "16", "259", None)[2] == "no_timezone"
    assert parse.local_to_utc("202403", "16", "2460", -6.0)[2] == "bad_time"
    assert parse.local_to_utc("202402", "30", "0", -6.0)[2] == "bad_time"


def test_parse_details_fixture() -> None:
    table = parse.parse_details(DETAILS, states=("TEXAS",))
    assert table.schema.equals(parse.SCHEMA)
    assert table.num_rows > 20
    fort_bend = table.filter(pc.equal(table["event_id"], 1158847)).to_pylist()[0]
    assert fort_bend["hail_size_in"] == 2.75
    assert fort_bend["hail_size_mm"] == pytest.approx(69.85)
    assert fort_bend["begin_utc"] == datetime(2024, 3, 16, 8, 59, tzinfo=UTC)
    assert fort_bend["cz_name"] == "FORT BEND"
    assert fort_bend["damage_property_usd"] == 0.0
    wind = table.filter(pc.equal(table["event_type"], "Thunderstorm Wind")).to_pylist()
    assert wind and all(w["wind_knots"] is not None and w["wind_kind"] == "gust" for w in wind)
    assert all(w["wind_ms"] == pytest.approx(w["wind_knots"] * 0.514444, abs=0.01) for w in wind)
    assert all(w["wind_measure"] in ("measured", "estimated") for w in wind)
    hail = table.filter(pc.equal(table["event_type"], "Hail")).to_pylist()
    assert all(h["wind_knots"] is None and h["hail_size_in"] is not None for h in hail)
    other = table.filter(pc.equal(table["event_type"], "Drought")).to_pylist()
    assert other and all(o["magnitude"] is None and o["cz_type"] == "Z" for o in other)
    assert set(table["time_flag"].to_pylist()) == {"ok"}


def test_event_geometry_priority() -> None:
    boundaries = geometry.Boundaries(
        counties={157: shapely.to_wkb(shapely.box(-96, 29, -95.5, 29.8))},
        zones={213: shapely.to_wkb(shapely.box(-96, 29, -95.5, 29.8))},
        county_source="test",
        zone_source="test",
    )
    base = {
        "event_id": 1,
        "begin_lat": None,
        "begin_lon": None,
        "end_lat": None,
        "end_lon": None,
        "cz_type": "C",
        "cz_fips": 157,
    }
    kind, wkb = geometry.event_geometry(base, {}, boundaries)
    assert kind == "county" and shapely.from_wkb(wkb).geom_type == "Polygon"
    kind, _ = geometry.event_geometry({**base, "cz_type": "Z", "cz_fips": 213}, {}, boundaries)
    assert kind == "zone"
    kind, _ = geometry.event_geometry({**base, "cz_type": "Z", "cz_fips": 999}, {}, boundaries)
    assert kind == "none"
    kind, wkb = geometry.event_geometry(
        {**base, "begin_lat": 29.4, "begin_lon": -95.8}, {}, boundaries
    )
    assert kind == "point"
    kind, wkb = geometry.event_geometry(
        {**base, "begin_lat": 29.4, "begin_lon": -95.8, "end_lat": 29.5, "end_lon": -95.7},
        {},
        boundaries,
    )
    assert kind == "path" and shapely.from_wkb(wkb).geom_type == "LineString"
    # locations points win over begin/end
    kind, wkb = geometry.event_geometry(
        base, {1: [(-95.8, 29.4), (-95.7, 29.5), (-95.6, 29.6)]}, boundaries
    )
    assert kind == "path" and len(shapely.from_wkb(wkb).coords) == 3


def test_add_cells_fixture_without_network() -> None:
    table = parse.parse_details(DETAILS, states=("TEXAS",))
    locations = geometry.read_locations([LOCATIONS])
    boundaries = geometry.Boundaries(
        counties={}, zones={}, county_source="test", zone_source="test"
    )
    out = geometry.add_cells(table, locations, boundaries)
    summary = geometry.cell_count_summary(out)
    assert summary["by_kind"]["point"] > 0
    assert summary["by_kind"].get("none", 0) > 0  # zone events, no polygons in this test
    with_points = out.filter(pc.not_equal(out["geometry_kind"], "none"))
    assert pc.min(pc.list_value_length(with_points["cells"])).as_py() >= 1
    path = out.filter(pc.equal(out["geometry_kind"], "path"))
    if path.num_rows:
        assert pc.max(pc.list_value_length(path["cells"])).as_py() >= 1


def test_listing_picks_newest_creation_per_year() -> None:
    html = """
    <a href="StormEvents_details-ftp_v1.0_d2024_c20250101.csv.gz">x</a>
    <a href="StormEvents_details-ftp_v1.0_d2024_c20260728.csv.gz">x</a>
    <a href="StormEvents_locations-ftp_v1.0_d2024_c20260728.csv.gz">x</a>
    <a href="StormEvents_details-ftp_v1.0_d1950_c20260323.csv.gz">x</a>
    """
    files = parse_listing(html)
    assert [(f.file_type, f.year, f.created) for f in files] == [
        ("details", 1950, "20260323"),
        ("details", 2024, "20260728"),
        ("locations", 2024, "20260728"),
    ]
    plan = StormEventsPlan(Path("/tmp/x")).between(2000, 2026).only("details")
    assert plan._wanted(files) == [files[1]]
    assert plan.explain()["years"] == (2000, 2026)
    with pytest.raises(ValueError):
        StormEventsPlan(Path("/tmp/x"), mode="sometimes")


def test_explorer_layer_packs_times_and_unlocated_events() -> None:
    import math
    import struct

    from crc_lab.storm_events import explorer_layer as layer

    assert layer.minutes_since_epoch(datetime(1950, 1, 1, 1, 30, tzinfo=UTC)) == 90
    assert layer.minutes_since_epoch(None) == 0
    point = shapely.to_wkb(shapely.Point(-95.83, 29.39))
    rows = [
        {
            "event_id": 7,
            "year": 2024,
            "event_type": "Hail",
            "magnitude": 2.75,
            "damage_property_usd": None,
            "geometry_kind": "point",
            "geometry_wkb": point,
            "begin_utc": datetime(2024, 3, 16, 8, 59, tzinfo=UTC),
            "end_utc": datetime(2024, 3, 16, 9, 9, tzinfo=UTC),
        },
        {
            "event_id": 8,
            "year": 2024,
            "event_type": "Drought",
            "magnitude": None,
            "damage_property_usd": 0.0,
            "geometry_kind": "zone",
            "geometry_wkb": None,
            "begin_utc": datetime(2024, 3, 17, tzinfo=UTC),
            "end_utc": None,
        },
    ]
    data = layer.pack_events(rows, {"Drought": 0, "Hail": 1})
    assert len(data) == 2 * layer.RECORD.size == 64
    a = struct.unpack_from("<ffHBxfIfII", data, 0)
    b = struct.unpack_from("<ffHBxfIfII", data, 32)
    assert a[0] == pytest.approx(-95.83) and a[2:4] == (2024, 1) and a[8] - a[7] == 10
    assert a[7] == layer.minutes_since_epoch(rows[0]["begin_utc"]) and math.isnan(a[6])
    assert math.isnan(b[0]) and math.isnan(b[4]) and b[8] == b[7]  # no point, no duration
    assert [f["offset"] for f in layer.FIELDS][-2:] == [24, 28]
