"""The base rate beside the real catches (eval/aidev_lift_rubric.json): in the same agent pull requests where a reviewer
wrote a scope comment, is a file the rules list more likely to draw that comment than a file they do not list? Reads
only the cache eval/aidev_recall.py built (eval/cache/aidev/); nothing is fetched or posted.

usage: python3 eval/aidev_lift.py [--out results/aidev_lift_v6.json]"""
from __future__ import annotations

import argparse, collections, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
from itemator import extras as X  # noqa: E402
import aidev_recall as R  # noqa: E402
import replay_gitlab as G  # noqa: E402


# ---------------------------------------------------------------- pure parts (tests/test_aidev_lift.py)

def earliest(comments: list, order: list) -> str | None:
    """The commit of the pull request's earliest case comment, by the pull request's commit order; None when none of
    the comments' commits is among them."""
    at = {sha: i for i, sha in enumerate(order)}
    known = [c["original_commit_id"] for c in comments if c["original_commit_id"] in at]
    return min(known, key=lambda s: at[s]) if known else None


def label(files: list, extras: list, objected_paths: set) -> list:
    """One row per file: is it listed, was it objected to, and its kind. Rows with no file name (the dataset has a few) are left out."""
    return [{"path": f["filename"], "listed": R.listed(extras, f["filename"]), "objected": f["filename"] in objected_paths,
             "kind": R.listable_kind(f["filename"])} for f in files if f["filename"]]


def shares(rows: list) -> dict:
    def one(rs):
        k, n = sum(r["objected"] for r in rs), len(rs)
        return {"files": n, "objected": k, "share": round(k / n, 4) if n else None, "wilson95": G.wilson(k, n)}
    lis, unl = one([r for r in rows if r["listed"]]), one([r for r in rows if not r["listed"]])
    ratio = round(lis["share"] / unl["share"], 2) if lis["share"] is not None and unl["share"] else None
    both = bool(lis["files"] and unl["files"])
    higher = both and lis["wilson95"][0] > unl["wilson95"][1]   # the rubric's headline_rule
    lower = both and lis["wilson95"][1] < unl["wilson95"][0]
    return {"listed": lis, "unlisted": unl, "ratio": ratio, "intervals_apart": higher or lower,
            "listed_clearly_higher": higher, "listed_clearly_lower": lower}


# ---------------------------------------------------------------- the run

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "aidev_lift_v6.json"))
    a = ap.parse_args(argv)
    cases = json.loads(R.CASES.read_text())["comments"]
    load = lambda n: json.loads((R.CACHE / n).read_text())
    prs = {r["html_url"]: r for r in load("pull_request.json")}
    commits = collections.defaultdict(list)
    for r in load("commit_details.json"):
        commits[r["pr_id"]].append({k: r.get(k) for k in ("sha", "filename", "status", "patch")})
    links = {r["pr_id"]: r["issue_id"] for r in load("related_issue.json")}
    issues = {r["id"]: r for r in load("issue.json")}
    by_pr = collections.defaultdict(list)
    for c in cases:
        by_pr[R.html_url(c["pull_request_url"])].append(c)
    rows, unreadable, per_pr = [], 0, []
    for url, cs in sorted(by_pr.items()):
        pr = prs.get(url)
        rs = commits.get(pr["id"], []) if pr else []
        order = list(dict.fromkeys(r["sha"] for r in rs))
        sha = earliest(cs, order)
        files = R.net_files(rs, sha) if sha else None
        if pr is None or files is None:
            unreadable += 1
            continue
        repo = "/".join(url.split("/")[3:5])
        task = R.task_text(issues.get(links.get(pr["id"])), pr)
        extras = X.analyse(task[0], files, repo=repo, version=6).extras
        got = label(files, extras, {c["path"] for c in cs})
        n_listed = sum(g["listed"] for g in got)
        for g in got:
            g.update(pr=url, agent=pr.get("agent"), pr_listed=n_listed)
        rows += got
        per_pr.append({"pr": url, "listed": sum(g["listed"] for g in got),
                       "listed_objected": any(g["listed"] and g["objected"] for g in got),
                       "unlisted_objected": any(not g["listed"] and g["objected"] for g in got)})
    with_listed = [p for p in per_pr if p["listed"]]
    summary = {"pull_requests": len(by_pr), "unreadable": unreadable, "readable": len(per_pr), "files": len(rows),
               "main": shares(rows),
               "same_kind": shares([r for r in rows if r["kind"]]),
               "per_pull_request": {"with_a_listed_file": len(with_listed),
                                    "listed_file_objected": sum(p["listed_objected"] for p in with_listed),
                                    "unlisted_file_objected": sum(p["unlisted_objected"] for p in with_listed)},
               "exploratory_not_registered": {
                   "why": "chosen after the main result was seen: two pull requests hold 1,065 of the 2,023 listed files (mass events), so the main shares mostly describe them",
                   "pull_requests_with_1_to_10_listed_files": shares([r for r in rows if 1 <= r["pr_listed"] <= 10])},
               "by_agent": {ag: shares([r for r in rows if r["agent"] == ag]) for ag in sorted({r["agent"] for r in rows}, key=str)}}
    out = {"rubric": "eval/aidev_lift_rubric.json (registered in commit 1902168 before scoring)", "rules_version": 6,
           "summary": summary,
           "rows": [{k: r[k] for k in ("pr", "path", "listed", "objected", "kind")} for r in rows if r["listed"] or r["objected"]]}
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: summary[k] for k in ("readable", "unreadable", "files", "main", "same_kind", "per_pull_request", "exploratory_not_registered")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
