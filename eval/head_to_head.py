"""Head-to-head (eval/head_to_head_rubric.json, pushed before any rival ran): on the AIDev scope-comment cases, which of
the files reviewers objected to do Itemator's rules and two offline scope checkers name, and how many files does each
name in total? Reads only eval/cache/aidev (the recall study's cache); the rivals run locally with no key. Results hold
paths, counts and yes/no only.

usage: python3 eval/head_to_head.py --overreach PATH/overreach --scd PATH/scope_creep.py [--out results/head_to_head_v1.json]"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import pathlib
import statistics
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
from itemator import extras as X  # noqa: E402
import aidev_recall as R  # noqa: E402

TOOLS = ("itemator", "overreach", "scope_creep_detector")


# ---------------------------------------------------------------- pure parts (tests/test_head_to_head.py)

def unified_diff(files: list) -> str:
    """A diff the rivals can read: a `diff --git` header per file, then the dataset's patch hunks when there are any."""
    out = []
    for f in files:
        n = f["filename"]
        if not n:                                         # a few dataset rows carry no filename
            continue
        old = "/dev/null" if f["status"] == "added" else f"a/{n}"
        new = "/dev/null" if f["status"] == "removed" else f"b/{n}"
        out.append(f"diff --git a/{n} b/{n}")
        if f["status"] == "added":
            out.append("new file mode 100644")
        elif f["status"] == "removed":
            out.append("deleted file mode 100644")
        out += [f"--- {old}", f"+++ {new}"]
        if f.get("patch"):
            out.append(f["patch"].rstrip("\n"))
    return "\n".join(out) + "\n"


def overreach_named(out: dict | None) -> set:
    return {f["file"] for f in (out or {}).get("findings") or () if isinstance(f, dict) and f.get("file")}


def overreach_advice(out: dict | None) -> set:
    w = ((out or {}).get("blast_radius") or {}).get("warnings") or ()
    return {p for x in w if isinstance(x, dict) for p in x.get("files") or ()}


def scd_named(out: dict | None) -> set:
    named = set()
    for key in ("likely_creep", "config_edits", "new_deps", "api_renames"):
        for x in (out or {}).get(key) or ():
            p = x.get("path") or x.get("file") if isinstance(x, dict) else None
            if p:
                named.add(p)
    return named


def itemator_named(task: str, files: list, repo: str) -> set:
    extras = X.analyse(task, files, repo=repo, version=6).extras
    return {f["filename"] for f in files if f["filename"] and R.listed(extras, f["filename"])}


def wilson(k: int, n: int) -> list:
    if not n:
        return [0.0, 0.0]
    p, z = k / n, 1.96
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(c - h, 3), round(c + h, 3)]


def summarize(rows: list, snaps: list) -> dict:
    """`rows`: one per case {named: {tool: bool}}; `snaps`: one per snapshot {changed, named: {tool: n}, errors: {tool: bool}}."""
    n = len(rows)
    s = {"cases": n, "snapshots": len(snaps), "files_changed": sum(x["changed"] for x in snaps), "tools": {}}
    for t in TOOLS:
        k = sum(r["named"][t] for r in rows)
        total = sum(x["named"][t] for x in snaps)
        s["tools"][t] = {"cases_named": k, "wilson95": wilson(k, n), "files_named": total,
                         "median_named_per_snapshot": statistics.median([x["named"][t] for x in snaps]) if snaps else 0,
                         "density": round(k / total, 3) if total else None,
                         "errors": sum(x["errors"].get(t, False) for x in snaps)}
    for t in TOOLS[1:]:
        s["tools"][t]["only_this_not_itemator"] = sum(r["named"][t] and not r["named"]["itemator"] for r in rows)
        s["tools"][t]["only_itemator_not_this"] = sum(r["named"]["itemator"] and not r["named"][t] for r in rows)
    return s


# ---------------------------------------------------------------- live (local processes only)

def run_json(cmd: list, env: dict | None = None) -> dict | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
        return json.loads(r.stdout)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None


