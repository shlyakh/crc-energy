"""IBTrACS tropical cyclone tracks for the explorer (the worked example of explorer v2).

Reads the North Atlantic basin subset through crc-sdk's ``IBTrACSPlan`` (cached, checksummed),
keeps every storm with at least one best-track point inside the Texas box, clips each track
to a wide Gulf box so the approach is visible, and writes one compact JSON file with one
record per storm and one row per track point. Winds are WMO agency winds (knots) when
present, else the US agency wind, with a flag; the Saffir-Simpson category is NOAA's
``USA_SSHS`` as published. Track points are observations, not asset winds or curves.
"""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from lab_common.texas import write_json_atomic

TEXAS = (-106.645646, 25.837377, -93.508292, 36.500704)
WIDE_BOX = (-110.0, 14.0, -75.0, 45.0)
SEASONS = (1950, 2025)
CITATION = "Schreck et al. (2024), IBTrACS v04r01, NOAA NCEI, doi:10.25921/82ty-9e16"


def _f(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _i(value: Any) -> int | None:
    f = _f(value)
    return int(f) if f is not None else None


def in_box(lon: float, lat: float, box: tuple[float, float, float, float]) -> bool:
    return box[0] <= lon <= box[2] and box[1] <= lat <= box[3]


QUADRANTS = ("NE", "SE", "SW", "NW")
RADII = (34, 50, 64)


def quadrant_radii(row: dict[str, Any], knots: int) -> list[float | None] | None:
    """``USA_R{knots}_{NE,SE,SW,NW}`` in nautical miles; None when no quadrant is given."""
    values = [_f(row.get(f"USA_R{knots}_{q}")) for q in QUADRANTS]
    values = [v if v is not None and v >= 0 else None for v in values]
    return values if any(v for v in values) else None


def storm_records(
    rows: list[dict[str, Any]], *, texas=TEXAS, box=WIDE_BOX, seasons=SEASONS
) -> list[dict[str, Any]]:
    """Group IBTrACS rows by storm; keep storms touching Texas; clip to ``box``.

    Pure function (tested offline). Rows carry the IBTrACS CSV columns as strings.
    """
    by_storm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        season = _i(r.get("SEASON"))
        if season is None or not seasons[0] <= season <= seasons[1]:
            continue
        by_storm[r["SID"]].append(r)
    storms = []
    for sid, pts in by_storm.items():
        pts.sort(key=lambda r: r.get("ISO_TIME") or "")
        track, hit, winds_tx, cats, winds, pres = [], False, [], [], [], []
        wind_source = set()
        has = {"r34": 0, "r50": 0, "r64": 0, "rmw": 0, "roci": 0}
        first_tx = last_tx = None
        for r in pts:
            lon, lat = _f(r.get("LON")), _f(r.get("LAT"))
            if lon is None or lat is None or not in_box(lon, lat, box):
                continue
            w = _f(r.get("WMO_WIND"))
            if w is not None:
                wind_source.add("wmo")
            else:
                w = _f(r.get("USA_WIND"))
                if w is not None:
                    wind_source.add("usa")
            p = _f(r.get("WMO_PRES"))
            if p is None:
                p = _f(r.get("USA_PRES"))
            cat = _i(r.get("USA_SSHS"))
            when = (r.get("ISO_TIME") or "")[:16]
            inside = in_box(lon, lat, texas)
            radii = [quadrant_radii(r, k) for k in RADII]
            rmw, roci = _f(r.get("USA_RMW")), _f(r.get("USA_ROCI"))
            for key, value in zip(("r34", "r50", "r64"), radii, strict=True):
                if value:
                    has[key] += 1
            has["rmw"] += rmw is not None
            has["roci"] += roci is not None
            track.append(
                [round(lon, 2), round(lat, 2), w, p, cat, when, r.get("NATURE") or None]
                + [*radii, rmw, roci]
            )
            if w is not None:
                winds.append(w)
            if p is not None:
                pres.append(p)
            if cat is not None:
                cats.append(cat)
            if inside:
                hit = True
                first_tx = first_tx or when
                last_tx = when
                if w is not None:
                    winds_tx.append(w)
        if not hit or len(track) < 2:
            continue
        head = pts[0]
        name = (head.get("NAME") or "").strip().title() or "Unnamed"
        storms.append(
            {
                "sid": sid,
                "name": name,
                "season": _i(head.get("SEASON")),
                "label": f"{name} {head.get('SEASON')}",
                "max_wind_kt": max(winds) if winds else None,
                "max_wind_kt_in_texas": max(winds_tx) if winds_tx else None,
                "min_pressure_mb": min(pres) if pres else None,
                "max_category": max(cats) if cats else None,
                "wind_source": "+".join(sorted(wind_source)) or None,
                "extent_points": has,
                "first_texas_point": first_tx,
                "last_texas_point": last_tx,
                "points": track,
            }
        )
    storms.sort(key=lambda s: (s["season"], s["sid"]))
    return storms


def build_tracks(cache_dir: Path, out: Path) -> dict[str, Any]:
    from crc_sdk.workflows import IBTrACSPlan

    started = time.time()
    plan = IBTrACSPlan("NA", cache_dir / "ibtracs").years(*SEASONS)
    source = dict(plan.prefetch())
    rows: list[dict[str, Any]] = []
    for batch in plan.batches():
        rows.extend(batch.to_pylist())
    storms = storm_records(rows)
    with_wind = sum(1 for s in storms if s["max_wind_kt"] is not None)
    payload = {
        "source": "NOAA NCEI IBTrACS v04r01, North Atlantic basin, via crc-sdk IBTrACSPlan",
        "citation": CITATION,
        "licence": "U.S. government work; attribution requested",
        "url": source.get("url"),
        "sha256": source.get("sha256"),
        "retrieved_at": source.get("retrieved_at"),
        "seasons": list(SEASONS),
        "texas_box": TEXAS,
        "clip_box": WIDE_BOX,
        "rule": "storms with at least one best-track point inside the Texas box; "
        "tracks clipped to the clip box",
        "point_fields": [
            "lon",
            "lat",
            "wind_kt",
            "pressure_mb",
            "category",
            "time_utc",
            "nature",
            "r34_nm",
            "r50_nm",
            "r64_nm",
            "rmw_nm",
            "roci_nm",
        ],
        "extent_note": "r34/r50/r64 are US agency estimates of the largest radius of 34, 50 and "
        "64 kt winds in the NE, SE, SW and NW quadrants (nautical miles); rmw is the radius of "
        "maximum wind, roci the radius of the outermost closed isobar; null where IBTrACS has none",
        "wind_note": "WMO agency wind where present, else US agency wind (wind_source says which); "
        "knots, 10-minute or 1-minute mean per agency; category is NOAA USA_SSHS",
        "storms": storms,
    }
    write_json_atomic(out, payload)
    return {
        "layer": "ibtracs",
        "file": str(out),
        "basin": "NA",
        "seasons": list(SEASONS),
        "rows_read": len(rows),
        "storms_crossing_texas": len(storms),
        "storms_with_wind": with_wind,
        "storms_with_r34": sum(1 for s in storms if s["extent_points"]["r34"]),
        "storms_with_r64": sum(1 for s in storms if s["extent_points"]["r64"]),
        "storms_with_rmw": sum(1 for s in storms if s["extent_points"]["rmw"]),
        "storms_with_roci": sum(1 for s in storms if s["extent_points"]["roci"]),
        "track_points": sum(len(s["points"]) for s in storms),
        "source": {
            k: str(v)[:200]
            for k, v in source.items()
            if k in ("url", "version", "sha256", "retrieved_at", "citation", "terms_url")
        },
        "licence": payload["licence"],
        "seconds": round(time.time() - started, 1),
        "bytes": out.stat().st_size,
    }
