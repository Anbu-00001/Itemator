"""itemator/stopgaps.py: an extra kept `until #N` is asked about again by the merge request that closes #N, while the
stopgap is still in the code. Real git repositories in tmp, a fake GitLab API, no network."""
import pytest

from itemator import ci, stopgaps as G
from test_ci import FIXED, FakeHttp, isolated, issue, job, mr, repo, routes  # noqa: F401  (fixtures)

REACT = ci.REACT_BOT
PATCH = "#!/bin/sh\n# stopgap until the parser is fixed upstream\nsed -i 's/,$//' build/input.csv\n"
RECORD = "Stopgap from !3: `ci/strip-commas.sh` was kept until this issue is fixed, by @ann. The merge request that closes this issue asks whether to take it out."
DIFF = {"new_path": "ci/strip-commas.sh", "new_file": True,
        "diff": "@@ -0,0 +1,3 @@\n+#!/bin/sh\n+# stopgap until the parser is fixed upstream\n+sed -i 's/,$//' build/input.csv\n"}


def note(body, user=REACT, nid=1, at="2026-10-01T10:00:00Z", system=False):
    return {"id": nid, "body": body, "author": {"username": user}, "created_at": at, "system": system}


def fake(notes, src_state="merged", diffs=(DIFF,), notes_count=None):
    it = issue() | {"user_notes_count": len(notes) if notes_count is None else notes_count}
    r = routes(mr(), [it])
    r["/projects/7/issues/12/notes?per_page=100&sort=asc"] = (200, notes)
    r["/projects/7/merge_requests/3"] = (200, {"iid": 3, "state": src_state})
    r["/projects/7/merge_requests/3/diffs?per_page=100"] = (200, list(diffs))
    return FakeHttp(r)


def run(repo, tmp_path, monkeypatch, http, base_files=None, change=None):
    repo.base = repo.commit({"ci/strip-commas.sh": PATCH, **(base_files or {})}, "base, after !3 was merged")
    head = repo.commit(change or {"src/parser.py": FIXED})
    code, out = job(repo, head, http, tmp_path, monkeypatch)
    assert code == 0
    return out, http


def test_the_fix_is_asked_about_the_stopgap_still_in_the_code(repo, tmp_path, monkeypatch):
    out, http = run(repo, tmp_path, monkeypatch, fake([note(RECORD)]))
    [e] = [x for x in out["extras"] if x["kind"] == G.KIND]
    assert e["name"] == "ci/strip-commas.sh" and e["anchor"] is None
    assert e["why"] == "was kept in !3 until #12 is fixed, by @ann; this merge request closes #12, and the stopgap is still in the file"
    assert e["plain_facts"]["stopgap"] == {"from": 3, "issue": 12, "who": "ann", "line": "# stopgap until the parser is fixed upstream"}
    stub = e["thread_stub"]
    assert "To take it out, change `ci/strip-commas.sh` in this merge request so that `# stopgap until the parser is fixed upstream` is gone, then reply `taken out`." in stub
    assert G.UNTIL_OFFER not in stub and "reply `split`" not in stub and "reply `remove`" not in stub
    assert stub.endswith(f"If this is not really an extra, reply `not an extra`. {ci.MEMBERS_ONLY}")
    assert out["card"]["final_line"] == "1 stopgap beyond #12 kept until this fix: `ci/strip-commas.sh`."
    assert '"taken out"' in out["card"]["todo_line"]
    assert out["stopgaps"] == [{"issue": 12, "from": 3, "path": "ci/strip-commas.sh", "who": "ann",
                                "line": "# stopgap until the parser is fixed upstream"}]


def test_a_stopgap_this_change_takes_out_is_reported_not_asked(repo, tmp_path, monkeypatch):
    out, _ = run(repo, tmp_path, monkeypatch, fake([note(RECORD)]), change={"src/parser.py": FIXED, "ci/strip-commas.sh": None})
    assert not [x for x in out["extras"] if x["kind"] == G.KIND]
    assert out["stopgaps"][0]["line"] is None


def test_only_short_lines_left_count_as_taken_out(repo, tmp_path, monkeypatch):
    out, _ = run(repo, tmp_path, monkeypatch, fake([note(RECORD)]), change={"src/parser.py": FIXED, "ci/strip-commas.sh": "#!/bin/sh\n"})
    assert not [x for x in out["extras"] if x["kind"] == G.KIND]


