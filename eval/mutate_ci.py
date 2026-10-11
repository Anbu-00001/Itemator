"""Mutation test for the CI job (T11): break the state logic, the injection scan or the
diff in a copy of itemator/ci.py; tests/test_ci.py must fail for every mutant.

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
src = (REPO / "itemator/ci.py").read_text()
def run(i, text):
    d = WORK / f"m{i:02d}"
    if d.exists(): shutil.rmtree(d)
    for sub in ("itemator", "tests", "tools"):
        shutil.copytree(REPO / sub, d / sub, ignore=shutil.ignore_patterns("__pycache__"))
    (d / "itemator/ci.py").write_text(text)
    return subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_ci.py"], cwd=d, capture_output=True, text=True)
base = run(99, src)
if base.returncode != 0:
    print("the unmutated copy fails, so no mutant can be judged:\n" + base.stdout[-2000:]); sys.exit(2)
survivors = 0
for i, (label, old, new) in enumerate(M):
    assert src.count(old) == 1, f"mutant {label!r}: anchor found {src.count(old)} times"
    r = run(i, src.replace(old, new))
    failed = [l.split("::")[1].split(" ")[0] for l in r.stdout.splitlines() if l.startswith("FAILED")]
    killed = r.returncode != 0
    survivors += not killed
    print(f"{'KILLED ' if killed else 'SURVIVED'} {label:40s} {','.join(failed)[:150]}")
print(f"{len(M) - survivors}/{len(M)} mutants killed")
sys.exit(1 if survivors else 0)
