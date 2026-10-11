"""Rules v3 (T9): one failing-then-passing fixture per change, from T8's audit of sample B.

The v1-era and v2 fixtures (test_extras.py, test_extras_v2.py) run on the frozen v2
rules; here they run again on v3 through an adapter that moves v3's `unplaced` files
back into v2's `file_outside_ask`. So every old fixture checks that v3 changes only
what it says it changes.
"""
import hashlib
import pathlib

import pytest

import test_extras as T1
import test_extras_v2 as T2
from itemator import extras_v3 as V3   # frozen v3 (T15); test_extras_v4.py re-runs these on v4
from itemator import extras_v2
from itemator.extras_v3 import analyse, extras

V2_SHA256 = "8b6ba12da5cfb716c7369f9d0cdb5a8a71d7d509e8ff3d9f2d13585a288da4f1"   # extras.py at 12b3d1b
EDIT = "@@ -1 +1 @@\n-a\n+b\n"


def f(filename, patch=None, status="modified", **kw):
    return {"filename": filename, "status": status, "patch": patch, **kw}


def kinds(result):
    return sorted({(e.kind, e.name) for e in result})


def gone(path):
    return f(path, "@@ -1,2 +0,0 @@\n-x = 1\n-y = 2\n", status="removed")


def binary(path, **kw):
    return {**f(path, None, status="added", additions=0, deletions=0), **kw}


# ---- the old fixtures, on v3
_ORDER = ("new_dependency", "ci_or_config", "tests_removed", "public_api_removed", "file_outside_ask")


class _AsV2:
    """v3 seen through v2's output shape: anchored `unplaced` files become file_outside_ask extras."""
    RULES_VERSION = 3

    def __getattr__(self, name):
        return getattr(V3, name)

    def analyse(self, issue_text, files, *, repo=None, version=None):
        a = V3.analyse(issue_text, files, repo=repo)
        if not a.anchored:
            return a
        moved = [V3.Extra("file_outside_ask", p, p, "no file the issue names is near this one") for p in a.unplaced]
        ex = sorted(a.extras + moved, key=lambda e: (_ORDER.index(e.kind), e.path, e.name))
        return V3.Analysis(extras=ex, named_paths=a.named_paths, anchored=True)

    def extras(self, issue_text, files, *, repo=None, version=None):
        return self.analyse(issue_text, files, repo=repo).extras


_SKIP = {"test_v1_is_reachable_and_differs"}   # asserts RULES_VERSION == 2; test_versions_and_frozen_v2 below
OLD = [(m, n) for m in (T1, T2) for n in sorted(vars(m)) if n.startswith("test_") and n not in _SKIP]


@pytest.mark.parametrize("mod,name", OLD, ids=[f"{m.__name__}.{n}" for m, n in OLD])
def test_old_fixtures_hold_on_v3(mod, name, monkeypatch):
    adapter = _AsV2()
    monkeypatch.setattr(mod, "X", adapter, raising=False)
    monkeypatch.setattr(mod, "analyse", adapter.analyse)
    monkeypatch.setattr(mod, "extras", adapter.extras)
    getattr(mod, name)()


def test_versions_and_frozen_v2():
    assert V3.RULES_VERSION == 3 and "file_outside_ask" not in V3.KINDS
    src = pathlib.Path(extras_v2.__file__).read_bytes()
    assert hashlib.sha256(src).hexdigest() == V2_SHA256
    issue, files = "The waitlist invite fails", [f("waitlist.py", EDIT), f("deploy/k8s.yaml", EDIT)]
    v2 = analyse(issue, files, version=2)
    assert type(v2) is extras_v2.Analysis and kinds(v2.extras) == [("file_outside_ask", "deploy/k8s.yaml")]
    assert kinds(analyse(issue, files, version=1).extras) == [("file_outside_ask", "deploy/k8s.yaml")]
    with pytest.raises(ValueError):
        analyse(issue, files, version=4)


# ---- change 1: rule 5 is the informational `unplaced` state, never an extra
def test_rule5_files_are_unplaced_not_extras():
    issue = "The waitlist invite fails"
    files = [f("waitlist.py", EDIT), f("mailer.py", EDIT), f("deploy/k8s.yaml", EDIT), f("tests/test_waitlist.py", EDIT)]
    a = analyse(issue, files)
    assert a.extras == [] and a.anchored is True
    assert a.unplaced == ["deploy/k8s.yaml"]
    assert a.named_paths == ["tests/test_waitlist.py", "waitlist.py"]
    b = analyse("Fix the crash on startup", [f("src/x.py", EDIT), f("deploy/secrets.yaml", EDIT)])
    assert b.anchored is False and b.unplaced == ["deploy/secrets.yaml", "src/x.py"] and b.extras == []


