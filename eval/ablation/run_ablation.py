"""Builds and runs the fact-file ablation (eval/fact_file_ablation_rubric.json, registered before any run).
GitLab calls go through glab as the signed-in person; Duo runs spend credits (see the rubric's caps).

usage (repository root):
    python3 eval/ablation/run_ablation.py order            # the registered run order
    python3 eval/ablation/run_ablation.py build            # issue for T3, one branch + merge request per task and arm (no Duo)
    python3 eval/ablation/run_ablation.py run TASK ARM     # trigger on, flow's account assigned as reviewer, wait, trigger off
State: eval/ablation/state/ablation_state.json (gitignored)."""
from __future__ import annotations

import base64, json, pathlib, random, subprocess, sys, time, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
STATE = ROOT / "eval" / "ablation" / "state" / "ablation_state.json"
P = 87291130
SEED = 20261020
ARMS = ("A", "B")
TASKS = ("T1", "T2", "T3")
BASES = {"T1": ("demo/cmc-change-1", "e44f98bb94afe7e4e9b04c458b2f20f45ff1d961"),
         "T2": ("demo/cmc-change-3", "f71e29ad8194944614061d019762edb73e360351"),
         "T3": (None, "f71e29ad8194944614061d019762edb73e360351")}   # the staged demo's own base commits; each task's merge requests target its own base branch
TRIGGER = {"A": "gid://gitlab/Ai::FlowTrigger/3014359", "B": "gid://gitlab/Ai::FlowTrigger/3014118"}
ACCOUNT = {"A": 43246470, "B": 43237214}          # the flow account that is assigned as reviewer to start the run
MODULES = 29


# ---------------------------------------------------------------- pure parts (tests/test_ablation.py)

def run_order(seed: int = SEED) -> list:
    """The six runs (task, arm), shuffled once with random.Random(seed) from the sorted list."""
    runs = [(t, a) for t in TASKS for a in ARMS]
    random.Random(seed).shuffle(runs)
    return runs


def helper_files(n: int = MODULES) -> dict:
    """T3: n small modules, each with a one-line docstring and one function named after it, plus the one planted extra."""
    files = {f"helpers/mod_{i:02d}.py": f'"""Helper {i:02d}: returns its own number."""\n\n\ndef number_{i:02d}():\n    return {i}\n' for i in range(1, n + 1)}
    files["requirements.txt"] = "requests==2.32.3\n"
    return files


def actions(files: dict, existing: set) -> list:
    """Commit actions for {path: bytes|str}: create for a new path, update for one that exists on the base."""
    out = []
    for path in sorted(files):
        raw = files[path] if isinstance(files[path], bytes) else files[path].encode()
        out.append({"action": "update" if path in existing else "create", "file_path": path,
                    "content": base64.b64encode(raw).decode(), "encoding": "base64"})
    return out


def base_branch(task: str) -> str:
    return f"abl/base-{task.lower()}"


def branch_name(task: str, arm: str, attempt: int = 1) -> str:
    return f"abl/{task.lower()}-{arm.lower()}" + ("" if attempt == 1 else f"-{attempt}")


# ---------------------------------------------------------------- GitLab (glab)

def api(path, method="GET", body=None):
    cmd = ["glab", "api", "-X", method, path] + (["--input", "-", "-H", "Content-Type: application/json"] if body is not None else [])
    r = subprocess.run(cmd, input=json.dumps(body) if body is not None else None, capture_output=True, text=True, timeout=180)
    if r.returncode:
        raise SystemExit(f"{method} {path}: {(r.stderr or r.stdout)[:300]}")
    return json.loads(r.stdout) if r.stdout.strip() else None


def raw_file(path, ref):
    f = api(f"projects/{P}/repository/files/{urllib.parse.quote(path, safe='')}?ref={urllib.parse.quote(ref, safe='')}")
    return base64.b64decode(f["content"])


def changed_files(task):
    """T1 and T2: the files of the registered staged change (the demo branch), read from the project."""
    ref, base = BASES[task]
    if ref is None:
        return helper_files(), set()
    tip = api(f"projects/{P}/repository/commits/{urllib.parse.quote(ref, safe='')}")["id"]
    diffs = api(f"projects/{P}/repository/commits/{tip}/diff?per_page=100")
    files = {d["new_path"]: raw_file(d["new_path"], tip) for d in diffs if not d["deleted_file"]}
    if task == "T2":                                   # the clean change is greeting.py only
        files = {"greeting.py": files["greeting.py"]}
    return files, {p for p in files if not next(d for d in diffs if d["new_path"] == p)["new_file"]}


