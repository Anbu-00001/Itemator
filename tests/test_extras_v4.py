"""Rules v4 (T15): one failing-then-passing fixture per change, from T10's audit of sample C and T13's live test.

The older fixtures run on their own frozen rules (test_extras.py and test_extras_v2.py on extras_v2,
test_extras_v3.py on extras_v3). Here they all run again on v4: the v1-era and v2 fixtures through
test_extras_v3's adapter (v4's `unplaced` back into v2's `file_outside_ask`), the v3 fixtures with v4 in
place of v3. A fixture whose expected output v4 changes on purpose is in _CHANGED with the reason, and
its v4 output is asserted below.
"""
import hashlib
import pathlib

import pytest

import test_extras as T1
import test_extras_v2 as T2
import test_extras_v3 as T3
from itemator import extras as V4
from itemator import extras_v3
from itemator.extras import analyse, extras

V3_SHA256 = "52915bc2314215ffc1b20c742ae59986efd9b51ab5673e8255fafc6aeef6b594"   # extras.py of rules v3 (T9 report)
EDIT, f, kinds, binary = T3.EDIT, T3.f, T3.kinds, T3.binary


def new(path, body):
    lines = body.split("\n")
    return f(path, f"@@ -0,0 +1,{len(lines)} @@\n" + "".join(f"+{x}\n" for x in lines), status="added",
             additions=len(lines), deletions=0)


# ---- the old fixtures, on v4
_CHANGED = {   # v3 fixture -> why v4 gives another answer (asserted in test_v3_fixture_v4_changes_on_purpose)
    "test_binary_rule_spares_text_named_and_modified_files":
        "change 3: scripts/run-all has lines but no patch, so GitHub found it too large to show",
}
_NOT_FIXTURES = {"test_old_fixtures_hold_on_v3", "test_versions_and_frozen_v2"}
OLD12 = [(m, n) for m in (T1, T2) for n in sorted(vars(m)) if n.startswith("test_") and n not in T3._SKIP]
OLD3 = [n for n in sorted(vars(T3)) if n.startswith("test_") and n not in _NOT_FIXTURES | set(_CHANGED)]


@pytest.mark.parametrize("mod,name", OLD12, ids=[f"{m.__name__}.{n}" for m, n in OLD12])
def test_v1_v2_fixtures_hold_on_v4(mod, name, monkeypatch):
    monkeypatch.setattr(T3, "V3", V4)            # the adapter reads the module named V3
    adapter = T3._AsV2()
    monkeypatch.setattr(mod, "X", adapter, raising=False)
    monkeypatch.setattr(mod, "analyse", adapter.analyse)
    monkeypatch.setattr(mod, "extras", adapter.extras)
    getattr(mod, name)()


@pytest.mark.parametrize("name", OLD3)
def test_v3_fixtures_hold_on_v4(name, monkeypatch):
    for attr, value in (("V3", V4), ("analyse", V4.analyse), ("extras", V4.extras)):
        monkeypatch.setattr(T3, attr, value)
    getattr(T3, name)()


def test_v3_fixture_v4_changes_on_purpose():
    files = [f("README.md", EDIT), binary("tests/server/middleware/__init__.py"), binary(".gitkeep"),
             f("models_generated.go", None, status="added", additions=5000, deletions=0),
             f("scripts/run-all", None, status="added", additions=300, deletions=0),
             f("logo.png", None, status="modified", additions=0, deletions=0),
             binary("packages/app/public/phoenix/favicon.png")]
    assert kinds(extras("Add a new build config for phoenix", files)) == [("binary_or_large_added", "scripts/run-all")]


def test_versions_and_frozen_v3():
    assert V4.RULES_VERSION == 4 and {"version_bump", "build_output_added", "stray_file"} <= set(V4.KINDS)
    assert hashlib.sha256(pathlib.Path(extras_v3.__file__).read_bytes()).hexdigest() == V3_SHA256
    issue, files = "The waitlist invite fails", [f("waitlist.py", EDIT), f("deploy/k8s.yaml", EDIT)]
    v3 = analyse(issue, files, version=3)
    assert type(v3) is extras_v3.Analysis and v3.unplaced == ["deploy/k8s.yaml"]
    assert kinds(analyse(issue, files, version=2).extras) == [("file_outside_ask", "deploy/k8s.yaml")]
    assert kinds(analyse(issue, files, version=1).extras) == [("file_outside_ask", "deploy/k8s.yaml")]
    with pytest.raises(ValueError):
        analyse(issue, files, version=5)


