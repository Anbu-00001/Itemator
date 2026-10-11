"""T12a: where each extra sits in the diff, the thread stub, the plain facts and the job-log copy.

Hunks are written out by hand, with the line numbers worked out from the hunk header; the git tests
check the same numbers against the real files at the base and the head."""
import datetime
import importlib.util
import json
import os
import subprocess
import sys
import urllib.request

import pytest

from itemator import ci
from itemator.extras import Extra
from test_ci import AUDIT, FakeHttp, Repo, issue, job, mr, routes


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for k, v in {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "T",
                 "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": os.devnull,
                 "GIT_CONFIG_NOSYSTEM": "1"}.items():
        monkeypatch.setenv(k, v)

    def no_network(*a, **k):
        raise AssertionError("a test reached the network")
    monkeypatch.setattr(urllib.request, "urlopen", no_network)


def F(name, patch, status="modified", **kw):
    return {"filename": name, "status": status, "patch": patch, **kw}


def anchor(e, *files):
    return ci.anchor_for(e, {f["filename"]: f for f in files})


def at(old_path, new_path, old_line, new_line):
    return {"old_path": old_path, "new_path": new_path, "old_line": old_line, "new_line": new_line}


def added(*texts):
    return f"@@ -0,0 +1,{len(texts)} @@\n" + "".join(f"+{t}\n" for t in texts)


def ci_extra(path):
    return Extra("ci_or_config", path, path, "changes CI config; the issue does not mention it")


# ------------------------------------------------------------ line counting

def test_diff_lines_numbers_context_added_and_removed():
    patch = ("@@ -40,3 +41,4 @@ def f():\n ctx a\n-old b\n+new b\n+new c\n ctx d\n"
             "@@ -100,2 +102,2 @@\n ctx e\n-old f\n+new f\n")
    assert list(ci.diff_lines(patch)) == [
        (" ", 40, 41, "ctx a"), ("-", 41, None, "old b"), ("+", None, 42, "new b"), ("+", None, 43, "new c"),
        (" ", 42, 44, "ctx d"), (" ", 100, 102, "ctx e"), ("-", 101, None, "old f"), ("+", None, 103, "new f")]


@pytest.mark.parametrize("patch, expected", [
    ("@@ -1,2 +1,3 @@\n a\n-b\n\\ No newline at end of file\n+b\n+c\n",
     [(" ", 1, 1, "a"), ("-", 2, None, "b"), ("+", None, 2, "b"), ("+", None, 3, "c")]),
    ("@@ -1 +1,2 @@\n a\n+b\n\\ No newline at end of file\n", [(" ", 1, 1, "a"), ("+", None, 2, "b")]),
    ("@@ -1 +1 @@\n-x\n+y\n", [("-", 1, None, "x"), ("+", None, 1, "y")]),
    ("@@ -0,0 +1,2 @@\n+a\n+b\n", [("+", None, 1, "a"), ("+", None, 2, "b")]),
    ("@@ -1,2 +0,0 @@\n-a\n-b\n", [("-", 1, None, "a"), ("-", 2, None, "b")]),
    ("@@ -5,0 +6,2 @@\n+a\n+b\n", [("+", None, 6, "a"), ("+", None, 7, "b")]),
    ("@@ -1,2 +1,2 @@\n--- a\n+++ b\n c\n", [("-", 1, None, "-- a"), ("+", None, 1, "++ b"), (" ", 2, 2, "c")]),
    ("@@ -1,3 +1,3 @@\n a\n\n-c\n+d\n",
     [(" ", 1, 1, "a"), (" ", 2, 2, ""), ("-", 3, None, "c"), ("+", None, 3, "d")]),
    ("", []), (None, []),
])
def test_diff_lines_edge_cases(patch, expected):
    assert list(ci.diff_lines(patch)) == expected


# ------------------------------------------------------ one example per kind

