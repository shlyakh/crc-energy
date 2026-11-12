"""NOAA extreme water levels assessment on fixed copies of NOAA's responses, offline.

The fixture holds NOAA's responses for two stations with the product and one without,
byte for byte (retrieved 2026-11-12), and NOAA's list of stations cut down to those two.
Both sides download through a fake ``urlopen`` that serves them, so the whole path runs:
reference download and parse, crc-sdk snapshot and tables, comparison, records.
Where a rule never fires on NOAA's data, the responses are altered by hand in the test.
"""

import copy
import io
import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from data_source_check.assessments import noaa_water_levels as assessment
from data_source_check.core import compare, inventory
from data_source_check.reference import noaa_water_levels as reference

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "noaa_water_levels_sample.json").read_text("utf-8")
)
VERSIONS = {"crc-sdk": "test"}
WITH, OTHER, WITHOUT = "8771450", "1611400", "8770475"
VALUE_CHECKS = {"levels", "annuals", "info"}


class Response(io.BytesIO):
    status = 200
    headers: dict[str, str] = {}


def serve(responses: dict[str, str]) -> Callable[..., Response]:
    def fake_urlopen(request, timeout=None):  # noqa: ANN001, ANN202
        address = request.full_url
        query = parse_qs(urlsplit(address).query)
        assert address.startswith(FIXTURE["endpoint"] + "?name=extremewaterlevels")
        if "station" not in query:
            return Response(responses["index"].encode())
        resource = (
            "levels" if "details" in query else "annuals" if "extremeType" in query else "station"
        )
        key = f"{query['station'][0]}/{resource}"
        if key not in responses:
            raise HTTPError(address, 404, "Not Found", None, None)  # type: ignore[arg-type]
        return Response(responses[key].encode())

    return fake_urlopen


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """The responses both sides are served; a test may alter them before running."""
    responses = copy.deepcopy(FIXTURE["responses"])
    fake = serve(responses)
    monkeypatch.setattr("data_source_check.reference.noaa_water_levels.urlopen", fake)
    monkeypatch.setattr("crc_sdk.workflows.noaa_water_levels.urlopen", fake)
    return responses


def alter(responses: dict[str, str], key: str, change: Callable[[dict], None]) -> None:
    payload = json.loads(responses[key])
    change(payload)
    responses[key] = json.dumps(payload, indent=2)


def run(tmp_path: Path, *, live: bool = True, **more: object) -> dict:
    return assessment.assess(tmp_path, live=live, versions=VERSIONS, **more)  # type: ignore[arg-type]


def outcomes(records: dict) -> dict[str, str]:
    return {check["check"]: check["outcome"] for check in records["checks"]}


def result(records: dict, name: str) -> dict:
    return next(c for c in records["checks"] if c["check"] == name)["result"]


def payloads(station: str) -> dict:
    return {
        name: json.loads(FIXTURE["responses"][f"{station}/{name}"], parse_float=Decimal)
        for name in reference.RESOURCES
    }


def test_reference_reader_applies_the_rules() -> None:
    with_product, without = payloads(WITH), payloads(WITHOUT)
    assert reference.refusal(with_product, WITH) is None
    assert reference.refusal(without, WITHOUT) == "station: not exactly one station listed"
    levels = reference.level_rows(with_product, WITH)
    assert len(levels) == 22 and all(len(row) == len(reference.LEVEL_COLUMNS) for row in levels)
    assert levels[0] == [
        WITH,
        "Galveston Pier 21",
        Decimal("-94.793297"),
        Decimal("29.309999"),
        "MHHW",
        "1997-2001",
        Decimal("0.99"),
        Decimal("1.01"),
        Decimal("0.33"),
        Decimal("0.31"),
        Decimal("0.35"),
    ]
    annuals = reference.annual_rows(with_product, WITH)
    assert len(annuals) == 118 and annuals[0][:4] == [WITH, 1908, Decimal("0.696"), "mhhw"]
    assert reference.url(WITH, "levels").endswith(
        "?name=extremewaterlevels&station=8771450&units=metric"
        "&details=exceedancelevels&levelType=high"
    )
    assert reference.valid_station_id(WITH) and not reference.valid_station_id("877145")
    assert assessment.canon([2.0, Decimal("2.0"), 2, 0.1, None, "a"]) == [
        "2",
        "2",
        "2",
        "0.1",
        None,
        "a",
    ]


