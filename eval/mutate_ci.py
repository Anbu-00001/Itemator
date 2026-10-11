"""Mutation test for the CI job (T11, T12a): break the state logic, the injection scan, the
diff, the line counting and anchors, the thread stub or the job-log copy in a copy of
itemator/ci.py; tests/test_ci.py (T11 mutants) or tests/test_ci_anchors.py (T12a mutants) must
fail for every mutant.

Usage (WORK must be outside the repository, or pytest would collect the copies):
    .venv/bin/python -I eval/mutate_ci.py "$PWD" /tmp/itemator-ci-mutants
Exit status 0 only when every mutant is killed.
"""
import pathlib, shutil, subprocess, sys
REPO = pathlib.Path(sys.argv[1]); WORK = pathlib.Path(sys.argv[2])
PY = str(REPO / ".venv/bin/python")
M = [
 # ---- state logic
 ("state: no_issue dropped", '    if not issues:\n        return "no_issue"\n', ""),
 ("state: author check any()", 'and all(i["author_id"] == mr_author_id for i in issues)', 'and any(i["author_id"] == mr_author_id for i in issues)'),
 ("state: author check dropped", '    if _author_wrote(issues, mr_author_id):\n        return "author_wrote_issue"\n', ""),
 ("state: author outranks extras", '    if analysis.extras:                      # the extras are the point; the author note rides along as a caveat\n', '    if analysis.extras and not _author_wrote(issues, mr_author_id):\n'),
 ("state: extras dropped", '    if analysis.extras:                      # the extras are the point; the author note rides along as a caveat\n        return "extras"\n', ""),
 ("card: caveat dropped", '"caveat_line": caveat,', '"caveat_line": None,'),
 ("card: caveat repeats the final line", 'state in ("extras", "unplaced_only", "inside_ask")', 'True'),
 ("state: unplaced_only dropped", '    if analysis.unplaced:\n        return "unplaced_only"\n', ""),
 ("state: no_issue keeps extras", 'found = [] if state == "no_issue" else analysis.extras', "found = analysis.extras"),
 ("issues: closes_issues ignored", "    if closes:\n", "    if False:\n"),
 ("issues: description fallback dropped", "    for n in closing_refs(description):", "    for n in []:"),
 ("api: token sent first", "status, body = self.http(url, {})", 'status, body = self.http(url, {"JOB-TOKEN": self.token} if self.token else {})'),
 ("card: singular wrong", '"Skim this file." if n == 1 else', '"Skim this file." if n == 0 else'),
 ("card: injection line dropped", '"injection_line": INJECTION_LINE if injection else None}', '"injection_line": None}'),
 # ---- injection scan
 ("scan: removed lines scanned", '        elif line.startswith("+"):\n            yield', '        elif line.startswith(("+", "-")):\n            yield'),
 ("scan: context lines not counted", '        elif line.startswith(" "):\n            n += 1', '        elif line.startswith(" "):\n            pass'),
 ("scan: ignore_previous dropped", '("ignore_previous", r"', '("ignore_previous", r"(?!x)x'),
 ("scan: reviewer_approve dropped", '("reviewer_approve", r"', '("reviewer_approve", r"(?!x)x'),
 ("scan: system_prompt dropped", '("system_prompt", r"', '("system_prompt", r"(?!x)x'),
 ("scan: invisible chars kept", 'plain = _INVISIBLE.sub("", text)', "plain = text"),
 ("scan: tag range off", r'_TAG = re.compile("[\U000E0000-\U000E007F]")', r'_TAG = re.compile("[\U000E0080-\U000E00FF]")'),
 ("scan: bidi dropped", "if _BIDI.search(line):", "if False:"),
 ("scan: comment addressee not required", "(_ADDRESSEE.search(body) and _IMPERATIVE.search(body))", "_IMPERATIVE.search(body)"),
 ("scan: html comments dropped", "for m in _COMMENT.finditer(joined):", "for m in []:"),
 ("scan: comment line from its end", 'starts[joined.count("\\n", 0, m.start())]', 'starts[joined.count("\\n", 0, m.end())]'),
 ("scan: agent config dropped", "if any(_is_agent_config(p) for p in paths):", "if False:"),
 ("scan: rename source ignored", 'paths = {f["filename"], f.get("previous_filename") or f["filename"]}', 'paths = {f["filename"]}'),
 ("scan: flow YAML not config", 'or ("flows" in parts[:-1] and base.endswith((".yml", ".yaml"))))', "or False)"),
 # ---- diff
 ("diff: binary flag dropped", '            f["binary"] = True', "            pass"),
 ("diff: previous_filename dropped", '            f["previous_filename"] = old', "            pass"),
]