# ---- change 1: a newly added manifest is one package, not one extra per dependency
def test_new_manifest_is_one_package_not_one_extra_per_dependency():
    cargo = new("crates/sim-gen/Cargo.toml", '[package]\nname = "sim-gen"\nversion = "0.1.0"\n\n[dependencies]\n'
                'anyhow = "1"\nclap = { version = "4" }\nserde = "1"\n\n[dev-dependencies]\ntempfile = "3"')
    found = extras("Support other languages", [f("src/x.rs", EDIT), cargo])
    assert kinds(found) == [("new_dependency", "sim-gen")]
    assert "4 dependencies" in found[0].why and found[0].path == "crates/sim-gen/Cargo.toml"
    npm = new("packages/ui/package.json", '{\n  "name": "@acme/ui",\n  "dependencies": {\n    "react": "^18.0.0"\n  }\n}')
    assert kinds(extras("Support other languages", [f("src/x.rs", EDIT), npm])) == [("new_dependency", "@acme/ui")]
    py = new("tools/gen/pyproject.toml", '[project]\nname = "acme-gen"\ndependencies = [\n  "requests>=2",\n]')
    assert kinds(extras("Support other languages", [f("src/x.rs", EDIT), py])) == [("new_dependency", "acme-gen")]
    nameless = new("app/package.json", '{\n  "dependencies": {\n    "left-pad": "^1.3.0"\n  }\n}')
    assert kinds(extras("Support other languages", [f("src/x.rs", EDIT), nameless])) == [("new_dependency", "app")]
    tool_only = new("pyproject.toml", "[tool.black]\nline-length = 120")
    assert [e for e in extras("Support other languages", [f("src/x.rs", EDIT), tool_only]) if e.kind == "new_dependency"] == []
    assert extras("Add the sim-gen crate", [f("src/x.rs", EDIT), cargo]) == []          # the issue names the package
    mixed = f("Cargo.toml", '@@ -1,2 +1,4 @@\n [dependencies]\n+anyhow = "1"\n+clap = "4"\n serde = "1"\n')
    assert kinds(extras("Support other languages", [f("src/x.rs", EDIT), mixed])) == [
        ("new_dependency", "anyhow"), ("new_dependency", "clap")]                       # existing manifest: unchanged


# ---- change 2: merges, moves and story helpers are not public API removals
def test_merged_or_moved_names_and_story_helpers_are_not_api_removal():
    issue = "Delete unused code"
    story = f("src/utils/form-story-helpers.tsx", "@@ -1,2 +0,0 @@\n-export const formArgs = {}\n-export function getArgs() {}\n",
              status="removed")
    mocks = f("src/__mocks__/api.ts", "@@ -1 +0,0 @@\n-export function fetchUser() {}\n", status="removed")
    fixtures = f("support/fixtures/data.py", "@@ -1 +0,0 @@\n-def make_user():\n", status="removed")
    stories = f("src/Button.stories.tsx", "@@ -1 +1 @@\n-export const Primary = {}\n+const x = 1\n")
    assert extras(issue, [f("src/a.ts", EDIT), story, mocks, fixtures, stories]) == []
    gone_def = f("src/a.py", "@@ -1,2 +0,0 @@\n-def parse(x):\n-    return x\n", status="removed")
    head = f("src/b.py", "@@ -1,3 +1,3 @@\n def parse(x):\n     return x\n-y = 1\n+y = 2\n")
    assert extras(issue, [gone_def, head]) == []                     # still defined at the head (a context line)
    old = f("src/old/loader.py", "@@ -1,2 +0,0 @@\n-def load():\n-    pass\n", status="removed")
    for twin in (f("src/new/loader.py", None, status="added", additions=40, deletions=0),
                 f("src/new/loader.py", None, status="renamed", previous_filename="src/tmp/x.py")):
        assert [e for e in extras(issue, [old, twin]) if e.kind == "public_api_removed"] == []   # moved: same stem
    real = f("src/utils/helpers.ts", "@@ -1 +0,0 @@\n-export function slugify() {}\n", status="removed")
    assert kinds(extras(issue, [f("src/a.ts", EDIT), real])) == [("public_api_removed", "slugify")]
    history = f("src/history.py", "@@ -1 +0,0 @@\n-def rewind():\n", status="removed")       # not a story
    assert kinds(extras(issue, [f("src/a.ts", EDIT), history])) == [("public_api_removed", "rewind")]


