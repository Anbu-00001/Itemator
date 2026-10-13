"""Field study: real Duo Developer Flow runs on this repository, measured with the Itemator job.

Pre-registered issue list: eval/field_study_issues.json (committed before the first run). For each issue, one at a time:
create the issue, assign the Duo Developer service account, wait for the merge request it opens and for that merge
request's pipeline, read the `itemator` job's itemator.json, count the session's tool calls, then close the merge
request and the issue and delete the branch. Nothing is merged. Raw records go to results/field_study_raw.json after
every run, so a stopped run resumes where it stopped.

usage (from the repository root, glab authenticated):
    python3 eval/field_study.py --dry-run                 # print the plan only
    python3 eval/field_study.py --max 2 --credit-stop 160 # run at most 2 issues; stop if the meter reads 160 or more
    python3 eval/field_study.py --summarize               # write results/field_study.json from the raw records
Standard library only. Network: the GitLab API through `glab api` (this project only).
"""
from __future__ import annotations

import argparse, json, pathlib, re, subprocess, sys, time, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
ISSUES = ROOT / "eval" / "field_study_issues.json"
RAW = ROOT / "results" / "field_study_raw.json"
OUT = ROOT / "results" / "field_study.json"
PROJECT = 87291130
NAMESPACE = "gitlab-ai-hackathon"
DEVELOPER = "duo-developer-gitlab-ai-hackathon"
MR_WAIT, PIPELINE_WAIT, POLL = 15 * 60, 12 * 60, 20      # seconds: agent run, pipeline, spacing of polls


def glab(*args: str, method: str = "GET", fields: dict | None = None, retries: int = 3):
    cmd = ["glab", "api", *(["-X", method] if method != "GET" else []), *args]
    for k, v in (fields or {}).items():
        cmd += ["-f", f"{k}={v}"]
    for attempt in range(retries):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            try:
                return json.loads(r.stdout) if r.stdout.strip() else None
            except json.JSONDecodeError:
                return r.stdout
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"glab {' '.join(args)[:80]} failed: {r.stderr.strip()[:160]}")


def meter() -> float | None:
    r = subprocess.run(["glab", "api", "graphql", "-f",
                        f'query={{ currentUser {{ creditsUsage(namespacePath:"{NAMESPACE}") {{ creditsUsed }} }} }}'],
                       capture_output=True, text=True, timeout=60)
    try:
        return float(json.loads(r.stdout)["data"]["currentUser"]["creditsUsage"]["creditsUsed"])
    except Exception:
        return None


def tool_calls(session_id: str) -> int | None:
    try:
        cps = glab(f"ai/duo_workflows/workflows/{session_id}/checkpoints?per_page=100")
        best = 0
        for c in cps or []:
            ck = c["checkpoint"]
            ck = json.loads(ck) if isinstance(ck, str) else ck
            conv = ck["channel_values"].get("conversation_history", {})
            n = sum(len(m.get("kwargs", m).get("tool_calls") or []) for msgs in conv.values() for m in msgs)
            best = max(best, n)
        return best
    except Exception:
        return None


