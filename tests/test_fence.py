"""itemator/fence.py: lines a change deletes that a bug-fix commit added. Real git repositories in tmp, no network."""
import pytest

from itemator import checked as C
from itemator import ci
from itemator import fence as F
from tests.test_ci import FakeHttp, isolated, issue, job, mr, repo, routes  # noqa: F401  (the fixtures)

GUARDED = "def parse(s):\n    if not s:\n        return []\n    return s.split(',')\n"
PLAIN = "def parse(s):\n    return s.split(',')\n"


def deleting(repo, path="src/p.py", before=GUARDED, after=PLAIN, first="Add the parser", then="Fix crash on empty input (#212)"):
    repo.commit({path: PLAIN}, first)
    repo.base = repo.commit({path: before}, then)
    return repo.commit({path: after}, "tidy")


def find(repo, head, skip=frozenset()):
    return F.find(str(repo.path), repo.base, ci.diff_files(str(repo.path), repo.base, head), skip)


@pytest.mark.parametrize("subject", ["Fix crash", "fix: guard", "Fixes #212", "hotfix login", 'Revert "Add x"', "CVE-2024-12345 patch", "bugfix: y", "fixed #3"])
def test_subjects_that_say_they_fix_something(subject):
    assert F.says_fix(subject)


@pytest.mark.parametrize("subject", ["Prefix the names", "Add fixture", "Suffix change", "Add parser", "Fixing things", "Refix"])
def test_subjects_that_do_not(subject):
    assert not F.says_fix(subject)


def test_a_deleted_guard_that_a_fix_added_is_listed_with_the_fix_subject(repo):
    head = deleting(repo)
    out = find(repo, head)
    assert [(d["path"], d["lines"], d["subject"]) for d in out["fenced"]] == [("src/p.py", 2, "Fix crash on empty input (#212)")]
    assert len(out["fenced"][0]["commit"]) == 8 and out["runs_read"] == 1 and out["capped"] is False


def test_a_guard_added_by_a_commit_that_is_not_a_fix_is_not_listed(repo):
    head = deleting(repo, then="Add the guard")
    assert find(repo, head)["fenced"] == []


def test_a_reformat_in_between_does_not_hide_the_fix(repo):
    repo.commit({"src/p.py": PLAIN}, "Add the parser")
    repo.commit({"src/p.py": GUARDED}, "Fix crash on empty input")
    repo.base = repo.commit({"src/p.py": GUARDED.replace("not s:\n", "not s:  \n").replace("[]\n", "[]   \n")}, "Trim spacing")
    head = repo.commit({"src/p.py": PLAIN}, "tidy")
    assert [d["subject"] for d in find(repo, head)["fenced"]] == ["Fix crash on empty input"]


def test_lines_the_change_adds_back_elsewhere_are_a_move_not_a_deletion(repo):
    repo.commit({"src/p.py": PLAIN, "src/q.py": "x = 1\n"}, "Add")
    repo.base = repo.commit({"src/p.py": GUARDED}, "Fix crash on empty input")
    head = repo.commit({"src/p.py": PLAIN, "src/q.py": "x = 1\n    if not s:\n        return []\n"}, "move")
    assert find(repo, head)["fenced"] == []


def test_test_and_doc_files_are_not_read(repo):
    for path in ("tests/test_p.py", "docs/p.md", "src/test_p.py"):
        r = deleting(repo, path=path)
        assert find(repo, r)["fenced"] == [], path


def test_deleted_blank_and_comment_lines_are_not_listed(repo):
    repo.commit({"src/p.py": "x = 1\n"}, "Add")
    repo.base = repo.commit({"src/p.py": "x = 1\n\n# the reason for x\n"}, "Fix crash on empty input")
    head = repo.commit({"src/p.py": "x = 1\n"}, "tidy")
    assert find(repo, head)["fenced"] == [] and find(repo, head)["runs_read"] == 0


def test_a_rewritten_line_is_not_a_deletion(repo):
    head = deleting(repo, after="def parse(s):\n    if s is None:\n        return []\n    return s.split(',')\n")
    assert find(repo, head)["fenced"] == []


def test_a_commit_that_touched_many_files_is_skipped(repo):
    repo.commit({"src/p.py": PLAIN}, "Add")
    repo.base = repo.commit({"src/p.py": GUARDED, **{f"f{i}.txt": "x\n" for i in range(25)}}, "Fix everything")
    head = repo.commit({"src/p.py": PLAIN}, "tidy")
    assert find(repo, head)["fenced"] == []


