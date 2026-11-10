# ruff: noqa: E501  (long policy strings and SQL read better on one line)
"""C1: per H3 r5 cell and year, the largest reported hail size and strongest thunderstorm gust.

Years without a report are real zeros (the cell saw no report, which is not the same as no hail;
the data card says so). An event on a path or in a zone counts in every cell it touches.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pyarrow as pa

HAIL = "hail_size"
GUST = "thunderstorm_gust"
HAIL_UNIT = "mm"
GUST_UNIT = "m/s"
FIRST_FULL_YEAR = 1996  # all event types reported from 1996; hail and wind back to 1955 but sparser


@dataclass(frozen=True)
class Window:
    start: int
    end: int  # last complete year

    @property
    def years(self) -> list[int]:
        return list(range(self.start, self.end + 1))


def last_complete_year(events: str, con: duckdb.DuckDBPyConnection) -> int:
    """The year before the snapshot's last event month (the last year is partial)."""
    latest = con.execute(
        f"SELECT CAST(max(begin_utc) AT TIME ZONE 'UTC' AS VARCHAR) FROM read_parquet('{events}')"
    ).fetchone()[0]
    return int(latest[:4]) - 1


def annual_maxima(
    events: str, cells: set[int], window: Window, con: duckdb.DuckDBPyConnection | None = None
) -> pa.Table:
    """Columns: cell (uint64), year, hail_mm, gust_ms, hail_reports, gust_reports; zeros where none."""
    con = con or duckdb.connect()
    con.execute(
        "CREATE OR REPLACE TABLE cells AS SELECT * FROM (VALUES "
        + ",".join(f"({c}::UBIGINT)" for c in sorted(cells))
        + ") t(cell)"
    )
    con.execute(
        f"CREATE OR REPLACE TABLE years AS SELECT unnest(range({window.start}, {window.end + 1})) AS year"
    )
    con.execute(
        f"""CREATE OR REPLACE TABLE reports AS
        SELECT unnest(cells) AS cell, year, event_type, hail_size_mm, wind_ms
        FROM read_parquet('{events}')
        WHERE year BETWEEN {window.start} AND {window.end}
          AND event_type IN ('Hail', 'Thunderstorm Wind')"""
    )
    table = con.execute(
        """SELECT c.cell, y.year,
                  coalesce(max(r.hail_size_mm) FILTER (WHERE r.event_type = 'Hail'), 0.0)
                      AS hail_mm,
                  coalesce(max(r.wind_ms) FILTER (WHERE r.event_type = 'Thunderstorm Wind'), 0.0)
                      AS gust_ms,
                  count(r.hail_size_mm) FILTER (WHERE r.event_type = 'Hail') AS hail_reports,
                  count(r.wind_ms) FILTER (WHERE r.event_type = 'Thunderstorm Wind') AS gust_reports
           FROM cells c CROSS JOIN years y
           LEFT JOIN reports r ON r.cell = c.cell AND r.year = y.year
           GROUP BY 1, 2 ORDER BY 1, 2"""
    ).to_arrow_table()
    return table.cast(
        pa.schema(
            [
                ("cell", pa.uint64()),
                ("year", pa.int32()),
                ("hail_mm", pa.float64()),
                ("gust_ms", pa.float64()),
                ("hail_reports", pa.int32()),
                ("gust_reports", pa.int32()),
            ]
        )
    )


def summary(table: pa.Table) -> dict[str, object]:
    con = duckdb.connect()
    con.register("am", table)
    row = con.execute(
        """SELECT count(DISTINCT cell) n_cells, count(DISTINCT year) n_years,
                  count(*) FILTER (WHERE hail_mm > 0) hail_cell_years,
                  count(*) FILTER (WHERE gust_ms > 0) gust_cell_years,
                  count(DISTINCT cell) FILTER (WHERE hail_mm > 0) cells_with_any_hail,
                  count(DISTINCT cell) FILTER (WHERE gust_ms > 0) cells_with_any_gust,
                  max(hail_mm) max_hail_mm, max(gust_ms) max_gust_ms
           FROM am"""
    ).fetchone()
    keys = [
        "cells",
        "years",
        "hail_cell_years",
        "gust_cell_years",
        "cells_with_any_hail",
        "cells_with_any_gust",
        "max_hail_mm",
        "max_gust_ms",
    ]
    out = dict(zip(keys, row, strict=True))
    out["hail_zero_share"] = round(1 - out["hail_cell_years"] / (out["cells"] * out["years"]), 3)
    out["gust_zero_share"] = round(1 - out["gust_cell_years"] / (out["cells"] * out["years"]), 3)
    return out