REQ = "@@ -40,3 +40,5 @@\n numpy==1.26.0\n+# build tools\n+leftpad-py==1.0.0\n pandas==2.1.0\n scipy==1.11\n"
PYPROJECT = ('@@ -8,4 +8,8 @@ dependencies = [\n     "requests>=2",\n+    "other-lib>=2",\n'
             '+    "leftpad-py>=1.0",\n ]\n \n+[project.optional-dependencies]\n'
             '+dev = ["leftpad-py>=1.0", "pytest"]\n [tool.x]\n')


def dep(path, name="leftpad-py"):
    return Extra("new_dependency", path, name, f"adds package {name}; the issue does not name it")


def test_new_dependency_anchors_on_the_line_that_names_the_package():
    a, reason = anchor(dep("requirements.txt"), F("requirements.txt", REQ))
    assert (a, reason) == (at("requirements.txt", "requirements.txt", None, 42), None)


def test_new_dependency_anchors_on_the_first_line_when_several_name_it():
    a, _ = anchor(dep("pyproject.toml"), F("pyproject.toml", PYPROJECT))
    assert a == at("pyproject.toml", "pyproject.toml", None, 10)


@pytest.mark.parametrize("name, lines, expected", [
    ("Foo_Bar", ["baz==1", "foo-bar==2"], 2),                    # case, '-' and '_' are the same name
    ("foo-bar", ["zzz==1", "foo.bar==2"], 2),
    ("req", ["requests==2", "req==1"], 2),                       # not the start of a longer name
    ("quests", ["requests==2", "quests==1"], 2),                 # not the end of one
    ("@scope/pkg", ['"scope-other": "1"', '"@scope/pkg": "^1"'], 2),
    ("ghost", ["a==1", "b==2"], 1),                              # named nowhere: the first added line
])
def test_new_dependency_line_matching(name, lines, expected):
    a, _ = anchor(dep("requirements.txt", name), F("requirements.txt", added(*lines)))
    assert a["new_line"] == expected and a["old_line"] is None


GITLAB_CI = ("@@ -1,4 +1,5 @@\n stages:\n-  - test\n+  - lint\n+  - test\n job:\n   script: x\n"
             "@@ -20,2 +21,3 @@\n a\n+b\n c\n")
PACKAGE = ('@@ -5,5 +5,7 @@\n   "version": "1.0.0",\n+  "private": true,\n   "scripts": {\n'
           '+    "postinstall": "node setup.js",\n     "test": "jest"\n   }\n }\n')


def test_config_change_anchors_on_the_first_added_line():
    a, _ = anchor(ci_extra(".gitlab-ci.yml"), F(".gitlab-ci.yml", GITLAB_CI))
    assert a == at(".gitlab-ci.yml", ".gitlab-ci.yml", None, 2)       # after the removed line, not on it


def test_added_and_deleted_config_files():
    assert anchor(ci_extra("ci.yml"), F("ci.yml", added("a", "b", "c"), "added"))[0] == at("ci.yml", "ci.yml", None, 1)
    gone = F("ci.yml", "@@ -1,3 +0,0 @@\n-a\n-b\n-c\n", "removed")
    assert anchor(ci_extra("ci.yml"), gone)[0] == at("ci.yml", "ci.yml", 1, None)    # only removed lines to anchor on


def test_npm_script_anchors_on_its_own_line():
    e = Extra("ci_or_config", "package.json", "postinstall", "adds or changes the npm postinstall script, which runs on install")
    assert anchor(e, F("package.json", PACKAGE))[0] == at("package.json", "package.json", None, 8)


def test_lint_settings_in_pyproject_anchor_on_the_first_added_line():
    e = Extra("ci_or_config", "pyproject.toml", "pyproject.toml", "changes lint settings (tool.ruff); the issue does not mention them")
    patch = '@@ -1,2 +1,4 @@\n [project]\n+version = "2"\n [tool.ruff]\n+select = ["E"]\n'
    assert anchor(e, F("pyproject.toml", patch))[0] == at("pyproject.toml", "pyproject.toml", None, 2)


