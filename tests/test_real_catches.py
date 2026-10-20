"""Leg 3's own parts (eval/real_catches.py): which pairs count, how a pull request's outcome is read from its final files,
what 'changed after the comment' means, and how the counts and shares are made."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import real_catches as C  # noqa: E402


def row(pr, path, cid, hit=True, agent="Copilot", kind=None, state="merged"):
    return {"pr": pr, "path": path, "comment_id": cid, "hit": hit, "agent": agent, "kind": kind, "state": state}


def test_a_pull_request_url_is_split_into_owner_repo_and_number():
    assert C.pr_parts("https://github.com/o/r/pull/12") == ("o", "r", 12)
    assert C.pr_parts("https://github.com/o/r/pull/12/") == ("o", "r", 12)


def test_pairs_are_distinct_pr_and_path_with_all_their_comments_and_only_the_rules_hits():
    rows = [row("https://github.com/o/r/pull/1", "a.py", 10), row("https://github.com/o/r/pull/1", "a.py", 11),
            row("https://github.com/o/r/pull/1", "b.py", 12), row("https://github.com/o/r/pull/2", "a.py", 13, hit=False)]
    got = C.pairs(rows)
    assert [(p["pr"][-1], p["path"], p["comment_ids"]) for p in got] == [("1", "a.py", [10, 11]), ("1", "b.py", [12])]


def test_a_closed_unmerged_pull_request_is_closed_unmerged_even_when_the_file_is_in_it():
    assert C.classify({"state": "closed", "merged": False}, [{"filename": "a.py"}], "a.py") == "closed_unmerged"


def test_a_merged_pull_request_without_the_file_removed_it_and_with_it_landed_it():
    pr = {"state": "closed", "merged": True}
    assert C.classify(pr, [{"filename": "b.py"}], "a.py") == "file_removed"
    assert C.classify(pr, [{"filename": "a.py"}, {"filename": "b.py"}], "a.py") == "landed_with_the_file"


def test_a_renamed_file_still_counts_as_present_and_an_open_pull_request_is_judged_by_its_files():
    pr = {"state": "open", "merged": False}
    assert C.classify(pr, [{"filename": "new.py", "previous_filename": "a.py"}], "a.py") == "landed_with_the_file"
    assert C.classify(pr, [], "a.py") == "file_removed"


def test_changed_after_needs_a_commit_strictly_later_than_the_comment():
    t = "2026-09-01T10:00:00Z"
    assert C.changed_after(["2026-09-01T10:00:01Z"], t)
    assert not C.changed_after(["2026-09-01T10:00:00Z", "2026-08-01T00:00:00Z"], t)
    assert not C.changed_after([None], t) and not C.changed_after([], t)


def case(key, outcome, changed=False, agent="Copilot", kind=None, unreadable=False):
    c = {"key": key, "agent": agent, "kind": kind, "unreadable": unreadable}
    if not unreadable:
        c.update(outcome=outcome, changed_after_comment=changed)
    return c


def test_the_summary_counts_each_outcome_the_share_that_did_not_land_and_the_unreadable_apart():
    cases = [case("1", "file_removed", True), case("2", "closed_unmerged"), case("3", "landed_with_the_file"),
             case("4", "landed_with_the_file", agent="Devin"), case("5", None, unreadable=True)]
    s = C.summarize(cases)
    assert (s["pairs"], s["unreadable"], s["read"]) == (5, 1, 4)
    assert (s["file_removed"], s["closed_unmerged"], s["landed_with_the_file"], s["did_not_land"]) == (1, 1, 2, 2)
    assert s["share_did_not_land"] == 0.5 and s["changed_after_comment"] == 1
    assert s["wilson95"][0] < 0.5 < s["wilson95"][1]
    assert s["by_agent"]["Devin"]["landed_with_the_file"] == 1 and s["by_agent"]["Copilot"]["pairs"] == 3


def test_my_reading_of_the_comments_is_reported_apart_and_unlabelled_pairs_are_counted():
    cases = [case("1", "file_removed"), case("2", "landed_with_the_file"), case("3", "closed_unmerged")]
    s = C.summarize(cases, {"1": "yes", "2": "no"})
    assert s["my_reading"]["counts"] == {"yes": 1, "no": 1, "unlabelled": 1}
    assert s["my_reading"]["asks_removal_yes"] == {"pairs": 1, "file_removed": 1, "closed_unmerged": 0, "landed_with_the_file": 0}
    assert "my_reading" not in C.summarize(cases)


def test_an_empty_run_gives_no_share_not_a_division_error():
    s = C.summarize([case("1", None, unreadable=True)])
    assert s["read"] == 0 and s["share_did_not_land"] is None and s["wilson95"] is None


def test_files_of_no_listable_kind_are_counted_under_none_not_dropped():
    cases = [case("1", "file_removed", kind=None), case("2", "landed_with_the_file", kind="binary"), case("3", "closed_unmerged", kind=None)]
    s = C.summarize(cases)
    assert s["by_kind"]["None"]["pairs"] == 2 and s["by_kind"]["binary"]["pairs"] == 1
    assert sum(v["pairs"] for v in s["by_kind"].values()) == s["read"]
