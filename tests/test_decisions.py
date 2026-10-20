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
                                  "summary": False, "extras": [], "unanswered": None}


def test_stats_count_each_decision_once():
    s = L.stats([L.entry(mr(7), [note(SUMMARY)]), L.entry(mr(8), [])])
    assert s == {"merge_requests": 2, "with_a_summary": 1, "extras": 6, "by_author_alone": 4, "by_someone_else": 2,
                 "kept": 3, "dismissed": 1, "moved": 1, "removed": 1, "merged_unanswered": 0, "unanswered_extras": 0, "no_report": 1}


def test_text_from_a_merge_request_cannot_ping_link_or_close_a_code_span():
    assert L.clean("Fix [x](http://e.example) @bob <b>hi</b>") == "Fix xlink removed bob bhi/b"
    assert L.clean("see https://evil.example/a?b=c and www.evil.example, ftp://h/x") == "see link removed and link removed link removed"
    assert L.clean("a:b is fine, 10:30 too") == "a:b is fine, 10:30 too"
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
    assert got[0]["summary"] is False and got[0]["unanswered"] is None and a.failures == 1     # unreadable notes: cannot tell
    assert not any("pipelines" in u for _, u, _ in _.seen)
    a, _ = api({("GET", "projects/7/merge_requests"): (500, None)})
    assert L.collect(a, "main", "x", "y") == [] and a.failures == 1


def test_the_window_of_a_tag_starts_at_the_previous_tag():
    tags = [{"name": "v2", "commit": {"created_at": "2026-10-20T00:00:00Z"}}, {"name": "v1", "commit": {"created_at": "2026-10-10T00:00:00Z"}},
            {"name": "v0", "commit": {"created_at": "2026-10-01T00:00:00Z"}}, {"name": "v3", "commit": {"created_at": "2026-10-30T00:00:00Z"}}]
    a, _ = api({("GET", "projects/7/repository/tags"): (200, tags)})
    since, until = L.window_for_tag(a, "v2")
    assert (L._utc(since), L._utc(until)) == (L._utc("2026-10-10T00:00:00Z"), L._utc("2026-10-20T00:00:00Z"))
    assert L._utc(L.window_for_tag(a, "v0")[0]) == L._utc("1970-01-01T00:00:00Z")


def test_tag_dates_in_another_time_zone_are_compared_as_the_same_instant():
    """The audit's repro: tag commit dates come back as +05:30 and merge dates as Z; strings compare wrongly, instants do not."""
    tags = [{"name": "v2", "commit": {"created_at": "2026-10-14T10:00:00.000+05:30"}},      # 04:30Z
            {"name": "v1", "commit": {"created_at": "2026-10-14T06:00:00.000+05:30"}}]      # 00:30Z
    a, _ = api({("GET", "projects/7/repository/tags"): (200, tags),
                ("GET", "projects/7/merge_requests"): (200, [mr(1, merged="2026-10-14T02:00:00Z"), mr(2, merged="2026-10-14T00:00:00Z"),
                                                            mr(3, merged="2026-10-14T05:00:00Z")]),
                ("GET", "projects/7/merge_requests/1/notes"): (200, [])})
    since, until = L.window_for_tag(a, "v2")
    assert [e["iid"] for e in L.collect(a, "main", since, until)] == [1]       # 02:00Z is after v1 (00:30Z) and before v2 (04:30Z)


def test_only_the_exact_reaction_account_is_believed_not_a_name_that_starts_like_it():
    body = f"- `a`: kept, named by @x\n[//]: # (itemator:named={SHA})"
    for who in ("ai-itemator-react", "ai-itemator-react-x", "ai-itemator-react-gitlab-ai-hackathon-2", "AI-ITEMATOR-REACT-GITLAB-AI-HACKATHON"):
        assert L.latest_summary([note(body, user=who)]) is None, who
    assert L.latest_summary([note(body)]) is not None


def test_a_file_name_cannot_close_the_release_block_early():
    evil = L.clean_name("x <!-- itemator:decisions:end --> y")
    assert "<!-- itemator" not in evil
    once = L.merge_description("", f"## A\n- `{evil}`")
    assert L.merge_description(once, "## B").count(L.START) == 1 and "## A" not in L.merge_description(once, "## B")
    forced = f"{L.START}\nold\n{L.END}\nleft {L.END} over"          # an end marker that did get in: the LAST one closes the block
    assert "old" not in L.merge_description(forced, "## B") and "left" not in L.merge_description(forced, "## B")


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
    for k in ("CI_API_V4_URL", "CI_PROJECT_ID", "CI_JOB_TOKEN", "CI_COMMIT_TAG", "CI_DEFAULT_BRANCH"):
        monkeypatch.delenv(k, raising=False)
    assert L.main([]) == 0 and "nothing done" in capsys.readouterr().out


