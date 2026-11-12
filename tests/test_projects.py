"""V5: the projects in this repository keep to themselves, and each one's site check runs."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
SITE = SRC.parent / "site"
#: package -> the other packages of this repository it may import
ALLOWED = {
    "lab_common": set(),
    "crc_lab": {"lab_common"},
    "crc_data_explorer": {"lab_common"},
    "data_source_check": set(),
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {
        (n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
    }
    names |= {
        a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    return names


@pytest.mark.parametrize("package", sorted(ALLOWED))
def test_packages_import_only_what_they_may(package: str) -> None:
    others = set(ALLOWED) - {package} - ALLOWED[package]
    for path in (SRC / package).rglob("*.py"):
        assert not _imports(path) & others, f"{path} imports {_imports(path) & others}"


def test_every_registry_layer_belongs_to_one_project_check() -> None:
    registry = json.loads((SITE / "layers.json").read_text())
    origins = {s["origin"] for s in registry["sources"]}
    assert origins == {"crc-lab", "crc-sdk"}  # the two origins the site checks cover


def test_layer_check_reports_a_missing_file(tmp_path: Path) -> None:
    from lab_common.site import missing_files, missing_layer_files

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "manifest.json").write_text(json.dumps({"horizons": [2050]}))
    (tmp_path / "data" / "a.json").write_text("{}")
    registry = {
        "sources": [{"id": "s1", "origin": "crc-sdk"}, {"id": "s2", "origin": "crc-lab"}],
        "layers": [
            {"id": "outline", "kind": "geojson", "file": "data/a.json"},
            {"id": "cells", "kind": "h3-cells", "source_id": "s1", "file": "data/c/{horizon}.json"},
            {"id": "pts", "kind": "points", "source_id": "s2", "file": "data/a.json"},
            {"id": "lost", "kind": "points", "source_id": "nobody", "file": "data/a.json"},
        ],
    }
    (tmp_path / "layers.json").write_text(json.dumps(registry))
    missing, count = missing_layer_files(tmp_path, "crc-sdk")
    assert count == 2  # the outline and the cells; the crc-lab layer is the other project's
    assert missing == ["data/c/2050.json", "source entry for layer lost (nobody)"]
    missing, count = missing_layer_files(tmp_path, "crc-lab")
    assert count == 2 and missing == ["source entry for layer lost (nobody)"]
    assert missing_files(tmp_path, ("layers.json", "nope.css")) == ["nope.css"]


def test_pages_forward_old_addresses() -> None:
    landing = (SITE / "index.html").read_text()
    assert "validation/explore/" in landing and '"hail/"' in landing and "hashchange" in landing
    assert "location.replace(EXPLORER" in (SITE / "hail" / "hail.js").read_text()
    assert "location.replace(HAIL" in (SITE / "validation" / "explore" / "explore.js").read_text()
    assert 'location.replace("../"' in (SITE / "next" / "index.html").read_text()
