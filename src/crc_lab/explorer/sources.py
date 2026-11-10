"""Sources track (S1): schematic explorer layers for crc-sdk sources other than CRC Open.

``python -m crc_lab.explorer.sources [--only name ...]`` writes GeoJSON files under
``site/data/sources/`` plus a ``manifest.json`` data card (G2). Layers are registered in
``site/layers.json`` with kind ``points`` or ``lines``; the page draws them generically.

Curves at points are either published by the source (NOAA CO-OPS annual exceedance levels,
shipped as published) or fitted by crc-sdk (GHCNh station curves, evaluated with
``curve_quantiles`` at the same return periods as the CRC Open layers). Nothing is fitted
or interpolated here.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import time
import warnings
from importlib.metadata import version
from pathlib import Path
from typing import Any

from crc_lab import PINNED
from crc_lab.explorer.hazards import RETURN_PERIODS, _params, _round
from crc_lab.explorer.texas import write_json_atomic

TEXAS = (-106.645646, 25.837377, -93.508292, 36.500704)
GHCNH_YEARS = (2000, 2024)

# NOAA CO-OPS water-level stations in Texas (state == "TX"), listed 2026-11-10 from
# https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=waterlevels
COOPS_TX_STATIONS = (
    "8770475",
    "8770520",
    "8770613",
    "8770777",
    "8770808",
    "8770822",
    "8770971",
    "8771013",
    "8771341",
    "8771367",
    "8771450",
    "8771486",
    "8771972",
    "8772471",
    "8772985",
    "8773037",
    "8773146",
    "8773259",
    "8773701",
    "8773767",
    "8774230",
    "8774513",
    "8774770",
    "8775132",
    "8775222",
    "8775237",
    "8775241",
    "8775283",
    "8775296",
    "8775792",
    "8775870",
    "8776139",
    "8776604",
    "8777812",
    "8778490",
    "8779280",
    "8779748",
    "8779749",
    "8779770",
)


def _f(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def in_box(lon: float, lat: float, box: tuple[float, float, float, float]) -> bool:
    return box[0] <= lon <= box[2] and box[1] <= lat <= box[3]


# ---------------------------------------------------------------- IBTrACS (tracks)
def build_ibtracs(cache_dir: Path, out: Path) -> dict[str, Any]:
    """Explorer v2: storm records with per-point wind, from ``crc_lab.explorer.tracks``."""
    from crc_lab.explorer.tracks import build_tracks

    return build_tracks(cache_dir, out)


# ---------------------------------------------------------------- NOAA CO-OPS (points)
def coops_feature(info: dict[str, Any], levels: list[dict[str, Any]]) -> dict | None:
    """One station's published annual-exceedance levels as a point with a curve (pure)."""
    if not levels:
        return None
    first = levels[0]
    lon, lat = _f(first.get("longitude")), _f(first.get("latitude"))
    if lon is None or lat is None:
        return None
    rows = sorted(
        (
            r
            for r in levels
            if _f(r.get("published_return_period_years")) and _f(r.get("water_level_m")) is not None
        ),
        key=lambda r: float(r["published_return_period_years"]),
    )
    station = info.get("station") if isinstance(info.get("station"), dict) else {}
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
        "properties": {
            "label": f"{first.get('station_name')} ({first.get('station_id')})",
            "station_id": first.get("station_id"),
            "datum": f"{first.get('datum')} (epoch {first.get('datum_epoch')})",
            "trend_mm_per_year": _f(info.get("trend")),
            "trend_period": f"{info.get('trend_start_date')} to {info.get('trend_end_date')}"
            if info.get("trend_start_date")
            else None,
            "levels_published": len(rows),
            "curve": {
                "return_periods": [float(r["published_return_period_years"]) for r in rows],
                "values": [float(r["water_level_m"]) for r in rows],
                "lower_90ci": [_f(r.get("lower_90ci_m")) for r in rows],
                "upper_90ci": [_f(r.get("upper_90ci_m")) for r in rows],
                "unit": f"m above {first.get('datum')}",
                "note": (
                    "Published by NOAA CO-OPS (annual exceedance probability levels, "
                    "detrended series); not fitted by crc-sdk."
                ),
            },
            "station_title": station.get("stationTitle") if isinstance(station, dict) else None,
        },
    }


