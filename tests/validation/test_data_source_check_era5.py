"""ERA5 assessment on a small constructed Zarr store, offline.

The store is built to sit on every rule's boundary: a cell with 36 and one with 37 days
missing (the 90 per cent line in a 365-day and a 366-day year), a rain day with one hour
missing that would be the wettest, temperature days with 17 and with 18 hours that hold the
year's extremes, land mask values of 0.5 and 0.49, a box whose north edge selects a row only
through the half-cell margin, and a time axis that ends at 23:00 on 31 December, as the
WeatherBench2 store's does. It is served to the reference reader through a fake download and
to crc-sdk as its own store.

Two small objects cut from the publisher's store (its last time chunk and its latitudes,
downloaded 2026-11-12 from gs://weatherbench2/datasets/era5/
1959-2022-1h-240x121_equiangular_with_poles_conservative.zarr, keys ``time/7`` and
``latitude/0``) test the decoder on real bytes.
"""

import io
import json
import shutil
import struct
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError

import numcodecs
import numpy as np
import pytest
import zarr

from data_source_check.assessments import era5 as assessment
from data_source_check.core import inventory
from data_source_check.reference import era5 as reference

FIXTURES = Path(__file__).parent / "fixtures"
VERSIONS = {"crc-sdk": "test"}
STORE = "wb2-1p5"
LAT = np.array([27.0, 28.5, 30.0, 31.5, 33.0])
LON = np.array([255.0, 256.5, 258.0, 259.5, 261.0, 262.5, 264.0])  # -105 ... -96
BOUNDS = (-102.0, 28.5, -99.0, 31.0)  # 31.5 is selected only through the half-cell margin
FIRST, STOP = np.datetime64("2019-01-01T00", "h"), np.datetime64("2022-01-01T00", "h")
ORIGIN = np.datetime64("1959-01-01T00", "h")
ASKED, COMPARED = (2018, 2019, 2020, 2021), (2020, 2021)
ALL_RECIPES = ("txx", "tnn", "rx1day", "rx5day")
# positions (longitude, latitude) in the arrays of four cells of the box
ON_LINE, UNDER_LINE, SHORT_DAY, EDGE_DAY = (2, 1), (3, 1), (4, 2), (2, 3)


def _hour(year: int, day: int, hour: int = 0) -> int:
    start = np.datetime64(f"{year}-01-01T00", "h")
    return int((start - FIRST) / np.timedelta64(1, "h")) + day * 24 + hour


def build_store(path: Path) -> None:
    hours = np.arange(FIRST, STOP, dtype="datetime64[h]")
    rng = np.random.default_rng(11)
    shape = (len(hours), len(LON), len(LAT))
    codec = numcodecs.Blosc(cname="lz4", clevel=5, shuffle=1)
    group = zarr.open_group(str(path), mode="w", zarr_format=2)

    def add(name: str, data: np.ndarray, dims: list[str], chunks: tuple, **attrs: str) -> None:
        fill = None if data.dtype.kind == "i" else np.nan
        array = group.create_array(name, data=data, chunks=chunks, compressors=codec,
                                   fill_value=fill)  # fmt: skip
        array.attrs.update({"_ARRAY_DIMENSIONS": dims, **attrs})

    add("time", (hours - ORIGIN).astype("<i8"), ["time"], (10000,),
        units="hours since 1959-01-01", calendar="proleptic_gregorian")  # fmt: skip
    add("latitude", LAT, ["latitude"], (len(LAT),))
    add("longitude", LON, ["longitude"], (len(LON),))

    rain = (rng.gamma(0.3, 0.002, shape)).astype("<f4")
    heat = (280 + 15 * rng.random(shape)).astype("<f4")
    for year in COMPARED:
        # 36 missing days leave a cell exactly on the 90 per cent line, 37 put it under.
        for cell, days in ((ON_LINE, 36), (UNDER_LINE, 37)):
            heat[_hour(year, 40) : _hour(year, 40 + days), cell[0], cell[1]] = np.nan
            # rain is stamped at the end of its hour: the same days, one hour later
            rain[_hour(year, 40, 1) : _hour(year, 40 + days, 1), cell[0], cell[1]] = np.nan
        # the wettest day by far, but one of its 24 hours is missing
        rain[_hour(year, 200, 1) : _hour(year, 201, 1), SHORT_DAY[0], SHORT_DAY[1]] = 0.05
        rain[_hour(year, 200, 7), SHORT_DAY[0], SHORT_DAY[1]] = np.nan
        # a day of 17 hours holding the year's extremes: not a day
        heat[_hour(year, 150, 0) : _hour(year, 150, 7), SHORT_DAY[0], SHORT_DAY[1]] = np.nan
        heat[_hour(year, 150, 12), SHORT_DAY[0], SHORT_DAY[1]] = 330.0
        heat[_hour(year, 150, 13), SHORT_DAY[0], SHORT_DAY[1]] = 230.0
        # a day of 18 hours holding the year's extremes: a day
        heat[_hour(year, 160, 0) : _hour(year, 160, 6), EDGE_DAY[0], EDGE_DAY[1]] = np.nan
        heat[_hour(year, 160, 12), EDGE_DAY[0], EDGE_DAY[1]] = 325.0
        heat[_hour(year, 160, 13), EDGE_DAY[0], EDGE_DAY[1]] = 235.0
    dims = ["time", "longitude", "latitude"]
    add("2m_temperature", heat, dims, (240, len(LON), len(LAT)), units="K")
    add("total_precipitation", rain, dims, (240, len(LON), len(LAT)), units="m")
    mask = np.ones((len(LON), len(LAT)), dtype="<f4")
    mask[2, 2], mask[3, 2], mask[4, 3] = 0.5, 0.49, 0.0
    add("land_sea_mask", mask, ["longitude", "latitude"], mask.shape, units="(0 - 1)")


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("era5") / "store.zarr"
    build_store(path)
    return path


