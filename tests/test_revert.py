"""itemator/revert.py: does a change that says it reverts a commit really undo it? Read from real git repositories."""
import subprocess

import pytest

from itemator import checked as C
from itemator import ci
from itemator import revert as RV
from tests.test_reland import Repo

A = "def alpha(x):\n    y = compute(x)\n    log(y)\n    return y\n"
B = "def beta(x):\n    z = other(x)\n    save(z)\n    return z\n"


@pytest.fixture
def repo(tmp_path):
    r = Repo(tmp_path)
    r.base = r.commit({"a.py": "x = 1\n", "b.py": "w = 2\n"}, "start")
    r.bad = r.commit({"a.py": "x = 1\n" + A, "b.py": "w = 2\n" + B}, "Add alpha and beta")
    return r


def message(repo, sha=None):
    return f'Revert "Add alpha and beta"\n\nThis reverts commit {sha or repo.bad}.'


def test_a_full_revert_says_nothing(repo):
    repo.g("revert", "--no-edit", repo.bad)
    head = repo.g("rev-parse", "HEAD")
    files = repo.files_changed_by(head)
    assert RV.find(str(repo.path), message(repo), files, None, None, []) is None


def test_a_file_the_revert_leaves_out_is_named(repo):
    repo.commit({"a.py": "x = 1\n", "b.py": "w = 2\n" + B}, "Revert only a.py")
    files = repo.files_changed_by(repo.g("rev-parse", "HEAD"))
    d = RV.find(str(repo.path), message(repo), files, None, None, [])
    assert d == {"left": [{"id": repo.bad[:12], "title": "Add alpha and beta", "files": [{"path": "b.py", "missing": 4, "of": 4}]}], "beyond": [], "copy": False}
    s = RV.sentence(d)
    assert "`b.py` (4 of 4 lines still in place)" in s and "reverts `%s`" % repo.bad[:12] in s


def test_part_of_a_file_left_in_place_is_counted(repo):
    repo.commit({"a.py": "x = 1\ndef alpha(x):\n    log(y)\n", "b.py": "w = 2\n"}, "Revert, mostly")
    files = repo.files_changed_by(repo.g("rev-parse", "HEAD"))
    d = RV.find(str(repo.path), message(repo), files, None, None, [])
    assert d["left"][0]["files"] == [{"path": "a.py", "missing": 2, "of": 4}]


def test_one_stray_line_is_below_the_bar(repo):
    assert RV.MIN_MISSING == 2
    repo.commit({"a.py": "x = 1\n" + "def alpha(x):\n", "b.py": "w = 2\n"}, "Revert, nearly")
    files = repo.files_changed_by(repo.g("rev-parse", "HEAD"))
    assert RV.find(str(repo.path), message(repo), files, None, None, []) is None


def test_files_the_reverted_commit_did_not_touch_are_named(repo):
    repo.g("revert", "--no-edit", repo.bad)
    repo.commit({"c.py": "extra = 1\n"}, "and more")
    files = repo.files_changed_by(repo.g("rev-parse", "HEAD"))
    files = [{"filename": "a.py", "status": "modified", "patch": "@@ -1,5 +1,1 @@\n x = 1\n" + "".join("-" + l + "\n" for l in A.splitlines())},
             {"filename": "b.py", "status": "modified", "patch": "@@ -1,5 +1,1 @@\n w = 2\n" + "".join("-" + l + "\n" for l in B.splitlines())},
             {"filename": "c.py", "status": "added", "patch": "@@ -0,0 +1 @@\n+extra = 1\n"}]
    d = RV.find(str(repo.path), message(repo), files, None, None, [])
    assert d == {"left": [], "beyond": ["c.py"], "copy": False}
    assert RV.sentence(d).endswith("which the reverted commit did not touch.")


def test_a_partial_revert_is_left_alone(repo):
    assert RV.find(str(repo.path), message(repo) + "\n\nA partial revert.", [], None, None, []) is None


