"""The v0 hail curves as crc-sdk impact expressions, where the form fits.

crc-framework's sigmoid is a logistic, not the Emanuel cubic, and its impact context carries no
glass class, stow or roof class. So every curve is offered as a tabulated expression: exact for
the piecewise-linear solar curves, sampled every millimetre for the Swiss and roof curves. The
plain callables in ``hail_curves`` stay the reference.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from crc_lab.impacts import hail_curves as hc

CALIBRATION = {
    "exposure_variable": hc.HAZARD_INPUT,  # kept distinct from any radar hail metric
    "exposure_unit": "mm",
    "impact_metric": "damage_ratio",
    "impact_unit": "fraction",
}
SAMPLED_TO_MM = 150


def pv_plant_knots(**parameters: Any) -> list[list[float]]:
    """Exact knots of the stow mixture: the breakage knots and the same knots divided by the
    stow multiplier (the mixture of two piecewise-linear curves is piecewise linear)."""
    curve = hc.load()["curves"]["pv_plant_hail_v0"]
    glass = parameters.get("glass_class") or curve["defaults"]["glass_class"]
    tilt = parameters.get("stow_tilt_deg")
    k = hc.stow_multiplier(curve["defaults"]["stow_tilt_deg"] if tilt is None else tilt)
    xs = sorted(
        {float(x) for x, _ in curve["break_probability"][glass]}
        | {x / k for x, _ in curve["break_probability"][glass]}
    )
    return [[x, float(hc.pv_plant_hail(x, **parameters))] for x in xs]


def definitions() -> dict[str, dict[str, Any]]:
    """Curve id -> points, whether they are exact, and the function they stand for."""
    curve = hc.load()["curves"]["pv_plant_hail_v0"]
    grid = [float(x) for x in range(SAMPLED_TO_MM + 1)]
    out: dict[str, dict[str, Any]] = {}
    for glass, knots in curve["break_probability"].items():
        out[f"pv_break_probability_{glass}"] = {
            "points": [[float(x), float(y)] for x, y in knots],
            "exact": True,
            "function": lambda d, g=glass: hc.pv_break_probability(d, g),
            "metadata": hc.metadata("pv_plant_hail_v0"),
        }
    out["pv_plant_hail_v0"] = {
        "points": pv_plant_knots(),
        "exact": True,
        "function": hc.pv_plant_hail,
        "metadata": hc.metadata("pv_plant_hail_v0"),
    }
    for name in ("bld_hail_swiss_v0", "bld_hail_roof_v0", "car_hail_swiss_v0"):
        function = hc.CURVES[name]
        out[name] = {
            "points": [[x, float(function(x))] for x in grid],
            "exact": False,
            "function": function,
            "metadata": hc.metadata(name),
        }
    return out


def expressions() -> dict[str, dict[str, Any]]:
    """Build each expression with crc-sdk and measure its largest gap to the callable."""
    from crc_sdk.impacts import ImpactExpression

    fine = np.linspace(0.0, 200.0, 20001)
    out: dict[str, dict[str, Any]] = {}
    for name, spec in definitions().items():
        expression = ImpactExpression.tabulated(spec["points"], calibration=CALIBRATION)
        gap = float(np.max(np.abs(np.asarray(expression.evaluate(fine)) - spec["function"](fine))))
        out[name] = {
            "expression": expression,
            "points": len(spec["points"]),
            "exact": spec["exact"],
            "max_abs_gap": gap,
            "definition_hash": expression.definition_hash,
            "monotonicity": expression.monotonicity,
            "metadata": spec["metadata"],
        }
    return out
