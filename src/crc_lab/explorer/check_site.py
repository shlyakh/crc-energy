"""``just site``: the static site is complete when every registry layer's files exist."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(site: Path = Path("site")) -> int:
    registry = json.loads((site / "layers.json").read_text())
    manifest_path = site / "data" / "manifest.json"
    if not manifest_path.exists():
        print("site/data/manifest.json missing: run `just data` first")
        return 1
    manifest = json.loads(manifest_path.read_text())
    missing: list[str] = []
    for name in (
        "index.html",
        "app.js",
        "style.css",
        "sources.json",
        "data/catalog.json",
        "data/texas.geojson",
    ):
        if not (site / name).exists():
            missing.append(name)
    for layer in registry["layers"]:
        if layer["kind"] == "h3-cells":
            for horizon in layer.get("horizons", manifest["horizons"]):
                path = layer["file"].replace("{horizon}", str(horizon))
                if not (site / path).exists():
                    missing.append(path)
        elif "file" in layer and not (site / layer["file"]).exists():
            missing.append(layer["file"])
    for path in missing:
        print(f"missing: {path}")
    if not missing:
        total = sum(p.stat().st_size for p in (site / "data").rglob("*") if p.is_file())
        print(f"site complete: {len(registry['layers'])} layers, data {total / 1e6:.1f} MB")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
