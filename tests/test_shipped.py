"""The deployment page: reads deployments and merge requests from a fake GitLab, never from the network."""
import json
import urllib.parse

from itemator import decisions as D
from itemator import shipped as L

SHA = "a" * 40
SUMMARY = f"Every extra has an answer: 1 kept.\n\n- `.gitlab-ci.yml`: kept, named by @alice\n\n[//]: # (itemator:named={SHA})"
BOT = "ai-itemator-react-gitlab-ai-hackathon"


def dep(i, at, sha="b" * 40):
    return {"id": 100 + i, "iid": i, "created_at": at, "ref": "main", "sha": sha}


def mr(iid, merged, title="Fix a typo", author="alice"):
    return {"iid": iid, "title": title, "author": {"username": author}, "merged_at": merged}


def api_for(routes):
    """routes: {path-prefix: data}; the longest matching prefix answers; a missing route is a 404."""
    calls = []

    def fetch(method, url, body=None):
        path = urllib.parse.urlsplit(url).path.split("/projects/1/", 1)[1]
        calls.append(path)
        for prefix in sorted(routes, key=len, reverse=True):
            if path == prefix or path.startswith(prefix):
                return 200, routes[prefix]
        return 404, None
    api = D.Api("https://gitlab.example/api/v4", 1, "tok", fetch=fetch)
    api.calls = calls
    return api


NOTES = [{"body": SUMMARY, "author": {"username": BOT}, "system": False, "created_at": "2026-10-13T10:00:00Z"}]


def test_gitlabs_own_list_is_used_when_it_has_one():
    api = api_for({"deployments": [dep(2, "2026-10-14T10:00:00Z"), dep(1, "2026-10-13T10:00:00Z")],
                   "deployments/102/merge_requests": [mr(7, "2026-10-14T09:00:00Z")], "deployments/101/merge_requests": [],
                   "merge_requests/7/notes": NOTES, "merge_requests": []})
    r = L.build(api, "production", "main")
    first, second = r["deployments"]
    assert first["source"].startswith("GitLab's list") and first["stats"]["extras"] == 1
    assert first["merge_requests"][0]["extras"][0]["who"] == "alice"
    assert second["source"].startswith("merge requests merged since")      # an empty list from GitLab falls back to the window


def test_the_window_runs_from_the_previous_deployment_to_this_one():
    inside, before, after = mr(5, "2026-10-14T05:00:00Z"), mr(4, "2026-10-13T05:00:00Z"), mr(6, "2026-10-14T11:00:00Z")
    api = api_for({"deployments": [dep(2, "2026-10-14T10:00:00Z"), dep(1, "2026-10-13T10:00:00Z")],
                   "deployments/102/merge_requests": [], "deployments/101/merge_requests": [],
                   "merge_requests": [inside, before, after], "merge_requests/5/notes": NOTES})
    first = L.build(api, "production", "main")["deployments"][0]
    assert [m["iid"] for m in first["merge_requests"]] == [5]


def test_no_deployment_gives_an_honest_empty_page():
    r = L.build(api_for({"deployments": []}), "production", "main")
    assert r["deployments"] == [] and "No successful deployment yet." in L.page(r)


def test_everything_that_came_from_gitlab_is_escaped_in_the_page():
    evil = mr(9, "2026-10-14T09:00:00Z", title="<script>alert(1)</script>")
    notes = [{"body": f"- `<img src=x onerror=1>`: kept, named by @alice\n\n[//]: # (itemator:named={SHA})", "author": {"username": BOT},
              "system": False, "created_at": "2026-10-13T10:00:00Z"}]
    api = api_for({"deployments": [dep(1, "2026-10-14T10:00:00Z")], "deployments/101/merge_requests": [evil], "merge_requests/9/notes": notes})
    out = L.page(L.build(api, "production", "main"))
    assert "<script>" not in out and "<img" not in out and "&lt;" in out


def test_a_merge_request_without_a_summary_or_a_job_report_is_said_to_have_none():
    api = api_for({"deployments": [dep(1, "2026-10-14T10:00:00Z")], "deployments/101/merge_requests": [mr(3, "2026-10-14T09:00:00Z")],
                   "merge_requests/3/notes": []})
    out = L.page(L.build(api, "production", "main"))
    assert "could not tell (no job report left" in out and "; could not tell for 1 (job reports are kept 30 days)." in out


