"""T43: the decision log. Notes are read from fixtures, never from the network; the fake fetch records every request."""
import json
import urllib.parse

import pytest

from itemator import decisions as L

SHA = "a" * 40
SUMMARY = ("Every extra has an answer: 3 kept, 1 dismissed, 1 moved, 1 removed.\n\n"
           "- `.gitlab-ci.yml`: kept, named by @alice\n"
           "- `leftpad-py`: kept, and a policy change was proposed in !31, by @bob\n"
           "- `Dockerfile`: dismissed as not an extra, said @alice\n"
           "- `notes.txt`: moved to !40, by @carol\n"
           "- `AGENTS.md`: removed from this merge request, by @alice\n"
           "- `0.0.2`: kept, named by @alice\n\n"
           "All of it was typed by the author of this merge request.\n\n"
           f"[//]: # (itemator:named={SHA})")


def note(body, user="ai-itemator-react-gitlab-ai-hackathon", system=False, at="2026-10-13T10:00:00Z"):
    return {"body": body, "author": {"username": user}, "system": system, "created_at": at}


def mr(iid, author="alice", title="Fix a typo", merged="2026-10-13T11:00:00Z"):
    return {"iid": iid, "title": title, "author": {"username": author}, "merged_at": merged}


def test_a_summary_is_read_line_by_line():
    got = L.parse_summary(SUMMARY)
    assert [(i["name"], i["decision"], i["who"], i["ref"]) for i in got["items"]] == [
        (".gitlab-ci.yml", "kept", "alice", None), ("leftpad-py", "kept", "bob", 31), ("Dockerfile", "dismissed", "alice", None),
        ("notes.txt", "moved", "carol", 40), ("AGENTS.md", "removed", "alice", None), ("0.0.2", "kept", "alice", None)]


@pytest.mark.parametrize("body", [None, 5, "", "Every extra has an answer.\n- `a`: kept, named by @x", "- `a`: kept, named by @x\n[//]: # (itemator:named=zz)",
                                  f"no lines here\n[//]: # (itemator:named={SHA})"])
def test_a_note_that_is_not_a_summary_gives_nothing(body):
    assert L.parse_summary(body) is None


def test_a_line_with_extra_text_is_not_read():
    body = f"- `a`: kept, named by @x and everyone else\n- `b`: kept, named by @y\n\n[//]: # (itemator:named={SHA})"
    assert [i["name"] for i in L.parse_summary(body)["items"]] == ["b"]


def test_only_the_reaction_account_is_believed():
    notes = [note(SUMMARY, user="mallory"), note(SUMMARY, user="ai-itemator-card-gitlab-ai-hackathon"), note(SUMMARY, system=True)]
    assert L.latest_summary(notes) is None
    assert L.latest_summary(notes + [note(SUMMARY)]) is not None


def test_the_newest_summary_wins():
    old = note(f"- `a`: kept, named by @x\n[//]: # (itemator:named={SHA})", at="2026-10-13T09:00:00Z")
    new = note(f"- `b`: dismissed as not an extra, said @y\n[//]: # (itemator:named={SHA})", at="2026-10-13T10:00:00Z")
    assert [i["name"] for i in L.latest_summary([new, old])["items"]] == ["b"]


def test_an_entry_knows_who_wrote_the_merge_request():
    e = L.entry(mr(7, author="alice"), [note(SUMMARY)])
    assert e["summary"] and [i["by_author"] for i in e["extras"]] == [True, False, True, False, True, True]
    assert L.entry(mr(8), []) == {"iid": 8, "title": "Fix a typo", "merged_at": "2026-10-13T11:00:00Z", "author": "alice",
                                  "summary": False, "extras": []}


def test_stats_count_each_decision_once():
    s = L.stats([L.entry(mr(7), [note(SUMMARY)]), L.entry(mr(8), [])])
    assert s == {"merge_requests": 2, "with_a_summary": 1, "extras": 6, "by_author_alone": 4, "by_someone_else": 2,
                 "kept": 3, "dismissed": 1, "moved": 1, "removed": 1}


def test_text_from_a_merge_request_cannot_ping_link_or_close_a_code_span():
    assert L.clean("Fix [x](http://e.example) @bob <b>hi</b>") == "Fix xhttp://e.example bob bhi/b"
    assert L.clean("a" * 200) == "a" * 80
    assert "`" not in L.clean_name("x`y\nz") and "\n" not in L.clean_name("x\ny")
    out = L.markdown([L.entry(mr(1, title="[click](http://e) @all"), [note(f"- `a`b`: kept, named by @x\n[//]: # (itemator:named={SHA})")])])
    assert "@all" not in out and "](" not in out


