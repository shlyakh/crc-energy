"""Comparison of two tables, seeded sampling and the making of check records.

The outcome of a check is decided here, by counting differences against a tolerance, and
nowhere else.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from itertools import zip_longest
from typing import Any

from .records import CheckRecord

MAX_EXAMPLES = 5


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sample(items: Iterable[Any], count: int, seed: int) -> list[Any]:
    """A reproducible sample: sorted, drawn with the seed, returned sorted."""
    pool = sorted(set(items))
    if count >= len(pool):
        return pool
    return sorted(random.Random(seed).sample(pool, count))


def compare_rows(
    columns: Sequence[str],
    reference: Iterable[Sequence[Any]],
    framework: Iterable[Sequence[Any]],
    *,
    tolerance: float = 0.0,
) -> dict[str, Any]:
    """Compare two row streams value by value, in order.

    Equality is exact unless ``tolerance`` is given, in which case two numbers agree when
    they differ by no more than it. The largest difference between numbers is reported.
    """

    def same(a: Any, b: Any) -> bool:
        nonlocal largest
        if a == b:
            return True
        if _is_number(a) and _is_number(b):
            largest = max(largest, abs(a - b))
            return abs(a - b) <= tolerance
        return False

    largest = 0.0
    rows_reference = rows_framework = cells = differing = 0
    examples: list[dict[str, Any]] = []
    by_column: dict[str, int] = {}
    for number, (ours, theirs) in enumerate(zip_longest(reference, framework)):
        if ours is None:
            rows_framework += 1
            continue
        if theirs is None:
            rows_reference += 1
            continue
        rows_reference += 1
        rows_framework += 1
        if len(ours) != len(theirs) or len(ours) != len(columns):
            differing += 1
            if len(examples) < MAX_EXAMPLES:
                examples.append(
                    {
                        "row": number,
                        "column": "(row width)",
                        "reference": len(ours),
                        "framework": len(theirs),
                    }
                )
            continue
        cells += len(ours)
        if ours == theirs:
            continue
        for name, a, b in zip(columns, ours, theirs, strict=True):
            if not same(a, b):
                differing += 1
                by_column[name] = by_column.get(name, 0) + 1
                if len(examples) < MAX_EXAMPLES:
                    examples.append({"row": number, "column": name, "reference": a, "framework": b})
    return {
        "rows_reference": rows_reference,
        "rows_framework": rows_framework,
        "values_compared": cells,
        "values_differing": differing,
        "columns_differing": dict(sorted(by_column.items())),
        "largest_difference": largest,
        "examples": examples,
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def rows_agree(result: dict[str, Any]) -> bool:
    return result["rows_reference"] == result["rows_framework"] and result["values_differing"] == 0


def record(
    *,
    source: str,
    check: str,
    tier: str,
    category: str,
    method: str,
    agrees: bool | None,
    versions: dict[str, str],
    result: dict[str, Any] | None = None,
    inputs: Sequence[dict[str, Any]] = (),
    sample: dict[str, Any] | None = None,
    tolerance: dict[str, Any] | None = None,
    steps: Sequence[str] = (),
    note: str = "",
    run_at: str | None = None,
) -> CheckRecord:
    """A validated check record. ``agrees`` None means the check could not be run."""
    outcome = "not checked" if agrees is None else ("confirmed" if agrees else "differs")
    made = CheckRecord(
        source=source,
        check=check,
        tier=tier,
        category=category,
        method=method,
        outcome=outcome,
        run_at=run_at or now(),
        versions=dict(versions),
        inputs=tuple(inputs),
        sample=dict(sample or {}),
        tolerance=dict(tolerance or {"values": "exact equality"}),
        result=dict(result or {}),
        steps=tuple(steps),
        note=note,
    )
    made.validate()
    return made


def step_outcomes(step_ids: Sequence[str], checks: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Outcome of each statement step from the checks that bear on it.

    ``differs`` if any check differs; ``confirmed`` if at least one check bears on the step
    and all of them are confirmed; otherwise ``not checked``.
    """
    seen: dict[str, set[str]] = {step: set() for step in step_ids}
    for check in checks:
        for step in check.get("steps", ()):
            if step in seen:
                seen[step].add(check["outcome"])
    out = {}
    for step, outcomes in seen.items():
        if "differs" in outcomes:
            out[step] = "differs"
        elif outcomes and outcomes <= {"confirmed"}:
            out[step] = "confirmed"
        else:
            out[step] = "not checked"
    return out


def number(value: object) -> str:
    return f"{value:,}" if isinstance(value, int) and not isinstance(value, bool) else str(value)


def rows_summary(result: dict[str, Any]) -> str:
    """One line for a row-by-row comparison."""
    return (
        f"{number(result['rows_reference'])} rows against {number(result['rows_framework'])}; "
        f"{number(result['values_compared'])} values compared, "
        f"{number(result['values_differing'])} differ"
    )


def tally(checks: Iterable[dict[str, Any]]) -> dict[str, int]:
    count: dict[str, int] = {}
    for check in checks:
        count[check["outcome"]] = count.get(check["outcome"], 0) + 1
    return count
