"""Rules v5 (T33): one failing-then-passing fixture per change, from T19's audit of sample D (sections 7 and 9).

The older fixtures run on their own frozen rules (test_extras_v4.py on extras_v4, and so on). Here every v1 to v4
fixture runs again on v5, through test_extras_v4's own runners with v5 in place of v4. A fixture whose expected
output v5 changes on purpose is in _CHANGED with the reason, and its v5 output is asserted below.
"""
import hashlib
import pathlib

import pytest

import test_extras_v3 as T3
import test_extras_v4 as T4
from itemator import extras_v5 as V5           # T37: v5 is frozen in extras_v5.py; test_extras_v6 runs these on v6
from itemator import extras_v3, extras_v4
from itemator.extras_v5 import analyse, extras

V4_SHA256 = "41e497cc53a0df460e1af58b6b2e45954ddb14236f8360a338aefee192098dd2"   # extras.py of rules v4 (T15 report)
EDIT, f, kinds, binary, new = T3.EDIT, T3.f, T3.kinds, T3.binary, T4.new


# ---- the old fixtures, on v5
_CHANGED = {}   # fixture id -> why v5 gives another answer (none: the one rule-2a change was measured and reverted, see the
                # "known limit" test below)
_NOT_FIXTURES = {"test_v1_v2_fixtures_hold_on_v4", "test_v3_fixtures_hold_on_v4", "test_versions_and_frozen_v3"}
OLD12 = [(m, n) for m, n in T4.OLD12 if f"{m.__name__}.{n}" not in _CHANGED]
OLD3 = [n for n in T4.OLD3 if f"test_extras_v3.{n}" not in _CHANGED]
OLD4 = [n for n in sorted(vars(T4)) if n.startswith("test_") and n not in _NOT_FIXTURES
        and f"test_extras_v4.{n}" not in _CHANGED]


@pytest.mark.parametrize("mod,name", OLD12, ids=[f"{m.__name__}.{n}" for m, n in OLD12])
def test_v1_v2_fixtures_hold_on_v5(mod, name, monkeypatch):
    monkeypatch.setattr(T4, "V4", V5)
    T4.test_v1_v2_fixtures_hold_on_v4(mod, name, monkeypatch)


@pytest.mark.parametrize("name", OLD3)
def test_v3_fixtures_hold_on_v5(name, monkeypatch):
    monkeypatch.setattr(T4, "V4", V5)
    T4.test_v3_fixtures_hold_on_v4(name, monkeypatch)


@pytest.mark.parametrize("name", OLD4)
def test_v4_fixtures_hold_on_v5(name, monkeypatch):
    for attr, value in (("V4", V5), ("analyse", V5.analyse), ("extras", V5.extras)):
        monkeypatch.setattr(T4, attr, value)
    getattr(T4, name)()


def test_versions_and_frozen_v4():
    assert V5.RULES_VERSION == 5 and V5.KINDS == extras_v4.KINDS + ("whitespace_only",)
    assert hashlib.sha256(pathlib.Path(extras_v4.__file__).read_bytes()).hexdigest() == V4_SHA256
    issue, files = "The waitlist invite fails", [f("waitlist.py", EDIT), f("deploy/k8s.yaml", EDIT)]
    v4 = analyse(issue, files, version=4)
    assert type(v4) is extras_v4.Analysis and v4.unplaced == ["deploy/k8s.yaml"]
    assert type(analyse(issue, files, version=3)) is extras_v3.Analysis
    assert kinds(analyse(issue, files, version=2).extras) == [("file_outside_ask", "deploy/k8s.yaml")]
    assert kinds(analyse(issue, files, version=1).extras) == [("file_outside_ask", "deploy/k8s.yaml")]
    with pytest.raises(ValueError):
        analyse(issue, files, version=6)


# ---- change 1: a config or manifest file the issue names anchors the change (T19 9.1, celestia-core#1982 shape)
WF = ("e2e", "tests", "proto-lint", "lint", "markdown-linter")
WF_PATCH = "@@ -1,3 +1,3 @@\n on:\n   push:\n-    branches: [v0.38.x]\n+    branches: [v0.38.x-chain]\n"


def test_config_files_the_issue_names_anchor_the_change():
    issue = ("update CI workflows to run on v0.38.x-chain\nWe need to update the following workflows:\n"
             + "\n".join(f"https://github.com/acme/chain/blob/main/.github/workflows/{n}.yml" for n in WF))
    files = [f(f".github/workflows/{n}.yml", WF_PATCH) for n in WF]
    a = analyse(issue, files)
    assert a.anchored and a.named_paths == sorted(x["filename"] for x in files)
    assert a.extras == [] and a.unplaced == []                                  # named config files are never unplaced
    far = analyse(issue, files + [f("src/p2p/peer.go", EDIT)])
    assert far.anchored and far.unplaced == ["src/p2p/peer.go"]
    cargo = f("Cargo.toml", '@@ -1,2 +1,2 @@\n [package]\n-description = "a"\n+description = "b"\n')
    assert analyse("Fix the description in Cargo.toml", [cargo]).anchored              # a named manifest anchors too
    assert not analyse("Speed up the parser", [f(".github/workflows/ci.yml", WF_PATCH)]).anchored   # not named: no anchor


