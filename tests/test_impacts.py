"""Phase 5: hail impact functions v0 against the spec's test vectors, and the annual-loss rule."""

from __future__ import annotations

import copy
import json
import math

import numpy as np
import pytest

from crc_lab.impacts import annual
from crc_lab.impacts import hail_curves as hc

# docs/requirements-hail-impact-v0.md, "Test vectors".
# D, 2.0 glass-glass flat, 3.2 backsheet flat, 2.0 glass-glass stowed 60 deg, plant at defaults
SOLAR = [
    (25.40, 0.0072, 0.0000, 0.0000, 0.0006),
    (31.75, 0.1215, 0.0000, 0.0000, 0.0097),
    (38.10, 0.3784, 0.0000, 0.0115, 0.0340),
    (44.45, 0.5979, 0.0312, 0.0884, 0.0761),
    (50.80, 0.8988, 0.4072, 0.1653, 0.1248),
    (63.50, 1.0000, 0.8220, 0.5601, 0.2592),
    (69.85, 1.0000, 0.9120, 0.7223, 0.3111),
    (76.20, 1.0000, 0.9671, 0.9041, 0.3693),
    (101.60, 1.0000, 1.0000, 1.0000, 0.4000),
]
# D, Swiss damage ratio, Swiss fraction affected, roof 3-tab, roof laminated
BUILDINGS = [
    (19.05, 0, 0.0007, 0.0003, 0.0000),
    (25.40, 1.477e-06, 0.0028, 0.0050, 0.0006),
    (31.75, 1.507e-05, 0.0070, 0.0227, 0.0050),
    (38.10, 5.363e-05, 0.0135, 0.0492, 0.0180),
    (44.45, 1.255e-04, 0.0223, 0.0724, 0.0383),
    (50.80, 2.312e-04, 0.0324, 0.0871, 0.0593),
    (63.50, 5.065e-04, 0.0537, 0.0978, 0.0870),
    (69.85, 6.493e-04, 0.0634, 0.0992, 0.0934),
    (101.60, 1.141e-03, 0.0947, 0.1000, 0.0999),
]
# D, Swiss damage ratio, Swiss fraction affected
CARS = [
    (19.05, 9.741e-06, 0.0006),
    (25.40, 9.957e-05, 0.0022),
    (31.75, 3.426e-04, 0.0052),
    (38.10, 7.507e-04, 0.0095),
    (44.45, 1.263e-03, 0.0146),
    (50.80, 1.787e-03, 0.0198),
    (63.50, 2.635e-03, 0.0286),
    (69.85, 2.932e-03, 0.0320),
    (101.60, 3.628e-03, 0.0408),
]


def close(got: float, want: float, absolute: float = 5.1e-5) -> bool:
    """The spec's tolerance (1% relative), plus the rounding of vectors printed to 4 decimals."""
    return abs(got - want) <= 0.01 * abs(want) + absolute


def test_parameter_file_is_the_spec_block_and_validates() -> None:
    import re
    from pathlib import Path

    spec = Path(__file__).parents[1] / "docs" / "requirements-hail-impact-v0.md"
    block = json.loads(re.search(r"```json\n(.*?)\n```", spec.read_text(), re.S).group(1))
    assert block == json.loads(hc.PARAMETERS.read_text())
    hc.validate(block)
    for breakit in (
        lambda d: d["curves"]["pv_plant_hail_v0"]["break_probability"]["glass_glass_2.0"].insert(
            1, [20, 0.1]
        ),
        lambda d: d["curves"]["pv_plant_hail_v0"]["break_probability"]["glass_glass_2.0"].append(
            [70, 1.2]
        ),
        lambda d: d["curves"]["car_hail_swiss_v0"]["damage_ratio"].update(v_half=10.0),
        lambda d: d.update(schema="other"),
    ):
        bad = copy.deepcopy(block)
        breakit(bad)
        with pytest.raises(ValueError):
            hc.validate(bad)


@pytest.mark.parametrize("row", SOLAR)
def test_solar_vectors(row: tuple[float, ...]) -> None:
    d, gg_flat, bs_flat, gg_stowed, plant = row
    assert close(hc.pv_break_probability(d, "glass_glass_2.0"), gg_flat)
    assert close(hc.pv_break_probability(d, "glass_backsheet_3.2"), bs_flat)
    assert close(hc.pv_break_probability(d * hc.stow_multiplier(60), "glass_glass_2.0"), gg_stowed)
    assert close(hc.pv_plant_hail(d), plant)


