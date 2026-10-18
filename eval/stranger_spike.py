"""Stranger-file trial, pre-registered in eval/stranger_spike_rubric.json: of the files human reviewers called out of
scope on agent pull requests (the 710 comments of eval/aidev_recall_cases.json), is the commented file more often one
that has never changed together with the other files of the pull request (itemator/cochange.py) than the other files
are? Reads each file's earlier history through read-only GitHub GETs (`gh api`), cached in eval/cache/stranger
(gitignored). The result holds ids, paths and labels only.

usage: python3 eval/stranger_spike.py [--out results/stranger_spike_v1.json]"""
from __future__ import annotations

import argparse, collections, hashlib, json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
from itemator import cochange as C  # noqa: E402
import aidev_recall as A  # noqa: E402
import replay_gitlab as G  # noqa: E402

CACHE = ROOT / "eval" / "cache" / "stranger"
MAX_FILES = 40                # modified files per pull request; larger ones are counted apart and not read


# ---------------------------------------------------------------- pure parts (tests/test_stranger_spike.py)

def row_for(case: dict, pr_url: str, modified: list[str] | None, histories: dict[str, list[str]] | None) -> dict:
    """One distinct commented file of one pull request. `modified`: the pull request's modified files when the comment
    was made (None when unreadable); `histories`: their earlier commit ids (None when GitHub would not say)."""
    row = {"comment_id": case["comment_id"], "pr": pr_url, "path": case["path"], "status": None, "label": None,
           "others": {C.STRANGER: 0, C.PARTNERED: 0}}
    if modified is None:
        return dict(row, status="unreadable")
    if case["path"] not in modified:
        return dict(row, status="not_modified")        # added, removed or renamed: it has no earlier history to read
    if len(modified) > MAX_FILES:
        return dict(row, status="too_many_files")
    if histories is None:
        return dict(row, status="history_unavailable")
    labels = C.strangers(histories)
    row["label"] = labels[case["path"]]
    row["status"] = "read"
    for f, lab in labels.items():
        if f != case["path"] and lab in row["others"]:
            row["others"][lab] += 1
    return row


def wilson(k: int, n: int):
    return G.wilson(k, n) if n else None


def summarize(rows: list[dict]) -> dict:
    read = [r for r in rows if r["status"] == "read"]
    eligible = [r for r in read if r["label"] in (C.STRANGER, C.PARTNERED)]
    cs = sum(r["label"] == C.STRANGER for r in eligible)
    os_ = sum(r["others"][C.STRANGER] for r in eligible)
    on = sum(r["others"][C.STRANGER] + r["others"][C.PARTNERED] for r in eligible)
    singled = sum(r["label"] == C.STRANGER and r["others"][C.STRANGER] == 0 for r in eligible)
    flagged = [(r["others"][C.STRANGER] + (r["label"] == C.STRANGER)) / (1 + r["others"][C.STRANGER] + r["others"][C.PARTNERED]) for r in eligible]
    return {"commented_files": len(rows), "by_status": dict(collections.Counter(r["status"] for r in rows)),
            "by_label": dict(collections.Counter(r["label"] for r in read)),
            "eligible_pull_requests": len({r["pr"] for r in eligible}), "eligible_commented_files": len(eligible),
            "commented_files_that_are_strangers": {"k": cs, "n": len(eligible), "wilson95": wilson(cs, len(eligible))},
            "other_files_that_are_strangers": {"k": os_, "n": on, "wilson95": wilson(os_, on)},
            "strangers_singled_out": {"k": singled, "n": len(eligible), "wilson95": wilson(singled, len(eligible))},
            "mean_share_of_files_flagged_per_pull_request": round(sum(flagged) / len(flagged), 4) if flagged else None}


# ---------------------------------------------------------------- network (GitHub GETs through gh; cached)

def history(repo: str, path: str, until: str) -> list[str] | None:
    """Ids of up to 100 commits that touched `path` before `until`, newest first; None when GitHub will not say."""
    args = ["gh", "api", "-X", "GET", f"repos/{repo}/commits", "-f", f"path={path}", "-f", f"until={until}", "-f", "per_page=100", "--jq", "[.[].sha]"]
    f = CACHE / (hashlib.sha1("\0".join(args).encode()).hexdigest() + ".json")
    if f.exists():
        return json.loads(f.read_text())
    for i in range(4):
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode == 0:
            CACHE.mkdir(parents=True, exist_ok=True)
            f.write_text(r.stdout.strip() or "[]")
            return json.loads(f.read_text())
        if "HTTP 4" in r.stderr and "403" not in r.stderr and "429" not in r.stderr:
            return None                                       # 404/409/422: gone or empty; waiting will not help
        time.sleep(60 if i else 20)
    return None


def created_at(urls: list[str]) -> dict[str, str]:
    import duckdb                                             # only here, so the unit tests need nothing beyond pytest
    con = duckdb.connect()
    q = ",".join("'" + u.replace("'", "''") + "'" for u in urls)
    pq = ROOT / "eval/cache/aidev/parquet/hao-li_AIDev__pull_request.parquet"
    return {u: str(t).replace(" ", "T").split("+")[0].split(".")[0] + "Z"
            for u, t in con.execute(f"SELECT html_url, created_at FROM read_parquet('{pq}') WHERE html_url IN ({q})").fetchall()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "stranger_spike_v1.json"))
    a = ap.parse_args(argv)
    cases = json.loads(A.CASES.read_text())["comments"]
    urls = sorted({A.html_url(c["pull_request_url"]) for c in cases})
    prs = {r["html_url"]: r for r in A.cached("pull_request.json", lambda: [])}
    ids = {p["id"] for p in prs.values()}
    commits = collections.defaultdict(list)
    for r in A.cached("commit_details.json", lambda: []):
        if r["pr_id"] in ids:
            commits[r["pr_id"]].append({k: r.get(k) for k in ("sha", "filename", "status", "patch")})
    when = created_at(urls)
    rows, seen = [], set()
    for c in cases:
        url = A.html_url(c["pull_request_url"])
        if (url, c["path"]) in seen:
            continue
        seen.add((url, c["path"]))
        pr = prs.get(url)
        files = A.net_files(commits.get(pr["id"], []), c["original_commit_id"]) if pr else None
        modified = [f["filename"] for f in files if f["status"] == "modified"] if files is not None else None
        hist = None
        if modified is not None and c["path"] in modified and len(modified) <= MAX_FILES and url in when:
            repo = "/".join(url.split("/")[3:5])
            got = {p: history(repo, p, when[url]) for p in modified}
            hist = None if any(v is None for v in got.values()) else got
        rows.append(row_for(c, url, modified, hist))
        if len(rows) % 25 == 0:
            print(f"{len(rows)} commented files", file=sys.stderr)
    out = {"rubric": "eval/stranger_spike_rubric.json", "summary": summarize(rows), "rows": rows}
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
