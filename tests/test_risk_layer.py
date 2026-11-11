"""The Risk tab's data files: class breaks, and the committed files against each other."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crc_lab.explorer import risk_layer

SITE = Path(__file__).resolve().parents[1] / "site" / "data" / "assets"


def test_nice_rounds_to_the_series() -> None:
    assert risk_layer.nice(0.118) == 0.1
    assert risk_layer.nice(0.26) == 0.3
    assert risk_layer.nice(640.0) == 700.0
    assert risk_layer.nice(0.0) == 0.0


def test_class_breaks_increase_and_stay_inside_the_data() -> None:
    values = [0.01 * i for i in range(1, 200)] + [None, 0.0]
    breaks = risk_layer.class_breaks(values)
    assert 1 <= len(breaks) <= 4
    assert breaks == sorted(set(breaks))
    assert min(v for v in values if v) < breaks[0] and breaks[-1] < max(v for v in values if v)
    assert risk_layer.class_breaks([None, 0.0]) == []
    assert risk_layer.class_breaks([5.0] * 10) == []  # one value: no break lies inside the data


def test_committed_plant_files_agree() -> None:
    payload = json.loads((SITE / "plants.json").read_text())
    detail = json.loads((SITE / "plants_detail.json").read_text())
    plants = payload["plants"]
    assert payload["totals"]["plants"] == len(plants) == len(detail)
    assert payload["totals"]["loss_usd"] == sum(p["loss_usd"] for p in plants)
    assert payload["totals"]["loss_usd_c"] == sum(p["loss_usd_c"] or 0 for p in plants)
    ids = [m["id"] for m in payload["measures"]]
    assert ids[0] == "loss_ratio" and len(set(ids)) == len(ids)
    for m in payload["measures"]:
        assert m["breaks"] == sorted(set(m["breaks"])) and 1 <= len(m["breaks"]) <= 4
        values = [p[f] * m["scale"] for p in plants for f in m["fields"] if p[f] is not None]
        assert min(values) < m["breaks"][0] and m["breaks"][-1] < max(values)
        assert m["has_basis"] == (m["fields"][0] != m["fields"][1])
    for p in plants:
        d = detail[p["id"]]
        assert d["circle"]["reports"] == len(d["reports"]) == p["reports"]
        assert bool(d["outline"]) == p["polygon"]
        assert set(d["hail_days"]) == {"reports", "reports_corrected", "mrms", "signatures"}
        assert d["more"]["hail_size_largest_mm"] == max(r[2] for r in d["reports"])
        assert len(d["curve"]["d_mm"]) == len(d["curve"]["damage_ratio"])
        assert d["curve"]["damage_ratio"] == sorted(d["curve"]["damage_ratio"])
        if p["factor"] is not None:
            assert p["factor_warning"] == (p["factor"] > payload["factor_warning_above"])
            assert p["loss_ratio_c"] == pytest.approx(p["loss_ratio"] * p["factor"], rel=0.02)


def test_plant_curves_match_the_curve_module_at_the_spec_vector() -> None:
    from crc_lab.impacts import hail_curves as hc

    payload = json.loads((SITE / "plants.json").read_text())
    detail = json.loads((SITE / "plants_detail.json").read_text())
    tracker = next(
        p for p in payload["plants"] if p["mount"] == "tracker" and p["glass"] == "glass_glass_2.0"
    )
    curve = detail[tracker["id"]]["curve"]
    at_50 = curve["damage_ratio"][curve["d_mm"].index(50.0)]
    assert at_50 == pytest.approx(hc.pv_plant_hail(50.0), abs=1e-5)
