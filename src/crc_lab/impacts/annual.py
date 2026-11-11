"""From hail events at an asset to a year's damage ratio.

Events arrive as a Poisson process. Each event damages a share of the asset. The damage ratios
of the events in one year are added and the year's total is capped at full loss (decided
2026-11-10). Standard library and numpy only, like ``hail_curves``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

Array = NDArray[np.float64]


def covered_shares(asset_area_km2: float, footprint_km2: float, n: int = 64) -> Array:
    """Share of a disc-shaped asset covered by a disc-shaped hail footprint that touches it.

    The footprint's centre is uniform over the disc in which the two touch (radius
    ``r_footprint + r_asset``). Returns ``n`` equally likely shares. For an asset with no area
    (a building, a car) every touch covers it, so the shares are all 1.

    The mean share times the touch area equals the footprint area exactly: per unit of event
    density, the expected covered share does not depend on the asset's size.
    """
    if asset_area_km2 <= 0:
        return np.ones(1)
    r_f, r_a = math.sqrt(footprint_km2 / math.pi), math.sqrt(asset_area_km2 / math.pi)
    d = (r_f + r_a) * np.sqrt((np.arange(n) + 0.5) / n)  # centre distance, uniform over the disc
    small, large = min(r_f, r_a), max(r_f, r_a)
    inside = d <= large - small
    dd = np.where(inside, large, d)
    a1 = np.clip((dd**2 + r_f**2 - r_a**2) / (2 * dd * r_f), -1, 1)
    a2 = np.clip((dd**2 + r_a**2 - r_f**2) / (2 * dd * r_a), -1, 1)
    root = np.clip(
        (-dd + r_f + r_a) * (dd + r_f - r_a) * (dd - r_f + r_a) * (dd + r_f + r_a), 0, None
    )
    lens = r_f**2 * np.arccos(a1) + r_a**2 * np.arccos(a2) - 0.5 * np.sqrt(root)
    overlap = np.where(inside, math.pi * small**2, lens)
    return overlap / (math.pi * r_a**2)


@dataclass(frozen=True)
class AnnualLoss:
    """One asset's annual damage ratio under the sum-capped rule."""

    events_per_year: float  # events touching the asset
    mean_event_damage: float  # mean damage ratio of one touching event
    expected: float  # expected annual damage ratio, capped
    expected_uncapped: float  # events_per_year x mean_event_damage
    chance_of_any: float  # chance the year's damage ratio is at least one grid step
    grid: Array
    pmf: Array

    def chance_at_least(self, damage_ratio: float) -> float:
        """Chance that the year's damage ratio reaches ``damage_ratio``."""
        return float(self.pmf[self.grid >= damage_ratio - 1e-12].sum())

    def exceeded_with_chance(self, chance: float) -> float:
        """The annual damage ratio exceeded with this chance in a year (0 if it is rarer)."""
        tail = 1.0 - np.cumsum(self.pmf)
        return float(self.grid[int(np.argmax(tail <= chance + 1e-15))])


def annual_loss(
    events_per_year: float,
    event_damage: ArrayLike,
    *,
    weights: ArrayLike | None = None,
    cap: float = 1.0,
    bins: int = 4000,
) -> AnnualLoss:
    """Distribution of a year's damage ratio: a Poisson number of events, damages added, capped.

    ``event_damage`` holds the possible damage ratios of one touching event, equally likely
    unless ``weights`` are given. Damages are rounded to a grid of ``cap / bins``.
    """
    damage = np.asarray(event_damage, dtype=np.float64).ravel()
    if events_per_year < 0 or not math.isfinite(events_per_year):
        raise ValueError("events_per_year must be finite and non-negative")
    if damage.size and (
        np.any(damage < 0) or np.any(damage > 1) or not np.all(np.isfinite(damage))
    ):
        raise ValueError("event damage ratios must lie in [0, 1]")
    w = np.ones(damage.size) if weights is None else np.asarray(weights, dtype=np.float64).ravel()
    grid = np.linspace(0.0, cap, bins + 1)
    pmf = np.zeros(bins + 1)
    if damage.size == 0 or events_per_year == 0:
        pmf[0] = 1.0
        return AnnualLoss(events_per_year, 0.0, 0.0, 0.0, 0.0, grid, pmf)
    w = w / w.sum()
    mean_event = float((damage * w).sum())
    single = np.bincount(
        np.minimum(np.rint(damage * bins / cap).astype(int), bins), weights=w, minlength=bins + 1
    )
    term = np.zeros(bins + 1)
    term[0] = 1.0  # distribution of the sum of k events, starting at k = 0
    weight = math.exp(-events_per_year)
    covered, k = 0.0, 0
    while True:
        pmf += weight * term
        covered += weight
        if 1.0 - covered < 1e-12 or k > 400:
            break
        k += 1
        weight *= events_per_year / k
        full = np.convolve(term, single)
        term = full[: bins + 1].copy()
        term[bins] += full[bins + 1 :].sum()  # anything past the cap is full loss
    pmf /= pmf.sum()
    return AnnualLoss(
        events_per_year,
        mean_event,
        float((grid * pmf).sum()),
        events_per_year * mean_event,
        float(1.0 - pmf[0]),
        grid,
        pmf,
    )
