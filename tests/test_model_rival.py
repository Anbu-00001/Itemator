import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import model_rival as M  # noqa: E402

RUBRIC = json.loads((ROOT / "eval" / "model_rival_rubric.json").read_text())


def wilson(k, n):
    return [0, 1]


def test_the_sample_is_fixed_and_capped():
    keys = list(range(500))
    assert M.draw(keys) == M.draw(keys) and len(M.draw(keys)) == 100
    assert M.draw(keys[:7]) == keys[:7]


def test_the_diff_is_cut_per_file_and_in_total():
    seen = []
    M.cut_diff([{"filename": "a", "patch": "x" * 5000}], lambda fs: seen.append(fs) or "y" * 20000)
    assert len(seen[0][0]["patch"]) == 600
    assert len(M.cut_diff([], lambda fs: "y" * 20000)) == 14000


def test_only_the_asked_json_counts_as_an_answer():
    assert M.parse('{"out_of_scope": ["a.sh"]}') == {"a.sh"}
    assert M.parse({"out_of_scope": []}) == set()
    assert M.parse("a.sh is out of scope") is None
    assert M.parse({"files": ["a.sh"]}) is None
    assert M.parse(None) is None


def test_summary_counts_cases_and_questions_for_both():
    rows = [{"named": {"itemator": True, "model": False}}, {"named": {"itemator": False, "model": True}}, {"named": {"itemator": False, "model": True}},
            {"named": {"itemator": True, "model": True}}]
    snaps = [{"invalid": False, "named": {"itemator": 1, "model": 9}}, {"invalid": True, "named": {"itemator": 0, "model": 0}}]
    s = M.summarise(rows, snaps, RUBRIC, wilson)
    assert (s["tools"]["itemator"]["cases_named"], s["tools"]["model"]["cases_named"]) == (2, 3)
    assert (s["tools"]["itemator"]["files_named"], s["tools"]["model"]["files_named"]) == (1, 9)
    assert (s["model_not_itemator"], s["itemator_not_model"], s["invalid_answers"]) == (2, 1, 1)
    assert "named 3 of 4 files reviewers objected to, by asking about 9 files; Itemator's rules named 2 by asking about 1" in s["sentence"]
