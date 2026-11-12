"""Drafted assessments: a brief for the drafter, a gate for the draft, and acceptance by a person.

    python -m data_source_check.draft brief <id>     # what is known about an unassessed source
    python -m data_source_check.draft check <id>     # is the draft complete? (exits 1 if not)
    python -m data_source_check.draft accept <id>    # a person publishes the draft's records

A draft may be written by an agent (see the skill ``draft-source-assessment``). It consists of the
source file's statement, a reference reader, an adapter, an assessment module and offline tests.
Its records are written to the draft folder by ``python -m data_source_check.build <id> --draft``
and reach the page only through ``accept``. The gate here is deterministic: it decides whether a
draft is complete, never whether the framework is right.
"""

from __future__ import annotations

import argparse
import ast
import inspect
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from . import build
from .adapters.crc import enumerate as crc
from .core import compare, inventory
from .core.records import Source

PACKAGE = Path(__file__).resolve().parent
TESTS = build.REPO / "tests" / "validation"
FAULT_WORDS = ("fault", "wrong", "broken")


def module_name(source_id: str) -> str:
    return source_id.replace("-", "_")


def paths(source_id: str) -> dict[str, Path]:
    """The files a draft consists of."""
    name = module_name(source_id)
    return {
        "source file": PACKAGE / "sources" / "crc_sdk" / f"{source_id}.toml",
        "reference reader": PACKAGE / "reference" / f"{name}.py",
        "adapter": PACKAGE / "adapters" / "crc" / f"{name}.py",
        "assessment": PACKAGE / "assessments" / f"{name}.py",
        "tests": TESTS / f"test_data_source_check_{name}.py",
        "draft records": build.DRAFTS / "records" / f"{source_id}.json",
        "drafting note": build.DOCS / "drafts" / f"{source_id}.md",
    }


def find_source(source_id: str) -> Source:
    for source in inventory.load_sources("crc_sdk"):
        if source.id == source_id:
            return source
    raise SystemExit(f"{source_id!r} is not in the inventory")


def _where(symbol: str) -> str:
    """File of a crc-sdk entry point such as ``HazardDataset.era5`` or ``IBTrACSPlan``."""
    try:
        import crc_sdk
        import crc_sdk.workflows as workflows

        target: Any = None
        head, _, tail = symbol.partition(".")
        for home in (workflows, crc_sdk):
            if hasattr(home, head):
                target = getattr(home, head)
                break
        if target is not None and tail:
            target = getattr(target, tail)
        target = getattr(target, "__func__", target)
        file = inspect.getsourcefile(target)
        line = inspect.getsourcelines(target)[1]
        root = Path(crc_sdk.__file__).resolve().parent.parent
        return f"{Path(file).resolve().relative_to(root)}:{line}" if file else "not found"
    except Exception as error:  # the brief is a help, not a check
        return f"not found ({type(error).__name__})"


def brief(source_id: str) -> str:
    """Everything the inventory already knows about a source, for whoever drafts its assessment."""
    source = find_source(source_id)
    offered = crc.offered()
    findings = [f for f in inventory.load_findings("crc_sdk") if f.source == source_id]
    lines = [
        f"# Brief: {source.title} ({source.id})",
        "",
        f"- Framework: crc-sdk {offered['versions'].get('crc-sdk', '?')}",
        f"- Kind: {source.kind}; tier {source.tier}",
        f"- Publisher: {source.publisher}",
        f"- Original: {source.original}",
        f"- Purpose: {source.purpose}",
        f"- Status: {source.status}",
        "",
        "## Entry points in crc-sdk",
        "",
    ]
    lines += [f"- `{symbol}`: `{_where(symbol)}`" for symbol in source.entry_points]
    lines += ["", "## Options the framework offers", ""]
    options = offered["options"].get(source_id, {}) or source.options
    lines += [f"- {name}: {', '.join(map(str, values))}" for name, values in options.items()] or [
        "- none enumerated"
    ]
    lines += ["", "## Findings already recorded", ""]
    for f in findings:
        lines += [f"- {f.id} ({f.kind}, {f.basis}): {f.title}"]
        lines += [f"  - evidence: {item}" for item in f.evidence]
    if not findings:
        lines.append("- none")
    lines += ["", "## Files of the draft", ""]
    lines += [
        f"- {role}: `{path.relative_to(build.REPO)}`{'' if path.exists() else ' (to write)'}"
        for role, path in paths(source_id).items()
    ]
    return "\n".join(lines) + "\n"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    names += [a.name for node in ast.walk(tree) if isinstance(node, ast.Import) for a in node.names]
    return names


