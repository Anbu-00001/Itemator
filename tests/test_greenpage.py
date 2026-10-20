"""The green check (itemator/greenpage.py, web/green.html, web/deps_rule.js, web/green.js): built from the results files, allowed three hosts
only, and the browser lists the same new dependencies as the CI job and does the same SCI arithmetic as eval/sci_estimate.py. The agreement
on real manifest diffs is results/green_agreement_v2.json."""
import json
import re
import shutil
import subprocess
import sys

import pytest

from itemator import extras as X, greenpage as P, sci as SCI

sys.path.insert(0, str(P.ROOT / "eval"))
import sci_estimate as S  # noqa: E402

NODE = pytest.mark.skipif(not shutil.which("node"), reason="needs node")


def node(script: str, *args):
    return json.loads(subprocess.run(["node", "-e", script, str(P.WEB), *args], capture_output=True, text=True, check=True).stdout)


def test_the_page_is_built_from_the_results_files_and_reaches_only_three_hosts():
    html = P.page()
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', html).group(1)
    assert "default-src 'none'" in csp and re.search(r"connect-src ([^;]+);", csp).group(1).split() == [
        "https://api.deps.dev", "https://pypi.org", "https://registry.npmjs.org", "https://gitlab.com", "https://api.github.com"]
    assert not re.search(r"/\*(PAYLOAD|DIFF|RULE|WEIGH|GREEN|FETCH)\*/", html) and "if (false) module.exports" in html
    assert html.count("<script>") == html.count("</script>") == 6
    for body in re.findall(r"<script>(.*?)</script>", html, re.S):
        assert "</script" not in body
    sci = json.loads((P.RESULTS / "sci_estimate_v1.json").read_text())
    agree = json.loads((P.RESULTS / P.AGREEMENT).read_text())
    d = P.payload()
    assert d["coefficients"] == sci["coefficients"] and d["seconds"] == sci["inputs"]["seconds_added"]
    assert agree["all_identical"] and d["agreement"].startswith(f"{agree['identical']:,} of {agree['units']:,} ")
    assert f"{d['seconds'][0]} to {d['seconds'][1]} s per added line" in d["sci"]


def test_a_closing_script_tag_in_a_source_cannot_end_its_script(tmp_path, monkeypatch):
    for f in P.WEB.iterdir():
        (tmp_path / f.name).write_bytes(f.read_bytes())
    (tmp_path / "green.js").write_text("var s = '</script><b>x</b>';\n")
    monkeypatch.setattr(P, "WEB", tmp_path)
    html = P.page()
    assert "var s = '<\\/script><b>x</b>';" in html and html.count("</script>") == 6


@NODE
def test_the_browser_does_the_same_sci_arithmetic_as_the_results_file():
    cases = [[31.0, [1.21, 1.65]], [0.57, [1.21, 1.65]], [0.0, [0.0, 0.0]], [1234.5, [3.0, 9.5]]]
    got = node("const G = require(process.argv[1] + '/green.js'); const c = JSON.parse(process.argv[2]);"
               "process.stdout.write(JSON.stringify(JSON.parse(process.argv[3]).map(([mb, s]) => G.perInstall(c, mb, s))));",
               json.dumps(P.payload()["coefficients"]), json.dumps(cases))
    for (mb, secs), g in zip(cases, got):
        want = S.per_install(mb, tuple(secs))
        for end in ("low", "high"):
            assert g[end] == pytest.approx(want[end], rel=1e-12, abs=1e-15), (mb, end)


@NODE
def test_a_total_sums_each_line_and_a_month_multiplies_by_the_pipelines():
    c, secs = P.payload()["coefficients"], P.payload()["seconds"]
    t = node("const G = require(process.argv[1] + '/green.js'); const a = JSON.parse(process.argv[2]);"
             "process.stdout.write(JSON.stringify([G.total(a.c, a.s, [{bytes: 31e6, at_least: false}, {bytes: 13e6, at_least: true}], 936),"
             " G.total(a.c, a.s, [{bytes: 5e5, at_least: false}], 0),"
             " [100000, 1500, 1000, 999.4, 2.894, 0.00241, 0, 13.4, 9.97, 0.0999, 0.00097].map(G.grams)]));", json.dumps({"c": c, "s": secs}))
    one, two = S.per_install(31.0, tuple(secs)), S.per_install(13.0, tuple(secs))
    low = one["low"]["sci_g_per_install"] + two["low"]["sci_g_per_install"]
    assert t[0]["bytes"] == 44e6 and t[0]["at_least"] is True and t[0]["lines"] == 2
    assert t[0]["g_low"] == pytest.approx(low) and t[0]["month_g_low"] == pytest.approx(low * 936) and t[0]["month_bytes"] == 44e6 * 936
    assert t[0]["month_g_high"] == pytest.approx((one["high"]["sci_g_per_install"] + two["high"]["sci_g_per_install"]) * 936)
    assert t[1]["at_least"] is False and "runs" not in t[1] and "month_g_low" not in t[1]
    assert t[2] == [SCI.grams(x) for x in (100000, 1500, 1000, 999.4, 2.894, 0.00241, 0, 13.4, 9.97, 0.0999, 0.00097)]