def test_assessment_confirms_every_check_on_the_fixture(tmp_path: Path, served: dict) -> None:
    records = run(tmp_path)
    got = outcomes(records)
    assert set(got.values()) == {"confirmed"} and len(got) == 11
    assert records["sample"]["texas"] == [WITH] and records["sample"]["elsewhere"] == [OTHER]
    assert records["sample"]["not_listed"] == [WITHOUT]
    acceptance = result(records, "acceptance")
    assert acceptance["delivered_by_both"] == 2 and acceptance["refused_by_both"] == 1
    assert acceptance["refused"][WITHOUT]["responses_cached_by_framework"] == 0
    assert result(records, "bytes")["responses_compared"] == 6
    levels, annuals = result(records, "levels"), result(records, "annuals")
    assert levels["rows_reference"] == levels["rows_framework"] == 44
    assert levels["values_compared"] == 44 * 11
    assert annuals["rows_reference"] == 118 + len(payloads(OTHER)["annuals"]["extremes"])
    assert annuals["values_compared"] == annuals["rows_reference"] * 6
    assert result(records, "requests")["addresses_compared"] == 3 * 3 + 2 * 3
    explored = records["exploration"]["stations"]
    assert sorted(explored) == [OTHER, WITH] and explored[WITH]["years"] == 118
    assert all(check["summary"] for check in records["checks"])
    assert records["chart"]["default"] == "8771450 Galveston Pier 21"


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ({"station_id_digits": 8}, {"station-id"}),
        ({"units": "english"}, {"requests"}),
        ({"level_type": "low"}, {"requests"}),
        ({"required_units": "feet"}, {"acceptance"}),
        ({"level_group": "GEV_LO"}, {"acceptance"}),
        ({"datum_labels_ignore_case": False}, {"acceptance"}),
        ({"bounds": ("upper90CI", "lower90CI")}, {"acceptance"}),
        ({"bounds": ("lower90CI", "level")}, {"levels", "second-download"}),
        ({"levels_datum_from": "annuals"}, {"levels", "second-download"}),
        ({"annuals_datum_from": "levels"}, {"annuals", "second-download"}),
        ({"epoch_field": "epochMidyear"}, {"levels", "annuals", "second-download"}),
    ],
)
def test_fault_in_a_reference_rule_ends_as_differs(
    tmp_path: Path, served: dict, rule: dict, expected: set[str]
) -> None:
    """A check that cannot fail proves nothing: break one rule and the comparison must differ."""
    got = outcomes(run(tmp_path, rules=reference.Rules(**rule)))
    assert {name for name, value in got.items() if value == "differs"} == expected


def _no_levels(payload: dict) -> None:
    payload["GEV_HI"] = None


def _bound_above(payload: dict) -> None:
    payload["GEV_HI"]["exceedanceLevels"][3]["lower90CI"] = 9.0


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        (_no_levels, {"refuse_without_levels": False}),
        (_bound_above, {"bounds_must_bracket": False}),
    ],
)
def test_fault_in_a_refusal_rule_ends_as_differs_on_constructed_responses(
    tmp_path: Path, served: dict, change: Callable[[dict], None], rule: dict
) -> None:
    alter(served, f"{OTHER}/levels", change)
    assert outcomes(run(tmp_path / "right"))["acceptance"] == "confirmed"
    wrong = run(tmp_path / "wrong", rules=reference.Rules(**rule))
    assert outcomes(wrong)["acceptance"] == "differs"
    assert result(wrong, "acceptance")["disagreements"] == [OTHER]


def _set(path: list, value: object) -> Callable[[dict], None]:
    def change(payload: dict) -> None:
        target = payload
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return change


