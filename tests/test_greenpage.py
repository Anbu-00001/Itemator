"""The green check (itemator/greenpage.py, web/green.html, web/deps_rule.js, web/green.js): built from the results files, allowed three hosts
only, and the browser lists the same new dependencies as the CI job and does the same SCI arithmetic as eval/sci_estimate.py. The agreement
on real manifest diffs is results/green_agreement_v2.json."""
import json
import re
import shutil
import subprocess
import sys

import pytest

from itemator import extras as X, greenpage as P

sys.path.insert(0, str(P.ROOT / "eval"))
import sci_estimate as S  # noqa: E402

NODE = pytest.mark.skipif(not shutil.which("node"), reason="needs node")


def node(script: str, *args):
    return json.loads(subprocess.run(["node", "-e", script, str(P.WEB), *args], capture_output=True, text=True, check=True).stdout)


def test_the_page_is_built_from_the_results_files_and_reaches_only_three_hosts():
    html = P.page()
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', html).group(1)
    assert "default-src 'none'" in csp and re.search(r"connect-src ([^;]+);", csp).group(1).split() == [
        "https://api.deps.dev", "https://pypi.org", "https://registry.npmjs.org"]
    assert not re.search(r"/\*(PAYLOAD|DIFF|RULE|WEIGH|GREEN)\*/", html) and "if (false) module.exports" in html
    assert html.count("<script>") == html.count("</script>") == 5
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
    assert "var s = '<\\/script><b>x</b>';" in html and html.count("</script>") == 5


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
             " [100000, 1500, 1000, 999.4, 2.894, 0.00241, 0].map(G.grams)]));", json.dumps({"c": c, "s": secs}))
    one, two = S.per_install(31.0, tuple(secs)), S.per_install(13.0, tuple(secs))
    low = one["low"]["sci_g_per_install"] + two["low"]["sci_g_per_install"]
    assert t[0]["bytes"] == 44e6 and t[0]["at_least"] is True and t[0]["lines"] == 2
    assert t[0]["g_low"] == pytest.approx(low) and t[0]["month_g_low"] == pytest.approx(low * 936) and t[0]["month_bytes"] == 44e6 * 936
    assert t[0]["month_g_high"] == pytest.approx((one["high"]["sci_g_per_install"] + two["high"]["sci_g_per_install"]) * 936)
    assert t[1]["at_least"] is False and "runs" not in t[1] and "month_g_low" not in t[1]
    assert t[2] == ["100 kg", "1.5 kg", "1 kg", "999 g", "2.89 g", "0.0024 g", "0 g"]


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