@NODE
def test_the_examples_list_what_the_ci_job_lists():
    got = node("const D = require(process.argv[1] + '/deps_rule.js'), I = require(process.argv[1] + '/try_checks.js');"
               "const ex = require(process.argv[1] + '/green_examples.json');"
               "process.stdout.write(JSON.stringify(ex.map((e) => { const f = I.parseDiff(e.diff);"
               " return {files: f, extras: D.extras(e.issue, f), added: D.added(e.issue, f).map((r) => [r.name, r.asked, D.pinned(r)])}; })));")
    examples = json.loads((P.WEB / "green_examples.json").read_text())
    for e, g in zip(examples, got):
        want = [{k: getattr(x, k) for k in ("kind", "path", "name", "why")} for x in X._new_dependencies(e["issue"], g["files"])]
        assert g["extras"] == want, e["id"]
    assert [g["added"] for g in got] == [
        [["tenacity", True, "8.2.3"], ["pandas", False, "2.2.2"], ["boto3", False, "1.34.131"]],
        [["moment", False, "2.30.1"], ["lodash", False, "4.17.21"]],
        [["python-dateutil", True, "2.9.0.post0"]]]


@NODE
def test_only_an_exact_pin_is_weighed_at_its_version():
    lines = [["requirements", "pandas==2.2.2"], ["requirements", "pandas>=2.2"], ["requirements", "pandas == 2.2.2 ; python_version>'3.8'"],
             ["pyproject", "\"httpx==0.27.0\","], ["pyproject", "\"httpx~=0.27\","], ["npm", "\"lodash\": \"4.17.21\","],
             ["npm", "\"lodash\": \"^4.17.21\","], ["npm", "\"lodash\": \"=4.17.21\""], ["npm", "\"left\": \"github:a/b\","]]
    got = node("const D = require(process.argv[1] + '/deps_rule.js');"
               "process.stdout.write(JSON.stringify(JSON.parse(process.argv[2]).map(([m, l]) => D.pinned({manifest: m, line: l}))));",
               json.dumps(lines))
    assert got == ["2.2.2", None, "2.2.2", "0.27.0", None, "4.17.21", None, "4.17.21", None]


@NODE
def test_python_line_breaks_split_the_same_in_the_browser():
    text = "a b\r\nc\x0bd\x85e\n\nf\n"
    assert node("const D = require(process.argv[1] + '/deps_rule.js'); process.stdout.write(JSON.stringify(D.splitlines(process.argv[2])));",
                text) == text.splitlines()


FETCH = ("const F = require(process.argv[1] + '/green_fetch.js'); const c = JSON.parse(process.argv[2]); const seen = [];"
         "const get = async (u) => { seen.push(u); const k = Object.keys(c.routes).find((p) => u.startsWith(p));"
         " return k ? {status: c.routes[k][0], json: c.routes[k][1]} : {status: 404, json: null}; };"
         "(async () => { const out = await F.read(get, F.parseLink(c.link)); process.stdout.write(JSON.stringify({out, seen})); })();")
GL = "https://gitlab.com/api/v4/projects/g%2Fsub%2Fp/merge_requests/7"
GH = "https://api.github.com/repos/o/r"


@NODE
def test_a_link_is_read_only_from_gitlab_or_github():
    got = node("const F = require(process.argv[1] + '/green_fetch.js');"
               "process.stdout.write(JSON.stringify(JSON.parse(process.argv[2]).map(F.parseLink)));", json.dumps([
                   "https://gitlab.com/g/sub/p/-/merge_requests/7", "https://gitlab.com/g/p/-/merge_requests/7/diffs?x=1 ",
                   "https://github.com/o/r/pull/12", "https://github.com/o/r/pull/12/files", "http://gitlab.com/g/p/-/merge_requests/7",
                   "https://evil.example/g/p/-/merge_requests/7", "https://github.com/o/r/issues/12", "https://gitlab.com.evil.example/g/p/-/merge_requests/7",
                   "see https://gitlab.com/g/p/-/merge_requests/7"]))
    assert got == [{"host": "gitlab", "project": "g/sub/p", "number": 7}, {"host": "gitlab", "project": "g/p", "number": 7},
                   {"host": "github", "owner": "o", "repo": "r", "number": 12}, {"host": "github", "owner": "o", "repo": "r", "number": 12},
                   None, None, None, None, None]