def build_coops(cache_dir: Path, out: Path) -> dict[str, Any]:
    from crc_sdk.workflows import NOAAExtremeWaterLevelPlan

    started = time.time()
    features, skipped = [], {}
    for sid in COOPS_TX_STATIONS:
        plan = NOAAExtremeWaterLevelPlan.for_station(sid).cache(cache_dir / "coops", mode="reuse")
        try:
            info = dict(plan.source_info())
            levels = plan.source_levels().to_pylist()
        except Exception as error:  # noqa: BLE001 - a station without the product is a finding, not a crash
            skipped[sid] = f"{type(error).__name__}: {str(error)[:160]}"
            continue
        feature = coops_feature(info, levels)
        if feature is None:
            skipped[sid] = "no published levels"
            continue
        features.append(feature)
    write_json_atomic(out, {"type": "FeatureCollection", "features": features})
    return {
        "layer": "coops",
        "file": str(out),
        "stations_tried": len(COOPS_TX_STATIONS),
        "stations_with_levels": len(features),
        "skipped": skipped,
        "source": (
            "NOAA CO-OPS Extreme Water Levels product (api.tidesandcurrents.noaa.gov); "
            "station list from the CO-OPS metadata API, 2026-11-10"
        ),
        "licence": "U.S. government work; attribution requested (NOAA CO-OPS)",
        "seconds": round(time.time() - started, 1),
        "bytes": out.stat().st_size,
    }


# ---------------------------------------------------------------- GHCNh (points with fitted curves)
def station_features(
    table_rows: list[dict[str, Any]],
    values: list[tuple[float | None, ...]],
    names: dict[str, str],
    unit: str,
    return_periods=RETURN_PERIODS,
) -> list[dict]:
    """Canonical station rows + evaluated values -> point features with a curve (pure)."""
    import shapely

    features = []
    for row, vals in zip(table_rows, values, strict=True):
        geom = shapely.from_wkb(row["source_geometry"]) if row.get("source_geometry") else None
        if geom is None:
            continue
        sid = row.get("source_id")
        kind = row["curve_kind"]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(geom.x, 4), round(geom.y, 4)]},
                "properties": {
                    "label": f"{names.get(sid, sid)} ({sid})",
                    "station": sid,
                    "hazard": row.get("hazard_name"),
                    "horizon": row.get("horizon"),
                    "curve_kind": kind,
                    "family": row.get("curve_type"),
                    "cell_index": f"{row['cell_index']:x}"
                    if row.get("cell_index") is not None
                    else None,
                    "params": _params(row),
                    "curve": {
                        "return_periods": list(return_periods),
                        "values": [_round(v) for v in vals],
                        "unit": unit,
                        "note": (
                            "Fitted by crc-sdk (GEV, sample L-moments) from GHCNh hourly "
                            "temperature, evaluated by curve_quantiles."
                        ),
                    },
                },
            }
        )
    return features


def build_ghcnh(
    cache_dir: Path, out: Path, *, max_stations: int = 40, workers: int | None = None
) -> dict[str, Any]:
    from crc_sdk.connectors import read_hazard_dataset, read_hazard_metadata
    from crc_sdk.workflows import BlockExtremaPolicy, HazardDataset
    from crc_sdk.workflows.distributions import curve_quantiles, return_periods_to_probabilities

    started = time.time()
    cache = cache_dir / "ghcnh"
    catalogue = (
        HazardDataset.ghcnh("temperature_max")
        .for_area(TEXAS)
        .cache(cache, mode="reuse")
        .stations()
        .to_pylist()
    )
    usw = [r for r in catalogue if r["station"].startswith("USW")][:max_stations]
    names = {r["station"]: r["name"] for r in usw}
    plan = (
        HazardDataset.ghcnh("temperature_max")
        .for_stations([r["station"] for r in usw])
        .years(*GHCNH_YEARS)
        .cache(cache, mode="reuse")
        .canonicalize(policy=BlockExtremaPolicy.curated(minimum_years=15))
    )
    target = cache / "ghcnh-txx-texas.parquet"
    notes: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan.materialize(target)
    notes.extend(sorted({str(w.message)[:200] for w in caught}))
    meta = read_hazard_metadata(target)
    table = read_hazard_dataset(target)
    rows = table.to_pylist()
    probabilities = return_periods_to_probabilities(RETURN_PERIODS, tail=meta.return_period_tail)
    values = curve_quantiles(table, probabilities, max_workers=workers or 1)
    features = station_features(rows, values, names, meta.value_unit)
    write_json_atomic(out, {"type": "FeatureCollection", "features": features})
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["curve_kind"]] = kinds.get(r["curve_kind"], 0) + 1
    return {
        "layer": "ghcnh",
        "file": str(out),
        "stations_in_texas_catalogue": len(catalogue),
        "stations_requested": len(usw),
        "stations_with_curves": len(features),
        "years": list(GHCNH_YEARS),
        "kinds": kinds,
        "unit": meta.value_unit,
        "tail": meta.return_period_tail,
        "probability_semantics": meta.probability_semantics,
        "warnings": notes,
        "source": str(meta.source)[:400],
        "licence": "CC0-1.0 per the AWS registry; attribution requested (NOAA GHCNh)",
        "seconds": round(time.time() - started, 1),
        "bytes": out.stat().st_size,
    }


