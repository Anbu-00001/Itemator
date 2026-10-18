"""Which lines does this change delete that a bug-fix commit added? Standard library only; no model.

The idea is the old SZZ method (Sliwerski, Zimmermann and Zeller, 2005) run backwards, and G. K. Chesterton's fence: before
you take a fence down, find out why it was put up. For every run of lines the change deletes outright, `git blame -w -M -C`
at the base names the commit that added them; if that commit's subject says it fixes something, the deletion is listed with
the subject. It is a fact from the history, not a finding that the deletion is wrong: a fix is sometimes made obsolete.

What it leaves out, so a reviewer is not sent after noise: test, documentation and lock files; runs of blank or comment
lines; lines that the change adds back somewhere else (a move); commits that touched more than MAX_COMMIT_FILES files; and
rewritten lines (only outright deletions are read). Past the caps it stops and says so."""
from __future__ import annotations

import re
import subprocess

MAX_RUNS = 30             # deleted runs read per change
MAX_RUNS_PER_FILE = 5
MAX_FILE_LINES = 5000
MAX_COMMIT_FILES = 20
SUBJECT_SHOWN = 70

_FIX = re.compile(r"^(?:fix(?:es|ed)?|hotfix|bugfix|revert)\b|\bfix(?:es|ed)?\s+(?:issue\s+)?#\d+|\bcve-\d{4}-\d{4,}", re.I)
_SKIP_PATH = re.compile(r"(?:^|/)(?:tests?|docs?|spec|specs|__tests__|vendor|node_modules)/|(?:^|/)test_[^/]*$|_test\.[a-z]+$|\.(?:md|rst|txt|lock)$|"
                        r"(?:^|/)(?:package-lock\.json|poetry\.lock|yarn\.lock|Cargo\.lock)$", re.I)
_COMMENT = re.compile(r"^\s*(?:#|//|--|/\*|\*|\*/|;)")
_HUNK = re.compile(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")
_ODD = re.compile(r"[^\x20-\x7e]")


def says_fix(subject: str) -> bool:
    return bool(_FIX.search(subject))


def tidy(subject: str) -> str:
    """A commit subject safe to put in a card: printable ASCII, no markup characters, one short line."""
    s = _ODD.sub("", subject).replace("`", "'").replace("<", "").replace(">", "").replace("[", "(").replace("]", ")").strip()
    return s if len(s) <= SUBJECT_SHOWN else s[:SUBJECT_SHOWN - 3].rstrip() + "..."


def deleted_runs(patch: str) -> list[tuple[int, int, list[str]]]:
    """(first old line, last old line, the lines) for each run of removed lines not directly followed by an added line."""
    runs, old, cur = [], 0, None
    for line in patch.split("\n"):
        m = _HUNK.match(line)
        if m:
            if cur:
                runs.append(cur)
            cur, old = None, int(m.group(1))
            continue
        if line.startswith("-") and not line.startswith("---"):
            if cur is None:
                cur = [old, old, []]
            cur[1] = old
            cur[2].append(line[1:])
            old += 1
            continue
        if line.startswith("+") and cur is not None:
            cur = None                  # the run was rewritten, not deleted
        elif cur:
            runs.append(cur)
            cur = None
        if not line.startswith("+") and not line.startswith("\\"):
            old += 1
    if cur:
        runs.append(cur)
    return [(a, b, ls) for a, b, ls in runs]


def _git(repo: str, *args: str) -> str | None:
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, errors="replace")
    return out.stdout if out.returncode == 0 else None


def _blame(repo: str, base: str, path: str, a: int, b: int) -> dict[str, str]:
    """{commit: subject} for the commits that added lines a..b of `path` at `base`."""
    text = _git(repo, "blame", "-w", "-M", "-C", "--porcelain", "-L", f"{a},{b}", base, "--", path)
    found, sha = {}, None
    for line in (text or "").split("\n"):
        head = line.split(" ")
        if len(head[0]) == 40 and all(c in "0123456789abcdef" for c in head[0]):
            sha = head[0]
        elif line.startswith("summary ") and sha:
            found[sha] = line[8:]
    return found


def _files_in(repo: str, sha: str) -> int:
    out = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha)
    return len((out or "").split())


def find(repo: str, base: str, files: list[dict], skip: set = frozenset()) -> dict:
    """{"fenced": [{path, lines, commit, subject}], "runs_read": n, "capped": bool}. `skip`: paths already listed as extras."""
    added = {l[1:].strip() for f in files for l in (f.get("patch") or "").split("\n") if l.startswith("+") and not l.startswith("+++")}
    fenced, read, capped, wide = [], 0, False, {}
    for f in files:
        path = f["filename"]
        if f.get("status") != "modified" or not f.get("patch") or path in skip or _SKIP_PATH.search(path):
            continue
        per_file = 0
        for a, b, lines in deleted_runs(f["patch"]):
            kept = [l for l in lines if l.strip() and not _COMMENT.match(l)]
            if all(l.strip() in added for l in kept):          # nothing but blanks and comments, or all of it moved
                continue
            if read >= MAX_RUNS or per_file >= MAX_RUNS_PER_FILE:
                capped = True
                continue
            read += 1
            per_file += 1
            for sha, subject in _blame(repo, base, path, a, b).items():
                if not says_fix(subject):
                    continue
                if sha not in wide:
                    wide[sha] = _files_in(repo, sha) > MAX_COMMIT_FILES
                if not wide[sha]:
                    fenced.append({"path": path, "lines": b - a + 1, "commit": sha[:8], "subject": tidy(subject)})
    return {"fenced": fenced, "runs_read": read, "capped": capped}
