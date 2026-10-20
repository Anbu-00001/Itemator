"""Leg 2's own parts (eval/aidev_revert.py): which pull requests count as reverted, how controls are drawn, the shares and
their difference, and one pull request's score."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import aidev_revert as R  # noqa: E402

S1, S2, S3 = "a" * 40, "b" * 40, "c" * 40


def c(sha, pr, msg=""):
    return {"sha": sha, "pr_id": pr, "message": msg}


def test_a_message_names_the_commits_it_reverts_in_lower_case():
    assert R.reverted_shas(f"Revert x\n\nThis reverts commit {S1.upper()}.") == [S1]
    assert R.reverted_shas("This reverts commit abc123") == []                      # under 12 digits: not a commit id
    assert R.reverted_shas(f"This reverts commit {S1} and This reverts commit {S2}") == [S1, S2]
    assert R.reverted_shas(None) == []


def test_a_pull_request_reverted_by_another_is_cross_and_by_itself_is_inside():
    got = R.find_reverts([c(S1, 1), c(S2, 2, f"This reverts commit {S1}"), c(S3, 3), c("d" * 40, 3, f"This reverts commit {S3}")])
    assert got == {"cross": {1: [2]}, "inside": [3]}


def test_a_pull_request_reverted_both_ways_stays_cross_only():
    got = R.find_reverts([c(S1, 1, f"This reverts commit {S1}"), c(S2, 2, f"This reverts commit {S1}")])
    assert got == {"cross": {1: [2]}, "inside": []}


def test_a_prefix_counts_from_twelve_digits_and_only_when_it_matches_one_sha():
    pre = S1[:12]
    assert R.find_reverts([c(S1, 1), c(S2, 2, f"This reverts commit {pre}")])["cross"] == {1: [2]}
    twin = S1[:12] + "d" * 28
    assert R.find_reverts([c(S1, 1), c(twin, 4), c(S2, 2, f"This reverts commit {pre}")])["cross"] == {}


def test_a_sha_shared_by_two_pull_requests_is_ambiguous_and_skipped():
    assert R.find_reverts([c(S1, 1), c(S1, 5), c(S2, 2, f"This reverts commit {S1}")]) == {"cross": {}, "inside": []}


def test_an_unknown_sha_is_ignored():
    assert R.find_reverts([c(S1, 1), c(S2, 2, f"This reverts commit {S3}")]) == {"cross": {}, "inside": []}


def prs(n, agent="Copilot", state="merged", start=100):
    return [{"id": start + i, "agent": agent, "state": state} for i in range(n)]


def test_controls_share_the_agent_and_state_are_not_excluded_and_not_reused():
    members = [{"id": 1, "agent": "Copilot", "state": "merged"}, {"id": 2, "agent": "Codex", "state": "closed"},
               {"id": 3, "agent": "Copilot", "state": "merged"}]
    pool = prs(8) + prs(5, "Codex", "closed", 200) + prs(4, "Copilot", "closed", 300)
    got = R.draw_controls(members, pool, exclude={100, 101})
    assert set(got) == {1, 2, 3}
    assert all(i >= 200 for i in got[2]) and len(got[2]) == 3
    assert all(100 <= i < 200 and i not in (100, 101) for k in (1, 3) for i in got[k])
    flat = [i for v in got.values() for i in v]
    assert len(flat) == len(set(flat)) == 9


def test_fewer_candidates_than_three_gives_what_there_is_and_the_draw_is_seeded():
    members = [{"id": 1, "agent": "Devin", "state": "merged"}]
    pool = prs(2, "Devin")
    assert R.draw_controls(members, pool, set()) == {1: [100, 101]}
    big = prs(50)
    m = [{"id": 1, "agent": "Copilot", "state": "merged"}]
    assert R.draw_controls(m, big, set()) == R.draw_controls(m, big, set())
    assert R.draw_controls(m, big, set(), seed=1) != R.draw_controls(m, big, set(), seed=2)


def test_the_difference_of_two_shares_and_its_interval():
    d = R.newcombe(30, 100, 20, 100)
    assert d["difference"] == 0.1 and d["interval"][0] < 0.1 < d["interval"][1]
    assert d["interval"] == [-0.0203, 0.2171]          # hand-checked: 0.1 -/+ the root of the summed squared Wilson half-widths
    assert R.newcombe(5, 0, 1, 2) == {"difference": None, "interval": None}
    same = R.newcombe(10, 50, 10, 50)
    assert same["difference"] == 0 and same["interval"][0] < 0 < same["interval"][1]


def test_a_share_counts_pull_requests_with_an_extra():
    assert R.share([{"extra": True}, {"extra": False}, {"extra": True}])["with_an_extra"] == 2
    assert R.share([])["share"] is None


PR = {"id": 9, "agent": "Copilot", "state": "merged"}


def rows(*items):
    return [{"sha": s, "filename": f, "status": st, "patch": p} for s, f, st, p in items]


def test_a_pull_request_with_no_file_rows_is_unreadable_not_dropped():
    assert R.score_pr(PR, [], ("task", "pr_text"), "o/r") == {"id": 9, "agent": "Copilot", "state": "merged", "task_from": "pr_text", "readable": False}


def test_a_new_dependency_the_task_never_names_is_an_extra_and_a_plain_edit_is_not():
    task = ("Fix the parser\nthe parser in src/parser.py drops a trailing comma", "linked_issue")
    dep = rows(("s1", "src/parser.py", "modified", "@@ -1 +1 @@\n-a\n+b\n"),
               ("s2", "requirements.txt", "modified", "@@ -1 +1,2 @@\n requests==2.31.0\n+leftpad-py==1.0.0\n"))
    got = R.score_pr(PR, dep, task, "o/r")
    assert got["readable"] and got["extra"] and "dependency" in got["kinds"]
    plain = R.score_pr(PR, dep[:1], task, "o/r")
    assert plain["readable"] and not plain["extra"] and plain["kinds"] == []


def test_files_are_read_at_the_last_commit_so_a_file_added_then_removed_is_gone():
    task = ("Fix the parser\nsrc/parser.py", "linked_issue")
    r = rows(("s1", "src/parser.py", "modified", "@@ -1 +1 @@\n-a\n+b\n"),
             ("s1", "scratch.txt", "added", "@@ -0,0 +1 @@\n+x\n"), ("s2", "scratch.txt", "removed", "@@ -1 +0,0 @@\n-x\n"))
    assert R.score_pr(PR, r, task, "o/r")["extra"] is False


def test_the_summary_compares_members_with_controls_and_counts_the_unreadable():
    m = [{"id": 1, "agent": "Copilot", "state": "merged", "task_from": "pr_text", "readable": True, "extra": True, "kinds": ["dependency"]},
         {"id": 2, "agent": "Copilot", "state": "merged", "task_from": "pr_text", "readable": False}]
    k = [{"id": 3, "agent": "Copilot", "state": "merged", "task_from": "pr_text", "readable": True, "extra": False, "kinds": []}]
    out = R.summarize({"g": (m, k)})["g"]
    assert out["members"]["with_an_extra"] == 1 and out["controls"]["with_an_extra"] == 0
    assert out["unreadable"] == {"members": 1, "controls": 0} and out["kinds"]["members"] == {"dependency": 1}
    assert out["by_agent"]["Copilot"]["difference"] == 1.0


def test_a_pull_request_whose_files_all_cancel_out_is_unreadable():
    gone = rows(("s1", "scratch.txt", "added", "@@ -0,0 +1 @@\n+x\n"), ("s2", "scratch.txt", "removed", "@@ -1 +0,0 @@\n-x\n"))
    assert R.score_pr(PR, gone, ("t", "pr_text"), "o/r")["readable"] is False


def test_a_pull_request_whose_file_rows_the_api_will_not_give_is_unreadable_and_marked_not_dropped_and_other_errors_still_stop_the_run():
    def boom():
        raise RuntimeError("pr_commit_details: HTTP Error 500")
    got = R.score_or_error(PR, boom, ("t", "pr_text"), "o/r")
    assert got == {"id": 9, "agent": "Copilot", "state": "merged", "task_from": "pr_text", "readable": False, "api_error": True}
    ok = R.score_or_error(PR, lambda: rows(("s1", "a.py", "modified", "@@ -1 +1 @@\n-a\n+b\n")), ("t", "pr_text"), "o/r")
    assert ok["readable"] and "api_error" not in ok

    def bug():
        raise KeyError("x")
    try:
        R.score_or_error(PR, bug, ("t", "pr_text"), "o/r")
    except KeyError:
        pass
    else:
        raise AssertionError("a programming error must not be swallowed")


def test_the_summary_counts_api_errors_apart_from_other_unreadable_ones():
    m = [{"id": 1, "agent": "Copilot", "state": "merged", "task_from": "pr_text", "readable": False, "api_error": True},
         {"id": 2, "agent": "Copilot", "state": "merged", "task_from": "pr_text", "readable": False}]
    out = R.summarize({"g": (m, [])})["g"]
    assert out["unreadable"] == {"members": 2, "controls": 0} and out["api_errors"] == {"members": 1, "controls": 0}
