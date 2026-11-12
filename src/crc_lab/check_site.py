"""``just site-hail``: the hail page is complete when its files and its registry layers exist."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from lab_common.site import SHARED, missing_files, missing_layer_files, report

FILES = (
    "hail/index.html",
    "hail/hail.js",
    "hail/risk.js",
    "hail/charts.js",
    "hail/methods.js",
    "hail/demo.js",
    "data/assets/plants.json",
    "data/assets/plants_detail.json",
    "data/assets/curves.json",
)


def main(site: Path = Path("site")) -> int:
    if not (site / "data" / "manifest.json").exists():
        print("site/data/manifest.json missing: run `just data` first")
        return 1
    missing = missing_files(site, SHARED + FILES)
    layers, count = missing_layer_files(site, "crc-lab")
    video = json.loads((site / "layers.json").read_text()).get("demo", {}).get("video")
    if video and not (site / video).exists():
        missing.append(video)
    return report("Texas hail risk", site, missing + layers, count)


if __name__ == "__main__":
    sys.exit(main())
