"""Build the inventory, the findings list and the page data.

    python -m data_source_check.build                   # inventory and page data (no network)
    python -m data_source_check.build ibtracs --live    # assess a source from the publisher
    python -m data_source_check.build ibtracs           # the same from the local caches
    python -m data_source_check.build <id> --draft [--live]   # a drafted assessment; see draft.py

An assessment writes its records to ``site/validation/data/records/<source>.json``. The
inventory, the page and ``docs/validation/sources/<source>.md`` are generated from records.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .adapters.crc import enumerate as crc
from .core import compare, inventory
from .core.io import write_json_atomic, write_text_atomic
from .core.records import SCHEMA, RecordError, Source
from .core.report import inventory_markdown, source_markdown

REPO = Path(__file__).resolve().parents[2]
PAGE_DATA = REPO / "site" / "validation" / "data"
DOCS = REPO / "docs" / "validation"
CACHE = REPO / "data" / "cache" / "validation"
ASSESSMENTS = ("ibtracs", "ghcnh", "nex-gddp-cmip6")
#: where a drafted assessment writes its records until a person accepts it (git-ignored)
DRAFTS = CACHE / "drafts"
#: a local clone of crc-sdk carrying fixes not yet released; used only where a check says so
FIXED_CLONE = REPO.parent / "forks" / "crc-sdk"


def load_records(source_id: str, page_data: Path = PAGE_DATA) -> dict[str, Any] | None:
    path = page_data / "records" / f"{source_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def with_outcomes(source: Source, records: dict[str, Any] | None) -> Source:
    """The source with each statement step's outcome taken from its check records."""
    if not source.statement:
        return source
    if records is None:
        if source.status["verification"] == "assessed":
            raise RecordError(f"source {source.id!r}: verification is assessed but has no records")
        return source
    outcomes = compare.step_outcomes([step.id for step in source.statement], records["checks"])
    steps = tuple(replace(step, outcome=outcomes[step.id]) for step in source.statement)
    for step in steps:
        if step.outcome == "not checked" and not step.note:
            raise RecordError(f"source {source.id!r}: step {step.id!r} is not checked; say why")
    return replace(source, statement=steps)


def draft_module(source_id: str) -> Any:
    """The assessment module of a drafted source: ``assessments/<id with _ for ->.py``."""
    import importlib

    name = f"{__package__}.assessments.{source_id.replace('-', '_')}"
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name != name:
            raise
        raise SystemExit(f"no assessment module for {source_id!r} ({name})") from error


def assess_draft(source_id: str, *, live: bool, cache: Path = CACHE) -> dict[str, Any]:
    """Run a drafted assessment. Its records go to the draft folder, never to the page."""
    if source_id in ASSESSMENTS:
        raise SystemExit(f"{source_id!r} is a published assessment; run it without --draft")
    module = draft_module(source_id)
    offered = crc.offered()
    run = module.assess(cache / source_id, live=live, versions=offered["versions"], log=print)
    run = {"schema": SCHEMA, "framework": offered["framework"]} | run
    write_json_atomic(DRAFTS / "records" / f"{source_id}.json", run)
    return run


def assess_source(
    source_id: str, *, live: bool, page_data: Path = PAGE_DATA, cache: Path = CACHE
) -> dict[str, Any]:
    """Run one source's assessment and write its records."""
    if source_id not in ASSESSMENTS:
        raise SystemExit(
            f"no published assessment for {source_id!r}; published: {ASSESSMENTS}. "
            "A draft runs with --draft."
        )
    offered = crc.offered()
    folder = cache / source_id
    if source_id == "ibtracs":
        from .assessments import ibtracs

        source = next(s for s in inventory.load_sources("crc_sdk") if s.id == source_id)
        run = ibtracs.assess(
            source.assessed_options["subset"],
            offered["options"]["ibtracs"]["subset"],
            folder,
            folder / "crc-sdk",
            live=live,
            versions=offered["versions"],
            log=print,
        )
    elif source_id == "nex-gddp-cmip6":
        from .assessments import nex

        run = nex.assess(
            folder,
            live=live,
            versions=offered["versions"],
            fixed_clone=FIXED_CLONE if (FIXED_CLONE / "crc_sdk").is_dir() else None,
            log=print,
        )
    else:
        from .assessments import ghcnh

        run = ghcnh.assess(
            folder, folder / "crc-sdk", live=live, versions=offered["versions"], log=print
        )
    run = {"schema": SCHEMA, "framework": offered["framework"]} | run
    write_json_atomic(page_data / "records" / f"{source_id}.json", run)
    return run


def build_inventory(
    page_data: Path = PAGE_DATA, docs: Path = DOCS, records_from: Path = PAGE_DATA
) -> dict[str, object]:
    findings = inventory.load_findings("crc_sdk")
    records = {s.id: load_records(s.id, records_from) for s in inventory.load_sources("crc_sdk")}
    sources = [with_outcomes(s, records[s.id]) for s in inventory.load_sources("crc_sdk")]
    inventory.check_references(sources, findings)
    offered = crc.offered()
    gaps = inventory.unassessed(sources, offered)
    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "schema": SCHEMA,
        "generated": generated,
        "framework": offered["framework"],
        "versions": offered["versions"],
        "sources": [
            source.to_dict()
            | {"records": f"records/{source.id}.json" if records[source.id] else ""}
            for source in sources
        ],
        "findings": [finding.to_dict() for finding in findings],
        "gaps": gaps,
    }
    write_json_atomic(page_data / "inventory.json", payload)
    write_text_atomic(
        docs / "inventory.md",
        inventory_markdown(
            offered["framework"], offered["versions"], sources, findings, gaps, generated[:10]
        ),
    )
    for source in sources:
        if records[source.id]:
            write_text_atomic(
                docs / "sources" / f"{source.id}.md",
                source_markdown(
                    source, records[source.id], [f for f in findings if f.source == source.id]
                ),
            )
    return payload


def _count(source_id: str, run: dict[str, Any]) -> None:
    count: dict[str, int] = {}
    for check in run["checks"]:
        count[check["outcome"]] = count.get(check["outcome"], 0) + 1
    print(f"{source_id}: {len(run['checks'])} checks, {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", nargs="?", help=f"a source to assess: {', '.join(ASSESSMENTS)}")
    parser.add_argument("--live", action="store_true", help="download from the publisher")
    parser.add_argument(
        "--draft", action="store_true", help="a drafted assessment: records go to the draft folder"
    )
    args = parser.parse_args()
    if args.source:
        if args.draft:
            run = assess_draft(args.source, live=args.live)
            _count(args.source, run)
            print(f"draft records: {DRAFTS / 'records' / (args.source + '.json')}")
            return  # a draft leaves the inventory, the page data and the documents as they are
        else:
            run = assess_source(args.source, live=args.live)
        _count(args.source, run)
    payload = build_inventory()
    gaps = payload["gaps"]
    print(
        f"{len(payload['sources'])} sources, {len(payload['findings'])} findings; "
        f"{len(gaps['unclaimed_symbols'])} entry points without an entry, "
        f"{len(gaps['new_options'])} new option values, "
        f"{len(gaps['unassessed_options'])} option values not assessed"
    )


if __name__ == "__main__":
    main()