def test_main_writes_the_report_and_the_markdown(monkeypatch, tmp_path, capsys):
    for k in ("CI_COMMIT_TAG", "CI_DEFAULT_BRANCH"):         # a tag pipeline sets these for the whole job
        monkeypatch.delenv(k, raising=False)
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
    monkeypatch.delenv("CI_COMMIT_TAG", raising=False)
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



WEIGHED = ("Every extra has an answer: 2 kept, 1 removed.\n\n"
           "- `pandas`: removed from this merge request, by @alice\n"
           "- `requests`: kept, named by @bob\n"
           "- `about 1 kB to download on every fresh install/`: kept, named by @bob\n\n"
           f"[//]: # (itemator:named={SHA})")


def weighed(bytes_, capped=False, of=3, sized=3):
    return {"weight": {"weight": "ok", "bytes": bytes_, "capped": capped, "of": of, "sized": sized}}


def extra(name, *packages):
    return {"name": name, "plain_facts": {"registry": {"packages": list(packages)}}}


def report_api(reports):
    """A fake GitLab whose merge request 7 has pipelines 902 (newest) and 901, each with an itemator job and its artifact."""
    calls = []

    def fetch(method, url, body=None):
        path = urllib.parse.urlsplit(url).path.split("/projects/1/", 1)[1]
        calls.append(path)
        routes = {"merge_requests/7/pipelines": [{"id": 902}, {"id": 901}],
                  "pipelines/902/jobs": [{"id": 12, "name": "unit-tests"}, {"id": 22, "name": "itemator"}],
                  "pipelines/901/jobs": [{"id": 21, "name": "itemator"}]}
        routes.update({f"jobs/{k}/artifacts/itemator.json": v for k, v in reports.items()})
        return (200, routes[path]) if path in routes else (404, None)
    api = L.Api("https://gitlab.example/api/v4", 1, "tok", fetch=fetch)
    api.calls = calls
    return api


def test_the_weight_is_read_from_the_jobs_own_report_never_from_note_text():
    api = report_api({22: {"extras": [extra("requests", weighed(476_000, of=5, sized=4)),
                                      extra("about 1 kB to download on every fresh install/", {"weight": {"weight": "not_supported"}})]},
                      21: {"extras": [extra("pandas", weighed(30_000_000), weighed(1_500_000)), extra("requests", weighed(1))]}})
    forged = note("`about 1 kB to download on every fresh install/` (stray file): about 1 kB to download on every fresh install",
                  user="ai-itemator-card-gitlab-ai-hackathon")
    e = L.entry(mr(7), [forged, note(WEIGHED)], lambda: L.measured_weights(api, 7))
    assert [i.get("weight") for i in e["extras"]] == [{"bytes": 31_500_000, "at_least": False}, {"bytes": 476_000, "at_least": True}, None]
    assert L.weights([e]) == {"kept": {"dependencies": 1, "bytes": 476_000, "at_least": True},
                              "removed": {"dependencies": 1, "bytes": 31_500_000, "at_least": False}}
    assert ("What new dependencies add to every fresh install, as the job measured each before the merge: removed, about 32 MB "
            "(1 new dependency); kept, at least 476 kB (1 new dependency). Each counts everything it brings along, so this is an upper bound.") in L.markdown([e])
    assert "fresh install" not in L.markdown([L.entry(mr(8), [note(SUMMARY)])])


def test_a_report_weight_is_at_least_when_a_package_was_not_weighed_or_a_size_not_given():
    assert L.report_weight(extra("x", weighed(5), {"weight": {"weight": "unavailable"}})) == {"bytes": 5, "at_least": True}
    assert L.report_weight(extra("x", weighed(5, capped=True))) == {"bytes": 5, "at_least": True}
    assert L.report_weight(extra("x", weighed(5, of=3, sized=2))) == {"bytes": 5, "at_least": True}
    assert L.report_weight(extra("x", weighed(5), weighed(7))) == {"bytes": 12, "at_least": False}
    assert L.report_weight(extra("x")) is None and L.report_weight({"name": "x"}) is None
    assert L.report_weight(extra("x", {"weight": {"weight": "ok", "bytes": "9"}})) is None


