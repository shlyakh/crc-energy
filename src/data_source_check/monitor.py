"""Monitoring run: is every assessment still current?

    python -m data_source_check.monitor              # ask the publishers (HEAD), compare, report
    python -m data_source_check.monitor --rerun      # also re-run stale sources (staged)
    python -m data_source_check.monitor --accept ID  # publish a staged re-run after review

Writes ``docs/validation/monitoring.md`` and ``site/validation/data/monitor.json``. Exits 1
when something needs attention, so that a scheduled run is noticed. It never replaces the
published records: a re-run is staged, and a person accepts it.
"""

from __future__ import annotations

import argparse
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import build
from .adapters.crc import enumerate as crc
from .core import compare, inventory, monitoring
from .core.io import write_json_atomic, write_text_atomic

STAGING = build.CACHE / "staging"
USER_AGENT = "data-source-check"


def head(url: str) -> dict[str, Any]:
    request = Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=60) as response:
            return {"status": int(response.status), "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified")}  # fmt: skip
    except HTTPError as error:
        return {"status": int(error.code)}
    except (URLError, TimeoutError, ConnectionError) as error:
        return {"status": None, "error": str(error)}


def run(*, rerun: bool = False, page_data: Path = build.PAGE_DATA, docs: Path = build.DOCS,
        ask: Any = head) -> dict[str, Any]:  # fmt: skip
    sources = inventory.load_sources("crc_sdk")
    offered = crc.offered()
    gaps = inventory.unassessed(sources, offered)
    records = {s.id: build.load_records(s.id, page_data) for s in sources}
    records = {name: value for name, value in records.items() if value}
    urls = sorted({item["url"] for value in records.values()
                   for item in monitoring.recorded_inputs(value)})  # fmt: skip
    print(f"asking the publishers about {len(urls)} files")
    with ThreadPoolExecutor(max_workers=16) as pool:
        heads = dict(zip(urls, pool.map(ask, urls), strict=True))
    states = [monitoring.source_state(value, heads, offered["versions"])
              for value in records.values()]  # fmt: skip
    report: dict[str, Any] = {
        "run_at": compare.now(),
        "installed": offered["versions"],
        "sources": states,
        "gaps": {key: gaps[key] for key in ("unclaimed_symbols", "new_options")},
        "needs_attention": monitoring.needs_attention(states, gaps),
        "reruns": [],
    }
    if rerun:
        for state in states:
            if not state["stale"]:
                continue
            name = state["source"]
            print(f"re-running {name} into the staging folder")
            staged = STAGING / "page-data"
            fresh = build.assess_source(name, live=True, page_data=staged,
                                        cache=STAGING / "cache")  # fmt: skip
            diff = monitoring.diff_records(records[name], fresh)
            report["reruns"].append(diff | {"staged": str(staged / "records" / f"{name}.json")})
    write_json_atomic(page_data / "monitor.json", report)
    write_text_atomic(docs / "monitoring.md", monitoring.markdown(report))
    return report


def accept(source_id: str) -> None:
    """Publish a staged re-run: a person runs this after reading the monitoring report."""
    staged = STAGING / "page-data" / "records" / f"{source_id}.json"
    if not staged.exists():
        raise SystemExit(f"nothing is staged for {source_id!r}")
    shutil.copyfile(staged, build.PAGE_DATA / "records" / f"{source_id}.json")
    build.build_inventory()
    print(f"{source_id}: staged records published; the assessment is a draft until signed again")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rerun", action="store_true", help="re-run stale sources (staged)")
    parser.add_argument("--accept", metavar="ID", help="publish a staged re-run")
    args = parser.parse_args()
    if args.accept:
        accept(args.accept)
        return
    report = run(rerun=args.rerun)
    for state in report["sources"]:
        print(f"{state['source']}: " + ("stale: " + "; ".join(state["reasons"])
                                        if state["stale"] else "current"))  # fmt: skip
    raise SystemExit(1 if report["needs_attention"] else 0)


if __name__ == "__main__":
    main()
