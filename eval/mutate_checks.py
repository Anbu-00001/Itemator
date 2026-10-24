"""Mutation test for the checks added after rules v6 (weight, untrusted text, attack shapes, moving references, scanner findings,
"Also checked", the decision log): break one line of a copy, and that module's tests must fail.

The unmutated copy runs first and must pass. Each module runs only its own test files, so a run stays short.

Usage (WORK must be outside the repository, or pytest would collect the copies):
    .venv/bin/python -I eval/mutate_checks.py "$PWD" /tmp/itemator-mutants-checks [module ...]
Exit status 0 only when every mutant is killed.
"""
import pathlib, shutil, subprocess, sys
REPO = pathlib.Path(sys.argv[1]); WORK = pathlib.Path(sys.argv[2]); ONLY = set(sys.argv[3:]) - {"--anchors-only"}
PY = str(REPO / ".venv/bin/python")

MODULES = {
 "patchday": (["tests/test_patchday.py"], [
  ("no cve still derives", "    if not found or SCOPE.read(issue_text) is not None:\n", "    if SCOPE.read(issue_text) is not None:\n"),
  ("fix widened to everything", "return SCOPE.Scope(paths=tuple(sorted(set(fix + locks))), cves=found)", 'return SCOPE.Scope(paths=("**",), cves=found)'),
  ("extra line ignored", "if not old or len(old) != len(new):", "if not old:"),
  ("listed versions ignored", "if not moved or (listed and not moved <= listed):", "if not moved:"),
  ("no fix file still derives", "    if not fix:\n        return None\n", ""),
  ("lockfile anywhere", "\n             and posixpath.dirname(f[\"filename\"]) in dirs]", "]"),
  ("digest not blanked", "X._DOTTED_VERSION.sub(\"V\", _DIGEST.sub(\"D\", line))", "X._DOTTED_VERSION.sub(\"V\", line)"),
  ("added file is the fix", 'if f.get("status") not in (None, "modified"):', "if False:"),
  ("reason not reworded", "if scope is None or not scope.cves:", "if True:"),
  ("whole-line change counted", "if a == b or _blank(a) != _blank(b):", "if a == b:"),
 ]),
 "weight": (["tests/test_weight.py", "tests/test_weighpage.py"], [
  ("yanked file picked", 'hit = [f for f in files if test(f["filename"]) and not f.get("yanked")]', 'hit = [f for f in files if test(f["filename"])]'),
  ("largest file of a tier picked", 'return min(hit, key=lambda f: f["size"])', 'return max(hit, key=lambda f: f["size"])'),
  ("source archive never picked", 'lambda n: _PY_TAG.search(n), lambda n: n.endswith((".tar.gz", ".zip"))):', "lambda n: _PY_TAG.search(n)):"),
  ("npm ranged answer refused", "if status not in (200, 206):", "if status not in (200,):"),
  ("bundled package counted", 'if not isinstance(key, dict) or n.get("bundled"):', "if not isinstance(key, dict):"),
  ("graph error read as a graph", 'if doc.get("error"):', "if False:"),
  ("empty graph weighed", "    if not nodes:\n", "    if False:\n"),
  ("cap never said", '"capped": len(nodes) > MAX_NODES,', '"capped": False,'),
  ("direct count of all", '"direct": sum(1 for n in nodes if n["relation"] == "DIRECT")', '"direct": len(nodes)'),
  ("unknown size hidden", "{'at least ' if (w['capped'] or unknown) else 'about '}", "{'at least ' if w['capped'] else 'about '}"),
  ("one package read as many", "    if n <= 1:\n", "    if n < 1:\n"),
  ("monthly line without a count", 'if not runs or not w.get("sized") or not runs.get("count"):', "if not runs:"),
  ("monthly says about when unknown", 'least = runs["at_least"] or w["capped"] or w["of"] > w["sized"]', 'least = runs["at_least"]'),
  ("kB boundary in binary units", "    if n < 1000 * 1000:\n", "    if n < 1024 * 1024:\n"),
 ]),
 "untrusted": (["tests/test_untrusted.py"], [
  ("comments read as commands", 'if text.lstrip().startswith("#"):', "if False:"),
  ("removed files read", 'if f.get("status") == "removed" or not f.get("patch") or not is_target(path) or FE._SKIP_PATH.search(path):', 'if not f.get("patch") or not is_target(path) or FE._SKIP_PATH.search(path):'),
  ("any file is a target", "    return PL.is_ci_path(path) or path.startswith(\".github/workflows/\")", "    return True or PL.is_ci_path(path) or path.startswith(\".github/workflows/\")"),
  ("single quotes protect nothing", "if _in_single_quotes(text, m.start()) or not _command_like(text, script):", "if not _command_like(text, script):"),
  ("variables: read as a command", "return m.group(1) in _SCRIPT_KEYS", "return True"),
  ("backslash escapes ignored", 'if c == "\\\\" and not single:', "if False:"),
  ("agent prompt not named", "if _AGENT.search(text):", "if False:"),
  ("stranger text needs no command", "if _pastes_stranger_text(text) and _command_like(text, script):", "if _pastes_stranger_text(text):"),
 ]),
 "shapes": (["tests/test_shapes.py"], [
  ("decode-and-run off", 'if any(p.search(text) for p in _DECODE):\n        return "decode-and-run"', 'if False:\n        return "decode-and-run"'),
  ("env send needs no whole env", "(_SEND.search(text) and _WHOLE_ENV.search(text))", "_SEND.search(text)"),
  ("runs never split", "if cur and n != cur[-1][0] + 1:", "if False:"),
  ("removed files read", 'if f.get("status") == "removed" or not f.get("patch") or FE._SKIP_PATH.search(path):', 'if not f.get("patch") or FE._SKIP_PATH.search(path):'),
 ]),
 "moving": (["tests/test_moving.py"], [
  ("variable image flagged", 'if ref.startswith(("$", "${")) or ref == "scratch":', 'if ref == "scratch":'),
  ("untagged image passes", '    if ":" not in last:\n        return "untagged"', '    if ":" not in last:\n        return None'),
  ("pinned tag read as latest", 'return "latest" if last.rsplit(":", 1)[1] == "latest" else None', 'return "latest"'),
  ("comments read", "            if line.lstrip().startswith(\"#\"):", "            if False:"),
  ("untagged build stage flagged", 'if not (dockerfile and k == "untagged"):', "if True:"),
  ("curl pipe to shell off", "if hit is None and _PIPE.search(line):", "if False:"),
 ]),
 "scanners": (["tests/test_scanners.py"], [
  ("removed files kept", 'changed = {f.get("filename"): f for f in files if f.get("status") != "removed"}', 'changed = {f.get("filename"): f for f in files}'),
  ("findings outside the change kept", '        if d["path"] not in changed:\n            continue', '        if d["path"] not in changed:\n            changed[d["path"]] = {}\n            new_lines[d["path"]] = set()'),
  ("touched read as introduced", "(introduced if any(n in new_lines[d[\"path\"]] for n in range(d[\"line\"], max(d[\"line\"], d[\"end\"]) + 1)) else touched)", "introduced"),
  ("multi-line finding reads one line", 'range(d["line"], max(d["line"], d["end"]) + 1)', 'range(d["line"], d["line"] + 1)'),
  ("named flag always true", 'd = {**d, "named": d["path"] in listed}', 'd = {**d, "named": True}'),
  ("oversized report read", "            if os.path.getsize(path) > MAX_BYTES:", "            if False:"),
 ]),
 "checked": (["tests/test_checked.py", "tests/test_untrusted.py", "tests/test_shapes.py", "tests/test_moving.py", "tests/test_scanners.py"], [
  ("scanner sentence dropped", "    if scanners:\n", "    if False:\n"),
  ("untrusted sentence dropped", "    if untrusted:\n", "    if False:\n"),
  ("shapes sentence dropped", "    if shapes:\n", "    if False:\n"),
  ("moving sentence dropped", "    if moving:\n", "    if False:\n"),
  ("empty line not None", "    if not parts:\n        return None", "    if False:\n        return None"),
  ("line length cap ignored", "if kept and used + len(part) + 1 > MAX_LINE:", "if False:"),
 ]),
 "decisions": (["tests/test_decisions.py", "tests/test_shipped.py"], [
  ("pipeline of any commit", 'pl = next((p for p in pls if not head_sha or p.get("sha") == head_sha), None)', "pl = next(iter(pls), None)"),
  ("no report read as no extras", "    if report is None:\n        return None", "    if report is None:\n        return []"),
  ("stale summary answers the merge", 'if parsed is not None and (not mr.get("sha") or parsed["sha"] == mr.get("sha")):', "if parsed is not None:"),
  ("partial answers ignored", "unanswered = None if listed is None else [n for n in listed if n not in answered]", "unanswered = listed"),
  ("unknown counted as answered", 'out["no_report"] = len([e for e in entries if e.get("unanswered") is None])', 'out["no_report"] = 0'),
  ("author alone not counted", '"by_author_alone": len([i for i in items if i["by_author"]]),', '"by_author_alone": 0,'),
  ("removed weight summed as kept", 'for d in ("kept", "removed"):\n        ws = [i["weight"] for e in entries for i in e["extras"] if i["decision"] == d and i.get("weight")]', 'for d in ("kept", "removed"):\n        ws = [i["weight"] for e in entries for i in e["extras"] if i.get("weight")]'),
 ]),
}