# ---- change 2 was reverted (kept as a documented limit; `_names_config` still serves rule 9c): the issue's generic word still mutes the config rule (T19 9.3, elsa-core#6677)
def test_known_limit_a_generic_word_still_mutes_the_config_rule():
    code = f("src/modules/PowerFx/Handler.cs", EDIT)
    wf = new(".github/workflows/copilot-setup-steps.yml.yml", "name: setup\non: workflow_dispatch")
    issue = "Add Power Fx as an expression type. Elsa Workflows supports JavaScript and Liquid in every workflow."
    assert extras(issue, [code, wf]) == []          # a workflow-engine issue mutes a CI file: the Elsa miss stays a miss
    for named in ("Edit .github/workflows/copilot-setup-steps.yml.yml for Power Fx", "Fix copilot-setup-steps.yml.yml",
                  "The copilot-setup-steps workflow must install Power Fx"):
        assert extras(named, [code, wf]) == [], named


# ---- change 3: whitespace-only edits (T19 7 and 9.5, ApplicationInsights-JS#2540 shape)
WS = {"newline": "@@ -1,2 +1,2 @@\n a\n-}\n\\ No newline at end of file\n+}\n",
      "indent": "@@ -1,2 +1,2 @@\n if x:\n-  return 1\n+    return 1\n",
      "blank": "@@ -1,3 +1,2 @@\n a\n-\n b\n"}


def test_whitespace_only_edits_are_one_extra():
    src = "shared/Core/src"
    names = [f"{src}/{d}/I{i:02d}.ts" for i, d in zip(range(17), ["Config", "Enums", "Interfaces"] * 6)]
    ws = [f(p, WS[("newline", "indent", "blank")[i % 3]]) for i, p in enumerate(names)]
    issue = "[BUG] SourceMaps do not include the original *.ts files, rewritten by the `updateDistEsm` script"
    a = analyse(issue, [f("tools/updateDistEsm/updateDistEsm.js", EDIT)] + ws)
    assert kinds(a.extras) == [("whitespace_only", src + "/")]
    e = a.extras[0]
    assert e.path == src + "/" and e.detail == tuple(sorted(names)) and e.why.startswith("17 files")
    assert all(p in e.why for p in sorted(names)[:3]) and sorted(names)[3] not in e.why
    assert not set(a.unplaced) & set(names)
    three = [f("a.ts", WS["newline"]), f("lib/b.ts", WS["indent"]), f("src/c.ts", WS["blank"])]
    b = analyse("Speed up the parser", [f("src/parser.py", EDIT)] + three)
    assert kinds(b.extras) == [("whitespace_only", "whitespace-only edits")] and b.extras[0].path == "./"
    two = analyse("Speed up the parser", [f("src/parser.py", EDIT)] + three[:2])
    assert two.extras == [] and two.unplaced == ["a.ts", "lib/b.ts"]                       # one or two: unplaced only
    assert extras("Run prettier over the code base", [f("src/parser.py", EDIT)] + three) == []   # the issue asks for it
    not_ws = [f("x/a.ts", "@@ -1,2 +1,2 @@\n-a\n-b\n+b\n+a\n"), f("x/b.ts", WS["newline"]), f("x/c.ts", WS["indent"])]
    assert extras("Speed up the parser", [f("src/parser.py", EDIT)] + not_ws) == []        # reordered lines are a change
    renamed = [f(f"x/{c}.ts", WS["indent"], status="renamed", previous_filename=f"y/{c}.ts") for c in "abc"]
    mode = [f(f"bin/{c}.sh", None, additions=0, deletions=0) for c in "abc"] + [f("bin/d.sh", "")]
    assert extras("Speed up the parser", [f("src/parser.py", EDIT)] + renamed + mode) == []
    reported = three[:2] + [f(".github/workflows/ci.yml", WS["indent"])]                  # a config change already
    assert kinds(extras("Speed up the parser", [f("src/parser.py", EDIT)] + reported)) == [
        ("ci_or_config", ".github/workflows/ci.yml")]


