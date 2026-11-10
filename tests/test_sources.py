"""Offline tests for the sources-track builders (pure functions on synthetic rows)."""

from __future__ import annotations

import json
from pathlib import Path

import shapely

from crc_lab.explorer import sources, tracks


def _track_row(
    sid: str,
    lon,
    lat,
    when: str,
    wind: str = "",
    name: str = "ALPHA",
    season: str = "2017",
    **extra,
) -> dict:
    return {
        "SID": sid,
        "NAME": name,
        "SEASON": season,
        "ISO_TIME": when,
        "LAT": str(lat),
        "LON": str(lon),
        "WMO_WIND": wind,
        "WMO_PRES": "",
        "NATURE": "TS",
        **extra,
    }


def test_storm_records_keep_storms_touching_texas_and_clip() -> None:
    rows = [
        _track_row(
            "A", -90.0, 25.0, "2017-08-24T00:00:00", wind="100"
        ),  # Gulf, inside the clip box
        _track_row("A", -97.0, 28.0, "2017-08-25T00:00:00", wind="115", USA_SSHS="4"),  # Texas
        _track_row("A", -98.0, 30.0, "2017-08-26T00:00:00", wind="", USA_WIND="40"),  # US wind only
        _track_row("A", -60.0, 20.0, "2017-08-20T00:00:00"),  # far away: clipped
        _track_row("B", -80.0, 25.0, "2017-09-10T00:00:00", name="BETA"),  # never in Texas
        _track_row("B", -81.0, 26.0, "2017-09-11T00:00:00", name="BETA"),
        _track_row("C", "x", -97.0, "2017-01-01T00:00:00"),  # bad coordinates ignored
        _track_row("D", -97.0, 28.0, "1900-08-25T00:00:00", season="1900"),  # before the window
    ]
    storms = tracks.storm_records(rows)
    assert [s["sid"] for s in storms] == ["A"]
    a = storms[0]
    assert a["label"] == "Alpha 2017" and a["season"] == 2017
    assert [p[:2] for p in a["points"]] == [[-90.0, 25.0], [-97.0, 28.0], [-98.0, 30.0]]
    assert a["max_wind_kt"] == 115 and a["max_wind_kt_in_texas"] == 115
    assert a["max_category"] == 4 and a["wind_source"] == "usa+wmo"
    assert (
        a["first_texas_point"] == "2017-08-25T00:00" and a["last_texas_point"] == "2017-08-26T00:00"
    )
    assert a["points"][2][2] == 40.0  # US wind filled the gap


def test_coops_feature_orders_published_levels_by_return_period() -> None:
    info = {"trend": "6.59", "trend_start_date": "09/15/1957", "trend_end_date": "12/15/2025"}
    levels = [
        {
            "station_id": "8771341",
            "station_name": "Galveston Bay Entrance, TX",
            "longitude": -94.724725,
            "latitude": 29.357461,
            "datum": "MHHW",
            "datum_epoch": "1997-2001",
            "published_return_period_years": rp,
            "water_level_m": level,
            "lower_90ci_m": level - 0.05,
            "upper_90ci_m": level + 0.05,
        }
        for rp, level in [(10.0, 1.5), (1.01, 0.37), (100.0, 2.4)]
    ]
    feature = sources.coops_feature(info, levels)
    assert feature["geometry"]["coordinates"] == [-94.72473, 29.35746]
    curve = feature["properties"]["curve"]
    assert curve["return_periods"] == [1.01, 10.0, 100.0]
    assert curve["values"] == [0.37, 1.5, 2.4]
    assert curve["unit"] == "m above MHHW"
    assert feature["properties"]["trend_mm_per_year"] == 6.59
    assert sources.coops_feature(info, []) is None


def test_station_features_carry_curve_and_params() -> None:
    point = shapely.Point(-97.68, 30.25)
    row = {
        "source_geometry": shapely.to_wkb(point),
        "source_id": "noaa-ghcnh:USW00013904",
        "hazard_name": "ghcnh_temperature_max",
        "horizon": 2012,
        "cell_index": 599661791974260735,
        "curve_kind": "fitted",
        "curve_type": "genextreme",
        "curve_location": 40.4,
        "curve_scale": 1.47,
        "curve_shape": 0.24,
        "curve_atom_probability": None,
        "curve_atom_location": None,
        "curve_probabilities": None,
    }
    values = [tuple(float(40 + i) for i in range(len(sources.RETURN_PERIODS)))]
    feats = sources.station_features([row], values, {"noaa-ghcnh:USW00013904": "AUSTIN"}, "degC")
    assert len(feats) == 1
    p = feats[0]["properties"]
    assert feats[0]["geometry"]["coordinates"] == [-97.68, 30.25]
    assert p["label"].startswith("AUSTIN")
    assert p["curve"]["return_periods"] == list(sources.RETURN_PERIODS)
    assert p["curve"]["values"][0] == 40.0
    assert p["params"][:2] == [0, "genextreme"]


def test_registry_lists_the_sources_layers() -> None:
    root = Path(__file__).resolve().parents[1] / "site"
    registry = json.loads((root / "layers.json").read_text())
    kinds = {layer["id"]: layer["kind"] for layer in registry["layers"]}
    assert kinds["ibtracs"] == "tracks"
    assert kinds["coops"] == "points"
    assert kinds["ghcnh"] == "points"
    era5 = next(layer for layer in registry["layers"] if layer["id"] == "era5_txx")
    assert era5["kind"] == "h3-cells" and era5["horizons"] == [2005]
    assert "{horizon}" in era5["file"] and era5["file"].startswith("data/sources/")
    for layer in registry["layers"]:
        if layer["kind"] in ("points", "lines"):
            assert layer["file"].startswith("data/sources/")
            assert layer["licence"] and layer["source"] and layer["caveat"]
    declared = {source["id"] for source in registry["sources"]}
    assert registry["defaults"]["source"] == "ibtracs"
    assert {
        "ibtracs",
        "storm_events",
        "storm_curves",
        "coops",
        "ghcnh",
        "era5",
        "crc_open",
    } == declared
    for layer in registry["layers"]:
        assert layer["source_id"] is None or layer["source_id"] in declared
    for source in registry["sources"]:
        assert source["status"] in ("loaded", "prototype", "planned")
        assert source["licence"] and source["coverage"] and source["returns"]
