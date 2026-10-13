"""Reply study for the reaction flow: eight pre-registered reply cases (eval/react_study_cases.json) on one throwaway
merge request. The card flow opens one thread per extra; this script types each case's reply as the merge
request author, starts the reaction flow once with a mention, then reads what happened to every thread and compares it with
the expected outcome written down before the run. Raw record: results/react_study_raw.json; counts: results/react_study.json.

usage (repository root, glab authenticated; spends Duo credits: one card run and one reaction run):
    python3 eval/react_study.py --credit-stop 172     # run once; refuses to start when the meter reads that or more
    python3 eval/react_study.py --summarize
Standard library only. Triggers are switched on only while a flow runs and are always switched off again.
"""
from __future__ import annotations

import argparse, base64, json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
CASES = ROOT / "eval" / "react_study_cases.json"
RAW = ROOT / "results" / "react_study_raw.json"
OUT = ROOT / "results" / "react_study.json"
P, NS = 87291130, "gitlab-ai-hackathon"
CARD_USER, REACT_MENTION = 43246470, "@ai-itemator-react-gitlab-ai-hackathon"
TRIG = {"card": "gid://gitlab/Ai::FlowTrigger/3014359", "react": "gid://gitlab/Ai::FlowTrigger/3014366"}
SIGN = "\n\nSigned-off-by: Anbu <39194174-anbuchelvanganesan.cse2024@users.noreply.gitlab.com>"
BRANCHES = ("probe/rs-src", "probe/rs-target")


def api(path, method="GET", **fields):
    cmd = ["glab", "api"] + (["-X", method] if method != "GET" else []) + [path]
    for k, v in fields.items():
        cmd += ["-f", f"{k}={v}"]
    for attempt in range(3):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            return json.loads(r.stdout) if r.stdout.strip() else None
        time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"{path}: {r.stderr.strip()[:200]}")


def commit(branch, message, actions):
    body = json.dumps({"branch": branch, "commit_message": message + SIGN, "actions": actions})
    r = subprocess.run(["glab", "api", "-X", "POST", f"projects/{P}/repository/commits", "--input", "-",
                        "-H", "Content-Type: application/json"], input=body, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[:200] + r.stdout[:200])


def trigger(which, on):
    q = 'mutation { aiFlowTriggerUpdate(input: {id: "%s", active: %s}) { errors } }' % (TRIG[which], "true" if on else "false")
    subprocess.run(["glab", "api", "graphql", "-f", f"query={q}"], capture_output=True, text=True)


def meter():
    r = subprocess.run(["glab", "api", "graphql", "-f", f'query={{ currentUser {{ creditsUsage(namespacePath:"{NS}") {{ creditsUsed }} }} }}'],
                       capture_output=True, text=True)
    try:
        return float(json.loads(r.stdout)["data"]["currentUser"]["creditsUsage"]["creditsUsed"])
    except Exception:
        return None


def discussions(iid):
    return api(f"projects/{P}/merge_requests/{iid}/discussions?per_page=100")