def test_no_report_is_read_when_nothing_could_be_kept_or_removed():
    asked = []
    L.entry(mr(7), [note(f"- `a`: dismissed as not an extra, said @x\n[//]: # (itemator:named={SHA})")], lambda: asked.append(1) or {})
    assert asked == []
    api = report_api({})                                    # no artifact anywhere: no weight, nothing raised
    assert L.measured_weights(api, 7) == {} and api.failures == 0


def test_weights_add_up_across_merge_requests_and_say_at_least_if_any_is():
    def item(d, b, least=False):
        return {"decision": d, "weight": {"bytes": b, "at_least": least}}
    es = [{"extras": [item("removed", 10), item("removed", 5, True), {"decision": "removed"}]}, {"extras": [item("kept", 7), item("dismissed", 99)]}]
    assert L.weights(es) == {"kept": {"dependencies": 1, "bytes": 7, "at_least": False}, "removed": {"dependencies": 2, "bytes": 15, "at_least": True}}


def test_extras_merged_without_an_answer_are_read_from_the_newest_pipelines_report():
    api = report_api({22: {"extras": [{"name": "pandas"}, {"name": "`x`"}]}, 21: {"extras": [{"name": "old"}]}})
    assert L.unanswered_at_merge(api, 7) == ["pandas", "x"]                    # pipeline 902 only: the one it was merged on
    assert L.unanswered_at_merge(report_api({22: {"extras": []}}), 7) == []
    assert L.unanswered_at_merge(report_api({}), 7) is None                   # the artifact is gone: unknown, never 0
    e = L.entry(mr(9), [], weights_of=None, unanswered_of=lambda: L.unanswered_at_merge(api, 7))
    assert e["unanswered"] == ["pandas", "x"] and e["extras"] == []
    s = L.stats([e, L.entry(mr(8), [note(SUMMARY)]), L.entry(mr(10), [], unanswered_of=lambda: None)])
    assert (s["merged_unanswered"], s["unanswered_extras"], s["no_report"]) == (1, 2, 1)
    out = L.markdown([e])
    assert ("Merged without a recorded answer for every extra: 1 merge request (2 extras, from the job's own report on the commit "
            "that was merged).") in out
    assert "- !9 Fix a typo: merged without a recorded answer: `pandas`, `x`" in out


def test_a_summary_means_every_extra_was_answered_and_no_report_is_read():
    asked = []
    e = L.entry(mr(7), [note(SUMMARY)], unanswered_of=lambda: asked.append(1) or ["a"])
    assert e["unanswered"] == [] and asked == []
    assert "Merged without a recorded answer for every extra: 0 merge requests (0 extras" in L.markdown([e])
    assert "; could not tell for 1 (job reports are kept 30 days)." in L.markdown([L.entry(mr(8), [], unanswered_of=lambda: None)])


def test_a_summary_for_an_earlier_commit_answers_only_the_extras_it_names():
    later = dict(mr(7), sha="b" * 40)                                     # pushed again after the summary for SHA
    e = L.entry(later, [note(SUMMARY)], unanswered_of=lambda: [".gitlab-ci.yml", "added-later"])
    assert e["unanswered"] == ["added-later"]
    asked = []
    same = L.entry(dict(mr(7), sha=SHA), [note(SUMMARY)], unanswered_of=lambda: asked.append(1) or ["x"])
    assert same["unanswered"] == [] and asked == []


def test_the_report_is_read_on_the_commit_that_was_merged_and_a_missing_list_is_empty():
    a, _ = api({("GET", "projects/7/merge_requests/7/pipelines"): (200, [{"id": 902, "sha": "c" * 40}, {"id": 901, "sha": "d" * 40}]),
                ("GET", "projects/7/pipelines/902/jobs"): (200, [{"id": 22, "name": "itemator"}]),
                ("GET", "projects/7/pipelines/901/jobs"): (200, [{"id": 21, "name": "itemator"}]),
                ("GET", "projects/7/jobs/22/artifacts/itemator.json"): (200, {"extras": [{"name": "after-merge"}]}),
                ("GET", "projects/7/jobs/21/artifacts/itemator.json"): (200, {"extras": None})})
    assert L.unanswered_at_merge(a, 7, "c" * 40) == ["after-merge"]
    assert L.unanswered_at_merge(a, 7, "d" * 40) == []                    # `extras: null` is no extras, not a crash
    assert L.unanswered_at_merge(a, 7, "e" * 40) is None                  # no pipeline on that commit: cannot tell
