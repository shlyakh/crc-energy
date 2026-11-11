"""Regional bias-corrected hail rate: the smoother alternative to the per-cell correction.

The reporting-bias model (``reporting_bias.py``, report 5) gives every Texas H3 resolution-5 cell a
reporting rate and groups cells into regions (their H3 resolution-3 parents, about 12,000 km2)
inside which the true hail rate is taken as uniform. Given the reporting rates, the Poisson
maximum-likelihood estimate of a region's true report rate is

    rate = reports in the region / (years x sum over its cells of reporting rate x cell area)

so every asset in a region gets the same rate, and the sizes of all the region's reports give its
size distribution. No circle around the asset is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from crc_lab.assets.exposure import Reports


def regional_rate(
    reports: float, reporting_rate: np.ndarray, area_km2: np.ndarray, years: float
) -> float:
    """Corrected reports per km2 per year in a region; 0 if nothing can be reported."""
    effective = float(np.sum(np.asarray(reporting_rate) * np.asarray(area_km2))) * years
    return reports / effective if effective > 0 else 0.0


@dataclass(frozen=True)
class Region:
    name: str
    cells: int
    area_km2: float
    reports: int
    mean_reporting_rate: float
    rate_per_km2_year: float  # corrected
    sizes_mm: np.ndarray


@dataclass(frozen=True)
class RegionalHail:
    regions: dict[str, Region]
    cell_region: dict[int, str]
    resolution: int

    def at(self, lon: float, lat: float) -> Region | None:
        """The region of the cell holding the point, or None outside the modelled cells."""
        import h3

        cell = h3.str_to_int(h3.latlng_to_cell(lat, lon, self.resolution))
        name = self.cell_region.get(cell)
        return self.regions[name] if name else None


def build(bias_parquet: Path, reports: Reports) -> RegionalHail:
    """Group the located reports by the model's regions; estimate each region's corrected rate."""
    import h3

    table = pq.read_table(bias_parquet, columns=["cell", "region", "reporting_rate"]).to_pylist()
    resolution = h3.get_resolution(h3.int_to_str(table[0]["cell"]))
    cell_region = {r["cell"]: r["region"] for r in table}
    sizes: dict[str, list[float]] = {}
    for lon, lat, size in zip(reports.lon, reports.lat, reports.size_mm, strict=True):
        name = cell_region.get(h3.str_to_int(h3.latlng_to_cell(float(lat), float(lon), resolution)))
        if name:
            sizes.setdefault(name, []).append(float(size))
    regions: dict[str, Region] = {}
    for name in sorted(set(cell_region.values())):
        rows = [r for r in table if r["region"] == name]
        rho = np.array([r["reporting_rate"] for r in rows])
        area = np.array([h3.cell_area(h3.int_to_str(r["cell"]), unit="km^2") for r in rows])
        got = np.array(sizes.get(name, []))
        regions[name] = Region(
            name=name,
            cells=len(rows),
            area_km2=float(area.sum()),
            reports=len(got),
            mean_reporting_rate=float(np.average(rho, weights=area)),
            rate_per_km2_year=regional_rate(len(got), rho, area, reports.years),
            sizes_mm=got,
        )
    return RegionalHail(regions, cell_region, resolution)
