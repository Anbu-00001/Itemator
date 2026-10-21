"""itemator/packed.py: new npm dependencies in a package.json written on one line."""
import json

from itemator import ci
from itemator import extras as X
from itemator import packed as P
from itemator import scope as S

ISSUE = "Fix the parser."


def one(old: dict, new: dict, path="package.json", status="modified"):
    return {"filename": path, "status": status, "patch": f"@@ -1 +1 @@\n-{json.dumps(old)}\n+{json.dumps(new)}\n"}


BASE = {"name": "a", "dependencies": {"left-pad": "1.0.0"}}
MORE = {"name": "a", "dependencies": {"left-pad": "1.0.0", "expresss": "4.0.0"}, "devDependencies": {"@types/node": "20"}}


def names(*files, issue=ISSUE):
    return [e.name for e in P.find(issue, list(files))]


def test_a_minified_manifest_shows_its_new_dependencies_and_rule_1_alone_does_not():
    f = one(BASE, MORE)
    assert [e.name for e in X.extras(ISSUE, [f])] == []
    assert names(f) == ["expresss", "@types/node"]
    assert all(e.why.endswith(P.ONE_LINE) for e in P.find(ISSUE, [f]))


def test_a_dependency_object_on_one_line_inside_a_normal_file():
    patch = '@@ -1,3 +1,3 @@\n {\n-  "dependencies": {"x": "1"},\n+  "dependencies": {"x": "1", "y": "2"},\n   "name": "a"\n'
    assert names({"filename": "web/package.json", "status": "modified", "patch": patch}) == ["y"]


def test_bumps_moves_named_packages_scripts_and_other_files_are_not():
    assert names(one(BASE, {"name": "a", "dependencies": {"left-pad": "2.0.0"}})) == []                  # a bump
    assert names(one(BASE, {"name": "a", "devDependencies": {"left-pad": "1.0.0"}})) == []               # a move
    assert names(one(BASE, MORE), issue="Use expresss and @types/node") == []
    assert names(one(BASE, {"name": "a", "dependencies": {"left-pad": "1.0.0"}, "scripts": {"t": "jest"}})) == []
    assert names(one(BASE, MORE, path="package.json.bak"), one(BASE, MORE, status="removed")) == []
    assert names({"filename": "package.json", "status": "modified"}) == []


def test_a_short_name_in_the_issue_counts():
    new = {"name": "a", "dependencies": {"left-pad": "1.0.0", "@scope/widget": "1"}}
    assert names(one(BASE, new), issue="Add the widget") == []


def test_a_multi_line_manifest_is_left_to_rule_1_and_never_listed_twice():
    patch = '@@ -1,4 +1,5 @@\n {\n   "dependencies": {\n     "x": "1",\n+    "evil": "2",\n   }\n'
    f = {"filename": "package.json", "status": "modified", "patch": patch}
    assert names(f) == []
    whole = {"filename": "package.json", "status": "added", "patch": '@@ -0,0 +1 @@\n+{"name": "a", "dependencies": {"evil": "2"}}\n'}
    a = P.apply(X.analyse(ISSUE, [whole]), ISSUE, [whole])
    assert [e.name for e in a.extras if e.kind == "new_dependency"].count("evil") == 1


def test_apply_keeps_the_order_and_returns_the_same_analysis_when_nothing_is_added():
    f = one(BASE, MORE)
    a = P.apply(X.analyse(ISSUE, [f]), ISSUE, [f])
    assert [e.name for e in a.extras] == ["@types/node", "expresss"]
    plain = X.analyse(ISSUE, [one(BASE, BASE)])
    assert P.apply(plain, ISSUE, [one(BASE, BASE)]) is plain


def test_no_split_or_remove_on_a_one_line_manifest():
    f = one(BASE, MORE)
    e = P.find(ISSUE, [f])[0]
    assert ci._split_remove(e, (), {"package.json": f}) == ()
    normal = X.Extra("new_dependency", "package.json", "evil", "adds package evil; the issue does not name it")
    assert ci._split_remove(normal, (), {"package.json": f}) == ("split", "remove")


def test_a_scope_dependency_list_sees_them_too():
    f = one(BASE, MORE)
    text = ISSUE + "\n```itemator-scope\ndependencies: expresss\n```\n"
    a = S.apply(S.read(text), P.apply(X.analyse(text, [f]), text, [f]), [f])
    assert [e.name for e in a.extras] == ["@types/node"]


def test_peer_and_optional_objects_the_old_side_and_rule_1s_own_are_read():
    new = {"name": "a", "dependencies": {"left-pad": "1.0.0"}, "peerDependencies": {"react": "18"}, "optionalDependencies": {"fsevents": "2"}}
    assert names(one(BASE, new)) == ["react", "fsevents"]
    ctx = {"filename": "package.json", "status": "modified",
           "patch": '@@ -1,2 +1,2 @@\n   "x": "1",\n-  "dependencies": {},\n+  "dependencies": {"x": "1"},\n'}
    assert names(ctx) == []                                      # a pair the old side shows as context is not new
    assert P.find(ISSUE, [one(BASE, MORE)], {("package.json", "expresss")})[0].name == "@types/node"
    twice = {"filename": "package.json", "status": "modified",
             "patch": '@@ -1 +1,2 @@\n+"dependencies": {"y": "1"},\n+"devDependencies": {"y": "1"}\n'}
    assert names(twice) == ["y"]


def test_only_a_dependency_can_be_a_one_line_one():
    assert not P.one_line(X.Extra("stray_file", "package.json", "x", "adds x; " + P.ONE_LINE))
