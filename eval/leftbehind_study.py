"""F1 study A (eval/leftbehind_rubric.json, committed in 2cedf8b before this file): on public AI-agent pull requests that
move a runtime or an image to a new version in a file, how often does the repository still pin the old version
elsewhere at the pull request's head, and was such a copy moved later or named by a reviewer?

Reads data/pull_request.parquet and data/pr_review_comments.parquet, and GitHub's REST API with GET only (the token of the
local `gh` login, held in memory, never printed or written). Every response is cached by URL under --cache, so a rerun
reads nothing twice.

usage: python3 eval/leftbehind_study.py [--limit N] [--cache DIR] [--out results/leftbehind_study_v1.json]"""
from __future__ import annotations

import argparse, concurrent.futures, datetime, hashlib, json, math, pathlib, random, re, subprocess, sys, time
import urllib.error, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from itemator import leftbehind as LB, patchday as PD  # noqa: E402

RUBRIC = json.loads((ROOT / "eval" / "leftbehind_rubric.json").read_text())
FRAME_RE = re.compile(r"\b(bump|bumps|update|updates|upgrade|upgrades|move|moves|pin|pins)\b.{0,80}\b(php|node|nodejs|node\.js|python|ruby|go|golang|java|jdk|openjdk|dotnet|alpine|debian|ubuntu|postgres|postgresql|mysql|mariadb|redis|nginx|image|base image|docker|dockerfile)\b")
assert FRAME_RE.pattern in RUBRIC["frame"], "the frame must be the pre-registered one"
SAMPLE, SEED, DAYS, MAX_PAGES = 400, 20261024, 90, 30
API = "https://api.github.com"


class GitHub:
    def __init__(self, cache: pathlib.Path):
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)
        self.token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
        self.calls = 0

    def get(self, path: str, raw: bool = False):
        """(status, body): JSON, or text with raw; 404 and 409 (an empty repository) are answers, not errors."""
        url = path if path.startswith("http") else API + path
        key = self.cache / (hashlib.sha256(f"{raw}:{url}".encode()).hexdigest() + ".json")
        if key.exists():
            got = json.loads(key.read_text())
            return got["status"], got["body"]
        status, data = None, b"null"
        accept = "application/vnd.github.raw" if raw else "application/vnd.github+json"
        for attempt in range(6):
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}", "Accept": accept,
                                                       "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "itemator-study"})
            try:
                self.calls += 1
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                    status = r.status
                    remaining = int(r.headers.get("X-RateLimit-Remaining") or 1)
                    if remaining < 50:
                        time.sleep(max(0, int(r.headers.get("X-RateLimit-Reset") or 0) - time.time()) + 5)
                break
            except urllib.error.HTTPError as e:
                if e.code in (404, 409, 422, 451):
                    status, data = e.code, b"null"
                    break
                if e.code in (403, 429, 500, 502, 503, 504) and attempt < 5:
                    time.sleep(2 ** attempt * 5)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt < 5:
                    time.sleep(2 ** attempt * 5)
                    continue
                raise
        body = data.decode("utf-8", "replace") if raw and status == 200 else json.loads(data or b"null")
        key.write_text(json.dumps({"status": status, "body": body}))
        return status, body


def frame(limit: int | None) -> list[dict]:
    import duckdb
    rows = duckdb.connect().execute("select id, number, title, body, agent, state, merged_at, repo_url, html_url "
                                    "from 'data/pull_request.parquet' order by id").fetchall()
    cols = ("id", "number", "title", "body", "agent", "state", "merged_at", "repo_url", "html_url")
    hits = [dict(zip(cols, r)) for r in rows if FRAME_RE.search((r[2] or "").lower())]
    picked = sorted(random.Random(SEED).sample(hits, SAMPLE), key=lambda r: r["id"]) if len(hits) > SAMPLE else hits
    return [{**h, "frame_size": len(hits)} for h in (picked[:limit] if limit else picked)]


def reader(gh: GitHub, repo: str, sha: str):
    def read(path: str):
        status, text = gh.get(f"/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={sha}", raw=True)
        return text if status == 200 and isinstance(text, str) else None
    return read


def template(p) -> str:
    return (p.text[:p.start] + "{V}" + p.text[p.start + len(p.shown):]).strip()


def one(gh: GitHub, pr: dict) -> dict:
    repo = pr["repo_url"].split("/repos/", 1)[1]
    row = {"pr": pr["html_url"], "agent": pr["agent"], "merged": bool(pr["merged_at"])}
    status, meta = gh.get(f"/repos/{repo}/pulls/{pr['number']}")
    if status != 200 or not meta:
        return {**row, "state": "unreadable", "why": f"pull request: HTTP {status}"}
    base, head, base_ref = meta["base"]["sha"], meta["head"]["sha"], meta["base"]["ref"]
    files = []
    for page in range(1, MAX_PAGES + 1):
        status, got = gh.get(f"/repos/{repo}/pulls/{pr['number']}/files?per_page=100&page={page}")
        if status != 200 or got is None:
            return {**row, "state": "unreadable", "why": f"files: HTTP {status}"}
        files += [{"filename": f["filename"], "status": f["status"]} for f in got]
        if len(got) < 100:
            break
    read_base, read_head = reader(gh, repo, base), reader(gh, repo, head)
    moves = LB.moved(files, read_base, read_head)
    if not moves:
        return {**row, "state": "no_move"}
    status, tree = gh.get(f"/repos/{repo}/git/trees/{head}?recursive=1")
    if status != 200 or not tree:
        return {**row, "state": "partly_read", "why": f"tree: HTTP {status}", "moved": [m.family for m in moves]}
    tracked = [t["path"] for t in tree.get("tree") or [] if t.get("type") == "blob"]
    text = f"{pr['title'] or ''}\n{pr['body'] or ''}"
    listed = PD.listed_versions(text) if PD.cves(text) else set()
    found = LB.find(files, tracked, read_base, read_head, listed)
    row |= {"state": "partly_read" if tree.get("truncated") or found.capped else "read",
            "moved": [{"path": m.path, "family": m.family, "to": m.shown} for m in found.moved],
            "left": [{"path": p.path, "line": p.line, "family": p.family, "version": p.shown, "to": t, "where": p.where,
                      "template": template(p)} for p, t, _ in found.left],
            "floating": len(found.floating)}
    if row["left"] and pr["merged_at"]:
        row["left"] = [c | later(gh, repo, base_ref, pr["merged_at"], c) for c in row["left"]]
    return row


