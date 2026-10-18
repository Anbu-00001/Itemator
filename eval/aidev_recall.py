"""Leg 1 of the "does it catch real problems" work (eval/aidev_recall_rubric.json): of the human reviewers' scope
comments on AI-agent pull requests in the public AIDev dataset, how often did Itemator's rules list the file the
reviewer was talking about? Everything is read from the dataset's public API (read-only); nothing is posted. Comment
text and patches stay in eval/cache/ (gitignored); results hold ids, paths, kinds and yes/no only.

usage: python3 eval/aidev_recall.py [--rules 6] [--out results/aidev_recall_v6.json]"""
from __future__ import annotations

import argparse, collections, concurrent.futures, hashlib, json, pathlib, re, sys, time, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
from itemator import extras as X  # noqa: E402
import replay_gitlab as G  # noqa: E402

CASES = ROOT / "eval" / "aidev_recall_cases.json"
CACHE = ROOT / "eval" / "cache" / "aidev"
API = "https://datasets-server.huggingface.co/filter"


# ---------------------------------------------------------------- pure parts (tests/test_aidev_recall.py)

def listable_kind(path: str) -> str | None:
    """The kind of file the rules can list on its own, from its path alone; None for source, tests and docs."""
    if X._manifest_kind(path):
        return "dependency"
    if X.is_agent_instructions(path):
        return "agent_instructions"
    if X._config_kind(path):
        return "ci_or_config"
    if X.is_generated(path):
        return "generated"
    ext = X._ext(path)
    if ext and ext not in X._TEXT_EXT:
        return "binary"
    return None


def listed(extras: list, path: str) -> bool:
    """An extra names the file itself, or a directory (path ending in /) that holds it, or a mass event's file list."""
    for e in extras:
        names = [e.path] + [d for d in (e.detail or ()) if isinstance(d, str)]
        if any(n == path or (n.endswith("/") and path.startswith(n)) for n in names if n):
            return True
    return False


def net_files(rows: list, upto_sha: str) -> list | None:
    """`rows`: one PR's commit-file rows in commit order ({sha, filename, status, patch}). The files as they stood up to
    and including `upto_sha`: a file added and later removed vanishes, one removed stays removed, one added stays added;
    patches of several commits are joined in order. None when the commit is not among the rows."""
    if not any(r["sha"] == upto_sha for r in rows):
        return None
    by, order, seen = {}, [], False
    for r in rows:
        if seen and r["sha"] != upto_sha:
            break
        seen = seen or r["sha"] == upto_sha
        f = by.get(r["filename"])
        if f is None:
            f = by[r["filename"]] = {"filename": r["filename"], "first": r["status"], "last": r["status"], "patch": []}
            order.append(r["filename"])
        f["last"] = r["status"]
        if r.get("patch"):
            f["patch"].append(r["patch"])
    out = []
    for name in order:
        f = by[name]
        if f["first"] == "added" and f["last"] == "removed":
            continue
        status = "removed" if f["last"] == "removed" else "added" if f["first"] == "added" else "modified"
        out.append({"filename": name, "status": status, "patch": "\n".join(f["patch"]) or None})
    return out


def task_text(issue: dict | None, pr: dict) -> tuple[str, str]:
    """The task the rules compare the change with: the linked issue's title and text, else the pull request's own."""
    if issue and (issue.get("title") or issue.get("body")):
        return f"{issue.get('title') or ''}\n{issue.get('body') or ''}", "linked_issue"
    return f"{pr.get('title') or ''}\n{pr.get('body') or ''}", "pr_text"


def score(case: dict, files: list | None, task: tuple[str, str], pr: dict, repo: str, version: int) -> dict:
    row = {"comment_id": case["comment_id"], "pr": pr["html_url"], "agent": pr.get("agent"), "state": pr_state(pr),
           "path": case["path"], "kind": listable_kind(case["path"]), "task_from": task[1]}
    if files is None:
        return dict(row, readable=False, hit=None, hit_title_only=None)
    full = X.analyse(task[0], files, repo=repo, version=version)
    title = X.analyse(task[0].split("\n", 1)[0], files, repo=repo, version=version)
    return dict(row, readable=True, hit=listed(full.extras, case["path"]), hit_title_only=listed(title.extras, case["path"]))


def pr_state(pr: dict) -> str:
    return "merged" if pr.get("merged_at") else (pr.get("state") or "unknown")


def share(rows: list, key: str = "hit") -> dict:
    n = sum(r[key] is not None for r in rows)
    k = sum(bool(r[key]) for r in rows)
    return {"comments": n, "listed": k, "wilson95": G.wilson(k, n)}


def summarize(rows: list) -> dict:
    readable = [r for r in rows if r["readable"]]
    group = lambda f: {str(k): share([r for r in readable if f(r) == k]) for k in sorted({f(r) for r in readable}, key=str)}
    prs = collections.defaultdict(lambda: {"comments": 0, "listed": 0})
    for r in readable:
        prs[r["pr"]]["comments"] += 1
        prs[r["pr"]]["listed"] += bool(r["hit"])
    kinds = [r for r in readable if r["kind"]]
    return {"comments": len(rows), "unreadable": len(rows) - len(readable), "all": share(readable),
            "on_a_listable_kind": share(kinds), "on_other_files": share([r for r in readable if not r["kind"]]),
            "by_kind": group(lambda r: r["kind"]), "by_agent": group(lambda r: r["agent"]), "by_state": group(lambda r: r["state"]),
            "by_task": group(lambda r: r["task_from"]),
            "title_only_all": share(readable, "hit_title_only"), "title_only_on_a_listable_kind": share(kinds, "hit_title_only"),
            "pull_requests": {"with_a_comment": len(prs), "with_a_listed_comment": sum(p["listed"] > 0 for p in prs.values())}}