@pytest.mark.parametrize("f", [
    F("logo.png", None, "added", binary=True),
    F("empty.txt", None, "added"),
    F("logo.png", "@@ -0,0 +1 @@\n+x\n", "added", binary=True),     # the flag wins over a patch
    F("tools/Makefile", None, "renamed", previous_filename="Makefile"),
])
def test_no_text_patch_means_no_anchor(f):
    e = Extra("binary_or_large_added", f["filename"], f["filename"], "adds a file GitHub marks binary")
    assert anchor(e, f) == (None, "no text patch")


def test_large_text_file_anchors_on_its_first_line_unless_gitlab_hides_the_diff():
    e = Extra("binary_or_large_added", "data/big.json", "data/big.json", "adds a file of 2,000,000 bytes (over 1 MB)")
    assert anchor(e, F("data/big.json", added("{", "}"), "added"))[0] == at("data/big.json", "data/big.json", None, 1)
    limit = "@@ -0,0 +1 @@\n+" + "x" * (ci.MAX_PATCH_BYTES - 16) + "\n"      # 204,800 bytes
    assert len(limit.encode()) == ci.MAX_PATCH_BYTES
    assert anchor(e, F("data/big.json", limit, "added"))[0]["new_line"] == 1
    over = limit.replace("xx", "xxx", 1)
    assert anchor(e, F("data/big.json", over, "added")) == (None, "patch over GitLab's size limit")


def test_extra_whose_file_is_not_in_the_diff():
    assert anchor(ci_extra("ci.yml")) == (None, "file not in the diff")


TESTS = ("@@ -3,8 +3,5 @@\n import pytest\n-import os\n \n-def test_gone():\n-    assert f() == 1\n \n"
         " def test_kept():\n     pass\n")


def test_removed_test_anchors_on_the_removed_definition_not_on_the_first_removed_line():
    e = Extra("tests_removed", "t/test_a.py", "t/test_a.py", "removes 1 more test definitions than it adds")
    assert anchor(e, F("t/test_a.py", TESTS))[0] == at("t/test_a.py", "t/test_a.py", 6, None)


def test_removed_assertions_anchor_on_the_removed_assertion():
    e = Extra("tests_removed", "t/test_a.py", "t/test_a.py", "removes 1 more assertion lines than it adds")
    assert anchor(e, F("t/test_a.py", TESTS))[0] == at("t/test_a.py", "t/test_a.py", 7, None)


def test_deleted_test_file():
    e = Extra("tests_removed", "t/test_x.py", "t/test_x.py", "deletes this test file")
    gone = F("t/test_x.py", "@@ -1,6 +0,0 @@\n-import pytest\n-\n-\n-def test_x():\n-    assert 1\n-    pass\n", "removed")
    assert anchor(e, gone)[0] == at("t/test_x.py", "t/test_x.py", 4, None)
    plain = F("t/test_x.py", "@@ -1,2 +0,0 @@\n-x = 1\n-y = 2\n", "removed")
    assert anchor(e, plain)[0] == at("t/test_x.py", "t/test_x.py", 1, None)         # no definition: the first removed line


API = ("@@ -1,3 +1,5 @@\n import os\n+import sys\n+import re\n \n x = 1\n"
       "@@ -120,7 +122,3 @@\n x = 1\n-def helper():\n-    pass\n-def old_fn(a):\n-    return a\n \n class Keep:\n")


def api(name, path="api.py"):
    return Extra("public_api_removed", path, name, f"removes public def/class {name}")


def test_removed_symbol_anchors_on_the_line_that_defines_it():
    assert anchor(api("old_fn"), F("api.py", API))[0] == at("api.py", "api.py", 123, None)
    assert anchor(api("helper"), F("api.py", API))[0] == at("api.py", "api.py", 121, None)


