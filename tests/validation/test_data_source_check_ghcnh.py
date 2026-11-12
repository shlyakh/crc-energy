"""GHCNh assessment on constructed station files, offline.

The files are built to sit on every rule's boundary (17 against 18 hours, 328 against 329
days, 61.8 against 61.9 degrees, listed against unlisted source codes, a station that moves),
written in both of NOAA's formats and served to both sides through fake downloads.
"""

import builtins
import io
import math
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from data_source_check import build
from data_source_check.assessments import ghcnh as assessment
from data_source_check.core import inventory
from data_source_check.reference import ghcnh as reference

A, B = "USW00099901", "USW00099902"
YEARS = (2001, 2007)
VERSIONS = {"crc-sdk": "test"}


def reports(station: str, year: int) -> list[tuple]:
    """Hourly reports for one station-year with the edge cases placed by the year."""
    rows = []
    start = datetime(year, 1, 1)
    days = 366 if year % 4 == 0 else 365
    short = {2002: days - 329, 2003: days - 328}.get(year, 3)  # days left with 17 hours
    for d in range(days):
        # the short days lose the last seven UTC hours; they alternate with full days
        hours = 17 if (d % 2 == 0 and d < 2 * short) else 24
        for h in range(hours):
            t = start + timedelta(days=d, hours=h, minutes=51)
            value = 20.0 + 10 * math.sin(d / 58.0) + 5 * math.sin(h / 3.8)
            lat = 30.0 + (0.06 if station == B and d > 200 else 0.0)
            rows.append(
                (
                    station,
                    t.isoformat(),
                    lat,
                    -97.5,
                    204.2 if d % 7 else -999.9,
                    round(value, 1),
                    "5" if h % 2 else "",
                    "343",
                )
            )
    day = lambda d, h, m=10: (start + timedelta(days=d, hours=h, minutes=m)).isoformat()  # noqa: E731
    step = (year - 2001) * 0.7  # extremes differ by year, or no distribution can be fitted
    extra = [
        (61.8 - step, "", "343", 100),  # in 2001 the upper limit itself: accepted
        (61.9, "", "343", 100),  # just above it is not
        (-93.2 + step, " 1 ", "220", 101),  # code 1 from a listed source, with padding
        (-93.3, "1", "220", 101),  # below the lower limit
        (60.5, "A", "343", 102),  # a quality code that is not accepted
        (60.6, "5", "999", 102),  # code 5 from an unlisted source
        (60.7, "1", "999", 102),  # code 1 from an unlisted source
        (60.8, "5", "220", 102),  # code 5 from a source listed only for code 1
        (None, "", "343", 103),  # no temperature
        (float("inf"), "", "343", 103),  # not finite
        (61.0, "", "343", 0),  # the year's extreme on a day with 17 hours: ignored
        (-80.0, "", "343", 0),
    ]
    for value, quality, code, d in extra:
        rows.append((station, day(d, 5), 30.0, -97.5, 204.2, value, quality, code))
    rows.append((station, day(0, 3, 5), 30.0, -97.5, 204.2, 21.0, "", "343"))  # a second report
    rows.append((station, day(0, 3, 6), 30.0, -97.5, 204.2, 21.0, "", "343"))  # in the same hour
    if year == 2004:  # the year's maximum at 03:10 UTC on a full day that follows a short one:
        # counted on its UTC day; a day boundary six hours off would put it on the short day
        rows.append((station, day(1, 3), 30.0, -97.5, 204.2, 61.7, "", "343"))
    rows.append((station, "not a date", 30.0, -97.5, 204.2, 61.5, "", "343"))
    rows.append(("USW00000000", day(50, 5), 30.0, -97.5, 204.2, 61.5, "", "343"))  # another station
    rows.append((station, f"{year - 1}-12-31T23:59:00", 30.0, -97.5, 204.2, 61.5, "", "343"))
    return rows