# ---- change 2: mass events are one extra, named by the directory, with the files as detail
def test_mass_deletion_is_one_extra_per_directory():
    t = [f(f"tests/legacy/test_m{i:02d}.py", "@@ -1,2 +0,0 @@\n-def test_x():\n-    assert 1\n", status="removed")
         for i in range(12)]
    found = extras("Speed up the parser", [f("src/parser.py", EDIT)] + t)
    assert kinds(found) == [("tests_removed", "tests/legacy/")]
    assert found[0].path == "tests/legacy/" and "12 test files deleted" in found[0].why
    assert found[0].detail == tuple(sorted(x["filename"] for x in t))
    nine = extras("Speed up the parser", [f("src/parser.py", EDIT)] + t[:9])
    assert len(nine) == 9 and all(e.detail == () for e in nine)


def test_mass_events_split_by_top_two_directories():
    a = [binary(f"pkg/one/bin/tool{i}") for i in range(10)]
    b = [binary(f"pkg/two/bin/tool{i}") for i in range(10)]
    c = [binary(f"pkg/three/tool{i}") for i in range(3)]
    found = extras("Speed up the parser", [f("src/parser.py", EDIT)] + a + b + c)
    assert kinds(found) == [("binary_or_large_added", "pkg/one/bin/"), ("binary_or_large_added", "pkg/three/tool0"),
                            ("binary_or_large_added", "pkg/three/tool1"), ("binary_or_large_added", "pkg/three/tool2"),
                            ("binary_or_large_added", "pkg/two/bin/")]
    assert [len(e.detail) for e in found if e.name.endswith("/")] == [10, 10]


def test_mass_config_files_added():
    wf = [f(f".github/workflows/w{i}.yml", "@@ -0,0 +1 @@\n+on: push\n", status="added") for i in range(10)]
    found = extras("Speed up the parser", [f("src/parser.py", EDIT)] + wf)
    assert kinds(found) == [("ci_or_config", ".github/workflows/")] and "10 config files added" in found[0].why
    mod = [f(f".github/workflows/m{i}.yml", EDIT) for i in range(10)]
    assert len(extras("Speed up the parser", [f("src/parser.py", EDIT)] + mod)) == 10   # modified: not a mass event


# ---- change 3: binary or large files added
def test_binary_added_is_extra():
    found = extras("Rename the project", [f("README.md", EDIT), binary("apps/evm/single/evm-single"), binary("run-evm-nodes"),
                                          binary("test/TestResults/a/run.coverage")])
    assert kinds(found) == [("binary_or_large_added", "apps/evm/single/evm-single"),
                            ("binary_or_large_added", "run-evm-nodes"),
                            ("binary_or_large_added", "test/TestResults/a/run.coverage")]
    assert all("size is not in the file list" in e.why for e in found)
    a = analyse("Rename the project", [f("README.md", EDIT), f("src/x.py", EDIT), binary("run-evm-nodes")])
    assert a.unplaced == ["src/x.py"] and kinds(a.extras) == [("binary_or_large_added", "run-evm-nodes")]


def test_binary_rule_spares_text_named_and_modified_files():
    files = [f("README.md", EDIT),
             binary("tests/server/middleware/__init__.py"),          # empty text file
             binary(".gitkeep"),
             f("models_generated.go", None, status="added", additions=5000, deletions=0),   # text, patch omitted
             f("scripts/run-all", None, status="added", additions=300, deletions=0),        # no extension, has lines
             f("logo.png", None, status="modified", additions=0, deletions=0),             # not added
             binary("packages/app/public/phoenix/favicon.png")]                            # named by the issue
    assert extras("Add a new build config for phoenix", files) == []


def test_binary_under_a_named_package_is_still_extra():
    cov = binary("packages/http-client-csharp/generator/test/TestResults/x/run.coverage")
    found = extras("Fix the http-client-csharp generator", [f("packages/http-client-csharp/generator/src/a.cs", EDIT), cov])
    assert kinds(found) == [("binary_or_large_added", cov["filename"])]
    assert extras("Fix the http-client-csharp generator", [binary("docs/x/run.coverage")]) != []
    assert extras("Add docs/x/run.coverage", [binary("docs/x/run.coverage")]) == []
    assert extras("Add the evm-single binary", [binary("bin/out/evm-single")]) == []     # named by its stem


def test_large_file_added_when_size_known():
    files = [f("README.md", EDIT), f("data/dump.json", "@@ -0,0 +1 @@\n+{}\n", status="added", size=2_000_000),
             f("data/small.json", "@@ -0,0 +1 @@\n+{}\n", status="added", size=900_000),
             binary("img/x.png", size=10), binary("bin/y", binary=True, additions=5)]   # lines counted, but GitHub marks it binary
    found = extras("Speed up the parser", files)
    assert kinds(found) == [("binary_or_large_added", "bin/y"), ("binary_or_large_added", "data/dump.json"),
                            ("binary_or_large_added", "img/x.png")]
    assert "2,000,000 bytes" in [e.why for e in found if e.path == "data/dump.json"][0]