def verify_ghcnh(cache_dir: Path, out: Path, *, sample: int = 3) -> dict[str, Any]:
    """Shipped station values equal crc-sdk's ``for_assets`` at the station point (H3 join)."""
    import tempfile

    import pyarrow as pa
    import pyarrow.parquet as pq
    from crc_sdk.workflows import HazardDataset

    payload = json.loads(out.read_text())
    feats = payload["features"][:sample]
    if not feats:
        return {"layer": "ghcnh", "values_checked": 0, "mismatches": [], "note": "no features"}
    assets = pa.table(
        {
            "asset_id": [f["properties"]["station"] for f in feats],
            "longitude": [f["geometry"]["coordinates"][0] for f in feats],
            "latitude": [f["geometry"]["coordinates"][1] for f in feats],
        }
    )
    checked, mismatches = 0, []
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "eval.parquet"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            HazardDataset.local(cache_dir / "ghcnh" / "ghcnh-txx-texas.parquet").for_assets(
                assets
            ).return_periods(list(RETURN_PERIODS)).write_parquet(target)
        for row in pq.read_table(target).to_pylist():
            feat = next(f for f in feats if f["properties"]["station"] == row["asset_id"])
            for rp, mine in zip(RETURN_PERIODS, feat["properties"]["curve"]["values"], strict=True):
                theirs = row[f"value_rp{rp}"]
                checked += 1
                if mine is None and theirs is None:
                    continue
                if (
                    mine is None
                    or theirs is None
                    or not math.isclose(mine, theirs, rel_tol=1e-5, abs_tol=1e-6)
                ):
                    mismatches.append(
                        {
                            "station": row["asset_id"],
                            "rp": rp,
                            "shipped": mine,
                            "for_assets": theirs,
                        }
                    )
    return {"layer": "ghcnh", "values_checked": checked, "mismatches": mismatches}


# ---------------------------------------------------------------- ERA5 txx baseline (h3-cells, r4)
ERA5_YEARS = (1991, 2020)
ERA5_RESOLUTION = 4