@NODE
def test_a_gitlab_merge_request_is_read_as_the_ci_job_reads_it():
    diffs = [{"new_path": f"f{i}.py", "diff": "@@ -1 +1 @@\n-a\n+b\n"} for i in range(100)]
    page2 = [{"new_path": "requirements.txt", "new_file": True, "diff": "@@ -0,0 +1 @@\n+pandas==2.2.2\n"},
             {"new_path": "gone.py", "deleted_file": True, "diff": ""}, {"new_path": "new_name.py", "renamed_file": True, "diff": ""},
             {"new_path": "big.json", "diff": "", "too_large": True}]
    issues = [{"title": "Fix the export", "description": "Retry uploads."}, {"title": "Second", "description": None}]
    routes = {f"{GL}/diffs?per_page=100&page=1": [200, diffs], f"{GL}/diffs?per_page=100&page=2": [200, page2], f"{GL}/closes_issues": [200, issues]}
    got = node(FETCH, json.dumps({"link": "https://gitlab.com/g/sub/p/-/merge_requests/7", "routes": routes}))["out"]
    assert len(got["files"]) == 104 and got["files"][100] == {"filename": "requirements.txt", "status": "added", "patch": "@@ -0,0 +1 @@\n+pandas==2.2.2\n", "too_large": False}
    assert [f["status"] for f in got["files"][101:]] == ["removed", "renamed", "modified"] and got["skipped"] == ["big.json"]
    ci_text = "\n\n".join(f"{i['title']}\n{i['description'] or ''}" for i in issues)      # itemator/ci.py's issue_text
    assert got["issue"] == ci_text and got["issueFrom"] == "the 2 issues it closes" and got["truncated"] is False


@NODE
def test_a_gitlab_merge_request_that_closes_nothing_or_is_private():
    routes = {f"{GL}/diffs?per_page=100&page=1": [200, []], f"{GL}/closes_issues": [200, []]}
    got = node(FETCH, json.dumps({"link": "https://gitlab.com/g/sub/p/-/merge_requests/7", "routes": routes}))["out"]
    assert got["issue"] == "" and got["issueFrom"] == "none (it closes no issue)"
    assert node(FETCH, json.dumps({"link": "https://gitlab.com/g/sub/p/-/merge_requests/7", "routes": {}}))["out"] == {"error": "not found, or not public"}


@NODE
def test_a_github_pull_request_is_checked_against_the_issue_it_closes_else_its_own_text():
    files = [{"filename": "package.json", "status": "modified", "patch": "@@ -1 +1 @@\n", "changes": 2}, {"filename": "huge.lock", "status": "modified", "changes": 9000}]
    base = {f"{GH}/pulls/12/files?per_page=100&page=1": [200, files]}
    closes = dict(base, **{f"{GH}/pulls/12": [200, {"title": "Add flag", "body": "Adds it.\n\nFixes #34"}], f"{GH}/issues/34": [200, {"title": "Want a flag", "body": "Please."}]})
    r = node(FETCH, json.dumps({"link": "https://github.com/o/r/pull/12", "routes": closes}))
    assert r["out"]["issue"] == "Want a flag\nPlease." and r["out"]["issueFrom"] == "issue #34, which it closes" and r["out"]["skipped"] == ["huge.lock"]
    own = dict(base, **{f"{GH}/pulls/12": [200, {"title": "Add flag", "body": "Mentions #34 but closes nothing"}]})
    r = node(FETCH, json.dumps({"link": "https://github.com/o/r/pull/12", "routes": own}))
    assert r["out"]["issue"] == "Add flag\nMentions #34 but closes nothing" and not any("/issues/" in u for u in r["seen"])
    assert r["out"]["issueFrom"] == "the pull request's own title and text (it closes no issue)"
    limited = {f"{GH}/pulls/12": [403, None]}
    assert "hourly limit" in node(FETCH, json.dumps({"link": "https://github.com/o/r/pull/12", "routes": limited}))["out"]["error"]