def snapshots():
    """(key, task, files, repo, cases) per reviewed snapshot of the recall study, rebuilt from its cache."""
    cases = json.loads(R.CASES.read_text())["comments"]
    readable = {r["comment_id"] for r in json.loads((ROOT / "results" / "aidev_recall_v6.json").read_text())["rows"] if r["readable"]}
    prs = {r["html_url"]: r for r in json.loads((R.CACHE / "pull_request.json").read_text())}
    commits = collections.defaultdict(list)
    for r in json.loads((R.CACHE / "commit_details.json").read_text()):
        commits[r["pr_id"]].append({k: r.get(k) for k in ("sha", "filename", "status", "patch")})
    links = {r["pr_id"]: r["issue_id"] for r in json.loads((R.CACHE / "related_issue.json").read_text())}
    issues = {r["id"]: r for r in json.loads((R.CACHE / "issue.json").read_text())}
    by = collections.OrderedDict()
    for c in cases:
        if c["comment_id"] not in readable:
            continue
        pr = prs[R.html_url(c["pull_request_url"])]
        key = (pr["html_url"], c["original_commit_id"])
        if key not in by:
            files = R.net_files(commits.get(pr["id"], []), c["original_commit_id"])
            u = pr["html_url"].split("/")
            by[key] = {"task": R.task_text(issues.get(links.get(pr["id"])), pr)[0], "files": files, "repo": f"{u[3]}/{u[4]}", "cases": []}
        by[key]["cases"].append(c)
    return by


def add_questions(path: pathlib.Path) -> dict:
    """Exploratory, chosen after the registered numbers were read: how many questions a person would answer. Itemator asks
    one per extra (a mass change is one extra however many files it holds); each rival file is counted as one question,
    which can only flatter the rivals. Itemator's rules are re-run; the rivals are not."""
    d = json.loads(path.read_text())
    snaps = snapshots()
    for x in d["snapshots"]:
        s = snaps[(x["pr"], x["sha"])]
        x["itemator_questions"] = len(X.analyse(s["task"], s["files"], repo=s["repo"], version=6).extras)
    d["exploratory_questions"] = {"note": add_questions.__doc__.split("\n\n")[0].replace("\n    ", " "),
                                  "itemator": sum(x["itemator_questions"] for x in d["snapshots"]),
                                  "overreach": d["summary"]["tools"]["overreach"]["files_named"],
                                  "scope_creep_detector": d["summary"]["tools"]["scope_creep_detector"]["files_named"]}
    path.write_text(json.dumps(d, indent=1) + "\n")
    return d["exploratory_questions"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--overreach")
    ap.add_argument("--scd")
    ap.add_argument("--limit", type=int, default=0, help="first N snapshots only (a smoke run; never the result)")
    ap.add_argument("--out", default=str(ROOT / "results" / "head_to_head_v1.json"))
    ap.add_argument("--questions", action="store_true", help="only add the exploratory question counts to --out")
    a = ap.parse_args(argv)
    if a.questions:
        print(json.dumps(add_questions(pathlib.Path(a.out))))
        return 0
    env = {"PATH": os.environ["PATH"], "OVERREACH_TELEMETRY": "0"}
    rows, snaps = [], []
    with tempfile.TemporaryDirectory() as tmp:
        env["HOME"] = tmp
        items = list(snapshots().items())[: a.limit or None]
        for i, ((url, sha), s) in enumerate(items):
            diff = pathlib.Path(tmp) / "change.diff"
            diff.write_text(unified_diff(s["files"]))
            o = run_json([a.overreach, "-p", s["task"], "--diff", str(diff), "--json", "--no-cache"], env)
            d = run_json([sys.executable, "-I", a.scd, "--diff", str(diff), "--intent", s["task"], "--json"], env)
            named = {"itemator": itemator_named(s["task"], s["files"], s["repo"]), "overreach": overreach_named(o), "scope_creep_detector": scd_named(d)}
            advice = overreach_advice(o)
            snaps.append({"pr": url, "sha": sha, "changed": sum(1 for f in s["files"] if f["filename"]), "named": {t: len(v) for t, v in named.items()},
                          "overreach_advice": len(advice), "errors": {"overreach": o is None, "scope_creep_detector": d is None}})
            for c in s["cases"]:
                rows.append({"comment_id": c["comment_id"], "pr": url, "path": c["path"],
                             "named": {t: c["path"] in v for t, v in named.items()}, "overreach_advice": c["path"] in advice})
            if (i + 1) % 50 == 0:
                print(f"{i + 1}/{len(items)}", file=sys.stderr)
    out = {"rubric": "eval/head_to_head_rubric.json", "limit": a.limit or None, "summary": summarize(rows, snaps),
           "overreach_advice_cases": sum(r["overreach_advice"] for r in rows), "snapshots": snaps, "rows": rows}
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
