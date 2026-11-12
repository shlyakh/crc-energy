"""Load the inventory (one TOML file per source, one findings file per framework)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .records import ASSESSMENT_TIERS, Finding, RecordError, Source, Step

SOURCES_DIR = Path(__file__).resolve().parents[1] / "sources"


def _tuples(table: dict[str, Any] | None) -> dict[str, tuple[str, ...]]:
    return {name: tuple(values) for name, values in (table or {}).items()}


def load_source(path: Path, framework: str) -> Source:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    status = {tier: "not assessed" for tier in ASSESSMENT_TIERS} | raw.get("status", {})
    source = Source(
        id=raw.get("id", ""),
        framework=framework,
        title=raw.get("title", ""),
        kind=raw.get("kind", ""),
        publisher=raw.get("publisher", ""),
        original=raw.get("original", ""),
        purpose=raw.get("purpose", ""),
        tier=raw.get("tier"),
        tier_reason=raw.get("tier_reason", ""),
        entry_points=tuple(raw.get("entry_points", ())),
        symbols=tuple(raw.get("symbols", ())),
        options=_tuples(raw.get("options")),
        assessed_options=_tuples(raw.get("assessed_options")),
        status=status,
        statement=tuple(Step(**step) for step in raw.get("statement", ())),
        notes=raw.get("notes", ""),
        explorer=raw.get("explorer", ""),
        drafted_by=raw.get("drafted_by", ""),
        reviewed_by=raw.get("reviewed_by", ""),
        reviewed_on=raw.get("reviewed_on", ""),
    )
    if source.id != path.stem:
        raise RecordError(f"{path.name}: id {source.id!r} does not match the file name")
    source.validate()
    return source


def load_sources(framework_dir: str, root: Path = SOURCES_DIR) -> list[Source]:
    """Every source of one framework, ordered by tier then title."""
    folder = root / framework_dir
    framework = framework_dir.replace("_", "-")
    sources = [
        load_source(path, framework)
        for path in sorted(folder.glob("*.toml"))
        if path.name != "findings.toml"
    ]
    return sorted(sources, key=lambda s: (s.tier or 9, s.title.lower()))


def load_findings(framework_dir: str, root: Path = SOURCES_DIR) -> list[Finding]:
    path = root / framework_dir / "findings.toml"
    if not path.exists():
        return []
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    findings = []
    for item in raw.get("finding", ()):
        finding = Finding(**{**item, "evidence": tuple(item.get("evidence", ()))})
        finding.validate()
        findings.append(finding)
    ids = [finding.id for finding in findings]
    if len(ids) != len(set(ids)):
        raise RecordError("finding ids must be unique")
    return findings


def check_references(sources: list[Source], findings: list[Finding]) -> None:
    """Findings must point at sources that exist (or at the framework as a whole)."""
    known = {source.id for source in sources} | {"framework"}
    for finding in findings:
        if finding.source not in known:
            raise RecordError(f"finding {finding.id}: unknown source {finding.source!r}")


def unassessed(sources: list[Source], offered: dict[str, Any]) -> dict[str, Any]:
    """What the framework offers that the inventory does not cover.

    ``offered`` comes from a framework adapter: ``symbols`` (public entry points found in the
    installed framework), ``ignored`` (symbols that are not sources, with the reason) and
    ``options`` (per source id, option name -> values found in the framework's own tables).
    """
    claimed = {name for source in sources for name in (*source.entry_points, *source.symbols)}
    unclaimed = sorted(set(offered["symbols"]) - claimed - set(offered.get("ignored", {})))
    by_id = {source.id: source for source in sources}
    new_options, open_options = [], []
    for source_id, table in sorted(offered.get("options", {}).items()):
        source = by_id.get(source_id)
        if source is None:
            continue
        for name, values in sorted(table.items()):
            for value in sorted(set(values) - set(source.options.get(name, ()))):
                new_options.append({"source": source_id, "option": name, "value": value})
    for source in sources:
        for name, values in sorted(source.options.items()):
            done = set(source.assessed_options.get(name, ()))
            for value in values:
                if value not in done:
                    open_options.append({"source": source.id, "option": name, "value": value})
    return {
        "unclaimed_symbols": unclaimed,
        "new_options": new_options,
        "unassessed_sources": [
            source.id
            for source in sources
            if source.kind != "user data"
            and all(source.status[tier] == "not assessed" for tier in ASSESSMENT_TIERS)
        ],
        "unassessed_options": open_options,
        "could_not_enumerate": offered.get("could_not_enumerate", []),
    }
