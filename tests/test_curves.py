"""Offline tests for the Phase 3 curve inputs: annual maxima, pooling, samples table."""

from __future__ import annotations

from pathlib import Path

import duckdb
import h3
import pyarrow as pa
import pyarrow.parquet as pq

from crc_lab.curves import annual_maxima as am_mod
from crc_lab.curves import fit


def _events(tmp_path: Path, cells: list[int]) -> str:
    """A tiny event table in the Phase 2 schema (only the columns the curves read)."""
    rows = [
        # year, type, hail mm, wind m/s, cells touched
        (1996, "Hail", 25.4, None, [cells[0]]),
        (1996, "Hail", 44.45, None, [cells[0], cells[1]]),  # a path across two cells
        (1997, "Thunderstorm Wind", None, 30.0, [cells[1]]),
        (1999, "Hail", 19.05, None, [cells[2]]),
        (1999, "Tornado", None, None, [cells[2]]),  # ignored
    ]
    table = pa.table(
        {
            "year": pa.array([r[0] for r in rows], pa.int32()),
            "event_type": [r[1] for r in rows],
            "hail_size_mm": pa.array([r[2] for r in rows], pa.float64()),
            "wind_ms": pa.array([r[3] for r in rows], pa.float64()),
            "cells": pa.array([r[4] for r in rows], pa.list_(pa.uint64())),
            "begin_utc": pa.array([f"{r[0]}-06-01T00:00:00+00:00" for r in rows], pa.string()).cast(
                pa.timestamp("s", tz="UTC")
            ),
        }
    )
    path = tmp_path / "events.parquet"
    pq.write_table(table, path)
    return str(path)


def test_annual_maxima_fills_zeros_and_takes_the_max(tmp_path: Path) -> None:
    centre = h3.latlng_to_cell(31.0, -99.0, 5)
    ring = h3.grid_disk(centre, 1)
    cells = [h3.str_to_int(c) for c in ring]
    events = _events(tmp_path, cells)
    window = am_mod.Window(1996, 1999)
    table = am_mod.annual_maxima(events, set(cells), window, duckdb.connect())
    assert table.num_rows == 7 * 4
    rows = {(r["cell"], r["year"]): r for r in table.to_pylist()}
    assert rows[(cells[0], 1996)]["hail_mm"] == 44.45
    assert rows[(cells[0], 1996)]["hail_reports"] == 2
    assert rows[(cells[1], 1996)]["hail_mm"] == 44.45
    assert rows[(cells[1], 1997)]["gust_ms"] == 30.0
    assert rows[(cells[2], 1999)]["hail_mm"] == 19.05
    assert rows[(cells[2], 1999)]["gust_ms"] == 0.0 and rows[(cells[2], 1999)]["gust_reports"] == 0
    assert rows[(cells[3], 1998)]["hail_mm"] == 0.0
    summary = am_mod.summary(table)
    assert summary["cells"] == 7 and summary["years"] == 4
    assert summary["hail_cell_years"] == 3 and summary["max_hail_mm"] == 44.45
    assert am_mod.last_complete_year(events, duckdb.connect()) == 1998


def test_pooling_unions_ring_samples(tmp_path: Path) -> None:
    centre = h3.latlng_to_cell(31.0, -99.0, 5)
    ring = h3.grid_disk(centre, 1)
    cells = [h3.str_to_int(c) for c in ring]
    events = _events(tmp_path, cells)
    window = am_mod.Window(1996, 1999)
    table = am_mod.annual_maxima(events, set(cells), window, duckdb.connect())
    centre_int = h3.str_to_int(centre)
    k0 = fit.pooled_samples(table, "hail_mm", [centre_int], window, 0)[0]
    k1 = fit.pooled_samples(table, "hail_mm", [centre_int], window, 1)[0]
    assert len(k0) == 4 and len(k1) == 7 * 4
    assert sorted(k1)[-2:] == [44.45, 44.45]
    assert sum(1 for v in k1 if v > 0) == 3  # three non-zero hail cell-years in the ring
    samples = fit.samples_table(table, fit.HAIL, window, 1, 1999)
    assert samples.num_rows == 7
    assert samples.schema.field("cell").type == pa.uint64()
    assert set(samples["hazard"].to_pylist()) == {fit.HAIL}
    assert set(samples["horizon"].to_pylist()) == {1999}


def test_variant_label_and_hazard_specs() -> None:
    assert fit.Variant().label == "k1-from1996-gumbel_r"
    assert set(fit.HAZARDS) == {"hail_size", "thunderstorm_gust"}
    assert fit.HAZARDS["hail_size"]["unit"] == "mm"
    assert fit.HAZARDS["thunderstorm_gust"]["unit"] == "m/s"
