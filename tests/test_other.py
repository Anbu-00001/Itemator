"""Another checker's findings (itemator/other.py)."""
import json

from itemator import extras as X
from itemator import other as O

FILES = [{"filename": "src/parser.py", "status": "modified", "patch": "@@ -1 +1 @@\n-a\n+b"},
         {"filename": "install.sh", "status": "added", "patch": "@@ -0,0 +1 @@\n+curl x"},
         {"filename": "docs/a.md", "status": "added", "patch": "@@ -0,0 +1 @@\n+x"}]


def test_it_reads_overreach_the_scope_creep_detector_and_a_plain_list():
    assert O.parse({"findings": [{"file": "install.sh", "detail": "not  authorized"}, {"kind": "x"}]}) == [("install.sh", "not authorized", "Overreach")]
    assert O.parse({"in_scope": [{"path": "src/parser.py"}], "likely_creep": [{"path": "install.sh", "reasons": ["no overlap"]}],
                    "config_edits": [{"path": "ci.yml"}], "new_deps": [], "api_renames": []}) == [
        ("install.sh", "no overlap", "the Scope Creep Detector"), ("ci.yml", "config edits", "the Scope Creep Detector")]
    assert O.parse({"tool": "mine", "files": [{"path": "a"}, {"path": "a", "why": "again"}]}) == [("a", "", "mine")]
    assert O.parse([1, 2]) == [] and O.parse({"findings": "no"}) == []
    assert O.parse({"tool": "t", "files": [{"path": "a", "why": "w" * 400}]})[0][1] == "w" * 160


def test_read_tells_no_file_set_from_an_unreadable_one(tmp_path):
    assert O.read(None) is None and O.read("") is None
    assert O.read(str(tmp_path / "missing.json")) is False
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert O.read(str(bad)) is False
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"findings": []}))
    assert O.read(str(empty)) == []                                 # read, and it names nothing
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"findings": [{"file": "install.sh"}]}))
    assert O.read(str(good)) == [("install.sh", "", "Overreach")]


def test_it_adds_only_changed_files_the_rules_did_not_already_name():
    a = X.Analysis([X.Extra("stray_file", "docs/", "docs/", "a new directory", ("docs/a.md",))], unplaced=["install.sh"])
    named = [("install.sh", "why", "T"), ("docs/a.md", "", "T"), ("not/changed.py", "", "T")]
    out = O.apply(a, named, FILES)
    assert [(e.kind, e.path) for e in out.extras if e.kind == O.KIND] == [(O.KIND, "install.sh")]
    assert out.unplaced == []
    assert "T named it (why); Itemator's own rules did not" in [e.why for e in out.extras if e.kind == O.KIND][0]
    assert O.apply(a, [("src/parser.py", "", "T")], FILES).extras[-1].why.startswith("T named it (no reason given)")


def test_nothing_changes_without_findings_or_when_the_issue_declares_its_scope():
    a = X.Analysis([], unplaced=[])
    assert O.apply(a, None, FILES) is a and O.apply(a, [], FILES) is a
    assert O.apply(a, [("install.sh", "", "T")], FILES, scope=object()) is a


def test_covered_follows_paths_directories_and_mass_lists():
    a = X.Analysis([X.Extra("stray_file", "x/", "x/", "w"), X.Extra("version_bump", "m", "m", "w", ("y/z.txt",))])
    assert O.covered(a, "x/q.py") and O.covered(a, "y/z.txt") and O.covered(a, "m")
    assert not O.covered(a, "xq.py") and not O.covered(a, "m.bak")      # a file named like an extra is not inside it


def test_a_relative_path_is_read_from_the_checkout(tmp_path):
    (tmp_path / "overreach.json").write_text(json.dumps({"findings": [{"file": "install.sh"}]}))
    assert O.read("overreach.json", str(tmp_path)) == [("install.sh", "", "Overreach")]
    assert O.read(str(tmp_path / "overreach.json"), "/elsewhere") == [("install.sh", "", "Overreach")]


def test_a_reason_cannot_mention_link_or_quote_code():
    got = O.parse({"tool": "x@y", "files": [{"path": "a", "why": "ping @maintainer, see [here](https://e.x) and `rm -rf` <b>"}]})
    assert got == [("a", "ping maintainer, see here(https://e.x) and rm -rf b", "xy")]