def test_extras_merged_with_no_answer_are_named_and_counted_at_the_top():
    base = {"deployments": [dep(1, "2026-10-14T10:00:00Z")], "deployments/101/merge_requests": [mr(3, "2026-10-14T09:00:00Z")],
            "merge_requests/3/notes": [], "merge_requests/3/pipelines": [{"id": 900}], "pipelines/900/jobs": [{"id": 55, "name": "itemator"}]}
    out = L.page(L.build(api_for(dict(base, **{"jobs/55/artifacts/itemator.json": {"extras": [{"name": "<b>x</b>"}, {"name": "pandas"}]}})),
                         "production", "main"))
    assert ("<strong>In the 1 deployment below, merged without a recorded answer for every extra: 1 merge request (2 extras, from the job&#x27;s own report on "
            "the commit that was merged).</strong> Itemator keeps, moves or removes nothing until a person replies") in out
    assert "<strong>merged without a recorded answer</strong>: <code>&lt;b&gt;x&lt;/b&gt;</code>, <code>pandas</code>" in out and "<b>x" not in out
    none = L.page(L.build(api_for(dict(base, **{"jobs/55/artifacts/itemator.json": {"extras": []}})), "production", "main"))
    assert "!3 Fix a typo: no extras" in none and "every extra: 0 merge requests (0 extras" in none


def test_only_the_reaction_account_is_believed():
    forged = [{"body": SUMMARY, "author": {"username": "mallory"}, "system": False, "created_at": "2026-10-13T10:00:00Z"}]
    api = api_for({"deployments": [dep(1, "2026-10-14T10:00:00Z")], "deployments/101/merge_requests": [mr(3, "2026-10-14T09:00:00Z")],
                   "merge_requests/3/notes": forged})
    assert L.build(api, "production", "main")["deployments"][0]["stats"]["extras"] == 0


