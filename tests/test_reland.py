"""itemator/reland.py: lines a change adds back that an earlier commit took out, read from real git repositories."""
import subprocess

import pytest

from itemator import checked as C
from itemator import reland as RL

BLOCK = ("def connect(host):\n"
         "    sock = open_socket(host, timeout=30)\n"
         "    sock.set_keepalive(True)\n"
         "    register(sock)\n"
         "    return sock\n")
OTHER = "def close(sock):\n    sock.close()\n"


class Repo:
    def __init__(self, path):
        self.path = path
        self.g("init", "-q", "-b", "main")

    def g(self, *a):
        return subprocess.run(["git", "-C", str(self.path), "-c", "user.email=a@b.c", "-c", "user.name=t", "-c", "commit.gpgsign=false", *a],
                              check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, files, msg):
        for name, text in files.items():
            (self.path / name).parent.mkdir(parents=True, exist_ok=True)
            (self.path / name).write_text(text)
        self.g("add", "-A")
        self.g("commit", "-qm", msg)
        return self.g("rev-parse", "HEAD")

    def files_changed_by(self, sha):
        out = []
        for line in self.g("diff-tree", "--no-commit-id", "-r", "--name-status", sha).splitlines():
            st, path = line.split("\t")
            patch = self.g("diff", "-U3", f"{sha}^", sha, "--", path)
            out.append({"filename": path, "status": "modified" if st == "M" else "added", "patch": patch[patch.find("@@"):] if "@@" in patch else ""})
        return out


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


def relanded_repo(repo, subject="Revert \"Keep the connection alive\""):
    repo.commit({"net.py": OTHER + "\n" + BLOCK}, "Keep the connection alive")
    repo.commit({"net.py": OTHER}, subject)
    repo.commit({"other.py": "x = 1\n"}, "Unrelated")
    base = repo.commit({"other.py": "x = 2\n"}, "Unrelated again")
    head = repo.commit({"net.py": OTHER + "\n" + BLOCK}, "Add the connection helper")
    return base, head


def test_a_change_that_adds_back_what_a_revert_removed_names_the_revert(repo):
    base, head = relanded_repo(repo)
    out = RL.find(str(repo.path), base, repo.files_changed_by(head))
    assert len(out["relanded"]) == 1
    d = out["relanded"][0]
    assert d["path"] == "net.py" and d["lines"] == 5 and d["revert"] is True and d["subject"] == "Revert \"Keep the connection alive\""
    assert len(d["commit"]) == 8 and len(d["date"]) == 10


def test_a_removal_that_is_not_a_revert_is_named_only_when_asked_for(repo):
    base, head = relanded_repo(repo, subject="Drop the keepalive helper")
    files = repo.files_changed_by(head)
    assert RL.find(str(repo.path), base, files)["relanded"] == []
    got = RL.find(str(repo.path), base, files, revert_only=False)["relanded"]
    assert len(got) == 1 and got[0]["revert"] is False


def test_lines_that_were_never_removed_are_not_named(repo):
    repo.commit({"net.py": OTHER}, "start")
    base = repo.commit({"other.py": "x = 1\n"}, "other")
    head = repo.commit({"net.py": OTHER + "\n" + BLOCK}, "Add the connection helper")
    assert RL.find(str(repo.path), base, repo.files_changed_by(head))["relanded"] == []


def test_a_run_too_small_to_name_a_history_for_is_skipped(repo):
    repo.commit({"net.py": OTHER + "a = 1\nb = 2\n"}, "x")
    repo.commit({"net.py": OTHER}, "Revert \"x\"")
    base = repo.commit({"o.py": "1\n"}, "o")
    head = repo.commit({"net.py": OTHER + "a = 1\nb = 2\n"}, "y")
    assert RL.find(str(repo.path), base, repo.files_changed_by(head))["relanded"] == []
    assert RL.worth_looking_up(["a = 1", "b = 2", "c = 3"]) is None            # three lines but under 60 characters
    assert RL.worth_looking_up(["# c", "", "x" * 30, "y" * 30]) is None        # comments and blanks do not count


def test_comments_and_blank_lines_do_not_stop_a_match(repo):
    spaced = BLOCK.replace("    register(sock)\n", "\n    # make it visible\n    register(sock)\n")
    repo.commit({"net.py": OTHER + "\n" + BLOCK}, "Keep the connection alive")
    repo.commit({"net.py": OTHER}, "Revert \"Keep the connection alive\"")
    base = repo.commit({"o.py": "1\n"}, "o")
    head = repo.commit({"net.py": OTHER + "\n" + spaced}, "Again")
    assert len(RL.find(str(repo.path), base, repo.files_changed_by(head))["relanded"]) == 1


def test_a_commit_that_moved_the_lines_instead_of_removing_them_is_not_named(repo):
    repo.commit({"net.py": BLOCK + "\n" + OTHER}, "start")
    repo.commit({"net.py": OTHER + "\n" + BLOCK}, "Revert \"reorder\"")           # same lines, new place
    base = repo.commit({"o.py": "1\n"}, "o")
    head = repo.commit({"net.py": OTHER + "\n" + BLOCK + "\n" + BLOCK}, "second copy")
    assert RL.find(str(repo.path), base, repo.files_changed_by(head))["relanded"] == []