# ---- change 4: new_dependency, general causes from sample B
def test_dependency_already_in_the_manifest_is_not_new():
    promoted = f("go.mod", "@@ -32,3 +32,4 @@ require (\n github.com/a/b v1.0.0\n+\tgithub.com/prometheus/client_model v0.6.1\n"
                           " github.com/c/d v1.0.0\n@@ -112,3 +113,2 @@ require (\n github.com/e/f v1 // indirect\n"
                           "-\tgithub.com/prometheus/client_model v0.6.1 // indirect\n github.com/g/h v1 // indirect\n")
    ctx = f("go.mod", "@@ -1,3 +1,4 @@\n require (\n+\tgithub.com/x/y v1.2.0\n \tgithub.com/x/y v1.2.0 // indirect\n )\n")
    assert X_new("Migrations ignore the log level", [promoted]) == []
    assert X_new("Migrations ignore the log level", [ctx]) == []
    fresh = f("go.mod", "@@ -1,2 +1,3 @@\n require (\n+\tgithub.com/x/z v1.2.0\n )\n")
    assert kinds(X_new("Migrations ignore the log level", [fresh])) == [("new_dependency", "github.com/x/z")]


def test_dependency_the_issue_title_names_in_capitals_is_not_new():
    py = f("pyproject.toml", '@@ -10,4 +10,5 @@ dependencies = [\n     "requests>=2.25",\n-    "ping3>=4.0.0"\n'
                             '+    "ping3>=4.0.0",\n+    "slixmpp>=1.8.0"\n ]\n')
    assert X_new("Feature request: XMPP\nCould XMPP be added to the providers?", [py]) == []
    assert kinds(X_new("Fix the crash in the sender\nThe XMPP provider crashes", [py])) == [("new_dependency", "slixmpp")]
    assert kinds(X_new("Add a chat provider\nPlease.", [py])) == [("new_dependency", "slixmpp")]
    jwt = f("requirements.txt", "@@ -1 +1,2 @@\n requests\n+pyjwt==2.8\n")
    assert kinds(X_new("Support JWT auth\nPlease.", [jwt])) == [("new_dependency", "pyjwt")]   # 3 capitals: too short
    cargo = f("Cargo.toml", '@@ -20,2 +20,4 @@\n lazy_static = "1.4.0"\n+ahash = "0.8"\n+fnv = { version = "1.0", optional = true }\n')
    assert kinds(X_new("Alternative hashing algorithms\nSee e.g. AHash, fxhash.", [cargo])) == [("new_dependency", "fnv")]


def X_new(issue, files):
    return V3._new_dependencies(issue, files)


# ---- change 5: generated or vendored code is not tests
def test_generated_code_under_test_dir_is_not_tests():
    gen = [gone(f"packages/ts-test/test/loadTest/generated/src/api/m{i:02d}.ts") for i in range(8)] + \
          [gone(f"packages/ts-test/test/hier/generated/src/h{i}.ts") for i in range(4)] + \
          [gone("packages/ts-test/test/hier/generated/README.md"),
           f("packages/ts-test/test/hier/generated/src/api.ts", "@@ -1 +0,0 @@\n-export function foo() {}\n", status="removed")]
    found = extras("Upgrade the dev dependencies", [f("packages/ts-test/package.json", EDIT)] + gen)
    assert kinds(found) == [("generated_code_removed", "packages/ts-test/test/")]
    assert len(found[0].detail) == 14 and "14 generated or vendored files deleted" in found[0].why
    few = extras("Upgrade the dev dependencies", [f("packages/ts-test/package.json", EDIT)] + gen[:9])
    assert few == []                                   # fewer than 10: regeneration churn, not reported
    named = "Drop packages/ts-test/test/loadTest/generated/src/api/ entirely"     # 8 named: 6 left, under MASS
    assert extras(named, [f("packages/ts-test/package.json", EDIT)] + gen) == []
    ancestor = "Regenerate everything under packages/ts-test/test/"               # names a whole area only
    assert kinds(extras(ancestor, [f("packages/ts-test/package.json", EDIT)] + gen)) == [
        ("generated_code_removed", "packages/ts-test/test/")]


def test_generated_markers():
    for p in ("a/generated/x.ts", "a/__generated__/x.ts", "vendor/x/y.go", "third_party/z.c", "node_modules/a/b.js",
              "lib/python3.12/site-packages/pip/x.py", "api/x_pb2.py", "api/x.pb.go", "src/Foo.generated.cs", "m.g.dart"):
        assert V3.is_generated(p), p
    for p in ("src/generator.py", "tests/test_gen.py", "general/x.py"):
        assert not V3.is_generated(p), p
    assert not V3.is_test_file("pkg/test/case/generated/src/index.ts")
    assert V3.is_test_file("pkg/test/case/src/index.ts")
