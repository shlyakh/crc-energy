"""IBTrACS assessment on a fixed excerpt of NOAA's file (three storms, 2023-2025), offline.

Both sides download through a fake ``urlopen`` that serves the excerpt, so the whole path
runs: reference download and parse, crc-sdk snapshot and batches, comparison, records.
"""

import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from data_source_check import build
from data_source_check.assessments import ibtracs as assessment
from data_source_check.core import compare, inventory
from data_source_check.core.records import RecordError
from data_source_check.reference import ibtracs as reference

SAMPLE = Path(__file__).parent / "fixtures" / "ibtracs_sample.csv"
VERSIONS = {"crc-sdk": "test"}
OFFERED = ["NA", "active"]


class Response(io.BytesIO):
    status = 200
    headers = {"ETag": '"sample"', "Last-Modified": "Tue, 10 Nov 2026 10:03:02 GMT"}


def fake_urlopen(request, timeout=None):  # noqa: ANN001, ANN201
    address = request.full_url
    if address.endswith("/"):
        return Response(
            b'<a href="ibtracs.ACTIVE.list.v04r01.csv">x</a> <a href="ibtracs.NA.list.v04r01.csv">'
        )
    if "ibtracs.NA." not in address:
        raise HTTPError(address, 404, "Not Found", None, None)  # type: ignore[arg-type]
    return Response(SAMPLE.read_bytes())


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("data_source_check.reference.ibtracs.urlopen", fake_urlopen)
    monkeypatch.setattr("crc_sdk.workflows.ibtracs.urlopen", fake_urlopen)


def run(tmp_path: Path, *, live: bool = True, **more: object) -> dict:
    return assessment.assess(
        ["NA", "active"],
        OFFERED,
        tmp_path,
        tmp_path / "crc-sdk",
        live=live,
        versions=VERSIONS,
        **more,
    )  # type: ignore[arg-type]


def outcomes(records: dict) -> dict[str, str]:
    return {check["check"]: check["outcome"] for check in records["checks"]}


def test_reference_reader_applies_the_two_rules() -> None:
    columns, units = reference.header(SAMPLE)
    assert columns[:3] == ["SID", "SEASON", "NUMBER"] and len(columns) == len(units) == 174
    rows = list(reference.rows(SAMPLE))
    raw = list(reference.rows(SAMPLE, trim=False, empty_as_null=False))
    assert len(rows) == len(raw) > 20
    assert any(value == " " for value in raw[0]) and None in rows[0]
    assert all(value is None or value == value.strip() != "" for row in rows for value in row)
    seasons = reference.storm_seasons(SAMPLE)
    assert len(seasons) == 3
    one = next(iter(seasons))
    picked = list(reference.select(rows, columns, storm_ids=[one]))
    assert picked and all(row[0] == one for row in picked)


def test_assessment_confirms_every_step_on_the_excerpt(tmp_path: Path, served: None) -> None:
    records = run(tmp_path)
    got = outcomes(records)
    assert got.pop("address") == "differs"  # "active" is accepted by crc-sdk and not served
    assert set(got.values()) == {"confirmed"} and len(got) == 7
    assert records["subsets_assessed"] == ["NA"] and "active" in records["subsets_skipped"]
    values = next(c for c in records["checks"] if c["check"] == "values[NA]")
    assert values["result"]["values_compared"] == values["result"]["rows_reference"] * 174
    assert values["inputs"][0]["sha256"] == reference.sha256(SAMPLE)
    assert records["exploration"]["NA"]["storms"] == 3


@pytest.mark.parametrize(
    ("rules", "expected"),
    [
        (
            {"trim": False},
            {"values[NA]", "storm-filter[NA]", "season-filter[NA]", "both-filters[NA]"},
        ),
        (
            {"empty_as_null": False},
            {"values[NA]", "storm-filter[NA]", "season-filter[NA]", "both-filters[NA]"},
        ),
    ],
)
def test_a_wrong_reference_rule_ends_as_differs(
    tmp_path: Path, served: None, rules: dict[str, bool], expected: set[str]
) -> None:
    """A check that cannot fail proves nothing: break one rule and the comparison must differ."""
    got = outcomes(run(tmp_path, rules=rules))
    assert {name for name, value in got.items() if value == "differs"} == expected | {"address"}


def test_a_changed_file_ends_as_differs(tmp_path: Path, served: None) -> None:
    run(tmp_path)
    cached = tmp_path / "reference" / "NA.csv"
    text = cached.read_text(encoding="utf-8")
    cached.write_text(text.replace("2023", "2022", 1), encoding="utf-8")
    sidecar = tmp_path / "reference" / "NA.json"
    record = json.loads(sidecar.read_text())
    sidecar.write_text(json.dumps(record | {"sha256": reference.sha256(cached)}))
    got = outcomes(run(tmp_path, live=False))
    assert got["bytes[NA]"] == "differs" and got["values[NA]"] == "differs"


def test_a_second_run_gives_the_same_records_apart_from_run_times(
    tmp_path: Path, served: None
) -> None:
    def stable(records: dict) -> str:
        records = json.loads(json.dumps(records))
        records.pop("run_at")
        for check in records["checks"]:
            check.pop("run_at")
        return json.dumps(records, sort_keys=True)

    first = run(tmp_path)
    assert stable(run(tmp_path, live=False)) == stable(first)


def test_step_outcomes_follow_the_checks() -> None:
    checks = [
        {"steps": ["a", "b"], "outcome": "confirmed"},
        {"steps": ["b"], "outcome": "differs"},
        {"steps": ["c"], "outcome": "not checked"},
    ]
    assert compare.step_outcomes(["a", "b", "c", "d"], checks) == {
        "a": "confirmed",
        "b": "differs",
        "c": "not checked",
        "d": "not checked",
    }


def test_an_empty_comparison_is_not_a_confirmation() -> None:
    result = compare.compare_rows(["x"], [], [])
    assert result["values_compared"] == 0  # the assessment records this as "not checked"
    assert compare.sample(range(100), 5, 1) == compare.sample(range(100), 5, 1)
    assert compare.sample(range(100), 5, 1) != compare.sample(range(100), 5, 2)


def test_committed_records_match_the_inventory() -> None:
    """The source file, the committed records and the generated page data agree."""
    source = next(s for s in inventory.load_sources("crc_sdk") if s.id == "ibtracs")
    records = build.load_records("ibtracs")
    assert records is not None
    assert sorted(source.assessed_options["subset"]) == records["subsets_assessed"]
    assessed = build.with_outcomes(source, records)
    by_step = {step.id: step.outcome for step in assessed.statement}
    assert by_step["address"] == "differs" and by_step["reuse"] == "not checked"
    assert all(v == "confirmed" for k, v in by_step.items() if k not in ("address", "reuse"))
    used = {step for check in records["checks"] for step in check["steps"]}
    assert used <= set(by_step)  # no check points at a step the statement lacks
    findings = inventory.load_findings("crc_sdk")
    assert any(f.source == "ibtracs" and f.kind == "defect" for f in findings)  # the differing step


def test_a_step_left_unchecked_must_say_why() -> None:
    source = next(s for s in inventory.load_sources("crc_sdk") if s.id == "ibtracs")
    with pytest.raises(RecordError, match="say why"):
        build.with_outcomes(source, {"checks": []})