# ---- change 3a: a lockfile of a package manager the repo does not use
def test_lockfile_of_a_package_manager_the_repo_does_not_use():
    lock = f("package-lock.json", None, status="added", additions=6443, deletions=0)
    issue, code = "Scroll to the timeline item on sidebar click", f("packages/gantt/index.tsx", EDIT)
    found = extras(issue, [code, lock])
    assert kinds(found) == [("stray_file", "package-lock.json")] and "npm" in found[0].why
    beside = extras(issue, [code, f("pnpm-lock.yaml", EDIT), lock])
    assert kinds(beside) == [("stray_file", "package-lock.json")] and "beside pnpm-lock.yaml" in beside[0].why
    fresh = [new("packages/new/package.json", '{\n  "name": "new"\n}'),
             f("packages/new/package-lock.json", None, status="added", additions=50, deletions=0)]
    assert [e for e in extras(issue, [code] + fresh) if e.kind in ("stray_file", "binary_or_large_added")] == []
    assert extras("Switch the repo to npm", [code, lock]) == []                         # the issue names the manager
    assert extras(issue, [code, f("package-lock.json", EDIT)]) == []                     # modified, not new
    assert extras(issue, [f("src/lib.rs", EDIT), f("Cargo.lock", None, status="added", additions=900, deletions=0)]) == []


# ---- change 3b: a version bump the issue did not ask for
def test_version_bump_the_issue_did_not_ask_for():
    py = f("pyproject.toml", '@@ -1,4 +1,4 @@\n [project]\n name = "carbon"\n-version = "3.0.4"\n+version = "3.0.5"\n description = "x"\n')
    ver = f("carbon/_version.py", '@@ -1 +1 @@\n-__version__ = "3.0.4"\n+__version__ = "3.0.5"\n')
    issue = "Check version coherence between the files bumpver changes, to avoid a manual bump"
    found = extras(issue, [f("scripts/versions.py", EDIT), py, ver])
    assert kinds(found) == [("version_bump", "3.0.5")]
    assert found[0].detail == ("carbon/_version.py", "pyproject.toml") and "3.0.4" in found[0].why
    npm = f("package.json", '@@ -1,4 +1,4 @@\n {\n   "name": "s3-zip",\n-  "version": "3.3.1a0",\n+  "version": "3.3.1-a0",\n   "main": "i.js"\n')
    assert kinds(extras("Make the build faster", [f("i.js", EDIT), npm])) == [("version_bump", "3.3.1-a0")]
    assert extras('npm warn publish "version" was cleaned and set to "3.3.1-a0"', [f("i.js", EDIT), npm]) == []
    cargo = f("Cargo.toml", '@@ -1,3 +1,3 @@\n [package]\n name = "x"\n-version = "0.1.0"\n+version = "0.2.0"\n')
    assert kinds(extras("Make the build faster", [f("src/lib.rs", EDIT), cargo])) == [("version_bump", "0.2.0")]
    dep_only = f("Cargo.toml", '@@ -1,3 +1,3 @@\n [dependencies.serde]\n-version = "1.0.1"\n+version = "1.0.2"\n')
    npm_dep = f("package.json", '@@ -1,3 +1,3 @@\n   "dependencies": {\n-    "react": "18.0.0"\n+    "react": "18.2.0"\n')
    assert extras("Make the build faster", [f("src/lib.rs", EDIT), dep_only, npm_dep]) == []


# ---- change 3c: a large added file GitHub gives no patch for, though it counts its lines
def test_large_patchless_added_file_with_lines():
    big = f("packages/core/genaisrc/genaiscript.d.ts", None, status="added", additions=6226, deletions=0)
    found = extras("Let generateImage take image input", [f("packages/core/src/image.ts", EDIT), big])
    assert kinds(found) == [("binary_or_large_added", big["filename"])]
    assert "+6226 -0" in found[0].why and "size is not in the file list" in found[0].why
    gen = f("azurecaf/models_generated.go", None, status="added", additions=5000, deletions=0)
    assert extras("Merge the two JSON files", [f("azurecaf/gen.go", EDIT), gen, binary("tests/server/__init__.py")]) == []
    marked = binary("bin/y", binary=True, additions=5)        # GitHub's binary mark still comes first (v3 rule 6)
    assert [e.why for e in extras("Speed up the parser", [f("src/parser.py", EDIT), marked])] == [
        "adds a file GitHub marks binary; its size is not in the file list"]


