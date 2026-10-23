"""The cleanup-after-merge study (eval/cleanup_rubric.json, pushed before any call): after an agent's pull request merged,
were the files it added that the rules list deleted later by a person more often than the files they do not list?
Reads the AIDev cache (eval/cache/aidev/) and GitHub through `gh api`, GET only.

usage: python3 eval/cleanup_after_merge.py [--out results/cleanup_after_merge_v1.json]"""
from __future__ import annotations

import argparse, collections, json, pathlib, random, subprocess, sys, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from itemator import extras as X  # noqa: E402
import aidev_recall as R  # noqa: E402

SEED, PER_SIDE, PER_PR = 20261024, 150, 3
AGENTS = {"copilot", "copilot-swe-agent", "devin-ai-integration", "cursor", "codex", "claude", "google-labs-jules"}


# ---------------------------------------------------------------- pure parts (tests/test_cleanup_after_merge.py)

def by_person(login: str | None) -> bool:
    """A deleting commit counts as a person's when its author is a GitHub user that is neither a bot nor an agent account."""
    if not login:
        return False
    low = login.lower()
    return not low.endswith("[bot]") and low not in AGENTS


def draw(rows: list) -> list:
    """Up to PER_SIDE listed and PER_SIDE unlisted rows, at most PER_PR of each per pull request, after a seeded shuffle."""
    rows = sorted(rows, key=lambda r: (r["pr"], r["path"]))
    random.Random(SEED).shuffle(rows)
    out, per = [], collections.Counter()
    for r in rows:
        side = r["listed"]
        if per[(r["pr"], side)] >= PER_PR or sum(1 for o in out if o["listed"] == side) >= PER_SIDE:
            continue
        per[(r["pr"], side)] += 1
        out.append(r)
    return out


def wilson(k: int, n: int) -> list | None:
    if not n:
        return None
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [round(c - h, 4), round(c + h, 4)]


def summarise(rows: list, rubric: dict) -> dict:
    s = {}
    for name, side in (("listed", True), ("unlisted", False)):
        rs = [r for r in rows if r["listed"] == side and r["state"] != "unreadable"]
        k = sum(r["state"] == "deleted_by_person" for r in rs)
        s[name] = {"n": len(rs), "deleted_by_person": k, "wilson95": wilson(k, len(rs)),
                   "states": dict(collections.Counter(r["state"] for r in rs))}
    s["unreadable"] = sum(r["state"] == "unreadable" for r in rows)
    l, u = s["listed"], s["unlisted"]
    higher = bool(l["n"] and u["n"] and l["deleted_by_person"] / l["n"] > u["deleted_by_person"] / u["n"])
    key = "listed_higher" if higher else "not_higher"
    s["sentence"] = rubric["sentences"][key].format(listed_n=l["n"], listed_k=l["deleted_by_person"],
                                                    unlisted_n=u["n"], unlisted_k=u["deleted_by_person"])
    return s


# ---------------------------------------------------------------- the run

def gh(path: str):
    p = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if p.returncode:
        return None, ("404" if "404" in p.stderr else "403" if "403" in p.stderr else "error")
    return json.loads(p.stdout or "null"), None


def candidates() -> list:
    load = lambda n: json.loads((R.CACHE / n).read_text())
    commits = collections.defaultdict(list)
    for r in load("commit_details.json"):
        commits[r["pr_id"]].append({k: r.get(k) for k in ("sha", "filename", "status", "patch")})
    links = {r["pr_id"]: r["issue_id"] for r in load("related_issue.json")}
    issues = {r["id"]: r for r in load("issue.json")}
    rows = []
    for pr in load("pull_request.json"):
        if not pr.get("merged_at") or pr["id"] not in commits:
            continue
        rs = commits[pr["id"]]
        files = R.net_files(rs, list(dict.fromkeys(r["sha"] for r in rs))[-1])
        if not files:
            continue
        repo = "/".join(pr["html_url"].split("/")[3:5])
        extras = X.analyse(R.task_text(issues.get(links.get(pr["id"])), pr)[0], files, repo=repo, version=6).extras
        for f in files:
            if f.get("status") == "added" and f.get("filename"):
                rows.append({"pr": pr["html_url"], "repo": repo, "path": f["filename"], "merged_at": pr["merged_at"],
                             "agent": pr.get("agent"), "listed": R.listed(extras, f["filename"])})
    return rows


def check(r: dict) -> dict:
    q = urllib.parse.quote(r["path"])
    got, err = gh(f"repos/{r['repo']}/contents/{q}")
    if got is not None:
        return dict(r, state="still_there")
    if err != "404":
        return dict(r, state="unreadable", why=err)
    repo, err = gh(f"repos/{r['repo']}")
    if repo is None:
        return dict(r, state="unreadable", why=f"repository {err}")
    cs, err = gh(f"repos/{r['repo']}/commits?path={q}&since={r['merged_at']}&per_page=1")
    if not cs:
        return dict(r, state="gone_no_commit_found")
    login = ((cs[0].get("author") or {}).get("login"))
    return dict(r, state="deleted_by_person" if by_person(login) else "deleted_by_bot_or_agent", deleted_by=login,
                deleted_in=cs[0].get("sha"), deleted_at=((cs[0].get("commit") or {}).get("author") or {}).get("date"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "cleanup_after_merge_v1.json"))
    a = ap.parse_args(argv)
    rubric = json.loads((ROOT / "eval" / "cleanup_rubric.json").read_text())
    rows = [check(r) for r in draw(candidates())]
    out = {"rubric": "eval/cleanup_rubric.json", "summary": summarise(rows, rubric), "rows": rows}
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
