"""itemator/record.py: does the project keep a written record per change, and does this change add one? Real git repositories."""
import subprocess

import pytest

from itemator import checked as C
from itemator import ci
from itemator import record as RC
from tests.test_reland import Repo


def build(tmp_path, with_record, without, record="changes/{i}.txt"):
    """A history of `with_record` code commits that add a record file and `without` that do not."""
    r = Repo(tmp_path)
    r.commit({"src/a.py": "x = 0\n"}, "start")
    n = 0
    for _ in range(with_record):
        n += 1
        r.commit({"src/a.py": f"x = {n}\n", record.format(i=n): f"note {n}\n"}, f"change {n}")
    for _ in range(without):
        n += 1
        r.commit({"src/a.py": f"x = {n}\n"}, f"change {n}")
    return r


def change(*paths, status="modified"):
    return [{"filename": p, "status": status, "patch": "@@ -1 +1 @@\n-a\n+b\n"} for p in paths]


@pytest.mark.parametrize("path,kind", [
    ("changes/1234.txt", "changes/"), ("a/b/changelog.d/x.md", "changelog.d/"), ("newsfragments/12.bugfix", "newsfragments/"),
    (".changeset/brave-owls.md", ".changeset/"), ("releasenotes/notes/x.yaml", "releasenotes/notes/"), ("CHANGELOG.md", "CHANGELOG.md"),
    ("docs/NEWS", "NEWS"), ("pkg/HISTORY.rst", "HISTORY.rst"), ("RELEASE_NOTES.md", "RELEASE_NOTES.md"),
])
def test_a_record_path_is_recognised(path, kind):
    assert RC.kind_of(path) == kind


@pytest.mark.parametrize("path", ["src/changes.py", "changes/", "news.py", "src/newsletter/a.py", "CHANGELOGS/x", "docs/history.py"])
def test_other_paths_are_not_records(path):
    assert RC.kind_of(path) is None


def test_shipped_files_leave_out_tests_docs_pipeline_hidden_and_records():
    for p in ("src/a.py", "lib/x.c", "app/main.go", "Makefile", "setup.cfg"):
        assert RC.shipped(p), p
    for p in ("tests/test_a.py", "docs/guide.md", "README.md", ".gitlab-ci.yml", ".github/workflows/x.yml", ".editorconfig", "changes/1.txt", "CHANGELOG.md", "uv.lock", "src/a_test.go"):
        assert not RC.shipped(p), p


def test_a_project_with_the_habit_is_seen(tmp_path):
    r = build(tmp_path, 8, 4)
    assert RC.convention(str(tmp_path), "HEAD") == {"kind": "changes/", "of": 13, "with": 8}


def test_a_project_without_the_habit_is_not(tmp_path):
    build(tmp_path, 3, 12)
    assert RC.convention(str(tmp_path), "HEAD") is None


def test_too_little_history_is_not_a_habit(tmp_path):
    build(tmp_path, 5, 0)
    assert RC.convention(str(tmp_path), "HEAD") is None                  # 6 code commits


def test_the_share_and_the_count_both_matter(tmp_path):
    build(tmp_path, 4, 6)                                                # 4 of 11, below the count
    assert RC.convention(str(tmp_path), "HEAD") is None
    build_dir = tmp_path / "second"
    build_dir.mkdir()
    build(build_dir, 6, 14)                                              # 6 of 21, below the share
    assert RC.convention(str(build_dir), "HEAD") is None


def test_merge_commits_are_not_counted(tmp_path):
    r = build(tmp_path, 8, 4)
    r.g("checkout", "-q", "-b", "side")
    r.commit({"src/b.py": "y = 1\n"}, "side work")
    r.g("checkout", "-q", "main")
    r.commit({"src/c.py": "z = 1\n"}, "main work")
    r.g("merge", "-q", "--no-ff", "-m", "merge side", "side")
    assert RC.convention(str(tmp_path), "HEAD")["of"] == 15             # 13 + side + main, not the merge


def test_a_change_to_shipped_files_without_a_record_is_named(tmp_path):
    build(tmp_path, 8, 4)
    d = RC.find(str(tmp_path), "HEAD", change("src/a.py", "tests/test_a.py", "docs/a.md"))
    assert d == {"kind": "changes/", "of": 13, "with": 8, "shipped": ["src/a.py"], "exempt": 2}
    s = RC.sentence(d)
    assert "8 of the last 13 commits" in s and "in changes/" in s and "`src/a.py`" in s and s.endswith("adds none.")