def run(d, rel, text, tests):
    if d.exists(): shutil.rmtree(d)
    for part in ("itemator", "tests", "results", "web", "flows", "skills", "docs", ".gitlab"):
        if (REPO / part).is_dir():
            shutil.copytree(REPO / part, d / part, ignore=shutil.ignore_patterns("__pycache__", "*.png"))
    for f in REPO.iterdir():                           # .gitlab-ci.yml, pyproject.toml, the policy file and the like
        if f.is_file():
            shutil.copy2(f, d / f.name)
    (d / "eval").mkdir()
    for f in (REPO / "eval").iterdir():                # its files only: eval/cache holds hundreds of MB of downloads
        if f.is_file():
            shutil.copy2(f, d / "eval" / f.name)
    (d / rel).write_text(text)
    return subprocess.run([PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests], cwd=d, capture_output=True, text=True)


if "--anchors-only" in sys.argv:            # tests/test_mutation_anchors.py: every anchor still names one place in the code
    for module, (_, mutants) in MODULES.items():
        src = (REPO / f"itemator/{module}.py").read_text()
        for label, old, new in mutants:
            assert src.count(old) == 1, f"{module} mutant {label!r}: anchor found {src.count(old)} times"
    print(f"{sum(len(m) for _, m in MODULES.values())} anchors found"); sys.exit(0)
