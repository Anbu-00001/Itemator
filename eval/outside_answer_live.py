"""One live card answered by someone outside the project (eval/outside_answer_rubric.json, committed before the card existed).

`card` opens the demo issue and merge request and lets the card flow open the extra's thread. Then the owner sends the link to one
person. `settle` runs only when that thread holds a reply from a person who is not one of the owner's accounts; it starts the reaction
flow with a bare mention and records what the flow did. Nothing here posts or edits an answer. Raw record: results/outside_answer_live.json.

usage (repository root, glab authenticated; spends Duo credits):
    python3 eval/outside_answer_live.py card --credit-stop 330
    python3 eval/outside_answer_live.py settle --credit-stop 333"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import react_study as R  # noqa: E402
from weight_live import read  # noqa: E402

OUT = R.ROOT / "results" / "outside_answer_live.json"
RUBRIC = json.loads((R.ROOT / "eval" / "outside_answer_rubric.json").read_text())
P = R.P
BRANCH = "demo/outside-answer"
DEPENDENCY = "rich==13.7.1"
NAME = "pyproject.toml"


def thread_of(iid: int):
    for d in R.discussions(iid):
        first = d["notes"][0]
        if "card" in first["author"]["username"] and "reply with its exact name" in first["body"]:
            return d
    return None


def outside_reply(thread: dict, is_person=lambda uid: R.api(f"users/{uid}").get("bot") is False):
    """The first reply in the thread from a person who is not one of the owner's accounts, or None."""
    for n in thread["notes"][1:]:
        who = n["author"]["username"]
        if n.get("system") or who in RUBRIC["owner_accounts"] or "itemator" in who:
            continue
        if is_person(n["author"]["id"]):
            return n
    return None


def card(rec: dict) -> dict:
    issue = R.api(f"projects/{P}/issues", "POST", title="What shipped: say that its times are UTC",
                  description="The What-shipped page shows deployment times without a time zone. Add one sentence to the docstring of "
                              "`itemator/shipped.py` saying that every time on the page is UTC. Nothing else is asked.")
    rec["issue_iid"] = issue["iid"]
    R.api(f"projects/{P}/repository/branches", "POST", branch=BRANCH, ref="main")
    src, py = read("itemator/shipped.py", BRANCH), read("pyproject.toml", BRANCH)
    assert src.count("and `shipped.json`.") == 1 and "dependencies = []" in py
    R.commit(BRANCH, "Say that the What-shipped page's times are UTC", [
        {"action": "update", "file_path": "itemator/shipped.py",
         "content": src.replace("and `shipped.json`.", "and `shipped.json`. Every time on the page is UTC.", 1)},
        {"action": "update", "file_path": "pyproject.toml", "content": py.replace("dependencies = []", f'dependencies = ["{DEPENDENCY}"]', 1)}])
    mr = R.api(f"projects/{P}/merge_requests", "POST", source_branch=BRANCH, target_branch="main",
               title="Say that the What-shipped page's times are UTC", description=f"Closes #{issue['iid']}\n\nOne docstring sentence.")
    iid = rec["mr_iid"] = mr["iid"]
    rec["mr_url"] = mr["web_url"]
    t0 = time.time()
    while time.time() - t0 < 900:
        pl = R.api(f"projects/{P}/merge_requests/{iid}/pipelines")
        if pl and pl[0]["status"] in ("success", "failed"):
            rec["pipeline"] = pl[0]["status"]
            break
        time.sleep(15)
    try:
        R.trigger("card", True)
        R.api(f"projects/{P}/merge_requests/{iid}", "PUT", reviewer_ids=R.CARD_USER)
        rec["card_done"] = R.wait_session_done(iid, "card", 1200)
    finally:
        R.trigger("card", False)
    time.sleep(5)
    t = thread_of(iid)
    rec["thread_url"] = f"{mr['web_url']}#note_{t['notes'][0]['id']}" if t else None
    rec["thread"] = t["notes"][0]["body"] if t else None
    return rec


def settle(rec: dict) -> dict:
    iid = rec["mr_iid"]
    t = thread_of(iid)
    reply = outside_reply(t) if t else None
    if not reply:
        print("no reply from someone outside the project yet; nothing started")
        rec["settle_refused"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        return rec
    rec["outside_reply"] = {"id": reply["id"], "at": reply["created_at"], "first_line": reply["body"].splitlines()[0]}
    try:
        R.trigger("react", True)
        R.api(f"projects/{P}/merge_requests/{iid}/notes", "POST", body=R.REACT_MENTION)
        rec["react_done"] = R.wait_session_done(iid, "react", 1200)
    finally:
        R.trigger("react", False)
    time.sleep(10)
    t = thread_of(iid)
    rec["settled"] = R.classify(t) if t else None
    notes = R.api(f"projects/{P}/merge_requests/{iid}/notes?per_page=100&sort=asc")
    rec["summary"] = next((n["body"] for n in reversed(notes) if "Every extra has an answer" in (n.get("body") or "")), None)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=("card", "settle"))
    ap.add_argument("--credit-stop", type=float, required=True)
    a = ap.parse_args()
    m = R.meter()
    if m is None or m >= a.credit_stop:
        print(f"meter {m}: at or over the stop {a.credit_stop}; nothing done")
        return 1
    rec = json.loads(OUT.read_text()) if OUT.exists() else {}
    if a.phase == "settle" and "mr_iid" not in rec:
        print("run the card phase first")
        return 1
    rec.setdefault("rubric", "eval/outside_answer_rubric.json")
    rec[f"{a.phase}_started"], rec[f"meter_before_{a.phase}"] = time.strftime("%Y-%m-%dT%H:%M:%S"), m
    rec = card(rec) if a.phase == "card" else settle(rec)
    rec[f"meter_after_{a.phase}"] = R.meter()
    OUT.write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps({k: rec.get(k) for k in ("mr_url", "pipeline", "card_done", "thread_url", "outside_reply", "react_done", "settled")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
