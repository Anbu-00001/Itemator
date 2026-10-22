"""Does a coding agent re-add an extra a reviewer answered `remove`, when it can read the project's answer log?
Registered in eval/agent_log_rubric.json before any run. Fixtures, issues and the prompt: eval/agent_log/.

  python eval/agent_log.py prepare ISSUE_ID ARM --root DIR   # copy the fixture, git init, write the log (arm with)
  python eval/agent_log.py score ISSUE_ID ARM --root DIR     # commit the agent's edits, list extras, run the check
  python eval/agent_log.py log REPO --root DIR               # build REPO's answer log from its history runs
  python eval/agent_log.py summary --root DIR                # write results/agent_log_v1.json

ARM is history, with or without. Standard library plus this repository's rules (itemator/)."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from itemator import after as AFTER  # noqa: E402
from itemator import ci  # noqa: E402

HERE = ROOT / "eval" / "agent_log"
RESULTS = ROOT / "results"
RUNS = RESULTS / "agent_log_runs"
LOG_PATH = ".itemator/answers.json"
ARMS = ("history", "with", "without")
STDLIB = set(sys.stdlib_module_names)


def issues() -> dict:
    return {i["id"]: i for i in json.loads((HERE / "issues.json").read_text(encoding="utf-8"))["issues"]}


def issue_text(i: dict) -> str:
    return f"{i['title']}\n\n{i['body']}"


def run_dir(root: pathlib.Path, iid: str, arm: str) -> pathlib.Path:
    return root / f"{iid}-{arm}" / "repo"


def git(repo, *args) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
           "GIT_AUTHOR_DATE": "2026-10-22T00:00:00Z", "GIT_COMMITTER_DATE": "2026-10-22T00:00:00Z"}
    return subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                          capture_output=True, text=True, check=True, env=env).stdout


def prepare(root: pathlib.Path, iid: str, arm: str) -> pathlib.Path:
    i = issues()[iid]
    if (arm == "history") != (i["phase"] == "history"):
        raise SystemExit(f"{iid} is a {i['phase']} issue; arm {arm} does not apply")
    d = run_dir(root, iid, arm)
    if d.exists():
        raise SystemExit(f"{d} exists: a run is never prepared twice")
    unchanged()
    shutil.copytree(HERE / "fixtures" / i["repo"], d, ignore=shutil.ignore_patterns("__pycache__"))
    if arm == "with":
        log = root / f"log-{i['repo']}.json"
        if not log.exists():
            raise SystemExit(f"no answer log for {i['repo']}: run `log {i['repo']}` after its history runs")
        (d / LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(log, d / LOG_PATH)
    git(d, "init", "-q", "-b", "main")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "base")
    return d


def unchanged() -> None:
    """The fixtures, issues and prompt are the registered ones (hashes in the rubric), or no run starts."""
    import hashlib
    r = json.loads((ROOT / "eval" / "agent_log_rubric.json").read_text())
    want = {**r["fixtures"]["files_sha256"], r["issues"]["file"]: r["issues"]["sha256"], "eval/agent_log/prompt.md": r["subject"]["prompt_sha256"]}
    have = {str(p.relative_to(ROOT)) for p in (HERE / "fixtures").rglob("*") if p.is_file() and "__pycache__" not in p.parts}   # never committed
    if have != set(r["fixtures"]["files_sha256"]):
        raise SystemExit(f"fixture files differ from the registered list: {sorted(have ^ set(r['fixtures']['files_sha256']))}")
    for path, sha in want.items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != sha:
            raise SystemExit(f"{path} is not the registered version")


def run_check(d: pathlib.Path, code: str | None) -> dict:
    """pass, fail, or needs_package (the change imports a package that is not installed here)."""
    if not code:
        return {"result": None}
    env = {**os.environ, "PYTHONPATH": str(d), "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        r = subprocess.run([sys.executable, "-c", code], cwd=d, capture_output=True, text=True, timeout=60, env=env)
    except subprocess.TimeoutExpired:
        return {"result": "fail", "why": "timeout"}
    last = (r.stderr.strip().splitlines() or [""])[-1]
    if r.returncode == 0:
        return {"result": "pass"}
    if last.startswith("ModuleNotFoundError: No module named "):
        mod = last.split("'")[1].split(".")[0] if "'" in last else ""
        if mod and mod not in STDLIB and not (d / mod).exists():
            return {"result": "needs_package", "why": last[:200]}
    return {"result": "fail", "why": last[:200]}


def same(name: str) -> str:
    """A name as PyPI compares packages (case and runs of - _ . ignored); a file path compares the same way, which
    changes no real path here."""
    return re.sub(r"[-_.]+", "-", name).lower()


def logged_removes(repo_name: str, root: pathlib.Path) -> set:
    log = root / f"log-{repo_name}.json"
    if not log.exists():
        return set()
    return {same(it["name"]) for e in json.loads(log.read_text())["entries"] for it in e["items"] if it["decision"] == "remove"}


def score(root: pathlib.Path, iid: str, arm: str) -> dict:
    i, d = issues()[iid], run_dir(root, iid, arm)
    base = git(d, "rev-parse", "HEAD").strip()
    git(d, "add", "-A")
    if git(d, "status", "--porcelain").strip():
        git(d, "commit", "-q", "-m", "agent")
    head = git(d, "rev-parse", "HEAD").strip()
    files = ci.diff_files(str(d), base, head) if head != base else []
    extras = AFTER.analyse(issue_text(i), files)[0].extras if files else []
    removed = logged_removes(i["repo"], root) if arm != "history" else set()
    row = {"issue": iid, "repo": i["repo"], "phase": i["phase"], "arm": arm,
           "files": [f["filename"] for f in files],
           "extras": [{"kind": e.kind, "name": e.name, "path": e.path} for e in extras],
           "recurred": sorted({e.name for e in extras if same(e.name) in removed}),
           "check": run_check(d, i["check"]),
           "diff": git(d, "diff", base, head) if head != base else ""}
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / f"{iid}-{arm}.json").write_text(json.dumps(row, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return row


def build_log(root: pathlib.Path, repo_name: str) -> dict:
    """The answer log a reviewer would have left: every extra of every history run answered `remove`, in the shape of
    the published answer log (answers/answers.json). The answers were written by the experimenter, standing in for a
    reviewer; the rubric says so."""
    entries = []
    for n, i in enumerate(sorted((x for x in issues().values() if x["repo"] == repo_name and x["phase"] == "history"),
                                 key=lambda x: x["id"]), start=1):
        p = RUNS / f"{i['id']}-history.json"
        if not p.exists():
            raise SystemExit(f"{i['id']} has no history run yet")
        row = json.loads(p.read_text())
        if row["extras"]:
            entries.append({"iid": n, "title": i["title"],
                            "items": [{"name": e["name"], "decision": "remove", "who": "reviewer"} for e in row["extras"]]})
    log = {"project": repo_name, "what": "What reviewers answered about changes earlier merge requests made beyond their issues.",
           "entries": entries}
    (root / f"log-{repo_name}.json").write_text(json.dumps(log, indent=1) + "\n")
    (RUNS / f"log-{repo_name}.json").write_text(json.dumps(log, indent=1) + "\n")
    return log


def summary() -> dict:
    rubric = json.loads((ROOT / "eval" / "agent_log_rubric.json").read_text())
    rows = [json.loads(p.read_text()) for p in sorted(RUNS.glob("*-*.json")) if not p.name.startswith("log-")]
    test = [r for r in rows if r["phase"] == "test"]
    out = {"rubric": "eval/agent_log_rubric.json", "runs": len(rows), "arms": {}}
    for arm in ("with", "without"):
        a = [r for r in test if r["arm"] == arm]
        checks = [r["check"]["result"] for r in a]
        out["arms"][arm] = {"runs": len(a), "runs_with_a_recurred_extra": sum(bool(r["recurred"]) for r in a),
                            "recurred_extras": sum(len(r["recurred"]) for r in a), "extras": sum(len(r["extras"]) for r in a),
                            "check_pass": checks.count("pass"), "check_fail": checks.count("fail"),
                            "check_needs_package": checks.count("needs_package")}
    w, wo = out["arms"]["with"]["runs_with_a_recurred_extra"], out["arms"]["without"]["runs_with_a_recurred_extra"]
    rule = rubric["decision"]
    if len([r for r in test if r["arm"] == "with"]) < rubric["test_issues"] or len([r for r in test if r["arm"] == "without"]) < rubric["test_issues"]:
        verdict = "incomplete"
    elif wo < rule["min_without"]:
        verdict = "too_few_to_tell"
    elif w <= rule["max_ratio"] * wo:
        verdict = "holds"
    else:
        verdict = "does_not_hold"
    out["result"] = verdict
    out["history"] = {r["issue"]: [e["name"] for e in r["extras"]] for r in rows if r["phase"] == "history"}
    out["per_issue"] = {r["issue"]: {} for r in test}
    for r in test:
        out["per_issue"][r["issue"]][r["arm"]] = {"recurred": r["recurred"], "extras": [e["name"] for e in r["extras"]],
                                                   "check": r["check"]["result"]}
    (RESULTS / "agent_log_v1.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agent_log")
    ap.add_argument("cmd", choices=("prepare", "score", "log", "summary"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--root", default=os.environ.get("AGENT_LOG_ROOT", "/tmp/agent_log_runs"))
    a = ap.parse_args(argv)
    root = pathlib.Path(a.root)
    root.mkdir(parents=True, exist_ok=True)
    if a.cmd == "prepare":
        print(prepare(root, a.args[0], a.args[1]))
    elif a.cmd == "score":
        r = score(root, a.args[0], a.args[1])
        print(json.dumps({k: r[k] for k in ("issue", "arm", "files", "extras", "recurred", "check")}))
    elif a.cmd == "log":
        print(json.dumps(build_log(root, a.args[0]), indent=1))
    else:
        print(json.dumps({k: v for k, v in summary().items() if k != "per_issue"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