total = survivors = 0
for module, (tests, mutants) in MODULES.items():
    if ONLY and module not in ONLY:
        continue
    rel = f"itemator/{module}.py"
    src = (REPO / rel).read_text()
    base = run(WORK / f"{module}-base", rel, src, tests)
    if base.returncode != 0:
        print(f"{module}: the unmutated copy fails, so no mutant can be judged:\n" + base.stdout[-2000:]); sys.exit(2)
    for i, (label, old, new) in enumerate(mutants):
        total += 1
        assert src.count(old) == 1, f"{module} mutant {label!r}: anchor found {src.count(old)} times"
        mutated = src.replace(old, new)
        try:
            compile(mutated, rel, "exec")
        except SyntaxError as e:            # a mutant that does not compile is not "killed by a test": it is a bad mutant
            print(f"INVALID  {module:10s} {label:40s} {e.msg}"); survivors += 1; continue
        r = run(WORK / f"{module}-{i:02d}", rel, mutated, tests)
        failed = [l.split("::")[1].split(" ")[0] for l in r.stdout.splitlines() if l.startswith("FAILED")]
        killed = r.returncode != 0
        survivors += not killed
        print(f"{'KILLED ' if killed else 'SURVIVED'} {module:10s} {label:40s} {','.join(failed)[:120]}")
print(f"{total - survivors}/{total} mutants killed")
sys.exit(1 if survivors else 0)