def build_era5(cache_dir: Path, out_dir: Path, *, workers: int | None = None) -> dict[str, Any]:
    """ERA5 ``txx`` 1991–2020 from the 1.5° WeatherBench2 store, fitted by crc-sdk on H3 r4 cells.

    Written in the same file shape as the CRC Open hazard files
    (``data/hazards/{hazard}/{horizon}.json``) so the page draws it through the ``h3-cells``
    kind; the registry entry carries its own ``horizons`` (the window centre).
    """
    from crc_sdk.connectors import read_hazard_dataset, read_hazard_metadata
    from crc_sdk.workflows import BlockExtremaPolicy, HazardDataset
    from crc_sdk.workflows.distributions import return_periods_to_probabilities

    from crc_lab.explorer.hazards import KINDS, evaluate

    started = time.time()
    cache = cache_dir / "era5"
    target = cache / f"era5-txx-r{ERA5_RESOLUTION}.parquet"
    notes: list[str] = []
    if not target.exists():
        plan = (
            HazardDataset.era5("txx", store="wb2-1p5")
            .for_area(TEXAS, land_only=True)
            .years(*ERA5_YEARS)
            .cache(cache, mode="reuse")
            .canonicalize(policy=BlockExtremaPolicy.curated(h3_resolution=ERA5_RESOLUTION))
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            plan.materialize(target)
        notes.extend(sorted({str(w.message)[:200] for w in caught}))
    meta = read_hazard_metadata(target)
    table = read_hazard_dataset(target).sort_by("cell_index")
    rows = table.to_pylist()
    probabilities = return_periods_to_probabilities(RETURN_PERIODS, tail=meta.return_period_tail)
    horizons = sorted({int(r["horizon"]) for r in rows})
    files, counts = [], {}
    for horizon in horizons:
        part = [r for r in rows if int(r["horizon"]) == horizon]
        import pyarrow as pa

        values, _outside = evaluate(
            pa.Table.from_pylist(part), part, probabilities, workers=workers
        )
        payload = {
            "hazard": "era5_txx",
            "horizon": horizon,
            "pathway": part[0]["pathway"] if part else "historical",
            "release": f"ERA5 via {meta.source.uri}" if hasattr(meta.source, "uri") else "ERA5",
            "unit": meta.value_unit,
            "value_semantics": meta.value_semantics,
            "tail": meta.return_period_tail,
            "probability_semantics": meta.probability_semantics,
            "h3_resolution": meta.h3_resolution,
            "return_periods": list(RETURN_PERIODS),
            "probabilities": [float(p) for p in probabilities],
            "kinds": list(KINDS),
            "cells": [f"{r['cell_index']:x}" for r in part],
            "values": [[_round(v) for v in per_cell] for per_cell in values],
            "params": [_params(r) for r in part],
        }
        path = out_dir / f"{horizon}.json"
        write_json_atomic(path, payload)
        files.append(str(path))
        counts[str(horizon)] = len(part)
    return {
        "layer": "era5_txx",
        "files": files,
        "years": list(ERA5_YEARS),
        "h3_resolution": meta.h3_resolution,
        "horizons": horizons,
        "cells_per_horizon": counts,
        "unit": meta.value_unit,
        "tail": meta.return_period_tail,
        "probability_semantics": meta.probability_semantics,
        "temporal_window": str(meta.temporal_window)[:200],
        "fitting": str(meta.fitting)[:200],
        "warnings": notes,
        "source": str(meta.source)[:400],
        "licence": (
            "CC BY 4.0 (Copernicus); "
            "'Contains modified Copernicus Climate Change Service information'"
        ),
        "seconds": round(time.time() - started, 1),
        "bytes": sum(Path(f).stat().st_size for f in files),
    }


BUILDERS = {
    "ibtracs": build_ibtracs,
    "coops": build_coops,
    "ghcnh": build_ghcnh,
    "era5": build_era5,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("site/data/sources"))
    parser.add_argument("--cache", type=Path, default=Path("data/cache/sources"))
    parser.add_argument("--only", nargs="+", default=list(BUILDERS))
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text())
        if manifest_path.exists()
        else {"layers": {}, "verification": {}}
    )
    started = time.time()
    for name in args.only:
        if name == "era5":
            target = args.out / "era5_txx"
        elif name == "ibtracs":
            target = args.out / "ibtracs.json"
        else:
            target = args.out / f"{name}.geojson"
        record = BUILDERS[name](args.cache, target)
        manifest["layers"][name] = record
        keys = (
            "storms_crossing_texas",
            "track_points",
            "stations_with_levels",
            "stations_with_curves",
        )
        keys += ("kinds", "seconds", "bytes")
        print(f"{name}: {json.dumps({k: v for k, v in record.items() if k in keys})}")
        if args.verify and name == "ghcnh":
            check = verify_ghcnh(args.cache, args.out / "ghcnh.geojson")
            manifest["verification"]["ghcnh"] = check
            n_bad = len(check["mismatches"])
            print(f"verify ghcnh: {check['values_checked']} values, {n_bad} mismatches")
    manifest.update(
        {
            "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "versions": {name: version(name) for name in PINNED},
            "return_periods": list(RETURN_PERIODS),
            "texas_bounds": TEXAS,
            "seconds": round(time.time() - started, 1),
        }
    )
    write_json_atomic(manifest_path, manifest, indent=1)
    failed = [k for k, v in manifest["verification"].items() if v.get("mismatches")]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