def run_one(issue: dict) -> dict:
    t0 = time.time()
    rec = {"id": issue["id"], "kind": issue["kind"], "title": issue["title"], "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    made = glab(f"projects/{PROJECT}/issues", method="POST", fields={"title": issue["title"], "description": issue["description"]})
    iid = made["iid"]; rec["issue_iid"] = iid
    glab(f"projects/{PROJECT}/issues/{iid}/notes", method="POST", fields={"body": f"/assign @{DEVELOPER}"})
    mr = None
    while time.time() - t0 < MR_WAIT and mr is None:
        time.sleep(POLL)
        for m in glab(f"projects/{PROJECT}/merge_requests?state=opened&per_page=30") or []:
            if re.search(rf"(work_items|issues)/{iid}\b|#{iid}\b", m.get("description") or ""):
                mr = m; break
    if mr is None:
        rec["outcome"] = "no merge request within the time limit"
        cleanup(iid, None, None)
        return rec
    rec["mr_iid"], rec["branch"], rec["seconds_to_mr"] = mr["iid"], mr["source_branch"], int(time.time() - t0)
    rec["mr_title"] = mr["title"]; rec["mr_description"] = mr.get("description") or ""
    notes = glab(f"projects/{PROJECT}/issues/{iid}/notes?per_page=50") or []
    sess = [m.group(1) for n in notes for m in [re.search(r"agent-sessions/(\d+)", n.get("body") or "")] if m]
    rec["session_id"] = sess[0] if sess else None
    rec["tool_calls"] = tool_calls(sess[0]) if sess else None
    diffs = glab(f"projects/{PROJECT}/merge_requests/{mr['iid']}/diffs?per_page=100") or []
    rec["files_changed"] = [d["new_path"] for d in diffs]
    t1, status, job = time.time(), None, None
    while time.time() - t1 < PIPELINE_WAIT:
        pls = [p for p in glab(f"projects/{PROJECT}/merge_requests/{mr['iid']}/pipelines") or [] if p["source"] == "merge_request_event"]
        if pls and pls[0]["status"] in ("success", "failed", "canceled"):
            status = pls[0]["status"]
            jobs = glab(f"projects/{PROJECT}/pipelines/{pls[0]['id']}/jobs") or []
            job = next((j for j in jobs if j["name"] == "itemator"), None)
            if job and job["status"] in ("success", "failed"):
                break
        time.sleep(POLL)
    rec["pipeline_status"] = status
    if job:
        try:
            art = glab(f"projects/{PROJECT}/jobs/{job['id']}/artifacts/itemator.json")
            rec["itemator"] = {"rules_version": art.get("rules_version"), "state": art.get("state"),
                               "extras": [{"kind": e["kind"], "name": e["name"], "said": (e.get("plain_facts") or {}).get("said")} for e in art.get("extras", [])],
                               "unplaced": len(art.get("unplaced") or []), "card": art.get("card"), "checker": art.get("checker")}
        except Exception as e:
            rec["itemator_error"] = str(e)[:160]
    rec.update(beyond_section(rec["mr_description"]))
    rec["seconds_total"] = int(time.time() - t0)
    cleanup(iid, mr["iid"], mr["source_branch"])
    return rec


def beyond_section(description: str) -> dict:
    """The skill asks for a "## Beyond the issue" section ending in `Nothing.` when the change stays inside the issue."""
    m = re.search(r"beyond the issue\s*\n(.*?)(?:\n#|\Z)", description, re.I | re.S)
    body = m.group(1).strip() if m else ""
    return {"has_beyond_section": bool(m), "beyond_names_something": bool(m) and body.rstrip(".").lower() != "nothing" and bool(body)}


def cleanup(issue_iid, mr_iid, branch):
    if mr_iid:
        glab(f"projects/{PROJECT}/merge_requests/{mr_iid}", method="PUT", fields={"state_event": "close"})
    glab(f"projects/{PROJECT}/issues/{issue_iid}", method="PUT", fields={"state_event": "close"})
    if branch:
        try:
            glab(f"projects/{PROJECT}/repository/branches/{urllib.parse.quote(branch, safe='')}", method="DELETE")
        except Exception:
            pass


def summarize(records: list[dict]) -> dict:
    ok = [r for r in records if r.get("itemator")]
    with_extras = [r for r in ok if r["itemator"]["extras"]]
    n_extras = sum(len(r["itemator"]["extras"]) for r in ok)
    said = {"listed": 0, "named": 0, "silent": 0, "no_sentence": 0}
    for r in ok:
        for e in r["itemator"]["extras"]:
            said[e["said"] or "no_sentence"] += 1
    calls = [r["tool_calls"] for r in records if r.get("tool_calls") is not None]
    return {
        "what": "Real Duo Developer Flow runs on this repository, one issue each, measured by the itemator job (rules v6). Counts, not precision. Pre-registered issues: eval/field_study_issues.json.",
        "limits": "Few runs, one repository, one agent, our own issues, our AGENTS.md and the stay-inside-the-issue skill in place. Nothing was merged.",
        "issues_run": len(records), "merge_requests_opened": len([r for r in records if r.get("mr_iid")]),
        "read_by_the_job": len(ok), "with_extras": len(with_extras), "extras": n_extras,
        "extras_said": said,
        "descriptions_with_a_beyond_section": len([r for r in records if r.get("has_beyond_section")]),
        "descriptions_listing_something_under_the_heading": len([r for r in records if r.get("beyond_names_something")]),   # may list what the issue asked for
        "tool_calls_median": sorted(calls)[len(calls) // 2] if calls else None,
        "tool_calls_total": sum(calls) if calls else None,
        "per_issue": [{"id": r["id"], "kind": r["kind"], "mr_iid": r.get("mr_iid"), "files_changed": r.get("files_changed"),
                       "state": (r.get("itemator") or {}).get("state"),
                       "extras": [(e["kind"], e["name"]) for e in (r.get("itemator") or {}).get("extras", [])],
                       "tool_calls": r.get("tool_calls"), "seconds_total": r.get("seconds_total"),
                       "pipeline_status": r.get("pipeline_status")} for r in records],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--summarize", action="store_true")
    ap.add_argument("--max", type=int, default=1); ap.add_argument("--credit-stop", type=float, default=0.0)
    a = ap.parse_args()
    spec = json.loads(ISSUES.read_text())
    records = json.loads(RAW.read_text()) if RAW.exists() else []
    if a.summarize:
        OUT.write_text(json.dumps(summarize(records), indent=1) + "\n"); print(f"wrote {OUT.relative_to(ROOT)}"); return 0
    todo = [i for i in spec["issues"] if i["id"] not in {r["id"] for r in records}]
    print(f"{len(records)} done, {len(todo)} to do; this run: {min(a.max, len(todo))}")
    if a.dry_run:
        for i in todo[: a.max]: print("  would run:", i["id"], i["kind"], i["title"])
        return 0
    for issue in todo[: a.max]:
        m = meter()
        print(f"meter {m}", flush=True)
        if a.credit_stop and m is not None and m >= a.credit_stop:
            print("credit stop reached; not starting another run"); break
        rec = run_one(issue)
        records.append(rec); RAW.write_text(json.dumps(records, indent=1) + "\n")
        print(f"issue {issue['id']}: mr {rec.get('mr_iid')}, calls {rec.get('tool_calls')}, "
              f"extras {[(e['kind'], e['name']) for e in (rec.get('itemator') or {}).get('extras', [])]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