def _test_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


def check(
    source_id: str, *, files: dict[str, Path] | None = None, source: Source | None = None
) -> list[str]:
    """What is missing from a draft. An empty list means the draft is complete."""
    files = files or paths(source_id)
    problems = [f"{role} is missing: {path}" for role, path in files.items() if not path.exists()]
    source = source or find_source(source_id)
    if source_id in build.ASSESSMENTS:
        return [f"{source_id} is a published assessment, not a draft"]
    if not source.drafted_by:
        problems.append("the source file does not say who drafted it (drafted_by)")
    if source.reviewed_by:
        problems.append("a draft cannot be marked as reviewed (reviewed_by is set)")
    if source.status["verification"] == "assessed":
        problems.append('status.verification is "assessed"; a draft stays "in progress"')
    if not source.statement:
        problems.append("the source file has no statement")
    for step in source.statement:
        if not step.code_ref:
            problems.append(f"step {step.id!r} has no code reference")
    reference = files["reference reader"]
    if reference.exists():
        bad = [
            n
            for n in _imports(reference)
            if n.split(".")[0] in ("crc_sdk", "crc_framework", "pyarrow", "crc_lab")
            or "adapters" in n
        ]
        if bad:
            problems.append(f"the reference reader imports {sorted(set(bad))}")
    tests = files["tests"]
    if tests.exists():
        names = [n for n in _test_names(tests) if n.startswith("test_")]
        if not any(word in name for name in names for word in FAULT_WORDS):
            problems.append(
                "no deliberate-fault test (a test whose name contains "
                f"{' or '.join(FAULT_WORDS)}): each reference rule, broken, must end as differs"
            )
    records = files["draft records"]
    if records.exists() and source.statement:
        run = json.loads(records.read_text(encoding="utf-8"))
        checks = run.get("checks", [])
        if not checks:
            problems.append("the draft records hold no check")
        for item in checks:
            if not item.get("summary"):
                problems.append(f"check {item.get('check')!r} has no summary")
            unknown = set(item.get("steps", ())) - {step.id for step in source.statement}
            if unknown:
                problems.append(
                    f"check {item.get('check')!r} names unknown steps {sorted(unknown)}"
                )
        outcomes = compare.step_outcomes([step.id for step in source.statement], checks)
        for step in source.statement:
            if outcomes[step.id] == "not checked" and not step.note:
                problems.append(f"step {step.id!r} is not checked and has no note saying why")
        if not any(outcome != "not checked" for outcome in outcomes.values()):
            problems.append("no statement step is covered by a check")
    return problems


def accept(source_id: str) -> Path:
    """Publish a complete draft's records. The person then signs the source file."""
    problems = check(source_id)
    if problems:
        raise SystemExit("the draft is not complete:\n- " + "\n- ".join(problems))
    target = build.PAGE_DATA / "records" / f"{source_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(paths(source_id)["draft records"], target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("brief", "check", "accept"))
    parser.add_argument("source")
    args = parser.parse_args()
    if args.action == "brief":
        print(brief(args.source), end="")
    elif args.action == "check":
        problems = check(args.source)
        for problem in problems:
            print(f"- {problem}")
        print(f"{args.source}: {'complete' if not problems else f'{len(problems)} to resolve'}")
        sys.exit(1 if problems else 0)
    else:
        target = accept(args.source)
        print(
            f"published {target.relative_to(build.REPO)}. Now, by hand: add {args.source!r} to "
            'ASSESSMENTS in build.py, set status.verification = "assessed" in the source file, '
            "run `just validation`, read the page, and fill reviewed_by and reviewed_on when you "
            "agree."
        )


if __name__ == "__main__":
    main()
