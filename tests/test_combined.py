import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import combined as C  # noqa: E402


def row(path, i=False, o=False, s=False):
    return {"path": path, "named": {"itemator": i, "overreach": o, "scope_creep_detector": s}}


H = {"rows": [row("a", i=True), row("b", o=True), row("c", s=True), row("d", o=True, s=True), row("e"), row(None, i=True)],
     "exploratory_questions": {"itemator": 10, "overreach": 20, "scope_creep_detector": 40}}


def test_a_file_counts_once_when_any_tool_in_the_pair_names_it():
    got = C.build(H)
    assert got["cases"] == 5
    assert got["named"] == {"itemator": 1, "itemator_with_overreach": 3, "itemator_with_scope_creep_detector": 3, "itemator_with_both": 4}


def test_questions_are_bounds_from_itemator_alone_to_every_rival_file_added():
    q = C.build(H)["questions"]
    assert q["itemator"] == {"at_least": 10, "at_most": 10}
    assert q["itemator_with_overreach"] == {"at_least": 10, "at_most": 30}
    assert q["itemator_with_both"] == {"at_least": 10, "at_most": 70}