def at_or_above(version: tuple, want: tuple) -> bool:
    """3.10.12 is below 3.11 and 3.11.4 is at it: compared on the digits both have."""
    k = min(len(version), len(want))
    return version[:k] >= want[:k]


def later(gh: GitHub, repo: str, ref: str, merged_at: str, copy: dict) -> dict:
    """followed: a commit within DAYS after the merge left that copy's file with a pin of the same line shape at or above
    its target; still_old: the file at the branch tip today still has that shape below the target."""
    want = LB.parse_version(copy["to"])
    want = want[0] if want else None

    def verdict(text):
        same = [p for p in LB.pins(copy["path"], text or "") if p.family == copy["family"] and template(p) == copy["template"]]
        if not same or want is None:
            return None
        return all(at_or_above(p.version, want) for p in same)
    start = datetime.datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
    until = (start + datetime.timedelta(days=DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    q = urllib.parse.urlencode({"sha": ref, "path": copy["path"], "since": merged_at, "until": until, "per_page": 100})
    status, commits = gh.get(f"/repos/{repo}/commits?{q}")
    followed = None
    if status == 200 and isinstance(commits, list):
        followed = False
        for c in reversed(commits):
            if verdict(reader(gh, repo, c["sha"])(copy["path"])):
                followed = True
                break
    now = verdict(reader(gh, repo, ref)(copy["path"]))
    return {"followed": followed, "commits_after": len(commits) if isinstance(commits, list) else None,
            "still_old": None if now is None else not now}


def named(rows: list) -> None:
    import duckdb
    urls = {r["pr"].replace("https://github.com/", "https://api.github.com/repos/").replace("/pull/", "/pulls/"): r
            for r in rows if r.get("left")}
    if not urls:
        return
    got = duckdb.connect().execute("select pull_request_url, path, body from 'data/pr_review_comments.parquet' "
                                   "where pull_request_url in (select unnest(?))", [list(urls)]).fetchall()
    for url, path, body in got:
        for c in urls[url]["left"]:
            if c["path"] in (body or "") or c["path"].rsplit("/", 1)[-1] in (body or "") or path == c["path"]:
                c["named"] = True
    for r in urls.values():
        for c in r["left"]:
            c.setdefault("named", False)


def wilson(k: int, n: int) -> list | None:
    if not n:
        return None
    p, z = k / n, 1.959964
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def summarise(rows: list, frame_size: int) -> dict:
    moved = [r for r in rows if r["state"] in ("read", "partly_read") and r.get("moved")]
    read = [r for r in moved if r["state"] == "read"]
    left = [r for r in read if r["left"]]
    copies = [c for r in left for c in r["left"]]
    merged = [c for r in left if r["merged"] for c in r["left"]]
    return {
        "frame_titles_matched": frame_size, "sampled": len(rows),
        "by_state": {s: sum(r["state"] == s for r in rows) for s in ("unreadable", "no_move", "partly_read", "read")},
        "with_a_move_read": len(read),
        "left_behind": {"prs": len(left), "share": round(len(left) / len(read), 4) if read else None,
                        "wilson95": wilson(len(left), len(read)), "copies": len(copies),
                        "files": len({(r["pr"], c["path"]) for r in left for c in r["left"]})},
        "merged_copies": {"n": len(merged), "followed": sum(c.get("followed") is True for c in merged),
                          "not_followed": sum(c.get("followed") is False for c in merged),
                          "unknown": sum(c.get("followed") is None for c in merged),
                          "still_old_today": sum(c.get("still_old") is True for c in merged),
                          "named_by_a_reviewer": sum(c.get("named") is True for c in copies)},
        "kill_rule_narrow": (len(left) / len(read) < 0.03) if read else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--cache", default=str(pathlib.Path.home() / ".cache" / "itemator-leftbehind"))
    ap.add_argument("--out", default=str(ROOT / "results" / "leftbehind_study_v1.json"))
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    gh = GitHub(pathlib.Path(a.cache))
    prs = frame(a.limit)
    with concurrent.futures.ThreadPoolExecutor(a.workers) as pool:
        rows = list(pool.map(lambda pr: one(gh, pr), prs))
    named(rows)
    out = {"rubric": "eval/leftbehind_rubric.json", "code": "eval/leftbehind_study.py",
           "run_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "github_calls": gh.calls, "summary": summarise(rows, prs[0]["frame_size"] if prs else 0), "rows": rows}
    if a.limit:
        print(json.dumps(out["summary"], indent=1))
        return 0
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
