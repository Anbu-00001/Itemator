import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import always_hides as H  # noqa: E402

RUBRIC = json.loads((ROOT / "eval" / "always_hides_rubric.json").read_text())


def row(i, when, paths):
    return {"id": i, "created_at": when, "questions": [["kind", p] for p in paths]}


def test_an_earlier_question_on_the_same_path_hides_the_later_case():
    case = row(5, "2025-03", ["x.sh"])
    assert H.hidden(case, [row(1, "2025-01", ["x.sh"]), case], "x.sh")


def test_a_later_or_other_path_question_does_not_hide_it():
    case = row(5, "2025-03", ["x.sh"])
    assert not H.hidden(case, [case, row(9, "2025-05", ["x.sh"]), row(2, "2025-01", ["y.sh"])], "x.sh")


def test_the_same_day_breaks_ties_by_id():
    case = row(5, "2025-03", ["x.sh"])
    assert H.hidden(case, [row(4, "2025-03", ["x.sh"])], "x.sh")
    assert not H.hidden(case, [row(6, "2025-03", ["x.sh"])], "x.sh")


def test_summary_leaves_unreadable_cases_out_and_fills_the_sentence():
    s = H.summarise([{"hidden": True}, {"hidden": False}, {"hidden": None}], RUBRIC)
    assert (s["read"], s["unreadable"], s["hidden"]) == (2, 1, 1)
    assert s["sentence"].startswith("Of the 2 files reviewers objected to that the rules list, 1 had already been asked")
    assert "could have hidden it from" in s["sentence"]
    assert "hidden them" in H.summarise([{"hidden": False}], RUBRIC)["sentence"]
