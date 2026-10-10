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
 ("1 version bump counted as new", "if low in removed or low in seen:", "if low in seen:"),
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
 ("5 file_outside_ask off", "for p in candidates if p not in named and posixpath.dirname(p) not in named_dirs]", "for p in candidates if False]"),
 ("5 same-directory rule dropped", "for p in candidates if p not in named and posixpath.dirname(p) not in named_dirs]", "for p in candidates if p not in named]"),
 ("5 generic names match tokens", "if name.lower() in generic or len(_squash(name)) < 3:", "if len(_squash(name)) < 3:"),
 ("5 abstain dropped", "    if not named:\n        return [], sorted(candidates), False\n", ""),
 ("5 docs not exempt", "    return (b in _LOCKFILES or _DOC_NAME.fullmatch(b) is not None", "    return (b in _LOCKFILES"),
 ("5 lockfiles not exempt", "    return (b in _LOCKFILES or _DOC_NAME", "    return (False or _DOC_NAME"),
 ("5d test-of-named dropped", "        if is_test_file(f[\"filename\"]) and _squash(_stem(f[\"filename\"])) in named_stems:", "        if False:"),
 ("5c directory tokens dropped", "                    or any(_token_named(d, toks, _GENERIC_DIRS) for d in _dirs(path))):", "                    ):"),
 ("5 three-word joins dropped", '_forms("".join(seq[i:i + 2])) | _forms("".join(seq[i:i + 3]))', '_forms("".join(seq[i:i + 2]))'),
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
    print(f"{'KILLED ' if killed else 'SURVIVED'} {label:32s} {','.join(failed)}")
print(f"{len(M) - survivors}/{len(M)} mutants killed")
sys.exit(1 if survivors else 0)
