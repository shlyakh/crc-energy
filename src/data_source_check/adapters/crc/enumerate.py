"""What the installed crc-sdk offers: entry points and the option tables it keeps.

crc-sdk has no registry of sources, so this reads three things: the ``HazardDataset``
constructors, the plans exported by ``crc_sdk.workflows`` and the recipe and dataset tables
in the providers. Some option lists are private or hard-coded upstream; those are reported
under ``could_not_enumerate`` instead of being guessed.
"""

from __future__ import annotations

import importlib
import importlib.metadata
from typing import Any

#: Public names that are not sources.
IGNORED = {
    "HazardDataset.local": "opens a canonical file already on disk",
}

#: source id -> option name -> (module, attribute) holding the values upstream.
OPTION_TABLES: dict[str, dict[str, tuple[str, str]]] = {
    "era5": {
        "recipe": ("crc_sdk.providers.era5", "ERA5_RECIPES"),
        "store": ("crc_sdk.providers.era5", "ERA5_STORES"),
    },
    "cmip6": {"recipe": ("crc_sdk.providers.cmip6", "CMIP6_RECIPES")},
    "nex-gddp-cmip6": {"recipe": ("crc_sdk.providers.cmip6", "CMIP6_RECIPES")},
    "jrc-flood": {"dataset": ("crc_sdk.providers.jrc", "JRC_DATASETS")},
    "jrc-edo": {"dataset": ("crc_sdk.providers.jrc_edo", "EDO_DATASETS")},
    "eccc-idf": {"duration": ("crc_sdk.providers.eccc_idf", "DURATIONS")},
    "ibtracs": {"subset": ("crc_sdk.workflows.ibtracs", "_SUBSETS")},
    "noaa-sea-level": {"scenario": ("crc_sdk.workflows.noaa_sea_level", "_SCENARIOS")},
}


def versions() -> dict[str, str]:
    return {name: importlib.metadata.version(name) for name in ("crc-sdk", "crc-framework")}


def _classmethods(cls: type) -> list[str]:
    return [
        f"{cls.__name__}.{name}"
        for name, value in vars(cls).items()
        if isinstance(value, classmethod | staticmethod) and not name.startswith("_")
    ]


def offered() -> dict[str, Any]:
    """Entry points and option values found in the installed crc-sdk."""
    workflows = importlib.import_module("crc_sdk.workflows")
    symbols = _classmethods(workflows.HazardDataset) + _classmethods(workflows.AgriculturalLayer)
    symbols += [name for name in workflows.__all__ if name.endswith("Plan")]
    options: dict[str, dict[str, list[str]]] = {}
    failed: list[str] = []
    for source_id, tables in OPTION_TABLES.items():
        for option, (module, attribute) in tables.items():
            try:
                values = getattr(importlib.import_module(module), attribute)
                options.setdefault(source_id, {})[option] = sorted(str(v) for v in values)
            except (ImportError, AttributeError, TypeError) as error:
                failed.append(f"{source_id}.{option}: {module}.{attribute} ({error})")
    return {
        "framework": "crc-sdk",
        "versions": versions(),
        "symbols": sorted(symbols),
        "ignored": IGNORED,
        "options": options,
        "could_not_enumerate": failed,
    }