def test_removed_export_in_a_list():
    patch = "@@ -3,3 +3,1 @@\n a\n-export { alpha, beta };\n-const z = 1;\n"
    assert anchor(api("beta", "src/index.ts"), F("src/index.ts", patch))[0] == at("src/index.ts", "src/index.ts", 4, None)


def test_renamed_file_keeps_both_paths():
    gone = F("pkg/new.py", "@@ -10,2 +10,1 @@\n keep = 1\n-def gone():\n", "renamed", previous_filename="pkg/old.py")
    assert anchor(api("gone", "pkg/new.py"), gone)[0] == at("pkg/old.py", "pkg/new.py", 11, None)
    make = F("build/Makefile", "@@ -1,3 +1,4 @@\n all:\n \tcc x\n+\tcc y\n clean:\n", "renamed", previous_filename="Makefile")
    e = Extra("ci_or_config", "build/Makefile", "build/Makefile", "changes build config; the issue does not mention it")
    assert anchor(e, make)[0] == at("Makefile", "build/Makefile", None, 3)


# ------------------------------------------------------------- mass events

def facts_for(files, issue_text="Parser drops trailing comma"):
    iss = [{"iid": 12, "ref": "#12", "title": issue_text, "description": "", "author_id": 1}]
    return ci.facts(mr_iid=5, mr_title="t", mr_description="", mr_author_id=2, issues=iss, issues_from="closes_issues",
                    files=files, repo="grp/showcase", base_sha="a" * 40, head_sha="b" * 40, warnings=[],
                    now=datetime.datetime(2026, 10, 11, tzinfo=datetime.timezone.utc))


def only_extra(report):
    assert len(report["extras"]) == 1, report["extras"]
    return report["extras"][0]


def test_mass_event_of_config_files_anchors_on_the_first_file():
    files = [F(f".github/workflows/w{i:02d}.yml", added("on: push", f"# {i}"), "added", additions=2, deletions=0)
             for i in range(12)][::-1]
    e = only_extra(facts_for(files))
    assert e["detail"] == [f".github/workflows/w{i:02d}.yml" for i in range(12)]
    assert e["anchor"] == at(e["detail"][0], e["detail"][0], None, 1) and e["anchorless_reason"] is None


def test_mass_event_of_binary_files_has_no_anchor():
    files = [F(f"assets/img{i:02d}.png", None, "added", binary=True, size=10, additions=0, deletions=0) for i in range(12)]
    e = only_extra(facts_for(files))
    assert e["kind"] == "binary_or_large_added" and len(e["detail"]) == 12
    assert e["anchor"] is None and e["anchorless_reason"] == "no text patch"


def test_mass_event_of_deleted_tests_anchors_on_the_first_removed_definition():
    files = [F(f"tests/t{i:02d}_test.py", "@@ -1,2 +0,0 @@\n-import pytest\n-def test_a():\n", "removed", additions=0, deletions=2)
             for i in range(12)]
    e = only_extra(facts_for(files))
    assert e["kind"] == "tests_removed" and len(e["detail"]) == 12
    assert e["anchor"] == at("tests/t00_test.py", "tests/t00_test.py", 2, None)


def test_mass_event_of_generated_files_anchors_on_the_first_removed_line():
    e = Extra("generated_code_removed", "gen/", "gen/", "2 generated or vendored files deleted under gen/",
              ("gen/a.pb.go", "gen/b.pb.go"))
    files = [F("gen/a.pb.go", "@@ -1,2 +0,0 @@\n-package gen\n-var x = 1\n", "removed"),
             F("gen/b.pb.go", "@@ -5 +0,0 @@\n-package gen\n", "removed")]
    assert anchor(e, *files)[0] == at("gen/a.pb.go", "gen/a.pb.go", 1, None)


# ------------------------------------------------- thread stub, plain facts