class Response(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.headers = {"ETag": '"x"', "Last-Modified": "now", "Content-Length": str(len(data))}

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def serve(monkeypatch: pytest.MonkeyPatch, folder: Path) -> None:
    """Both sides read ``folder``: the reference by download, crc-sdk as its own store."""
    from crc_sdk.providers import era5 as provider

    def fake_urlopen(request, timeout=None):  # noqa: ANN001, ANN202
        path = folder / request.full_url.split(".zarr/", 1)[1]
        if not path.is_file():
            raise HTTPError(request.full_url, 404, "Not Found", None, None)  # type: ignore[arg-type]
        return Response(path.read_bytes())

    monkeypatch.setattr("data_source_check.reference.era5.urlopen", fake_urlopen)
    monkeypatch.setitem(provider.ERA5_STORES, STORE,
                        replace(provider.ERA5_STORES[STORE], url=str(folder),
                                storage_options={}))  # fmt: skip


@pytest.fixture
def served(store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    serve(monkeypatch, store)


def run(cache: Path, rules: reference.Rules | None = None, live: bool = True,
        recipes: tuple[str, ...] = ALL_RECIPES) -> dict:  # fmt: skip
    return assessment.assess(cache, live=live, versions=VERSIONS, rules=rules, bounds=BOUNDS,
                             recipes=recipes, years_asked=ASKED, years_compared=COMPARED,
                             probe_years=range(2015, 2025), sample_chunks=1)  # fmt: skip


def outcomes(records: dict) -> dict[str, str]:
    return {check["check"]: check["outcome"] for check in records["checks"]}


def check(records: dict, name: str) -> dict:
    return next(c for c in records["checks"] if c["check"] == name)


@pytest.mark.parametrize("typesize", [4, 8])
@pytest.mark.parametrize("shuffle", [0, 1])
@pytest.mark.parametrize("kind", ["smooth", "noise", "constant", "short"])
def test_the_plain_python_decoder_agrees_with_c_blosc(typesize: int, shuffle: int,
                                                      kind: str) -> None:  # fmt: skip
    rng = np.random.default_rng(3)
    count = 40 if kind == "short" else 200_000
    values = {
        "smooth": np.cumsum(rng.normal(size=count)),
        "noise": rng.random(count) * 1e30,
        "constant": np.full(count, 7.5),
        "short": rng.random(count),
    }[kind].astype(f"<f{typesize}")
    packed = numcodecs.Blosc(cname="lz4", clevel=5, shuffle=shuffle).encode(values)
    assert reference.blosc_decode(bytes(packed)) == values.tobytes()


def test_the_decoder_reads_objects_cut_from_the_publishers_store() -> None:
    time = reference.blosc_decode((FIXTURES / "era5_wb2_time_7.bin").read_bytes())
    hours = struct.unpack(f"<{len(time) // 8}q", time)
    assert len(hours) == 69033 and hours[-1] == 552263  # 2021-12-31T23, counted from 1959
    assert datetime(1959, 1, 1).toordinal() * 24 + hours[-1] == (
        datetime(2021, 12, 31).toordinal() * 24 + 23
    )
    lat = struct.unpack("<121d", reference.blosc_decode(
        (FIXTURES / "era5_wb2_latitude_0.bin").read_bytes()))  # fmt: skip
    assert lat[0] == -90.0 and lat[-1] == 90.0 and lat[60] == pytest.approx(0.0, abs=1e-9)


def test_reference_rules_on_small_series() -> None:
    rules = reference.Rules()
    hot = [1.0] * 17 + [None] * 7
    assert reference.daily_value(hot, "txx", rules) is None  # 17 of 24 hours
    assert reference.daily_value([1.0] * 18 + [None] * 6, "txx", rules) == 1.0
    assert reference.daily_value([1.0] * 23 + [None], "rx1day", rules) is None  # needs all 24
    assert reference.daily_value([0.5] * 24, "rx1day", rules) == 12.0
    year = [1.0] * 329 + [None] * 36
    assert reference.annual_value(year, "rx1day", rules) == 1.0
    assert reference.annual_value([1.0] * 328 + [None] * 37, "rx1day", rules) is None
    days = [1.0, None, 1.0, 1.0, 1.0, 1.0, 1.0, 9.0, 1.0, 1.0]
    assert reference.annual_value(days, "rx5day", rules) == 13.0  # no window crosses the gap
    assert reference.annual_value([0.1] * 10, "rx1day", rules) == reference.to_float32(0.1)
    assert reference.annual_value([0.1] * 10, "rx1day", replace(rules, float32_output=False)) == 0.1


def test_assessment_on_the_constructed_store(tmp_path: Path, served: None) -> None:
    records = run(tmp_path)
    got = outcomes(records)
    # the test store is a local folder, so its address is the one thing that must differ
    assert got.pop(f"store[{STORE}]") == "differs"
    assert list(check(records, f"store[{STORE}]")["result"]["differences"]) == ["address"]
    # like the publisher's store, this one ends before the years crc-sdk accepts
    assert got.pop(f"coverage[{STORE}]") == "differs"
    coverage = check(records, f"coverage[{STORE}]")["result"]
    assert coverage["complete_on_the_time_axis"] == {"rain": [2019, 2020],
                                                     "temperature": [2019, 2021]}  # fmt: skip
    assert coverage["accepted_by_crc_sdk"] == {"rain": [2015, 2021], "temperature": [2015, 2022]}
    assert coverage["year_beyond"] == {"year": 2022, "hours_of_that_year_on_the_time_axis": 0,
                                       "crc_sdk_error": "", "rows_for_that_year": 0}  # fmt: skip
    bad = [(c["check"], c["summary"]) for c in records["checks"]
           if c["outcome"] != "confirmed" and c["check"] in got]  # fmt: skip
    assert not bad, bad
    assert len(got) == 3 + 2 * len(ALL_RECIPES)
    every = check(records, "annual[rx1day 2020-2021 all cells]")["result"]
    # 9 cells in the box. The cell under the 90 per cent line has no value in either year;
    # in 2021 the cell on the line loses 31 December as well and falls under it.
    assert every["cells_in_box"] == 9 and every["rows_reference"] == 8 + 7
    heat = check(records, "annual[txx 2020-2021 all cells]")["result"]
    assert heat["rows_reference"] == 8 + 8
    assert every["rows_for_years_not_in_the_copy"] == 0
    land = check(records, "annual[txx 2020-2021 land only]")["result"]
    assert land["rows_reference"] == 2 * 6  # the cells with mask 0.49 and 0 are also left out
    last = next(c for c in records["exploration"]["cases"] if c["case"] == "rx1day 2021 all cells")
    assert (last["hours_expected"], last["hours_on_the_time_axis"]) == (8760, 8759)
    assert last["days_valid_highest"] == 364  # 31 December lacks the hour stamped 00:00


@pytest.mark.parametrize(
    ("wrong", "recipe", "variant"),
    [
        ({"kelvin_offset": -273.0}, "txx", "all cells"),
        ({"metres_to_mm": 999.0}, "rx1day", "all cells"),
        ({"interval_end_stamps": False}, "rx1day", "all cells"),
        ({"day_fraction_temperature": 0.7}, "txx", "all cells"),
        ({"day_fraction_temperature": 0.8}, "tnn", "all cells"),
        ({"day_fraction_rain": 0.95}, "rx1day", "all cells"),
        ({"year_fraction": 0.89}, "rx5day", "all cells"),
        ({"year_fraction": 0.91}, "txx", "all cells"),
        ({"window_days": 4}, "rx5day", "all cells"),
        ({"half_cell_margin": False}, "tnn", "all cells"),
        ({"land_threshold": 0.51}, "rx1day", "land only"),
        ({"float32_output": False}, "rx5day", "all cells"),
    ],
    ids=lambda value: "-".join(f"{k}={v}" for k, v in value.items())
    if isinstance(value, dict) else str(value).replace(" ", "-"),
)  # fmt: skip
def test_a_wrong_reference_rule_ends_as_differs_fault(
    tmp_path: Path, served: None, wrong: dict[str, object], recipe: str, variant: str
) -> None:
    rules = replace(reference.Rules(), **wrong)
    got = outcomes(run(tmp_path, rules=rules, recipes=(recipe,)))
    assert got[f"annual[{recipe} 2020-2021 {variant}]"] == "differs"


def test_a_chunk_that_does_not_decode_alike_ends_as_differs_fault(
    tmp_path: Path, served: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    decode = reference.blosc_decode

    def off_by_one_bit(chunk: bytes) -> bytes:
        plain = bytearray(decode(chunk))
        if len(plain) > 4000:  # the data chunks, not the axes
            plain[100] ^= 1
        return bytes(plain)

    monkeypatch.setattr(reference, "blosc_decode", off_by_one_bit)
    got = outcomes(run(tmp_path, recipes=("rx1day",)))
    assert got["hours[total_precipitation]"] == "differs"
    assert got["hours[2m_temperature]"] == "differs"


def test_a_unit_the_conversion_does_not_assume_is_not_noticed_by_crc_sdk(
    tmp_path: Path, store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CRC-006-ERA5 on a constructed store: temperature declared in degrees Celsius."""
    other = tmp_path / "store.zarr"
    shutil.copytree(store, other)
    attrs = other / "2m_temperature" / ".zattrs"
    attrs.write_text(json.dumps(json.loads(attrs.read_text()) | {"units": "degC"}))
    serve(monkeypatch, other)
    records = run(tmp_path / "cache", recipes=("txx",))
    declared = check(records, f"units-declared[{STORE}]")
    assert declared["outcome"] == "differs"
    assert declared["result"]["declared_in_the_store"]["2m_temperature"] == "degC"
    annual = check(records, "annual[txx 2020-2021 all cells]")
    # crc-sdk raises nothing and subtracts 273.15 all the same, as the reference rule does
    assert annual["outcome"] == "confirmed" and annual["result"]["crc_sdk_error"] == ""
    assert max(c["highest"] for c in records["exploration"]["cases"]) < 60.0


def test_a_second_run_from_the_stored_answers_gives_the_same_records(
    tmp_path: Path, served: None
) -> None:
    def stable(records: dict) -> list:
        return [{k: v for k, v in c.items() if k != "run_at"} for c in records["checks"]]

    first = run(tmp_path, recipes=("rx1day", "tnn"))
    assert stable(first) == stable(run(tmp_path, live=False, recipes=("rx1day", "tnn")))


def test_checks_name_only_steps_of_the_statement(tmp_path: Path, served: None) -> None:
    source = next(s for s in inventory.load_sources("crc_sdk") if s.id == "era5")
    steps = {step.id for step in source.statement}
    used = {step for c in run(tmp_path, recipes=("rx1day", "txx"))["checks"] for step in c["steps"]}
    assert used <= steps
    assert source.drafted_by and not source.reviewed_by
    assert source.status["verification"] == "in progress"
