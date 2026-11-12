"""The inventory loads, the detector finds gaps, and the project keeps to its import rules."""

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

import data_source_check
from data_source_check.adapters.crc import enumerate as crc
from data_source_check.build import build_inventory
from data_source_check.core import inventory
from data_source_check.core.records import RecordError

PACKAGE = Path(data_source_check.__file__).parent


def test_inventory_loads_and_is_consistent() -> None:
    sources = inventory.load_sources("crc_sdk")
    findings = inventory.load_findings("crc_sdk")
    inventory.check_references(sources, findings)
    assert len(sources) == 20
    assert len({source.id for source in sources}) == 20
    assert [source.tier or 9 for source in sources] == sorted(
        source.tier or 9 for source in sources
    )
    assert all(source.is_draft for source in sources)  # nothing is signed before it is assessed
    assert {"ibtracs", "ghcnh", "nex-gddp-cmip6"} <= {source.id for source in sources}


def test_every_installed_entry_point_has_an_inventory_entry() -> None:
    """Fails when a crc-sdk upgrade adds a source or an option the inventory does not know."""
    gaps = inventory.unassessed(inventory.load_sources("crc_sdk"), crc.offered())
    assert gaps["unclaimed_symbols"] == []
    assert gaps["new_options"] == []
    assert gaps["could_not_enumerate"] == []


def _era5_untouched(sources: list) -> list:
    """The inventory with era5 as before anyone drafted it: the example of an unassessed source."""
    blank = {tier: "not assessed" for tier in ("exploration", "verification", "validation")}
    return [
        replace(s, assessed_options={}, statement=(), status=blank) if s.id == "era5" else s
        for s in sources
    ]


def test_detector_reports_new_entry_points_and_options() -> None:
    sources = _era5_untouched(inventory.load_sources("crc_sdk"))
    offered = {
        "symbols": ["IBTrACSPlan", "HailReportsPlan", "HazardDataset.local"],
        "ignored": {"HazardDataset.local": "not a source"},
        "options": {"era5": {"recipe": ["txx", "wsdi"]}, "unknown-source": {"x": ["y"]}},
    }
    gaps = inventory.unassessed(sources, offered)
    assert gaps["unclaimed_symbols"] == ["HailReportsPlan"]
    assert gaps["new_options"] == [{"source": "era5", "option": "recipe", "value": "wsdi"}]
    assert "era5" in gaps["unassessed_sources"] and "own-data" not in gaps["unassessed_sources"]
    assert "ibtracs" not in gaps["unassessed_sources"]  # assessed in phase V1


def test_assessed_options_leave_the_open_list() -> None:
    sources = _era5_untouched(inventory.load_sources("crc_sdk"))
    done = [
        replace(s, assessed_options={"recipe": ("txx",)}) if s.id == "era5" else s for s in sources
    ]
    before = inventory.unassessed(sources, {"symbols": []})["unassessed_options"]
    after = inventory.unassessed(done, {"symbols": []})["unassessed_options"]
    gone = {"source": "era5", "option": "recipe", "value": "txx"}
    assert gone in before and gone not in after and len(after) == len(before) - 1


def test_finding_for_an_unknown_source_is_refused() -> None:
    sources = inventory.load_sources("crc_sdk")
    findings = inventory.load_findings("crc_sdk")
    with pytest.raises(RecordError, match="unknown source"):
        inventory.check_references(sources, [replace(findings[0], source="nowhere")])


def test_source_file_name_must_match_its_id(tmp_path: Path) -> None:
    folder = tmp_path / "demo"
    folder.mkdir()
    text = (PACKAGE / "sources" / "crc_sdk" / "ibtracs.toml").read_text()
    (folder / "other.toml").write_text(text)
    with pytest.raises(RecordError, match="does not match"):
        inventory.load_sources("demo", root=tmp_path)


def test_build_writes_page_data_and_inventory_text(tmp_path: Path) -> None:
    payload = build_inventory(page_data=tmp_path / "data", docs=tmp_path / "docs")
    on_disk = json.loads((tmp_path / "data" / "inventory.json").read_text())
    assert on_disk["versions"] == payload["versions"] and len(on_disk["sources"]) == 20
    text = (tmp_path / "docs" / "inventory.md").read_text()
    assert "CRC-001-NEX" in text and "| IBTrACS tropical cyclone tracks (`ibtracs`)" in text
    ibtracs = next(s for s in on_disk["sources"] if s["id"] == "ibtracs")
    assert ibtracs["records"] == "records/ibtracs.json"
    assert {step["outcome"] for step in ibtracs["statement"]} == {
        "confirmed",
        "differs",
        "not checked",
    }
    report = (tmp_path / "docs" / "sources" / "ibtracs.md").read_text()
    assert "Draft: not yet reviewed" in report and "values[ALL]" in report


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    names = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    names += [a.name for node in ast.walk(tree) if isinstance(node, ast.Import) for a in node.names]
    return names


def test_import_rules() -> None:
    """core and reference never import the framework; nothing imports the other projects' code."""
    for path in PACKAGE.rglob("*.py"):
        names = _imports(path)
        other = ("crc_lab", "crc_data_explorer", "lab_common")
        assert not [n for n in names if n.split(".")[0] in other], path
        part = path.relative_to(PACKAGE).parts[0]
        if part in ("core", "reference"):
            framework = [n for n in names if n.split(".")[0] in ("crc_sdk", "crc_framework")]
            assert not framework, f"{path} imports {framework}"
        if part == "reference":
            # the reference side shares no parser with the framework (crc-sdk reads with pyarrow)
            shared = [n for n in names if n.split(".")[0] == "pyarrow" or "adapters" in n]
            assert not shared, f"{path} imports {shared}"
