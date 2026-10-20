"""Does the browser version of rule 1 (web/deps_rule.js) list exactly the new dependencies the CI job lists (itemator/extras.py)?
The rules are in eval/green_agreement_rubric.json, written before the two were compared. Needs node and eval/cache/aidev/ (written by
eval/aidev_recall.py). Read-only.

usage: python3 eval/green_agreement.py [--out results/green_agreement_v1.json] [--mutants]"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from itemator import extras as X  # noqa: E402

CACHE = ROOT / "eval" / "cache" / "aidev"
KINDS = ("requirements", "pyproject", "npm")
KEYS = ("kind", "path", "name", "why")
# Deliberate breaks of the JavaScript for --mutants: [old, new], each must occur once in web/deps_rule.js.
MUTANTS = [
    ['if (source === null && removed[low]) return;', ''],
    ['if (source !== null && removedSources[source]) return;', ''],
    ['if (seen[low]) return;', ''],
    ['row.asked = issue.toLowerCase().indexOf(source.toLowerCase()) >= 0;', 'row.asked = false;'],
    ['if (acronyms.some(', 'if (false && acronyms.some('],
    ['(short !== name && mentions(issue, short))', 'false'],
    ['[squash(issue), squash(name)]', '[issue, name]'],
    ['{3,}\\b/g', '{2,}\\b/g'],
    ['if (f.status === "added" && PACKAGE_MANIFESTS', 'if (f.status === "nope" && PACKAGE_MANIFESTS'],
    ['if (mentions(issue, name) || mentions(issue, name.slice', 'if (mentions(issue, name) || false && mentions(issue, name.slice'],
    ['return key === "dependencies" || key === "dev-dependencies" || section.slice(-12) === "dependencies";', 'return key === "dependencies";'],
    ['if (section === "build-system") return key === "requires";', ''],
    ['else if (!known && q[3] && HAS_VERSION.test(q[3]))', 'else if (!known && q[3])'],
    ['&& key.toLowerCase() !== "python"', ''],
    ['else if (block === null && NPM_NOT_DEPS.indexOf(key) < 0 && NPM_VERSION.test(value))', 'else if (false)'],
    ['if (s[0] === "-") return;', ''],
    ['if (URLISH.test(s)) { var name = urlReqName(s); if (name) out.push([sign, name, text]); return; }', ''],
    ['if (/^\\s*\\}/.test(text)) { if (stack.length) stack.pop(); else stack = ["<top>"]; return; }', 'if (/^\\s*\\}/.test(text)) { stack.pop(); return; }'],
    ['if (sign === "@") { section = null; arrayKey = null; return; }', ''],
    ['(n === 1 ? "dependency" : "dependencies")', '"dependencies"'],
]


def units() -> list[dict]:
    """(A) every manifest row of the three kinds, under the pull request's own text and an empty issue; (B) under its added names."""
    prs = {r["id"]: r for r in json.loads((CACHE / "pull_request.json").read_text())}
    rows = [r for r in json.loads((CACHE / "commit_details.json").read_text())
            if r.get("patch") and X._manifest_kind(r.get("filename") or "") in KINDS]
    out = []
    for r in sorted(rows, key=lambda r: (r["pr_id"], r["sha"], r["filename"])):
        f = {k: r.get(k) for k in ("filename", "status", "patch")}
        pr = prs.get(r["pr_id"]) or {}
        names = sorted({n for sign, n, _ in X._DEP_PARSERS[X._manifest_kind(f["filename"])](f["patch"]) if sign == "+"})
        base = {"pr": pr.get("html_url"), "sha": r["sha"][:10], "file": f}
        out += [dict(base, id=f"{r['sha'][:10]}:{f['filename']}:{w}", issue=t) for w, t in
                (("pr", f"{pr.get('title') or ''}\n\n{pr.get('body') or ''}"), ("empty", ""), ("names", "Add " + ", ".join(names)))]
    return out


FIXTURES = ROOT / "eval" / "green_fixtures.json"


