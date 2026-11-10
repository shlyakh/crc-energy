# ruff: noqa: E501
"""A2: compare the two federal building sources for one county (Fort Bend, FIPS 48157).

National Structure Inventory (USACE): one point per structure with occupancy, building type and
values. USA Structures (FEMA / ORNL, GeoParquet copy on Source Cooperative): footprint polygons
with occupancy class. Reports counts, occupancy agreement and how well points join to footprints.
``python -m crc_lab.assets.real_estate`` writes the note and one map.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import urllib.request
from pathlib import Path
from typing import Any

import duckdb

FIPS = "48157"
NSI_URL = "https://nsi.sec.usace.army.mil/nsiapi/structures?fips={fips}&fmt=fc"
USA_LISTING = "https://data.source.coop/wherobots/usa-structures/"
# NSI damage category -> USA Structures occupancy classes counted as agreeing
AGREE = {
    "RES": {"Residential"},
    "COM": {"Commercial", "Assembly"},
    "IND": {"Industrial", "Utility and Misc", "Agriculture"},
    "PUB": {"Government", "Education", "Assembly"},
}


def fetch(cache: Path, fips: str = FIPS) -> tuple[Path, Path]:
    directory = cache / "real-estate"
    directory.mkdir(parents=True, exist_ok=True)
    nsi = directory / f"nsi_{fips}.geojson"
    if not nsi.exists():
        urllib.request.urlretrieve(NSI_URL.format(fips=fips), nsi)
    usa = directory / f"usa_structures_{fips}.parquet"
    if not usa.exists():
        xml = urllib.request.urlopen(USA_LISTING).read().decode()
        urls = [
            "https://data.source.coop/wherobots/" + k
            for k in re.findall(r"<Key>(usa-structures/geoparquet/part[^<]*)</Key>", xml)
        ]
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
        con.execute(
            f"COPY (SELECT * FROM read_parquet({urls!r}) WHERE FIPS = '{fips}') TO '{usa}' (FORMAT PARQUET)"
        )
    return nsi, usa


def analyse(nsi: Path, usa: Path) -> dict[str, Any]:
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute(f"""CREATE TABLE n AS SELECT fd_id, st_damcat, occtype, bldgtype, val_struct, val_cont, sqft, ftprntsrc, ftprntid, geom
                    FROM ST_Read('{nsi}')""")
    con.execute(
        f"CREATE TABLE u AS SELECT BUILD_ID, UUID, OCC_CLS, PRIM_OCC, SQMETERS, geometry AS geom FROM read_parquet('{usa}')"
    )
    con.execute("CREATE INDEX u_idx ON u USING RTREE (geom)")
    con.execute(
        "CREATE TABLE j AS SELECT n.fd_id, n.st_damcat, n.val_struct, u.BUILD_ID, u.OCC_CLS FROM n LEFT JOIN u ON ST_Within(n.geom, u.geom)"
    )
    one = lambda sql: con.execute(sql).fetchone()  # noqa: E731
    out: dict[str, Any] = {"fips": FIPS}
    out["counts"] = {
        "nsi_points": one("SELECT count(*) FROM n")[0],
        "usa_footprints": one("SELECT count(*) FROM u")[0],
        "nsi_structure_value_usd": one("SELECT sum(val_struct) FROM n")[0],
        "nsi_contents_value_usd": one("SELECT sum(val_cont) FROM n")[0],
        "usa_footprint_area_km2": one("SELECT sum(SQMETERS) / 1e6 FROM u")[0],
    }
    out["nsi_by_category"] = con.execute(
        "SELECT st_damcat, count(*), round(sum(val_struct) / 1e9, 2) FROM n GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()
    out["nsi_by_building_type"] = con.execute(
        "SELECT bldgtype, count(*) FROM n GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()
    out["nsi_footprint_source"] = con.execute(
        "SELECT ftprntsrc, count(*) FROM n GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()
    out["usa_by_class"] = con.execute(
        "SELECT OCC_CLS, count(*) FROM u GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()
    points_in = one("SELECT count(DISTINCT fd_id) FROM j WHERE BUILD_ID IS NOT NULL")[0]
    out["join"] = {
        "nsi_points_inside_a_footprint": points_in,
        "share_of_nsi_points": points_in / out["counts"]["nsi_points"],
        "nsi_points_in_several_footprints": one(
            "SELECT count(*) FROM (SELECT fd_id FROM j WHERE BUILD_ID IS NOT NULL GROUP BY 1 HAVING count(*) > 1)"
        )[0],
        "footprints_with_a_point": one(
            "SELECT count(DISTINCT BUILD_ID) FROM j WHERE BUILD_ID IS NOT NULL"
        )[0],
        "footprints_with_several_points": one(
            "SELECT count(*) FROM (SELECT BUILD_ID FROM j WHERE BUILD_ID IS NOT NULL GROUP BY 1 HAVING count(*) > 1)"
        )[0],
        "share_of_structure_value_joined": one(
            "SELECT sum(val_struct) FILTER (WHERE BUILD_ID IS NOT NULL) / sum(val_struct) FROM (SELECT DISTINCT ON (fd_id) * FROM j)"
        )[0],
    }
    out["join"]["share_of_footprints_with_a_point"] = (
        out["join"]["footprints_with_a_point"] / out["counts"]["usa_footprints"]
    )
    pairs = con.execute(
        "SELECT st_damcat, OCC_CLS, count(*) FROM j WHERE BUILD_ID IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 3 DESC"
    ).fetchall()
    out["occupancy_pairs"] = pairs
    agree = sum(n for cat, cls, n in pairs if cls in AGREE.get(cat, set()))
    out["occupancy_agreement"] = {
        "joined_pairs": sum(n for *_, n in pairs),
        "agree": agree,
        "share": agree / max(1, sum(n for *_, n in pairs)),
        "mapping": {k: sorted(v) for k, v in AGREE.items()},
    }
    out["points"] = con.execute(
        "SELECT round(ST_X(geom), 2), round(ST_Y(geom), 2), count(*), sum(CASE WHEN fd_id IN (SELECT fd_id FROM j WHERE BUILD_ID IS NOT NULL) THEN 1 ELSE 0 END) FROM n GROUP BY 1, 2"
    ).fetchall()
    return out


def map_svg(results: dict[str, Any]) -> str:
    pts = results["points"]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs) + 0.01, min(ys), max(ys) + 0.01
    w = 720
    k = w / (x1 - x0)
    h = (y1 - y0) * k / math.cos(math.radians((y0 + y1) / 2))
    ky = h / (y1 - y0)
    top = math.log1p(max(p[2] for p in pts))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h + 34:.0f}" font-family="Helvetica, Arial, sans-serif">',
        f'<rect width="{w}" height="{h + 34:.0f}" fill="#faf9f6"/>',
        '<text x="10" y="20" font-size="14" font-weight="600" fill="#2a2a28">Fort Bend County: structures per 0.01° bin (National Structure Inventory)</text>',
        '<g transform="translate(0,30)">',
    ]
    for x, y, n, joined in pts:
        t = math.log1p(n) / top
        stroke = "" if joined / n >= 0.5 else ' stroke="#eb6834" stroke-width="0.8"'
        parts.append(
            f'<rect x="{(x - x0) * k:.1f}" y="{h - (y - y0 + 0.01) * ky:.1f}" width="{0.01 * k:.1f}" height="{0.01 * ky:.1f}" fill="oklch({93 - 58 * t:.0f}% {0.12 + 0.05 * t:.2f} 235)"{stroke}/>'
        )
    parts.append("</g></svg>")
    return "\n".join(parts)


def markdown(r: dict[str, Any]) -> str:
    c, j, a = r["counts"], r["join"], r["occupancy_agreement"]
    row = lambda items: "\n".join(f"| {' | '.join(str(x) for x in i)} |" for i in items)  # noqa: E731
    return f"""# Phase 4 note: two federal building sources in Fort Bend County (A2)