KEEP = ("To keep it, reply with its exact name. To move it into its own MR, reply `split`. "
        "If this is not really an extra, reply `not an extra`.")


def test_thread_stub_text():
    e = Extra("new_dependency", "requirements.txt", "leftpad-py", "adds package leftpad-py; the issue does not name it")
    assert ci.thread_stub(e) == ("`leftpad-py` (new dependency): adds package leftpad-py; the issue does not name it. " + KEEP)
    ci_e = Extra("ci_or_config", ".gitlab-ci.yml", ".gitlab-ci.yml", "changes CI config; the issue does not mention it.")
    assert ci.thread_stub(ci_e) == ("`.gitlab-ci.yml` (CI change): changes CI config; the issue does not mention it. " + KEEP)
    mass = Extra("ci_or_config", "conf/", "conf/", "12 config files added under conf/", tuple("abcdefghijkl"))
    assert ci.thread_stub(mass).startswith("`conf/` (config change, 12 files): 12 config files added under conf/. To keep it")


def test_thread_stub_survives_odd_names():
    assert ci.thread_stub(Extra("tests_removed", "p", "a`b", "x")).startswith("``a`b`` (tests removed): x. ")
    assert ci.thread_stub(Extra("tests_removed", "p", "`a`", "x")).startswith("`` `a` `` (tests removed): x. ")
    odd = ci.thread_stub(Extra("tests_removed", "p", "a\nb", "deletes\r\nit"))
    assert "\n" not in odd and "\r" not in odd and odd.startswith("`a b` (tests removed): deletes it. ")


def test_thread_stub_has_no_banned_words(monkeypatch):
    spec = importlib.util.spec_from_file_location("hardcode_audit_for_stub", AUDIT)
    audit = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, audit)
    spec.loader.exec_module(audit)
    for kind in ("new_dependency", "ci_or_config", "tests_removed", "generated_code_removed",
                 "public_api_removed", "binary_or_large_added"):
        stub = ci.thread_stub(Extra(kind, "p", "n", "why it is here", ("a", "b")))
        assert f"({ci._label(Extra(kind, 'p', 'n', 'w', ('a', 'b')))})" in stub and not audit.BANNED_RE.search(stub)


def test_plain_facts_and_record_shape():
    e = Extra("ci_or_config", "conf/", "conf/", "12 config files added under conf/", tuple("abcdefghijkl"))
    rec = ci.describe_extra(e, {})
    assert rec["plain_facts"] == {"kind": "ci_or_config", "name": "conf/", "why": "12 config files added under conf/",
                                  "detail_count": 12, "path": "conf/"}
    assert list(rec) == ["kind", "path", "name", "why", "detail", "anchor", "anchorless_reason", "thread_stub", "plain_facts"]
    assert rec["detail"] == list("abcdefghijkl") and rec["thread_stub"] == ci.thread_stub(e)
    one = ci.describe_extra(dep("r.txt"), {"r.txt": F("r.txt", added("leftpad-py==1"))})
    assert one["plain_facts"]["detail_count"] == 0 and one["anchor"] == at("r.txt", "r.txt", None, 1)


# --------------------------------------------- real git, checked against the files

def show(repo, ref, path):
    return subprocess.run(["git", "-C", str(repo.path), "show", f"{ref}:{path}"], check=True,
                          capture_output=True, text=True).stdout.split("\n")


