"""Offline tests for Phase 4: value from the ATB reference file, hail exposure by density."""

from __future__ import annotations

import json
import math

import numpy as np
import pyarrow as pa
import pytest

from crc_lab.assets import exposure, value


def test_reference_file_has_provenance_and_the_default_cost() -> None:
    reference = json.loads(value.REFERENCE.read_text())
    assert len(reference["sha256"]) == 64 and reference["url"].startswith("https://")
    occ, provenance = value.cost_per_kw()
    assert occ > 0 and provenance["cost_year"] == 2024 and provenance["occ_usd_per_kw"] == occ
    with pytest.raises(KeyError):
        value.cost_per_kw(year=1900)


def test_add_value_is_capacity_times_cost() -> None:
    table = pa.table({"capacity_ac_mw": pa.array([100.0, None, 2.5])})
    out = value.add_value(table, 1000.0)["value_usd"].to_pylist()
    assert out == [100_000_000.0, None, 2_500_000.0]


def _ring(n: int, radius_deg: float, size: float) -> exposure.Reports:
    angles = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return exposure.Reports(
        lon=-99.0 + radius_deg * np.cos(angles) / math.cos(math.radians(31.0)),
        lat=31.0 + radius_deg * np.sin(angles),
        size_mm=np.full(n, size),
        start=1996,
        end=2025,
    )


def test_distance_is_great_circle_in_km() -> None:
    reports = exposure.Reports(np.array([-99.0]), np.array([32.0]), np.array([25.4]), 1996, 2025)
    assert exposure.distances_km(-99.0, 31.0, reports)[0] == pytest.approx(111.2, abs=0.2)


def test_circle_grows_to_n_and_rate_follows() -> None:
    reports = _ring(200, 0.2, 50.8)  # 200 reports about 22 km away
    rule = exposure.Rule(n_target=100, min_radius_km=10, max_radius_km=75, footprint_km2=25)
    out = exposure.at_point(-99.0, 31.0, reports, rule)
    assert out["flag"] == "ok"
    assert out["radius_km"] == pytest.approx(22.2, abs=0.3)
    assert out["reports_in_radius"] >= 100
    area = math.pi * out["radius_km"] ** 2
    expected = out["reports_in_radius"] / (area * 30) * 100
    assert out["report_rate_per_100km2_year"] == pytest.approx(expected, rel=1e-3)
    rate_2in = out["rate_ge_2in_per_100km2_year"] / 100
    assert out["annual_prob_ge_2in"] == pytest.approx(1 - math.exp(-rate_2in * 25), rel=1e-3)
    assert out["annual_prob_ge_3in"] == 0.0 and out["size_max_mm"] == 50.8


def test_minimum_and_maximum_radius_guards() -> None:
    dense = _ring(300, 0.01, 25.4)  # all within about 1 km
    out = exposure.at_point(-99.0, 31.0, dense, exposure.Rule(min_radius_km=10))
    assert out["radius_km"] == 10 and out["radius_to_n_km"] < 2
    assert out["reports_in_radius"] == 300
    sparse = _ring(20, 0.2, 25.4)  # fewer than N anywhere
    out = exposure.at_point(-99.0, 31.0, sparse, exposure.Rule())
    assert out["flag"] == "too_few_reports" and out["radius_km"] == 75
    assert out["radius_to_n_km"] is None


def test_rule_label_and_placeholder_flag() -> None:
    rule = exposure.Rule()
    assert rule.label == "N100-r10-75-A25"
    assert exposure.rule_dict(rule)["footprint_is_placeholder"] is True
