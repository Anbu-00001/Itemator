"""Which lines does this change add back that an earlier commit took out? Standard library only; no model.

A change that re-adds what a revert removed is a "reland": whoever reverted the code had a reason, and the commit that
says why is in the history. The card names that commit. This is the fence check (itemator/fence.py) the other way round:
the fence asks why a deleted line was put up, this asks why an added line was once taken down.

How it reads: for each modified file, each run of added lines with at least MIN_LINES meaningful lines (not blank, not a
comment) and MIN_CHARS characters is looked up in the file's history with `git log -S` on its longest line; a candidate
commit counts when one run of lines it removed contains all of them, in order. It leaves out test, documentation and lock
files, commits that touched more than MAX_COMMIT_FILES files, and commits that put the same lines back elsewhere (a move).
By default only commits whose subject starts with "Revert" are named (`revert_only`); the evaluation also measures every
removal. It is a fact from the history, not a finding that the change is wrong."""
from __future__ import annotations

import re
import subprocess

from itemator import fence as FE

MIN_LINES = 3
MIN_CHARS = 60
MIN_ANCHOR = 12
MAX_RUNS = 20             # added runs looked up per change
MAX_RUNS_PER_FILE = 5
MAX_CANDIDATES = 20       # commits read per run
MAX_COMMIT_FILES = 20

_REVERT = re.compile(r"^\s*revert\b", re.I)
_COMMENT = FE._COMMENT


def _meaningful(lines: list[str]) -> list[str]:
    return [l.strip() for l in lines if l.strip() and not _COMMENT.match(l)]


def runs(patch: str, sign: str) -> list[list[str]]:
    """The runs of consecutive lines that start with `sign` ("+" or "-") in a unified diff, without the sign."""
    out, cur = [], []
    for line in patch.split("\n"):
        if line.startswith(sign) and not line.startswith(sign * 3):
            cur.append(line[1:])
        else:
            if cur:
                out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def worth_looking_up(lines: list[str]) -> list[str] | None:
    """The meaningful lines of an added run, or None when it is too small to name a history for."""
    m = _meaningful(lines)
    return m if len(m) >= MIN_LINES and sum(map(len, m)) >= MIN_CHARS else None


def _contains(removed: list[str], wanted: list[str]) -> bool:
    n = len(wanted)
    return any(removed[i:i + n] == wanted for i in range(len(removed) - n + 1))


def removed_it(patch: str, wanted: list[str]) -> bool:
    """True when one run of lines a diff removes holds `wanted` in order and the same diff does not add them all back."""
    adds = {l.strip() for r in runs(patch, "+") for l in r}
    if all(w in adds for w in wanted):
        return False                          # moved inside the file, not removed
    return any(_contains(_meaningful(r), wanted) for r in runs(patch, "-"))


def _git(repo: str, *args: str) -> str:
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, errors="replace")
    return out.stdout if out.returncode == 0 else ""


def candidates(repo: str, base: str, path: str, anchor: str) -> list[tuple[str, str, str]]:
    """(sha, date, subject) of up to MAX_CANDIDATES commits that changed how often `anchor` occurs in `path`, newest first."""
    text = _git(repo, "log", "-S" + anchor, f"--max-count={MAX_CANDIDATES}", "--format=%H%x1f%cs%x1f%s", base, "--", path)
    out = []
    for line in text.splitlines():
        if line.count("\x1f") == 2:
            sha, date, subject = line.split("\x1f", 2)
            out.append((sha, date, subject))
    return out


def find(repo: str, base: str, files: list[dict], revert_only: bool = True) -> dict:
    """{"relanded": [{path, lines, commit, date, subject, revert}], "runs_read": n, "capped": bool}.
    One entry per (file, commit): the longest run when a commit removed several."""
    found: dict[tuple[str, str], dict] = {}
    read, capped = 0, False
    for f in files:
        path = f.get("filename", "")
        if f.get("status") != "modified" or not f.get("patch") or FE._SKIP_PATH.search(path):
            continue
        per_file = 0
        for added in runs(f["patch"], "+"):
            wanted = worth_looking_up(added)
            if wanted is None:
                continue
            if read >= MAX_RUNS or per_file >= MAX_RUNS_PER_FILE:
                capped = True
                continue
            read += 1
            per_file += 1
            anchor = max(wanted, key=len)
            if len(anchor) < MIN_ANCHOR:
                continue
            for sha, date, subject in candidates(repo, base, path, anchor):
                is_revert = bool(_REVERT.match(subject))
                if revert_only and not is_revert:
                    continue
                patch = _git(repo, "show", "--format=", "-U0", "--no-color", sha, "--", path)
                if not removed_it(patch, wanted):
                    continue
                if len(_git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha).split()) > MAX_COMMIT_FILES:
                    continue
                key = (path, sha)
                if key not in found or found[key]["lines"] < len(wanted):
                    found[key] = {"path": path, "lines": len(wanted), "commit": sha[:8], "date": date, "subject": FE.tidy(subject), "revert": is_revert}
                break                         # the newest commit that removed them is the one to name
    return {"relanded": list(found.values()), "runs_read": read, "capped": capped}
