"""The card's "also checked" sentence (itemator/checked.py) and its place in the CI job: real git repositories, a fake API."""
import lzma

from itemator import checked as C
from itemator import local as L
from tests.test_ci import FIXED, FakeHttp, isolated, issue, job, mr, repo, routes  # noqa: F401  (the fixtures)

BASE_PY = "def a():\n    return 1\n\n\ndef b():\n    return 2\n"
SPACED = "def a():\n\n    # one\n    return 1\n\n\n\ndef b():\n    return 2   # two\n"


def test_nothing_checked_says_nothing():
    assert C.sentence([], []) is None


def test_one_layout_only_file():
    assert C.sentence(["a.py"], []) == ("Also checked, with no model: 1 Python file changed only in layout, comments, "
                                        "docstrings or the order of plain functions: `a.py`.")


def test_names_are_capped_and_the_rest_counted():
    s = C.sentence([f"f{i}.py" for i in range(5)], [])
    assert s.startswith("Also checked, with no model: 5 Python files changed only") and "`f0.py`, `f1.py`, `f2.py` and 2 more." in s
    assert "f3.py" not in s


def test_opened_files_are_named_with_what_was_read():
    s = C.sentence([], [("t/x.xz", "xz file, 1 KiB, unpacks to 4 bytes of text")] * 5)
    assert s.count("Opened `t/x.xz`") == 3 and s.endswith("2 more binary files opened.")


def test_one_more_opened_file_is_counted_in_the_singular():
    s = C.sentence([], [(f"t/{i}.xz", "xz file") for i in range(4)])
    assert s.count("Opened `") == 3 and s.endswith("1 more binary file opened.")


def test_the_job_says_which_python_files_only_changed_in_layout(repo, tmp_path, monkeypatch):
    repo.base = repo.commit({"src/parser.py": FIXED, "src/other.py": BASE_PY})
    head = repo.commit({"src/other.py": SPACED})
    code, out = job(repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch)
    assert code == 0
    assert [n["path"] for n in out["checked"]["neutral"]] == ["src/other.py"]
    assert "`src/other.py`" in out["card"]["checked_line"] and out["card"]["checked_line"].startswith("Also checked")


def test_a_real_change_to_a_python_file_is_not_called_layout_only(repo, tmp_path, monkeypatch):
    head = repo.commit({"src/parser.py": FIXED})
    _, out = job(repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch)
    assert out["checked"]["neutral"] == [] and "checked_line" not in out["card"]


def test_an_added_archive_is_opened_and_its_mismatch_is_on_the_card(repo, tmp_path, monkeypatch):
    head = repo.commit({"src/parser.py": FIXED, "tests/files/bad.xz": lzma.compress(b"#!/bin/sh\necho hi\n")})
    _, out = job(repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch)
    assert [o["path"] for o in out["checked"]["opened"]] == ["tests/files/bad.xz"]
    assert "unpacks to a program or script" in out["card"]["checked_line"]


def test_the_state_and_the_extras_do_not_depend_on_the_check(repo, tmp_path, monkeypatch):
    head = repo.commit({"src/parser.py": FIXED, "requirements.txt": "requests==2.31.0\nleftpad-py==1.0.0\n"})
    _, with_check = job(repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch)
    monkeypatch.setattr(L, "neutral_verdict", lambda *a: None)
    monkeypatch.setattr(L, "opened", lambda *a: None)
    _, without = job(repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch)
    for k in ("state", "extras", "unplaced", "card"):
        assert with_check[k] == without[k]


def test_a_check_that_breaks_never_fails_the_job(repo, tmp_path, monkeypatch):
    def boom(*a):
        raise RecursionError("deeply nested source")
    monkeypatch.setattr(L, "neutral_verdict", boom)
    head = repo.commit({"src/parser.py": FIXED})
    code, out = job(repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch)
    assert code == 0 and out["checked"]["neutral"] == []
    assert any("no extra check on src/parser.py: RecursionError" in w for w in out["warnings"])


