"""The CI job's anonymous GraphQL reads (itemator/ci.py Api.graphql): on gitlab.com the job token gets HTTP 401 on issue
notes, merge request discussions and members, and GraphQL refuses it (probed from a CI job on 2026-10-24), so the hold's
answer check and the stopgap check read those through anonymous GraphQL first, and through REST when GraphQL fails."""
import pytest

from itemator import ci, replycheck
from test_ci import FakeHttp, isolated, issue, job, mr, repo, routes  # noqa: F401  (fixtures)
from test_hold import DISC, NOTES, members_thread, setup, summary, thread
from test_stopgaps import DIFF, PATCH, RECORD, note

from test_ci import FIXED


def gql_thread(d, bots=()):
    return {"id": f"gid://gitlab/Discussion/{d['id']}", "notes": {"pageInfo": {"hasNextPage": False}, "nodes": [
        {"id": f"gid://gitlab/Note/{n['id']}", "body": n["body"], "system": n["system"], "createdAt": n["created_at"],
         "author": {"id": f"gid://gitlab/User/{n['author']['id']}", "username": n["author"]["username"],
                    "bot": n["author"]["id"] == 100 or n["author"]["id"] in bots}} for n in d["notes"]]}}


def member_node(uid=2, username="ann", level=30, expires=None, state="active"):
    return {"accessLevel": {"integerValue": level}, "expiresAt": expires,
            "user": {"id": f"gid://gitlab/User/{uid}", "username": username, "state": state}}


