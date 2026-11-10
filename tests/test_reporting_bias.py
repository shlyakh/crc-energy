"""Offline tests for the hail reporting-bias model (pure functions on synthetic data)."""

from __future__ import annotations

import numpy as np
import pytest

from crc_lab.assets import reporting_bias as rb


def test_reporting_rate_rises_from_floor_to_one() -> None:
    pop = np.array([0.0, 10.0, 1e6])
    road = np.zeros(3)
    rate = rb.reporting_rate(pop, road, floor=0.2, b_pop=0.05, b_road=1.0)
    assert rate[0] == pytest.approx(0.2)
    assert rate[0] < rate[1] < rate[2]
    assert rate[2] == pytest.approx(1.0)
    with_road = rb.reporting_rate(np.zeros(1), np.array([0.5]), 0.2, 0.05, 1.0)[0]
    assert with_road == pytest.approx(0.2 + 0.8 * (1 - np.exp(-0.5)))


def test_profile_true_rates_is_the_poisson_optimum() -> None:
    counts = np.array([10.0, 30.0, 5.0, 0.0])
    rho = np.array([0.5, 1.0, 1.0, 0.25])
    region = np.array([0, 0, 1, 1])
    lam = rb.profile_true_rates(counts, rho, region, years=10.0, n_regions=2)
    assert lam[0] == pytest.approx(40.0 / (10 * 1.5))
    assert lam[1] == pytest.approx(5.0 / (10 * 1.25))
    best = rb.poisson_loglik(counts, 10 * lam[region] * rho)
    for bump in (0.9, 1.1):
        assert rb.poisson_loglik(counts, 10 * lam[region] * bump * rho) < best


def test_area_weighting_conserves_the_total() -> None:
    # two sources: one wholly in target 0, one split 25/75 between targets 0 and 1
    values = np.array([100.0, 40.0, 40.0])
    source_area = np.array([2.0, 8.0, 8.0])
    overlap = np.array([2.0, 2.0, 6.0])
    target = np.array([0, 0, 1])
    out = rb.area_weighted(values, source_area, overlap, target, 2)
    assert out.tolist() == [110.0, 30.0]
    assert out.sum() == pytest.approx(140.0)


def _synthetic(seed: int = 3) -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng(seed)
    n_regions, per = 30, 60
    region = np.repeat(np.arange(n_regions), per)
    pop = rng.lognormal(1.5, 1.8, n_regions * per)
    road = rng.gamma(1.2, 0.08, n_regions * per)
    true = rng.uniform(0.5, 4.0, n_regions)
    rho = rb.reporting_rate(pop, road, 0.15, 0.02, 2.0)
    counts = rng.poisson(30.0 * true[region] * rho).astype(float)
    return counts, pop, road, region, true


def test_fit_recovers_known_parameters() -> None:
    counts, pop, road, region, true = _synthetic()
    fitted = rb.fit(counts, pop, road, region, 30.0, "both")
    assert fitted.floor == pytest.approx(0.15, abs=0.03)
    assert fitted.b_pop == pytest.approx(0.02, rel=0.25)
    assert fitted.b_road == pytest.approx(2.0, rel=0.25)
    assert np.corrcoef(fitted.true_rates, true)[0, 1] > 0.98
    none = rb.fit(counts, pop, road, region, 30.0, "none")
    assert none.floor == 1.0 and fitted.loglik > none.loglik


def test_held_out_likelihood_prefers_the_true_model() -> None:
    counts, pop, road, region, _ = _synthetic(seed=8)
    scores = rb.held_out(counts, pop, road, region, 30.0, folds=3)
    assert set(scores) == set(rb.MODELS)
    assert scores["both"] > scores["population"] > scores["none"]
    assert scores["both"] > scores["roads"]


def test_bootstrap_interval_covers_the_truth() -> None:
    counts, pop, road, region, _ = _synthetic(seed=5)
    boot = rb.bootstrap(counts, pop, road, region, 30.0, "both", reps=20)
    assert boot["floor"][0] <= 0.15 + 0.03 and boot["floor"][1] >= 0.15 - 0.03
    assert boot["rho_lo"].shape == counts.shape
    assert np.all(boot["rho_lo"] <= boot["rho_hi"])
