"""Completeness checks of the static site, shared by the projects' own ``check_site`` modules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def missing_files(site: Path, names: tuple[str, ...]) -> list[str]:
    return [name for name in names if not (site / name).exists()]


def missing_layer_files(site: Path, origin: str) -> tuple[list[str], int]:
    """Missing files of the registry layers whose source has this origin, and how many layers.

    A layer without a ``source_id`` (the Texas outline) belongs to every project.
    """
    registry: dict[str, Any] = json.loads((site / "layers.json").read_text())
    manifest = json.loads((site / "data" / "manifest.json").read_text())
    origins = {s["id"]: s["origin"] for s in registry.get("sources", [])}
    missing: list[str] = []
    count = 0
    for layer in registry["layers"]:
        source = layer.get("source_id")
        if source and source not in origins:
            missing.append(f"source entry for layer {layer['id']} ({source})")
            continue
        if source and origins[source] != origin:
            continue
        count += 1
        if layer["kind"] == "h3-cells":
            for horizon in layer.get("horizons", manifest["horizons"]):
                path = layer["file"].replace("{horizon}", str(horizon))
                if not (site / path).exists():
                    missing.append(path)
        elif "file" in layer and not (site / layer["file"]).exists():
            missing.append(layer["file"])
        if layer["kind"] == "points-binary" and not (site / layer["index"]).exists():
            missing.append(layer["index"])
    return missing, count


def report(project: str, site: Path, missing: list[str], layers: int) -> int:
    for path in missing:
        print(f"missing: {path}")
    if not missing:
        print(f"{project}: site complete, {layers} layers")
    return 1 if missing else 0


SHARED = (
    "index.html",
    "landing.css",
    "layers.json",
    "sources.json",
    "shared/style.css",
    "shared/sources.css",
    "shared/util.js",
    "shared/sources.js",
    "shared/views/core.js",
    "data/manifest.json",
    "data/texas.geojson",
)