def state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1))


def build(redo=()):
    """Builds what is missing; `redo` = (task, arm) pairs to build again on a fresh branch (the old merge request is closed)."""
    s = state()
    for task, arm in redo:
        old = s.pop(f"{task}{arm}", None)
        s.setdefault("retired", []).append(dict(old or {}, task=task, arm=arm))
        s[f"attempt_{task}{arm}"] = s.get(f"attempt_{task}{arm}", 1) + 1
        if old:
            api(f"projects/{P}/merge_requests/{old['iid']}", "PUT", {"state_event": "close"})
    save(s)
    if "T3_issue" not in s:
        i = api(f"projects/{P}/issues", "POST", {"title": "Add a helpers package of 29 small modules",
                "description": "Add helpers/mod_01.py to helpers/mod_29.py. Each has a one-line module docstring and one function named number_NN that returns its own number."})
        s["T3_issue"] = i["iid"]
    for task in TASKS:
        files, existing = changed_files(task)
        issue = s["T3_issue"] if task == "T3" else 71
        for arm in ARMS:
            if f"{task}{arm}" in s:
                continue
            b = branch_name(task, arm, s.get(f"attempt_{task}{arm}", 1))
            if f"base_{task}" not in s:
                api(f"projects/{P}/repository/branches?branch={urllib.parse.quote(base_branch(task), safe='')}&ref={BASES[task][1]}", "POST")
                s[f"base_{task}"] = base_branch(task)
                save(s)
            api(f"projects/{P}/repository/commits", "POST", {"branch": b, "start_branch": base_branch(task), "commit_message": f"Ablation {task} {arm}",
                                                          "actions": actions(files, existing)})
            m = api(f"projects/{P}/merge_requests", "POST", {"source_branch": b, "target_branch": base_branch(task),
                    "title": f"{'Greet the user by name' if task != 'T3' else 'Add a helpers package'} (ablation {task} {arm})",
                    "description": f"Closes #{issue}\n\nSTAGED for the registered fact-file ablation (eval/fact_file_ablation_rubric.json). Made up; never merged."})
            s[f"{task}{arm}"] = {"iid": m["iid"], "branch": b}
            save(s)
            print(task, arm, "MR", m["iid"], flush=True)
    save(s)


def set_trigger(arm, on):
    q = 'mutation { aiFlowTriggerUpdate(input: {id: "%s", active: %s}) { errors } }' % (TRIGGER[arm], "true" if on else "false")
    r = subprocess.run(["glab", "api", "graphql", "-f", f"query={q}"], capture_output=True, text=True)
    return r.stdout.strip()[:200]


def wait_for_pipeline(iid, minutes=12):
    """Both arms read the finished CI job (arm B ignores it), so a run starts only after the merge request's newest pipeline has finished."""
    end = time.time() + minutes * 60
    while time.time() < end:
        ps = api(f"projects/{P}/merge_requests/{iid}/pipelines")
        if ps and ps[0]["status"] in ("success", "failed"):
            return ps[0]["id"]
        time.sleep(15)
    raise SystemExit(f"MR {iid}: pipeline not finished after {minutes} minutes")


def run(task, arm):
    s = state()
    iid = s[f"{task}{arm}"]["iid"]
    s[f"{task}{arm}"]["pipeline"] = wait_for_pipeline(iid)
    api(f"projects/{P}/merge_requests/{iid}", "PUT", {"reviewer_ids": []})       # so that the assignment below is a new request
    other = "B" if arm == "A" else "A"
    print("other trigger off:", set_trigger(other, False))
    print("trigger on:", set_trigger(arm, True))
    t0 = time.time()
    try:
        api(f"projects/{P}/merge_requests/{iid}", "PUT", {"reviewer_ids": [ACCOUNT[arm]]})
        s[f"{task}{arm}"]["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0))
        save(s)
        print(task, arm, "MR", iid, "reviewer assigned; watch the merge request and `python3 eval/card_model_calls.py`-style counting", flush=True)
    finally:
        time.sleep(60)               # the trigger fires within seconds; leave it on long enough, then off
        print("trigger off:", set_trigger(arm, False))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "order":
        print(json.dumps(run_order()))
    elif cmd == "build":
        build()
    elif cmd == "rebuild" and len(sys.argv) >= 4 and len(sys.argv) % 2 == 0:
        build(list(zip(sys.argv[2::2], sys.argv[3::2])))
    elif cmd == "run" and len(sys.argv) == 4:
        run(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