def wait_session_done(iid, who, timeout=900):
    """A system note 'completed session' (or 'failed') by the flow's account on this merge request."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(15)
        for d in discussions(iid):
            for n in d["notes"]:
                if n["system"] and who in n["author"]["username"] and ("completed session" in n["body"] or "failed session" in n["body"]):
                    return n["body"][:40]
    return None


def classify(thread, react_user="ai-itemator-react"):
    """What the reaction flow did in one thread, read from its notes."""
    bot = [n["body"] for n in thread["notes"][1:] if react_user in n["author"]["username"] and not n["system"]]
    first = thread["notes"][0]
    settled = next((b.split(":")[0] for b in bot if b.split(":")[0] in ("Kept", "Dismissed", "Removed", "Split")), None)
    return {"bot_notes": [b[:160] for b in bot], "settled": settled.lower() if settled else None,
            "resolved": bool(first.get("resolved"))}


def run(cases_doc):
    cases = cases_doc["cases"]
    rec = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "cases": []}
    issue = api(f"projects/{P}/issues", "POST", title="Probe: fix a typo in the README (reply study)",
                description="Fix one typo in the README heading. Nothing else is asked.")
    rec["issue_iid"] = issue["iid"]
    api(f"projects/{P}/repository/branches", "POST", branch=BRANCHES[1], ref="main")
    api(f"projects/{P}/repository/branches", "POST", branch=BRANCHES[0], ref=BRANCHES[1])
    rd = base64.b64decode(api(f"projects/{P}/repository/files/README.md?ref={BRANCHES[0]}")["content"]).decode()
    def read(path):
        return base64.b64decode(api(f"projects/{P}/repository/files/{path.replace('/', '%2F')}?ref={BRANCHES[0]}")["content"]).decode()
    ci, pp, pol, ag = read(".gitlab-ci.yml"), read("pyproject.toml"), read(".itemator.toml"), read("AGENTS.md")
    assert 'version = "0.0.1"' in pp
    actions = [
        {"action": "update", "file_path": "README.md", "content": rd.replace("## Related tools\n", "## Related tools:\n", 1)},
        {"action": "create", "file_path": "requirements.txt", "content": "leftpad-py==1.0.0\n"},
        {"action": "update", "file_path": ".gitlab-ci.yml", "content": "# probe: ordering note\n" + ci},
        {"action": "create", "file_path": "Dockerfile", "content": "FROM python:3.12-slim\nRUN true\n"},
        {"action": "create", "file_path": ".github/workflows/ci.yml", "content": "name: probe\non: push\njobs: {}\n"},
        {"action": "create", "file_path": "notes.txt", "content": "scratch notes\n"},
        {"action": "update", "file_path": "pyproject.toml", "content": pp.replace('version = "0.0.1"', 'version = "0.0.2"', 1)},
        {"action": "update", "file_path": ".itemator.toml", "content": "# probe comment\n" + pol},
        {"action": "update", "file_path": "AGENTS.md", "content": ag + "- Probe line.\n"},
    ]
    commit(BRANCHES[0], "Fix a typo in the README", actions)
    mr = api(f"projects/{P}/merge_requests", "POST", source_branch=BRANCHES[0], target_branch=BRANCHES[1],
             title="Fix a typo in the README", description=f"Closes #{issue['iid']}\n\nFixes the heading.")
    iid = rec["mr_iid"] = mr["iid"]
    t0 = time.time()
    while time.time() - t0 < 720:
        pl = api(f"projects/{P}/merge_requests/{iid}/pipelines")
        if pl and pl[0]["status"] in ("success", "failed"):
            rec["pipeline"] = pl[0]["status"]; break
        time.sleep(15)
    try:
        trigger("card", True)
        api(f"projects/{P}/merge_requests/{iid}", "PUT", reviewer_ids=CARD_USER)
        rec["card_done"] = wait_session_done(iid, "card", 1200)
    finally:
        trigger("card", False)
    time.sleep(5)
    threads = {}
    for d in discussions(iid):
        first = d["notes"][0]
        if "card" in first["author"]["username"] and "reply with its exact name" in first["body"]:
            ticks = first["body"].split("`")
            if len(ticks) > 1:
                threads[ticks[1]] = d["id"]
    rec["threads_found"] = sorted(threads)
    for c in cases:
        for r in c["replies"]:
            r["sent"] = r["text"].replace("{NAME}", c["name"])
    start = cases[-1]
    for c in cases[:-1]:
        d = threads.get(c["name"])
        if d:
            for r in c["replies"]:
                api(f"projects/{P}/merge_requests/{iid}/discussions/{d}/notes", "POST", body=r["sent"])
    try:
        trigger("react", True)
        d = threads.get(start["name"])
        if d:
            api(f"projects/{P}/merge_requests/{iid}/discussions/{d}/notes", "POST", body=start["replies"][0]["sent"])
        rec["react_done"] = wait_session_done(iid, "react", 1200)
    finally:
        trigger("react", False)
    time.sleep(10)
    by_id = {d["id"]: d for d in discussions(iid)}
    for c in cases:
        d = threads.get(c["name"])
        got = classify(by_id[d]) if d in by_id else {"settled": None, "resolved": False, "bot_notes": [], "missing_thread": True}
        outcome = got["settled"] or "open"
        if outcome == "open" and got["resolved"]:
            outcome = "resolved silently"             # resolved with no settled note: never counts as a correct "stayed open"
        if outcome == "dismissed" and not got["resolved"] or outcome == "kept" and not got["resolved"]:
            outcome += " (not resolved)"
        rec["cases"].append({"n": c["n"], "name": c["name"], "label": c["label"], "sent": [r["sent"] for r in c["replies"]],
                             "expected": c["expected"], "got": outcome, "match": outcome == c["expected"] and not got.get("missing_thread"),
                             "bot_notes": got["bot_notes"], "thread_resolved": got["resolved"]})
    m = api(f"projects/{P}/merge_requests/{iid}")
    rec["mr_after"] = {"state": m["state"], "title": m["title"], "labels": m["labels"], "merge_status": m.get("detailed_merge_status")}
    rec["removed_file_gone"] = all(f["new_path"] != next((c["name"] for c in cases if c["expected"] == "removed"), "") for f in api(f"projects/{P}/merge_requests/{iid}/diffs?per_page=100"))
    for step in (lambda: api(f"projects/{P}/merge_requests/{iid}", "PUT", state_event="close"),
                 lambda: api(f"projects/{P}/issues/{issue['iid']}", "PUT", state_event="close"),
                 lambda: api(f"projects/{P}/repository/branches/{BRANCHES[0].replace('/', '%2F')}", "DELETE"),
                 lambda: api(f"projects/{P}/repository/branches/{BRANCHES[1].replace('/', '%2F')}", "DELETE")):
        try: step()
        except Exception: pass
    return rec


def summarize(runs):
    rows = [c for r in runs for c in r["cases"]]
    ok = [c for c in rows if c["match"]]
    return {"what": "Eight reply cases for the reaction flow (react v1.5.0), pre-registered in eval/react_study_cases.json. Counts only.",
            "limits": "One merge request per run, eight cases written by us, one author account, one model reading. It measures how the model reads our reply tests, not how people answer.",
            "runs": len(runs), "cases": len(rows), "as_expected": len(ok), "misread": len(rows) - len(ok),
            "misread_cases": [{"n": c["n"], "label": c["label"], "expected": c["expected"], "got": c["got"]} for c in rows if not c["match"]],
            "settled_wrongly": len([c for c in rows if c["expected"] == "open" and c["got"] != "open"]),
            "left_open_wrongly": len([c for c in rows if c["expected"] != "open" and c["got"] == "open"])}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--credit-stop", type=float, default=0.0); ap.add_argument("--summarize", action="store_true")
    a = ap.parse_args()
    runs = json.loads(RAW.read_text()) if RAW.exists() else []
    if a.summarize:
        OUT.write_text(json.dumps(summarize(runs), indent=1) + "\n"); print("wrote", OUT.name); return 0
    m = meter(); print("meter", m)
    if a.credit_stop and m is not None and m >= a.credit_stop:
        print("credit stop reached"); return 1
    rec = run(json.loads(CASES.read_text()))
    runs.append(rec); RAW.write_text(json.dumps(runs, indent=1) + "\n")
    for c in rec["cases"]:
        print(f"{c['n']:>2} {c['label'][:44]:44} expected {c['expected']:9} got {c['got']:9} {'OK' if c['match'] else 'MISMATCH'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