def test_a_file_an_extra_already_lists_is_not_also_called_layout_only(repo, tmp_path, monkeypatch):
    from itemator import ci
    base = repo.commit({"a.py": BASE_PY, "b.py": BASE_PY})
    head = repo.commit({"a.py": SPACED, "b.py": SPACED})
    files = ci.diff_files(str(repo.path), base, head)
    report = {"extras": [{"path": "a.py", "detail": []}, {"path": "", "detail": ["b.py (and why)"]}],
              "warnings": [], "card": {"caveat_line": None}}
    ci.also_checked(report, str(repo.path), base, head, files)
    assert report["checked"]["neutral"] == [] and "checked_line" not in report["card"]
    report["extras"] = []
    ci.also_checked(report, str(repo.path), base, head, files)
    assert [n["path"] for n in report["checked"]["neutral"]] == ["a.py", "b.py"]


def test_only_the_first_files_are_read(repo, tmp_path, monkeypatch):
    from itemator import ci
    monkeypatch.setattr(ci, "MAX_CHECKED_FILES", 1)
    repo.base = repo.commit({"a.py": BASE_PY, "b.py": BASE_PY})
    head = repo.commit({"a.py": SPACED, "b.py": SPACED})
    _, out = job(repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch)
    assert [n["path"] for n in out["checked"]["neutral"]] == ["a.py"] and out["checked"]["files_read"] == 1 and out["checked"]["files"] == 2


# ---- files that have never changed together with the others (itemator/cochange.py, trial: results/stranger_spike_v1.json)

def _history(repo):
    """a+b change together three times, c+d three times, e alone three times; then one change touches all five."""
    for i in range(3):
        repo.commit({"a.py": f"A{i}\n", "b.py": f"B{i}\n"})
        repo.commit({"c.py": f"C{i}\n", "d.py": f"D{i}\n"})
        repo.base = repo.commit({"e.py": f"E{i}\n"})
    return repo.commit({f"{n}.py": "changed\n" for n in "abcde"})


def test_a_file_that_never_changed_with_the_others_is_named_on_the_card(repo, tmp_path, monkeypatch):
    head = _history(repo)
    _, out = job(repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch)
    assert out["checked"]["strangers"] == ["e.py"]
    assert ("In the repository's history `e.py` has never changed in the same commit as any other file changed here."
            in out["card"]["checked_line"])


def test_two_strangers_are_named_in_the_plural():
    s = C.sentence([], [], ["x.py", "y.py"])
    assert s == ("Also checked, with no model: In the repository's history `x.py`, `y.py` have never changed in the same commit "
                 "as any of the other files changed here.")


def test_fewer_than_three_modified_files_are_not_compared(repo, tmp_path, monkeypatch):
    from itemator import cochange
    reads = []
    monkeypatch.setattr(cochange, "history", lambda *a, **k: reads.append(a) or [])
    head = repo.commit({"src/parser.py": FIXED, "README.md": "# changed\n"})
    _, out = job(repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch)
    assert out["checked"]["strangers"] == [] and reads == []


def test_a_change_with_more_modified_files_than_the_cap_is_not_read(repo, tmp_path, monkeypatch):
    from itemator import cochange
    reads = []
    real = cochange.history
    monkeypatch.setattr(cochange, "history", lambda *a, **k: reads.append(a) or real(*a, **k))
    monkeypatch.setattr(cochange, "MAX_FILES", 4)
    head = _history(repo)
    _, out = job(repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch)
    assert out["checked"]["strangers"] == [] and reads == []


def test_a_listed_file_is_not_also_called_a_stranger(repo, tmp_path, monkeypatch):
    from itemator import ci
    head = _history(repo)
    files = ci.diff_files(str(repo.path), repo.base, head)
    report = {"extras": [{"path": "e.py", "detail": []}], "warnings": [], "card": {"caveat_line": None}}
    ci.also_checked(report, str(repo.path), repo.base, head, files)
    assert report["checked"]["strangers"] == [] and "checked_line" not in report["card"]


def test_a_history_that_cannot_be_read_never_fails_the_job(repo, tmp_path, monkeypatch):
    from itemator import cochange
    monkeypatch.setattr(cochange, "history", lambda *a, **k: (_ for _ in ()).throw(OSError("no git")))
    head = _history(repo)
    code, out = job(repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch)
    assert code == 0 and out["checked"]["strangers"] == [] and any("no history check: OSError" in w for w in out["warnings"])