def _two_stations(payload: dict) -> None:
    payload["ExtremeWaterLevels"] *= 2


def _repeat_probability(payload: dict) -> None:
    rows = payload["GEV_HI"]["exceedanceLevels"]
    rows[1]["probability"] = rows[0]["probability"]


LEVEL = ["GEV_HI", "exceedanceLevels", 2]
REFUSED = [
    ("station", _two_stations),
    ("station", _set(["ExtremeWaterLevels", 0, "stationId"], "1611401")),
    ("station", _set(["ExtremeWaterLevels", 0, "longitude"], 180.5)),
    ("station", _set(["ExtremeWaterLevels", 0, "latitude"], None)),
    ("station", _set(["ExtremeWaterLevels", 0, "epoch"], "")),
    ("levels", _set(["stationId"], "1611401")),
    ("levels", _set(["units"], "feet")),
    ("levels", _set(["datum"], "")),
    ("levels", _no_levels),
    ("levels", _set([*LEVEL, "probability"], 0)),
    ("levels", _set([*LEVEL, "probability"], 1.5)),
    ("levels", _repeat_probability),
    ("levels", _set([*LEVEL, "returnPeriod"], 0.5)),
    ("levels", _set([*LEVEL, "level"], None)),
    ("levels", _set([*LEVEL, "lower90CI"], 9.0)),
    ("levels", _set([*LEVEL, "upper90CI"], -9.0)),
    ("levels", _set([*LEVEL, "upper90CI"], "high")),
    ("annuals", _set(["units"], "feet")),
    ("annuals", _set(["datum"], "NAVD88")),
    ("annuals", _set(["notice"], "")),
    ("annuals", _set(["trend"], "rising")),
    ("annuals", _set(["extremes", 0, "year"], "1955")),
    ("annuals", _set(["extremes", 0, "year"], 1955.5)),
    ("annuals", _set(["extremes", 0, "value"], None)),
]


@pytest.mark.parametrize(("resource", "change"), REFUSED)
def test_constructed_responses_are_refused_by_both_sides(
    tmp_path: Path, served: dict, resource: str, change: Callable[[dict], None]
) -> None:
    """The refusal rules that never fire on NOAA's data, each on a response altered by hand."""
    alter(served, f"{OTHER}/{resource}", change)
    records = run(tmp_path)
    acceptance = result(records, "acceptance")
    assert outcomes(records)["acceptance"] == "confirmed"
    assert acceptance["refused"][OTHER]["reference"] and acceptance["refused"][OTHER]["framework"]
    assert acceptance["delivered_by_both"] == 1 and acceptance["refused_by_both"] == 2
    assert "differs" not in outcomes(records).values()


def test_constructed_oddities_are_delivered_alike(tmp_path: Path, served: dict) -> None:
    """A missing bound, a whole number, an equal bound and a gap in the years change nothing."""

    def odd_levels(payload: dict) -> None:
        rows = payload["GEV_HI"]["exceedanceLevels"]
        del rows[0]["lower90CI"]
        rows[1]["upper90CI"] = None
        rows[2]["level"] = rows[2]["upper90CI"] = 1
        rows[3]["probability"] = 1

    def odd_annuals(payload: dict) -> None:
        del payload["extremes"][5:9]
        payload["trend"] = None
        payload["datum"] = payload["datum"].upper()

    alter(served, f"{OTHER}/levels", odd_levels)
    alter(served, f"{OTHER}/annuals", odd_annuals)
    records = run(tmp_path)
    assert set(outcomes(records).values()) == {"confirmed"}
    assert result(records, "acceptance")["delivered_by_both"] == 2
    explored = records["exploration"]["stations"][OTHER]
    assert explored["levels_without_a_bound"] == 2 and explored["years_missing_between"] == 4


