"""eval/cleanup_after_merge.py: the pure parts (who deleted a file, the draw, the summary sentence)."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import cleanup_after_merge as C  # noqa: E402

RUBRIC = json.loads((pathlib.Path(__file__).resolve().parent.parent / "eval" / "cleanup_rubric.json").read_text())


def test_only_a_person_counts_as_the_deleter():
    assert C.by_person("octocat") and C.by_person("Copilotfan")
    assert not any(C.by_person(x) for x in (None, "", "dependabot[bot]", "Copilot", "devin-ai-integration"))


def test_the_draw_caps_each_side_and_each_pull_request():
    rows = [{"pr": f"p{(i // 2) % 60}", "path": f"f{i}", "listed": i % 2 == 0} for i in range(2000)]
    got = C.draw(rows)
    assert sum(r["listed"] for r in got) == C.PER_SIDE and sum(not r["listed"] for r in got) == C.PER_SIDE
    per = {}
    for r in got:
        per[(r["pr"], r["listed"])] = per.get((r["pr"], r["listed"]), 0) + 1
    assert max(per.values()) <= C.PER_PR
    assert C.draw(list(reversed(rows))) == got                              # the order of the input does not matter


def test_the_summary_leaves_out_unreadable_files_and_picks_the_sentence():
    rows = ([{"listed": True, "state": "deleted_by_person"}] * 3 + [{"listed": True, "state": "still_there"}] * 7
            + [{"listed": False, "state": "deleted_by_person"}] * 1 + [{"listed": False, "state": "still_there"}] * 9
            + [{"listed": True, "state": "unreadable"}] * 5)
    s = C.summarise(rows, RUBRIC)
    assert s["listed"]["n"] == 10 and s["listed"]["deleted_by_person"] == 3 and s["unreadable"] == 5
    assert s["sentence"].startswith("Of 10 added files the rules list, 3 were later deleted by a person, against 1 of 10")
    flipped = [dict(r, listed=not r["listed"]) for r in rows if r["state"] != "unreadable"]
    assert C.summarise(flipped, RUBRIC)["sentence"].startswith("Files the rules list were not deleted later more often")
