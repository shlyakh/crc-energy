"""The record format refuses records that would mislead."""

from dataclasses import replace

import pytest

from data_source_check.core.records import CheckRecord, Finding, RecordError, Source, Step

STATUS = {
    "exploration": "not assessed",
    "verification": "not assessed",
    "validation": "not assessed",
}


def source(**changes: object) -> Source:
    base = Source(
        id="demo",
        framework="demo-sdk",
        title="Demo",
        kind="pass-through",
        publisher="Someone",
        original="https://example.org/data",
        purpose="A purpose.",
        tier=3,
        tier_reason="Tier 3: not used.",
        entry_points=("DemoPlan",),
        options={"recipe": ("a", "b")},
        status=dict(STATUS),
    )
    return replace(base, **changes)


def finding(**changes: object) -> Finding:
    base = Finding(
        id="X-001",
        source="demo",
        kind="observation",
        title="A title",
        documented="",
        observed="Something.",
        evidence=("file.py:1",),
        basis="code reading",
        status="open",
        found_on="2026-11-11",
        framework_version="1.0",
    )
    return replace(base, **changes)


def check(**changes: object) -> CheckRecord:
    base = CheckRecord(
        source="demo",
        check="values-equal",
        tier="verification",
        category="fidelity",
        method="Compare every value.",
        outcome="confirmed",
        run_at="2026-11-11T12:00:00Z",
        versions={"demo-sdk": "1.0"},
        result={"compared": 10, "different": 0},
    )
    return replace(base, **changes)


def test_valid_records_pass() -> None:
    source().validate()
    finding().validate()
    check().validate()
    assert source().is_draft and source().to_dict()["draft"] is True


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "magic"},
        {"tier": 4},
        {"tier_reason": ""},
        {"entry_points": ()},
        {"status": {"exploration": "assessed"}},
        {"status": {**STATUS, "verification": "done"}},
        {"assessed_options": {"recipe": ("c",)}},
        {"reviewed_by": "Yuri"},
        {"reviewed_by": "Yuri", "reviewed_on": "yesterday"},
        {"statement": (Step("s1", "Trim.", outcome="fine"),)},
        {"kind": "user data"},
    ],
)
def test_bad_sources_are_refused(changes: dict[str, object]) -> None:
    with pytest.raises(RecordError):
        source(**changes).validate()


def test_signed_source_is_not_a_draft() -> None:
    signed = source(reviewed_by="Yuri", reviewed_on="2026-11-12")
    signed.validate()
    assert not signed.is_draft


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "bug"},
        {"basis": "hearsay"},
        {"evidence": ()},
        {"observed": ""},
        {"found_on": "11/11/2026"},
        {"kind": "doc-code difference"},  # needs what the documentation says
        {"status": "reported upstream"},  # needs the reference
        {"status": "fixed"},  # needs the version
    ],
)
def test_bad_findings_are_refused(changes: dict[str, object]) -> None:
    with pytest.raises(RecordError):
        finding(**changes).validate()


@pytest.mark.parametrize(
    "changes",
    [
        {"outcome": "passed"},
        {"category": "vibes"},
        {"tier": "audit"},
        {"versions": {}},
        {"run_at": "2026-11-11T12:00:00"},
        {"result": {}},  # an outcome needs its numbers
        {"outcome": "not checked"},  # needs the reason
    ],
)
def test_bad_checks_are_refused(changes: dict[str, object]) -> None:
    with pytest.raises(RecordError):
        check(**changes).validate()


def test_not_checked_with_a_reason_is_allowed() -> None:
    check(
        outcome="not checked", result={}, note="The publisher's server was unreachable."
    ).validate()
