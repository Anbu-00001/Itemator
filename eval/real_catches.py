"""Leg 3 of the "does Itemator catch real problems" work (eval/real_catches_rubric.json, registered before any outcome was
read): for each file where the frozen rules (v6) listed an extra and a human reviewer had commented on the same file
(results/aidev_recall_v6.json, leg 1), did the file land in the pull request? Read-only: GET requests through `gh api`;
nothing is posted. Comment text is never stored; results hold ids, paths and counts.

usage (repository root):
    python3 eval/real_catches.py            # reads GitHub, writes results/real_catches_v1.json
    python3 eval/real_catches.py --labels eval/real_catches_labels.json   # adds my reading of each comment (yes/no/unclear)"""
from __future__ import annotations

import argparse, collections, json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import aidev_recall as A  # noqa: E402

LEG1 = ROOT / "results" / "aidev_recall_v6.json"
OUT = ROOT / "results" / "real_catches_v1.json"


# ---------------------------------------------------------------- pure parts (tests/test_real_catches.py)

def pr_parts(url: str) -> tuple[str, str, int]:
    """`https://github.com/o/r/pull/N` -> (o, r, N)."""
    owner, repo, kind, num = url.rstrip("/").split("github.com/", 1)[1].split("/")[:4]
    assert kind == "pull", url
    return owner, repo, int(num)


def pairs(rows: list) -> list[dict]:
    """Distinct (pull request, path) pairs among the rows the rules listed (hit), in a stable order, each with the ids of
    its comments, the agent, the kind of file and the dataset's state."""
    out: dict = {}
    for r in rows:
        if not r.get("hit"):
            continue
        p = out.setdefault((r["pr"], r["path"]), {"pr": r["pr"], "path": r["path"], "agent": r["agent"], "kind": r["kind"],
                                                 "state_in_dataset": r["state"], "comment_ids": []})
        p["comment_ids"].append(r["comment_id"])
    return [out[k] for k in sorted(out)]


def classify(pr: dict, files: list, path: str) -> str:
    """closed_unmerged, file_removed or landed_with_the_file (rubric precedence). `pr`: {state, merged}; `files`: the pull
    request's final file list ({filename, previous_filename?})."""
    if pr.get("state") == "closed" and not pr.get("merged"):
        return "closed_unmerged"
    present = any(f.get("filename") == path or f.get("previous_filename") == path for f in files)
    return "landed_with_the_file" if present else "file_removed"


def changed_after(commit_dates: list, comment_created_at: str) -> bool:
    """At least one commit dated strictly later than the comment (ISO 8601 UTC strings compare as text)."""
    return any(d and d > comment_created_at for d in commit_dates)


def summarize(cases: list, labels: dict | None = None) -> dict:
    """Counts first, then the share that did not land with its Wilson interval. `cases`: {outcome, changed_after_comment,
    agent, kind, key, unreadable?}. `labels`: {key: yes|no|unclear}, the model's reading, optional."""
    read = [c for c in cases if not c.get("unreadable")]
    n = len(read)
    cnt = collections.Counter(c["outcome"] for c in read)
    not_landed = cnt["file_removed"] + cnt["closed_unmerged"]
    out = {"pairs": len(cases), "unreadable": len(cases) - n, "read": n,
           "file_removed": cnt["file_removed"], "closed_unmerged": cnt["closed_unmerged"],
           "landed_with_the_file": cnt["landed_with_the_file"], "did_not_land": not_landed,
           "share_did_not_land": round(not_landed / n, 4) if n else None,
           "wilson95": A.G.wilson(not_landed, n) if n else None,
           "changed_after_comment": sum(1 for c in read if c["changed_after_comment"]),
           "by_agent": {a: _by(read, lambda c, a=a: c["agent"] == a) for a in sorted({c["agent"] for c in read})},
           "by_kind": {str(k): _by(read, lambda c, k=k: str(c["kind"]) == k) for k in sorted({str(c["kind"]) for c in read})}}
    if labels is not None:
        lab = {c["key"]: labels.get(c["key"], "unlabelled") for c in read}
        out["my_reading"] = {"counts": dict(collections.Counter(lab.values())),
                             "asks_removal_yes": _by(read, lambda c: lab[c["key"]] == "yes")}
    return out


def _by(read: list, pred) -> dict:
    sel = [c for c in read if pred(c)]
    cnt = collections.Counter(c["outcome"] for c in sel)
    return {"pairs": len(sel), "file_removed": cnt["file_removed"], "closed_unmerged": cnt["closed_unmerged"],
            "landed_with_the_file": cnt["landed_with_the_file"]}


# ---------------------------------------------------------------- reading GitHub (network)

def gh(path: str, retries: int = 4):
    last = ""
    for i in range(retries):
        r = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=90)
        if r.returncode == 0:
            return json.loads(r.stdout)
        last = (r.stderr or r.stdout).strip()[:200]
        if "404" in last or "410" in last:
            break
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"{path}: {last}")


def all_pages(path: str) -> list:
    out, page = [], 1
    while True:
        chunk = gh(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        out += chunk
        if len(chunk) < 100:
            return out
        page += 1


def read_pair(p: dict) -> dict:
    owner, repo, n = pr_parts(p["pr"])
    base = {"key": f"{p['pr']}#{p['path']}", "pr": p["pr"], "path": p["path"], "agent": p["agent"], "kind": p["kind"]}
    try:
        pr = gh(f"repos/{owner}/{repo}/pulls/{n}")
        files = all_pages(f"repos/{owner}/{repo}/pulls/{n}/files")
        commits = all_pages(f"repos/{owner}/{repo}/pulls/{n}/commits")
        comments = [gh(f"repos/{owner}/{repo}/pulls/comments/{cid}") for cid in p["comment_ids"]]
    except RuntimeError as e:
        return dict(base, unreadable=True, reason=str(e)[:160])
    first = min(c["created_at"] for c in comments)
    dates = [((c.get("commit") or {}).get("committer") or {}).get("date") for c in commits]
    return dict(base, unreadable=False, state=pr["state"], merged=bool(pr.get("merged")), comment_created_at=first,
                human_comment=all(c["user"]["type"] == "User" and c["path"] == p["path"] for c in comments),
                outcome=classify(pr, files, p["path"]), changed_after_comment=changed_after(dates, first))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", help="JSON {pair key: yes|no|unclear}: my reading of each comment, optional")
    a = ap.parse_args(argv)
    rows = json.loads(LEG1.read_text())["rows"]
    ps = pairs(rows)
    cases = [read_pair(p) for p in ps]
    labels = json.loads(pathlib.Path(a.labels).read_text()) if a.labels else None
    res = {"rubric": "eval/real_catches_rubric.json", "read_on": time.strftime("%Y-%m-%d", time.gmtime()),
           "summary": summarize(cases, labels),
           "cases": [{k: v for k, v in c.items() if k not in ("key",)} | {"key": c["key"]} for c in cases]}
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    s = res["summary"]
    print(json.dumps({k: s[k] for k in ("pairs", "unreadable", "file_removed", "closed_unmerged", "landed_with_the_file",
                                         "did_not_land", "share_did_not_land", "wilson95", "changed_after_comment")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
