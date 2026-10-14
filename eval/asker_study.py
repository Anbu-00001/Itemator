"""Reply study for names.asker_required: six pre-registered cases (eval/asker_study_cases.json) on one throwaway merge request.
The issue is written by the second account (the ASKER); the merge request is opened by the first account (the OTHER person,
also the merge request author). The target branch's .itemator.toml sets names.asker_required = true. The card flow opens one
thread per extra; each case's reply is typed by the account named in the case ('ASKER' = second account with its token from
~/.itemator-second-token, 'OTHER' = the first account); the reaction flow is started once with a mention and every thread is read
afterwards. Raw record: results/asker_study_raw.json, counts: results/asker_study.json.

usage (repository root, glab authenticated; spends Duo credits, about two flow runs):
    python3 eval/asker_study.py --credit-stop 241
    python3 eval/asker_study.py --summarize
The token is read from the file and sent only to gitlab.com; it is never printed or stored.
"""
from __future__ import annotations

import argparse, base64, json, os, pathlib, sys, time, urllib.parse, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import react_study as R                                    # the same helpers and the same platform constants

ROOT = R.ROOT
CASES = ROOT / "eval" / "asker_study_cases.json"
RAW = ROOT / "results" / "asker_study_raw.json"
OUT = ROOT / "results" / "asker_study.json"
BRANCHES = ("probe/as-src", "probe/as-target")
P = R.P
MENTION = R.REACT_MENTION
TOKEN_FILE = pathlib.Path("~/.itemator-second-token").expanduser()


def second(method, path, **fields):
    """One call as the second account. The token never leaves this function."""
    tok = TOKEN_FILE.read_text().strip()
    data = urllib.parse.urlencode(fields).encode() if fields else None
    req = urllib.request.Request(f"https://gitlab.com/api/v4/{path}", data=data, method=method, headers={"PRIVATE-TOKEN": tok})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"null")


def run(doc):
    cases = doc["cases"]
    rec = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "cases": []}
    issue = second("POST", f"projects/{P}/issues", title="Probe: fix a typo in the README (asker study)",
                   description="Fix one typo in the README heading. Nothing else is asked.")
    asker = issue["author"]["username"]
    rec.update(issue_iid=issue["iid"], asker=asker)
    R.api(f"projects/{P}/repository/branches", "POST", branch=BRANCHES[1], ref="main")
    R.api(f"projects/{P}/repository/branches", "POST", branch=BRANCHES[0], ref=BRANCHES[1])

    def read(path, ref):
        return base64.b64decode(R.api(f"projects/{P}/repository/files/{path.replace('/', '%2F')}?ref={ref}")["content"]).decode()
    pol = read(".itemator.toml", BRANCHES[1])
    assert "other_person_required = false" in pol
    R.commit(BRANCHES[1], "Only the issue's author keeps an extra (test target only)",
             [{"action": "update", "file_path": ".itemator.toml",
               "content": pol.replace("other_person_required = false", "other_person_required = false\nasker_required = true", 1)}])
    rd, ci = read("README.md", BRANCHES[0]), read(".gitlab-ci.yml", BRANCHES[0])
    R.commit(BRANCHES[0], "Fix a typo in the README", [
        {"action": "update", "file_path": "README.md", "content": rd.replace("## Related tools\n", "## Related tools:\n", 1)},
        {"action": "create", "file_path": "docker-compose.yml", "content": "services: {}\n"},
        {"action": "create", "file_path": "Dockerfile", "content": "FROM python:3.12-slim\nRUN true\n"},
        {"action": "create", "file_path": "notes.txt", "content": "scratch notes\n"},
        {"action": "create", "file_path": "setup.cfg", "content": "[metadata]\nname = probe\n"},
        {"action": "create", "file_path": "tox.ini", "content": "[tox]\nenvlist = py312\n"},
        {"action": "update", "file_path": ".gitlab-ci.yml", "content": "# probe: ordering note\n" + ci}])
    mr = R.api(f"projects/{P}/merge_requests", "POST", source_branch=BRANCHES[0], target_branch=BRANCHES[1],
               title="Fix a typo in the README", description=f"Closes #{issue['iid']}\n\nFixes the heading.")
    iid = rec["mr_iid"] = mr["iid"]
    t0 = time.time()
    while time.time() - t0 < 720:
        pl = R.api(f"projects/{P}/merge_requests/{iid}/pipelines")
        if pl and pl[0]["status"] in ("success", "failed"):
            rec["pipeline"] = pl[0]["status"]; break
        time.sleep(15)
    try:
        R.trigger("card", True)
        R.api(f"projects/{P}/merge_requests/{iid}", "PUT", reviewer_ids=R.CARD_USER)
        rec["card_done"] = R.wait_session_done(iid, "card", 1200)
    finally:
        R.trigger("card", False)
    time.sleep(5)
    threads = {}
    for d in R.discussions(iid):
        first = d["notes"][0]
        if "card" in first["author"]["username"] and "reply with its exact name" in first["body"]:
            ticks = first["body"].split("`")
            if len(ticks) > 1:
                threads[ticks[1]] = (d["id"], first["body"])
    rec["threads_found"] = sorted(threads)
    rec["asker_sentence_in_every_thread"] = all(f"(@{asker}) can keep this." in b for _, b in threads.values()) if threads else False
    for c in cases:
        d = threads.get(c["name"], (None, ""))[0]
        c["sent"] = [r["text"].replace("{NAME}", c["name"]) for r in c["replies"]]
        if not d:
            continue
        for text in c["sent"]:
            if c["author"] == "ASKER":
                second("POST", f"projects/{P}/merge_requests/{iid}/discussions/{d}/notes", body=text)
            else:
                R.api(f"projects/{P}/merge_requests/{iid}/discussions/{d}/notes", "POST", body=text)
    try:
        R.trigger("react", True)
        R.api(f"projects/{P}/merge_requests/{iid}/notes", "POST", body=f"{MENTION} check")
        rec["react_done"] = R.wait_session_done(iid, "react", 1200)
    finally:
        R.trigger("react", False)
    time.sleep(10)
    by_id = {d["id"]: d for d in R.discussions(iid)}
    for c in cases:
        d = threads.get(c["name"], (None, ""))[0]
        got = R.classify(by_id[d]) if d in by_id else {"settled": None, "resolved": False, "bot_notes": [], "missing_thread": True}
        outcome = got["settled"] or "open"
        if outcome == "open" and got["resolved"]:
            outcome = "resolved silently"
        rec["cases"].append({"n": c["n"], "name": c["name"], "label": c["label"], "author": c["author"], "sent": c["sent"],
                             "expected": c["expected"], "got": outcome,
                             "match": outcome == c["expected"] and not got.get("missing_thread"),
                             "bot_notes": got["bot_notes"], "thread_resolved": got["resolved"]})
    m = R.api(f"projects/{P}/merge_requests/{iid}")
    rec["mr_after"] = {"state": m["state"], "title": m["title"], "labels": m["labels"], "merge_status": m.get("detailed_merge_status")}
    issue_notes = second("GET", f"projects/{P}/issues/{issue['iid']}/notes?per_page=50")
    rec["receipt_on_issue"] = any("Receipt from Itemator" in (n.get("body") or "") for n in issue_notes)
    for step in (lambda: R.api(f"projects/{P}/merge_requests/{iid}", "PUT", state_event="close"),
                 lambda: R.api(f"projects/{P}/issues/{issue['iid']}", "PUT", state_event="close"),
                 lambda: R.api(f"projects/{P}/repository/branches/{BRANCHES[0].replace('/', '%2F')}", "DELETE"),
                 lambda: R.api(f"projects/{P}/repository/branches/{BRANCHES[1].replace('/', '%2F')}", "DELETE")):
        try: step()
        except Exception: pass
    return rec


