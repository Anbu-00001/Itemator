"""T26 B1: a merge request cannot blind the checker with git attributes. `git diff` reads attributes from the
checkout (the merge request's own .gitattributes, at any depth), $GIT_DIR/info/attributes, core.attributesFile and
the system file; any of them can mark a changed file `-diff` or `binary`, and then the patch rules see "Binary files
differ" instead of the lines. The checker ignores what it can, re-reads as text any file git calls binary although
its stored blobs hold no NUL in their first 8000 bytes (git's own test), and still reports a real binary as binary.
Each case runs twice: with GIT_ATTR_SOURCE set to the base (git 2.40 or later) and without it, as on an older git.
Real git repositories in tmp, a fake GitLab API, no network."""
import subprocess

import pytest

from itemator import ci
from test_ci import FakeHttp, Repo, isolated, issue, job, mr, routes  # noqa: F401  (autouse fixture)

TEST_A = "def test_a():\n    assert 1\n    assert 2\n    assert 3\n"
FEWER = "def test_a():\n    assert 1\n"          # the T24 fixture: two of three asserts removed


@pytest.fixture(params=[True, False], ids=["attr-source", "old-git"])
def attr_source(request, monkeypatch):
    monkeypatch.setattr(ci, "ATTR_SOURCE", request.param)
    return request.param


@pytest.fixture
def base_repo(tmp_path):
    r = Repo(tmp_path / "repo")
    r.base = r.commit({"src/parser.py": "x = 0\n", "tests/test_a.py": TEST_A, "README.md": "# demo\n"})
    return r


def config(**pairs):
    def setup(repo, tmp_path):
        for k, v in pairs.items():
            repo.git("config", k.replace("__", "."), v)
    return setup


def attributes_file(repo, tmp_path):
    (tmp_path / "attrs").write_text("* -diff\n")
    repo.git("config", "core.attributesFile", str(tmp_path / "attrs"))


def info_attributes(repo, tmp_path):
    (repo.path / ".git" / "info").mkdir(exist_ok=True)
    (repo.path / ".git" / "info" / "attributes").write_text("* -diff\n")


CASES = {
    "file -diff": ({".gitattributes": "tests/test_a.py -diff\n"}, None),
    "file binary": ({".gitattributes": "tests/test_a.py binary\n"}, None),
    "* -diff": ({".gitattributes": "* -diff\n"}, None),
    "* binary": ({".gitattributes": "* binary\n"}, None),
    "-text": ({".gitattributes": "*.py -text\n"}, None),
    "eol": ({".gitattributes": "*.py eol=crlf\n"}, None),
    "filter": ({".gitattributes": "*.py filter=evil\n"}, config(filter__evil__clean="true", filter__evil__smudge="true")),
    "textconv": ({".gitattributes": "*.py diff=evil\n"}, config(diff__evil__textconv="true")),
    "binary driver": ({".gitattributes": "*.py diff=evil\n"}, config(diff__evil__binary="true")),
    "subdirectory": ({"tests/.gitattributes": "test_a.py -diff\n"}, None),
    "attributesFile": ({}, attributes_file),
    "info/attributes": ({}, info_attributes),
}


@pytest.mark.parametrize("case", CASES)
def test_attributes_never_hide_a_removed_test(base_repo, tmp_path, monkeypatch, attr_source, case):
    files, setup = CASES[case]
    head = base_repo.commit({"tests/test_a.py": FEWER, **files})
    if setup:
        setup(base_repo, tmp_path)               # after the commit: a clean filter would rewrite what is stored
    f = {x["filename"]: x for x in ci.diff_files(str(base_repo.path), base_repo.base, head)}["tests/test_a.py"]
    assert "binary" not in f and "-    assert 3" in f["patch"] and (f["additions"], f["deletions"]) == (0, 2)
    code, out = job(base_repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch)
    assert code == 0 and out["state"] == "extras"
    assert ("tests_removed", "tests/test_a.py") in [(e["kind"], e["path"]) for e in out["extras"]]


@pytest.mark.parametrize("attrs", ["", "*.dat diff\n", "*.dat text\n", "* -binary diff\n"])
def test_a_real_binary_is_still_binary(base_repo, attr_source, attrs):
    blob = b"\0" + b"line\n" * 4000                       # a NUL in the first byte, lines after it
    base_repo.base = base_repo.commit({"data/old.dat": blob})
    files = {"data/new.dat": bytes(range(256)) * 40, "data/old.dat": blob + b"tail\n"}   # added; changed at the end only
    if attrs:
        files[".gitattributes"] = attrs
    head = base_repo.commit(files)
    out = {f["filename"]: f for f in ci.diff_files(str(base_repo.path), base_repo.base, head)}
    for path in ("data/new.dat", "data/old.dat"):
        assert out[path]["binary"] is True and out[path]["patch"] is None, path
    assert out["data/new.dat"]["size"] == 256 * 40


def test_a_text_file_git_calls_binary_is_read_as_text_with_its_rename(base_repo, attr_source):
    base_repo.git("mv", "tests/test_a.py", "tests/test_b.py")
    head = base_repo.commit({"tests/test_b.py": TEST_A.replace("assert 3", "assert 4"), ".gitattributes": "* -diff\n"})
    f = {x["filename"]: x for x in ci.diff_files(str(base_repo.path), base_repo.base, head)}["tests/test_b.py"]
    assert f["status"] == "renamed" and f["previous_filename"] == "tests/test_a.py" and "binary" not in f
    assert "-    assert 3\n+    assert 4" in f["patch"]


def test_every_git_call_ignores_attribute_files(base_repo, monkeypatch, attr_source):
    head = base_repo.commit({"tests/test_a.py": FEWER, "new.txt": "x\n", ".gitattributes": "* -diff\n"})
    calls, real = [], subprocess.run

    def spy(argv, **kw):
        calls.append((list(argv), kw.get("env") or {}))
        return real(argv, **kw)
    monkeypatch.setattr(ci.subprocess, "run", spy)
    ci.diff_files(str(base_repo.path), base_repo.base, head)
    assert len([c for c in calls if "diff" in c[0]]) >= 2
    for argv, env in calls:
        assert argv[:3] == ["git", "-c", "core.attributesFile=/dev/null"] and env.get("GIT_ATTR_NOSYSTEM") == "1"
        if "diff" in argv:
            assert "--no-textconv" in argv and "--no-ext-diff" in argv
            assert env.get("GIT_ATTR_SOURCE") == (base_repo.base if attr_source else None)