def test_lines_taken_out_by_two_different_commits_are_not_named(repo):
    lines = BLOCK.splitlines(True)
    repo.commit({"net.py": OTHER + "\n" + BLOCK}, "k")
    repo.commit({"net.py": OTHER + "\n" + "".join(lines[2:])}, "Revert \"k\" part one")           # the first two lines
    repo.commit({"net.py": OTHER}, "Revert \"k\" part two")                                         # the other three
    base = repo.commit({"o.py": "1\n"}, "o")
    head = repo.commit({"net.py": OTHER + "\n" + BLOCK}, "again")
    assert RL.find(str(repo.path), base, repo.files_changed_by(head))["relanded"] == []


def test_the_newest_commit_that_removed_the_lines_is_the_one_named(repo):
    repo.commit({"net.py": OTHER + "\n" + BLOCK}, "k")
    repo.commit({"net.py": OTHER}, "Revert \"k\"")
    repo.commit({"net.py": OTHER + "\n" + BLOCK}, "Reland \"k\"")
    newest = repo.commit({"net.py": OTHER}, "Revert \"Reland k\"")
    base = repo.commit({"o.py": "1\n"}, "o")
    head = repo.commit({"net.py": OTHER + "\n" + BLOCK}, "again")
    got = RL.find(str(repo.path), base, repo.files_changed_by(head))["relanded"]
    assert [d["commit"] for d in got] == [newest[:8]]


def test_the_caps_stop_the_reading_and_say_so(repo, monkeypatch):
    block2 = BLOCK.replace("connect", "connect2").replace("sock", "sk")
    base = repo.commit({"net.py": OTHER + "sep = 1\n"}, "start")
    head = repo.commit({"net.py": OTHER + BLOCK + "sep = 1\n" + block2}, "two separate runs")
    files = repo.files_changed_by(head)
    assert len(RL.runs(files[0]["patch"], "+")) == 2
    assert RL.find(str(repo.path), base, files)["runs_read"] == 2
    monkeypatch.setattr(RL, "MAX_RUNS_PER_FILE", 1)
    out = RL.find(str(repo.path), base, files)
    assert out["runs_read"] == 1 and out["capped"] is True
    monkeypatch.setattr(RL, "MAX_RUNS_PER_FILE", 5)
    monkeypatch.setattr(RL, "MAX_RUNS", 1)
    assert RL.find(str(repo.path), base, files)["capped"] is True


def test_test_files_are_skipped(repo):
    repo.commit({"tests/test_net.py": OTHER + "\n" + BLOCK}, "k")
    repo.commit({"tests/test_net.py": OTHER}, "Revert \"k\"")
    base = repo.commit({"o.py": "1\n"}, "o")
    head = repo.commit({"tests/test_net.py": OTHER + "\n" + BLOCK}, "again")
    assert RL.find(str(repo.path), base, repo.files_changed_by(head))["relanded"] == []


def test_a_sweeping_revert_is_not_named(repo):
    repo.commit({"net.py": OTHER + "\n" + BLOCK}, "k")
    repo.commit({"net.py": OTHER, **{f"f{i}.txt": str(i) for i in range(RL.MAX_COMMIT_FILES + 2)}}, "Revert \"everything\"")
    base = repo.commit({"o.py": "1\n"}, "o")
    head = repo.commit({"net.py": OTHER + "\n" + BLOCK}, "again")
    assert RL.find(str(repo.path), base, repo.files_changed_by(head))["relanded"] == []


def test_runs_are_read_from_a_unified_diff():
    patch = "@@ -1,3 +1,4 @@\n a\n-b\n-c\n+d\n+e\n+f\n g\n+h\n"
    assert RL.runs(patch, "-") == [["b", "c"]] and RL.runs(patch, "+") == [["d", "e", "f"], ["h"]]


def test_the_card_sentence_names_the_revert():
    d = {"path": "net.py", "lines": 5, "commit": "abcd1234", "date": "2026-03-02", "subject": "Revert \"x\"", "revert": True}
    s = C.sentence([], [], relanded=[d])
    assert s == ("Also checked, with no model: This change adds back lines that a revert removed earlier: "
                 "`net.py` (5 lines, removed by `abcd1234`, \"Revert \"x\"\", 2026-03-02).")
    assert C.sentence([], [], relanded=[]) is None
    many = C.sentence([], [], relanded=[d] * 5)
    assert many is not None and many.count("`net.py`") == 3 and many.endswith("and 2 more.")


def test_a_check_that_breaks_warns_and_says_nothing(tmp_path):
    warn = []
    out = C.reland_check(str(tmp_path / "missing"), "b" * 40, [{"filename": "a.py", "status": "modified", "patch": "@@ -1 +1,3 @@\n+" + "\n+".join(["x" * 30] * 3)}], warn)
    assert out["relanded"] == []        # git cannot read the repository: no candidates, no crash


def test_a_diff_that_removes_and_re_adds_the_same_lines_is_a_move_not_a_removal():
    wanted = [l.strip() for l in BLOCK.splitlines()]
    removal = "@@ -1,5 +0,0 @@\n" + "".join(f"-{l}\n" for l in BLOCK.splitlines())
    moved = removal + "@@ -9,0 +5,5 @@\n" + "".join(f"+{l}\n" for l in BLOCK.splitlines())
    assert RL.removed_it(removal, wanted) is True
    assert RL.removed_it(moved, wanted) is False
