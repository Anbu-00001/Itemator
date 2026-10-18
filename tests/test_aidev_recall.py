"""Leg 1 of the recall work: the pure parts of eval/aidev_recall.py."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import aidev_recall as A  # noqa: E402
from itemator.extras import Extra  # noqa: E402


def row(sha, name, status="modified", patch=None):
    return {"sha": sha, "filename": name, "status": status, "patch": patch}


def test_listable_kind_from_the_path_alone():
    want = {"package.json": "dependency", "requirements.txt": "dependency", ".github/workflows/ci.yml": "ci_or_config",
            "AGENTS.md": "agent_instructions", ".github/copilot-instructions.md": "agent_instructions", "logo.png": "binary",
            "src/app.py": None, "tests/test_a.py": None, "docs/guide.md": None, "src/gen/api.pb.go": "generated",
            "tests/fixtures/img.png": "binary", "LICENSE": None}
    assert {p: A.listable_kind(p) for p in want} == want


def test_listed_names_the_file_a_directory_or_a_mass_event_file():
    ex = [Extra("stray_file", "tmp/", "tmp/", "x"), Extra("ci_or_config", ".github/a.yml", "a", "x"),
          Extra("version_bump", "", "v", "x", detail=("pkg/a.json", 3))]
    assert A.listed(ex, "tmp/out.txt") and A.listed(ex, ".github/a.yml") and A.listed(ex, "pkg/a.json")
    assert not A.listed(ex, "tmp") and not A.listed(ex, ".github/a.yml.bak") and not A.listed(ex, "src/a.py")
    assert not A.listed([], "x")
    assert not A.listed([Extra("stray_file", "pkg", "pkg", "x")], "pkg/a.py")      # a name without a trailing slash is a file


def test_net_files_stop_at_the_commented_commit():
    rows = [row("c1", "a.py", "added", "+1"), row("c1", "b.py", "added", "+b"), row("c2", "a.py", "modified", "+2"),
            row("c2", "b.py", "removed", "-b"), row("c2", "c.py", "added", "+c"), row("c3", "d.py", "added", "+d"),
            row("c3", "old.py", "removed", "-o"), row("c3", "e.py", "modified", "+e")]
    at2 = {f["filename"]: f for f in A.net_files(rows, "c2")}
    assert set(at2) == {"a.py", "c.py"}                     # b.py was added and removed; d.py came later
    assert at2["a.py"]["status"] == "added" and at2["a.py"]["patch"] == "+1\n+2"
    at3 = {f["filename"]: f["status"] for f in A.net_files(rows, "c3")}
    assert at3 == {"a.py": "added", "c.py": "added", "d.py": "added", "old.py": "removed", "e.py": "modified"}
    assert {f["filename"] for f in A.net_files(rows, "c1")} == {"a.py", "b.py"}
    assert A.net_files(rows, "nope") is None and A.net_files([], "c1") is None
    assert A.net_files([row("c1", "x.py", "removed"), row("c2", "x.py", "added")], "c2")[0]["status"] == "modified"


def test_task_text_prefers_the_linked_issue():
    pr = {"title": "T", "body": "B"}
    assert A.task_text({"title": "I", "body": "J"}, pr) == ("I\nJ", "linked_issue")
    assert A.task_text({"title": "", "body": None}, pr) == ("T\nB", "pr_text")
    assert A.task_text(None, {"title": "T", "body": None}) == ("T\n", "pr_text")


def test_score_hits_and_the_title_only_variant():
    pr = {"html_url": "https://github.com/o/r/pull/1", "agent": "Copilot", "state": "closed", "merged_at": None, "title": "Add README blurb"}
    files = [{"filename": "README.md", "status": "modified", "patch": "+hello"},
             {"filename": ".github/workflows/ci.yml", "status": "modified", "patch": "@@\n-a\n+b"}]
    case = {"comment_id": 7, "path": ".github/workflows/ci.yml"}
    # the PR text names the workflow, the title does not: only the title-only run lists the change
    r = A.score(case, files, ("Add README blurb\nalso tweaks the workflow", "pr_text"), pr, "o/r", 6)
    assert (r["readable"], r["state"], r["kind"], r["task_from"], r["hit"], r["hit_title_only"]) == (True, "closed", "ci_or_config", "pr_text", False, True)
    u = A.score(case, None, ("x", "pr_text"), pr, "o/r", 6)
    assert (u["readable"], u["hit"], u["hit_title_only"]) == (False, None, None)
    assert A.score({"comment_id": 8, "path": "README.md"}, files, ("Add README blurb\n", "pr_text"), dict(pr, merged_at="2026-01-01"), "o/r", 6)["state"] == "merged"


def test_share_leaves_out_what_could_not_be_read():
    assert A.share([{"hit": None}, {"hit": True}, {"hit": False}]) == {"comments": 2, "listed": 1, "wilson95": [0.095, 0.905]}


def test_score_runs_the_rules_version_it_was_given(monkeypatch):
    seen = []
    monkeypatch.setattr(A.X, "analyse", lambda t, f, repo=None, version=6: seen.append(version) or A.X.Analysis(extras=[]))
    A.score({"comment_id": 1, "path": "a"}, [], ("t", "pr_text"), {"html_url": "u"}, "o/r", 5)
    assert seen == [5, 5]


def test_summary_counts_unreadable_apart():
    def r(pr, hit, kind=None, agent="Copilot", state="merged", task="pr_text", readable=True):
        return {"comment_id": 0, "pr": pr, "agent": agent, "state": state, "path": "p", "kind": kind, "task_from": task,
                "readable": readable, "hit": hit if readable else None, "hit_title_only": (not hit) if readable else None}
    rows = [r("a", True, "ci_or_config"), r("a", False), r("b", False, "dependency", "Devin", "closed", "linked_issue"),
            r("c", None, readable=False), r("d", True, "binary", "Devin")]
    s = A.summarize(rows)
    assert (s["comments"], s["unreadable"]) == (5, 1)
    assert s["all"] == {"comments": 4, "listed": 2, "wilson95": [0.15, 0.85]}
    assert (s["on_a_listable_kind"]["comments"], s["on_a_listable_kind"]["listed"]) == (3, 2)
    assert (s["on_other_files"]["comments"], s["on_other_files"]["listed"]) == (1, 0)
    assert s["by_agent"]["Devin"]["comments"] == 2 and s["by_state"]["closed"]["comments"] == 1
    assert s["by_task"]["linked_issue"]["comments"] == 1 and s["by_kind"]["None"]["comments"] == 1
    assert s["pull_requests"] == {"with_a_comment": 3, "with_a_listed_comment": 2}
    assert (s["title_only_all"]["comments"], s["title_only_all"]["listed"]) == (4, 2)
    assert s["title_only_on_a_listable_kind"]["listed"] == 1


def test_html_url():
    assert A.html_url("https://api.github.com/repos/o/r/pulls/12") == "https://github.com/o/r/pull/12"
    assert A.html_url("https://example.com/x") == "https://example.com/x"
    assert A.html_url("https://api.github.com/repos/o/r/pulls/12/files") == "https://api.github.com/repos/o/r/pulls/12/files"


def test_cases_keep_human_comments_once_in_id_order():
    import aidev_cases as C
    rows = [{"id": 9, "user_type": "User", "path": "b", "pull_request_url": "u2", "original_commit_id": "c2", "body": "secret text"},
            {"id": 3, "user_type": "User", "path": "a", "pull_request_url": "u1", "original_commit_id": "c1", "body": "x"},
            {"id": 3, "user_type": "User", "path": "a", "pull_request_url": "u1", "original_commit_id": "c1", "body": "x"},
            {"id": 5, "user_type": "Bot", "path": "a", "pull_request_url": "u1", "original_commit_id": "c1"},
            {"id": 6, "user_type": "User", "path": None, "pull_request_url": "u1", "original_commit_id": "c1"}]
    assert C.select(rows) == [{"comment_id": 3, "pull_request_url": "u1", "path": "a", "original_commit_id": "c1"},
                              {"comment_id": 9, "pull_request_url": "u2", "path": "b", "original_commit_id": "c2"}]
