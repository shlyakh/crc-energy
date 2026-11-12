"""The record format: sources, transformation steps, check records and findings.

Everything the page and the reports show is generated from these records. The vocabulary
is fixed here and explained in ``docs/validation/method.md``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

SCHEMA = "data_source_check/0.1"

#: What a source hands to its user.
SOURCE_KINDS = (
    "pass-through",  # the publisher's records, reformatted only
    "annual samples",  # reduced to annual values, no fit
    "fitted curves",  # reduced and fitted by the framework
    "pre-fitted release",  # curves fitted elsewhere and published by the framework's owner
    "user data",  # not an upstream source
)
TIERS = (1, 2, 3)
#: Outcome of one transformation step or one check.
OUTCOMES = ("confirmed", "differs", "not checked", "not applicable")
#: Progress of each assessment tier for a source.
TIER_STATUS = ("not assessed", "in progress", "assessed", "not possible")
ASSESSMENT_TIERS = ("exploration", "verification", "validation")
#: Check categories, after the Copernicus C3S quality assessments.
CATEGORIES = (
    "completeness",
    "consistency",
    "extremes",
    "resolution",
    "timeliness",
    "uncertainty",
    "validation",
    "fidelity",  # agreement with the publisher's original (tier 2); not a C3S category
)
FINDING_KINDS = ("defect", "doc-code difference", "observation")
FINDING_STATUS = ("open", "reported upstream", "fixed", "by design")
#: How a finding is known.
BASIS = ("reproduced", "code reading")


class RecordError(ValueError):
    """A record does not follow the format."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RecordError(message)


def _one_of(value: Any, allowed: tuple[Any, ...], name: str) -> None:
    _require(value in allowed, f"{name} must be one of {allowed}, got {value!r}")


def _iso_date(value: str, name: str) -> None:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise RecordError(f"{name} must be an ISO date, got {value!r}") from error


@dataclass(frozen=True)
class Step:
    """One thing the framework does between the publisher's bytes and its output."""

    id: str
    text: str
    code_ref: str = ""
    outcome: str = "not checked"
    note: str = ""  # why a step is not checked, or what the outcome does not cover

    def validate(self) -> None:
        _require(bool(self.id and self.text), "a step needs an id and a text")
        _one_of(self.outcome, OUTCOMES, "step outcome")


@dataclass(frozen=True)
class Source:
    """One entry of the inventory."""

    id: str
    framework: str
    title: str
    kind: str
    publisher: str
    original: str
    purpose: str
    tier: int | None
    tier_reason: str
    entry_points: tuple[str, ...]
    symbols: tuple[str, ...] = ()
    options: dict[str, tuple[str, ...]] = field(default_factory=dict)
    assessed_options: dict[str, tuple[str, ...]] = field(default_factory=dict)
    status: dict[str, str] = field(default_factory=dict)
    statement: tuple[Step, ...] = ()
    notes: str = ""
    #: address of a view of this source in a data explorer, relative to the page; empty if none
    explorer: str = ""
    #: who or what wrote the draft, e.g. "agent (draft-source-assessment skill), 2026-11-12"
    drafted_by: str = ""
    reviewed_by: str = ""
    reviewed_on: str = ""

    def validate(self) -> None:
        for name in ("id", "framework", "title", "publisher", "original", "purpose"):
            _require(bool(getattr(self, name)), f"source {self.id!r}: {name} is empty")
        _one_of(self.kind, SOURCE_KINDS, f"source {self.id!r}: kind")
        if self.kind == "user data":
            _require(self.tier is None, f"source {self.id!r}: user data has no tier")
        else:
            _one_of(self.tier, TIERS, f"source {self.id!r}: tier")
            _require(bool(self.tier_reason), f"source {self.id!r}: tier_reason is empty")
        _require(bool(self.entry_points), f"source {self.id!r}: no entry point")
        _require(
            set(self.status) == set(ASSESSMENT_TIERS),
            f"source {self.id!r}: status needs exactly {ASSESSMENT_TIERS}",
        )
        for tier, value in self.status.items():
            _one_of(value, TIER_STATUS, f"source {self.id!r}: status.{tier}")
        for name, values in self.assessed_options.items():
            extra = set(values) - set(self.options.get(name, ()))
            _require(not extra, f"source {self.id!r}: assessed {name} {sorted(extra)} not offered")
        for step in self.statement:
            step.validate()
        _require(
            bool(self.reviewed_by) == bool(self.reviewed_on),
            f"source {self.id!r}: reviewed_by and reviewed_on go together",
        )
        if self.reviewed_on:
            _iso_date(self.reviewed_on, f"source {self.id!r}: reviewed_on")

    @property
    def is_draft(self) -> bool:
        return not self.reviewed_by

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["draft"] = self.is_draft
        return out


@dataclass(frozen=True)
class Finding:
    """Something the framework does that its user should know, worded neutrally."""

    id: str
    source: str
    kind: str
    title: str
    documented: str  # what the documentation says, with its reference ("" if silent)
    observed: str  # what the code or the data shows
    evidence: tuple[str, ...]  # file:line references or record ids
    basis: str
    status: str
    found_on: str
    framework_version: str
    consequence: str = ""
    upstream_ref: str = ""  # issue or pull request, once reported
    fixed_in: str = ""

    def validate(self) -> None:
        _require(bool(self.id and self.source and self.title), "a finding needs id, source, title")
        _one_of(self.kind, FINDING_KINDS, f"finding {self.id}: kind")
        _one_of(self.basis, BASIS, f"finding {self.id}: basis")
        _one_of(self.status, FINDING_STATUS, f"finding {self.id}: status")
        _require(bool(self.observed), f"finding {self.id}: observed is empty")
        _require(bool(self.evidence), f"finding {self.id}: no evidence")
        _iso_date(self.found_on, f"finding {self.id}: found_on")
        if self.kind == "doc-code difference":
            _require(bool(self.documented), f"finding {self.id}: documented is empty")
        if self.status == "reported upstream":
            _require(bool(self.upstream_ref), f"finding {self.id}: reported without a reference")
        if self.status == "fixed":
            _require(bool(self.fixed_in), f"finding {self.id}: fixed without a version")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CheckRecord:
    """The result of running one check once. Written by code, never by hand."""

    source: str
    check: str
    tier: str
    category: str
    method: str
    outcome: str
    run_at: str  # ISO timestamp, UTC
    versions: dict[str, str]
    inputs: tuple[dict[str, Any], ...] = ()  # url, sha256, retrieved_at of every file read
    sample: dict[str, Any] = field(default_factory=dict)  # what was compared, and the seed
    tolerance: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    steps: tuple[str, ...] = ()  # statement step ids this check bears on
    note: str = ""
    summary: str = ""  # one line of numbers for people, written by the assessment from the result
    schema: str = SCHEMA

    def validate(self) -> None:
        _require(
            bool(self.source and self.check and self.method), "a check needs source, id, method"
        )
        _one_of(self.tier, ASSESSMENT_TIERS, f"check {self.check}: tier")
        _one_of(self.category, CATEGORIES, f"check {self.check}: category")
        _one_of(self.outcome, OUTCOMES, f"check {self.check}: outcome")
        _require(bool(self.versions), f"check {self.check}: versions are missing")
        _require(self.run_at.endswith(("Z", "+00:00")), f"check {self.check}: run_at must be UTC")
        if self.outcome in ("confirmed", "differs"):
            _require(bool(self.result), f"check {self.check}: an outcome needs a result")
        if self.outcome == "not checked":
            _require(bool(self.note), f"check {self.check}: say why it was not checked")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