@pytest.fixture
def scenario(tmp_path):
    r = Repo(tmp_path / "repo")
    reqs = [f"pkg{i}==1.{i}\n" for i in range(45)]
    api = [f"X{i} = {i}\n" for i in range(19)] + ["def old_api(x):\n", "    return x\n", "def keep():\n", "    return 1\n"]
    tests = ["import pytest\n", "\n", "\n", "def test_a():\n", "    assert 1 == 1\n", "\n", "\n", "def test_b():\n",
             "    assert 2 == 2\n", "\n", "\n", "def test_c():\n", "    assert 3 == 3\n"]
    ci_yml = ["stages:\n", "  - test\n", "test:\n", "  script:\n", "    - pytest\n", "    - echo a\n", "    - echo b\n",
              "    - echo c\n", "    - echo d\n", "    - echo e\n"]
    r.base = r.commit({
        "requirements.txt": "".join(reqs), "src/api.py": "".join(api), "tests/test_parser.py": "".join(tests),
        ".gitlab-ci.yml": "".join(ci_yml), "Makefile": "all:\n\tcc a\n\tcc b\n\tcc c\n\tcc d\nclean:\n\trm x\n",
        "setup.cfg": "[metadata]\nname = x", "src/parser.py": "def parse(s):\n    return s.split(',')\n",
        "tests/test_old.py": "import pytest\n\n\ndef test_x():\n    assert 1\n\n\ndef test_y():\n    assert 2\n"})
    head = r.commit({
        "requirements.txt": "".join(reqs[:30] + ["leftpad-py==1.0.0\n"] + reqs[30:]),
        "src/api.py": "import sys\n" + "".join(api[:19] + api[21:]),
        "tests/test_parser.py": "".join(tests[:7] + tests[10:]),
        ".gitlab-ci.yml": "".join(ci_yml[:7] + ["    - echo new\n"] + ci_yml[7:]),
        "Makefile": None, "build/Makefile": "all:\n\tcc a\n\tcc b\n\tcc c\n\tcc d\n\tcc e\nclean:\n\trm x\n",
        "setup.cfg": "[metadata]\nname = x\nversion = 1\n", "tests/test_old.py": None,
        "src/parser.py": "def parse(s):\n    return [x for x in s.split(',') if x]\n",
        "logo.png": b"\x89PNG\x00\x01\x02"})
    r.head = head
    return r


ISSUE_TEXT = "Parser drops trailing comma\nThe parser in src/parser.py keeps an empty item after a trailing comma."

EXPECTED = {   # name: (anchor, the line it must be: ("new" = at the head, "old" = at the base), text)
    "leftpad-py": (at("requirements.txt", "requirements.txt", None, 31), "new", "leftpad-py==1.0.0"),
    ".gitlab-ci.yml": (at(".gitlab-ci.yml", ".gitlab-ci.yml", None, 8), "new", "    - echo new"),
    "tests/test_parser.py": (at("tests/test_parser.py", "tests/test_parser.py", 8, None), "old", "def test_b():"),
    "tests/test_old.py": (at("tests/test_old.py", "tests/test_old.py", 4, None), "old", "def test_x():"),
    "old_api": (at("src/api.py", "src/api.py", 20, None), "old", "def old_api(x):"),
    "build/Makefile": (at("Makefile", "build/Makefile", None, 6), "new", "\tcc e"),
    "setup.cfg": (at("setup.cfg", "setup.cfg", None, 2), "new", "name = x"),
    "logo.png": (None, None, None),
}


def test_anchors_on_a_real_diff(scenario):
    r = scenario
    files = ci.diff_files(str(r.path), r.base, r.head)
    report = facts_for(files, ISSUE_TEXT)
    by_name = {e["name"]: e for e in report["extras"]}
    assert set(by_name) == set(EXPECTED)
    for name, (want, side, text) in EXPECTED.items():
        e = by_name[name]
        assert e["anchor"] == want, name
        if want is None:
            assert e["anchorless_reason"] == "no text patch"
            continue
        assert e["anchorless_reason"] is None and (e["anchor"]["old_line"] is None) != (e["anchor"]["new_line"] is None)
        if side == "new":
            assert show(r, r.head, want["new_path"])[want["new_line"] - 1] == text, name      # the head's own line
        else:
            assert show(r, r.base, want["old_path"])[want["old_line"] - 1] == text, name      # the base's own line