# ---- change 4: stray files are triaged out of `unplaced` into one extra
def test_stray_files_are_one_extra_and_still_listed():
    issue = "Recorder drops the last result"
    files = [f("src/Recorder.cs", EDIT), new("global.json.backup", "{}"), new("prepare-changelog.md", "# How"),
             new("README.md", "x"), new("docs/notes.md", "x"), new("src/.vscode/settings.json.bak", "{}")]
    a = analyse(issue, files)
    assert a.stray == ["global.json.backup", "prepare-changelog.md", "src/.vscode/settings.json.bak"]
    assert kinds(a.extras) == [("stray_file", "stray files")] and a.extras[0].detail == tuple(a.stray)
    assert "global.json.backup" in a.unplaced and "prepare-changelog.md" in a.unplaced      # the list is kept
    one = analyse(issue, [f("src/Recorder.cs", EDIT), new("global.json.backup", "{}")])
    assert kinds(one.extras) == [("stray_file", "global.json.backup")] and one.extras[0].detail == ()
    top = analyse(issue, [f("src/Recorder.cs", EDIT), new("claude_desktop_config.json", "{}")])
    assert top.stray == ["claude_desktop_config.json"]                                      # top level, nothing refers to it
    keep = [f("src/Recorder.cs", EDIT), new("CONTRIBUTING.md", "x"), new("LICENSE", "MIT"), new(".gitkeep", ""),
            new("main.go", "package main"), f("NOTES.md", EDIT), new("notes.txt", "x"), new("src/data/table.csv", "a,b"),
            f("src/app.py", '@@ -1 +1,2 @@\n x = 1\n+open("notes.txt")\n')]
    assert analyse(issue, keep).stray == [] and not any(e.kind == "stray_file" for e in analyse(issue, keep).extras)
    assert analyse("Add a SECURITY.md", [f("src/Recorder.cs", EDIT), new("SECURITY.md", "x")]).stray == []
    cited = [f("src/Recorder.cs", EDIT), new("plan.md", "x"), f("src/app.py", "@@ -1 +1,2 @@\n x = 1\n+# see plan.md\n")]
    assert analyse(issue, cited).stray == ["plan.md"]                                       # a top-level document, cited or not


# ---- change 5: committed build output is one extra per directory
def test_build_output_is_one_extra_per_directory():
    out = [new(f"packages/core/.tshy-build/esm/m{i:02d}.js", "x") for i in range(12)]
    pyc = [f(f"tool/__pycache__/m{i:02d}.cpython-312.pyc", None, status="added", additions=0, deletions=0) for i in range(10)]
    a = analyse("Let generateImage take image input", [f("packages/core/src/image.ts", EDIT)] + out + pyc)
    assert kinds(a.extras) == [("build_output_added", "packages/core/.tshy-build/"), ("build_output_added", "tool/__pycache__/")]
    e = [x for x in a.extras if x.name == "packages/core/.tshy-build/"][0]
    assert "12 generated files committed" in e.why and e.detail == tuple(sorted(x["filename"] for x in out))
    assert not set(a.unplaced) & {x["filename"] for x in out + pyc}
    few = [new(f"dist/m{i}.js", "x") for i in range(3)]
    assert [x for x in extras("Let generateImage take image input", [f("packages/core/src/image.ts", EDIT)] + few)
            if x.kind == "build_output_added"] == []
    site = [new(f"py/venv/lib/python3.12/site-packages/pip/m{i:02d}.py", "x") for i in range(10)]
    assert kinds(extras("Speed up the parser", [f("src/parser.py", EDIT)] + site)) == [
        ("build_output_added", "py/venv/lib/python3.12/site-packages/")]


# ---- change 6: a one-line dependency array in a hunk without its section header (T13)
def test_single_line_dependency_array_without_its_section_header():
    t13 = f("pyproject.toml", '@@ -5,7 +5,7 @@ requires-python = ">=3.10"\n readme = "README.md"\n-dependencies = []\n'
                              '+dependencies = ["leftpad-py>=1.0"]\n license = "MIT"\n')
    assert kinds(extras("Add a greeting command", [f("src/greet.py", EDIT), t13])) == [("new_dependency", "leftpad-py")]
    dev = f("pyproject.toml", '@@ -9 +9 @@\n-dev-dependencies = ["pytest"]\n+dev-dependencies = ["pytest", "hypothesis"]\n')
    assert kinds(extras("Add a greeting command", [f("src/greet.py", EDIT), dev])) == [("new_dependency", "hypothesis")]
    other = f("pyproject.toml", '@@ -9 +9 @@\n-keywords = []\n+keywords = ["leftpad-py"]\n')
    assert extras("Add a greeting command", [f("src/greet.py", EDIT), other]) == []
