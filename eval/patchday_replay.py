"""The patch-day replay (eval/patchday_rubric.json, pushed in 88634f5 before any pull request was read): on every
public agent pull request in AIDev that names a CVE, does patch-day mode switch on, and which files would it ask about?
Reads data/*.parquet and the dataset's pr_commit_details rows through its API, GET only.

usage: python3 eval/patchday_replay.py [--out results/patchday_replay_v1.json]"""
from __future__ import annotations

import argparse, collections, concurrent.futures, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from itemator import after, patchday as P, scope as S  # noqa: E402
import aidev_recall as A  # noqa: E402

DATA = ROOT / "data"


def judge(task: str, files: list | None) -> dict:
    """One pull request's row: switched on, or the rubric's reason it did not."""
    if files is None:
        return {"switched_on": False, "why_not": "unreadable"}
    found = P.cves(task)
    if not found:
        return {"cves": [], "switched_on": False, "why_not": "no_cve_in_task_text"}
    if S.read(task) is not None:
        return {"cves": list(found), "switched_on": False, "why_not": "own_scope_block"}
    s = P.derive(task, files)
    if s is None:
        return {"cves": list(found), "switched_on": False, "why_not": "no_version_only_file"}
    a, _ = after.analyse(task, files)
    return {"cves": list(found), "switched_on": True, "why_not": None, "fix_files": list(s.paths),
            "asked_files": sorted({e.path for e in a.extras})}


def summarise(rows: list, rubric: dict) -> dict:
    on = [r for r in rows if r["switched_on"]]
    reasons = collections.Counter(r["why_not"] for r in rows if not r["switched_on"])
    asked = sum(len(r["asked_files"]) for r in on)
    key = "some" if on else "none"
    top = reasons.most_common(1)[0][0].replace("_", " ") if reasons else "nothing"
    return {"pull_requests": len(rows), "switched_on": len(on), "asked_files": asked, "why_not": dict(reasons),
            "sentence": rubric["sentences"][key].format(on=len(on), n=len(rows), asked=asked, top_reason=top)}


def population() -> list:
    import duckdb
    q = duckdb.connect()
    prs = q.execute(f"SELECT CAST(id AS BIGINT), html_url, agent, title, body, merged_at FROM read_parquet('{DATA}/pull_request.parquet') "
                    "WHERE regexp_matches(coalesce(title,'') || ' ' || coalesce(body,''), 'CVE-\\d{4}-\\d{4,}', 'i') ORDER BY 1").fetchall()
    links = dict(q.execute(f"SELECT CAST(pr_id AS BIGINT), CAST(issue_id AS BIGINT) FROM read_parquet('{DATA}/related_issue.parquet')").fetchall())
    ids = [links[p[0]] for p in prs if p[0] in links]
    issues = {i: {"title": t, "body": b} for i, t, b in q.execute(
        f"SELECT CAST(id AS BIGINT), title, body FROM read_parquet('{DATA}/issue.parquet') WHERE id = ANY(?)", [ids]).fetchall()} if ids else {}
    return [{"id": p[0], "url": p[1], "agent": p[2], "merged": p[5] is not None,
             "task": A.task_text(issues.get(links.get(p[0])), {"title": p[3], "body": p[4]})[0]} for p in prs]


def files_by_pr(ids: list) -> dict:
    """{pr_id: net files of its last commit, or None}: the dataset's pr_commit_details rows through its API, five
    queries at a time, GET only."""
    def one(i):
        for _ in range(3):                  # the API answers 500 at times; three tries, then the pull request is unreadable
            try:
                return [{k: r.get(k) for k in ("sha", "filename", "status", "patch")}
                        for r in A.rows_where("hao-li/AIDev", "pr_commit_details", f'"pr_id"={int(i)}')]
            except RuntimeError:
                continue
        return None
    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        rows = dict(zip(ids, pool.map(one, ids)))
    return {i: A.net_files(rows[i], list(dict.fromkeys(r["sha"] for r in rows[i]))[-1]) if rows.get(i) else None
            for i in ids}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "patchday_replay_v1.json"))
    a = ap.parse_args(argv)
    rubric = json.loads((ROOT / "eval" / "patchday_rubric.json").read_text())
    prs = population()
    files = files_by_pr([p["id"] for p in prs])
    rows = [dict({"url": p["url"], "agent": p["agent"], "merged": p["merged"]}, **judge(p["task"], files[p["id"]])) for p in prs]
    out = {"rubric": "eval/patchday_rubric.json (88634f5)", "summary": summarise(rows, rubric), "rows": rows}
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
