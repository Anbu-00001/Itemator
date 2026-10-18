"""eval/stranger_spike.py: the pure parts (the network part is exercised by the trial itself)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import stranger_spike as S  # noqa: E402
from itemator import cochange as C  # noqa: E402

CASE = {"comment_id": 7, "path": "a.py"}
H = {"a.py": ["z1", "z2", "z3"], "b.py": ["c1", "c2", "c3"], "c.py": ["c1", "c4", "c5"], "d.py": ["c2", "c6", "c7"]}


def test_a_commented_stranger_with_partnered_others():
    r = S.row_for(CASE, "u", list(H), H)
    assert (r["status"], r["label"], r["others"]) == ("read", C.STRANGER, {C.STRANGER: 0, C.PARTNERED: 3})


def test_unreadable_unmodified_big_and_unavailable_are_counted_apart():
    assert S.row_for(CASE, "u", None, None)["status"] == "unreadable"
    assert S.row_for(CASE, "u", ["b.py"], None)["status"] == "not_modified"
    assert S.row_for(CASE, "u", [f"{i}.py" for i in range(S.MAX_FILES + 1)] + ["a.py"], None)["status"] == "too_many_files"
    assert S.row_for(CASE, "u", [f"{i}.py" for i in range(S.MAX_FILES - 1)] + ["a.py"], None)["status"] == "history_unavailable"


def test_summary_counts_and_labels():
    rows = [S.row_for(CASE, "u1", list(H), H),                                           # stranger, 3 partnered others
            S.row_for({"comment_id": 8, "path": "b.py"}, "u2", list(H), H),              # partnered, a.py stranger beside it
            S.row_for(CASE, "u3", None, None)]
    s = S.summarize(rows)
    assert s["commented_files"] == 3 and s["by_status"] == {"read": 2, "unreadable": 1}
    assert s["eligible_pull_requests"] == 2 and s["eligible_commented_files"] == 2
    assert (s["commented_files_that_are_strangers"]["k"], s["commented_files_that_are_strangers"]["n"]) == (1, 2)
    assert (s["other_files_that_are_strangers"]["k"], s["other_files_that_are_strangers"]["n"]) == (1, 6)
    assert (s["strangers_singled_out"]["k"], s["strangers_singled_out"]["n"]) == (1, 2)
    assert s["mean_share_of_files_flagged_per_pull_request"] == 0.25


def test_too_new_commented_file_is_read_but_not_eligible():
    h = {**H, "a.py": ["z1"]}
    r = S.row_for(CASE, "u", list(h), h)
    assert (r["status"], r["label"]) == ("read", C.TOO_NEW)
    assert S.summarize([r])["eligible_commented_files"] == 0
    assert S.summarize([])["mean_share_of_files_flagged_per_pull_request"] is None


def test_singled_out_needs_no_other_stranger_and_an_empty_file_list_is_not_unreadable():
    h = {**H, "e.py": ["y1", "y2", "y3"]}                                   # a.py and e.py are both strangers
    r = S.row_for(CASE, "u", list(h), h)
    assert r["others"][C.STRANGER] == 1 and S.summarize([r])["strangers_singled_out"]["k"] == 0
    assert S.row_for(CASE, "u", [], None)["status"] == "not_modified"
