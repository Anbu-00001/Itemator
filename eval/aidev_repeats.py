"""The repeat-question study (eval/aidev_repeats_rubric.json, registered before it ran): of the questions the frozen rules would ask
on public AI-agent pull requests, how many are about a file the same repository was already asked about in an earlier one?
Those are what an `always` answer the first time would have skipped. Read-only; runs in the manual CI job `repeats-study`.

usage: python3 eval/aidev_repeats.py --commit-details PARQUET [--limit N]"""
from __future__ import annotations

import argparse, collections, json, math, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

OUT = ROOT / "results" / "aidev_repeats_v1.json"
NONE_BELOW = 0.02


# ---------------------------------------------------------------- pure parts (tests/test_aidev_repeats.py)

def wilson(k: int, n: int) -> list:
    if not n:
        return [0.0, 0.0]
    p, z = k / n, 1.96
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(c - h, 4), round(c + h, 4)]


def tally(prs: list) -> dict:
    """`prs`: {id, repo, created_at, agent, questions: [[kind, path], ...]} for readable pull requests. A question repeats when an
    earlier pull request of the same repository asked about the same path (by kind for the looser count)."""
    by_repo = collections.defaultdict(list)
    for p in prs:
        by_repo[p["repo"]].append(p)
    q = rep_path = rep_kind = silenced = 0
    agents = collections.defaultdict(lambda: [0, 0])
    asked_repos = 0
    for rows in by_repo.values():
        rows.sort(key=lambda r: (r["created_at"] or "", r["id"]))
        paths, kinds, asked = set(), set(), 0
        for r in rows:
            qs = r["questions"]
            if not qs:
                continue
            asked += 1
            hits = [path in paths for _, path in qs]
            q += len(qs)
            rep_path += sum(hits)
            rep_kind += sum(kind in kinds for kind, _ in qs)
            silenced += all(hits)
            agents[r["agent"]][0] += len(qs)
            agents[r["agent"]][1] += sum(hits)
            paths |= {path for _, path in qs}
            kinds |= {kind for kind, _ in qs}
        asked_repos += asked >= 2
    share = round(rep_path / q, 4) if q else 0.0
    return {"pull_requests": len(prs), "questions": q, "repeats": rep_path, "share": share, "wilson95": wilson(rep_path, q),
            "repeats_by_kind": rep_kind, "share_by_kind": round(rep_kind / q, 4) if q else 0.0,
            "pull_requests_with_questions": sum(1 for p in prs if p["questions"]), "cards_not_posted": silenced,
            "repositories_asked_twice_or_more": asked_repos,
            "by_agent": {a: {"questions": n, "repeats": k, "share": round(k / n, 4) if n else 0.0} for a, (n, k) in sorted(agents.items())}}


def sentence(s: dict, rubric: dict) -> str:
    key = "none" if s["share"] < NONE_BELOW else "any"
    return rubric["sentences"][key].format(repeats=f"{s['repeats']:,}", questions=f"{s['questions']:,}", share=f"{s['share']:.0%}")


# ---------------------------------------------------------------- the run (network and dataset files)

def shard_ids(ids: list, shard: str | None) -> list:
    """`shard` "i/n" keeps every n-th id from the i-th (amendment 2); None keeps all."""
    if not shard:
        return ids
    i, n = (int(x) for x in shard.split("/"))
    return ids[i::n]


def merge(parts: list) -> tuple:
    """Rows and counts of every shard's file, for one tally."""
    rows = [r for p in parts for r in p["rows"]]
    return rows, {k: sum(p[k] for p in parts) for k in ("with_file_rows", "unreadable")}, parts[0]["table_rows"] if parts else 0


def run(commit_details: str, limit: int | None = None, size: int = 4000, shard: str | None = None) -> dict:
    import aidev_local
    import aidev_recall as A
    import aidev_revert as R
    from itemator import extras as X
    import duckdb
    prs = {p["id"]: p for p in R.pull_requests()}
    with_rows = {int(r[0]) for r in duckdb.connect().execute(
        "SELECT DISTINCT CAST(pr_id AS BIGINT) FROM read_parquet(?)", [str(commit_details)]).fetchall()}   # amendment 1
    ids = sorted(i for i in prs if i in with_rows)
    ids = ids[:limit] if limit else ids
    ids = shard_ids(ids, shard)
    texts = {r["id"]: r for r in A.pq_rows("hao-li/AIDev", "pull_request", "id, html_url, title, body, CAST(created_at AS VARCHAR) AS created_at", "id", ids)}
    links = {r["pr_id"]: r["issue_id"] for r in A.pq_rows("hao-li/AIDev-7.6M", "related_issue", "pr_id, issue_id", "pr_id", ids)}
    issues = {r["id"]: r for r in A.pq_rows("hao-li/AIDev-7.6M", "issue", "id, title, body", "id", sorted(set(links.values())))}
    rows, unreadable, t0 = [], 0, time.time()
    for start in range(0, len(ids), size):
        group = ids[start:start + size]
        local = aidev_local.commit_rows(commit_details, group)
        for pid in group:
            rs = local.get(pid) or []
            files = A.net_files(rs, rs[-1]["sha"]) if rs else None
            if not files:
                unreadable += 1
                continue
            t = texts.get(pid) or {}
            repo = "/".join((t.get("html_url") or "///").split("/")[3:5])
            res = X.analyse(A.task_text(issues.get(links.get(pid)), t)[0], files, repo=repo)
            rows.append({"id": pid, "repo": repo, "created_at": t.get("created_at"), "agent": prs[pid]["agent"],
                         "questions": [[e.kind, e.path] for e in res.extras]})
        print(f"{start + len(group)}/{len(ids)} pull requests, {round(time.time() - t0)} s", flush=True)
    if shard:
        return {"shard": shard, "table_rows": len(prs), "with_file_rows": len(ids), "unreadable": unreadable, "rows": rows}
    s = tally(rows)
    rubric = json.loads((ROOT / "eval" / "aidev_repeats_rubric.json").read_text())
    return {"rubric": "eval/aidev_repeats_rubric.json", "rules_version": X.RULES_VERSION, "table_rows": len(prs),
            "with_file_rows": len(ids), "unreadable": unreadable,
            "summary": s, "sentence": sentence(s, rubric)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit-details")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--shard", help="i/n: read one shard and write its rows (amendment 2)")
    ap.add_argument("--tally", nargs="+", help="shard row files to tally into the result")
    a = ap.parse_args(argv)
    if a.tally:
        rows, counts, table = merge([json.loads(pathlib.Path(f).read_text()) for f in a.tally])
        s = tally(rows)
        rubric = json.loads((ROOT / "eval" / "aidev_repeats_rubric.json").read_text())
        from itemator import extras as X
        out = {"rubric": "eval/aidev_repeats_rubric.json", "rules_version": X.RULES_VERSION, "table_rows": table, **counts,
               "shards": len(a.tally), "summary": s, "sentence": sentence(s, rubric)}
    elif a.shard:
        part = run(a.commit_details, a.limit, shard=a.shard)
        i = a.shard.split("/")[0]
        (ROOT / "results" / f"aidev_repeats_rows_{i}.json").write_text(json.dumps(part) + "\n")
        print(json.dumps({k: part[k] for k in ("shard", "with_file_rows", "unreadable")}))
        return 0
    else:
        out = run(a.commit_details, a.limit)
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("unreadable", "sentence")}), json.dumps(out["summary"])[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
