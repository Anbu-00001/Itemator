"""The paste-a-diff page (itemator/tryit.py, web/try.html, web/try_checks.js)."""
import json
import re
import shutil
import subprocess

import pytest

from itemator import moving as MV
from itemator import shapes as SH
from itemator import tryit as T
from itemator import untrusted as UT

import sys, pathlib  # noqa: E401
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import incident_replay as IR  # noqa: E402

EXAMPLES = json.loads((T.WEB / "try_examples.json").read_text())
WANT = {"download-over-source": "shapes", "pr-title-in-workflow": "untrusted", "decode-and-run": "shapes", "environment-to-server": "shapes", "moving-references": "moving", "ordinary": None}


def python_names(diff):
    files = IR.files_of(diff)
    return {n: bool(m.find(files)) for n, m in (("moving", MV), ("shapes", SH), ("untrusted", UT))}


def test_every_example_is_named_by_the_check_it_claims_and_the_ordinary_one_by_none():
    assert {e["id"] for e in EXAMPLES} == set(WANT)
    for e in EXAMPLES:
        said = python_names(e["diff"])
        assert [n for n, v in said.items() if v] == ([WANT[e["id"]]] if WANT[e["id"]] else []), e["id"]


def test_the_page_forbids_the_network_and_uses_none():
    html = T.page()
    assert "default-src 'none'" in html and "connect-src" not in html            # the policy: no request of any kind
    tag = '<script id="payload" type="application/json">'
    html = html[:html.index(tag)] + html[html.index("</script>", html.index(tag)):]      # the example diffs are text, not code
    for word in ("XMLHttpRequest", "WebSocket", "sendBeacon", "EventSource", "importScripts"):
        assert word not in html
    assert not re.search(r"\bfetch\(|\bimport\(|<script[^>]*\bsrc=|<link[^>]*href=|<img", html)


def test_the_data_tag_holds_no_angle_bracket_or_ampersand_and_the_code_tag_is_not_closable():
    html = T.page()
    tag = '<script id="payload" type="application/json">'
    raw = html[html.index(tag) + len(tag):html.index("</script>", html.index(tag))]
    assert not set("<>&") & set(raw)
    assert html.count("</script>") == 3                                            # data, checks, page code


def test_the_table_is_the_results_files_and_nothing_more():
    ev = T.evidence(T._load("mesa_noise_v1.json"), T._load("agent_noise_v1.json"), T._load("incident_replay_v1.json"), T._load("try_agreement_v2.json"))
    mesa, agents = T._load("mesa_noise_v1.json"), T._load("agent_noise_v1.json")
    for row in ev["rows"]:
        c = row["check"]
        for got, x in ((row["ordinary"], mesa["ordinary"]["checks"][c]), (row["agents"], agents["checks"][c])):
            assert got.startswith(f"{x['spoke']} of {x['read']}")
            assert (f"({x['readable']} changed a file it reads)" in got) == (x["readable"] != x["read"])
    assert ev["rows"][2]["ordinary"] == "0 of 1499 (4 changed a file it reads)"         # the moving check reads few commits
    assert {r["check"]: r["incidents"] for r in ev["rows"]} == {"shapes": "1 of 1", "untrusted": "1 of 1", "moving": "none in the set"}


def test_the_page_is_not_built_when_the_two_versions_disagree(monkeypatch):
    real = T._load

    def load(name):
        d = real(name)
        return {**d, "all_identical": False} if name.startswith("try_agreement") else d
    monkeypatch.setattr(T, "_load", load)
    with pytest.raises(SystemExit, match="disagree"):
        T.page()


def test_main_writes_the_page(tmp_path):
    assert T.main(["--out", str(tmp_path / "o")]) == 0
    assert "Paste a diff" in (tmp_path / "o" / "index.html").read_text()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_javascript_says_what_the_python_says_on_the_examples(tmp_path):
    units = [{"id": e["id"], "diff": e["diff"]} for e in EXAMPLES]
    (tmp_path / "u.json").write_text(json.dumps(units))
    subprocess.run(["node", str(T.WEB / "try_agree.js"), str(tmp_path / "u.json"), str(tmp_path / "o.json")], check=True)
    got = json.loads((tmp_path / "o.json").read_text())
    for e in EXAMPLES:
        files = IR.files_of(e["diff"])
        for name, mod in (("moving", MV), ("shapes", SH), ("untrusted", UT)):
            assert got[e["id"]][name] == mod.find(files), (e["id"], name)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_a_text_that_is_not_a_diff_gives_no_files(tmp_path):
    out = subprocess.run(["node", "-e", "var I=require(process.argv[1]);console.log(JSON.stringify([I.parseDiff('hello'),I.parseDiff('')]))", str(T.WEB / "try_checks.js")],
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [[], []]
