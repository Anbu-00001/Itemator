"""The comments leg 1 reads (eval/aidev_recall_rubric.json): every human inline review comment in AIDev's
`pr_review_comments` (hao-li/AIDev, v4 pull requests from repositories with over 100 stars) whose text contains one of
five phrases. Writes ids, pull request addresses and paths only (no comment text) to eval/aidev_recall_cases.json.

usage: python3 eval/aidev_cases.py"""
from __future__ import annotations

import datetime, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import aidev_recall as A

PHRASES = ("unrelated", "out of scope", "separate PR", "not needed", "unnecessary")
KEEP = ("pull_request_url", "path", "original_commit_id")


def select(rows: list) -> list:
    """Human comments (user_type User), each once, in id order, reduced to the fields we keep."""
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r["id"]):
        if r.get("user_type") == "User" and r["id"] not in seen and r.get("path"):
            seen.add(r["id"])
            out.append({"comment_id": r["id"], **{k: r[k] for k in KEEP}})
    return out


def main() -> int:
    where = " OR ".join(f"\"body\" ILIKE '%{p}%'" for p in PHRASES)
    rows = A.rows_where("hao-li/AIDev", "pr_review_comments", where)
    cases = select(rows)
    A.CASES.write_text(json.dumps({"what": "Human inline review comments of AIDev's pr_review_comments that contain one of the phrases; ids and paths only.",
                                   "dataset": "hao-li/AIDev (public, CC-BY-4.0)", "phrases": list(PHRASES), "read_on": datetime.date.today().isoformat(),
                                   "matched_all_users": len(rows), "comments": cases}, indent=1) + "\n")
    print(len(rows), "matched,", len(cases), "human comments on", len({c["pull_request_url"] for c in cases}), "pull requests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
