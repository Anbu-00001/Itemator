"""The pure parts of eval/neutral_cases.py and eval/neutral_spike.py."""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import neutral_cases as C  # noqa: E402
import neutral_spike as S  # noqa: E402
from itemator import neutral as N  # noqa: E402


def test_pick_is_a_fixed_order_independent_of_input_order():
    rows = [(i, i, "A", f"u{i}", "t") for i in range(1, 30)]
    a = C.pick(rows, 10)
    assert [c["pr_id"] for c in a] == [c["pr_id"] for c in C.pick(list(reversed(rows)), 10)]
    assert len(a) == 10 and len({c["pr_id"] for c in a}) == 10
    assert a[0]["pr_id"] == min(rows, key=lambda r: C.order_key(r[0]))[0]
    assert set(a[0]) == {"pr_id", "number", "agent", "html_url"}


def test_the_seed_changes_the_order(monkeypatch):
    rows = [(i, i, "A", f"u{i}", "t") for i in range(1, 60)]
    a = [c["pr_id"] for c in C.pick(rows, 20)]
    monkeypatch.setattr(C, "SEED", 1)
    assert a != [c["pr_id"] for c in C.pick(rows, 20)]


def pr(agent, *levels, fetched=True):
    return {"pr_id": 1, "agent": agent, "html_url": "u", "fetched": fetched,
            "files": [{"path": "a.py", "level": l, "compiled_same": True if l == N.SAME_SYNTAX else None} for l in levels]}


def test_summary_counts_levels_and_shares():
    prs = [pr("X", N.SAME_SYNTAX, N.NOT_PROVED), pr("X", N.REORDERED, N.DOCS_ONLY), pr("Y", N.NOT_PROVED, "unfetched"),
           pr("Y", fetched=False)]
    s = S.summarize(prs, 9)
    assert s["pull_requests_examined"] == 9 and s["pull_requests_with_a_modified_py_file"] == 4 and s["pull_requests_fetched"] == 3
    assert s["py_files"] == 6 and s["py_files_unfetched"] == 1 and s["py_files_read"] == 5
    assert s["by_level"][N.SAME_SYNTAX] == 1 and s["by_level"][N.NOT_PROVED] == 2 and s["py_files_proved"] == 3
    assert s["share_of_read_files_proved"] == 0.6
    assert s["pull_requests_where_every_read_file_is_proved"] == 1          # only the second PR has no unproved file
    assert s["same_syntax_checked_against_compiled_code"] == {"files": 1, "compiled_same": 1, "not_same": 0}
    assert s["by_agent"]["X"] == {"pull_requests": 2, "read_files": 4, "proved": 3}
    assert s["by_agent"]["Y"] == {"pull_requests": 1, "read_files": 1, "proved": 0}


def test_summary_flags_a_rule_defect():
    bad = pr("X", N.SAME_SYNTAX)
    bad["files"][0]["compiled_same"] = False
    assert S.summarize([bad], 1)["same_syntax_checked_against_compiled_code"]["not_same"] == 1


def test_summary_with_nothing_read():
    s = S.summarize([], 5)
    assert s["share_of_read_files_proved"] is None and s["pull_requests_where_every_read_file_is_proved"] == 0


def test_a_pull_request_with_an_unfetched_file_is_not_counted_as_fully_proved():
    s = S.summarize([pr("X", N.SAME_SYNTAX, "unfetched")], 1)
    assert s["pull_requests_where_every_read_file_is_proved"] == 0


def test_only_modified_python_files_count():
    files = [{"filename": "a.py", "status": "modified"}, {"filename": "b.py", "status": "added"}, {"filename": "c.py", "status": "removed"},
             {"filename": "d.py", "status": "renamed"}, {"filename": "e.js", "status": "modified"}, {"filename": "f.pyi", "status": "modified"},
             {"filename": "pkg/g.py", "status": "modified"}]
    assert [f["filename"] for f in S.modified_py(files)] == ["a.py", "pkg/g.py"]


def test_compiled_check_counts_both_outcomes():
    a, b = pr("X", N.SAME_SYNTAX, N.SAME_SYNTAX, N.SAME_SYNTAX), None
    a["files"][1]["compiled_same"] = False
    a["files"][2]["compiled_same"] = None
    assert S.summarize([a], 1)["same_syntax_checked_against_compiled_code"] == {"files": 3, "compiled_same": 1, "not_same": 1}