@pytest.fixture(scope="module")
def bucket(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("bucket")
    for station in (A, B):
        for year in range(YEARS[0], YEARS[1] + 1):
            if year == 2005 or (station == B and year > 2002):
                continue  # NOAA has no file: 404
            rows = reports(station, year)
            table = pa.table(
                {name: [row[i] for row in rows] for i, name in enumerate(reference.COLUMNS)}
                | {"wind_speed": [1.0] * len(rows)}
            )
            pq.write_table(table, root / f"GHCNh_{station}_{year}.parquet")
            with (root / f"GHCNh_{station}_{year}.psv").open("w", encoding="utf-8") as out:
                out.write("|".join(("Station_name", *reference.COLUMNS, "wind_speed")) + "\n")
                for row in rows:
                    cells = ["" if v is None else str(v) for v in row]
                    out.write("|".join(("TEST AP", *cells, "1.0")) + "\n")
    return root


class Response(io.BytesIO):
    status = 200

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.headers = {"ETag": '"x"', "Last-Modified": "now", "Content-Length": str(len(data))}


@pytest.fixture
def served(bucket: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def local(address: str) -> Path:
        path = bucket / address.rsplit("/", 1)[-1]
        if not path.exists():
            raise HTTPError(address, 404, "Not Found", None, None)  # type: ignore[arg-type]
        return path

    def fake_urlopen(request, timeout=None):  # noqa: ANN001, ANN202
        return Response(local(request.full_url).read_bytes())

    class FakeFsspec:
        @staticmethod
        def open(address: str, mode: str = "rb", **_: object):  # noqa: ANN205
            return builtins.open(local(address), mode)

    monkeypatch.setattr("data_source_check.reference.ghcnh.urlopen", fake_urlopen)
    monkeypatch.setattr("crc_sdk.providers.ghcnh.urlopen", fake_urlopen)
    monkeypatch.setattr("crc_sdk.providers.ghcnh.fsspec", FakeFsspec)


def run(tmp_path: Path, rules: reference.Rules | None = None, live: bool = True) -> dict:
    return assessment.assess(
        tmp_path,
        tmp_path / "crc-sdk",
        live=live,
        versions=VERSIONS,
        rules=rules,
        stations=[A, B],
        years=YEARS,
        minimum_years=4,
        psv_sample=4,
    )


def outcomes(records: dict) -> dict[str, str]:
    return {check["check"]: check["outcome"] for check in records["checks"]}


def test_reference_rules_on_the_constructed_year(bucket: Path) -> None:
    row = reference.annual_row(reference.read_parquet(bucket / f"GHCNh_{A}_2001.parquet"), A, 2001)
    assert (row["value_max"], row["value_min"]) == (61.8, -93.2)  # the limits, nothing beyond
    assert row["valid_days"] == 362 and row["complete"] and row["elevation"] == 204.2
    assert row["excluded"] == {
        "no temperature": 1,
        "not a finite number": 1,
        "outside the physical range": 2,
        "quality code 1 from a source not accepted": 1,
        "quality code 5 from a source not accepted": 2,
        "quality code not accepted": 1,
    }
    same = reference.annual_row(reference.read_psv(bucket / f"GHCNh_{A}_2001.psv"), A, 2001)
    assert same == row  # NOAA's two formats give the same row
    edge = {
        y: reference.annual_row(reference.read_parquet(bucket / f"GHCNh_{A}_{y}.parquet"), A, y)
        for y in (2002, 2003)
    }
    assert (edge[2002]["valid_days"], edge[2002]["complete"]) == (329, True)
    assert (edge[2003]["valid_days"], edge[2003]["complete"]) == (328, False)
    moved = reference.annual_row(
        reference.read_parquet(bucket / f"GHCNh_{B}_2001.parquet"), B, 2001
    )
    assert moved["error"] == "invalid or moving coordinates"


def test_assessment_confirms_every_check_on_the_constructed_files(
    tmp_path: Path, served: None
) -> None:
    records = run(tmp_path)
    bad = [(c["check"], c["result"]) for c in records["checks"] if c["outcome"] != "confirmed"]
    assert not bad, bad
    assert len(records["checks"]) == 8
    annual = next(c for c in records["checks"] if c["check"] == "annual[temperature_max]")
    assert annual["result"]["stations_refused_reference"] == [B]
    assert annual["result"]["stations_refused_framework"] == [B]  # crc-sdk refuses it too
    assert annual["result"]["complete_years_reference"] == 5  # 2001, 2002, 2004, 2006, 2007
    curves = next(c for c in records["checks"] if c["check"] == "curve-stations[temperature_min]")
    assert curves["result"]["stations_with_a_curve"] == [A]
    assert records["exploration"]["station_years_with_a_file"] == 8


@pytest.mark.parametrize(
    "wrong",
    [
        {"hours_per_day": 17},
        {"day_fraction": 0.89},
        {"day_offset_hours": -6},
        {"highest": 62.0},
        {"lowest": -93.3},
        {"quality_codes": ("", "1", "5", "A")},
        {"sources_for_5": (*reference.Rules().sources_for_5, "999")},
        {"sources_for_1": (*reference.Rules().sources_for_1, "999")},
        {"missing_elevation": 0.0},
    ],
    ids=lambda wrong: next(iter(wrong)),
)
def test_a_wrong_reference_rule_ends_as_differs(
    tmp_path: Path, served: None, wrong: dict[str, object]
) -> None:
    """Each rule, broken on its own, must be caught by the comparison with crc-sdk."""
    got = outcomes(run(tmp_path, rules=replace(reference.Rules(), **wrong)))
    assert (
        got["annual[temperature_max]"] == "differs" or got["annual[temperature_min]"] == "differs"
    )


def test_a_wrong_coordinate_rule_ends_as_differs(tmp_path: Path, served: None) -> None:
    got = outcomes(run(tmp_path, rules=replace(reference.Rules(), coordinate_tolerance=0.1)))
    assert got["annual[temperature_max]"] == "differs"  # crc-sdk refuses a station we would keep


def test_a_second_run_from_the_caches_gives_the_same_records(tmp_path: Path, served: None) -> None:
    def stable(records: dict) -> list:
        return [{k: v for k, v in check.items() if k != "run_at"} for check in records["checks"]]

    first = run(tmp_path)
    second = run(tmp_path, live=False)
    for a, b in zip(stable(first), stable(second), strict=True):
        a["inputs"] = [{k: v for k, v in i.items() if k != "retrieved_at"} for i in a["inputs"]]
        b["inputs"] = [{k: v for k, v in i.items() if k != "retrieved_at"} for i in b["inputs"]]
        assert a == b
    assert first["exploration"]["stations"] == second["exploration"]["stations"]


def test_committed_records_match_the_inventory() -> None:
    source = next(s for s in inventory.load_sources("crc_sdk") if s.id == "ghcnh")
    records = build.load_records("ghcnh")
    assert records is not None
    assert sorted(source.assessed_options["recipe"]) == records["recipes_assessed"]
    steps = {step.id: step.outcome for step in build.with_outcomes(source, records).statement}
    assert set(steps.values()) == {"confirmed"}
    used = {step for check in records["checks"] for step in check["steps"]}
    assert used == set(steps)  # every step has a check and every check names a real step
