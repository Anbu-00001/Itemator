"""Bypass matrix for the optional hold (names.hold_until_named): eight pre-registered attempts (eval/bypass_matrix_cases.json) to merge
a merge request with an unnamed extra. API only, no Duo credits (no flow is started): one throwaway target branch with the hold on,
one merge request per scenario, a merge attempt after the pipeline has finished. Merges go only into the throwaway target branch.
usage (repository root, glab authenticated): python3 eval/bypass_matrix.py [--summarize]
Raw record results/bypass_matrix_raw.json, counts results/bypass_matrix.json. Scenario 7 uses the second account's token file."""
from __future__ import annotations

import argparse, base64, json, os, pathlib, re, subprocess, sys, time, urllib.parse, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import react_study as R

ROOT = R.ROOT
CASES, RAW, OUT = ROOT / "eval" / "bypass_matrix_cases.json", ROOT / "results" / "bypass_matrix_raw.json", ROOT / "results" / "bypass_matrix.json"
P, TARGET = R.P, "probe/bm-target"
SIGN = R.SIGN


def second(method, path, **fields):
    tok = pathlib.Path("~/.itemator-second-token").expanduser().read_text().strip()
    req = urllib.request.Request(f"https://gitlab.com/api/v4/{path}", data=urllib.parse.urlencode(fields).encode() if fields else None,
                                 method=method, headers={"PRIVATE-TOKEN": tok})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"null")


def read(path, ref):
    return base64.b64decode(R.api(f"projects/{P}/repository/files/{path.replace('/', '%2F')}?ref={ref}")["content"]).decode()


def job_block(ci):
    m = re.search(r"(?m)^itemator:\n(?:[ \t].*\n|\n)*", ci)
    assert m, "no itemator job in the CI file"
    return m


def edit_ci(ci, scenario):
    ci = "# probe: ordering note\n" + ci            # the extra: a CI-file change the issue never mentions
    m = job_block(ci)
    block = m.group(0)
    if scenario == "job deleted":
        return ci.replace(block, "")
    if scenario == "allowed to fail":
        return ci.replace(block, block.replace("itemator:\n", "itemator:\n  allow_failure: true\n", 1))
    if scenario == "script emptied":
        return ci.replace(block, re.sub(r"(?m)^  script:\n(?:    .*\n|\n)*", "  script:\n    - \"true\"\n", block, count=1))
    if scenario == "job never runs":
        return ci.replace(block, re.sub(r"(?m)^  rules:\n(?:    .*\n)*", "  rules:\n    - when: never\n", block, count=1))
    return ci


def pipeline(iid, timeout=480):
    t0 = time.time()
    while time.time() - t0 < timeout:
        pl = R.api(f"projects/{P}/merge_requests/{iid}/pipelines")
        if pl and pl[0]["status"] in ("success", "failed", "canceled"):
            return pl[0]
        time.sleep(10)


def attempt_merge(iid):
    r = subprocess.run(["glab", "api", "-X", "PUT", f"projects/{P}/merge_requests/{iid}/merge"], capture_output=True, text=True)
    m = R.api(f"projects/{P}/merge_requests/{iid}")
    return {"state": m["state"], "http_ok": r.returncode == 0, "detail": (r.stdout or r.stderr)[:160], "status": m.get("detailed_merge_status")}


