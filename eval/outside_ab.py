"""The outside reviewer test (eval/outside_ab_rubric.json, committed before the ask): scores each participant's replies by
the rubric's outcome rule, so no one judges them by hand. A planted change is caught when a reply names its file or package
and asks to drop it, question it or move it out, or when a reply in its own Itemator thread is `remove` or `split`.
A reply with an asking word but no planted name is not settled by the rule: it is quoted in full and counted as missed.
Participants are listed in eval/outside_ab_merge_requests.json by number, arm and merge request; usernames are never written.

usage (repository root, glab authenticated; GET only): python3 eval/outside_ab.py"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIST = ROOT / "eval" / "outside_ab_merge_requests.json"
OUT = ROOT / "results" / "outside_ab_v1.json"
OWNERS = {"anbuchelvanganesan.cse2024", "anbuchelvannew"}
PLANTED = {"package": "leftpad-py", "ci": ".gitlab-ci.yml"}
ASK = re.compile(r"\b(remove|drop|delete|revert|split|move|unrelated|unnecessary|not needed|why|out of scope)\b|\?", re.I)
THREAD = re.compile(r"\[//\]: # \(itemator:extra=([^)]+)\)")


def is_participant(author: str) -> bool:
    return author not in OWNERS and not author.startswith(("ai-", "duo-"))


def score(discussions: list) -> dict:
    """`discussions`: [{notes: [{author, body, system}]}] oldest first. Returns {planted id: caught} and the unsettled quotes."""
    caught = {k: False for k in PLANTED}
    replies, unsettled = [], []
    for d in discussions:
        notes = d["notes"]
        tm = THREAD.search(notes[0]["body"]) if notes else None
        thread_of = tm.group(1) if tm else None
        for n in notes:
            if n.get("system") or not is_participant(n["author"]):
                continue
            body = n["body"]
            replies.append(body)
            here = set()
            for k, name in PLANTED.items():
                if thread_of == name and body.strip().lower() in ("remove", "split"):
                    here.add(k)
                elif name.lower() in body.lower() and ASK.search(body):
                    here.add(k)
            for k in here:
                caught[k] = True
            one_word = bool(thread_of) and body.strip().lower() in ("remove", "split")       # settled by its thread
            if ASK.search(body) and not one_word and len(here) < len(PLANTED):   # it asks for something not tied to every change
                unsettled.append(body)
    return {"caught": caught, "replies": replies, "unsettled": unsettled}


def summarise(rows: list, by_group: bool = True) -> dict:
    out = {}
    for arm in ("with_itemator", "without"):
        rs = [r for r in rows if r["arm"] == arm and r["replied"]]
        n_caught = sum(v for r in rs for v in r["caught"].values())
        out[arm] = {"participants": len(rs), "planted": len(rs) * len(PLANTED), "caught": n_caught,
                    "share": round(n_caught / (len(rs) * len(PLANTED)), 3) if rs else None}
    both = min(out["with_itemator"]["participants"], out["without"]["participants"])
    out["difference_claimed"] = both >= 5
    if by_group:   # amendment of 2026-10-22: each way of finding people, reported on its own
        out["by_group"] = {g: summarise([r for r in rows if r.get("found") == g], False)
                           for g in sorted({r.get("found") for r in rows if r.get("found")})}
    return out


def _get(path: str):
    return json.loads(subprocess.run(["glab", "api", path], capture_output=True, text=True, check=True).stdout)


def fetch(project_id: int, iid: int) -> list:
    ds = _get(f"projects/{project_id}/merge_requests/{iid}/discussions?per_page=100")
    return [{"notes": [{"author": n["author"]["username"], "body": n["body"], "system": n["system"]} for n in d["notes"]]}
            for d in ds]


def main() -> int:
    rows = []
    for p in json.loads(LIST.read_text())["participants"]:
        s = score(fetch(p["project_id"], p["iid"]))
        rows.append({"n": p["n"], "arm": p["arm"], "found": p.get("found"), "merge_request": p["url"], "replied": bool(s["replies"]), **s})
    OUT.write_text(json.dumps({"rubric": "eval/outside_ab_rubric.json", "participants": rows, "summary": summarise(rows)},
                              indent=1) + "\n")
    print(json.dumps(summarise(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
