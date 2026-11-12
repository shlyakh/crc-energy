"""E1: the CRC Open catalogue as one JSON file, taken from the release's own metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from crc_sdk.providers.crc_open import CRCCatalog

from lab_common.texas import write_json_atomic


def catalog_payload(catalog: CRCCatalog) -> dict[str, Any]:
    """Every hazard with unit, meaning, tail, resolution, semantics, horizons, pathways, notes."""
    hazards = {}
    for name in sorted(catalog.hazards):
        hazard = catalog.hazards[name]
        hazards[name] = {
            "unit": hazard.unit,
            "value_semantics": hazard.value_semantics,
            "tail": hazard.tail,
            "h3_resolution": hazard.h3_resolution,
            "probability_semantics": hazard.probability_semantics,
            "pooling": hazard.pooling,
            "pathways": list(hazard.pathways),
            "horizons": list(hazard.horizons),
            "partitions": len(hazard.partitions),
            "rows": sum(partition.rows for partition in hazard.partitions),
            "bytes": sum(partition.size_bytes for partition in hazard.partitions),
            "notes": hazard.notes,
        }
    return {
        "release": catalog.release,
        "schema_version": catalog.schema_version,
        "licence": catalog.licence,
        "attribution": catalog.attribution,
        "retrieved_at": catalog.retrieved_at,
        "pathways": list(catalog.pathways),
        "no_data_reasons": dict(catalog.no_data_reasons),
        "excluded_hazards": dict(catalog.excluded_hazards),
        "hazards": hazards,
    }


def write_catalog(catalog: CRCCatalog, path: Path) -> dict[str, Any]:
    payload = catalog_payload(catalog)
    write_json_atomic(path, payload)
    return payload
