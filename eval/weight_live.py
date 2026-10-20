"""The weight, live (eval/weight_live_rubric.json, registered before it ran): a merge request into main whose issue asks for a small
change and whose diff also adds a dependency the issue never names (pandas, in pyproject.toml). The policy-injected job weighs it,
the card flow opens its thread, the author replies `remove`, and the reaction flow takes the line out. The merge request is left
open for a person to merge, so the decision log and the What-shipped page can then show what the `remove` kept out.
Raw record: results/weight_live.json.

usage (repository root, glab authenticated; spends Duo credits, one card run and one reaction run):
    python3 eval/weight_live.py --credit-stop 320"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import react_study as R  # noqa: E402

ROOT = R.ROOT
OUT = ROOT / "results" / "weight_live.json"
P = R.P
BRANCH = "demo/weight-remove"
DEPENDENCY = "pandas==2.2.3"


def read(path, ref):
    return base64.b64decode(R.api(f"projects/{P}/repository/files/{path.replace('/', '%2F')}?ref={ref}")["content"]).decode()


def run() -> dict:
    rec = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "meter_before": R.meter()}
    issue = R.api(f"projects/{P}/issues", "POST", title="Decision log: say which time zone the window uses",
                  description="The decision log's window is in UTC, but its markdown section does not say so. Add a short note to the "
                              "docstring of `itemator/decisions.py` saying that every time in the window is UTC. Nothing else is asked.")
    rec["issue_iid"] = issue["iid"]
    R.api(f"projects/{P}/repository/branches", "POST", branch=BRANCH, ref="main")
    src, py = read("itemator/decisions.py", BRANCH), read("pyproject.toml", BRANCH)
    assert "dependencies = []" in py
    R.commit(BRANCH, "Say that the decision log's window is in UTC", [
        {"action": "update", "file_path": "itemator/decisions.py",
         "content": src.replace("Standard library only.\n", "Standard library only. Every time in the window is UTC.\n", 1)},
        {"action": "update", "file_path": "pyproject.toml", "content": py.replace("dependencies = []", f'dependencies = ["{DEPENDENCY}"]', 1)}])
    mr = R.api(f"projects/{P}/merge_requests", "POST", source_branch=BRANCH, target_branch="main",
               title="Say that the decision log's window is in UTC", description=f"Closes #{issue['iid']}\n\nOne docstring line.")
    iid = rec["mr_iid"] = mr["iid"]
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
    thread = None
    for d in R.discussions(iid):
        first = d["notes"][0]
        if "card" in first["author"]["username"] and first["body"].startswith("`pandas`"):
            thread = d
    rec["thread"] = thread["notes"][0]["body"] if thread else None
    rec["weight_sentence"] = bool(thread) and "to download on every fresh install" in rec["thread"]
    rec["pipelines_sentence"] = bool(thread) and "pipelines in the last 30 days" in rec["thread"]
    if thread:
        R.api(f"projects/{P}/merge_requests/{iid}/discussions/{thread['id']}/notes", "POST", body="remove")
        try:
            R.trigger("react", True)
            R.api(f"projects/{P}/merge_requests/{iid}/notes", "POST", body=f"{R.REACT_MENTION} check")
            rec["react_done"] = R.wait_session_done(iid, "react", 1200)
        finally:
            R.trigger("react", False)
        time.sleep(10)
        by_id = {d["id"]: d for d in R.discussions(iid)}
        rec["settled"] = R.classify(by_id[thread["id"]])
    rec["pyproject_after"] = read("pyproject.toml", BRANCH)
    rec["removed_from_branch"] = DEPENDENCY not in rec["pyproject_after"]
    notes = R.api(f"projects/{P}/merge_requests/{iid}/notes?per_page=100&sort=asc")
    rec["summary"] = next((n["body"] for n in reversed(notes) if "Every extra has an answer" in (n.get("body") or "")), None)
    rec["meter_after"] = R.meter()
    rec["left_open_for_a_person_to_merge"] = True
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--credit-stop", type=float, required=True)
    a = ap.parse_args()
    m = R.meter()
    if m is None or m >= a.credit_stop:
        print(f"meter {m}: at or over the stop {a.credit_stop}; nothing done")
        return 1
    rec = run()
    OUT.write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps({k: rec.get(k) for k in ("mr_iid", "pipeline", "card_done", "weight_sentence", "pipelines_sentence", "react_done",
                                               "removed_from_branch", "meter_before", "meter_after")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
