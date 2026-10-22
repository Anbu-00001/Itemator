"""results/stories.md: real cases from results/real_catches.md told as stories, at most one per outcome (taken out, closed
without merging, merged with the file), with how many hours passed before the reviewer's comment (results/catch_timing_v1.json).

The rule: in each outcome, among the rows whose reading is "asks to take it out" and whose comment is about the whole file,
the one with the most hours between the pull request opening and the comment; a tie goes to the first row on the page.
A comment is about the whole file when GitHub marks it as a file comment or puts it on the file's first line
(results/catch_comment_scope_v1.json, written by --fetch with GET requests only).

Rule history: the first version, committed before any output, had no whole-file condition. It picked
Azure/azure-sdk-for-python#42404, where the comment was about a licence classifier line and the rules list a package added
on another line, so the story put an objection next to an extra it was not about. The condition was added after seeing
that, and the page says so. No card was shown on these pull requests: "with Itemator" says only what the frozen rules list,
and the replay of one case (second-project !2) is the live run.

usage (repository root):  python3 eval/stories_page.py [--fetch]"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "results" / "real_catches.md"
TIMING = ROOT / "results" / "catch_timing_v1.json"
CASES = ROOT / "results" / "real_catches_v1.json"
OUT = ROOT / "results" / "stories.md"
SCOPE = ROOT / "results" / "catch_comment_scope_v1.json"
OUTCOMES = {"Taken out of the pull request": "removed", "Pull request closed without merging": "closed",
            "Merged (or still open) with the file in it": "landed"}
THEN = {"removed": "The file was taken out of the pull request.",
        "closed": "The pull request was closed without merging.",
        "landed": "The pull request merged with the file still changed.",
        "open": "The pull request is still open with the file in it."}
REPLAY = "https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/39194174/second-project/-/merge_requests/2"
_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def rows(page: str) -> list[dict]:
    """Each table row of the page: outcome, pr, repo, agent, file, rule, quote, comment, reading."""
    out, outcome = [], None
    for line in page.splitlines():
        if line.startswith("## "):
            outcome = next((v for k, v in OUTCOMES.items() if line[3:].startswith(k)), None)
            continue
        if not (outcome and line.startswith("| [")):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 6:
            continue
        pm, qm = _LINK.match(cells[0]), _LINK.match(cells[4])
        if not (pm and qm):
            continue
        repo, pr = pm.groups()
        quote, comment = qm.groups()
        out.append({"outcome": outcome, "pr": pr, "repo": repo.split("#")[0], "agent": cells[1].replace("_", " "),
                    "file": cells[2].strip("`"), "rule": cells[3], "quote": quote.strip('"'), "comment": comment,
                    "reading": cells[5]})
    return out


def hours_of(timing: dict) -> dict:
    return {(c["pr"], c["path"].rsplit("/", 1)[-1]): c["hours"] for c in timing["cases"] if c.get("hours") is not None}


def whole_file(c: dict) -> bool:
    return c.get("subject_type") == "file" or c.get("original_line") == 1


def pick(rs: list[dict], hours: dict, scope: dict) -> list[dict]:
    chosen = []
    for outcome in OUTCOMES.values():
        cands = [dict(r, hours=hours.get((r["pr"], r["file"].rsplit("/", 1)[-1])))
                 for r in rs if r["outcome"] == outcome and r["reading"] == "asks to take it out"
                 and whole_file(scope.get(r["comment"], {}))]
        cands = [c for c in cands if c["hours"] is not None]
        if cands:
            chosen.append(max(cands, key=lambda c: c["hours"] or 0))     # max keeps the first of equal values
    return chosen


def _when(h: float) -> str:
    return f"{h:.0f} hours ({h / 24:.1f} days)" if h >= 48 else f"{h:.1f} hours"


def story(s: dict, merged: dict | None = None) -> str:
    then = s["outcome"]
    if then == "landed" and merged is not None and not merged.get(s["pr"], True):
        then = "open"
    return (f"### {s['agent']} in {s['repo']}: `{s['file'].rsplit('/', 1)[-1]}`\n\n"
            f"{s['agent']} opened [the pull request]({s['pr']}). What the rules list in `{s['file']}`: {s['rule']}. "
            f"A reviewer wrote [\"{s['quote']}\"]({s['comment']}) {_when(s['hours'])} after the pull request opened. "
            f"{THEN[then]}\n\n"
            "**With Itemator:** the card would have named it when the pipeline finished, and the merge request would have "
            "stayed a draft until someone kept it, split it or removed it.\n")


def render(page: str, timing: dict, scope: dict, cases: dict | None = None) -> str:
    rs, s = rows(page), timing["summary"]
    told = pick(rs, hours_of(timing), scope)
    missing = [k for k, v in OUTCOMES.items() if v not in {t["outcome"] for t in told}]
    head = ("# Real pull requests, and what the card would have said\n\n"
            f"In each of the {s['read']} real cases on [the cases page](real_catches.md), a reviewer objected by hand. "
            f"The median wait from the pull request opening to that comment was {s['median_hours']} hours; "
            f"{s['over_24h']} waited more than a day ([timing](catch_timing_v1.json)). Each story below is the longest wait "
            "in its outcome, among the comments that ask to take out the whole file (the rule and its history are in "
            "eval/stories_page.py). Nobody saw an Itemator card on these pull requests. One more case, an install script "
            f"Copilot added, was replayed with the real job and flows: [second-project !2]({REPLAY}).\n\n")
    if missing:
        head += ("No story for: " + "; ".join(m.lower() for m in missing) + ". No comment there that asks to take a "
                 "file out is about the whole file, so a story would put an objection next to an extra it was not about. "
                 "The first version of the rule did that, with a licence line in Azure/azure-sdk-for-python#42404.\n\n")
    merged = {c["pr"]: c["merged"] for c in (cases or {}).get("cases", [])} if cases else None
    return head + "\n".join(story(t, merged) for t in told)


def fetch(page: str) -> dict:
    """GitHub's subject_type and original_line for each row's comment; GET requests only."""
    out = {}
    for r in rows(page):
        own, repo, _, num = r["pr"].split("/")[3:7]
        cid = r["comment"].rsplit("discussion_r", 1)[-1]
        got = subprocess.run(["gh", "api", "-X", "GET", f"repos/{own}/{repo}/pulls/comments/{cid}"],
                             capture_output=True, text=True, check=True)
        c = json.loads(got.stdout)
        out[r["comment"]] = {"subject_type": c.get("subject_type"), "original_line": c.get("original_line")}
    return out


def main() -> int:
    if "--fetch" in sys.argv[1:]:
        SCOPE.write_text(json.dumps({"source": "GitHub REST API, pull request review comments, GET only",
                                     "comments": fetch(PAGE.read_text())}, indent=1) + "\n")
    scope = json.loads(SCOPE.read_text())["comments"]
    OUT.write_text(render(PAGE.read_text(), json.loads(TIMING.read_text()), scope, json.loads(CASES.read_text())))
    print(OUT.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