def test_job_prints_the_facts_between_markers_after_the_card_lines(scenario, tmp_path, monkeypatch, capsys):
    r = scenario
    http = FakeHttp(routes(mr(), [issue(title="Parser drops trailing comma",
                                         description="The parser in src/parser.py keeps an empty item after a trailing comma.")]))
    code, out = job(r, r.head, http, tmp_path, monkeypatch)
    lines = capsys.readouterr().out.split("\n")
    assert code == 0 and lines[1] == out["card"]["final_line"] and lines[2] == out["card"]["todo_line"]
    assert lines[3] == "<<<ITEMATOR-JSON" and lines[5] == "ITEMATOR-JSON>>>" and lines[6] == ""
    assert json.loads(lines[4]) == out and out["truncated"] is False
    assert all("anchor" in e and e["thread_stub"] and e["plain_facts"] for e in out["extras"])


# ------------------------------------------------------------------ job log

def test_log_block_is_the_report_between_two_markers():
    report = facts_for([F("r.txt", added("leftpad-py==1"), "added", additions=1, deletions=0)])
    block = ci.log_block(report)
    first, body, last = block.split("\n")
    assert (first, last) == ("<<<ITEMATOR-JSON", "ITEMATOR-JSON>>>") and json.loads(body) == report


def test_a_name_cannot_spell_a_marker():
    nasty = "x<<<ITEMATOR-JSON ITEMATOR-JSON>>>y"
    report = facts_for([F("r.txt", added("a"), "added", additions=1, deletions=0)])
    report["extras"].append({"name": nasty, "detail": []})
    block = ci.log_block(report)
    assert block.count("<<<ITEMATOR-JSON") == 1 and block.count("ITEMATOR-JSON>>>") == 1 and "<" not in block.split("\n")[1]
    assert json.loads(block.split("\n")[1])["extras"][-1]["name"] == nasty


def test_big_report_gets_a_compact_copy_without_detail():
    files = [F(f".github/workflows/w{i:04d}.yml", added("on: push"), "added", additions=1, deletions=0) for i in range(4000)]
    report = facts_for(files)
    assert len(json.dumps(report)) > ci.LOG_LIMIT and len(only_extra(report)["detail"]) == 4000 and report["truncated"] is False
    block = ci.log_block(report)
    compact = json.loads(block.split("\n")[1])
    e = only_extra(compact)
    assert len(block.split("\n")[1]) <= ci.LOG_LIMIT and compact["truncated"] == ["extras[].detail"]
    assert "detail" not in e and e["plain_facts"]["detail_count"] == 4000 and e["thread_stub"] and e["anchor"]["new_line"] == 1
    assert compact["state"] == report["state"] and compact["card"] == report["card"]


def test_compact_copy_cuts_long_lists_then_extras_only_as_far_as_it_must():
    base = {"state": "extras", "card": {}, "injection": [{"where": "w", "line": i, "rule": "r"} for i in range(500)],
            "unplaced": [f"some/dir/file{i}.py" for i in range(5000)], "extras": []}
    c = json.loads(ci.log_block(base).split("\n")[1])
    assert c["truncated"] == ["extras[].detail", "unplaced[20:]"] and len(c["unplaced"]) == 20 and c["unplaced_total"] == 5000
    assert len(c["injection"]) == 500 and "injection_total" not in c
    big = {**base, "extras": [{"name": f"n{i}", "thread_stub": "s" * 200, "plain_facts": {"name": f"n{i}"}, "detail": []}
                              for i in range(1000)]}
    c = json.loads(ci.log_block(big, limit=60_000).split("\n")[1])
    kept = len(c["extras"])
    assert 0 < kept < 1000 and c["extras_total"] == 1000 and c["truncated"][-1] == f"extras[{kept}:]"
    assert "extras[].plain_facts" in c["truncated"] and len(ci._one_line(c)) <= 60_000
    assert all("plain_facts" not in e and "detail" not in e for e in c["extras"])