def test_a_response_the_publisher_does_not_serve_is_recorded_not_raised(
    tmp_path: Path, served: dict
) -> None:
    del served[f"{WITHOUT}/levels"]
    records = run(tmp_path)
    assert result(records, "acceptance")["reference_could_not_read"] == {
        WITHOUT: {"station": 200, "levels": 404, "annuals": 200}
    }
    assert result(records, "acceptance")["stations"] == 2


def test_a_changed_response_ends_as_differs(tmp_path: Path, served: dict) -> None:
    run(tmp_path)
    cached = tmp_path / "reference" / WITH / "levels.json"
    cached.write_text(cached.read_text("utf-8").replace('"level": 0.33', '"level": 0.34'), "utf-8")
    sidecar = tmp_path / "reference" / WITH / "levels.meta.json"
    record = json.loads(sidecar.read_text())
    sidecar.write_text(json.dumps(record | {"sha256": reference.sha256(cached)}))
    again = run(tmp_path, live=False)
    got = outcomes(again)
    assert {name for name, value in got.items() if value == "differs"} == {
        "bytes",
        "second-download",
    }
    second = result(again, "second-download")
    assert second["values_differing"] == 1 and second["stations_with_a_difference"] == [WITH]
    assert second["largest_difference_between_numbers"] == "0.01"
    assert second["examples"][0] == {
        "station": WITH,
        "table": "levels",
        "row": 0,
        "position": 8,
        "reference": "0.34",
        "framework": "0.33",
    }


def test_another_answer_to_the_framework_differs_only_where_the_two_downloads_meet(
    tmp_path: Path, served: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NOAA answering the two sides differently is not laid at the door of the tables."""
    rounded = copy.deepcopy(served)

    def one_decimal(payload: dict) -> None:
        for row in payload["extremes"]:
            row["value"] = round(row["value"], 1)

    alter(rounded, f"{WITH}/annuals", one_decimal)
    monkeypatch.setattr("crc_sdk.workflows.noaa_water_levels.urlopen", serve(rounded))
    records = run(tmp_path)
    got = outcomes(records)
    assert {name for name, value in got.items() if value == "differs"} == {
        "bytes",
        "second-download",
    }
    assert result(records, "bytes")["responses_differing"] == 1
    second = result(records, "second-download")
    assert second["values_differing_by_table"].keys() == {"annuals"}
    assert second["values_differing"] == sum(
        1 for row in payloads(WITH)["annuals"]["extremes"] if len(str(row["value"])) > 3
    )
    source = next(s for s in inventory.load_sources("crc_sdk") if s.id == assessment.SOURCE)
    steps = compare.step_outcomes([s.id for s in source.statement], records["checks"])
    assert {step for step, outcome in steps.items() if outcome == "differs"} == {
        "bytes",
        "one-answer",
    }


def test_a_second_run_gives_the_same_records_apart_from_run_times(
    tmp_path: Path, served: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    def stable(records: dict) -> str:
        records = json.loads(json.dumps(records))
        records.pop("run_at")
        for check in records["checks"]:
            check.pop("run_at")
        return json.dumps(records, sort_keys=True)

    first = run(tmp_path)

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("a run from the caches must not download")

    monkeypatch.setattr("data_source_check.reference.noaa_water_levels.urlopen", no_network)
    monkeypatch.setattr("crc_sdk.workflows.noaa_water_levels.urlopen", no_network)
    assert stable(run(tmp_path, live=False)) == stable(first)


def test_the_statement_and_the_checks_name_the_same_steps(tmp_path: Path, served: dict) -> None:
    source = next(s for s in inventory.load_sources("crc_sdk") if s.id == assessment.SOURCE)
    assert source.drafted_by and not source.reviewed_by
    assert source.status["verification"] == "in progress"
    records = run(tmp_path)
    steps = [step.id for step in source.statement]
    used = {step for check in records["checks"] for step in check["steps"]}
    assert used <= set(steps)
    by_step = compare.step_outcomes(steps, records["checks"])
    unchecked = {step for step, outcome in by_step.items() if outcome == "not checked"}
    assert unchecked == {"limits", "snapshot", "reuse"}
    assert all(step.note for step in source.statement if step.id in unchecked)