@pytest.mark.parametrize("row", BUILDINGS)
def test_building_vectors(row: tuple[float, ...]) -> None:
    d, ratio, affected, three_tab, laminated = row
    assert close(hc.bld_hail_swiss(d), ratio, 1e-6)
    assert close(hc.bld_hail_swiss(d, output="fraction_affected"), affected)
    assert close(hc.bld_hail_roof(d, roof_class="asphalt_3tab"), three_tab)
    assert close(hc.bld_hail_roof(d), laminated)


@pytest.mark.parametrize("row", CARS)
def test_car_vectors(row: tuple[float, ...]) -> None:
    d, ratio, affected = row
    assert close(hc.car_hail_swiss(d), ratio, 1e-6)
    assert close(hc.car_hail_swiss(d, output="fraction_affected"), affected)


def test_extra_checks_from_the_spec() -> None:
    for name, function in hc.CURVES.items():
        assert function(0.0) == 0.0, name
    p = hc.load()["curves"]
    for name, function in (
        ("bld_hail_swiss_v0", hc.bld_hail_swiss),
        ("car_hail_swiss_v0", hc.car_hail_swiss),
    ):
        for output in hc.SIGMOID_OUTPUTS:
            q = p[name][output]
            assert function(q["v_half"], output=output) == pytest.approx(q["scale"] / 2, rel=1e-12)
    assert hc.stow_multiplier(52) == pytest.approx(0.7579, abs=5e-5)
    assert hc.stow_multiplier(60) == pytest.approx(0.6730, abs=5e-5)
    assert hc.stow_multiplier(75) == pytest.approx(0.4619, abs=5e-5)
    # the paper's empirical values at 60 mm: about 5% affected, damage ratio near 0.05%
    assert hc.bld_hail_swiss(60.0, output="fraction_affected") == pytest.approx(0.048, abs=0.001)
    assert hc.bld_hail_swiss(60.0) == pytest.approx(0.00043, abs=0.00001)


def test_curves_are_monotone_and_bounded_on_a_fine_grid() -> None:
    grid = np.linspace(0, 150, 3001)
    variants = [
        hc.pv_plant_hail(grid),
        hc.pv_plant_hail(grid, glass_class="glass_backsheet_3.2", p_stow=1.0, stow_tilt_deg=20),
        hc.pv_plant_hail(grid, p_stow=0.0, module_cost_share=1.0),
        hc.bld_hail_swiss(grid),
        hc.bld_hail_swiss(grid, output="fraction_affected"),
        hc.bld_hail_roof(grid),
        hc.bld_hail_roof(grid, roof_class="asphalt_3tab", roof_cost_share=1.0),
        hc.car_hail_swiss(grid),
        hc.car_hail_swiss(grid, output="fraction_affected"),
    ]
    for values in variants:
        assert values.shape == grid.shape
        assert np.all(values >= 0) and np.all(values <= 1)
        assert np.all(np.diff(values) >= -1e-15)
    assert hc.pv_plant_hail(150.0) == pytest.approx(0.40)  # flat above the last knot


def test_bad_input_is_rejected_not_zeroed() -> None:
    for bad in (-1.0, float("nan"), float("inf"), [10.0, None]):
        with pytest.raises((ValueError, TypeError)):
            hc.pv_plant_hail(bad)  # type: ignore[arg-type]
    with pytest.raises(KeyError):
        hc.pv_break_probability(40.0, "glass_unknown")
    with pytest.raises(KeyError):
        hc.bld_hail_roof(40.0, roof_class="metal")
    with pytest.raises(ValueError):
        hc.pv_plant_hail(40.0, p_stow=1.2)


def test_metadata_travels_with_every_curve() -> None:
    for name in hc.CURVES:
        meta = hc.metadata(name)
        assert meta["hazard_input"] == "hail_diameter_obs_mm"
        assert all(meta[k] for k in ("native_metric", "calibration_region", "confidence", "source"))
    assert hc.metadata("pv_plant_hail_v0")["placeholders"] == [
        "stow_tilt_deg",
        "p_stow",
        "module_cost_share",
    ]


def test_curve_modules_import_nothing_from_crc() -> None:
    import ast

    for module in (hc, annual):
        tree = ast.parse(open(module.__file__).read())
        names = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        names += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not [n for n in names if n.startswith(("crc_lab", "crc_sdk", "crc_framework"))]


