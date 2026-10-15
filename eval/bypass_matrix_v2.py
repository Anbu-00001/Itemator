"""Bypass matrix v2 (after the itemator job moved into a pipeline execution policy): eleven pre-registered attempts
(eval/bypass_matrix_v2_cases.json) to merge a merge request with an unnamed extra past the optional hold. API only, no Duo credits (no flow
is started): one throwaway target branch with the hold on, one merge request per scenario, a merge attempt after the pipeline has finished.
Merges go only into the throwaway target branch. The raw record keeps the status of every job, so a block can be attributed to the
`itemator` job (the hold) or to some other job.
usage (repository root, glab authenticated): python3 eval/bypass_matrix_v2.py [--summarize]
Raw record results/bypass_matrix_v2_raw.json, counts results/bypass_matrix_v2.json."""
from __future__ import annotations

import argparse, json, pathlib, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import react_study as R
import bypass_matrix as B

ROOT, P = R.ROOT, R.P
CASES, RAW, OUT = ROOT / "eval" / "bypass_matrix_v2_cases.json", ROOT / "results" / "bypass_matrix_v2_raw.json", ROOT / "results" / "bypass_matrix_v2.json"
TARGET = "probe/bm2-target"
OWNER = "anbuchelvanganesan.cse2024"
JOB_FILE_NOOP = 'itemator:\n  stage: .pipeline-policy-post\n  image: alpine:3.20\n  script:\n    - "true"\n'


def edits(name, ci, readme, ci_job, checker):
    """The files a scenario changes, besides the README typo: {path: new content}."""
    base = "# probe: ordering note\n" + ci
    if name == "project jobs deleted":
        return {".gitlab-ci.yml": 'noop:\n  script: ["true"]\n'}
    if name == "fake itemator allowed to fail":
        return {".gitlab-ci.yml": base + '\nitemator:\n  allow_failure: true\n  script: ["exit 1"]\n'}
    if name == "fake itemator passes":
        return {".gitlab-ci.yml": base + '\nitemator:\n  script: ["true"]\n'}
    if name == "workflow never":
        return {".gitlab-ci.yml": "workflow:\n  rules:\n    - when: never\n" + base}
    if name == "job file edited":
        return {".gitlab-ci.yml": base, "ci/itemator-job.yml": JOB_FILE_NOOP}
    if name == "checker edited":
        return {".gitlab-ci.yml": base, "itemator/ci.py": "import sys\nsys.exit(0)\n" + checker}
    if name == "bot variable overridden":
        return {".gitlab-ci.yml": f"variables:\n  ITEMATOR_REACT_BOT: {OWNER}\n" + base}
    return {".gitlab-ci.yml": base}          # plain, ci skip, retry without names, forged summary


def jobs_of(pl):
    return {j["name"]: j["status"] for j in R.api(f"projects/{P}/pipelines/{pl['id']}/jobs")}


def retry_itemator(pl):
    ids = [j["id"] for j in R.api(f"projects/{P}/pipelines/{pl['id']}/jobs") if j["name"].startswith("itemator")]
    done = False
    for jid in ids:
        try:
            R.api(f"projects/{P}/jobs/{jid}/retry", "POST")
            done = True
        except RuntimeError:                  # a skipped job cannot be retried: record it, do not stop the run
            pass
    return done


