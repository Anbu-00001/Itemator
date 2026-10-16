"""Scan history: the CI job's rules over merge requests already merged into a branch (a manual job; it only reads).

For each of the last merge requests merged into the target branch it reads what the CI job reads (the merge request
and the issues it links) and takes the change from git: the merge or squash commit against its first parent, which is
the merge request as it landed. Nothing is posted and no Duo credit is used. A merge request whose commit is not in
this clone, or that cannot be read, is counted with its reason, never guessed. Writes scan.json and scan.md.

usage (CI, with GIT_DEPTH 0): python -E -m itemator.scan [--target main] [--last 50]
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import sys
import urllib.parse

from itemator import ci
from itemator import decisions as D
from itemator import extras as X
from itemator import policy as POL

LAST, PAGES = 50, 5          # merge requests scanned by default; pages of 100 listed (newest merge first)


def merged(api: ci.Api, pid: str, target: str, last: int = LAST) -> list[dict]:
    """The last `last` merge requests merged into `target`, newest merge first (order_by=merged_at, GitLab 17.2 or later)."""
    out = []
    for page in range(1, PAGES + 1):
        data = api.get(f"/projects/{pid}/merge_requests?state=merged&target_branch={urllib.parse.quote(target, safe='')}"
                       f"&order_by=merged_at&sort=desc&per_page=100&page={page}")
        if not isinstance(data, list):
            break
        out += [m for m in data if isinstance(m, dict) and isinstance(m.get("iid"), int) and m.get("merged_at")]
        if len(data) < 100:
            break
    return sorted(out, key=lambda m: m["merged_at"], reverse=True)[:last]


def landed(repo: str, mr: dict) -> tuple[str, str] | None:
    """(parent, commit): the merge request as it landed, from its merge or squash commit; None when there is no such
    commit (a fast-forward merge) or it is not in this clone."""
    commit = mr.get("merge_commit_sha") or mr.get("squash_commit_sha")
    if not isinstance(commit, str) or not ci._SHA40.fullmatch(commit):
        return None
    try:
        parent = ci._git(repo, "rev-parse", "-q", "--verify", f"{commit}^1").decode("ascii", "replace").strip()
    except ci.JobError:
        return None
    return (parent, commit) if ci._SHA40.fullmatch(parent) else None


def scan_one(api: ci.Api, repo: str, pid: str, path: str | None, mr: dict, policy, now) -> dict:
    row = {"iid": mr["iid"], "title": D.clean(mr.get("title"), 100), "merged_at": mr["merged_at"]}
    if not (mr.get("merge_commit_sha") or mr.get("squash_commit_sha")):
        return {**row, "state": "unreadable", "reason": "merged without a merge or squash commit (fast-forward), so its own change cannot be told apart"}
    change = landed(repo, mr)
    if change is None:
        return {**row, "state": "unreadable", "reason": "its merge or squash commit is not in this clone"}
    description = mr.get("description") or ""
    warnings: list[str] = []
    try:
        files = ci.diff_files(repo, *change)
        issues, issues_from = ci.linked_issues(api, pid, mr["iid"], description, warnings, mr.get("source_branch"), path)
    except ci.JobError as e:
        return {**row, "state": "unreadable", "reason": str(e)[:200]}
    r = ci.facts(mr_iid=mr["iid"], mr_title=mr.get("title") or "", mr_description=description,
                 mr_author_id=(mr.get("author") or {}).get("id"), issues=issues, issues_from=issues_from, files=files,
                 repo=path, base_sha=change[0], head_sha=change[1], warnings=warnings, now=now, policy=policy)
    return {**row, "state": r["state"], "issue_iids": r["issue_iids"], "issues_from": issues_from,
            "extras": [{"kind": e["kind"], "name": D.clean_name(e["name"])} for e in r["extras"]],
            "unplaced": len(r["unplaced"]), "warnings": warnings}


def summary(rows: list) -> dict:
    read = [r for r in rows if r["state"] != "unreadable"]
    linked = [r for r in read if r["state"] != "no_issue"]
    flagged = [r for r in linked if r["extras"]]
    kinds = collections.Counter(e["kind"] for r in flagged for e in r["extras"])
    return {"merge_requests": len(rows), "unreadable": len(rows) - len(read), "no_issue": len(read) - len(linked),
            "with_an_issue": len(linked), "with_extras": len(flagged), "extras": sum(kinds.values()),
            "extras_by_kind": dict(sorted(kinds.items()))}


def _cell(text) -> str:
    """Text for a markdown table cell: a pipe would start a new cell."""
    return str(text).replace("|", "\\|")


def markdown(report: dict) -> str:
    s, n = report["summary"], report["summary"]["merge_requests"]
    out = [f"# Scan history: the last {n} merge request{'' if n == 1 else 's'} merged into `{report['target']}`", "",
           f"Itemator's rules (version {report['rules_version']}) over merge requests already merged: the change as it "
           "landed, read from git, against the issues each one links. Nothing was posted.", "",
           "| | merge requests |", "|---|---|",
           f"| scanned | {n} |", f"| linked to an issue | {s['with_an_issue']} |",
           f"| with at least one extra | {s['with_extras']} |", f"| no issue linked | {s['no_issue']} |",
           f"| could not be read | {s['unreadable']} |", ""]
    flagged = [r for r in report["merge_requests"] if r.get("extras")]
    if flagged:
        out += ["## Merge requests with extras", "", "| merge request | merged | issue | extras |", "|---|---|---|---|"]
        for r in flagged:
            extras = ", ".join(f"`{_cell(e['name'])}` ({ci._LABEL.get(e['kind'], e['kind'])})" for e in r["extras"])
            issues = ", ".join(f"#{i}" for i in r["issue_iids"])
            out.append(f"| !{r['iid']} {_cell(r['title'])} | {r['merged_at'][:10]} | {issues} | {extras} |")
        out.append("")
    return "\n".join(out)


def main(argv=None, env=None, http=None) -> int:
    p = argparse.ArgumentParser(prog="python -m itemator.scan", description=__doc__.split("\n")[0])
    p.add_argument("--target", default=None, help="the branch merged into (default: CI_DEFAULT_BRANCH)")
    p.add_argument("--last", type=int, default=LAST)
    p.add_argument("--repo", default=".")
    p.add_argument("--out", default="scan", help="writes <out>.json and <out>.md")
    a = p.parse_args(argv)
    if a.last < 1:
        p.error("--last must be 1 or more")
    env = os.environ if env is None else env
    if not env.get("CI_API_V4_URL") or not env.get("CI_PROJECT_ID"):
        print("itemator scan: CI_API_V4_URL and CI_PROJECT_ID are needed", file=sys.stderr)
        return 2
    target = a.target or env.get("CI_DEFAULT_BRANCH") or "main"
    api = ci.Api(env["CI_API_V4_URL"], env.get("CI_JOB_TOKEN") or None, http or ci.http_get)
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        tip = env.get("CI_COMMIT_SHA") or ci._git(a.repo, "rev-parse", "HEAD").decode("ascii", "replace").strip()
        policy = POL.read(a.repo, tip)            # the team policy as the branch has it now
        rows = [scan_one(api, a.repo, env["CI_PROJECT_ID"], env.get("CI_PROJECT_PATH"), m, policy, now)
                for m in merged(api, env["CI_PROJECT_ID"], target, a.last)]
    except ci.JobError as e:
        print(f"itemator scan: {e}", file=sys.stderr)
        return 2
    report = {"rules_version": X.RULES_VERSION, "target": target, "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "summary": summary(rows), "merge_requests": rows}
    with open(f"{a.out}.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    md = markdown(report)
    with open(f"{a.out}.md", "w", encoding="utf-8") as fh:
        fh.write(md + "\n")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