@pytest.mark.parametrize("notes, state", [
    ([note(RECORD, user="ann")], "merged"),                         # anyone can comment on a public issue
    ([note(RECORD, system=True)], "merged"),
    ([note(RECORD.replace("Stopgap from", "stopgap from"))], "merged"),
    ([note(RECORD)], "closed"),                                     # the stopgap never reached the code
    ([note(RECORD.replace("!3", "!5"))], "merged"),                  # kept in this very merge request
])
def test_no_question_without_a_real_record_of_a_merged_stopgap(repo, tmp_path, monkeypatch, notes, state):
    out, _ = run(repo, tmp_path, monkeypatch, fake(notes, src_state=state))
    assert not [x for x in out["extras"] if x["kind"] == G.KIND]


def test_another_projects_issue_is_not_read(repo, tmp_path, monkeypatch):
    http = fake([note(RECORD)])
    other = issue() | {"project_id": 8, "user_notes_count": 1, "web_url": "https://gitlab.example/grp/lib/-/issues/12"}
    http.routes["/projects/7/merge_requests/5/closes_issues?per_page=100"] = (200, [other])
    out, _ = run(repo, tmp_path, monkeypatch, http)
    assert not [c for c, _ in http.calls if "/notes" in c] and "stopgaps" not in out


def test_an_issue_nobody_commented_on_costs_no_read(repo, tmp_path, monkeypatch):
    out, http = run(repo, tmp_path, monkeypatch, fake([note(RECORD)], notes_count=0))
    assert not [c for c, _ in http.calls if "/notes" in c] and "stopgaps" not in out


def test_a_record_for_a_file_its_merge_request_never_touched_is_ignored(repo, tmp_path, monkeypatch):
    out, _ = run(repo, tmp_path, monkeypatch, fake([note(RECORD)], diffs=({**DIFF, "new_path": "other.sh"},)))
    assert not [x for x in out["extras"] if x["kind"] == G.KIND] and "stopgaps" not in out


@pytest.mark.parametrize("policy, asked", [('[ignore]\npaths = ["ci/strip-commas.sh"]\n', True),
                                            ('[ignore]\nkinds = ["stopgap_due"]\n', False)])
def test_the_team_policy_quiets_it_only_by_kind(repo, tmp_path, monkeypatch, policy, asked):
    out, _ = run(repo, tmp_path, monkeypatch, fake([note(RECORD)]), base_files={".itemator.toml": policy})
    assert [x["kind"] for x in out["extras"]] == ([G.KIND] if asked else [])


def test_records_are_read_strictly():
    notes = [note(RECORD, nid=2, at="2026-10-02T00:00:00Z"), note(RECORD, nid=1), note("Kept: `x`, named by @ann.", nid=3),
             note(RECORD.replace("`ci/strip-commas.sh`", "`a`b`"), nid=4)]
    assert G.records(notes, REACT) == [{"from": 3, "path": "ci/strip-commas.sh", "who": "ann", "note": 1}]
    many = [note(RECORD.replace("!3", f"!{n}"), nid=n) for n in range(1, 30)]
    assert len(G.records(many, REACT)) == G.MAX_RECORDS


def test_still_there_reads_the_longer_added_lines():
    added = G.added_lines([DIFF], "ci/strip-commas.sh")
    assert added == ["#!/bin/sh", "# stopgap until the parser is fixed upstream", "sed -i 's/,$//' build/input.csv"]
    assert G.added_lines([DIFF], "x") is None
    assert G.still_there(added, PATCH) == "# stopgap until the parser is fixed upstream"
    assert G.still_there(added, "#!/bin/sh\n") is None
    assert G.still_there(added, None) is None
    assert G.still_there(["echo `date` > stamp.txt", "a longer line here"], "  echo `date` > stamp.txt\n  a longer line here\n") == "a longer line here"


def test_every_other_thread_offers_until():
    e = ci.X.Extra("stray_file", "a.sh", "a.sh", "x")
    assert G.UNTIL_OFFER in ci.thread_stub(e)
    assert ci.thread_stub(e).index(ci.KEEP) < ci.thread_stub(e).index(G.UNTIL_OFFER)
    for kind in ("left_behind", G.KIND, "policy_changed"):
        assert G.UNTIL_OFFER not in ci.thread_stub(ci.X.Extra(kind, "a.sh", "a.sh", "x"))