def test_a_change_that_cites_no_revert_is_not_read(repo):
    assert RV.find(str(repo.path), f"Fixes: {repo.bad}", [{"filename": "z.py", "status": "added", "patch": "@@ -0,0 +1 @@\n+z = 1\n"}], None, None, []) is None


def test_a_file_without_a_patch_is_unknown_never_left(repo):
    files = [{"filename": "a.py", "status": "modified", "patch": ""}, {"filename": "b.py", "status": "modified", "patch": ""}]
    assert RV.find(str(repo.path), message(repo), files, None, None, []) is None


def test_lines_of_a_removed_file_count(repo):
    r2 = repo.commit({"d.py": "def gamma(x):\n    return other(x)\n    # note\n"}, "Add gamma")
    files = [{"filename": "d.py", "status": "removed", "patch": "@@ -1,3 +0,0 @@\n-def gamma(x):\n-    return other(x)\n-    # note\n"}]
    assert RV.find(str(repo.path), f"This reverts commit {r2}", files, None, None, []) is None


def test_header_lines_are_not_content_but_a_removed_sql_comment_is():
    add, rem = RV.sides("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old line here\n+new line here\n--- sql comment\n")
    assert list(add) == ["new line here"] and sorted(rem) == ["-- sql comment", "old line here"]


class Api:
    def __init__(self, rows, title="Add alpha and beta"):
        self.rows, self.title, self.paths = rows, title, []

    def get(self, path, missing_ok=False):    # noqa: ARG002
        self.paths.append(path)
        return {"title": self.title} if path.endswith(("0" * 40,)) else (self.rows if "/diff" in path else {"title": self.title})