def summarize(runs):
    rows = [c for r in runs for c in r["cases"]]
    ok = [c for c in rows if c["match"]]
    return {"what": "Six reply cases for names.asker_required (reaction flow), pre-registered in eval/asker_study_cases.json. Counts only.",
            "limits": "One run, one merge request, six cases written by us, two accounts, one model reading. The cases file names the first account as ASKER; the runner (committed before the run, a86e848) used the second account as ASKER and the first as OTHER, the same swap in every case, so the outcomes stand. It shows whether the model applies the username test, not how people answer; a username that differs only in letter case cannot be produced on GitLab, so that clause is covered by unit tests only.",
            "runs": len(runs), "cases": len(rows), "as_expected": len(ok), "misread": len(rows) - len(ok),
            "misread_cases": [{"n": c["n"], "label": c["label"], "expected": c["expected"], "got": c["got"]} for c in rows if not c["match"]],
            "asker_sentence_in_every_thread": all(r.get("asker_sentence_in_every_thread") for r in runs),
            "record_on_issue_posted": any(r.get("receipt_on_issue") for r in runs)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--credit-stop", type=float, default=0.0); ap.add_argument("--summarize", action="store_true")
    a = ap.parse_args()
    runs = json.loads(RAW.read_text()) if RAW.exists() else []
    if a.summarize:
        OUT.write_text(json.dumps(summarize(runs), indent=1) + "\n"); print("wrote", OUT.name); return 0
    m = R.meter(); print("meter", m)
    if a.credit_stop and m is not None and m >= a.credit_stop:
        print("credit stop reached"); return 1
    rec = run(json.loads(CASES.read_text()))
    runs.append(rec); RAW.write_text(json.dumps(runs, indent=1) + "\n")
    for c in rec["cases"]:
        print(f"{c['n']:>2} {c['label'][:52]:52} expected {c['expected']:9} got {c['got']:9} {'OK' if c['match'] else 'MISMATCH'}")
    print("asker sentence in every thread:", rec["asker_sentence_in_every_thread"], "| record on issue:", rec["receipt_on_issue"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
