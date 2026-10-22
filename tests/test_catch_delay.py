import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import catch_delay as C  # noqa: E402

RUBRIC = json.loads((ROOT / "eval" / "catch_delay_rubric.json").read_text())


def test_start_is_the_later_of_the_pull_request_and_the_commit_that_brought_the_file():
    commits = [{"date": "2025-01-01T00:00:00Z", "files": ["a.py"]}, {"date": "2025-01-03T00:00:00Z", "files": ["x.sh"]}]
    assert C.start("2025-01-02T00:00:00Z", commits, "x.sh") == "2025-01-03T00:00:00Z"
    assert C.start("2025-01-02T00:00:00Z", commits, "a.py") == "2025-01-02T00:00:00Z"   # pushed before the pull request opened
    assert C.start("2025-01-02T00:00:00Z", commits, "gone.txt") is None


def test_durations_read_as_minutes_hours_or_days():
    assert C.say(0.5) == "30 minutes"
    assert C.say(1.2) == "1 hour"
    assert C.say(5) == "5 hours"
    assert C.say(72) == "3 days"


def test_summary_counts_quick_and_slow_and_leaves_unreadable_out():
    rows = [{"hours": 0.5, "outcome": "file_removed"}, {"hours": 30, "outcome": "file_removed"},
            {"hours": 2, "outcome": "closed_unmerged"}, {"hours": None, "outcome": "closed_unmerged"}]
    s = C.summarise(rows, RUBRIC)
    assert (s["n"], s["unreadable"], s["median_hours"]) == (3, 1, 2)
    assert (s["within_hour"], s["day_or_more"]) == (1, 1)
    assert s["by_outcome"]["file_removed"]["n"] == 2
    assert s["sentence"].startswith("On the 3 files reviewers objected to, the objection came a median of 2 hours")


def test_no_readable_case_gives_no_sentence():
    assert "sentence" not in C.summarise([{"hours": None, "outcome": "x"}], RUBRIC)
