"""The lift study's pure parts: eval/aidev_lift.py."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import aidev_lift as L  # noqa: E402
from itemator.extras import Extra  # noqa: E402


def test_earliest_takes_the_first_commit_in_pull_request_order_not_in_comment_order():
    cs = [{"original_commit_id": "c"}, {"original_commit_id": "b"}, {"original_commit_id": "zz"}]
    assert L.earliest(cs, ["a", "b", "c"]) == "b"
    assert L.earliest([{"original_commit_id": "zz"}], ["a"]) is None
    assert L.earliest([], ["a"]) is None


def test_label_marks_listed_and_objected_and_drops_unnamed_rows():
    files = [{"filename": "AGENTS.md"}, {"filename": "src/a.py"}, {"filename": None}]
    got = L.label(files, [Extra("agent_instructions", "AGENTS.md", "AGENTS.md", "x")], {"src/a.py"})
    assert got == [{"path": "AGENTS.md", "listed": True, "objected": False, "kind": "agent_instructions"},
                   {"path": "src/a.py", "listed": False, "objected": True, "kind": None}]


def test_shares_ratio_and_whether_the_intervals_are_apart():
    rows = [{"listed": True, "objected": i < 5} for i in range(10)] + [{"listed": False, "objected": i < 10} for i in range(1000)]
    s = L.shares(rows)
    assert (s["listed"]["files"], s["listed"]["objected"], s["unlisted"]["objected"]) == (10, 5, 10)
    assert s["ratio"] == 50.0 and s["intervals_apart"] is True
    close = [{"listed": True, "objected": i < 1} for i in range(10)] + [{"listed": False, "objected": i < 1} for i in range(20)]
    assert s["listed_clearly_higher"] is True and s["listed_clearly_lower"] is False
    assert L.shares(close)["intervals_apart"] is False
    under = [{"listed": True, "objected": False} for i in range(1000)] + [{"listed": False, "objected": i < 100} for i in range(1000)]
    u = L.shares(under)
    assert (u["intervals_apart"], u["listed_clearly_higher"], u["listed_clearly_lower"]) == (True, False, True)
    assert L.shares([{"listed": False, "objected": False}])["ratio"] is None
    assert L.shares([{"listed": True, "objected": True}, {"listed": False, "objected": False}])["ratio"] is None   # no base rate: no ratio
