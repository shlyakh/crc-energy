"""Offline tests for the explorer data build (no network: a synthetic canonical file)."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pytest
import shapely

from crc_data_explorer import hazards
from lab_common import texas


def test_intersecting_cells_covers_a_small_polygon() -> None:
    # A 1°x1° square in central Texas: a handful of r5 cells, all touching the square.
    square = shapely.box(-99.0, 31.0, -98.0, 32.0)
    cells = texas.intersecting_cells(shapely.to_wkb(square), 5)
    assert 40 <= len(cells) <= 80
    assert all(isinstance(c, int) and c > 0 for c in cells)


def test_write_json_atomic_is_compact_and_readable(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "out.json"
    texas.write_json_atomic(path, {"a": [1, 2.5, None]})
    assert path.read_text() == '{"a":[1,2.5,null]}'
    assert not list(tmp_path.glob("**/*.part"))
    assert path.stat().st_mode & 0o444 == 0o444


def test_round_keeps_six_significant_digits() -> None:
    assert hazards._round(312.3456789) == 312.346
    assert hazards._round(0.0) == 0.0
    assert hazards._round(None) is None
    assert hazards._round(float("nan")) is None


def test_params_follow_curve_kind() -> None:
    row = {
        "curve_kind": "hurdle",
        "curve_type": "gumbel_r",
        "curve_location": 1.0,
        "curve_scale": 2.0,
        "curve_shape": None,
        "curve_atom_probability": 0.3,
        "curve_atom_location": 0.0,
        "curve_probabilities": None,
    }
    assert hazards._params(row) == [1, "gumbel_r", 1.0, 2.0, None, 0.3, 0.0]
    row.update(curve_kind="no_data", curve_type="insufficient_informative_support")
    assert hazards._params(row) == [4, "insufficient_informative_support"]
    row.update(
        curve_kind="tabulated",
        curve_type="linear_probability",
        curve_probabilities=[0.996, 0.998, 0.999],
    )
    assert hazards._params(row) == [3, "linear_probability", 3]


def test_return_periods_match_requirement_e4() -> None:
    assert hazards.RETURN_PERIODS == (2, 5, 10, 20, 50, 100, 200, 500)
    assert hazards.HORIZONS == (2030, 2050, 2080)
    assert len(hazards.HAZARDS) == 8


def test_evaluate_handles_tabulated_rows_outside_support() -> None:
    """A tabulated curve with knots near the rare end gives nulls elsewhere, not an error."""
    from crc_sdk.workflows.distributions import return_periods_to_probabilities

    rows = [
        {
            "curve_kind": "fitted",
            "curve_type": "gumbel_r",
            "curve_location": 10.0,
            "curve_scale": 2.0,
            "curve_shape": None,
            "curve_atom_probability": None,
            "curve_atom_location": None,
            "curve_probabilities": None,
            "curve_values": None,
        },
        {
            "curve_kind": "tabulated",
            "curve_type": "linear_probability",
            "curve_location": None,
            "curve_scale": None,
            "curve_shape": None,
            "curve_atom_probability": None,
            "curve_atom_location": None,
            "curve_probabilities": [0.996, 0.998, 0.999],
            "curve_values": [0.0, 0.5, 1.0],
        },
    ]
    table = pa.Table.from_pylist(rows)
    probabilities = return_periods_to_probabilities(hazards.RETURN_PERIODS, tail="upper")
    values, outside = hazards.evaluate(table, rows, probabilities, workers=1)
    assert len(values) == 2
    assert all(v is not None for v in values[0])
    assert values[0][-1] > values[0][0]
    assert values[1][:7] == (None,) * 7
    assert values[1][7] == pytest.approx(0.5)
    assert outside == 7


def test_registry_and_sources_are_valid_json() -> None:
    root = Path(__file__).resolve().parents[1] / "site"
    registry = json.loads((root / "layers.json").read_text())
    ids = [layer["id"] for layer in registry["layers"]]
    assert len(ids) == len(set(ids))
    cells = [layer for layer in registry["layers"] if layer["kind"] == "h3-cells"]
    crc_open = [layer for layer in cells if layer["source"] == "CRC Open"]
    assert {layer["id"] for layer in crc_open} == set(hazards.HAZARDS)
    assert {layer["id"] for layer in cells} - set(hazards.HAZARDS) == {
        "hail_size",
        "thunderstorm_gust",
        "era5_txx",
    }
    for layer in crc_open:
        assert layer["licence"] == "CC BY-NC 4.0"
    for layer in cells:
        assert "{horizon}" in layer["file"]
        assert {"hue", "chroma"} <= set(layer["style"])
    sources = json.loads((root / "sources.json").read_text())
    assert sources["sources"] and sources["not_in_crc"]
