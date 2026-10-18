"""Spike for the refactor-claim check (itemator/neutral.py), pre-registered in eval/neutral_spike_rubric.json.
Walks the ordered AIDev pull requests of eval/neutral_spike_cases.json; for each, reads the changed Python files from
GitHub (read-only GETs through `gh api`: the pull request, its file list, the merge base, and each modified .py file at
the merge base and at the head) and records the level itemator.neutral proves for each file. Stops at WANT pull
requests that have at least one modified .py file. Source text stays in eval/cache/neutral/ (gitignored); the result
holds ids, paths and levels only.

usage: python3 eval/neutral_spike.py [--want 40] [--out results/neutral_spike_v1.json]"""
from __future__ import annotations

import argparse, base64, collections, json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from itemator import neutral as N  # noqa: E402

CASES = ROOT / "eval" / "neutral_spike_cases.json"
CACHE = ROOT / "eval" / "cache" / "neutral"
MAX_PY_FILES = 12            # per pull request, in the order GitHub lists them
WANT = 40


def gh(path: str, retries: int = 3):
    """One GET through the GitHub CLI, cached by path. None when GitHub refuses (deleted repo, too large, not found)."""
    f = CACHE / (path.replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "_") + ".json")
    if f.exists():
        return json.loads(f.read_text())
    for i in range(retries):
        r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
        if r.returncode == 0:
            CACHE.mkdir(parents=True, exist_ok=True)
            f.write_text(r.stdout)
            return json.loads(r.stdout)
        if "HTTP 4" in r.stderr and "429" not in r.stderr and "403" not in r.stderr:
            return None                  # 404, 410, 422: the thing is gone; retrying will not bring it back
        time.sleep(5 * (i + 1))
    return None


def content(repo: str, path: str, sha: str) -> str | None:
    d = gh(f"repos/{repo}/contents/{path}?ref={sha}")
    if not d or d.get("encoding") != "base64":
        return None
    try:
        return base64.b64decode(d["content"]).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return None


def modified_py(files: list[dict]) -> list[dict]:
    """The pull request's modified (not added, removed or renamed) .py files, in GitHub's listing order."""
    return [f for f in files if f["filename"].endswith(".py") and f["status"] == "modified"]


def one_pr(case: dict) -> dict | None:
    """The per-file levels of one pull request, or None when it has no modified .py file (not counted)."""
    repo = "/".join(case["html_url"].split("/")[3:5])
    n = case["number"]
    files = gh(f"repos/{repo}/pulls/{n}/files?per_page=100")
    if files is None:
        return {"pr_id": case["pr_id"], "agent": case["agent"], "html_url": case["html_url"], "fetched": False, "files": []}
    py = modified_py(files)
    if not py:
        return None
    pr = gh(f"repos/{repo}/pulls/{n}")
    mb = None
    if pr:
        cmp_ = gh(f"repos/{repo}/compare/{pr['base']['sha']}...{pr['head']['sha']}")
        mb = (cmp_ or {}).get("merge_base_commit", {}).get("sha")
    head = pr["head"]["sha"] if pr else None
    rows = []
    for f in py[:MAX_PY_FILES]:
        old = content(repo, f["filename"], mb) if mb else None
        new = content(repo, f["filename"], head) if head else None
        if old is None or new is None:
            rows.append({"path": f["filename"], "level": "unfetched", "compiled_same": None})
            continue
        v = N.classify(old, new)
        rows.append({"path": f["filename"], "level": v.level, "compiled_same": N.compiled_same(old, new) if v.level == N.SAME_SYNTAX else None})
    return {"pr_id": case["pr_id"], "agent": case["agent"], "html_url": case["html_url"], "fetched": True,
            "py_files_changed": len(py), "py_files_read": len(rows), "files": rows}


def summarize(prs: list[dict], examined: int) -> dict:
    """The registered numbers. `prs`: one_pr results that had a modified .py file; `examined`: pull requests walked."""
    fetched = [p for p in prs if p["fetched"]]
    files = [f for p in fetched for f in p["files"]]
    read = [f for f in files if f["level"] != "unfetched"]
    by_level = collections.Counter(f["level"] for f in read)
    proved = sum(by_level[l] for l in N.PROVED)
    full = [p for p in fetched if p["files"] and all(f["level"] in N.PROVED for f in p["files"])]
    same = [f for f in read if f["level"] == N.SAME_SYNTAX]
    return {"pull_requests_examined": examined, "pull_requests_with_a_modified_py_file": len(prs), "pull_requests_fetched": len(fetched),
            "py_files": len(files), "py_files_unfetched": len(files) - len(read), "py_files_read": len(read),
            "by_level": {l: by_level.get(l, 0) for l in N.LEVELS}, "py_files_proved": proved,
            "share_of_read_files_proved": round(proved / len(read), 4) if read else None,
            "pull_requests_where_every_read_file_is_proved": len(full),
            "same_syntax_checked_against_compiled_code": {"files": len(same), "compiled_same": sum(f["compiled_same"] is True for f in same),
                                                          "not_same": sum(f["compiled_same"] is False for f in same)},
            "by_agent": {a: {"pull_requests": sum(p["agent"] == a for p in fetched),
                             "read_files": sum(1 for p in fetched if p["agent"] == a for f in p["files"] if f["level"] != "unfetched"),
                             "proved": sum(1 for p in fetched if p["agent"] == a for f in p["files"] if f["level"] in N.PROVED)}
                         for a in sorted({p["agent"] for p in fetched})}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--want", type=int, default=WANT)
    ap.add_argument("--out", default=str(ROOT / "results" / "neutral_spike_v1.json"))
    a = ap.parse_args()
    cases = json.loads(CASES.read_text())["cases"]
    prs, examined = [], 0
    for c in cases:
        if len(prs) >= a.want:
            break
        examined += 1
        r = one_pr(c)
        if r:
            prs.append(r)
        if examined % 20 == 0:
            print(f"{examined} examined, {len(prs)} with python", file=sys.stderr, flush=True)
    out = {"rubric": "eval/neutral_spike_rubric.json", "summary": summarize(prs, examined), "pull_requests": prs}
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(out["summary"]))


if __name__ == "__main__":
    main()