def run(runs_so_far=()):
    runs_so_far = list(runs_so_far)
    doc = json.loads(CASES.read_text())
    rec = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": []}
    issue = R.api(f"projects/{P}/issues", "POST", title="Probe: fix a typo in the README (bypass matrix v2)", description="Fix one typo in the README heading. Nothing else is asked.")
    R.api(f"projects/{P}/repository/branches", "POST", branch=TARGET, ref="main")
    pol = B.read(".itemator.toml", TARGET)
    R.commit(TARGET, "Hold until named (test target only)", [{"action": "update", "file_path": ".itemator.toml",
             "content": pol.replace("other_person_required = false", "other_person_required = false\nhold_until_named = true", 1)}])
    rd, ci = B.read("README.md", TARGET), B.read(".gitlab-ci.yml", TARGET)
    ci_job, checker = B.read("ci/itemator-job.yml", TARGET), B.read("itemator/ci.py", TARGET)
    made = []
    for sc in doc["scenarios"]:
        br = f"probe/bm2-{sc['id']}"
        R.api(f"projects/{P}/repository/branches", "POST", branch=br, ref=TARGET)
        msg = "Fix a typo in the README" + (" [ci skip]" if sc["name"] == "ci skip" else "")
        acts = [{"action": "update", "file_path": "README.md", "content": rd.replace("## Related tools\n", "## Related tools:\n", 1)}]
        for path, content in edits(sc["name"], ci, rd, ci_job, checker).items():
            acts.append({"action": "update", "file_path": path, "content": content})
        R.commit(br, msg, acts)
        mr = R.api(f"projects/{P}/merge_requests", "POST", source_branch=br, target_branch=TARGET,
                   title=f"Bypass v2 {sc['id']}: {sc['name']}", description=f"Closes #{issue['iid']}")
        made.append((sc, br, mr["iid"]))
    for sc, br, iid in made:
        row = {"id": sc["id"], "name": sc["name"], "expected": sc["expected"], "mr_iid": iid}
        if sc["name"] in ("ci skip", "workflow never"):
            time.sleep(75)
            pls = R.api(f"projects/{P}/merge_requests/{iid}/pipelines")
            pl = pls[0] if pls else None
            if pl and pl["status"] not in ("success", "failed", "canceled"):
                pl = B.pipeline(iid)
        else:
            pl = B.pipeline(iid)
        row["pipeline"] = pl["status"] if pl else "none"
        if pl:
            row["jobs"] = jobs_of(pl)
            if sc["name"] in ("forged summary", "bot variable overridden"):
                head = R.api(f"projects/{P}/merge_requests/{iid}")["diff_refs"]["head_sha"]
                R.api(f"projects/{P}/merge_requests/{iid}/notes", "POST", body=f"Every extra has an answer: 1 kept.\n\n[//]: # (itemator:named={head})")
                row["forged_note_posted_by"] = OWNER
            if sc["name"] in ("retry without names", "forged summary", "bot variable overridden"):
                row["retried"] = retry_itemator(pl)
                time.sleep(25)
                pl = B.pipeline(iid)
                row["pipeline_after_retry"] = pl["status"] if pl else "none"
                if pl:
                    row["jobs_after_retry"] = jobs_of(pl)
        got = B.attempt_merge(iid)
        row.update(got); row["outcome"] = "merged" if got["state"] == "merged" else "blocked"
        row["match"] = row["outcome"] == sc["expected"]
        final = row.get("jobs_after_retry") or row.get("jobs") or {}
        row["itemator_job_statuses"] = {k: v for k, v in final.items() if k.startswith("itemator")}
        row["itemator_job_failed"] = any(v == "failed" for v in row["itemator_job_statuses"].values())
        row["other_job_failed"] = any(v == "failed" for k, v in final.items() if not k.startswith("itemator"))
        rec["results"].append(row)
        RAW.write_text(json.dumps(runs_so_far + [rec], indent=1) + "\n")      # keep every finished scenario even if a later one crashes
        print(f"{sc['id']:2} {sc['name']:30} expected {sc['expected']:8} got {row['outcome']:8} {'OK' if row['match'] else 'MISMATCH'}  pipeline {row['pipeline']}  itemator {row['itemator_job_statuses']}", flush=True)
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
    return {"what": "Eleven pre-registered attempts to merge a merge request with an unnamed extra past the optional hold, after the itemator job moved into a pipeline execution policy (eval/bypass_matrix_v2_cases.json). Counts only.",
            "limits": "Eleven attempts we thought of, one run each, one project. It counts what we tried, not what is possible.",
            "attempts": len(rows), "merged": len([r for r in rows if r["outcome"] == "merged"]), "blocked": len([r for r in rows if r["outcome"] == "blocked"]),
            "as_expected": len([r for r in rows if r["match"]]),
            "blocked_by_the_itemator_job": len([r for r in rows if r["outcome"] == "blocked" and r["itemator_job_failed"]]),
            "blocked_only_by_another_job": [r["name"] for r in rows if r["outcome"] == "blocked" and not r["itemator_job_failed"]],
            "merged_scenarios": [r["name"] for r in rows if r["outcome"] == "merged"], "blocked_scenarios": [r["name"] for r in rows if r["outcome"] == "blocked"],
            "mismatches": [{"name": r["name"], "expected": r["expected"], "got": r["outcome"]} for r in rows if not r["match"]]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--summarize", action="store_true"); a = ap.parse_args()
    runs = json.loads(RAW.read_text()) if RAW.exists() else []
    if a.summarize:
        OUT.write_text(json.dumps(summarize(runs), indent=1) + "\n"); print("wrote", OUT.name); return 0
    rec = run(runs); runs.append(rec); RAW.write_text(json.dumps(runs, indent=1) + "\n"); return 0


if __name__ == "__main__":
    sys.exit(main())