def test_markdown_says_the_counts_and_names_each_extra():
    out = L.markdown([L.entry(mr(7), [note(SUMMARY)]), L.entry(mr(8), [])], "Decisions in v1")
    assert out.startswith("## Decisions in v1\n")
    assert "Merge requests merged: 2, of which with an Itemator summary: 1." in out
    assert "Extras decided: 6 (3 kept, 1 dismissed, 1 moved, 1 removed)." in out
    assert "Typed by the merge request's own author: 4; by someone else: 2." in out
    assert "- !7 Fix a typo: `.gitlab-ci.yml` kept by @alice; `leftpad-py` kept by @bob;" in out and "!8" not in out
    assert "No merge request was merged" in L.markdown([])


def test_the_release_description_is_replaced_not_stacked():
    once = L.merge_description("Notes for v1.", "## A\n")
    twice = L.merge_description(once, "## B\n")
    assert twice.count(L.START) == 1 and "## B" in twice and "## A" not in twice and twice.startswith("Notes for v1.")
    assert L.merge_description(None, "## A") == f"{L.START}\n## A\n{L.END}\n"
    assert L.merge_description(f"x{L.END}y{L.START}z", "## A").startswith(f"x{L.END}y{L.START}z")      # end before start: append


class Fake:
    """A fake GitLab: routes are (method, path) -> (status, data); every request is recorded."""

    def __init__(self, routes):
        self.routes, self.seen = routes, []

    def __call__(self, method, url, body=None):
        self.seen.append((method, url, body))
        path = url.split("/api/v4/", 1)[1].split("?")[0]
        key = (method, path)
        if key not in self.routes:
            return 404, None
        got = self.routes[key]
        if isinstance(got, Exception):
            raise got
        return got


def api(routes):
    f = Fake(routes)
    return L.Api("https://gitlab.example/api/v4", 7, "tok", fetch=f), f


def test_collect_reads_only_merge_requests_inside_the_window_in_order():
    a, f = api({("GET", "projects/7/merge_requests"): (200, [mr(3, merged="2026-10-13T12:00:00Z"), mr(1, merged="2026-10-01T00:00:00Z"),
                                                            mr(2, merged="2026-10-13T11:00:00Z"), mr(4, merged="2026-10-20T00:00:00Z")]),
                ("GET", "projects/7/merge_requests/2/notes"): (200, [note(SUMMARY)]),
                ("GET", "projects/7/merge_requests/3/notes"): (200, [])})
    got = L.collect(a, "main", "2026-10-10T00:00:00Z", "2026-10-14T00:00:00Z")
    assert [e["iid"] for e in got] == [2, 3] and got[0]["summary"] and not got[1]["summary"]
    assert all(m == "GET" for m, _, _ in f.seen)
    assert "target_branch=main" in f.seen[0][1] and "state=merged" in f.seen[0][1]


def test_an_unreadable_request_is_counted_and_never_raises():
    a, _ = api({("GET", "projects/7/merge_requests"): (200, [mr(2)]), ("GET", "projects/7/merge_requests/2/notes"): OSError("down")})
    got = L.collect(a, "main", "2026-10-01T00:00:00Z", "2026-10-14T00:00:00Z")
    assert got[0]["summary"] is False and a.failures == 1
    a, _ = api({("GET", "projects/7/merge_requests"): (500, None)})
    assert L.collect(a, "main", "x", "y") == [] and a.failures == 1


def test_the_window_of_a_tag_starts_at_the_previous_tag():
    tags = [{"name": "v2", "commit": {"created_at": "2026-10-20T00:00:00Z"}}, {"name": "v1", "commit": {"created_at": "2026-10-10T00:00:00Z"}},
            {"name": "v0", "commit": {"created_at": "2026-10-01T00:00:00Z"}}, {"name": "v3", "commit": {"created_at": "2026-10-30T00:00:00Z"}}]
    a, _ = api({("GET", "projects/7/repository/tags"): (200, tags)})
    assert L.window_for_tag(a, "v2") == ("2026-10-10T00:00:00Z", "2026-10-20T00:00:00Z")
    assert L.window_for_tag(a, "v0")[0] == "1970-01-01T00:00:00Z"


def test_publish_updates_an_existing_release_and_creates_a_missing_one():
    a, f = api({("GET", "projects/7/releases/v1"): (200, {"description": "Old."}), ("PUT", "projects/7/releases/v1"): (200, {})})
    assert L.publish(a, "v1", "## D") == "updated"
    put = [s for s in f.seen if s[0] == "PUT"][0]
    assert put[2]["description"].startswith("Old.\n\n" + L.START)
    a, f = api({("POST", "projects/7/releases"): (201, {})})
    assert L.publish(a, "v1", "## D") == "created" and f.seen[-1][2]["tag_name"] == "v1"
    a, _ = api({("POST", "projects/7/releases"): (403, None)})
    assert L.publish(a, "v1", "## D") == "not created (HTTP 403)"
    a, _ = api({("GET", "projects/7/releases/v1"): (200, {"description": ""}), ("PUT", "projects/7/releases/v1"): OSError("x")})
    assert L.publish(a, "v1", "## D") == "not written (request failed)"


def test_only_the_job_server_is_asked():
    a = L.Api("https://gitlab.example/api/v4", 7, "tok")
    with pytest.raises(ValueError):
        a._fetch("GET", "https://evil.example/api/v4/projects/7/merge_requests")


