"""V6: the gate for drafted assessments; a draft never reaches the page by itself."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from data_source_check import build, draft
from data_source_check.core.records import Step

GOOD_REFERENCE = "import csv\n\ndef rows(path):\n    return list(csv.reader(open(path)))\n"
GOOD_TESTS = (
    "def test_values_agree():\n    pass\n\ndef test_fault_without_trimming_differs():\n    pass\n"
)


def _draft(tmp_path: Path, *, reference: str = GOOD_REFERENCE, tests: str = GOOD_TESTS,
           checks: list[dict] | None = None) -> dict[str, Path]:  # fmt: skip
    files = {role: tmp_path / f"{role.replace(' ', '_')}.txt" for role in draft.paths("x")}
    for path in files.values():
        path.write_text("x\n")
    files["reference reader"].write_text(reference)
    files["tests"].write_text(tests)
    if checks is None:
        checks = [{"check": "values", "summary": "3 of 3 agree", "outcome": "confirmed",
                   "steps": ["read", "trim"]}]  # fmt: skip
    files["draft records"].write_text(json.dumps({"checks": checks}))
    return files


def _source(**changes: object):
    base = draft.find_source("chirps")  # an entry of the real inventory, used as a template
    steps = (
        Step(id="read", text="Reads the file.", code_ref="crc_sdk/x.py:1"),
        Step(id="trim", text="Trims.", code_ref="crc_sdk/x.py:2"),
    )
    status = base.status | {"verification": "in progress"}
    made = replace(base, statement=steps, drafted_by="agent, 2026-11-12", status=status)
    return replace(made, **changes)


def test_complete_draft_passes(tmp_path: Path) -> None:
    assert draft.check("chirps", files=_draft(tmp_path), source=_source()) == []


def test_missing_file_is_reported(tmp_path: Path) -> None:
    files = _draft(tmp_path)
    files["drafting note"].unlink()
    assert any(
        "drafting note is missing" in p
        for p in draft.check("chirps", files=files, source=_source())
    )


@pytest.mark.parametrize(
    ("changes", "words"),
    [
        ({"drafted_by": ""}, "who drafted"),
        ({"reviewed_by": "Y", "reviewed_on": "2026-11-12"}, "cannot be marked as reviewed"),
        ({"statement": ()}, "no statement"),
        ({"statement": (Step(id="read", text="Reads."),)}, "no code reference"),
    ],
)
def test_source_file_rules(tmp_path: Path, changes: dict, words: str) -> None:
    problems = draft.check("chirps", files=_draft(tmp_path), source=_source(**changes))
    assert any(words in p for p in problems), problems


def test_assessed_status_is_refused_for_a_draft(tmp_path: Path) -> None:
    source = _source()
    source = replace(source, status=source.status | {"verification": "assessed"})
    assert any(
        "in progress" in p for p in draft.check("chirps", files=_draft(tmp_path), source=source)
    )


def test_reference_reader_must_stay_independent(tmp_path: Path) -> None:
    for line in ("import crc_sdk", "import pyarrow.parquet", "from ..adapters.crc import x"):
        files = _draft(tmp_path, reference=line + "\n")
        problems = draft.check("chirps", files=files, source=_source())
        assert any("reference reader imports" in p for p in problems), line


def test_a_draft_without_a_fault_test_is_incomplete(tmp_path: Path) -> None:
    files = _draft(tmp_path, tests="def test_values_agree():\n    pass\n")
    assert any(
        "deliberate-fault" in p for p in draft.check("chirps", files=files, source=_source())
    )


def test_unchecked_step_needs_a_note_and_checks_need_summaries(tmp_path: Path) -> None:
    checks = [{"check": "values", "summary": "", "outcome": "confirmed", "steps": ["read", "gone"]}]
    problems = draft.check("chirps", files=_draft(tmp_path, checks=checks), source=_source())
    assert any("has no summary" in p for p in problems)
    assert any("unknown steps" in p for p in problems)
    assert any("'trim' is not checked" in p for p in problems)


def test_published_assessment_is_not_a_draft() -> None:
    assert draft.check("ibtracs") == ["ibtracs is a published assessment, not a draft"]
    with pytest.raises(SystemExit):
        build.assess_draft("ibtracs", live=False)


def test_draft_records_stay_out_of_the_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Module:
        @staticmethod
        def assess(folder: Path, *, live: bool, versions: dict, log: object) -> dict:
            return {"source": "chirps", "checks": []}

    monkeypatch.setattr(build, "draft_module", lambda source_id: Module)
    monkeypatch.setattr(build, "DRAFTS", tmp_path / "drafts")
    before = sorted(p.name for p in (build.PAGE_DATA / "records").iterdir())
    build.assess_draft("chirps", live=False, cache=tmp_path / "cache")
    assert (tmp_path / "drafts" / "records" / "chirps.json").exists()
    assert sorted(p.name for p in (build.PAGE_DATA / "records").iterdir()) == before


def test_unbuilt_draft_cannot_be_accepted() -> None:
    with pytest.raises(SystemExit):
        draft.accept("chirps")


def test_brief_names_entry_point_and_files() -> None:
    text = draft.brief("noaa-water-levels")
    assert "NOAAExtremeWaterLevelPlan" in text and "crc_sdk/workflows/" in text
    assert "reference/noaa_water_levels.py" in text
