"""Markdown generated from records. Nothing here is typed by hand into a report."""

from __future__ import annotations

from typing import Any

from .records import ASSESSMENT_TIERS, Finding, Source


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _table(header: list[str], rows: list[list[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(_cell(value) for value in row) + " |" for row in rows]
    return lines


def inventory_markdown(
    framework: str,
    versions: dict[str, str],
    sources: list[Source],
    findings: list[Finding],
    gaps: dict[str, Any],
    generated: str,
) -> str:
    pins = ", ".join(f"{name} {version}" for name, version in sorted(versions.items()))
    count: dict[str, int] = {}
    for finding in findings:
        count[finding.source] = count.get(finding.source, 0) + 1
    lines = [
        f"# Inventory: {framework} sources",
        "",
        f"Generated {generated} by `python -m data_source_check.build` against {pins}.",
        "Do not edit: change the files under `src/data_source_check/sources/` and rebuild.",
        "",
        "## Sources",
        "",
    ]
    lines += _table(
        [
            "Source",
            "Kind",
            "Tier",
            "Exploration",
            "Verification",
            "Validation",
            "Findings",
            "Signed",
        ],
        [
            [
                f"{source.title} (`{source.id}`)",
                source.kind,
                source.tier if source.tier is not None else "n/a",
                *(source.status[tier] for tier in ASSESSMENT_TIERS),
                count.get(source.id, 0),
                f"{source.reviewed_by}, {source.reviewed_on}" if source.reviewed_by else "draft",
            ]
            for source in sources
        ],
    )
    lines += ["", "## What crc-sdk offers that is not assessed", ""]
    if gaps["unclaimed_symbols"]:
        lines += ["Entry points found in the installed version with no inventory entry:", ""]
        lines += [f"- `{name}`" for name in gaps["unclaimed_symbols"]] + [""]
    else:
        lines += ["Every entry point found in the installed version has an inventory entry.", ""]
    if gaps["new_options"]:
        lines += ["Option values found upstream that the inventory does not list:", ""]
        lines += _table(
            ["Source", "Option", "Value"],
            [[g["source"], g["option"], g["value"]] for g in gaps["new_options"]],
        ) + [""]
    lines += [
        f"Sources with no assessment at any tier: {len(gaps['unassessed_sources'])} of "
        f"{sum(1 for source in sources if source.kind != 'user data')}.",
        f"Option values (recipes, datasets, versions) not yet assessed: "
        f"{len(gaps['unassessed_options'])}.",
        "",
    ]
    if gaps["could_not_enumerate"]:
        lines += ["Option tables that could not be read from the installed version:", ""]
        lines += [f"- {item}" for item in gaps["could_not_enumerate"]] + [""]
    lines += ["## Findings", ""]
    lines += _table(
        ["Id", "Source", "Kind", "Finding", "Basis", "Status"],
        [[f.id, f.source, f.kind, f.title, f.basis, f.status] for f in findings],
    )
    for finding in findings:
        lines += ["", f"### {finding.id}: {finding.title}", ""]
        if finding.documented:
            lines += [f"- **Documented:** {finding.documented}"]
        lines += [f"- **Observed:** {finding.observed}"]
        if finding.consequence:
            lines += [f"- **Consequence:** {finding.consequence}"]
        lines += [
            f"- **Evidence:** {'; '.join(finding.evidence)}",
            f"- **Basis:** {finding.basis} · **Status:** {finding.status}"
            + (f" ({finding.upstream_ref})" if finding.upstream_ref else "")
            + f" · found {finding.found_on} at {framework} {finding.framework_version}",
        ]
    return "\n".join(lines) + "\n"


def source_markdown(source: Source, records: dict[str, Any], findings: list[Finding]) -> str:
    """The assessment of one source, from its inventory entry and the records of one run."""
    pins = ", ".join(f"{name} {version}" for name, version in sorted(records["versions"].items()))
    signed = (
        f"Reviewed by {source.reviewed_by}, {source.reviewed_on}."
        if source.reviewed_by
        else "**Draft: not yet reviewed.**"
    )
    lines = [
        f"# {source.title}: assessment",
        "",
        f"Generated from the records of the run of {records['run_at']} against {pins}. {signed}",
        "Do not edit: change the source file or re-run the assessment and rebuild.",
        "",
        f"- **Purpose (the framework's documentation):** {source.purpose}",
        f"- **Publisher:** {source.publisher} · {source.original}",
        f"- **Entry points:** {', '.join(f'`{name}`' for name in source.entry_points)}",
        "- **Status:** " + ", ".join(f"{tier} {source.status[tier]}" for tier in ASSESSMENT_TIERS),
    ]
    for name, values in source.options.items():
        done = set(source.assessed_options.get(name, ()))
        lines.append(
            f"- **Options, {name}:** assessed {', '.join(v for v in values if v in done) or 'none'}"
            f"; not assessed {', '.join(v for v in values if v not in done) or 'none'}"
        )
    for name, reason in records.get("subsets_skipped", {}).items():
        lines.append(f"- **Skipped:** `{name}`: {reason}")

    lines += ["", "## Exploration", ""]
    for table in records.get("tables", ()):
        lines += [f"### {table['title']}", ""]
        if table.get("note"):
            lines += [table["note"], ""]
        lines += _table(
            table["head"],
            [
                [f"{v:,}" if isinstance(v, int) and not isinstance(v, bool) else v for v in row]
                for row in table["rows"]
            ],
        )
        lines.append("")
    if source.notes:
        lines += [source.notes, ""]

    lines += ["## What the framework does (transformation statement)", ""]
    lines += _table(
        ["Step", "What crc-sdk does", "Code", "Outcome"],
        [
            [
                step.id,
                step.text,
                step.code_ref,
                f"**{step.outcome}**" + (f". {step.note}" if step.note else ""),
            ]
            for step in source.statement
        ],
    )

    lines += ["", "## Checks", ""]
    by_name: dict[str, list[dict[str, Any]]] = {}
    for check in records["checks"]:
        by_name.setdefault(check["check"].split("[")[0], []).append(check)
    for name, group in by_name.items():
        first = group[0]
        lines += [
            f"### {name}",
            "",
            f"{first['method']} Steps: {', '.join(first['steps'])}. "
            f"Tolerance: {'; '.join(f'{k}: {v}' for k, v in first['tolerance'].items())}.",
            "",
        ]
        lines += _table(
            ["Check", "Outcome", "Result"],
            [[c["check"], c["outcome"], c.get("summary") or c.get("note", "")] for c in group],
        )
        lines.append("")

    lines += ["## Inputs", ""]
    seen: dict[str, dict[str, Any]] = {}
    for check in records["checks"]:
        for item in check["inputs"]:
            seen.setdefault(f"{item['role']}|{item['url']}", item)
    lines += _table(
        ["Role", "File", "SHA-256", "Retrieved"],
        [
            [
                item["role"],
                item["url"].rsplit("/", 1)[-1],
                item.get("sha256", ""),
                item.get("retrieved_at", ""),
            ]
            for item in seen.values()
        ],
    )
    lines += ["", "## Findings", ""]
    if findings:
        lines += _table(
            ["Id", "Kind", "Finding", "Basis", "Status"],
            [[f.id, f.kind, f.title, f.basis, f.status] for f in findings],
        )
        lines += ["", "Details are in [the inventory](../inventory.md#findings)."]
    else:
        lines.append("None.")
    lines += [
        "",
        "## What this does not cover",
        "",
        f"- A `confirmed` outcome holds for these files, these options and {pins}.",
        "- Verification says nothing about whether the publisher's values are right.",
        "- Validation (fitness for a stated use) is not assessed.",
    ]
    return "\n".join(lines) + "\n"