def test_a_job_without_a_token_does_nothing(monkeypatch, capsys):
    for k in ("CI_API_V4_URL", "CI_PROJECT_ID", "CI_JOB_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert L.main([]) == 0 and "nothing done" in capsys.readouterr().out


def test_main_writes_the_report_and_the_markdown(monkeypatch, tmp_path, capsys):
    f = Fake({("GET", "projects/7/merge_requests"): (200, [mr(2, merged="2999-01-01T00:00:00Z")]),
              ("GET", "projects/7/merge_requests/2/notes"): (200, [note(SUMMARY)])})
    monkeypatch.setattr(L.Api, "_fetch", lambda self, m, u, b=None: f(m, u, b))
    monkeypatch.setenv("CI_JOB_TOKEN", "tok")
    out, md = tmp_path / "d.json", tmp_path / "d.md"
    # the window ends now, so a merge date in the far future is outside it: nothing is collected
    assert L.main(["--api", "https://gitlab.example/api/v4", "--project", "7", "--out", str(out), "--md", str(md), "--days", "3"]) == 0
    assert json.loads(out.read_text())["stats"]["merge_requests"] == 0 and "No merge request" in md.read_text()
    assert "release: no release (report mode)" in capsys.readouterr().out
    assert not [x for x in f.seen if x[0] != "GET"]                      # report mode never writes


def test_main_in_release_mode_collects_the_window_and_updates_the_release(monkeypatch, tmp_path, capsys):
    tags = [{"name": "v1", "commit": {"created_at": "2026-10-20T00:00:00Z"}}, {"name": "v0", "commit": {"created_at": "2026-10-10T00:00:00Z"}}]
    f = Fake({("GET", "projects/7/repository/tags"): (200, tags),
              ("GET", "projects/7/merge_requests"): (200, [mr(2, merged="2026-10-13T11:00:00Z"), mr(3, merged="2026-10-09T11:00:00Z")]),
              ("GET", "projects/7/merge_requests/2/notes"): (200, [note(SUMMARY)]),
              ("GET", "projects/7/releases/v1"): (200, {"description": "Notes."}), ("PUT", "projects/7/releases/v1"): (200, {})})
    monkeypatch.setattr(L.Api, "_fetch", lambda self, m, u, b=None: f(m, u, b))
    monkeypatch.setenv("CI_JOB_TOKEN", "tok")
    out, md = tmp_path / "d.json", tmp_path / "d.md"
    assert L.main(["--api", "https://gitlab.example/api/v4", "--project", "7", "--tag", "v1", "--out", str(out), "--md", str(md)]) == 0
    rep = json.loads(out.read_text())
    assert [e["iid"] for e in rep["merge_requests"]] == [2] and rep["stats"]["extras"] == 6
    assert md.read_text().startswith("## Decisions in v1\n") and "release: updated" in capsys.readouterr().out
    put = [x for x in f.seen if x[0] == "PUT"]
    assert len(put) == 1 and put[0][2]["description"].startswith("Notes.") and "- !2 Fix a typo" in put[0][2]["description"]


def test_the_window_includes_its_end_and_excludes_its_start():
    """A merge request merged at the previous tag's commit date belongs to the previous release."""
    a, _ = api({("GET", "projects/7/merge_requests"): (200, [mr(1, merged="2026-10-10T00:00:00Z"), mr(2, merged="2026-10-20T00:00:00Z"),
                                                            mr(3, merged="2026-10-20T00:00:01Z")]),
                ("GET", "projects/7/merge_requests/2/notes"): (200, [])})
    assert [e["iid"] for e in L.collect(a, "main", "2026-10-10T00:00:00Z", "2026-10-20T00:00:00Z")] == [2]


def test_a_missing_release_is_not_a_failed_request():
    a, _ = api({("POST", "projects/7/releases"): (201, {})})
    assert L.publish(a, "v1", "## D") == "created" and a.failures == 0


def test_more_than_one_page_is_read_until_a_short_page():
    page = [mr(i, merged="2026-10-13T11:00:00Z") for i in range(1, 101)]
    calls = []

    def fetch(method, url, body=None):
        calls.append(url)
        n = int(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["page"][0])
        return 200, page if n == 1 else page[:3]
    a = L.Api("https://gitlab.example/api/v4", 7, "tok", fetch=fetch)
    assert len(a.pages("merge_requests", 5)) == 103 and len(calls) == 2


def test_a_refused_listing_is_reported_with_its_status():
    a, _ = api({("GET", "projects/7/merge_requests"): (403, None)})
    assert L.collect(a, "main", "x", "y") == [] and a.failures == 1 and a.errors == ["merge_requests: HTTP 403"]
    a, _ = api({})                                  # a 404 on a list is a failure too; only a missing release is not
    assert L.collect(a, "main", "x", "y") == [] and a.errors == ["merge_requests: HTTP 404"]