def run():
    doc = json.loads(CASES.read_text())
    rec = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": []}
    issue = R.api(f"projects/{P}/issues", "POST", title="Probe: fix a typo in the README (bypass matrix)", description="Fix one typo in the README heading. Nothing else is asked.")
    R.api(f"projects/{P}/repository/branches", "POST", branch=TARGET, ref="main")
    pol = read(".itemator.toml", TARGET)
    R.commit(TARGET, "Hold until named (test target only)", [{"action": "update", "file_path": ".itemator.toml",
             "content": pol.replace("other_person_required = false", "other_person_required = false\nhold_until_named = true", 1)}])
    rd, ci = read("README.md", TARGET), read(".gitlab-ci.yml", TARGET)
    made = []
    for sc in doc["scenarios"]:
        br = f"probe/bm-{sc['id']}"
        R.api(f"projects/{P}/repository/branches", "POST", branch=br, ref=TARGET)
        msg = "Fix a typo in the README" + (" [ci skip]" if sc["name"] == "ci skip" else "")
        R.commit(br, msg, [{"action": "update", "file_path": "README.md", "content": rd.replace("## Related tools\n", "## Related tools:\n", 1)},
                           {"action": "update", "file_path": ".gitlab-ci.yml", "content": edit_ci(ci, sc["name"])}])
        mr = R.api(f"projects/{P}/merge_requests", "POST", source_branch=br, target_branch=TARGET,
                   title=f"Bypass {sc['id']}: {sc['name']}", description=f"Closes #{issue['iid']}")
        made.append((sc, br, mr["iid"]))
    for sc, br, iid in made:
        row = {"id": sc["id"], "name": sc["name"], "expected": sc["expected"], "mr_iid": iid}
        pl = pipeline(iid) if sc["name"] != "ci skip" else None
        if sc["name"] == "ci skip":
            time.sleep(60)
            pls = R.api(f"projects/{P}/merge_requests/{iid}/pipelines")
            pl = pls[0] if pls else None
        row["pipeline"] = pl["status"] if pl else "none"
        if pl:
            jobs = {j["name"]: j["status"] for j in R.api(f"projects/{P}/pipelines/{pl['id']}/jobs")}
            row["itemator_job"] = jobs.get("itemator", "absent")
            if sc["name"] == "forged summary":
                head = R.api(f"projects/{P}/merge_requests/{iid}")["diff_refs"]["head_sha"]
                second("POST", f"projects/{P}/merge_requests/{iid}/notes", body=f"Every extra has an answer: 1 kept.\n\n[//]: # (itemator:named={head})")
                jid = [j["id"] for j in R.api(f"projects/{P}/pipelines/{pl['id']}/jobs") if j["name"] == "itemator"]
                if jid:
                    R.api(f"projects/{P}/jobs/{jid[0]}/retry", "POST"); time.sleep(20); pl = pipeline(iid)
                    row["pipeline_after_retry"] = pl["status"] if pl else "none"
            if sc["name"] == "retry without names":
                jid = [j["id"] for j in R.api(f"projects/{P}/pipelines/{pl['id']}/jobs") if j["name"] == "itemator"]
                if jid:
                    R.api(f"projects/{P}/jobs/{jid[0]}/retry", "POST"); time.sleep(20); pl = pipeline(iid)
                    row["pipeline_after_retry"] = pl["status"] if pl else "none"
        got = attempt_merge(iid)
        row.update(got); row["outcome"] = "merged" if got["state"] == "merged" else "blocked"
        row["match"] = row["outcome"] == sc["expected"]
        rec["results"].append(row)
        print(f"{sc['id']} {sc['name']:22} expected {sc['expected']:8} got {row['outcome']:8} {'OK' if row['match'] else 'MISMATCH'}  pipeline {row['pipeline']}", flush=True)
    for sc, br, iid in made:
        for f in (lambda: R.api(f"projects/{P}/merge_requests/{iid}", "PUT", state_event="close"),
                  lambda: R.api(f"projects/{P}/repository/branches/{br.replace('/', '%2F')}", "DELETE")):
            try: f()
            except Exception: pass
    for f in (lambda: R.api(f"projects/{P}/issues/{issue['iid']}", "PUT", state_event="close"),
              lambda: R.api(f"projects/{P}/repository/branches/{TARGET.replace('/', '%2F')}", "DELETE")):
        try: f()
        except Exception: pass
    return rec


def summarize(runs):
    rows = [r for x in runs for r in x["results"]]
    return {"what": "Eight pre-registered attempts to merge a merge request with an unnamed extra past the optional hold (eval/bypass_matrix_cases.json). Counts only.",
            "limits": "Eight scenarios we thought of, one run each, one project. It counts what we tried, not what is possible.",
            "attempts": len(rows), "merged": len([r for r in rows if r["outcome"] == "merged"]), "blocked": len([r for r in rows if r["outcome"] == "blocked"]),
            "as_expected": len([r for r in rows if r["match"]]),
            "merged_scenarios": [r["name"] for r in rows if r["outcome"] == "merged"], "blocked_scenarios": [r["name"] for r in rows if r["outcome"] == "blocked"],
            "mismatches": [{"name": r["name"], "expected": r["expected"], "got": r["outcome"]} for r in rows if not r["match"]]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--summarize", action="store_true"); a = ap.parse_args()
    runs = json.loads(RAW.read_text()) if RAW.exists() else []
    if a.summarize:
        OUT.write_text(json.dumps(summarize(runs), indent=1) + "\n"); print("wrote", OUT.name); return 0
    rec = run(); runs.append(rec); RAW.write_text(json.dumps(runs, indent=1) + "\n"); return 0


if __name__ == "__main__":
    sys.exit(main())