# T12a: anchors (line counting, which line, which paths), thread stubs, the job-log copy
A = [
 # ---- line counting
 ("anchors: hunk start off by one", "old, new = int(m.group(1)), int(m.group(2))", "old, new = int(m.group(1)), int(m.group(2)) + 1"),
 ("anchors: old and new starts swapped", "old, new = int(m.group(1)), int(m.group(2))", "new, old = int(m.group(1)), int(m.group(2))"),
 ("anchors: hunk header ignored", "                old, new = int(m.group(1)), int(m.group(2))\n", "                pass\n"),
 ("anchors: context lines not counted", '            yield " ", old, new, line[1:]\n            old += 1\n            new += 1\n', '            yield " ", old, new, line[1:]\n'),
 ("anchors: context counted on one side", '            yield " ", old, new, line[1:]\n            old += 1\n            new += 1\n', '            yield " ", old, new, line[1:]\n            new += 1\n'),
 ("anchors: removed lines counted as new", '            yield "-", old, None, line[1:]\n            old += 1\n', '            yield "-", old, None, line[1:]\n            old += 1\n            new += 1\n'),
 ("anchors: added lines counted as old", '            yield "+", None, new, line[1:]\n            new += 1\n', '            yield "+", None, new, line[1:]\n            new += 1\n            old += 1\n'),
 ("anchors: removed lines not counted", '            yield "-", old, None, line[1:]\n            old += 1\n', '            yield "-", old, None, line[1:]\n'),
 ("anchors: no-newline marker counted", r'        if line.startswith("\\"):' + "\n            continue\n", ""),
 ("anchors: trailing blank line kept", '    if lines[-1] == "":\n        lines.pop()\n', ""),
 ("anchors: context line anchored", "if sign in signs and (matches", 'if sign in signs + " " and (matches'),
 # ---- which line
 ("anchors: dependency not matched by name", "            matches = _names(e.name)\n", "            matches = None\n"),
 ("anchors: name boundary after dropped", r'+ r"(?![A-Za-z0-9])"', '+ ""'),
 ("anchors: name boundary before dropped", r'r"(?<![A-Za-z0-9])" + ', '"" + '),
 ("anchors: name separators exact", r'r"[-_.]*".join(parts)', '"-".join(parts)'),
 ("anchors: name case-sensitive", ", re.I).search", ").search"),
 ("anchors: npm script not matched by key", """            matches = lambda text: f'"{e.name}"' in text\n""", "            matches = None\n"),
 ("anchors: tests anchor on any removed line", 'signs, matches = "-", (X._ASSERT if "assertion lines" in e.why else X._TEST_DEF).search', 'signs, matches = "-", None'),
 ("anchors: assertions anchor on the definition", '"assertion lines" in e.why else', 'False else'),
 ("anchors: tests anchor on added lines", 'signs, matches = "-", (X._ASSERT', 'signs, matches = "+", (X._ASSERT'),
 ("anchors: symbol not matched", 'signs, matches = "-", lambda text: e.name in X._symbols(text, ext)', 'signs, matches = "-", None'),
 ("anchors: added kinds anchor on removed lines", '        signs, matches = "+", None\n', '        signs, matches = "-", None\n'),
 ("anchors: no fallback to the other sign", " or _first_line(f, signs) or _first_line(f, other)", " or _first_line(f, signs)"),
 ("anchors: no fallback to any line of the sign", " or _first_line(f, signs) or _first_line(f, other)", " or _first_line(f, other)"),
 ("anchors: mass event anchors on its directory", "f = by_path.get(e.detail[0] if e.detail else e.path)", "f = by_path.get(e.path)"),
 ("anchors: mass event anchors on its last file", "by_path.get(e.detail[0] if", "by_path.get(e.detail[-1] if"),
 # ---- which paths, which files get none
 ("anchors: rename source ignored", '"old_path": f.get("previous_filename") or f["filename"]', '"old_path": f["filename"]'),
 ("anchors: rename target ignored", '"new_path": f["filename"],\n                    "old_line"', '"new_path": f.get("previous_filename") or f["filename"],\n                    "old_line"'),
 ("anchors: binary flag ignored", 'if f.get("binary") or not patch:', "if not patch:"),
 ("anchors: size limit off by one", "> MAX_PATCH_BYTES:", ">= MAX_PATCH_BYTES:"),
 ("anchors: size limit dropped", 'if len(patch.encode("utf-8", "replace")) > MAX_PATCH_BYTES:', "if False:"),
 ("anchors: missing file reason", 'return None, "file not in the diff"', 'return None, "no text patch"'),
 ("anchors: extras carry none", '"extras": [describe_extra(e, by_path) for e in found],', '"extras": [{**e.to_dict(), "detail": list(e.detail)} for e in found],'),
 # ---- stub, plain facts
 ("stub: no closing full stop", '    if not why.endswith((".", "!", "?")):\n        why += "."\n', ""),
 ("stub: double full stop", 'if not why.endswith((".", "!", "?")):', "if True:"),
 ("stub: kind instead of label", '({_label(e)}): {why}', '({e.kind}): {why}'),
 ("stub: code fence too short", "default=0) + 1)", "default=1))"),
 ("stub: code span unpadded", 'pad = " " if text.startswith("`") or text.endswith("`") else ""', 'pad = ""'),
 ("stub: newline kept in the name", '    text = re.sub(r"[\\r\\n]+", " ", text)\n', ""),
 ("stub: newline kept in the reason", 'why = re.sub(r"[\\r\\n]+", " ", e.why).strip()', "why = e.why"),
 ("plain facts: detail count wrong", '"detail_count": len(e.detail)', '"detail_count": 0'),
 # ---- job log
 ("log: markers not escaped", r'.replace("<", "\\u003c").replace(">", "\\u003e")', ""),
 ("log: size limit ignored", "    if len(text) > limit:\n", "    if False:\n"),
 ("log: detail kept in the compact copy", 'c = {**report, "extras": [{k: v for k, v in e.items() if k != "detail"} for e in report["extras"]]}', "c = dict(report)"),
 ("log: truncated flag missing", 'text = _one_line({**c, "truncated": cut})', "text = _one_line(c)"),
 ("log: long lists never cut", "if size() > limit and len(c[key]) > 20:", "if False:"),
 ("log: plain facts never cut", '        if size() > limit:\n            c["extras"] = [{k: v for k, v in e.items() if k != "plain_facts"}', '        if False:\n            c["extras"] = [{k: v for k, v in e.items() if k != "plain_facts"}'),
 ("log: extras dropped all at once", 'c["extras"] = c["extras"][:len(c["extras"]) // 2]', 'c["extras"] = []'),
 ("log: extras total not recorded", '            c["extras_total"] = n\n', ""),
 ("log: job prints no block", "    print(log_block(report))\n", ""),
 ("log: block printed before the card", '    print(report["card"]["final_line"])\n    print(report["card"]["todo_line"])\n    print(log_block(report))\n', '    print(log_block(report))\n    print(report["card"]["final_line"])\n    print(report["card"]["todo_line"])\n'),
]
src = (REPO / "itemator/ci.py").read_text()
def run(i, text, tests="tests/test_ci.py"):
    d = WORK / f"m{i:02d}"
    if d.exists(): shutil.rmtree(d)
    for sub in ("itemator", "tests", "tools"):
        shutil.copytree(REPO / sub, d / sub, ignore=shutil.ignore_patterns("__pycache__"))
    (d / "itemator/ci.py").write_text(text)
    return subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", tests], cwd=d, capture_output=True, text=True)
for target in ("tests/test_ci.py", "tests/test_ci_anchors.py"):
    base = run(99, src, target)
    if base.returncode != 0:
        print(f"the unmutated copy fails {target}, so no mutant can be judged:\n" + base.stdout[-2000:]); sys.exit(2)
survivors = 0
for i, (label, old, new, target) in enumerate([(*m, "tests/test_ci.py") for m in M] + [(*m, "tests/test_ci_anchors.py") for m in A]):
    assert src.count(old) == 1, f"mutant {label!r}: anchor found {src.count(old)} times"
    r = run(i, src.replace(old, new), target)
    failed = [l.split("::")[1].split(" ")[0] for l in r.stdout.splitlines() if l.startswith("FAILED")]
    killed = r.returncode != 0
    survivors += not killed
    print(f"{'KILLED ' if killed else 'SURVIVED'} {label:46s} {','.join(failed)[:150]}")
total = len(M) + len(A)
print(f"{total - survivors}/{total} mutants killed")
sys.exit(1 if survivors else 0)