# ---------------------------------------------------------------- network (the dataset's public API; cached)

def api(dataset: str, config: str, where: str, offset: int = 0, length: int = 100) -> dict:
    q = urllib.parse.urlencode({"dataset": dataset, "config": config, "split": "train", "where": where, "offset": offset, "length": length})
    page = CACHE / "pages" / (hashlib.sha1(q.encode()).hexdigest() + ".json")      # a page read once is never read again
    if page.exists():
        return json.loads(page.read_text())
    err = None
    for i in range(12):
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "Mozilla/5.0"}), timeout=90) as r:
                d = json.load(r)
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(json.dumps(d))
            return d
        except Exception as e:           # the API answers 502 now and then: wait and retry
            err = e
            time.sleep(min(60, 5 * (i + 1)))
    raise RuntimeError(f"{config}: {err}")


def rows_where(dataset: str, config: str, where: str) -> list:
    out, off = [], 0
    while True:
        d = api(dataset, config, where, off)
        out += [r["row"] for r in d["rows"]]
        off += 100
        if off >= d["num_rows_total"]:
            return out


def in_batches(dataset: str, config: str, column: str, values: list, size: int, quote: bool = False) -> list:
    """One equality query per value (the API answers 422 to IN lists), five at a time: the API answers in 0.4 to 46 seconds.
    Results come back in the order of `values`. `size` is kept so the callers read the same."""
    def one(v):
        lit = "'" + str(v).replace("'", "''") + "'" if quote else str(int(v))
        return rows_where(dataset, config, f'"{column}"={lit}')
    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        return [r for rows in pool.map(one, values) for r in rows]


def parquet(dataset: str, config: str) -> pathlib.Path:
    """The dataset's own parquet file for one small table, downloaded once (57 MB pull_request, 26 MB issue, under 1 MB
    related_issue). The API answers one lookup per 0.4 to 46 seconds; reading these from a file is the same rows, faster.
    pr_commit_details (1.3 GB) stays on the API, one pr_id per query."""
    f = CACHE / "parquet" / f"{dataset.replace('/', '_')}__{config}.parquet"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/datasets/{dataset}/resolve/refs%2Fconvert%2Fparquet/{config}/train/0000.parquet"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=300) as r, open(f.with_suffix(".part"), "wb") as out:
            while chunk := r.read(1 << 20):
                out.write(chunk)
        f.with_suffix(".part").rename(f)
    return f


def pq_rows(dataset: str, config: str, columns: str, where: str, values: list) -> list:
    import duckdb
    con = duckdb.connect()
    cur = con.execute(f"SELECT {columns} FROM read_parquet(?) WHERE {where} = ANY(?)", [str(parquet(dataset, config)), values])
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def html_url(api_url: str) -> str:
    return re.sub(r"^https://api\.github\.com/repos/([^/]+/[^/]+)/pulls/(\d+)$", r"https://github.com/\1/pull/\2", api_url)


def cached(name: str, make):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / name
    if f.exists():
        return json.loads(f.read_text())
    data = make()
    f.write_text(json.dumps(data))
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", type=int, default=X.RULES_VERSION)
    ap.add_argument("--out", default=str(ROOT / "results" / "aidev_recall_v6.json"))
    a = ap.parse_args(argv)
    cases = json.loads(CASES.read_text())["comments"]
    urls = sorted({html_url(c["pull_request_url"]) for c in cases})
    prs = {r["html_url"]: r for r in cached("pull_request.json", lambda: pq_rows("hao-li/AIDev", "pull_request", "id, html_url, agent, state, CAST(merged_at AS VARCHAR) AS merged_at, title, body", "html_url", urls))}
    ids = sorted(p["id"] for p in prs.values())
    commits = collections.defaultdict(list)
    for r in cached("commit_details.json", lambda: in_batches("hao-li/AIDev", "pr_commit_details", "pr_id", ids, 15)):
        commits[r["pr_id"]].append({k: r.get(k) for k in ("sha", "filename", "status", "patch")})
    links = {r["pr_id"]: r["issue_id"] for r in cached("related_issue.json", lambda: pq_rows("hao-li/AIDev-7.6M", "related_issue", "pr_id, issue_id", "pr_id", ids))}
    issues = {r["id"]: r for r in cached("issue.json", lambda: pq_rows("hao-li/AIDev-7.6M", "issue", "id, title, body", "id", sorted(set(links.values()))))}
    rows = []
    for c in cases:
        pr = prs.get(html_url(c["pull_request_url"]))
        if pr is None:
            rows.append({"comment_id": c["comment_id"], "pr": html_url(c["pull_request_url"]), "agent": None, "state": "unknown", "path": c["path"],
                         "kind": listable_kind(c["path"]), "task_from": None, "readable": False, "hit": None, "hit_title_only": None})
            continue
        files = net_files(commits.get(pr["id"], []), c["original_commit_id"])
        repo = pr["html_url"].split("/")[3] + "/" + pr["html_url"].split("/")[4]
        rows.append(score(c, files, task_text(issues.get(links.get(pr["id"])), pr), pr, repo, a.rules))
    out = {"rubric": "eval/aidev_recall_rubric.json", "rules_version": a.rules, "summary": summarize(rows), "rows": rows}
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out["summary"].items() if k in ("comments", "unreadable", "all", "on_a_listable_kind", "on_other_files", "pull_requests")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