def test_history_is_read_from_the_base_not_the_head(repo):
    from itemator import cochange
    head = _history(repo)
    assert len(cochange.history(str(repo.path), repo.base, "a.py")) == 3
    assert len(cochange.history(str(repo.path), head, "a.py")) == 4
    assert cochange.history(str(repo.path), "nope", "a.py") == []
    assert len(cochange.history(str(repo.path), repo.base, "a.py", limit=2)) == 2


GHOST = "feedface1234567"


def test_a_cited_commit_the_project_does_not_have_is_on_the_card(repo, tmp_path, monkeypatch):
    head = repo.commit({"src/parser.py": FIXED}, f"Fix the parser\n\nThis reverts commit {GHOST}.")
    code, out = job(repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch)
    assert code == 0 and out["checked"]["cites"][0]["id"] == GHOST[:12] and out["checked"]["cites"][0]["kind"] == "missing"
    assert f"`{GHOST[:12]}`" in out["card"]["checked_line"] and "is not a commit of this project" in out["card"]["checked_line"]


def test_a_cited_commit_the_api_knows_is_not_reported(repo, tmp_path, monkeypatch):
    head = repo.commit({"src/parser.py": FIXED}, f"Fix the parser\n\nThis reverts commit {GHOST}.")
    r = routes(mr(), [issue()])
    r[f"/projects/7/repository/commits/{GHOST}"] = (200, {"id": GHOST, "title": "Something"})
    _, out = job(repo, head, FakeHttp(r), tmp_path, monkeypatch)
    assert out["checked"]["cites"] == [] and "checked_line" not in out["card"]


def test_a_citation_in_the_merge_request_description_counts_too(repo, tmp_path, monkeypatch):
    head = repo.commit({"src/parser.py": FIXED})
    _, out = job(repo, head, FakeHttp(routes(mr(description=f"Closes #12. Fixes: {GHOST}"), [issue()])), tmp_path, monkeypatch)
    assert [c["id"] for c in out["checked"]["cites"]] == [GHOST[:12]]


def test_parts_that_fit_are_all_kept(monkeypatch):
    sh = [{"path": "s.sh", "line": 1, "kind": "env-to-network", "text": ""}]
    unt = [{"path": "c.yml", "line": 1, "kind": "interpreter", "text": ""}]
    full = C.sentence(["a.py"], [], [], [], None, [], [], None, [], None, None, sh, unt, None)
    assert full is not None and "more result" not in full
    n = len(full) - len("Also checked, with no model: ")
    monkeypatch.setattr(C, "MAX_LINE", n + 1)              # exactly enough room for every part (each part counts a space after it)
    assert C.sentence(["a.py"], [], [], [], None, [], [], None, [], None, None, sh, unt, None) == full
    monkeypatch.setattr(C, "MAX_LINE", n)                  # one character short: the last part goes
    cut = C.sentence(["a.py"], [], [], [], None, [], [], None, [], None, None, sh, unt, None)
    assert cut.endswith("1 more result is in `checked` in itemator.json.") and "shape that has carried" not in cut and "treat a title" in cut


def test_the_first_part_is_always_kept_and_the_count_is_exact():
    old = C.MAX_LINE
    C.MAX_LINE = 10
    try:
        s = C.sentence(["a.py"], [("t/x.xz", "xz file")], [], [], None, [], [], None, [], None, None, [{"path": "s.sh", "line": 1, "kind": "env-to-network", "text": ""}], [], None)
        assert s is not None and s.startswith("Also checked, with no model: 1 Python file changed only in layout") and s.endswith("2 more results are in `checked` in itemator.json.")
        s1 = C.sentence(["a.py"], [], [], [], None, [], [], None, [], None, None, [{"path": "s.sh", "line": 1, "kind": "env-to-network", "text": ""}], [], None)
        assert s1.endswith("1 more result is in `checked` in itemator.json.")
    finally:
        C.MAX_LINE = old