def test_a_change_that_adds_a_record_is_fine(tmp_path):
    build(tmp_path, 8, 4)
    assert RC.find(str(tmp_path), "HEAD", change("src/a.py") + change("changes/99.txt", status="added")) is None
    assert RC.find(str(tmp_path), "HEAD", change("src/a.py", "CHANGELOG.md")) is None


def test_a_layout_only_change_needs_no_record(tmp_path):
    build(tmp_path, 8, 4)
    assert RC.find(str(tmp_path), "HEAD", change("src/a.py"), {"src/a.py"}) is None
    d = RC.find(str(tmp_path), "HEAD", change("src/a.py", "src/b.py"), {"src/a.py"})
    assert d["shipped"] == ["src/b.py"] and d["exempt"] == 1


def test_a_change_that_touches_nothing_shipped_needs_no_record(tmp_path):
    build(tmp_path, 8, 4)
    assert RC.find(str(tmp_path), "HEAD", change("tests/test_a.py", "README.md", ".gitlab-ci.yml")) is None


@pytest.mark.parametrize("text", ["No changelog needed.", "[skip changelog]", "no news please", "skip release notes", "no_news_changes_needed", "NO CHANGES FILE"])
def test_a_text_that_says_no_record_is_needed_is_respected(tmp_path, text):
    build(tmp_path, 8, 4)
    assert RC.find(str(tmp_path), "HEAD", change("src/a.py"), text=text) is None


def test_a_project_without_the_habit_gets_nothing(tmp_path):
    build(tmp_path, 1, 14)
    assert RC.find(str(tmp_path), "HEAD", change("src/a.py")) is None


def test_the_names_are_capped(tmp_path):
    build(tmp_path, 8, 4)
    s = RC.sentence(RC.find(str(tmp_path), "HEAD", change(*[f"src/f{i}.py" for i in range(5)])))
    assert s.count("`src/f") == 3 and "and 2 more" in s


def test_the_card_carries_the_record_line_before_the_pipeline_line():
    d = {"kind": "changes/", "of": 13, "with": 8, "shipped": ["src/a.py"], "exempt": 0}
    s = C.sentence([], [], [], [], {"added": ["j"], "removed": [], "changed": [], "global": []}, [], [], None, [], d)
    assert s.startswith("Also checked, with no model: This project keeps a record per change") and s.index("keeps a record") < s.index("The project's pipeline")
    assert C.sentence([], [], [], [], None, [], [], None, [], None) is None


def test_also_checked_reports_the_missing_record_and_never_changes_the_state(tmp_path):
    r = build(tmp_path, 8, 4)
    base = r.g("rev-parse", "HEAD")
    head = r.commit({"src/a.py": "x = 'new'\n"}, "no note")
    report = {"extras": [], "warnings": [], "card": {}, "state": "clean"}
    ci.also_checked(report, str(tmp_path), base, head, r.files_changed_by(head), None, None, "A change")
    assert report["checked"]["record"]["shipped"] == ["src/a.py"] and "keeps a record per change" in report["card"]["checked_line"]
    assert report["state"] == "clean"
    report2 = {"extras": [], "warnings": [], "card": {}}
    ci.also_checked(report2, str(tmp_path), base, head, r.files_changed_by(head), None, None, "A change [skip changelog]")
    assert report2["checked"]["record"] is None


def test_the_count_bar_holds_when_the_share_is_met(tmp_path):
    build(tmp_path, 4, 5)                                                # 10 code commits, 4 with a record: 0.4 but only 4
    assert RC.convention(str(tmp_path), "HEAD") is None


def test_the_share_bar_is_inclusive(tmp_path):
    build(tmp_path, 6, 8)                                                # 15 code commits, 6 with a record: exactly 0.4
    assert RC.convention(str(tmp_path), "HEAD") == {"kind": "changes/", "of": 15, "with": 6}


def test_pipeline_files_in_ci_folders_are_not_shipped(tmp_path):
    build(tmp_path, 8, 4)
    assert RC.find(str(tmp_path), "HEAD", change("ci/build.yml")) is None


def test_a_commit_that_only_adds_a_record_is_not_a_code_commit(tmp_path):
    r = build(tmp_path, 8, 4)
    for i in range(10):
        r.commit({f"changes/late{i}.bugfix": "late note\n"}, f"add missing changes file {i}")
    assert RC.convention(str(tmp_path), "HEAD") == {"kind": "changes/", "of": 13, "with": 8}
