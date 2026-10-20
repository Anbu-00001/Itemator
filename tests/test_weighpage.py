"""The weigh page (itemator/weighpage.py, web/weigh.html, web/weigh.js): built from the results file, allowed three hosts only, and the
browser's measure picks the same file as the CI job's. The live agreement on real packages is results/weigh_agreement_v1.json."""
import json
import re
import shutil
import subprocess

import pytest

from itemator import weight as W, weighpage as P

FILES = [{"filename": "x-1-py3-none-any.whl", "size": 990}, {"filename": "x-1-cp39-abi3-manylinux_2_17_x86_64.whl", "size": 450},
         {"filename": "x-1-cp312-cp312-manylinux_2_17_x86_64.whl", "size": 500}, {"filename": "x-1-py3-none-any.whl", "size": 900}, {"filename": "x-1-py2.py3-none-any.whl", "size": 850},
         {"filename": "x-1.tar.gz", "size": 100}, {"filename": "x-1-py3-none-manylinux2014_x86_64.whl", "size": 70},
         {"filename": "x-1-cp312-cp312-win_amd64.whl", "size": 7}, {"filename": "x-1-py3-none-any.whl", "size": 800, "yanked": True}]


def test_the_page_is_built_from_the_results_file_and_reaches_only_three_hosts():
    html = P.page()
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', html).group(1)
    assert "default-src 'none'" in csp and re.search(r"connect-src ([^;]+);", csp).group(1).split() == [
        "https://api.deps.dev", "https://pypi.org", "https://registry.npmjs.org"]
    assert "/*PAYLOAD*/" not in html and "/*WEIGH*/" not in html and "if (false) module.exports" in html
    result = json.loads((P.RESULTS / "aidev_weight_v1_corrected.json").read_text())
    s = P.study(result)
    assert f"of {result['readme']['lines_weighed']} dependencies" in s["sentence"] and f"{result['readme']['scanned_pull_requests']:,}" in s["sentence"]
    latest = sum(1 for r in json.loads((P.RESULTS / "aidev_weight_v1.json").read_text())["rows"]
                 if (r.get("weight") or {}).get("weight") == "ok" and r["weight"].get("of_version") == "latest")
    assert result["readme"]["weighed_at_latest"] == latest and f"one per pull request; {latest} weighed at today's latest version" in s["sentence"]
    assert [h["name"] for h in s["heaviest"]] == [h["name"] for h in result["summary"]["heaviest"]]
    assert s["heaviest"][0]["name"] == "flash-attn" and s["heaviest"][0]["at_least"] is False      # all 31 sizes read after the fix
    assert "</script" not in html.split("<script>", 1)[1].rsplit("</script>", 1)[0]


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_the_browser_picks_the_same_file_and_says_the_same_size_as_the_ci_job():
    js = ("const W = require(process.argv[1]); const f = JSON.parse(process.argv[2]);"
          "const out = []; for (let i = 0; i <= f.length; i++) { const p = W.pickWheel(f.slice(i)); out.push(p ? p.size : null); }"
          "out.push([1, 499, 2500, 3500, 1250000, 12500000, 999499, 1000000, 9949999, 10400000, 999499999, 1000000000, 27551016000].map(W.human));"
          "out.push(W.graphUrl('npm', '@types/node', '20.11.0'), W.sizeUrl('npm', '@types/node', '20.11.0'), W.pep503('Leftpad_Py.x'));"
          "process.stdout.write(JSON.stringify(out));")
    got = json.loads(subprocess.run(["node", "-e", js, str(P.WEB / "weigh.js"), json.dumps(FILES)], capture_output=True, text=True, check=True).stdout)
    want = [(W.pick_wheel(FILES[i:]) or {}).get("size") for i in range(len(FILES) + 1)]
    assert got[:len(want)] == want
    assert got[len(want)] == [W.human(n) for n in (1, 499, 2500, 3500, 1250000, 12500000, 999499, 1000000, 9949999, 10400000, 999499999, 1000000000, 27551016000)]
    assert got[-3:] == [W.graph_url("npm", "@types/node", "20.11.0"), W.size_request("npm", "@types/node", "20.11.0")[1], "leftpad-py-x"]


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_the_browser_weighs_like_the_ci_job_on_the_same_answers():
    from test_weight import GRAPH, ROUTES, ask_from, graph, node
    from test_registry import Fake
    npm_graph = "https://api.deps.dev/v3/systems/npm/packages/%40scope%2Fa/versions/1.0.0:dependencies"
    npm = {"nodes": [{"versionKey": {"name": "@scope/a", "version": "1.0.0"}, "relation": "SELF"},
                     {"versionKey": {"name": "b", "version": "2.0.0"}, "relation": "DIRECT"},
                     {"versionKey": {"name": "c", "version": "3.0.0"}, "relation": "INDIRECT", "bundled": True},
                     {"versionKey": {"name": "d", "version": "4.0.0"}, "relation": "INDIRECT"}], "error": ""}
    lengths = {"https://registry.npmjs.org/@scope/a/-/a-1.0.0.tgz": 1200, "https://registry.npmjs.org/b/-/b-2.0.0.tgz": 3400}
    cases = {"plain": dict(ROUTES),
             "unknown size": {k: v for k, v in ROUTES.items() if "big" not in k},
             "bundled": dict(ROUTES, **{GRAPH: (200, graph(node("leftpad-py", "1.2.0", "SELF"), node("tiny", "0.1", bundled=True)))}),
             "error graph": {GRAPH: (200, {"nodes": [], "error": "x"})}, "no graph": {}}
    script = ("const W = require(process.argv[1]); const cases = JSON.parse(process.argv[2]); const out = {};"
              "(async () => { for (const [k, c] of Object.entries(cases)) {"
              " const get = async (u, len) => { if (len) return u in c.lengths ? {status: 200, length: c.lengths[u]} : {status: 404, length: 50};"
              "  const r = c.routes[u]; return r ? {status: r[0], json: r[1]} : {status: 404, json: null}; };"
              " out[k] = await W.weigh(get, c.eco, c.name, c.version); } process.stdout.write(JSON.stringify(out)); })();")
    payload = {k: {"eco": "PyPI", "name": "leftpad-py", "version": "1.2.0", "routes": v, "lengths": {}} for k, v in cases.items()}
    payload["npm"] = {"eco": "npm", "name": "@scope/a", "version": "1.0.0", "routes": {npm_graph: [200, npm]}, "lengths": lengths}
    got = json.loads(subprocess.run(["node", "-e", script, str(P.WEB / "weigh.js"), json.dumps(payload)], capture_output=True, text=True,
                                    check=True).stdout)

    def npm_ask(method, url):
        if url == npm_graph:
            return 200, json.dumps(npm).encode()
        return (206, str(lengths[url]).encode()) if url in lengths else (404, b"")
    for k, routes in cases.items():
        want = W.weigh(ask_from(Fake(routes)), "PyPI", "leftpad-py", "1.2.0")
        assert {x: got[k].get(x) for x in want} == want if want["weight"] != "ok" else \
            ({x: got[k][x] for x in ("packages", "direct", "sized", "of", "bytes", "capped")} ==
             {x: want[x] for x in ("packages", "direct", "sized", "of", "bytes", "capped")}), k
    want = W.weigh(npm_ask, "npm", "@scope/a", "1.0.0")
    assert (got["npm"]["packages"], got["npm"]["sized"], got["npm"]["bytes"]) == (want["packages"], want["sized"], want["bytes"]) == (3, 2, 4600)