def test_covered_share_mean_times_touch_area_is_the_footprint() -> None:
    for asset, footprint in ((8.0, 25.0), (60.0, 25.0), (0.5, 25.0), (25.0, 25.0)):
        shares = annual.covered_shares(asset, footprint, n=4000)
        touch = math.pi * (math.sqrt(asset / math.pi) + math.sqrt(footprint / math.pi)) ** 2
        assert shares.max() <= 1 + 1e-9 and shares.min() >= 0
        assert shares.mean() * touch == pytest.approx(footprint, rel=2e-3)
    assert annual.covered_shares(0.0, 25.0).tolist() == [1.0]


def test_annual_loss_small_rate_matches_rate_times_mean() -> None:
    out = annual.annual_loss(0.02, [0.0, 0.1, 0.3])
    assert out.expected_uncapped == pytest.approx(0.02 * 0.4 / 3)
    assert out.expected == pytest.approx(out.expected_uncapped, rel=1e-3)
    assert out.chance_of_any == pytest.approx(1 - math.exp(-0.02 * 2 / 3), rel=1e-6)
    assert out.exceeded_with_chance(0.5) == 0.0


def test_annual_loss_adds_events_and_caps_at_full_loss() -> None:
    out = annual.annual_loss(3.0, [0.6])  # two or more events exceed the asset's value
    p0, p1 = math.exp(-3), 3 * math.exp(-3)
    assert out.expected == pytest.approx(0.6 * p1 + 1.0 * (1 - p0 - p1), rel=1e-6)
    assert out.expected < out.expected_uncapped == pytest.approx(1.8)
    assert out.exceeded_with_chance(0.5) == 1.0
    rng = np.random.default_rng(0)
    damages = np.array([0.05, 0.2, 0.45])
    counts = rng.poisson(1.5, 200_000)
    sim = np.array([min(1.0, rng.choice(damages, k).sum()) for k in counts[:50_000]])
    assert annual.annual_loss(1.5, damages).expected == pytest.approx(sim.mean(), rel=0.02)


def test_no_events_means_no_loss() -> None:
    assert annual.annual_loss(0.0, [0.5]).expected == 0.0
    assert annual.annual_loss(0.3, []).expected == 0.0
    with pytest.raises(ValueError):
        annual.annual_loss(0.3, [1.5])


def test_crc_expressions_match_the_callables() -> None:
    from crc_lab.impacts import crc_adapter

    built = crc_adapter.expressions()
    assert set(hc.CURVES) <= set(built)
    for name, entry in built.items():
        assert entry["monotonicity"] == "non_decreasing", name
        assert entry["max_abs_gap"] < (1e-12 if entry["exact"] else 1e-4), name
        calibration = entry["expression"].calibration
        assert calibration.exposure_variable == "hail_diameter_obs_mm"
        assert calibration.impact_metric == "damage_ratio"
    assert float(built["pv_plant_hail_v0"]["expression"].evaluate(50.8)) == pytest.approx(
        0.1248, abs=1e-4
    )


def test_plant_parameters_follow_year_and_mounting() -> None:
    from crc_lab.impacts.build import curve_arguments, plant_parameters

    base = dict.fromkeys(
        ("single_axis", "dual_axis", "fixed_tilt", "uspvdb_axis", "thin_film_cdte")
    )
    base |= {"uspvdb_module_tech": None, "tilt_deg": None}
    tracker = plant_parameters(base | {"single_axis": True, "year": 2023})
    assert tracker["glass_class"] == "glass_glass_2.0" and tracker["p_stow"] == 0.8
    assert tracker["stow_tilt_deg"] == 60 and not tracker["notes"]
    fixed = plant_parameters(base | {"fixed_tilt": True, "year": 2015, "tilt_deg": 20.0})
    assert fixed["glass_class"] == "glass_backsheet_3.2"
    assert (fixed["p_stow"], fixed["stow_tilt_deg"]) == (1.0, 20.0)
    unknown = plant_parameters(base | {"year": 2026, "thin_film_cdte": True})
    assert unknown["tracker"] and len(unknown["notes"]) == 2
    # stow overrides leave fixed-tilt plants alone; other overrides apply to all
    assert curve_arguments(fixed, {"p_stow": 0.0, "module_cost_share": 0.5}) == {
        "glass_class": "glass_backsheet_3.2",
        "stow_tilt_deg": 20.0,
        "p_stow": 1.0,
        "module_cost_share": 0.5,
    }
    assert curve_arguments(tracker, {"p_stow": 0.0, "footprint_km2": 61.0})["p_stow"] == 0.0
