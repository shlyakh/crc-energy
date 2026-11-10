# ruff: noqa: E501
"""A4: plant replacement value = AC capacity x overnight capital cost per kW.

The cost comes from NREL's Annual Technology Baseline (ATB), utility-scale PV, overnight
capital cost (OCC). The ATB file is 320 MB, so the few rows used are extracted once into
``reference/atb_utility_pv_occ.json`` with the source file's SHA-256 (``extract``); the
build reads only that small file. Replacement value is today's cost to rebuild, so one
recent cost year applies to every plant, whatever its build year.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

REFERENCE = Path(__file__).parent / "reference" / "atb_utility_pv_occ.json"
ATB_URL = "https://oedi-data-lake.s3.amazonaws.com/ATB/electricity/csv/2025/v1.0.0/ATBe.csv"


def extract(atb_csv: Path, out: Path = REFERENCE) -> dict[str, Any]:
    """Pull utility-PV OCC by year (Moderate scenario) out of the full ATB table."""
    import duckdb

    digest = hashlib.sha256()
    with atb_csv.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    con = duckdb.connect()
    rows = con.execute(
        f"""SELECT core_metric_variable AS year, scenario, round(avg(value), 2) AS occ, any_value(units) AS units,
                   count(DISTINCT round(value, 2)) AS distinct_values, any_value(atb_year) AS atb_year
            FROM read_csv('{atb_csv}', header=true)
            WHERE technology = 'UtilityPV' AND core_metric_parameter = 'OCC'
              AND core_metric_case = 'R&D' AND crpyears = 30 AND core_metric_variable <= 2030
            GROUP BY 1, 2 ORDER BY 1, 2"""
    ).fetchall()
    payload = {
        "source": "NREL Annual Technology Baseline (ATB) 2025, electricity, v1.0.0",
        "url": ATB_URL,
        "sha256": digest.hexdigest(),
        "technology": "UtilityPV",
        "parameter": "OCC (overnight capital cost)",
        "case": "R&D financial case, 30-year cost recovery; identical across resource classes",
        "capacity_basis": "per kW AC, as ATB reports utility PV",
        "dollar_year": "as stated in the ATB 2025 documentation; not given in the data file",
        "rows": [
            {
                "year": y,
                "scenario": s,
                "occ_usd_per_kw": v,
                "units": u,
                "distinct_values_across_classes": d,
            }
            for y, s, v, u, d, _ in rows
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1) + "\n")
    return payload


def cost_per_kw(year: int = 2024, scenario: str = "Moderate") -> tuple[float, dict[str, Any]]:
    """OCC in $/kW for one ATB year and scenario, with the provenance to store beside it."""
    reference = json.loads(REFERENCE.read_text())
    for row in reference["rows"]:
        if row["year"] == year and row["scenario"] == scenario:
            provenance = {
                k: reference[k]
                for k in ("source", "url", "sha256", "parameter", "capacity_basis", "dollar_year")
            }
            provenance |= {
                "cost_year": year,
                "scenario": scenario,
                "occ_usd_per_kw": row["occ_usd_per_kw"],
            }
            return float(row["occ_usd_per_kw"]), provenance
    raise KeyError(f"no ATB OCC row for {year} {scenario}")


def add_value(assets: pa.Table, occ_usd_per_kw: float) -> pa.Table:
    """``value_usd`` = AC capacity (MW) x 1000 x $/kW; null where capacity is missing."""
    value = pc.multiply(pc.multiply(assets["capacity_ac_mw"], 1000.0), occ_usd_per_kw)
    return assets.append_column("value_usd", value)
