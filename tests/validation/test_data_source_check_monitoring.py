"""Monitoring: stale assessments are found, a re-run is compared, nothing is published."""

from pathlib import Path

from data_source_check import build, monitor
from data_source_check.core import monitoring

RECORDS = {
    "source": "demo",
    "run_at": "2026-11-12T00:00:00Z",
    "versions": {"crc-sdk": "0.11.1 with the fix of CRC-001-NEX (local clone)"},
    "files": [
        {"url": "https://x/a", "etag": '"1"', "last_modified": "Mon", "missing": False},
        {"url": "https://x/gone", "etag": '"2"', "last_modified": "Mon", "missing": False},
        {"url": "https://x/absent", "missing": True},
    ],
    "checks": [
        {"check": "values[A]", "outcome": "confirmed", "summary": "10 rows",
         "inputs": [{"role": "reference", "url": "https://x/b", "etag": '"3"',
                     "last_modified": "Mon"},
                    {"role": "summary", "url": "https://x (5 files)", "sha256": "s"}]},
        {"check": "header[A]", "outcome": "confirmed", "summary": "3 columns", "inputs": []},
    ],
}  # fmt: skip


def test_recorded_inputs_are_the_publisher_files_once() -> None:
    urls = [item["url"] for item in monitoring.recorded_inputs(RECORDS)]
    assert urls == ["https://x/a", "https://x/absent", "https://x/b", "https://x/gone"]


def test_a_file_is_classified_by_etag_then_date() -> None:
    old = {"etag": '"1"', "last_modified": "Mon", "missing": False}
    assert (
        monitoring.classify(old, {"status": 200, "etag": '"1"', "last_modified": "Tue"})
        == "unchanged"
    )
    assert (
        monitoring.classify(old, {"status": 200, "etag": '"9"', "last_modified": "Mon"})
        == "changed"
    )
    assert monitoring.classify(old, {"status": 404}) == "gone"
    assert monitoring.classify({"missing": True}, {"status": 200, "etag": '"1"'}) == "appeared"
    assert monitoring.classify({"missing": True}, {"status": 404}) == "unchanged"
    no_etag = {"last_modified": "Mon", "missing": False}
    assert monitoring.classify(no_etag, {"status": 200, "last_modified": "Tue"}) == "changed"


def test_source_state_names_every_reason() -> None:
    same = {
        "https://x/a": {"status": 200, "etag": '"1"'},
        "https://x/b": {"status": 200, "etag": '"3"'},
        "https://x/gone": {"status": 200, "etag": '"2"'},
        "https://x/absent": {"status": 404},
    }
    assert not monitoring.source_state(RECORDS, same, {"crc-sdk": "0.11.1"})["stale"]
    moved = same | {
        "https://x/a": {"status": 200, "etag": '"7"'},
        "https://x/gone": {"status": 404},
        "https://x/absent": {"status": 200, "etag": '"8"'},
    }
    state = monitoring.source_state(RECORDS, moved, {"crc-sdk": "0.12.0"})
    assert state["stale"] and len(state["reasons"]) == 2
    assert {item["change"] for item in state["files_changed"]} == {"changed", "gone", "appeared"}
    assert state["versions_changed"] == {"crc-sdk": {"assessed": "0.11.1", "installed": "0.12.0"}}
    down = same | {"https://x/a": {"status": None, "error": "timeout"}}
    quiet = monitoring.source_state(RECORDS, down, {"crc-sdk": "0.11.1"})
    assert not quiet["stale"] and quiet["files_unreachable"] == ["https://x/a"]  # not a change


def test_a_rerun_is_compared_check_by_check() -> None:
    new = {"source": "demo", "checks": [
        {"check": "values[A]", "outcome": "differs", "summary": "10 rows"},
        {"check": "header[A]", "outcome": "confirmed", "summary": "4 columns"},
        {"check": "new[A]", "outcome": "confirmed", "summary": ""},
    ]}  # fmt: skip
    diff = monitoring.diff_records(RECORDS, new)
    assert diff["newly_differing"] == ["values[A]"] and diff["checks_added"] == ["new[A]"]
    assert [item["check"] for item in diff["summaries_changed"]] == ["header[A]"]
    report = {"run_at": "now", "installed": {"crc-sdk": "0.11.1"}, "sources": [],
              "gaps": {"unclaimed_symbols": [], "new_options": []}, "needs_attention": True,
              "reruns": [diff | {"staged": "staging/demo.json"}]}  # fmt: skip
    text = monitoring.markdown(report)
    assert "confirmed to **differs**" in text and "is not published" in text


def test_a_monitoring_run_reports_and_leaves_the_records_alone(tmp_path: Path) -> None:
    """Against the committed records, with a publisher that changed one IBTrACS file."""
    before = {p.name: p.read_bytes() for p in (build.PAGE_DATA / "records").glob("*.json")}
    ibtracs = build.load_records("ibtracs")
    target = monitoring.recorded_inputs(ibtracs)[0]["url"]

    def ask(url: str) -> dict:
        for records in (build.load_records(name) for name in build.ASSESSMENTS):
            for item in monitoring.recorded_inputs(records):
                if item["url"] == url:
                    if item.get("missing"):
                        return {"status": 404}
                    etag = '"changed"' if url == target else item.get("etag")
                    return {"status": 200, "etag": etag, "last_modified": item.get("last_modified")}
        return {"status": 404}

    page = tmp_path / "page"
    (page / "records").mkdir(parents=True)
    for name, data in before.items():
        (page / "records" / name).write_bytes(data)
    report = monitor.run(page_data=page, docs=tmp_path / "docs", ask=ask)
    states = {state["source"]: state for state in report["sources"]}
    assert states["ibtracs"]["stale"] and len(states["ibtracs"]["files_changed"]) == 1
    assert not states["ghcnh"]["stale"] and not states["nex-gddp-cmip6"]["stale"]
    assert report["needs_attention"]
    assert (
        "stale: the publisher changed 1 of 10 files"
        in (tmp_path / "docs" / "monitoring.md").read_text()
    )
    after = {p.name: p.read_bytes() for p in (build.PAGE_DATA / "records").glob("*.json")}
    assert after == before  # the published records are untouched


def test_a_rerun_is_staged_and_not_published(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    before = {p.name: p.read_bytes() for p in (build.PAGE_DATA / "records").glob("*.json")}
    page = tmp_path / "page"
    (page / "records").mkdir(parents=True)
    for name, data in before.items():
        (page / "records" / name).write_bytes(data)
    calls = []

    def fake_assess(source_id: str, *, live: bool, page_data: Path, cache: Path) -> dict:
        calls.append((source_id, live, page_data, cache))
        fresh = build.load_records(source_id)
        fresh["checks"][1]["outcome"] = "differs"
        return fresh

    monkeypatch.setattr(build, "assess_source", fake_assess)
    monkeypatch.setattr(monitor, "STAGING", tmp_path / "staging")
    ask = lambda url: {"status": 200, "etag": '"other"'}  # noqa: E731  every file changed
    report = monitor.run(rerun=True, page_data=page, docs=tmp_path / "docs", ask=ask)
    assert [call[0] for call in calls] == ["ibtracs", "ghcnh", "nex-gddp-cmip6"]
    assert all(live and str(tmp_path / "staging") in str(where) and "staging" in str(cache)
               for _, live, where, cache in calls)  # fmt: skip
    assert all(len(diff["newly_differing"]) == 1 for diff in report["reruns"])
    after = {p.name: p.read_bytes() for p in (build.PAGE_DATA / "records").glob("*.json")}
    assert after == before