County FIPS {r["fips"]}. National Structure Inventory (NSI, US Army Corps, API) against USA Structures (FEMA / Oak
Ridge, GeoParquet copy on Source Cooperative). Every number is computed by `python -m crc_lab.assets.real_estate`.

## Counts

| | NSI | USA Structures |
| --- | --- | --- |
| Records | {c["nsi_points"]:,} points | {c["usa_footprints"]:,} footprints |
| Structure value | ${c["nsi_structure_value_usd"] / 1e9:,.1f} billion (contents ${c["nsi_contents_value_usd"] / 1e9:,.1f} billion) | not provided |
| Footprint area | not provided as geometry | {c["usa_footprint_area_km2"]:,.1f} km² |

NSI by damage category (count, structure value in $ billion):

| Category | Count | Value |
| --- | --- | --- |
{row(r["nsi_by_category"])}

NSI building type (W wood, M masonry, S steel, H manufactured, C concrete):

| Type | Count |
| --- | --- |
{row(r["nsi_by_building_type"])}

USA Structures occupancy class:

| Class | Count |
| --- | --- |
{row(r["usa_by_class"])}

Where NSI says its own footprint came from:

| Source | Count |
| --- | --- |
{row(r["nsi_footprint_source"])}

## Point-to-footprint join

| Measure | Value |
| --- | --- |
| NSI points inside a USA Structures footprint | {j["nsi_points_inside_a_footprint"]:,} ({j["share_of_nsi_points"]:.1%}) |
| Share of NSI structure value on joined points | {j["share_of_structure_value_joined"]:.1%} |
| NSI points inside more than one footprint | {j["nsi_points_in_several_footprints"]:,} |
| Footprints holding at least one NSI point | {j["footprints_with_a_point"]:,} ({j["share_of_footprints_with_a_point"]:.1%}) |
| Footprints holding several NSI points | {j["footprints_with_several_points"]:,} |

## Occupancy agreement on joined pairs

{a["agree"]:,} of {a["joined_pairs"]:,} joined pairs agree ({a["share"]:.1%}) under this mapping: {json.dumps(a["mapping"])}.

| NSI category | USA Structures class | Pairs |
| --- | --- | --- |
{row(r["occupancy_pairs"])}

## Map

Darker bins hold more structures; an orange outline marks bins where fewer than half of the NSI points fall inside
a USA Structures footprint.

![Fort Bend structures](figures/real-estate-fort-bend.svg)
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument(
        "--note", type=Path, default=Path("docs/reports/4-real-estate-fort-bend.md")
    )
    args = parser.parse_args(argv)
    nsi, usa = fetch(args.cache)
    results = analyse(nsi, usa)
    figures = args.note.parent / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    (figures / "real-estate-fort-bend.svg").write_text(map_svg(results))
    args.note.write_text(markdown(results))
    summary = {k: results[k] for k in ("counts", "join", "occupancy_agreement")}
    print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
