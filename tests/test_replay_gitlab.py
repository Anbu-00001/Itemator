"""The public replay's own parts: GitLab diffs become the CI job's file list, the flow's merge requests and versions are
told apart from a person's, and the card is the CI job's own (itemator.ci.facts)."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import replay_gitlab as G  # noqa: E402

FLOW = {"author_name": "Duo Developer", "author_email": "service_account_group_9970_x@noreply.gitlab.com"}
PERSON = {"author_name": "A Person", "author_email": "person@example.com"}


def test_a_gitlab_diff_becomes_the_file_list_the_rules_take():
    files = G.to_files([
        {"new_path": "README.md", "old_path": "README.md", "diff": "@@ -1 +1 @@\n-a\n+b\n"},
        {"new_path": "Dockerfile", "old_path": "Dockerfile", "new_file": True, "diff": "@@ -0,0 +1 @@\n+FROM x"},
        {"new_path": "b.py", "old_path": "a.py", "renamed_file": True, "diff": ""},
        {"new_path": "gone.txt", "old_path": "gone.txt", "deleted_file": True, "diff": "@@ -1 +0,0 @@\n-x\n"},
        {"new_path": "big.json", "old_path": "big.json", "too_large": True, "diff": "@@ -1 +1 @@\n-a\n+b\n"}])
    assert [f["status"] for f in files] == ["modified", "added", "renamed", "removed", "modified"]
    assert files[0]["additions"] == 1 and files[0]["deletions"] == 1 and files[0]["patch"].endswith("\n")
    assert files[1]["patch"] == "@@ -0,0 +1 @@\n+FROM x\n"
    assert files[2]["previous_filename"] == "a.py" and files[2]["patch"] is None
    assert files[4]["patch"] is None and files[4]["withheld"] is True and "withheld" not in files[0]


def test_only_the_flow_accounts_own_note_makes_a_merge_request_the_flows():
    note = {"system": True, "author": {"username": "duo-developer-gitlab-org"}, "body": "assigned to @someone"}
    assert G.flow_made([note], "duo-developer-gitlab-org")
    assert not G.flow_made([dict(note, system=False)], "duo-developer-gitlab-org")
    assert not G.flow_made([note], "duo-developer-gitlab-ai-hackathon")
    assert not G.flow_made([], "duo-developer-gitlab-org")
    assert G.any_duo_account([dict(note, author={"username": "duo-recommend-reviewers-gitlab-org"})])
    assert not G.any_duo_account([dict(note, author={"username": "someone"})])


def test_bots_are_told_apart_from_people():
    assert G.is_bot("gitlab-bot") and G.is_bot("project_278964_bot_89f9") and G.is_bot("project_278964_89f9") and G.is_bot("group_9_x")
    assert not G.is_bot("lindsey-shelton")


def test_the_agent_version_is_the_newest_with_only_the_flows_commits():
    v1 = {"commits": [FLOW], "diffs": []}
    v2 = {"commits": [FLOW], "diffs": [{"new_path": "a"}]}
    v3 = {"commits": [FLOW, FLOW], "diffs": [{"new_path": "a"}, {"new_path": "b"}]}
    v4 = {"commits": [FLOW, FLOW, PERSON], "diffs": [{"new_path": "c"}]}
    v5 = {"commits": [FLOW, FLOW, PERSON, FLOW], "diffs": [{"new_path": "d"}]}
    assert G.agent_version([v1, v2, v3, v4, v5]) is v3
    assert G.agent_version([v1]) is None
    assert G.agent_version([{"commits": [PERSON], "diffs": [{"new_path": "a"}]}, v2]) is None
    assert G.agent_commit({"author_name": "x", "author_email": "service_account_1@x"}) and not G.agent_commit(PERSON)


def test_the_flows_issue_comes_from_its_own_note_then_the_branch():
    acc = "duo-developer-gitlab-org"
    note = {"system": True, "author": {"username": acc}, "body": "mentioned in issue #631280"}
    assert G.flow_issue([note], acc, "duo/fix/1-x") == 631280
    assert G.flow_issue([dict(note, author={"username": "someone"})], acc, "duo/fix/634131-session-bar") == 634131
    assert G.flow_issue([], acc, "duo/ai-instructions-mr-template") is None
    assert G.flow_issue([], acc, "feature/634131-x") is None


def test_wilson_interval_and_the_per_project_cap():
    assert G.wilson(0, 0) is None
    lo, hi = G.wilson(5, 10)
    assert lo < 0.5 < hi and 0.2 < lo and hi < 0.8
    assert G.wilson(0, 20)[0] == 0.0
    rows = [{"project": "p", "created_at": f"2026-10-0{i}"} for i in range(1, 8)] + [{"project": "q", "created_at": "2026-10-01"}]
    kept = G.capped(rows, 5)
    assert len(kept) == 6 and [r["created_at"] for r in kept if r["project"] == "p"][-1] == "2026-10-05"


def test_field_projects_are_hashed_the_same_way_every_time():
    assert G.anon(43068850) == G.anon("43068850") and len(G.anon(1)) == 8 and G.anon(1) != G.anon(2)


def test_the_card_is_the_ci_jobs_own_and_lists_what_the_issue_did_not_ask_for():
    issue = {"iid": 5, "ref": "#5", "title": "Fix a typo in the README heading", "description": "One word is misspelled.",
             "author_id": 1, "author_username": "asker"}
    files = G.to_files([{"new_path": "README.md", "old_path": "README.md", "diff": "@@ -1 +1 @@\n-# Helo\n+# Hello\n"},
                        {"new_path": "Dockerfile", "old_path": "Dockerfile", "new_file": True, "diff": "@@ -0,0 +1 @@\n+FROM python:3.12\n"}])
    mr = {"iid": 9, "title": "Fix the typo", "description": "Closes #5", "author": {"id": 2}}
    got = G.card(1, "group/project", mr, [issue], "description", files, "a", "b")
    assert got["state"] == "extras" and [e["path"] for e in got["extras"]] == ["Dockerfile"]
    inside = G.card(1, "group/project", mr, [issue], "description", files[:1], "a", "b")
    assert inside["state"] != "extras" and inside["extras"] == []


def test_the_summary_counts_flagged_merge_requests_and_who_would_link_them():
    rows = [{"issues_from": "closes_issues", "extras": [{"kind": "config_change"}]},
            {"issues_from": "flow_issue", "extras": [{"kind": "stray_file"}, {"kind": "config_change"}]},
            {"issues_from": "description", "extras": []}]
    s = G.share(rows)
    assert (s["scored"], s["flagged"], s["extras"]) == (3, 2, 3) and s["extras_by_kind"] == {"config_change": 2, "stray_file": 1}
    assert (s["linked_by_the_ci_job_itself"], s["flagged_among_those"]) == (2, 1)


def test_the_cases_file_names_three_populations_and_rules_v6():
    d = json.loads((ROOT / "eval" / "public_replay_cases.json").read_text())
    assert set(d["populations"]) == {"G", "F", "H", "C"} and d["rules_version"] == 6 == G.CI.X.RULES_VERSION
    assert d["populations"]["F"]["anonymised"] is True and d["populations"]["F"]["per_project_cap"] == 5


def test_amendment_1_rebuilds_a_version_gitlab_no_longer_serves(monkeypatch):
    calls = []
    def fake(path):
        calls.append(path)
        return {"diffs": [{"new_path": "a.rb", "old_path": "a.rb", "diff": "@@ -1 +1 @@\n-a\n+b\n"}]}
    monkeypatch.setattr(G, "get", fake)
    old = {"base_commit_sha": "b1", "head_commit_sha": "h1", "diffs": [], "commits": [FLOW]}
    got = G.rebuilt(5, old)
    assert got["diffs_from"] == "compare" and got["diffs"][0]["new_path"] == "a.rb"
    assert calls == ["projects/5/repository/compare?from=b1&to=h1&straight=true"]
    served = {"base_commit_sha": "b1", "head_commit_sha": "h1", "diffs": [{"new_path": "x"}]}
    assert G.rebuilt(5, served) is served and len(calls) == 1
    assert G.rebuilt(5, {"diffs": []}) == {"diffs": []} and len(calls) == 1


def test_amendment_2_reads_closing_links_written_as_a_number_or_as_the_issues_url():
    text = ("Closes https://gitlab.com/gitlab-org/gitlab/-/issues/501\nFixes #7, resolves https://gitlab.com/gitlab-org/gitlab/-/work_items/502\n"
            "See https://gitlab.com/gitlab-org/gitlab/-/issues/503\nCloses https://gitlab.com/gitlab-org/cli/-/issues/504\nCloses #7\n"
            "Closes https://gitlab.com/gitlab-org/gitlab/-/issues/501")
    assert G.closing_links(text) == [7, 501, 502]
    assert G.closing_links(None) == []


def test_population_c_keeps_only_community_merge_requests_whose_issue_lists_them(monkeypatch):
    def mr(iid, **kw):
        return {"iid": iid, "created_at": "2026-09-02", "labels": ["Community contribution"], "source_branch": "fix-x",
                "author": {"username": "someone"}, "description": f"Closes #{iid + 100}", **kw}
    sept = [mr(1), mr(2, labels=[]), mr(3, source_branch="duo/fix/103-x"), mr(4, author={"username": "gitlab-bot"}),
            mr(5), mr(6), mr(7, description="Related to #107")]
    closed_by = {101: [{"iid": 1}], 105: [{"iid": 99}], 106: [{"iid": 6}], 107: [{"iid": 7}], 102: [{"iid": 2}], 103: [{"iid": 3}], 104: [{"iid": 4}]}
    monkeypatch.setattr(G, "get", lambda path: closed_by.get(int(path.split("/issues/")[1].split("/")[0])) if "closed_by" in path else None)
    duo_note = [{"system": True, "author": {"username": "duo-code-review-gitlab-org"}}]
    monkeypatch.setattr(G, "notes_of", lambda pid, iid: duo_note if iid == 6 else [])
    rows = G.frame_c(sept)
    assert [(r["iid"], r["issue_iid"]) for r in rows] == [(1, 101)]


def test_a_frame_confirmed_issue_is_read_directly(monkeypatch):
    seen = []
    monkeypatch.setattr(G, "get", lambda path: seen.append(path) or {"iid": 101, "project_id": 278964, "title": "t", "description": "d", "author": {"id": 1}})
    issues, src = G.linked("C", 278964, {"iid": 1, "description": "", "source_branch": "x"}, [], 101)
    assert src == "closing_link_confirmed" and issues[0]["iid"] == 101 and seen == ["projects/278964/issues/101"]
    monkeypatch.setattr(G, "get", lambda path: None)
    assert G.linked("C", 278964, {"iid": 1, "description": "", "source_branch": "x"}, [], 101) == ([], "none")


def test_amendment_2_scores_only_population_c(monkeypatch):
    got = []
    monkeypatch.setattr(G, "score_one", lambda pop, row: got.append(pop) or [])
    fr = {"rows": {"G": [{"iid": 1}], "F": [{"iid": 2}], "H": [{"iid": 3}], "C": [{"iid": 4}]}}
    monkeypatch.setattr(G, "AMENDMENT", 2)
    G.score(fr, workers=1)
    assert got == ["C"]
    got.clear(); monkeypatch.setattr(G, "AMENDMENT", 1)
    G.score(fr, workers=1)
    assert got == ["G", "F", "H", "C"]