def test_main_without_a_job_token_does_nothing(capsys, monkeypatch, tmp_path):
    for k in ("CI_API_V4_URL", "CI_PROJECT_ID", "CI_JOB_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert L.main(["--out", str(tmp_path / "public")]) == 0
    assert not (tmp_path / "public").exists() and "nothing done" in capsys.readouterr().out


def test_main_writes_the_page_and_the_json(monkeypatch, tmp_path):
    api = api_for({"deployments": [dep(1, "2026-10-14T10:00:00Z")], "deployments/101/merge_requests": [mr(3, "2026-10-14T09:00:00Z")],
                   "merge_requests/3/notes": NOTES})
    monkeypatch.setattr(L.D, "Api", lambda *a, **k: api)
    monkeypatch.setenv("CI_JOB_TOKEN", "t")
    assert L.main(["--api", "https://x/api/v4", "--project", "1", "--out", str(tmp_path / "public")]) == 0
    assert "What shipped to production" in (tmp_path / "public" / "index.html").read_text()
    assert json.loads((tmp_path / "public" / "shipped.json").read_text())["deployments"][0]["stats"]["extras"] == 1


def test_a_request_gitlab_refuses_is_counted_not_hidden():
    r = L.build(api_for({}), "production", "main")        # every route is a 404
    assert r["deployments"] == [] and r["unreadable_requests"] == 1


def test_one_merge_request_is_not_plural():
    api = api_for({"deployments": [dep(1, "2026-10-14T10:00:00Z")], "deployments/101/merge_requests": [mr(3, "2026-10-14T09:00:00Z")],
                   "merge_requests/3/notes": NOTES})
    out = L.page(L.build(api, "production", "main"))
    assert "1 merge request," in out and "1 merge requests" not in out


def test_the_deploy_job_runs_in_a_resource_group_and_reads_the_environment_scoped_variable():
    import pathlib
    import yaml
    job = yaml.safe_load((pathlib.Path(__file__).resolve().parent.parent / ".gitlab-ci.yml").read_text())["publish-package"]
    assert job["resource_group"] == "production" and job["environment"]["name"] == "production"
    assert job["environment"]["url"] == "https://showcase-3cd72e.gitlab.io/"      # the environment list gets an Open button
    assert any("DEPLOY_TARGET" in line for line in job["script"])


def test_the_page_says_what_a_remove_kept_out_of_every_fresh_install():
    summary = (f"Every extra has an answer: 1 kept, 1 removed.\n\n- `pandas`: removed from this merge request, by @bob\n"
               f"- `requests`: kept, named by @alice\n\n[//]: # (itemator:named={SHA})")
    notes = [{"body": summary, "author": {"username": BOT}, "system": False, "created_at": "2026-10-13T10:00:00Z"}]

    def pkg(b, of=3, sized=3):
        return {"weight": {"weight": "ok", "bytes": b, "capped": False, "of": of, "sized": sized}}
    report = {"extras": [{"name": "pandas", "plain_facts": {"registry": {"packages": [pkg(31_000_000)]}}},
                         {"name": "requests", "plain_facts": {"registry": {"packages": [pkg(476_000, of=5, sized=4)]}}}]}
    routes = {"deployments": [dep(1, "2026-10-14T10:00:00Z")], "deployments/101/merge_requests": [mr(7, "2026-10-14T09:00:00Z")],
              "merge_requests/7/notes": notes, "merge_requests": [], "merge_requests/7/pipelines": [{"id": 900}],
              "pipelines/900/jobs": [{"id": 55, "name": "itemator"}], "jobs/55/artifacts/itemator.json": report}
    r = L.build(api_for(routes), "production", "main")
    assert r["deployments"][0]["weight"]["removed"] == {"dependencies": 1, "bytes": 31_000_000, "at_least": False}
    out = L.page(r)
    assert ("Kept out by a reviewer's <code>remove</code>: about 31 MB on every fresh install</strong> (by the SCI method, a bracket "
            "from borrowed coefficients: 0.014 g to 2.1 g CO2e each time), 1 new dependency with what it") in out
    assert "<code>requests</code> (at least 476 kB on every fresh install) kept by @alice" in out
    kept_only = dict(routes, **{"merge_requests/7/notes": [{"body": f"Every extra has an answer: 1 kept.\n\n- `requests`: kept, named by @alice\n\n[//]: # (itemator:named={SHA})",
                                                              "author": {"username": BOT}, "system": False, "created_at": "2026-10-13T11:00:00Z"}]})
    out = L.page(L.build(api_for(kept_only), "production", "main"))
    assert "Kept out" not in out and "(at least 476 kB on every fresh install) kept" in out
    plain = L.page(L.build(api_for({"deployments": [dep(1, "2026-10-14T10:00:00Z")], "deployments/101/merge_requests": [mr(7, "2026-10-14T09:00:00Z")],
                                    "merge_requests/7/notes": NOTES, "merge_requests": []}), "production", "main"))
    assert "Kept out" not in plain and "fresh install" not in plain


def test_each_merge_request_says_who_merged_it():
    merged = dict(mr(3, "2026-10-14T09:00:00Z"), merge_user={"username": "<bo>"})
    api = api_for({"deployments": [dep(1, "2026-10-14T10:00:00Z")], "deployments/101/merge_requests": [merged],
                   "merge_requests/3/notes": [{"body": SUMMARY, "author": {"username": BOT}, "system": False, "created_at": "2026-10-13T11:00:00Z"}]})
    out = L.page(L.build(api, "production", "main"))
    assert "kept by @alice; merged by @bo</li>" in out and "<bo>" not in out
    plain = api_for({"deployments": [dep(1, "2026-10-14T10:00:00Z")], "deployments/101/merge_requests": [mr(3, "2026-10-14T09:00:00Z")],
                     "merge_requests/3/notes": []})
    assert "merged by" not in L.page(L.build(plain, "production", "main"))


def test_the_front_page_links_every_page_the_pages_job_builds():
    import pathlib, re
    out = L.page({"environment": "production", "deployments": []})
    assert L.NAV in out
    ci = (pathlib.Path(__file__).resolve().parent.parent / ".gitlab-ci.yml").read_text()
    built = set(re.findall(r"--out public/(\w+)", ci))
    linked = set(re.findall(r'href="(\w+)/"', L.NAV))
    assert linked == built == {"try", "green", "weigh", "catches", "map", "answers"}
