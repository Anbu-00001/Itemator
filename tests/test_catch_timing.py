"""eval/catch_timing.py: hours between a pull request opening and the objection, on made-up rows (no network)."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import catch_timing as CT  # noqa: E402


def case(pr, at, path="a.sh"):
    return {"pr": pr, "path": path, "comment_created_at": at}


def test_hours_are_the_gap_to_one_decimal():
    assert CT.hours_between("2025-01-01T00:00:00Z", "2025-01-01T04:30:00Z") == 4.5
    assert CT.hours_between("2025-01-01T00:00:00Z", "2025-01-03T00:00:00Z") == 48.0


def test_bad_or_backwards_times_are_unreadable():
    assert CT.hours_between(None, "2025-01-01T00:00:00Z") is None
    assert CT.hours_between("2025-01-01T00:00:00Z", "soon") is None
    assert CT.hours_between("2025-01-02T00:00:00Z", "2025-01-01T00:00:00Z") is None


def test_only_github_pull_links_parse():
    assert CT.parse_pr("https://github.com/o/r/pull/12") == ("o", "r", "12")
    assert CT.parse_pr("https://example.com/o/r/pull/12") is None


def test_summary_counts_median_and_over_a_day():
    opened = {"1": "2025-01-01T00:00:00Z", "2": "2025-01-01T00:00:00Z", "3": "2025-01-01T00:00:00Z", "4": None}
    cases = [case(f"https://github.com/o/r/pull/{n}", t) for n, t in
             [(1, "2025-01-01T02:00:00Z"), (2, "2025-01-01T10:00:00Z"), (3, "2025-01-03T00:00:00Z"), (4, "2025-01-01T01:00:00Z")]]
    rows, s = CT.measure(cases, lambda o, r, n: opened[n])
    assert [r["hours"] for r in rows] == [2.0, 10.0, 48.0, None]
    assert s == {"read": 3, "unreadable": 1, "median_hours": 10.0, "min_hours": 2.0, "max_hours": 48.0, "over_24h": 1}


def test_exactly_24_hours_is_not_over_24():
    rows = [{"hours": 24.0}, {"hours": 24.1}]
    assert CT.summarise(rows)["over_24h"] == 1


def test_a_failed_fetch_is_unreadable_not_guessed():
    rows, s = CT.measure([case("not a link", "2025-01-01T00:00:00Z")], lambda *a: "2025-01-01T00:00:00Z")
    assert rows[0]["hours"] is None and s == {"read": 0, "unreadable": 1}


def test_cache_is_used_before_the_network(tmp_path):
    (tmp_path / "o__r__7.json").write_text(json.dumps({"created_at": "2025-02-02T00:00:00Z"}))
    assert CT.fetch_created_at("o", "r", "7", cache=tmp_path) == "2025-02-02T00:00:00Z"