def test_a_commit_the_checkout_lacks_is_read_through_the_api(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    sha = "ab" * 20
    rows = [{"new_path": "a.py", "old_path": "a.py", "diff": "@@ -1 +1,5 @@\n x = 1\n+" + "\n+".join(A.splitlines()) + "\n"}]
    api = Api(rows)
    files = [{"filename": "a.py", "status": "modified", "patch": "@@ -1,5 +1 @@\n x = 1\n-" + "\n-".join(A.splitlines()) + "\n"}]
    assert RV.find(str(tmp_path), f"This reverts commit {sha}", files, api, 7, []) is None
    assert any(p.startswith(f"/projects/7/repository/commits/{sha}/diff") for p in api.paths)
    d = RV.find(str(tmp_path), f"This reverts commit {sha}", [{"filename": "q.py", "status": "added", "patch": "@@ -0,0 +1 @@\n+q = 1\n"}], api, 7, [])
    assert d["left"][0]["files"] == [{"path": "a.py", "missing": 4, "of": 4}] and d["beyond"] == ["q.py"]


def test_a_commit_nobody_can_read_warns_and_says_nothing(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    warn = []
    assert RV.find(str(tmp_path), "This reverts commit " + "cd" * 20, [], None, None, warn) is None and warn == []
    class Down:
        def get(self, *a, **k):
            raise ci.JobError("HTTP 500")
    assert RV.find(str(tmp_path), "This reverts commit " + "cd" * 20, [], Down(), 7, warn) is None
    assert len(warn) == 1 and warn[0].startswith("no revert check")


def test_the_card_carries_the_revert_line_between_cites_and_pipeline():
    d = {"left": [{"id": "abc1234", "title": "T", "files": [{"path": "b.py", "missing": 4, "of": 4}]}], "beyond": [], "copy": False}
    s = C.sentence([], [], [], [], {"added": ["j"], "removed": [], "changed": [], "global": []}, [], [], d)
    assert s.startswith("Also checked, with no model: As a revert") and s.index("As a revert") < s.index("The project's pipeline")
    assert C.sentence([], [], [], [], None, [], [], None) is None


def test_also_checked_puts_the_revert_in_the_report_and_never_changes_the_state(repo):
    repo.commit({"a.py": "x = 1\n", "b.py": "w = 2\n" + B}, "Revert only a.py")
    head = repo.g("rev-parse", "HEAD")
    files = repo.files_changed_by(head)
    report = {"extras": [], "warnings": [], "card": {}, "state": "clean"}
    ci.also_checked(report, str(repo.path), repo.bad, head, files, None, None, message(repo))
    assert report["checked"]["revert"]["left"][0]["files"][0]["path"] == "b.py"
    assert "As a revert" in report["card"]["checked_line"] and report["state"] == "clean"


def mr(*rows):
    return [{"filename": n, "status": st, "patch": p, **({"previous_filename": prev} if prev else {})} for n, st, p, prev in rows]


def test_an_untouched_file_is_named_for_one_line(repo):
    r2 = repo.commit({"e.py": "setting = enabled\n"}, "Add e")
    d = RV.find(str(repo.path), f"This reverts commit {r2}", mr(("z.py", "added", "@@ -0,0 +1 @@\n+z = 1\n", None)), None, None, [])
    assert d["left"] == [{"id": r2[:12], "title": "Add e", "files": [{"path": "e.py", "missing": 1, "of": 1}]}]


def test_lines_too_short_to_tell_are_not_counted(repo):
    r2 = repo.commit({"f.py": "}\n)\n]\n"}, "Add f")
    d = RV.find(str(repo.path), f"This reverts commit {r2}", mr(("f.py", "modified", "@@ -1 +1 @@\n-keep\n+kept\n", None)), None, None, [])
    assert d is None


def test_a_renamed_file_is_not_beyond(repo):
    repo.g("revert", "--no-edit", repo.bad)
    files = mr(("a.py", "modified", "@@ -1,5 +1 @@\n x = 1\n" + "".join("-" + l + "\n" for l in A.splitlines()), None),
               ("b.py", "removed", "@@ -1,5 +0,0 @@\n" + "".join("-" + l + "\n" for l in ["w = 2"] + B.splitlines()), None),
               ("b2.py", "renamed", "@@ -0,0 +1 @@\n+w = 2\n", "b.py"))
    assert RV.find(str(repo.path), message(repo), files, None, None, []) is None


def test_a_line_added_three_times_must_be_removed_three_times(repo):
    r2 = repo.commit({"g.py": "foo()\nfoo()\nfoo()\nbar()\n"}, "Add g")
    d = RV.find(str(repo.path), f"This reverts commit {r2}", mr(("g.py", "modified", "@@ -1,4 +1,2 @@\n-foo()\n foo()\n-bar()\n", None)), None, None, [])
    assert d["left"][0]["files"] == [{"path": "g.py", "missing": 2, "of": 4}]


def test_a_reverted_commit_of_too_many_files_is_not_read(repo):
    big = repo.commit({f"many/f{i}.py": f"value_{i} = {i}{i}\n" for i in range(RV.MAX_FILES + 1)}, "Add many")
    warn = []
    assert RV.find(str(repo.path), f"This reverts commit {big}", mr(("z.py", "added", "@@ -0,0 +1 @@\n+z = 1\n", None)), None, None, warn) is None
    assert warn == [f"no revert check on {big[:12]}: the commit could not be read"]


# --- copies: cherry-pick -x and stable "commit <id> upstream" ---------------------------------------------------------------

def copy_of(repo, files, how="cherry picked from commit {}", **kw):
    return RV.find(str(repo.path), "Backport\n\n(" + how.format(repo.bad) + ")", files, None, None, [], copy=True, **kw)


def test_a_faithful_copy_says_nothing(repo):
    # the copy is the same change, so its diff adds what the original added
    files = mr(("a.py", "modified", "@@ -1 +1,5 @@\n x = 1\n" + "".join("+" + l + "\n" for l in A.splitlines()), None),
               ("b.py", "modified", "@@ -1 +1,5 @@\n w = 2\n" + "".join("+" + l + "\n" for l in B.splitlines()), None))
    assert copy_of(repo, files) is None


def test_a_copy_that_leaves_out_a_file_or_lines_is_named(repo):
    files = mr(("a.py", "modified", "@@ -1 +1,3 @@\n x = 1\n+def alpha(x):\n+    log(y)\n", None))
    d = copy_of(repo, files)
    assert d["copy"] is True
    assert d["left"][0]["files"] == [{"path": "a.py", "missing": 2, "of": 4}, {"path": "b.py", "missing": 4, "of": 4}]
    s = RV.sentence(d)
    assert s.startswith("As a copy, this change differs from what it copies") and "is a copy of" in s and "lines missing" in s


def test_a_copy_that_changes_other_files_names_them(repo):
    files = mr(("a.py", "modified", "@@ -1 +1,5 @@\n x = 1\n" + "".join("+" + l + "\n" for l in A.splitlines()), None),
               ("b.py", "modified", "@@ -1 +1,5 @@\n w = 2\n" + "".join("+" + l + "\n" for l in B.splitlines()), None),
               ("c.py", "added", "@@ -0,0 +1 @@\n+extra = 1\n", None))
    d = copy_of(repo, files)
    assert d == {"left": [], "beyond": ["c.py"], "copy": True} and "which the original commit did not touch" in RV.sentence(d)


@pytest.mark.parametrize("how", ["cherry picked from commit {}", "commit {} upstream.", "[ Upstream commit {} ]"])
def test_each_way_of_naming_the_original_is_read(repo, how):
    assert copy_of(repo, mr(("z.py", "added", "@@ -0,0 +1 @@\n+z = 1\n", None)), how)["left"]


def test_a_copy_check_does_not_read_a_revert_or_a_fix(repo):
    q = mr(("z.py", "added", "@@ -0,0 +1 @@\n+z = 1\n", None))
    assert RV.find(str(repo.path), f"This reverts commit {repo.bad}", q, None, None, [], copy=True) is None
    assert RV.find(str(repo.path), f"Fixes: {repo.bad}", q, None, None, [], copy=True) is None
    assert RV.find(str(repo.path), f"(cherry picked from commit {repo.bad})", q, None, None, []) is None


def test_the_card_carries_a_copy_line(repo):
    d = {"left": [{"id": "abc1234", "title": "T", "files": [{"path": "b.py", "missing": 4, "of": 4}]}], "beyond": [], "copy": True}
    s = C.sentence([], [], [], [], None, [], [], None, [], None, d)
    assert s.startswith("Also checked, with no model: As a copy")


def test_an_unreadable_original_warns_by_name(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    class Down:
        def get(self, *a, **k):
            raise ci.JobError("HTTP 500")
    warn = []
    assert RV.find(str(tmp_path), "(cherry picked from commit " + "ef" * 20 + ")", [], Down(), 7, warn, copy=True) is None
    assert warn == ["no copy check on " + "ef" * 6 + ": the commit could not be read"]


def test_hidden_files_are_not_extra_changes(repo):
    files = mr(("a.py", "modified", "@@ -1 +1,5 @@\n x = 1\n" + "".join("+" + l + "\n" for l in A.splitlines()), None),
               ("b.py", "modified", "@@ -1 +1,5 @@\n w = 2\n" + "".join("+" + l + "\n" for l in B.splitlines()), None),
               (".pick_status.json", "modified", "@@ -1 +1 @@\n-1\n+2\n", None),
               ("sub/.ci-farms/x", "added", "@@ -0,0 +1 @@\n+x\n", None))
    assert copy_of(repo, files) is None
    d = copy_of(repo, files + mr(("c.py", "added", "@@ -0,0 +1 @@\n+c = 1\n", None)))
    assert d["beyond"] == ["c.py"]
    assert RV._hidden(".github/x.yml") and RV._hidden("a/.b") and not RV._hidden("a/b.c") and not RV._hidden("a/b.")
