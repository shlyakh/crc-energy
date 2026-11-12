"""``just site-validation``: the assessments page is complete when its files and records exist.

Stands alone (no import from the other projects in this repository), like the rest of the package.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

FILES = (
    "index.html",
    "validation.js",
    "validation.css",
    "data/inventory.json",
    "data/monitor.json",
)


def main(page: Path = Path("site/validation")) -> int:
    missing = [name for name in FILES if not (page / name).exists()]
    assessed = 0
    if not missing:
        inventory = json.loads((page / "data" / "inventory.json").read_text(encoding="utf-8"))
        for source in inventory["sources"]:
            record = source.get("records")
            if not record:
                continue
            assessed += 1
            record = f"data/{record}"
            if not (page / record).exists():
                missing.append(record)
    for name in missing:
        print(f"missing: site/validation/{name}")
    if not missing:
        print(f"Source validation: site complete, {assessed} assessed sources with records")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