def test_a_commit_that_touched_a_few_files_is_still_listed(repo):
    repo.commit({"src/p.py": PLAIN}, "Add")
    repo.base = repo.commit({"src/p.py": GUARDED, **{f"f{i}.txt": "x\n" for i in range(5)}}, "Fix everything")
    head = repo.commit({"src/p.py": PLAIN}, "tidy")
    assert [d["subject"] for d in find(repo, head)["fenced"]] == ["Fix everything"]


def test_a_file_deleted_whole_is_not_read(repo):
    repo.commit({"src/p.py": PLAIN}, "Add")
    repo.base = repo.commit({"src/p.py": GUARDED}, "Fix crash")
    head = repo.commit({"src/p.py": None}, "remove the file")
    assert find(repo, head) == {"fenced": [], "runs_read": 0, "capped": False}


def test_the_cap_on_the_whole_change_stops_the_reading(repo, monkeypatch):
    monkeypatch.setattr(F, "MAX_RUNS", 1)
    repo.commit({"src/a.py": PLAIN, "src/b.py": PLAIN}, "Add")
    repo.base = repo.commit({"src/a.py": GUARDED, "src/b.py": GUARDED}, "Fix crash")
    head = repo.commit({"src/a.py": PLAIN, "src/b.py": PLAIN}, "tidy")
    out = find(repo, head)
    assert out["runs_read"] == 1 and out["capped"] is True and [d["path"] for d in out["fenced"]] == ["src/a.py"]


def test_two_runs_from_one_commit_in_one_file_are_named_once_on_the_card():
    d = {"path": "a.py", "lines": 2, "commit": "abcd1234", "subject": "Fix it"}
    s = C.sentence([], [], [], [d, dict(d, lines=3)])
    assert s.count("`a.py`") == 1 and "and 1 more" not in s


def test_a_file_an_extra_already_lists_is_skipped(repo):
    head = deleting(repo)
    assert find(repo, head, skip={"src/p.py"})["fenced"] == []


def test_the_caps_stop_the_reading_and_say_so(repo, monkeypatch):
    monkeypatch.setattr(F, "MAX_RUNS_PER_FILE", 1)
    body = lambda keep: "".join(f"line {i}\n" if i in keep else f"guard {i}\n" for i in range(9))
    repo.commit({"src/p.py": "".join(f"line {i}\n" for i in range(9))}, "Add")
    repo.base = repo.commit({"src/p.py": body({0, 2, 4, 6, 8})}, "Fix crash")
    head = repo.commit({"src/p.py": "".join(f"line {i}\n" for i in (0, 2, 4, 6, 8))}, "tidy")
    out = find(repo, head)
    assert out["runs_read"] == 1 and out["capped"] is True


def test_a_subject_is_made_safe_for_a_card():
    s = F.tidy("Fix `x` <b>bold</b> [link](http://x) \u202e\x00 " + "y" * 100)
    assert "`" not in s and "<" not in s and "[" not in s and "\u202e" not in s and len(s) <= F.SUBJECT_SHOWN


def test_the_card_sentence_names_the_fix_and_counts_the_rest():
    d = lambda i: {"path": f"a{i}.py", "lines": 1 if i == 0 else 3, "commit": "abcd1234", "subject": "Fix it"}
    s = C.sentence([], [], [], [d(i) for i in range(5)])
    assert s.startswith("Also checked, with no model: This change deletes lines that a commit whose subject says it fixes something had added: ")
    assert "`a0.py` (1 line added by `abcd1234`, \"Fix it\")" in s and "`a1.py` (3 lines" in s and s.endswith(" and 2 more.")
    assert "a3.py" not in s and C.sentence([], [], [], []) is None


def test_the_job_puts_the_fence_on_the_card_and_never_fails_on_it(repo, tmp_path, monkeypatch):
    head = deleting(repo)
    code, out = job(repo, head, FakeHttp(routes(mr(), [issue(description="Tidy src/p.py")])), tmp_path, monkeypatch)
    assert code == 0 and out["checked"]["fenced"][0]["subject"] == "Fix crash on empty input (#212)"
    assert "deletes lines that a commit whose subject says it fixes something" in out["card"]["checked_line"]
    monkeypatch.setattr(F, "find", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    code, out = job(repo, head, FakeHttp(routes(mr(), [issue(description="Tidy src/p.py")])), tmp_path, monkeypatch)
    assert code == 0 and out["checked"]["fenced"] == [] and any("no fence check: RuntimeError" in w for w in out["warnings"])


def test_the_caps_are_the_documented_ones():
    assert (F.MAX_RUNS, F.MAX_RUNS_PER_FILE, F.MAX_FILE_LINES, F.MAX_COMMIT_FILES) == (30, 5, 5000, 20)