def record_fixtures() -> list[dict]:
    """(C) every (issue, files) input the Python unit tests of the rules pass to _new_dependencies, cut to the three manifests."""
    import pytest
    seen, real = [], X._new_dependencies

    def spy(issue_text, files):
        keep = [{k: f.get(k) for k in ("filename", "status", "patch")} for f in files
                if f.get("patch") and X._manifest_kind(f.get("filename") or "") in KINDS]
        if keep and (issue_text, keep) not in seen:
            seen.append((issue_text, keep))
        return real(issue_text, files)

    class Plugin:
        def pytest_runtest_setup(self, item):
            X._new_dependencies = spy

        def pytest_runtest_teardown(self, item):
            X._new_dependencies = real

    pytest.main(["-q", "-p", "no:cacheprovider", *sorted(str(p) for p in (ROOT / "tests").glob("test_extras*.py"))], plugins=[Plugin()])
    out = [{"issue": i, "files": f} for i, f in seen]
    FIXTURES.write_text(json.dumps(out, indent=1) + "\n")
    return out


def fixture_units() -> list[dict]:
    return [{"pr": None, "sha": f"fixture-{n}", "file": fx["files"][0], "files": fx["files"], "id": f"fixture-{n}:{fx['files'][0]['filename']}:test",
             "issue": fx["issue"]} for n, fx in enumerate(json.loads(FIXTURES.read_text()))]


def python_says(u: dict) -> list[dict]:
    return [{k: getattr(e, k) for k in KEYS} for e in X._new_dependencies(u["issue"], u.get("files") or [u["file"]])]


def node_says(todo: list[dict], js: pathlib.Path) -> dict:
    with tempfile.TemporaryDirectory() as d:
        src, dst = pathlib.Path(d) / "units.json", pathlib.Path(d) / "out.json"
        src.write_text(json.dumps([{"id": u["id"], "issue": u["issue"], "files": u.get("files") or [u["file"]]} for u in todo]))
        subprocess.run(["node", str(ROOT / "eval" / "green_node.js"), str(js), str(src), str(dst)], check=True, timeout=600)
        return json.loads(dst.read_text())


def mutants(todo: list[dict], py: dict) -> list[dict]:
    text = (ROOT / "web" / "deps_rule.js").read_text()
    out = []
    with tempfile.TemporaryDirectory() as d:
        js = pathlib.Path(d) / "deps_rule.js"
        for old, new in MUTANTS:
            assert text.count(old) == 1, old
            js.write_text(text.replace(old, new, 1))
            got = node_says(todo, js)
            out.append({"break": old[:80], "noticed_by": sum(got[u["id"]] != py[u["id"]] for u in todo)})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/green_agreement_v1.json")
    ap.add_argument("--mutants", action="store_true")
    ap.add_argument("--fixtures", action="store_true", help="add (C), the unit tests' inputs (v2); --record rewrites eval/green_fixtures.json")
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args(argv)
    if a.record:
        record_fixtures()
    todo = units() + (fixture_units() if a.fixtures else [])
    py = {u["id"]: python_says(u) for u in todo}
    js = node_says(todo, ROOT / "web" / "deps_rule.js")
    bad = [{"pr": u["pr"], "sha": u["sha"], "path": u["file"]["filename"], "issue": u["id"].rsplit(":", 1)[1],
            "python": py[u["id"]], "browser": js[u["id"]]} for u in todo if js[u["id"]] != py[u["id"]]]
    out = {"rubric": "eval/green_agreement_rubric.json", "checked": datetime.date.today().isoformat(), "units": len(todo),
           "files": sum(u["id"].endswith((":pr", ":empty", ":names")) for u in todo) // 3,
           "fixtures": sum(u["id"].startswith("fixture-") for u in todo), "units_with_an_extra": sum(bool(py[u["id"]]) for u in todo),
           "identical": len(todo) - len(bad), "all_identical": not bad, "disagreements": bad}
    if a.mutants:
        out["mutants"] = mutants(todo, py)
        out["mutants_unnoticed"] = [m["break"] for m in out["mutants"] if not m["noticed_by"]]
    (ROOT / a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"{out['identical']} of {out['units']} identical; {out['units_with_an_extra']} units list an extra"
          + (f"; {len(out['mutants_unnoticed'])} of {len(MUTANTS)} breaks unnoticed" if a.mutants else ""))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
