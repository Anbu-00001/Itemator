"""Patch-week study (eval/php_patch_rubric.json, committed before this file): on public GitHub pull requests opened in
the week of PHP's 21 October 2026 advisory that move PHP to a fixed release, how often does the repository still pin an
older PHP in another file, and was that copy moved later or named on the pull request?

GET only, through the local `gh` login's token (held in memory, never printed or written); every response is cached by
URL under --cache. The reading code is eval/leftbehind_study.py's, with this frame and only PHP moves and copies.

usage: python3 eval/php_patch_study.py [--limit N] [--cache DIR] [--out results/php_patch_study_v1.json]"""
from __future__ import annotations

import argparse, concurrent.futures, datetime, json, pathlib, random, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

import leftbehind_study as LS  # noqa: E402

RUBRIC = json.loads((ROOT / "eval" / "php_patch_rubric.json").read_text())
FIXED = ("8.5.12", "8.4.27", "8.3.36", "8.2.35")
WINDOW = "2026-10-21..2026-10-24"
SAMPLE, SEED = 200, 20261024
QUERY = '"{v}" php in:title is:pr is:public created:' + WINDOW
assert QUERY.replace("{v}", "V") in RUBRIC["frame"], "the frame must be the pre-registered one"
assert f"{SAMPLE} drawn with random.Random({SEED})" in RUBRIC["frame"], "the sample must be the pre-registered one"


def search(q: str, page: int) -> list[dict]:
    """One page of GitHub's issue search through `gh` (search has its own rate limit, which LS.GitHub would wait on)."""
    got = subprocess.run(["gh", "api", "-X", "GET", "search/issues", "-f", f"q={q}", "-f", "per_page=100", "-f",
                          f"page={page}"], capture_output=True, text=True, check=True).stdout
    return json.loads(got).get("items") or []


def frame(limit: int | None) -> tuple[list[dict], int]:
    seen = {}
    for v in FIXED:
        for page in range(1, 11):
            items = search(QUERY.format(v=v), page)
            for it in items:
                seen.setdefault(it["html_url"], it)
            if len(items) < 100:
                break
    hits = [seen[u] for u in sorted(seen)]
    picked = hits
    if len(hits) > SAMPLE:
        picked = sorted(random.Random(SEED).sample(hits, SAMPLE), key=lambda i: i["html_url"])
    return [as_pr(i) for i in (picked[:limit] if limit else picked)], len(hits)


def as_pr(item: dict) -> dict:
    """The fields eval/leftbehind_study.one reads, from a search item."""
    return {"number": item["number"], "title": item.get("title"), "body": item.get("body"),
            "agent": (item.get("user") or {}).get("login"), "author_type": (item.get("user") or {}).get("type"),
            "merged_at": (item.get("pull_request") or {}).get("merged_at"),
            "repo_url": item["repository_url"], "html_url": item["html_url"]}


def php_only(row: dict) -> dict:
    """Keep PHP moves and PHP copies; a pull request that moved only something else is 'no_move'."""
    if row.get("state") not in ("read", "partly_read"):
        return row
    moved = [m for m in row.get("moved") or [] if isinstance(m, dict) and m.get("family") == "php"]
    if not moved:
        return {k: v for k, v in row.items() if k not in ("moved", "left", "floating")} | {"state": "no_move"}
    return row | {"moved": moved, "left": [c for c in row.get("left") or [] if c["family"] == "php"]}


def one(gh: LS.GitHub, pr: dict) -> dict:
    row = LS.one(gh, {**pr, "merged_at": None})
    if row.get("state") in ("read", "partly_read") and isinstance((row.get("moved") or [None])[0], str):
        row["moved"] = [{"family": f} for f in row["moved"]]
    row = php_only(row) | {"author_type": pr["author_type"], "merged": bool(pr["merged_at"])}
    if row.get("left") and pr["merged_at"]:
        repo = pr["repo_url"].split("/repos/", 1)[1]
        status, meta = gh.get(f"/repos/{repo}/pulls/{pr['number']}")
        ref = meta["base"]["ref"] if status == 200 and meta else None
        unknown = {"followed": None, "still_old": None}
        row["left"] = [c | (LS.later(gh, repo, ref, pr["merged_at"], c) if ref else unknown) for c in row["left"]]
    return row


def named(gh: LS.GitHub, rows: list, prs: dict) -> None:
    for r in rows:
        if not r.get("left"):
            continue
        pr = prs[r["pr"]]
        repo = pr["repo_url"].split("/repos/", 1)[1]
        texts = []
        for kind in ("pulls", "issues"):
            status, got = gh.get(f"/repos/{repo}/{kind}/{pr['number']}/comments?per_page=100")
            texts += [(c.get("body") or "", c.get("path")) for c in got or []] if status == 200 else []
        for c in r["left"]:
            name = c["path"].rsplit("/", 1)[-1]
            c["named"] = any(c["path"] in b or name in b or p == c["path"] for b, p in texts)


def summarise(rows: list, frame_size: int) -> dict:
    out = LS.summarise(rows, frame_size)
    out["frame_titles_matched"] = frame_size
    out.pop("kill_rule_narrow", None)
    left = [r for r in rows if r["state"] == "read" and r.get("left")]
    out["left_behind"]["by_author_type"] = {t: sum(r.get("author_type") == t for r in left)
                                            for t in sorted({r.get("author_type") or "?" for r in left})}
    out["list_instead_of_share"] = out["with_a_move_read"] < 30
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--cache", default=str(pathlib.Path.home() / ".cache" / "itemator-leftbehind"))
    ap.add_argument("--out", default=str(ROOT / "results" / "php_patch_study_v1.json"))
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    gh = LS.GitHub(pathlib.Path(a.cache))
    prs, size = frame(a.limit)
    with concurrent.futures.ThreadPoolExecutor(a.workers) as pool:
        rows = list(pool.map(lambda pr: one(gh, pr), prs))
    named(gh, rows, {p["html_url"]: p for p in prs})
    out = {"rubric": "eval/php_patch_rubric.json", "code": "eval/php_patch_study.py",
           "run_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "github_calls": gh.calls, "summary": summarise(rows, size), "rows": rows}
    print(json.dumps(out["summary"], indent=1))
    if not a.limit:
        pathlib.Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
