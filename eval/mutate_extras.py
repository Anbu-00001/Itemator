"""Mutation test: break each rule in a copy of extras.py; the suite must fail.

Usage (WORK must be outside the repository, or pytest would collect the copies):
    .venv/bin/python -I eval/mutate_extras.py "$PWD" /tmp/itemator-mutants
Exit status 0 only when every mutant is killed.
"""
import pathlib, shutil, subprocess, sys
REPO = pathlib.Path(sys.argv[1]); WORK = pathlib.Path(sys.argv[2])
PY = str(REPO / ".venv/bin/python")
M = [
 ("1 new_dependency off", "def _new_dependencies(issue_text, files):\n    out = []", "def _new_dependencies(issue_text, files):\n    return []"),
 ("1 version bump counted as new", "if source is None and low in removed:", "if False:"),
 ("1 issue mention ignored", "if _mentions(issue_text, name) or (short != name and _mentions(issue_text, short)):", "if False:"),
 ("1 go indirect counted", 'if m and not (m.group(2) or "").replace(" ", "").startswith("//indirect"):', "if m:"),
 ("1 pyproject keywords counted", "elif not known and q.group(3) and _HAS_VERSION.search(q.group(3)):", "elif not known:"),
 ("2 ci_or_config off", "def _ci_or_config(issue_text, files):\n    out = []", "def _ci_or_config(issue_text, files):\n    return []"),
 ("2 mention ignored", 'if _mentions(issue_text, _base(f["filename"])) or any(_mentions(issue_text, w) for w in words):', "if False:"),
 ("3 deleted test ignored", 'out.append(Extra("tests_removed", path, path, "deletes this test file"))', "pass"),
 ("3 net loss ignored", "if minus > plus and net[label] < 0:", "if False:"),
 ("3 MR-wide guard dropped", "if minus > plus and net[label] < 0:", "if minus > plus:"),
 ("4 public_api off", "def _public_api_removed(issue_text, files):\n    defined_again = set()", "def _public_api_removed(issue_text, files):\n    return []\n    defined_again = set()"),
 ("4 underscore names counted", r'_PY_DEF = re.compile(r"^(?: {0,4}|\t)(?:async\s+def|def|class)\s+([A-Za-z]\w*)")', r'_PY_DEF = re.compile(r"^(?: {0,4}|\t)(?:async\s+def|def|class)\s+([A-Za-z_]\w*)")'),
 ("4 redefinition ignored", "if name in seen or name in defined_again or _mentions(issue_text, name):", "if name in seen or _mentions(issue_text, name):"),
 ("4 JS export list ignored", "        m = _JS_EXPORT_LIST.match(text)\n        if m:", "        m = _JS_EXPORT_LIST.match(text)\n        if False:"),
 ("5 file_outside_ask off", "if p not in named and not _near(p, named) and not _test_support(p)]", "if False]"),
 ("5 same-directory rule dropped", "        if a == b:\n            return True\n", ""),
 ("5 generic names match tokens", "if name.lower() in generic or len(_squash(name)) < 3:", "if len(_squash(name)) < 3:"),
 ("5 abstain dropped", "    if all(_test_support(p) for p in named):\n        return [], sorted(candidates), False", "    if False:\n        pass"),
 ("5 docs not exempt", "    return (b in _LOCKFILES or _DOC_NAME.fullmatch(b) is not None", "    return (b in _LOCKFILES"),
 ("5 lockfiles not exempt", "    return (b in _LOCKFILES or _DOC_NAME", "    return (False or _DOC_NAME"),
 ("5d test-of-named dropped", "        if is_test_file(f[\"filename\"]) and _squash(_stem(f[\"filename\"])) in named_stems:", "        if False:"),
 ("5c directory tokens dropped", "                    or any(_token_named(d, toks, _GENERIC_DIRS) for d in _dirs(path) if not own(d))):", "                    ):"),
 ("5 three-word joins dropped", '_forms("".join(seq[i:i + 2])) | _forms("".join(seq[i:i + 3]))', '_forms("".join(seq[i:i + 2]))'),
 # ---- rules v2 (T7)
 ("v2 version=1 not dispatched", "    if version == 1:\n", "    if False:\n"),
 ("v2 1 URL lines yield nothing", "            name = _url_req_name(s)\n", "            name = None\n"),
 ("v2 1 URL source read as version", "            source = _url_source(kind, text)\n", "            source = None\n"),
 ("v2 1 npm owner/repo not a URL", " or _NPM_SHORTHAND.fullmatch(value):", ":"),
 ("v2 1 moved URL counted", "            if source is not None and source in removed_sources:\n", "            if False:\n"),
 ("v2 1 URL mention ignored", "                if source.lower() in issue_text.lower():\n", "                if False:\n"),
 ("v2 2 dependabot words dropped", '     ("dependabot", "renovate")),', "     _CI_WORDS),"),
 ("v2 2 lifecycle off", "return out + _npm_lifecycle(issue_text, files) + _pyproject_lint(issue_text, files)", "return out + _pyproject_lint(issue_text, files)"),
 ("v2 2 lifecycle only new keys", 'for key, value in sorted(pairs["+"] - pairs["-"]):', 'for key, value in sorted(p for p in pairs["+"] if p[0] not in {k for k, _ in pairs["-"]}):'),
 ("v2 2 lifecycle mention ignored", "            if not _mentions(issue_text, key):\n", "            if True:\n"),
 ("v2 2 pyproject lint off", " + _pyproject_lint(issue_text, files)\n", "\n"),
 ("v2 2 lint unknown-section keys ignored", "if lint or (section is None and (key in _IGNORE_KEYS or array_key in _IGNORE_KEYS)):", "if lint:"),
 ("v2 2 lint mention ignored", '        if hit and not (_mentions(issue_text, "pyproject.toml")\n                        or any(_mentions(issue_text, w) for w in _LINT_WORDS + ("pre-commit",))):', "        if hit:"),
 ("v2 3a source twin dropped", "if b in added_names or _squash(st) in gone_sources:", "if b in added_names:"),
 ("v2 3a directory rewrite dropped", "if lost.get(d, 0) > 0 and gained.get(d, 0) >= lost[d]:", "if False:"),
 ("v2 3a rewrite counts any directory", "gained.get(d, 0) >= lost[d]:", "sum(gained.values()) >= lost[d]:"),
 ("v2 5 package dir names files", "for d in _dirs(path) if not own(d))):", "for d in _dirs(path))):"),
 ("v2 5 package stem names files", "(not own(_stem(path)) and _token_named(", "(_token_named("),
 ("v2 5 tests-only anchor allowed", "    if all(_test_support(p) for p in named):\n", "    if not named:\n"),
 ("v2 5 two shared dirs dropped", "        if common >= 2:\n", "        if False:\n"),
 ("v2 5 test support flagged", " and not _test_support(p)]", "]"),
 ("v2 5 fixtures not support", '_SUPPORT_DIRS = _TEST_DIRS | {"fixtures", "__fixtures__", "testdata", "test-data", "__mocks__", "mocks"}', "_SUPPORT_DIRS = _TEST_DIRS"),
 ("v2 5 changeset not exempt", '"__snapshots__", ".changeset")', '"__snapshots__")'),
]
src = (REPO / "itemator/extras.py").read_text()
survivors = 0
for i, (label, old, new) in enumerate(M):
    assert src.count(old) == 1, f"mutant {label!r}: anchor found {src.count(old)} times"
    d = WORK / f"m{i:02d}"
    if d.exists(): shutil.rmtree(d)
    shutil.copytree(REPO / "itemator", d / "itemator"); shutil.copytree(REPO / "tests", d / "tests")
    (d / "itemator/extras.py").write_text(src.replace(old, new))
    r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], cwd=d, capture_output=True, text=True)
    failed = [l.split("::")[1].split(" ")[0] for l in r.stdout.splitlines() if l.startswith("FAILED")]
    killed = r.returncode != 0
    survivors += not killed
    print(f"{'KILLED ' if killed else 'SURVIVED'} {label:40s} {','.join(failed)[:150]}")
print(f"{len(M) - survivors}/{len(M)} mutants killed")
sys.exit(1 if survivors else 0)
