"""The filmed real-agent run (eval/film_real_agent_rubric.json, registered before it ran): GitLab's Developer Flow gets an
ordinary issue, opens its own merge request, the policy-injected job lists what goes beyond the issue, and the card flow opens
its threads. The answer is typed by the project owner on camera; `react` then starts the reaction flow on it. Nothing is merged.
Raw record: results/film_real_agent.json (one entry per issue).

usage (repository root, glab authenticated; spends Duo credits):
    python3 eval/film_real_agent.py start --issue 1 --credit-stop 360
    python3 eval/film_real_agent.py react --mr <iid>          # after the owner has typed an answer in a thread
    The second film: add --rubric eval/film_real_agent_v2_rubric.json --out results/film_real_agent_v2.json to both."""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import react_study as R  # noqa: E402

ROOT = R.ROOT
RUBRIC = ROOT / "eval" / "film_real_agent_rubric.json"
OUT = ROOT / "results" / "film_real_agent.json"
P = R.P
DEVELOPER = "duo-developer-gitlab-ai-hackathon"
OWNER = "anbuchelvanganesan.cse2024"
MR_WAIT, PIPELINE_WAIT, ANSWER_WAIT, POLL = 25 * 60, 20 * 60, 60 * 60, 20


def load() -> list:
    return json.loads(OUT.read_text()) if OUT.exists() else []


def save(records: list) -> None:
    OUT.write_text(json.dumps(records, indent=1) + "\n")


def find_mr(issue_iid: int):
    for m in R.api(f"projects/{P}/merge_requests?state=opened&per_page=30") or []:
        if re.search(rf"(work_items|issues)/{issue_iid}\b|#{issue_iid}\b", m.get("description") or ""):
            return m
    return None


def itemator_report(mr_iid: int):
    """(pipeline status, itemator.json) for the merge request's newest pipeline, once its itemator job has finished."""
    t0 = time.time()
    while time.time() - t0 < PIPELINE_WAIT:
        pls = R.api(f"projects/{P}/merge_requests/{mr_iid}/pipelines") or []
        if pls:
            jobs = R.api(f"projects/{P}/pipelines/{pls[0]['id']}/jobs?per_page=100") or []
            job = next((j for j in jobs if j["name"] == "itemator"), None)
            if job and job["status"] in ("success", "failed"):
                return pls[0]["status"], R.api(f"projects/{P}/jobs/{job['id']}/artifacts/itemator.json")
        time.sleep(POLL)
    return None, None


def start(n: int, credit_stop: float) -> int:
    issue = next(i for i in json.loads(RUBRIC.read_text())["issues"] if i["id"] == n)
    m0 = R.meter()
    if m0 is None or m0 >= credit_stop:
        print(f"meter {m0}: at or over the stop {credit_stop}; nothing done")
        return 1
    rec = {"issue": n, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "meter_before": m0}
    made = R.api(f"projects/{P}/issues", "POST", title=issue["title"], description=issue["description"])
    rec["issue_iid"] = made["iid"]
    R.api(f"projects/{P}/issues/{made['iid']}/notes", "POST", body=f"/assign @{DEVELOPER}")
    t0, mr = time.time(), None
    while time.time() - t0 < MR_WAIT and mr is None:
        time.sleep(POLL)
        mr = find_mr(made["iid"])
    if mr is None:
        rec["outcome"] = "no merge request within the time limit"
        save(load() + [rec])
        print(json.dumps(rec))
        return 1
    rec.update(mr_iid=mr["iid"], mr_author=mr["author"]["username"], seconds_to_mr=int(time.time() - t0))
    time.sleep(60)                                       # the agent may push more than once; let its pipeline settle
    rec["files_changed"] = [d["new_path"] for d in R.api(f"projects/{P}/merge_requests/{mr['iid']}/diffs?per_page=100") or []]
    status, report = itemator_report(mr["iid"])
    rec["pipeline"] = status
    if isinstance(report, dict):
        rec["itemator"] = {"state": report.get("state"), "extras": [{"kind": e["kind"], "name": e["name"]} for e in report.get("extras") or []],
                           "card": report.get("card")}
    t1 = time.time()
    try:
        R.trigger("card", True)
        R.api(f"projects/{P}/merge_requests/{mr['iid']}", "PUT", reviewer_ids=R.CARD_USER)
        rec["card_done"] = R.wait_session_done(mr["iid"], "card", 1800)
    finally:
        R.trigger("card", False)
    rec["card_minutes_after_pipeline"] = round((time.time() - t1) / 60, 1)
    time.sleep(5)
    rec["threads"] = [d["notes"][0]["body"] for d in R.discussions(mr["iid"]) if "card" in d["notes"][0]["author"]["username"]]
    rec["meter_after_card"] = R.meter()
    save(load() + [rec])
    print(json.dumps({k: rec.get(k) for k in ("issue_iid", "mr_iid", "files_changed", "pipeline", "card_done", "card_minutes_after_pipeline")}))
    print(json.dumps((rec.get("itemator") or {}).get("extras")))
    return 0


def react(mr_iid: int) -> int:
    records = load()
    rec = next(r for r in records if r.get("mr_iid") == mr_iid)
    t0, answer = time.time(), None
    while time.time() - t0 < ANSWER_WAIT and answer is None:
        for d in R.discussions(mr_iid):
            first = d["notes"][0]
            if "card" in first["author"]["username"]:
                answer = next((x for x in d["notes"][1:] if x["author"]["username"] == OWNER and not x["system"]), None) or answer
        if answer is None:
            time.sleep(POLL)
    if answer is None:
        print("no answer from the owner within the hour; nothing started")
        return 1
    rec["owner_answer"] = answer["body"][:200]
    try:
        R.trigger("react", True)
        R.api(f"projects/{P}/merge_requests/{mr_iid}/notes", "POST", body=f"{R.REACT_MENTION} check")
        rec["react_done"] = R.wait_session_done(mr_iid, "react", 1800)
    finally:
        R.trigger("react", False)
    time.sleep(10)
    rec["settled"] = [R.classify(d) for d in R.discussions(mr_iid) if "card" in d["notes"][0]["author"]["username"]]
    rec["meter_after_react"] = R.meter()
    save(records)
    print(json.dumps({k: rec.get(k) for k in ("owner_answer", "react_done", "settled", "meter_after_react")}))
    return 0


def main() -> int:
    global RUBRIC, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--rubric", type=pathlib.Path, default=RUBRIC)
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--issue", type=int, required=True, choices=(1, 2))
    s.add_argument("--credit-stop", type=float, required=True)
    r = sub.add_parser("react")
    r.add_argument("--mr", type=int, required=True)
    a = ap.parse_args()
    RUBRIC, OUT = a.rubric, a.out
    return start(a.issue, a.credit_stop) if a.cmd == "start" else react(a.mr)


if __name__ == "__main__":
    sys.exit(main())
