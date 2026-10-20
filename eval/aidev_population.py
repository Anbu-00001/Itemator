"""The population run (eval/aidev_population_rubric.json, registered before it ran): over every pull request in AIDev's
pull_request table, would Itemator's frozen rules (v6) have opened a card, and with how many threads? A count of how often the
card would speak, not of whether it is right. Read-only; nothing is posted. Meant to run on the Hugging Face Space
(hf_runner/server.py, job `population`), where the dataset's parquet files are a download away.

usage: python3 eval/aidev_population.py --commit-details PARQUET [--limit N]"""
from __future__ import annotations

import argparse, collections, json, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
import aidev_local  # noqa: E402
import aidev_recall as A  # noqa: E402
import aidev_revert as R  # noqa: E402

OUT = ROOT / "results" / "aidev_population_v6.json"
BUCKETS = ("0", "1", "2", "3 to 5", "6 or more")


# ---------------------------------------------------------------- pure parts (tests/test_aidev_population.py)

def bucket(n: int) -> str:
    return "0" if n == 0 else "1" if n == 1 else "2" if n == 2 else "3 to 5" if n <= 5 else "6 or more"


def part(rows: list) -> dict:
    """Share with at least one extra, with its Wilson interval, over the readable rows."""
    n = len(rows)
    k = sum(1 for r in rows if r["n"] > 0)
    return {"pull_requests": n, "with_an_extra": k, "share": round(k / n, 4) if n else None, "wilson95": A.G.wilson(k, n) if n else None}


def summarize(rows: list) -> dict:
    """`rows`: {id, agent, state, task_from, readable, n (listed extras), kinds}. Unreadable rows are counted apart."""
    ok = [r for r in rows if r["readable"]]
    threads = collections.Counter(bucket(r["n"]) for r in ok)
    by = lambda key: {str(v): part([r for r in ok if r[key] == v]) for v in sorted({r[key] for r in ok}, key=str)}
    return {"pull_requests": len(rows), "unreadable": len(rows) - len(ok), "readable": len(ok),
            "unreadable_with_api_error": sum(1 for r in rows if r.get("api_error")),
            "overall": part(ok),
            "threads": {b: threads.get(b, 0) for b in BUCKETS},
            "with_three_or_more": {"pull_requests": sum(threads.get(b, 0) for b in BUCKETS[3:]),
                                   "share": round(sum(threads.get(b, 0) for b in BUCKETS[3:]) / len(ok), 4) if ok else None},
            "most_threads_on_one_pull_request": max((r["n"] for r in ok), default=0),
            "by_agent": by("agent"), "by_state": by("state"), "by_task": by("task_from"),
            "extras_by_kind": dict(collections.Counter(k for r in ok for k in r["kinds"])),
            "no_linked_issue": sum(1 for r in ok if r["task_from"] != "linked_issue")}


def chunks(ids: list, size: int):
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


# ---------------------------------------------------------------- the run

def run(commit_details: str, limit: int | None = None, size: int = 4000) -> dict:
    prs = {p["id"]: p for p in R.pull_requests()}
    ids = sorted(prs)[:limit] if limit else sorted(prs)
    texts = {r["id"]: r for r in A.pq_rows("hao-li/AIDev", "pull_request", "id, html_url, title, body", "id", ids)}
    links = {r["pr_id"]: r["issue_id"] for r in A.pq_rows("hao-li/AIDev-7.6M", "related_issue", "pr_id, issue_id", "pr_id", ids)}
    issues = {r["id"]: r for r in A.pq_rows("hao-li/AIDev-7.6M", "issue", "id, title, body", "id", sorted(set(links.values())))}
    rows, t0 = [], time.time()
    for n, group in enumerate(chunks(ids, size)):
        local = aidev_local.commit_rows(commit_details, group)
        for pid in group:
            t = texts.get(pid) or {}
            repo = "/".join((t.get("html_url") or "///").split("/")[3:5])
            task = A.task_text(issues.get(links.get(pid)), t)
            r = R.score_or_error(prs[pid], lambda: local.get(pid, []), task, repo)
            rows.append({"id": pid, "agent": r["agent"], "state": r["state"], "task_from": r["task_from"], "readable": r["readable"],
                         "n": r.get("n", 0), "kinds": r.get("kinds_all", []), "api_error": r.get("api_error", False)})
        print(f"{len(rows)}/{len(ids)} pull requests, {round(time.time() - t0)} s", flush=True)
    return {"rubric": "eval/aidev_population_rubric.json", "rules_version": R.X.RULES_VERSION, "summary": summarize(rows)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit-details", required=True)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    out = run(a.commit_details, a.limit)
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    s = out["summary"]
    print(json.dumps({k: s[k] for k in ("pull_requests", "unreadable", "overall", "threads", "with_three_or_more")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
