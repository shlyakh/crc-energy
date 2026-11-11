"""Hail impact functions v0: hail diameter in millimetres to a damage ratio in [0, 1].

Specified in ``docs/requirements-hail-impact-v0.md``. Parameters come from one data file,
``hail_v0.json`` (the spec's machine-readable block, unchanged). This module imports only the
standard library and numpy, and nothing from crc-lab or crc-sdk, so it can be lifted into
another package together with the data file and its tests.

These are first-approximation curves. Several defaults are placeholders with no source
(``placeholders`` in the data file); callers must carry that label into anything they publish.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

PARAMETERS = Path(__file__).with_name("hail_v0.json")
SCHEMA = "hail-impact-curves/v0"
HAZARD_INPUT = "hail_diameter_obs_mm"
SIGMOID_CURVES = ("bld_hail_swiss_v0", "car_hail_swiss_v0")
SIGMOID_OUTPUTS = ("damage_ratio", "fraction_affected")

Array = NDArray[np.float64]
_cache: dict[Path, dict[str, Any]] = {}


def validate(document: Mapping[str, Any]) -> None:
    """Raise ValueError unless the parameter document is well formed."""
    if document.get("schema") != SCHEMA:
        raise ValueError(f"expected schema {SCHEMA!r}, got {document.get('schema')!r}")
    curves = document["curves"]
    for glass, knots in curves["pv_plant_hail_v0"]["break_probability"].items():
        xs, ys = [k[0] for k in knots], [k[1] for k in knots]
        if any(b <= a for a, b in zip(xs, xs[1:], strict=False)):
            raise ValueError(f"{glass}: knot diameters must be strictly increasing")
        if any(not 0.0 <= y <= 1.0 for y in ys):
            raise ValueError(f"{glass}: knot values must lie in [0, 1]")
        if any(b < a for a, b in zip(ys, ys[1:], strict=False)):
            raise ValueError(f"{glass}: knot values must not decrease")
    for name in SIGMOID_CURVES:
        for output in SIGMOID_OUTPUTS:
            p = curves[name][output]
            if not p["v_half"] > p["v_thresh"] >= 0:
                raise ValueError(f"{name}.{output}: need v_half > v_thresh >= 0")
            if not 0.0 <= p["scale"] <= 1.0:
                raise ValueError(f"{name}.{output}: scale must lie in [0, 1]")
    for roof, p in curves["bld_hail_roof_v0"]["roof_classes"].items():
        if not (p["theta"] > 0 and p["beta"] > 0):
            raise ValueError(f"{roof}: theta and beta must be positive")
    d = curves["pv_plant_hail_v0"]["defaults"]
    if not (0.0 <= d["p_stow"] <= 1.0 and 0.0 <= d["module_cost_share"] <= 1.0):
        raise ValueError("pv defaults: p_stow and module_cost_share must lie in [0, 1]")
    if not 0.0 <= d["stow_tilt_deg"] < 90.0:
        raise ValueError("pv defaults: stow_tilt_deg must lie in [0, 90)")
    if not 0.0 <= curves["bld_hail_roof_v0"]["defaults"]["roof_cost_share"] <= 1.0:
        raise ValueError("roof defaults: roof_cost_share must lie in [0, 1]")


def load(path: Path = PARAMETERS) -> dict[str, Any]:
    """The validated parameter document (cached per path)."""
    if path not in _cache:
        document = json.loads(path.read_text())
        validate(document)
        _cache[path] = document
    return _cache[path]


def metadata(curve_id: str, path: Path = PARAMETERS) -> dict[str, Any]:
    """``native_metric``, ``calibration_region``, ``confidence``, ``source`` and placeholders."""
    curve = load(path)["curves"][curve_id]
    keys = ("asset", "form", "native_metric", "calibration_region", "confidence", "source")
    return {k: curve[k] for k in keys} | {
        "curve_id": curve_id,
        "hazard_input": HAZARD_INPUT,
        "value_semantics": "damage ratio",
        "placeholders": list(curve.get("placeholders", [])),
    }


def _diameter(d_mm: ArrayLike) -> Array:
    """Finite, non-negative diameters as an array; anything else is rejected, never zeroed."""
    d = np.asarray(d_mm, dtype=np.float64)
    if not np.all(np.isfinite(d)):
        raise ValueError("hail diameter must be finite (missing values are not treated as zero)")
    if np.any(d < 0):
        raise ValueError("hail diameter must be non-negative")
    return d


def _result(values: Array, like: ArrayLike) -> Any:
    return float(values) if np.ndim(like) == 0 else values


# ---- the three functional forms ----


def emanuel_sigmoid(d_mm: ArrayLike, v_thresh: float, v_half: float, scale: float) -> Any:
    """Emanuel-type cubic sigmoid: 0 up to ``v_thresh``, ``scale / 2`` at ``v_half``."""
    d = _diameter(d_mm)
    v = np.maximum(d - v_thresh, 0.0) / (v_half - v_thresh)
    return _result(scale * v**3 / (1.0 + v**3), d_mm)


def piecewise_linear(d_mm: ArrayLike, knots: Sequence[Sequence[float]]) -> Any:
    """Linear interpolation between ``(diameter, value)`` knots, flat outside them."""
    d = _diameter(d_mm)
    xs, ys = [k[0] for k in knots], [k[1] for k in knots]
    return _result(np.interp(d, xs, ys), d_mm)


_erf = np.vectorize(math.erf, otypes=[np.float64])


def lognormal_cdf(d_mm: ArrayLike, theta: float, beta: float) -> Any:
    """Lognormal distribution function with median ``theta`` and log deviation ``beta``; 0 at 0."""
    d = _diameter(d_mm)
    z = np.log(np.where(d > 0, d, 1.0) / theta) / beta
    return _result(np.where(d > 0, 0.5 * (1.0 + _erf(z / math.sqrt(2.0))), 0.0), d_mm)


# ---- the four curves ----


def stow_multiplier(
    stow_tilt_deg: float, *, stow_energy_factor: float | None = None, path: Path = PARAMETERS
) -> float:
    """Effective diameter over actual diameter for a module tilted ``stow_tilt_deg`` from flat.

    Elastic model: normal impact energy scales with cos^2 of the tilt and single-stone energy
    with diameter to the power 3.5. ``stow_energy_factor`` replaces cos^2 (sensitivity only).
    """
    if not 0.0 <= stow_tilt_deg < 90.0:
        raise ValueError("stow_tilt_deg must lie in [0, 90)")
    exponent = load(path)["curves"]["pv_plant_hail_v0"]["stow"]["ke_diameter_exponent"]
    energy = (
        math.cos(math.radians(stow_tilt_deg)) ** 2
        if stow_energy_factor is None
        else stow_energy_factor
    )
    if not 0.0 <= energy <= 1.0:
        raise ValueError("stow_energy_factor must lie in [0, 1]")
    return float(energy ** (1.0 / exponent))


def pv_break_probability(
    d_mm: ArrayLike, glass_class: str | None = None, *, path: Path = PARAMETERS
) -> Any:
    """Module glass-breakage probability at normal incidence (step 1 of the solar curve)."""
    curve = load(path)["curves"]["pv_plant_hail_v0"]
    glass_class = glass_class or curve["defaults"]["glass_class"]
    if glass_class not in curve["break_probability"]:
        raise KeyError(f"unknown glass class {glass_class!r}")
    return piecewise_linear(d_mm, curve["break_probability"][glass_class])


def pv_plant_hail(
    d_mm: ArrayLike,
    *,
    glass_class: str | None = None,
    stow_tilt_deg: float | None = None,
    p_stow: float | None = None,
    module_cost_share: float | None = None,
    stow_energy_factor: float | None = None,
    path: Path = PARAMETERS,
) -> Any:
    """``pv_plant_hail_v0``: damage ratio of plant value.

    A mixture of stowed and unstowed breakage, times the modules' share of plant value. For a
    fixed-tilt plant pass ``p_stow=1`` and the fixed tilt as ``stow_tilt_deg``. Arguments left
    as None take the data file's defaults, three of which are placeholders.
    """
    defaults = load(path)["curves"]["pv_plant_hail_v0"]["defaults"]
    tilt = defaults["stow_tilt_deg"] if stow_tilt_deg is None else stow_tilt_deg
    p = defaults["p_stow"] if p_stow is None else p_stow
    share = defaults["module_cost_share"] if module_cost_share is None else module_cost_share
    if not (0.0 <= p <= 1.0 and 0.0 <= share <= 1.0):
        raise ValueError("p_stow and module_cost_share must lie in [0, 1]")
    d = _diameter(d_mm)
    k = stow_multiplier(tilt, stow_energy_factor=stow_energy_factor, path=path)
    stowed = pv_break_probability(d * k, glass_class, path=path)
    flat = pv_break_probability(d, glass_class, path=path)
    return _result(np.asarray(share * (p * stowed + (1.0 - p) * flat)), d_mm)


def _swiss(curve_id: str, d_mm: ArrayLike, output: str, path: Path) -> Any:
    if output not in SIGMOID_OUTPUTS:
        raise KeyError(f"output must be one of {SIGMOID_OUTPUTS}")
    p = load(path)["curves"][curve_id][output]
    return emanuel_sigmoid(d_mm, p["v_thresh"], p["v_half"], p["scale"])


def bld_hail_swiss(
    d_mm: ArrayLike, *, output: str = "damage_ratio", path: Path = PARAMETERS
) -> Any:
    """``bld_hail_swiss_v0``: buildings, Swiss claims curve. Use ``damage_ratio`` for loss;
    ``fraction_affected`` is for claim counts only and the two are never multiplied."""
    return _swiss("bld_hail_swiss_v0", d_mm, output, path)


def car_hail_swiss(
    d_mm: ArrayLike, *, output: str = "damage_ratio", path: Path = PARAMETERS
) -> Any:
    """``car_hail_swiss_v0``: general car fleet by registered address. Not for cars in the open."""
    return _swiss("car_hail_swiss_v0", d_mm, output, path)


def bld_hail_roof(
    d_mm: ArrayLike,
    *,
    roof_class: str | None = None,
    roof_cost_share: float | None = None,
    path: Path = PARAMETERS,
) -> Any:
    """``bld_hail_roof_v0``: chance the roof needs replacing times the roof's share of value."""
    curve = load(path)["curves"]["bld_hail_roof_v0"]
    roof_class = roof_class or curve["defaults"]["roof_class"]
    if roof_class not in curve["roof_classes"]:
        raise KeyError(f"unknown roof class {roof_class!r}")
    share = curve["defaults"]["roof_cost_share"] if roof_cost_share is None else roof_cost_share
    if not 0.0 <= share <= 1.0:
        raise ValueError("roof_cost_share must lie in [0, 1]")
    p = curve["roof_classes"][roof_class]
    return _result(np.asarray(share * lognormal_cdf(d_mm, p["theta"], p["beta"])), d_mm)


CURVES = {
    "pv_plant_hail_v0": pv_plant_hail,
    "bld_hail_swiss_v0": bld_hail_swiss,
    "bld_hail_roof_v0": bld_hail_roof,
    "car_hail_swiss_v0": car_hail_swiss,
}