# ---- change 4: temp and scratch artefacts are stray files (T19 9.5)
def test_temp_and_scratch_artefacts_are_stray_files():
    issue = "[Azure App Configuration] Support the new feature flag schema fields"     # names the package directory
    code = f("sdk/appconfiguration/app-configuration/src/featureFlag.ts", EDIT)
    tmp_cfg = new("sdk/appconfiguration/app-configuration/tsconfig.test.vitest-temp.json", '{\n  "extends": "/home/runner/work/x/tsconfig.json"\n}')
    one = analyse(issue, [code, tmp_cfg])
    assert kinds(one.extras) == [("stray_file", tmp_cfg["filename"])] and "temp or scratch file" in one.extras[0].why
    tempdir = [new("tempvalidator/Program.cs", "Console.WriteLine();"), new("tempvalidator/tempvalidator.csproj", "<Project/>")]
    others = [new("src/cache/data.tmp", "x"), new("tools/scratch_notes.py", "x = 1")]
    a = analyse(issue, [code] + tempdir + others)
    assert a.stray == ["src/cache/data.tmp", "tempvalidator/", "tools/scratch_notes.py"]
    assert kinds(a.extras) == [("stray_file", "stray files")] and "temp or scratch directory (2 added files)" in a.extras[0].why
    words = [new("templates/mail.html", "x"), new("tmpl/a.html", "x"), new("temporal/flow.py", "x"),
             new("tests/fixtures/run-temp.json", "{}"), new("src/my-template.json", "{}")]
    assert analyse(issue, [code] + words).stray == []                                      # words, not markers; test data
    assert analyse(issue, [code, new("tmp/a.txt", "x"), f("tmp/b.txt", EDIT)]).stray == []   # not wholly added
    assert analyse("Add a tempvalidator console app", [code] + tempdir).stray == []        # the issue names it
    assert analyse("Cache the flags in src/cache/data.tmp", [code, others[0]]).stray == []


# ---- change 5: a virtual environment is one extra named by its root (T19 9.6, typespec#7664 shape)
def test_a_virtual_environment_is_one_extra_named_by_its_root():
    root = "packages/http-client-python/venv_build_wheel"
    site = [new(f"{root}/lib/python3.12/site-packages/pip/m{i:02d}.py", "x") for i in range(12)]
    marks = [new(f"{root}/pyvenv.cfg", "home = /usr/bin"), new(f"{root}/lib64", "lib"), new(f"{root}/bin/activate", "# venv")]
    a = analyse("upgrade dependencies for http-client-python", [f("packages/http-client-python/emitter.py", EDIT)] + site + marks)
    assert kinds(a.extras) == [("build_output_added", root + "/")]
    e = a.extras[0]
    assert e.path == root + "/" and e.why.startswith("15 generated files") and len(e.detail) == 15
    assert not {m["filename"] for m in marks} & set(a.named_paths + a.unplaced)
    env = [new(f"env/lib/python3.11/site-packages/m{i:02d}.py", "x") for i in range(9)] + [new("env/bin/activate", "# venv")]
    assert kinds(extras("Speed up the parser", [f("src/parser.py", EDIT)] + env)) == [("build_output_added", "env/")]


# ---- change 6: the lockfile reason says only what the cached files show (T19 9.4, ultracite#180 shape)
def test_lockfile_reason_says_only_what_the_cached_files_show():
    lock = f("package-lock.json", None, status="added", additions=7100, deletions=0)
    code, issue = f("scripts/package-manager.ts", EDIT), "does not work with turborepo"
    alone = extras(issue, [code, lock])[0].why
    assert "had none" not in alone and "the changed files show no matching manifest (package.json)" in alone
    beside = extras(issue, [code, f("pnpm-lock.yaml", EDIT), lock])[0].why
    assert "a second lockfile for another package manager" in beside and "in use" not in beside
    pj = f("package.json", '@@ -1,3 +1,3 @@\n {\n-  "description": "a",\n+  "description": "b",\n')
    kept = extras(issue, [code, pj, lock])[0].why
    assert "had none" not in kept and "package.json is in the change but not new" in kept


def test_names_config_reads_the_files_own_name_only():
    n = V5._names_config
    assert n("Fix .eslintrc.json", ".eslintrc.json")                  # base name
    assert n("Configure ESLint for the repo", ".eslintrc.json")        # tool name: leading dot, "rc" suffix dropped
    assert n("Use pre-commit hooks", ".pre-commit-config.yaml")        # "-config" suffix dropped
    assert n("The copilot-setup-steps workflow", ".github/workflows/copilot-setup-steps.yml.yml")   # stem as a whole word
    assert not n("Make the workflow faster", ".github/workflows/release.yml")                         # a kind word is not a name
    assert not n("Update a thing", "a.yml")                            # one-letter stem: the article "a" does not name it
    assert n("Fix x.yml please", "x.yml")                              # a one-letter stem is skipped; the base name still names it
    assert not n("configure the pipeline", ".gitlab-ci.yml")
