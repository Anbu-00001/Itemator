"""How many hours passed between an agent's pull request opening and the reviewer's objection, per case of results/real_catches_v1.json.

Rules in eval/catch_timing_rubric.json. Only GET requests to the public GitHub REST API; responses cached in eval/cache/github/.
Run: python eval/catch_timing.py --out results/catch_timing_v1.json"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import statistics
import subprocess
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CASES = ROOT / "results" / "real_catches_v1.json"
CACHE = ROOT / "eval" / "cache" / "github"
_PR = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)$")


def parse_pr(url: str):
    m = _PR.match(url)
    return m.groups() if m else None


def _stamp(s):
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def hours_between(opened, commented):
    """Hours (one decimal) from opened to commented, or None if either is unreadable or the order is wrong."""
    a, b = _stamp(opened), _stamp(commented)
    if a is None or b is None or b < a:
        return None
    return round((b - a).total_seconds() / 3600, 1)


def fetch_created_at(owner, repo, n, cache=CACHE):
    """created_at of the pull request from GET /repos/{owner}/{repo}/pulls/{n}; cached; None if the call fails."""
    f = pathlib.Path(cache) / f"{owner}__{repo}__{n}.json"
    if f.exists():
        data = json.loads(f.read_text())
    else:
        path = f"repos/{owner}/{repo}/pulls/{n}"
        try:
            r = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=30)
            raw = r.stdout if r.returncode == 0 else urllib.request.urlopen(
                urllib.request.Request("https://api.github.com/" + path, headers={"User-Agent": "itemator-eval"}), timeout=30).read().decode()
            data = json.loads(raw)
        except Exception:
            return None
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data))
    return data.get("created_at") if isinstance(data, dict) else None


def measure(cases, get_created=fetch_created_at):
    rows = []
    for c in cases:
        p = parse_pr(c["pr"])
        opened = get_created(*p) if p else None
        rows.append({"pr": c["pr"], "path": c["path"], "pr_created_at": opened, "comment_created_at": c.get("comment_created_at"),
                     "hours": hours_between(opened, c.get("comment_created_at"))})
    return rows, summarise(rows)


def summarise(rows):
    h = [r["hours"] for r in rows if r["hours"] is not None]
    s = {"read": len(h), "unreadable": len(rows) - len(h)}
    if h:
        s.update(median_hours=round(statistics.median(h), 1), min_hours=min(h), max_hours=max(h), over_24h=sum(x > 24 for x in h))
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--cases", default=str(CASES))
    a = ap.parse_args(argv)
    rows, s = measure(json.load(open(a.cases))["cases"])
    with open(a.out, "w") as fh:
        json.dump({"rubric": "eval/catch_timing_rubric.json", "summary": s, "cases": rows}, fh, indent=1)
        fh.write("\n")
    print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
