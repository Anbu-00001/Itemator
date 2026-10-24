"""eval/leftbehind_study.py: the parts that decide an outcome, without the network."""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import leftbehind_study as S  # noqa: E402


def test_versions_compare_on_the_digits_both_have():
    assert not S.at_or_above((3, 10, 12), (3, 11))
    assert S.at_or_above((3, 11, 4), (3, 11)) and S.at_or_above((3, 11), (3, 11, 4))
    assert S.at_or_above((3, 12), (3, 11)) and not S.at_or_above((3, 10), (3, 11))


def test_wilson_interval():
    assert S.wilson(0, 0) is None
    assert S.wilson(2, 2) == [0.3424, 1.0]
    lo, hi = S.wilson(10, 100)
    assert lo == 0.0552 and hi == 0.1744


def row(state, left=(), merged=True):
    return {"state": state, "moved": [{"path": "Dockerfile"}], "merged": merged, "pr": "p", "left": list(left)}


def test_the_share_counts_only_fully_read_pull_requests():
    copy = {"path": "a", "followed": False, "still_old": True, "named": True}
    unknown = {"path": "b", "followed": None, "still_old": None}
    s = S.summarise([row("read", [copy, unknown]), row("read"), row("partly_read", [copy]), {"state": "no_move"}], 9)
    assert s["with_a_move_read"] == 2 and s["left_behind"]["prs"] == 1 and s["left_behind"]["share"] == 0.5
    assert s["merged_copies"] == {"n": 2, "followed": 0, "not_followed": 1, "unknown": 1, "still_old_today": 1,
                                  "named_by_a_reviewer": 1}
    assert s["by_state"]["partly_read"] == 1 and s["kill_rule_narrow"] is False


def test_the_frame_is_the_pre_registered_one():
    assert S.FRAME_RE.pattern in S.RUBRIC["frame"] and S.SEED == 20261024 and S.SAMPLE == 400