def answers(threads=None, members=(), issue_notes=None, bots=(), more=False):
    def answer(query, v):
        assert v["p"] == "grp/showcase"
        if "mergeRequest(" in query and threads is not None:
            return 200, {"data": {"project": {"mergeRequest": {"discussions": {
                "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [gql_thread(d, bots) for d in threads]}}}}}
        if "projectMembers(" in query:
            return 200, {"data": {"project": {"projectMembers": {"nodes": [m for m in members
                                                                           if v["u"] in m["user"]["username"]]}}}}
        if "issue(" in query and issue_notes is not None:
            return 200, {"data": {"project": {"issue": {"notes": {"pageInfo": {"hasNextPage": more}, "nodes": [
                {"id": f"gid://gitlab/Note/{n['id']}", "body": n["body"], "system": n["system"], "createdAt": n["created_at"],
                 "author": {"id": "gid://gitlab/User/9", "username": n["author"]["username"], "bot": True}}
                for n in issue_notes]}}}}}
        return 200, {"errors": [{"message": "not here"}]}
    return answer


def hold_run(repo, tmp_path, monkeypatch, gql, rest_threads=None, member_rest=None):
    head = setup(repo)
    r = routes(dict(mr(), author={"id": 2, "username": "ann"}), [issue()])
    r[NOTES.format(1)] = (200, [summary(head)])
    r["GRAPHQL"] = gql
    if rest_threads is not None:
        r[DISC] = rest_threads
        r["/users/2"] = (200, {"id": 2, "bot": False})
    if member_rest is not None:
        r["/projects/7/members/all/2"] = member_rest
    http = FakeHttp(r)
    code, out = job(repo, head, http, tmp_path, monkeypatch)
    return code, out, http


def test_the_answer_check_reads_the_threads_anonymously_through_graphql(repo, tmp_path, monkeypatch):
    gql = answers([thread(".gitlab-ci.yml")])
    code, out, http = hold_run(repo, tmp_path, monkeypatch, gql)
    assert code == 0 and out["hold"] == {"enabled": True, "blocked": False, "reason": None}       # checked, not just the summary
    assert all(h == {} for c, h in http.calls if c == "GRAPHQL")                                 # no job token sent there
    assert not [c for c, _ in http.calls if "/discussions" in c or c.startswith("/users/")]


def test_a_bot_reply_read_through_graphql_is_not_an_answer(repo, tmp_path, monkeypatch):
    d = thread(".gitlab-ci.yml")
    d["notes"][1]["author"] = {"id": 55, "username": "duo-developer"}
    code, out, _ = hold_run(repo, tmp_path, monkeypatch, answers([d], bots=(55,)))
    assert code == 1 and out["hold"]["blocked"] is True


@pytest.mark.parametrize("members, blocked", [
    ([member_node()], False),
    ([member_node(level=20)], True),                                      # Reporter
    ([], True),                                                           # not a member
    ([member_node(uid=3)], True),                                         # another user whose name matches the search
    ([member_node(username="ann2")], True),
    ([member_node(expires="2026-10-23T00:00:00Z")], True),                # expired the day before the reply
    ([member_node(expires="2026-11-01T00:00:00Z")], False),
    ([member_node(expires="2026-10-24T00:00:00Z")], True),                # expires the day of the reply (REST: "2026-10-24")
    ([member_node(state="blocked")], True),
])
def test_members_only_threads_read_the_role_through_graphql(repo, tmp_path, monkeypatch, members, blocked):
    code, out, _ = hold_run(repo, tmp_path, monkeypatch, answers([members_thread()], members=members))
    assert out["hold"]["blocked"] is blocked and code == (1 if blocked else 0)


def test_when_graphql_fails_the_threads_are_read_through_rest(repo, tmp_path, monkeypatch):
    code, out, http = hold_run(repo, tmp_path, monkeypatch, (403, {"message": "403 Forbidden"}),
                               rest_threads=(200, [members_thread()]),
                               member_rest=(200, {"id": 2, "access_level": 30, "state": "active", "expires_at": None}))
    assert code == 0 and out["hold"] == {"enabled": True, "blocked": False, "reason": None}
    assert "/projects/7/members/all/2" in [c for c, _ in http.calls]


def test_neither_readable_keeps_the_summary_rule_and_says_so(repo, tmp_path, monkeypatch):
    code, out, _ = hold_run(repo, tmp_path, monkeypatch, (200, {"errors": [{"message": "x"}]}))
    assert code == 0 and out["hold"]["checked"] is False


def stopgap_run(repo, tmp_path, monkeypatch, gql, rest_notes=None):
    it = issue() | {"user_notes_count": 1}
    r = routes(mr(), [it])
    r["GRAPHQL"] = gql
    if rest_notes is not None:
        r["/projects/7/issues/12/notes?per_page=100&sort=asc"] = rest_notes
    r["/projects/7/merge_requests/3"] = (200, {"iid": 3, "state": "merged"})
    r["/projects/7/merge_requests/3/diffs?per_page=100"] = (200, [DIFF])
    repo.base = repo.commit({"ci/strip-commas.sh": PATCH}, "base, after !3 was merged")
    head = repo.commit({"src/parser.py": FIXED})
    code, out = job(repo, head, FakeHttp(r), tmp_path, monkeypatch)
    assert code == 0
    return out


def test_the_stopgap_record_is_read_through_graphql(repo, tmp_path, monkeypatch):
    out = stopgap_run(repo, tmp_path, monkeypatch, answers(issue_notes=[note(RECORD, user=ci.REACT_BOT)]))
    assert [e["name"] for e in out["extras"] if e["kind"] == "stopgap_due"] == ["ci/strip-commas.sh"]
    assert not out["warnings"]


@pytest.mark.parametrize("more", [False, True])
def test_the_stopgap_record_falls_back_to_rest(repo, tmp_path, monkeypatch, more):
    gql = answers(issue_notes=[] if more else None, more=more)                # an error, or more than one page
    out = stopgap_run(repo, tmp_path, monkeypatch, gql, rest_notes=(200, [note(RECORD)]))
    assert [e["name"] for e in out["extras"] if e["kind"] == "stopgap_due"] == ["ci/strip-commas.sh"]


def test_an_answer_with_errors_is_not_read_even_with_data():
    body = b'{"data": {"project": {"projectMembers": null}}, "errors": [{"message": "x"}]}'
    api = ci.Api("https://gitlab.example/api/v4", "tok", lambda url, h: (200, body), "grp/showcase")
    with pytest.raises(ci.JobError):
        api.graphql(ci.GQL_MEMBER, {"u": "ann"})


def test_graphql_needs_the_project_path():
    api = ci.Api("https://gitlab.example/api/v4", "tok", lambda url, h: (200, b"{}"))
    with pytest.raises(ci.JobError):
        api.graphql(ci.GQL_ISSUE_NOTES, {"i": "1"})


def test_the_reply_check_agrees_on_graphql_shaped_notes():
    """The REST shape built from GraphQL keeps what replycheck reads: ids as numbers, created_at, author id and name."""
    got = ci._gql_notes(gql_thread(thread("x"))["notes"])
    assert got[1] == {"id": 2, "body": "x", "system": False, "created_at": "2026-10-24T01:01:00Z",
                      "author": {"id": 2, "username": "ann", "bot": False}}
    assert replycheck.threads([{"id": "t1", "notes": got}])
