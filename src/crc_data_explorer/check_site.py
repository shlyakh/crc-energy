"""``just site-explorer``: the Texas data explorer is complete when its files and layers exist."""

from __future__ import annotations

import sys
from pathlib import Path

from lab_common.site import SHARED, missing_files, missing_layer_files, report

FILES = (
    "validation/explore/index.html",
    "validation/explore/explore.js",
    "validation/explore/about.js",
    "validation/explore/tour.js",
    "data/catalog.json",
)


def main(site: Path = Path("site")) -> int:
    if not (site / "data" / "manifest.json").exists():
        print("site/data/manifest.json missing: run `just data` first")
        return 1
    missing = missing_files(site, SHARED + FILES)
    layers, count = missing_layer_files(site, "crc-sdk")
    return report("Texas CRC data explorer", site, missing + layers, count)


if __name__ == "__main__":
    sys.exit(main())
