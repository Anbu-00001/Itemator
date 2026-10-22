"""The catch-delay study (eval/catch_delay_rubric.json, registered before it ran): on the 24 real catches, how long after the
file appeared in the pull request did a maintainer object to it? Reads GitHub through `gh api`, GET only.

usage: python3 eval/catch_delay.py"""
from __future__ import annotations

import datetime as dt, json, pathlib, statistics, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "catch_delay_v1.json"


# ---------------------------------------------------------------- pure parts (tests/test_catch_delay.py)

def when(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def start(pr_created: str, commits: list, path: str) -> str | None:
    """`commits`: [{date, files: [path, ...]}, ...] in pull request order. The later of the pull request's creation and the
    first commit holding `path`; None when no commit holds it."""
    for c in commits:
        if path in c["files"]:
            return max(pr_created, c["date"], key=when)
    return None


def say(hours: float) -> str:
    if hours < 1:
        return f"{round(hours * 60)} minutes"
    if hours < 48:
        return f"{round(hours)} hours" if round(hours) != 1 else "1 hour"
    return f"{round(hours / 24, 1):g} days"


def summarise(rows: list, rubric: dict) -> dict:
    hs = [r["hours"] for r in rows if r["hours"] is not None]
    if not hs:
        return {"n": 0, "unreadable": len(rows)}
    by = {}
    for o in sorted({r["outcome"] for r in rows}):
        sub = [r["hours"] for r in rows if r["outcome"] == o and r["hours"] is not None]
        by[o] = {"n": len(sub), "median_hours": round(statistics.median(sub), 2) if sub else None,
                 "median_whole_hours": round(statistics.median(sub)) if sub else None}
    s = {"n": len(hs), "unreadable": len(rows) - len(hs), "median_hours": round(statistics.median(hs), 2), "median_whole_hours": round(statistics.median(hs)),
         "min_hours": round(min(hs), 2), "max_hours": round(max(hs), 2),
         "within_hour": sum(h < 1 for h in hs), "day_or_more": sum(h >= 24 for h in hs), "by_outcome": by}
    s["sentence"] = rubric["sentence"].format(n=s["n"], median=say(s["median_hours"]),
                                              within_hour=s["within_hour"], day_or_more=s["day_or_more"])
    return s


# ---------------------------------------------------------------- the run (network)

def gh(path: str):
    out = subprocess.run(["gh", "api", "-X", "GET", path], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def read(case: dict) -> dict:
    owner, repo, _, num = case["pr"].split("/")[3:7]
    base = f"repos/{owner}/{repo}"
    row = {"key": case["key"], "outcome": case["outcome"], "objected_at": case["comment_created_at"], "start": None, "hours": None}
    try:
        pr = gh(f"{base}/pulls/{num}")
        commits = []
        for c in gh(f"{base}/pulls/{num}/commits?per_page=100"):
            files = [f["filename"] for f in gh(f"{base}/commits/{c['sha']}").get("files") or []]
            commits.append({"date": c["commit"]["committer"]["date"], "files": files})
            if case["path"] in files:
                break
        row["start"] = start(pr["created_at"], commits, case["path"])
    except (subprocess.CalledProcessError, KeyError, IndexError, json.JSONDecodeError) as e:
        row["error"] = type(e).__name__
    if row["start"]:
        row["hours"] = round((when(row["objected_at"]) - when(row["start"])).total_seconds() / 3600, 3)
    return row


def main() -> int:
    cases = json.loads((ROOT / "results" / "real_catches_v1.json").read_text())["cases"]
    rubric = json.loads((ROOT / "eval" / "catch_delay_rubric.json").read_text())
    rows = []
    for c in cases:
        rows.append(read(c))
        print(rows[-1]["key"], rows[-1]["hours"], flush=True)
    out = {"rubric": "eval/catch_delay_rubric.json", "read_on": dt.date.today().isoformat(), "summary": summarise(rows, rubric), "rows": rows}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
