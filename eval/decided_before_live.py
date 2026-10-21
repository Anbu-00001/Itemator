"""The decided-before line, live (eval/decided_before_live_rubric.json, pushed before the run): one staged merge request
brings back two extras people already answered on other merge requests; the pipeline's itemator.json must say what was
decided before. CI only, no flow runs, no credits. Raw record: results/decided_before_live.json.

usage (repository root, glab authenticated): python3 eval/decided_before_live.py"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import react_study as R  # noqa: E402

OUT = R.ROOT / "results" / "decided_before_live.json"
P = R.P
BRANCH = "demo/decided-before"
WANT = {"rich": "Decided before: kept on !278 by francisdevasargunam on 2026-10-21 (public answer log).",
        "scratch.bak": "Decided before: removed on !17 by anbuchelvanganesan.cse2024 on 2026-10-11 (public answer log)."}


def checks(report: dict | None, before: dict, after: dict, flow_notes: int) -> dict:
    extras = {e["name"]: e.get("thread_stub", "") for e in (report or {}).get("extras") or ()}
    return {"D1_job_ran": report is not None,
            "D2_rich": extras.get("rich", "").endswith(WANT["rich"]),
            "D3_scratch": extras.get("scratch.bak", "").endswith(WANT["scratch.bak"]),
            "D4_record": (report or {}).get("decided_before") == {"read": True, "matched": 2},
            "D5_no_flow": bool(before) and not any(before.values()) and not any(after.values()),
            "D6_no_notes": flow_notes == 0}


def artifact(job_id: int) -> dict | None:
    r = subprocess.run(["glab", "api", f"projects/{P}/jobs/{job_id}/artifacts/itemator.json"], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def main() -> int:
    before = R.trigger_states()
    rec = {"staged": True, "branch": BRANCH, "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "triggers_before": before}
    issue = R.api(f"projects/{P}/issues", "POST", title="Parser: strip spaces around each item",
                  description="`parse` in `examples/parser.py` keeps the spaces around each item. Strip them. Nothing else is asked.")
    rec["issue_iid"] = issue["iid"]
    R.api(f"projects/{P}/repository/branches", "POST", branch=BRANCH, ref="main")
    py = (R.ROOT / "pyproject.toml").read_text().replace("dependencies = []", 'dependencies = ["rich>=13"]', 1)
    R.commit(BRANCH, "Strip spaces around each item", [
        {"action": "create", "file_path": "examples/parser.py",
         "content": "def parse(s):\n    \"\"\"Split on commas and strip the spaces around each item.\"\"\"\n    return [x.strip() for x in s.split(',')]\n"},
        {"action": "update", "file_path": "pyproject.toml", "content": py},
        {"action": "create", "file_path": "scratch.bak", "content": "notes from a local run\n"}])
    mr = R.api(f"projects/{P}/merge_requests", "POST", source_branch=BRANCH, target_branch="main",
               title="Strip spaces around each item", description=f"Closes #{issue['iid']}\n\nStaged for the decided-before live check.")
    iid = rec["mr_iid"] = mr["iid"]
    rec["mr_url"] = mr["web_url"]
    job, t0 = None, time.time()
    while time.time() - t0 < 1200:
        pl = R.api(f"projects/{P}/merge_requests/{iid}/pipelines")
        if pl and pl[0]["status"] in ("success", "failed", "canceled"):
            rec["pipeline"] = {"id": pl[0]["id"], "status": pl[0]["status"]}
            jobs = R.api(f"projects/{P}/pipelines/{pl[0]['id']}/jobs")
            job = next((j for j in jobs if j["name"] == "itemator"), None)
            break
        time.sleep(20)
    report = artifact(job["id"]) if job else None
    rec["itemator_job"] = job and {"id": job["id"], "status": job["status"], "url": job["web_url"]}
    rec["extras"] = [{"name": e["name"], "kind": e["kind"], "thread_stub": e.get("thread_stub")} for e in (report or {}).get("extras") or ()]
    rec["decided_before"] = (report or {}).get("decided_before")
    notes = R.api(f"projects/{P}/merge_requests/{iid}/notes?per_page=100") or []
    flow_notes = sum(1 for n in notes if (n["author"]["username"] or "").startswith("ai-itemator-"))
    rec["triggers_after"] = after = R.trigger_states()
    rec["checks"] = checks(report, before, after, flow_notes)
    R.api(f"projects/{P}/merge_requests/{iid}", "PUT", state_event="close")
    R.api(f"projects/{P}/issues/{issue['iid']}", "PUT", state_event="close")
    rec["left"] = "merge request and issue closed unmerged after recording"
    OUT.write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec["checks"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
