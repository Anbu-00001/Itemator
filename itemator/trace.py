"""The path of every changed file through Itemator's checks, as one JSON file: `python -m itemator.trace --commits --out trace.json`.

For each changed file the trace records, in order, what the request rules said (a word of the request names it, or not),
whether an extras rule lists it, what the layout-only proof (itemator/neutral.py) said for a modified .py file, what the
opener (itemator/unwrap.py) read from an added or changed binary file, what the two history checks said, and the bin it lands in:

  listed    an extras rule lists it
  opened    the opener read it (a binary file)
  neutral   the change is provably only layout, comments, docstrings or plain-function order
  noted     a history check noted it: the file never changed in a commit with the other changed files, or the change deletes
            lines that a bug-fix commit added (itemator/cochange.py, itemator/fence.py)
  ordinary  nothing lists it: read this one yourself. It is not a statement that the file is fine.

Standard library only; no network, no model. The same inputs give the same file."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys

from itemator import ci
from itemator import extras as X
from itemator import local as L
from itemator import checked as C
from itemator import cochange as CC
from itemator import neutral as N

SCHEMA = 2
BINS = ("listed", "opened", "neutral", "noted", "ordinary")           # a file lands in the first one that applies
SAY_REQUEST = {"listed": "an extras rule lists this file", "unplaced": "the rules could not place this file against the request",
               "named": "a word of the request matches this file", "none": "no word of the request matches this file"}


def history_steps(path: str, status: str, labels: dict, fenced: list[dict]) -> list[dict]:
    """The two history stations for one file: has it changed together with the other changed files, and does the change delete
    lines that a bug-fix commit added."""
    label = labels.get(path)
    if status != "modified":
        together = {"outcome": "not_applicable", "say": "only modified files have a history to compare"}
    elif label == CC.STRANGER:
        together = {"outcome": "hit", "say": "never changed in the same commit as any other changed file"}
    elif label == CC.PARTNERED:
        together = {"outcome": "pass", "say": "has changed in a commit with another changed file"}
    elif label == CC.TOO_NEW:
        together = {"outcome": "not_applicable", "say": "fewer than three earlier commits: nothing to compare yet"}
    else:
        together = {"outcome": "not_applicable", "say": "needs three to forty modified files with history to compare"}
    mine = [d for d in fenced if d["path"] == path]
    if mine:
        d = mine[0]
        fence = {"outcome": "hit", "say": f"{d['lines']} deleted line(s) added by {d['commit']}, \"{d['subject']}\""}
    elif status == "modified":
        fence = {"outcome": "pass", "say": "no outright deletion was added by a commit that says it fixes something"}
    else:
        fence = {"outcome": "not_applicable", "say": "only modified files are read"}
    return [{"check": "history", **together}, {"check": "fence", **fence}]


def route(how: str, kinds: list[str], verdict: N.Verdict | None, look, history: list[dict] | None = None) -> list[dict]:
    """The stations one file passed, each with the outcome and one plain sentence from the check that ran."""
    steps = [{"check": "request", "outcome": "pass" if how == "named" else "not_matched", "say": SAY_REQUEST[how]},
             {"check": "extras", "outcome": "hit" if how == "listed" else "pass",
              "say": "listed as: " + ", ".join(kinds) if how == "listed" else "no extras rule lists it"}]
    if verdict is None:
        steps.append({"check": "neutral", "outcome": "not_applicable", "say": "only modified Python files are checked"})
    else:
        steps.append({"check": "neutral", "outcome": "hit" if verdict.level in N.PROVED else "not_proved", "say": verdict.reason})
    if look is None:
        steps.append({"check": "unwrap", "outcome": "not_applicable", "say": "only added or changed binary files are opened"})
    else:
        steps.append({"check": "unwrap", "outcome": "hit", "say": look.line()})
    return steps + (history or [])


def landing(how: str, verdict: N.Verdict | None, look, history: list[dict] | None = None) -> str:
    if how == "listed":
        return "listed"
    if look is not None:
        return "opened"
    if verdict is not None and verdict.level in N.PROVED:
        return "neutral"
    if any(h["outcome"] == "hit" for h in history or []):
        return "noted"
    return "ordinary"


def build(repo: str, base: str, head: str, text: str, files: list[dict]) -> dict:
    analysis = X.analyse(text, files)
    placed = L.placement(analysis, files)
    labels, fence = C.history_checks(repo, base, files, {p for p, (how, _) in placed.items() if how == "listed"}, [])
    out = []
    for f in files:
        how, kinds = placed[f["filename"]]
        verdict, look = L.neutral_verdict(repo, base, head, f), L.opened(repo, head, f)
        hist = history_steps(f["filename"], f.get("status", "modified"), labels, fence["fenced"])
        out.append({"path": f["filename"], "status": f.get("status", "modified"), "additions": f.get("additions", 0),
                    "deletions": f.get("deletions", 0), "route": route(how, kinds, verdict, look, hist),
                    "landing": landing(how, verdict, look, hist)})
    diff = subprocess.run(["git", "-C", repo, "diff", "--find-renames", "--binary", base, head], capture_output=True).stdout
    return {"schema": SCHEMA,
            "source": {"base_sha": base, "head_sha": head, "rules_version": X.RULES_VERSION, "input_sha256": hashlib.sha256(diff).hexdigest()},
            "files": out, "totals": {b: sum(x["landing"] == b for x in out) for b in BINS}}


def _sha(repo: str, ref: str) -> str:
    out = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", ref + "^{commit}"], capture_output=True, text=True)
    if out.returncode != 0:
        raise ci.JobError(f"unknown commit: {ref}")
    return out.stdout.strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="itemator.trace", description=(__doc__ or "").split("\n\n")[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--issue", help="file with the issue text, or - for standard input")
    src.add_argument("--issue-text", help="the issue text itself")
    src.add_argument("--commits", action="store_true", help="use the commit messages from BASE to HEAD as the request")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base")
    ap.add_argument("--target", default="main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--out", default="trace.json")
    a = ap.parse_args(argv)
    try:
        base = _sha(a.repo, a.base or L.merge_base(a.repo, a.target, a.head))
        if a.commits:
            text = L.commit_messages(a.repo, base, a.head)
        elif a.issue == "-":
            text = sys.stdin.read()
        elif a.issue:
            with open(a.issue, encoding="utf-8", errors="replace") as f:
                text = f.read()
        else:
            text = a.issue_text or ""
        head = _sha(a.repo, a.head)
        data = build(a.repo, base, head, text, ci.diff_files(a.repo, base, head))
    except (ci.JobError, OSError) as e:
        print(f"itemator.trace: {e}", file=sys.stderr)
        return 2
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    print(f"{len(data['files'])} file(s): " + ", ".join(f"{n} {b}" for b, n in data["totals"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
