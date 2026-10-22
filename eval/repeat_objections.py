"""Repeat objections (eval/repeat_objections_rubric.json, pushed before counting): a reviewer objected to the same file in two
or more agent pull requests of one repository. Read from the cached AIDev objection set, nothing fetched.

usage: python3 eval/repeat_objections.py  ->  results/repeat_objections_v1.json"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import aidev_recall as R  # noqa: E402
from head_to_head import wilson  # noqa: E402

ROOT = R.ROOT
OUT = ROOT / "results" / "repeat_objections_v1.json"


def pairs(comments: list) -> dict:
    """{(repo, path): {pr url: [comment ids]}} for every pair objected to in at least two pull requests."""
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for c in comments:
        pr = R.html_url(c["pull_request_url"])
        u = pr.split("/")
        by[(f"{u[3]}/{u[4]}", c["path"])][pr].append(c["comment_id"])
    return {k: dict(v) for k, v in by.items() if len(v) >= 2}


def build(comments: list, named: dict | None = None) -> dict:
    """`named`: {comment id: {tool: named}} from results/head_to_head_v1.json, added after counting (which tool would have
    put the file in a thread, so that a first answer could be shown again)."""
    named = named or {}
    rep = pairs(comments)
    repeats = sum(len(v) - 1 for v in rep.values())       # every pull request after the first, per pair
    n = len(comments)
    return {"rubric": "eval/repeat_objections_rubric.json", "objections": n, "pairs_in_two_or_more": len(rep),
            "repeat_objections": repeats, "share": round(repeats / n, 4) if n else None, "wilson95": wilson(repeats, n),
            "pairs": [{"repo": r, "path": p, "pull_requests": [{"url": u, "comments": v[u], "named": [named.get(str(c)) for c in v[u]]} for u in sorted(v)]} for (r, p), v in sorted(rep.items())]}


def main() -> int:
    readable = {r["comment_id"] for r in json.loads((ROOT / "results" / "aidev_recall_v6.json").read_text())["rows"] if r["readable"]}
    comments = [c for c in json.loads(R.CASES.read_text())["comments"] if c["comment_id"] in readable and c.get("path")]
    h2h = json.loads((ROOT / "results" / "head_to_head_v1.json").read_text())["rows"]
    out = build(comments, {str(r["comment_id"]): r["named"] for r in h2h})
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "pairs"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
