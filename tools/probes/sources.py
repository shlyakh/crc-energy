"""Sources track, Part 1: probe each crc-sdk source against Texas.

``uv run python tools/probes/sources.py <name>`` prints one JSON record: what came back, time,
bytes where known, and ``could_not_verify`` with the error text when a source is unreachable.
Nothing here is invented: every number is measured by the run.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
import warnings
from pathlib import Path

TEXAS = (-106.645646, 25.837377, -93.508292, 36.500704)
AUSTIN_BOX = (-98.0, 30.0, -97.5, 30.5)
SMALL_BOX = (-97.6, 30.2, -97.5, 30.3)
CACHE = Path(__file__).resolve().parents[2] / "data" / "cache" / "sources"


def dir_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0


def _rows(table) -> int:
    return table.num_rows if hasattr(table, "num_rows") else len(table)


def probe_ghcnh(recipe: str = "temperature_max") -> dict:
    import pyarrow.parquet as pq
    from crc_sdk.workflows import BlockExtremaPolicy, HazardDataset

    cache = CACHE / "ghcnh"
    plan = HazardDataset.ghcnh(recipe).for_area(TEXAS).cache(cache, mode="reuse")
    t = time.time()
    stations = plan.stations()
    out = {
        "stations_in_texas": _rows(stations),
        "columns": stations.column_names,
        "catalogue_s": round(time.time() - t, 1),
        "sample": stations.slice(0, 3).to_pylist(),
    }
    rows = stations.to_pylist()
    # The catalogue carries no years for these stations; USW... are NWS/FAA airport stations
    usw = [r for r in rows if r["station"].startswith("USW")]
    out["stations_usw"] = len(usw)
    out["stations_by_prefix"] = {
        p: sum(1 for r in rows if r["station"].startswith(p)) for p in ("USW", "USC", "US1", "MX")
    }
    ids = [r["station"] for r in usw[:3]]
    out["probe_ids"] = [(r["station"], r["name"]) for r in usw[:3]]
    t = time.time()
    small = (
        HazardDataset.ghcnh(recipe)
        .for_stations(ids)
        .years(2000, 2024)
        .cache(cache, mode="reuse")
        .canonicalize(policy=BlockExtremaPolicy.curated(minimum_years=15))
    )
    target = cache / f"{recipe}-3stations.parquet"
    ds = small.materialize(target)
    out["three_stations_s"] = round(time.time() - t, 1)
    out["cache_bytes"] = dir_bytes(cache)
    tbl = pq.read_table(target)
    out["curve_rows"] = tbl.num_rows
    out["curve_sample"] = {
        k: (str(v)[:60] if isinstance(v, bytes) else v)
        for k, v in tbl.slice(0, 1).to_pylist()[0].items()
    }
    out["provenance"] = str(ds.provenance())[:400]
    return out


def probe_isd() -> dict:
    from crc_sdk.workflows import HazardDataset

    cache = CACHE / "isd"
    t = time.time()
    stations = (
        HazardDataset.isd("temperature_max").for_area(TEXAS).cache(cache, mode="reuse").stations()
    )
    return {
        "stations_in_texas": _rows(stations),
        "columns": stations.column_names,
        "catalogue_s": round(time.time() - t, 1),
        "sample": stations.slice(0, 2).to_pylist(),
        "cache_bytes": dir_bytes(cache),
    }


def probe_usgs() -> dict:
    from crc_sdk.workflows import USGSStreamflowPlan

    cache = CACHE / "usgs"
    plan = (
        USGSStreamflowPlan.for_station("USGS-08158000")
        .between("2020-01-01", "2024-12-31")
        .cache(cache, mode="reuse")
    )
    t = time.time()
    src = plan.prefetch()
    rows, first = 0, None
    for batch in plan.batches():
        rows += batch.num_rows
        if first is None and batch.num_rows:
            first = batch.slice(0, 1).to_pylist()[0]
    return {
        "station": "USGS-08158000 Colorado River at Austin",
        "rows": rows,
        "seconds": round(time.time() - t, 1),
        "first_row": {k: str(v) for k, v in (first or {}).items()},
        "source": {k: str(v)[:120] for k, v in dict(src).items()},
        "cache_bytes": dir_bytes(cache),
    }


def probe_chirps() -> dict:
    from crc_sdk.workflows import CHIRPSMonthlyPlan

    cache = CACHE / "chirps"
    plan = CHIRPSMonthlyPlan.monthly(2024, 5).for_area(TEXAS).cache(cache, mode="reuse")
    t = time.time()
    src = plan.prefetch()
    rows, cols = 0, None
    for batch in plan.batches():
        rows += batch.num_rows
        cols = cols or batch.schema.names
    return {
        "pixels_in_texas_box": rows,
        "columns": cols,
        "seconds": round(time.time() - t, 1),
        "source": {k: str(v)[:120] for k, v in dict(src).items()},
        "cache_bytes": dir_bytes(cache),
    }


def probe_ibtracs() -> dict:
    from crc_sdk.workflows import IBTrACSPlan

    cache = CACHE / "ibtracs"
    plan = IBTrACSPlan("NA", cache).years(1980, 2024)
    t = time.time()
    src = plan.prefetch()
    storms, points, cols = set(), 0, None
    for batch in plan.batches():
        cols = cols or batch.schema.names
        for r in batch.to_pylist():
            try:
                lat, lon = float(r["LAT"]), float(r["LON"])
            except (TypeError, ValueError, KeyError):
                continue
            if TEXAS[0] <= lon <= TEXAS[2] and TEXAS[1] <= lat <= TEXAS[3]:
                storms.add(r["SID"])
                points += 1
    return {
        "basin": "NA",
        "years": "1980-2024",
        "storms_with_points_in_texas_box": len(storms),
        "track_points_in_box": points,
        "columns": cols[:14] if cols else None,
        "seconds": round(time.time() - t, 1),
        "source": {k: str(v)[:120] for k, v in dict(src).items()},
        "cache_bytes": dir_bytes(cache),
    }


def probe_coops() -> dict:
    from crc_sdk.workflows import NOAAExtremeWaterLevelPlan, NOAASeaLevelPlan

    cache = CACHE / "coops"
    out = {}
    t = time.time()
    wl = NOAAExtremeWaterLevelPlan.for_station("8771341").cache(cache, mode="reuse")
    info = wl.source_info()
    out["water_levels_info"] = (
        {k: str(v)[:100] for k, v in dict(info).items()}
        if hasattr(info, "items")
        else str(info)[:300]
    )
    levels = wl.source_levels()
    out["levels"] = levels.to_pylist()[:8] if hasattr(levels, "to_pylist") else str(levels)[:500]
    ann = wl.annual_extremes()
    out["annual_rows"] = _rows(ann)
    out["annual_sample"] = ann.slice(0, 2).to_pylist() if hasattr(ann, "slice") else str(ann)[:200]
    out["water_levels_s"] = round(time.time() - t, 1)
    t = time.time()
    sl = NOAASeaLevelPlan.for_station("8771450").scenario("all").cache(cache, mode="reuse")
    proj = sl.projections()
    out["sea_level_rows"] = _rows(proj)
    out["sea_level_sample"] = (
        proj.slice(0, 3).to_pylist() if hasattr(proj, "slice") else str(proj)[:300]
    )
    out["sea_level_s"] = round(time.time() - t, 1)
    out["cache_bytes"] = dir_bytes(cache)
    return out


def probe_glofas() -> dict:
    import pyarrow.parquet as pq
    from crc_sdk.workflows import HazardDataset, JRCFloodPolicy

    cache = CACHE / "glofas"
    plan = (
        HazardDataset.glofas()
        .for_area(AUSTIN_BOX)
        .cache(cache, mode="reuse")
        .source_periods("all")
        .canonicalize(policy=JRCFloodPolicy.curated(h3_resolution=7))
    )
    t = time.time()
    target = cache / "glofas-austin.parquet"
    ds = plan.materialize(target)
    tbl = pq.read_table(target)
    return {
        "box": AUSTIN_BOX,
        "rows": tbl.num_rows,
        "seconds": round(time.time() - t, 1),
        "kinds": tbl.column("curve_kind").value_counts().to_pylist(),
        "cache_bytes": dir_bytes(cache),
        "provenance": str(ds.provenance())[:400],
    }


def probe_edo() -> dict:
    import pyarrow.parquet as pq
    from crc_sdk.workflows import EDODroughtPolicy, HazardDataset

    cache = CACHE / "edo"
    plan = (
        HazardDataset.smi()
        .for_area(AUSTIN_BOX)
        .years("all_complete")
        .cache(cache, mode="reuse")
        .canonicalize(policy=EDODroughtPolicy.curated(h3_resolution=5))
    )
    t = time.time()
    target = cache / "edo-austin.parquet"
    ds = plan.materialize(target)
    return {
        "rows": pq.read_table(target).num_rows,
        "seconds": round(time.time() - t, 1),
        "provenance": str(ds.provenance())[:300],
    }


def probe_eccc() -> dict:
    from crc_sdk.workflows import ECCCDailyPlan, HazardDataset

    cache = CACHE / "eccc"
    out = {}
    try:
        st = (
            HazardDataset.eccc_idf("1h", province="ON", version="3.40")
            .for_area(TEXAS)
            .cache(cache, mode="reuse")
            .stations()
        )
        out["idf_ON_stations_in_texas"] = _rows(st)
    except Exception as e:  # noqa: BLE001
        out["idf_ON"] = f"{type(e).__name__}: {str(e)[:300]}"
    out["eccc_daily_api"] = [m for m in dir(ECCCDailyPlan) if not m.startswith("_")]
    return out


def probe_cdl() -> dict:
    from crc_sdk.workflows import AgriculturalLayer

    t = time.time()
    mix = (
        AgriculturalLayer.usda_cdl()
        .resolution("30m")
        .for_area(SMALL_BOX)
        .years(2024)
        .scan()
        .pipeline()
        .aggregate("count(*) AS sampled_pixels", groups="year, crop_code, crop_name")
    )
    rows = []
    for batch in mix.to_arrow_reader():
        rows.extend(batch.to_pylist())
    rows.sort(key=lambda r: -r["sampled_pixels"])
    return {
        "box": SMALL_BOX,
        "classes": len(rows),
        "top": rows[:6],
        "seconds": round(time.time() - t, 1),
    }


def probe_ftw() -> dict:
    from crc_sdk.workflows import AgriculturalLayer

    t = time.time()
    fields = AgriculturalLayer.ftw_fields().in_country("US").for_area(SMALL_BOX).scan().pipeline()
    n, cols = 0, None
    for batch in fields.to_arrow_reader():
        n += batch.num_rows
        cols = cols or batch.schema.names
    return {"fields_in_box": n, "columns": cols, "seconds": round(time.time() - t, 1)}


def probe_era5() -> dict:
    import pyarrow.parquet as pq
    from crc_sdk.workflows import BlockExtremaPolicy, HazardDataset

    years, resolution = (1991, 2020), 4
    cache = CACHE / "era5"
    plan = (
        HazardDataset.era5("txx", store="wb2-1p5")
        .for_area(TEXAS, land_only=True)
        .years(*years)
        .cache(cache, mode="reuse")
        .canonicalize(policy=BlockExtremaPolicy.curated(h3_resolution=resolution))
    )
    t = time.time()
    target = cache / f"era5-txx-r{resolution}.parquet"
    ds = plan.materialize(target)
    tbl = pq.read_table(target)
    return {
        "years": years,
        "h3_resolution": resolution,
        "rows": tbl.num_rows,
        "seconds": round(time.time() - t, 1),
        "cache_bytes": dir_bytes(cache),
        "provenance": str(ds.provenance())[:400],
    }


def probe_nex() -> dict:
    from crc_sdk.workflows import HazardDataset

    t = time.time()
    plan = (
        HazardDataset.nex_gddp_cmip6(
            "txx", model="ACCESS-CM2", scenario="historical", version="1.0"
        )
        .for_area(AUSTIN_BOX)
        .years(2014)
    )
    n, cols = 0, None
    for batch in plan.annual_extremes():
        n += batch.num_rows
        cols = cols or batch.schema.names
    return {"rows": n, "columns": cols, "seconds": round(time.time() - t, 1)}


PROBES = {name[6:]: fn for name, fn in dict(globals()).items() if name.startswith("probe_")}

if __name__ == "__main__":
    name = sys.argv[1]
    started = time.time()
    record = {"source": name, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            record["result"] = PROBES[name]()
        except Exception as error:  # noqa: BLE001
            record["could_not_verify"] = f"{type(error).__name__}: {str(error)[:600]}"
            record["traceback"] = traceback.format_exc()[-1500:]
    record["warnings"] = sorted({str(w.message)[:200] for w in caught})
    record["total_s"] = round(time.time() - started, 1)
    print(json.dumps(record, indent=1, default=str))
