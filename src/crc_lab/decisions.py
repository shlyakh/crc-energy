# ruff: noqa: E501
"""``python -m crc_lab.decisions``: the decisions document, with a chart for each choice and its alternatives.

Every number and chart is computed here from the built tables, so the document can be regenerated
after any rebuild. It reads: the plant table, the event table, neighbour hail reports, the radar
results, the reporting-bias cells, the four-source cell comparison and the Phase 3 sensitivity run.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow.parquet as pq

from crc_lab.assets import eia, exposure, solar
from lab_common.texas import texas_boundary

INK, MUTE, LINE, BG = "#2a2a28", "#7a7976", "#d9d7d2", "#faf9f6"
BLUE, ORANGE = "#2a78d6", "#eb6834"


def _svg(width: int, height: int, body: list[str], title: str) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" font-family="Helvetica, Arial, sans-serif" role="img" aria-label="{title}">',
            f'<rect width="{width}" height="{height}" fill="{BG}"/>',
            f'<text x="12" y="20" font-size="13" font-weight="600" fill="{INK}">{title}</text>',
            *body,
            "</svg>",
        ]
    )


def bars(
    title: str,
    rows: list[tuple[str, float]],
    unit: str,
    *,
    highlight: str | None = None,
    fmt: str = "{:,.0f}",
) -> str:
    """Horizontal bars, one hue; the chosen option is marked in orange."""
    w, left, bar_h, gap = 960, 430, 18, 10
    top = 36
    h = top + len(rows) * (bar_h + gap) + 24
    vmax = max(v for _, v in rows) or 1.0
    body = []
    for i, (label, v) in enumerate(rows):
        y = top + i * (bar_h + gap)
        length = (w - left - 110) * v / vmax
        colour = ORANGE if label == highlight else BLUE
        body += [
            f'<text x="{left - 8}" y="{y + 13}" font-size="12" text-anchor="end" fill="{INK}">{label}</text>',
            f'<rect x="{left}" y="{y}" width="{max(length, 1):.1f}" height="{bar_h}" rx="3" fill="{colour}"/>',
            f'<text x="{left + length + 6:.1f}" y="{y + 13}" font-size="12" fill="{INK}">{fmt.format(v)}</text>',
        ]
    body.append(f'<text x="{left}" y="{h - 6}" font-size="11" fill="{MUTE}">{unit}</text>')
    return _svg(w, h, body, title)


def ranges(
    title: str,
    rows: list[tuple[str, float, float, float]],
    unit: str,
    *,
    highlight: str | None = None,
    fmt: str = "{:.2f}",
    log: bool = False,
) -> str:
    """One line per option from the 10th to the 90th percentile with a dot at the median."""
    w, left, row_h = 960, 430, 28
    top = 40
    h = top + len(rows) * row_h + 30
    lo = min(r[1] for r in rows)
    hi = max(r[3] for r in rows)
    if log:
        lo = max(lo, hi / 1e4)

        def f(v):
            return (math.log10(max(v, lo)) - math.log10(lo)) / (
                math.log10(hi) - math.log10(lo) or 1
            )  # noqa: E731
    else:
        lo = 0.0
        f = lambda v: (v - lo) / (hi - lo or 1)  # noqa: E731
    span = w - left - 120
    body = []
    for i, (label, p10, med, p90) in enumerate(rows):
        y = top + i * row_h + 10
        colour = ORANGE if label == highlight else BLUE
        x1, xm, x2 = left + span * f(p10), left + span * f(med), left + span * f(p90)
        body += [
            f'<text x="{left - 8}" y="{y + 4}" font-size="12" text-anchor="end" fill="{INK}">{label}</text>',
            f'<line x1="{x1:.1f}" x2="{x2:.1f}" y1="{y}" y2="{y}" stroke="{colour}" stroke-width="2" stroke-linecap="round"/>',
            f'<circle cx="{xm:.1f}" cy="{y}" r="5" fill="{colour}" stroke="{BG}" stroke-width="2"/>',
            f'<text x="{x2 + 8:.1f}" y="{y + 4}" font-size="11.5" fill="{INK}">{fmt.format(med)} ({fmt.format(p10)}–{fmt.format(p90)})</text>',
        ]
    body.append(
        f'<text x="{left}" y="{h - 8}" font-size="11" fill="{MUTE}">{unit}: dot = median, line = 10th to 90th percentile{" (log scale)" if log else ""}</text>'
    )
    return _svg(w, h, body, title)


def q3(values: list[float]) -> tuple[float, float, float]:
    a = np.asarray([v for v in values if v is not None and not math.isnan(v)], dtype=float)
    return float(np.quantile(a, 0.1)), float(np.median(a)), float(np.quantile(a, 0.9))


def table(header: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def pct(v: float | None, d: int = 2) -> str:
    return "–" if v is None else f"{100 * v:.{d}f}%"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/cache"))
    parser.add_argument("--events", type=Path, default=Path("data/storm-events/events.parquet"))
    parser.add_argument("--assets", type=Path, default=Path("data/assets"))
    parser.add_argument("--curves", type=Path, default=Path("data/curves"))
    parser.add_argument("--doc", type=Path, default=Path("docs/decisions.md"))
    args = parser.parse_args(argv)
    fig = args.doc.parent / "figures" / "decisions"
    fig.mkdir(parents=True, exist_ok=True)

    def save(name: str, svg: str) -> str:
        (fig / name).write_text(svg)
        return f"![{name}](figures/decisions/{name})"

    plants = pq.read_table(args.assets / "solar_tx.parquet").to_pylist()
    card = json.loads((args.assets / "solar_tx.card.json").read_text())
    cmp_ = card["assets"]["comparison"]
    md: list[str] = [
        "# Decisions and their effect",
        "",
        "What was chosen at each fork in the hail and asset work, what the alternatives were, and how much the choice moves "
        "the result. Orange marks the option in use. Every number and chart is computed by `python -m crc_lab.decisions` "
        f"from the built tables (plant table built {card['built_at'][:10]}). Texas solar plants are the running example; "
        "Fighting Jays in Fort Bend County, badly damaged by hail in March 2024, is the test case.",
        "",
    ]

    # 1. plant list
    con = duckdb.connect()
    md += [
        "## 1. Which plant list",
        "",
        "**Chosen: EIA's generator inventory (through PUDL), with the solar database (USPVDB) joined in for array polygons.** "
        "Alternative: the solar database alone, which was the first build.",
        "",
        save(
            "1-plant-list.svg",
            bars(
                "Texas solar capacity by list (MW AC)",
                [
                    ("EIA through PUDL", cmp_["eia"][1]),
                    ("Solar database (USPVDB)", cmp_["uspvdb"][1]),
                    ("In EIA only", sum(r[2] for r in cmp_["eia_only_by_first_year"])),
                ],
                "MW AC",
                highlight="EIA through PUDL",
            ),
        ),
        "",
        table(
            ["", "Plants", "MW AC"],
            [
                ["EIA through PUDL", cmp_["eia"][0], f"{cmp_['eia'][1]:,.0f}"],
                ["Solar database", cmp_["uspvdb"][0], f"{cmp_['uspvdb'][1]:,.0f}"],
                ["In both", cmp_["matched"][0], f"{cmp_['matched'][1]:,.0f}"],
            ],
        ),
        "",
        "Is the difference newer plants or corrections? Both, mostly newer:",
        "",
        save(
            "1-eia-only-by-year.svg",
            bars(
                "Plants in EIA only, by first year online",
                [(str(y), n) for y, n, _ in cmp_["eia_only_by_first_year"]],
                "plants",
            ),
        ),
        "",
        "- Older plants missing from the solar database: "
        + "; ".join(
            f"{n} ({c} County, {y}, {mw:g} MW)" for n, c, y, mw in cmp_["eia_only_before_2025"]
        )
        + ".",
        f"- Among matched plants, capacity differs by more than 5% for {cmp_['capacity_differs'][0]} of {cmp_['capacity_differs'][1]}; the first year differs for {cmp_['year_differs'][0]}, by more than one year for {cmp_['year_differs'][1]} "
        "("
        + "; ".join(f"{n}: EIA {a}, solar database {b}" for n, a, b in cmp_["year_examples"])
        + ").",
        "- In the solar database only: "
        + "; ".join(f"{n} ({mw:g} MW)" for _, n, _, mw in cmp_["uspvdb_only"])
        + ".",
        "",
    ]

    # 2. coordinates
    eia_tbl = eia.plants(args.cache)
    usp = solar.load(args.cache, solar.fetch(args.cache))
    con.register("e", eia_tbl)
    con.register("u", usp)
    dist = [
        r[0]
        for r in con.execute("""SELECT 111.2 * sqrt(pow(e.latitude - u.latitude, 2) + pow((e.longitude - u.longitude) * cos(radians(e.latitude)), 2))
                                         FROM e JOIN (SELECT eia_id, any_value(latitude) latitude, any_value(longitude) longitude FROM u GROUP BY 1) u USING (eia_id) WHERE e.latitude IS NOT NULL""").fetchall()
    ]
    bins = [(0, 0.5), (0.5, 1), (1, 2), (2, 5), (5, 10), (10, 1e9)]
    labels = ["under 0.5 km", "0.5–1 km", "1–2 km", "2–5 km", "5–10 km", "over 10 km"]
    src = {}
    for p in plants:
        src[p["location_source"]] = src.get(p["location_source"], 0) + 1
    md += [
        "## 2. Which coordinates",
        "",
        "**Chosen: the solar database's position where a plant has one (checked against imagery), EIA's otherwise.** "
        "The source used is stored per plant (`location_source`) and shown in the explorer panel.",
        "",
        save(
            "2-coordinates.svg",
            bars(
                "Distance between EIA's and the solar database's position, matched plants",
                [
                    (lab, sum(1 for d in dist if a <= d < b))
                    for lab, (a, b) in zip(labels, bins, strict=True)
                ],
                "plants",
            ),
        ),
        "",
        f"Median {statistics.median(dist):.2f} km; {sum(1 for d in dist if d > 5)} of {len(dist)} plants differ by more than 5 km, the largest by {max(dist):.0f} km. "
        "The hail circle is tens of kilometres wide, so most differences do not matter, but the largest do. "
        f"Positions in use: {', '.join(f'{v} from {k}' for k, v in src.items())}.",
        "",
    ]

    # 3-5: exposure steps
    win = card["hail_exposure"]["window"]
    rep_tx = exposure.load_reports(str(args.events), win[0], win[1])
    rep_all = exposure.load_reports(
        str(args.events), win[0], win[1], args.events.parent / "hail_neighbours.parquet"
    )
    tx = texas_boundary(args.cache).geometry
    region = exposure.reporting_region(args.cache / "cb_2024_us_state_500k.zip")
    rule = exposure.Rule()
    steps: list[tuple[str, list[float]]] = []
    fj: dict[str, float] = {}

    def run(
        label: str,
        reports: exposure.Reports,
        reg: object | None,
        use_area: bool,
        r: exposure.Rule = rule,
    ) -> list[float]:
        vals = []
        for p in plants:
            out = exposure.at_point(
                p["longitude"],
                p["latitude"],
                reports,
                r,
                region=reg,
                plant_area_km2=(p["area_m2"] or 0) / 1e6 if use_area else 0.0,
            )
            vals.append(out["annual_prob_ge_2in"])
            if "Fighting Jays" in p["name"]:
                fj[label] = out["annual_prob_ge_2in"]
        steps.append((label, vals))
        return vals

    run("First build: Texas reports, whole circle, plant as a point", rep_tx, None, False)
    run("+ circle clipped to Texas", rep_tx, tx, False)
    run("+ plant's own array area", rep_tx, tx, True)
    run("+ reports from four neighbouring states", rep_all, region, True)
    corr = [p["hail_annual_prob_ge_2in_corrected"] for p in plants]
    steps.append(("+ reporting-bias correction", corr))
    fj["+ reporting-bias correction"] = next(
        p["hail_annual_prob_ge_2in_corrected"] for p in plants if "Fighting Jays" in p["name"]
    )
    md += [
        "## 3. Borders, plant size and reporting bias: the steps so far",
        "",
        "Annual chance that hail of 2 inches or more hits a plant, across the plants, as each decision was added. "
        "**In use: the fourth line as the uncorrected figure and the fifth as the corrected one; both are kept in the plant table.**",
        "",
        save(
            "3-exposure-steps.svg",
            ranges(
                "Annual chance of hail 2 inches or more at a plant",
                [(lab, *[100 * x for x in q3(v)]) for lab, v in steps],
                "percent per year",
                highlight="+ reports from four neighbouring states",
                log=True,
            ),
        ),
        "",
        table(
            ["Step", "10th percentile", "Median", "90th percentile", "Fighting Jays"],
            [[lab, *[pct(x) for x in q3(v)], pct(fj.get(lab))] for lab, v in steps],
        ),
        "",
        "- **Clipping** matters only near Mexico and the Gulf: without it a border plant's reports are spread over land that can hold none.",
        "- **Plant area** is the largest geometric change: a plant of several km² is a much bigger target than a point.",
        "- **Neighbouring states** change plants near the state line; elsewhere nothing.",
        "- **Bias correction** multiplies the rate by one over the fitted reporting rate around the plant (median "
        f"{statistics.median([p['hail_reporting_rate'] for p in plants if p['hail_reporting_rate']]):.2f} across plants).",
        "",
    ]

    # 4. footprint
    radar_meta = json.loads(
        pq.read_schema(args.assets / "radar_plants.parquet").metadata[b"crc_lab.radar"]
    )
    foot = []
    for a in (20.0, 25.0, 50.0, 100.0):
        vals = [
            exposure.at_point(
                p["longitude"],
                p["latitude"],
                rep_all,
                exposure.Rule(footprint_km2=a),
                region=region,
                plant_area_km2=(p["area_m2"] or 0) / 1e6,
            )["annual_prob_ge_2in"]
            for p in plants
        ]
        foot.append((f"{a:g} km²" + (" (in use)" if a == 25 else ""), *[100 * x for x in q3(vals)]))
    md += [
        "## 4. Area of one hail event (the footprint)",
        "",
        "**Chosen: 25 km² per report (Yuri, 2026-11-10).** A report is a point; this is the ground assumed hit. "
        "Published hailstreaks are mostly 10–21 km²; published radar swaths of severe hail are most often 50–100 km².",
        "",
        save(
            "4-footprint.svg",
            ranges(
                "Annual chance of hail 2 inches or more, by footprint",
                foot,
                "percent per year",
                highlight="25 km² (in use)",
            ),
        ),
        "",
    ]
    hc = (
        json.loads((args.assets / "hail_compare.json").read_text())
        if (args.assets / "hail_compare.json").exists()
        else None
    )
    swath_note = (args.doc.parent / "reports" / "4-radar-hail.md").read_text()
    sw_rows = [
        ln for ln in swath_note.splitlines() if ln.startswith("| 30 mm") or ln.startswith("| 50 mm")
    ]
    if sw_rows:
        md += [
            "Measured from radar over Texas (connected areas at or above the threshold on one day, 2020–2025):",
            "",
            "| Threshold | Swaths | 25th percentile km² | Median km² | 75th percentile km² | 90th percentile km² | Mean km² |",
            "| --- | --- | --- | --- | --- | --- | --- |",
            *sw_rows,
            "",
            "25 km² lies between the measured median and mean.",
            "",
        ]

    # 5. N and radius
    nr = []
    for lab, r in (
        ("30 reports", exposure.Rule(n_target=30)),
        ("100 reports (in use)", rule),
        ("300 reports", exposure.Rule(n_target=300)),
        ("100, no minimum radius", exposure.Rule(min_radius_km=0.0)),
        ("100, minimum 25 km", exposure.Rule(min_radius_km=25.0)),
    ):
        vals = [
            exposure.at_point(
                p["longitude"],
                p["latitude"],
                rep_all,
                r,
                region=region,
                plant_area_km2=(p["area_m2"] or 0) / 1e6,
            )["annual_prob_ge_2in"]
            for p in plants
        ]
        nr.append((lab, *[100 * x for x in q3(vals)]))
    md += [
        "## 5. How many reports, and the smallest circle",
        "",
        "**Chosen: grow the circle to 100 reports, never under 10 km, never over 75 km.**",
        "",
        save(
            "5-n-and-radius.svg",
            ranges(
                "Annual chance of hail 2 inches or more, by circle rule",
                nr,
                "percent per year",
                highlight="100 reports (in use)",
            ),
        ),
        "",
        "The count and the minimum radius move the median plant little. They matter in cities, where 100 reports sit within a few kilometres.",
        "",
    ]

    # 6. bias correction against radar
    radar = {
        r["asset_id"]: r for r in pq.read_table(args.assets / "radar_plants.parquet").to_pylist()
    }
    r_un, r_co = [], []
    for p in plants:
        rd = radar[p["asset_id"]]["radar_local_rate_ge_30mm"]
        un = -math.log(1 - p["hail_annual_prob_ge_1in"])
        co = p["hail_annual_prob_ge_1in_corrected"]
        if un > 0:
            r_un.append(rd / un)
        if co not in (None, 1.0) and co > 0:
            r_co.append(rd / -math.log(1 - co))
    md += [
        "## 6. Correcting for where reports come from",
        "",
        "**Chosen: keep both. The fitted correction (population and roads) is applied as a second set of columns, never replacing the first.** "
        f"Radar ({radar_meta['first_day'][:4]}–{radar_meta['last_day'][:4]}) is the independent check: how many radar hail days (30 mm or more) per report-based hit (1 inch or more) at each plant. A ratio of 1 means agreement.",
        "",
        save(
            "6-bias-vs-radar.svg",
            ranges(
                "Radar hail days ÷ report-based hits, at the plants",
                [("Reports as they are", *q3(r_un)), ("Reports, bias-corrected", *q3(r_co))],
                "ratio",
                highlight="Reports, bias-corrected",
                fmt="{:.1f}",
            ),
        ),
        "",
        "Uncorrected reports sit well below radar at the median plant; corrected reports sit close to it, without the correction having been tuned to radar. "
        "Radar over-calls, so a ratio somewhat above 1 would also be reasonable.",
        "",
    ]

    # 7. radar threshold
    md += [
        "## 7. Radar threshold for a hail day",
        "",
        "**Chosen: 30 mm of radar hail size (MESH), stated wherever it is used; 50 mm is shown beside it.** "
        "30 mm is the best single discriminator of severe hail in the literature. Radar hail size is built to exceed most observed stones.",
        "",
        save(
            "7-radar-threshold.svg",
            ranges(
                "Radar hail days per year at a point (25 km average), across plants",
                [
                    (
                        "30 mm or more (in use)",
                        *q3([r["radar_local_rate_ge_30mm"] for r in radar.values()]),
                    ),
                    ("50 mm or more", *q3([r["radar_local_rate_ge_50mm"] for r in radar.values()])),
                ],
                "days per year",
                highlight="30 mm or more (in use)",
            ),
        ),
        "",
    ]

    # 8. sources compared per cell
    if hc:
        rows = [
            (s["title"] + f" ({s['period']})", *q3(s["values"])) for s in hc["sources"].values()
        ]
        md += [
            "## 8. Four hail records for the same cells",
            "",
            "Hail days per year in each Texas cell (about 253 km²), from each source. **No single source is chosen: they are shown side by side in the explorer.**",
            "",
            save(
                "8-sources.svg",
                ranges(
                    "Hail days per year per cell, by source", rows, "days per year", fmt="{:.2f}"
                ),
            ),
            "",
            "Reports need a person nearby; radar sees everywhere but over-calls; signatures come from single radars whose coverage and algorithm changed over the years.",
            "",
        ]
        yr = hc.get("signatures_per_year") or []
        if yr:
            md += [
                save(
                    "8-signatures-by-year.svg",
                    bars(
                        "Radar hail signatures of 1.25 inches or more in the Texas box, by year",
                        [(str(y["year"]), y["rows_ge_threshold"]) for y in yr],
                        "signatures",
                        fmt="{:,.0f}",
                    ),
                ),
                "",
                "The year-to-year swing in signatures is partly weather and partly the record itself (missing values before the late 1990s, algorithm and network changes). It is a reason to treat the long record with care.",
                "",
            ]

    # 9. phase 3 curves
    sens_path = args.curves / "sensitivity" / "results.json"
    if sens_path.exists():
        sens = json.loads(sens_path.read_text())
        idx = sens["return_periods"].index(100)
        rows = []
        for v in sens["variants"]:
            vals = [
                c[idx] for c in v["hazards"]["hail_size"]["cities"].values() if c[idx] is not None
            ]
            rows.append((v["name"] + (" (in use)" if v["name"] == "default" else ""), *q3(vals)))
        md += [
            "## 9. Hail curves per cell (Phase 3): pooling, window and family",
            "",
            "**Chosen: pool each cell with its six neighbours, window 1996–2025, Gumbel with a zero atom.** 1-in-100-year hail size at ten city centres under each alternative:",
            "",
            save(
                "9-curves.svg",
                ranges(
                    "1-in-100-year hail size at ten cities, by method",
                    rows,
                    "mm",
                    highlight="default (in use)",
                    fmt="{:.0f}",
                ),
            ),
            "",
            "Pooling is the choice that matters; the family and the start year move values by a few millimetres. Details in `reports/3-curves-sensitivity.md`.",
            "",
        ]

    md += [
        "## Other decisions, without a chart",
        "",
        "- **Several hail events in one year at one plant:** damage ratios are added and capped at 1 (2026-11-10).",
        "- **Cells:** every H3 resolution-5 cell that intersects Texas, not only those whose centre is inside.",
        "- **Curves in the browser:** evaluated by crc-sdk in Python at fixed return periods; the page never re-implements a curve.",
        "- **Replacement value:** AC capacity times one recent benchmark cost per kW for every plant, since replacement is today's cost.",
        "- **Storm Events source:** NCEI direct, not the Source Cooperative copy, which lags and stores local time without an offset.",
        "- **Curve data and code** stay in this repo, written so they can be offered to crc-sdk.",
        "",
    ]
    args.doc.write_text("\n".join(md))
    print(f"wrote {args.doc} with {len(list(fig.glob('*.svg')))} figures; Fighting Jays: {fj}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
