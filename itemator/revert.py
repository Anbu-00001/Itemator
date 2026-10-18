"""Does a change that says it reverts a commit really undo that commit? Standard library only; no model.

"This reverts commit 1a2b3c4" is written by `git revert`, by agents and by people. The commit it names added some lines and
removed some; an undo removes the added ones and puts the removed ones back, in the same files. This reads both diffs and
names what is left in place (a file the change does not touch, or lines of a file it does not undo) and the files the change
touches that the reverted commit did not. It is the stable-kernel backport check run on a revert, with the same idea as
`git patch-id` but per file, so a partial undo can be named. Information only; a change that says "partial" is left alone.

The reverted commit's diff is read from the checkout first and then from the project's API (a CI checkout can be shallow)."""
from __future__ import annotations

import re
import subprocess
import urllib.parse
from collections import Counter

from itemator import fence as FE
from itemator import refs as RF

MIN_CHARS = 3             # a line shorter than this ("}", ")") says nothing about which change it came from
MIN_MISSING = 2           # lines of one file still in place before the file is named
MAX_REVERTED = 3          # distinct reverted commits read per change
MAX_FILES = 50            # files of one reverted commit; a bigger commit is left out
SHOWN = 3

_PARTIAL = re.compile(r"\bpartial(ly)?\b", re.I)


def sides(patch: str) -> tuple[Counter, Counter]:
    """(added, removed): the lines a unified diff adds and removes, stripped, as multisets; short lines are left out."""
    added, removed = Counter(), Counter()
    in_hunk = False
    for line in (patch or "").split("\n"):
        if line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line[:1] in ("+", "-"):
            text = line[1:].strip()
            if len(text) >= MIN_CHARS:
                (added if line[0] == "+" else removed)[text] += 1
    return added, removed


def _local(repo: str, h: str):
    """(title, {path: patch}) of commit `h` against its first parent, or None when the checkout cannot say."""
    def git(*a):
        o = subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, errors="replace")
        return o.stdout if o.returncode == 0 else None
    title = git("log", "-1", "--format=%s", f"{h}^{{commit}}")
    names = git("diff", "--name-only", f"{h}^1", h) if title is not None else None
    if title is None or names is None:
        return None
    paths = [p for p in names.splitlines() if p]
    if len(paths) > MAX_FILES:
        return title.strip(), None
    return title.strip(), {p: git("diff", "-U0", "--no-color", f"{h}^1", h, "--", p) or "" for p in paths}


def _remote(api, pid, h: str):
    try:
        info = api.get(f"/projects/{pid}/repository/commits/{urllib.parse.quote(h)}", missing_ok=True)
        rows = api.get(f"/projects/{pid}/repository/commits/{urllib.parse.quote(h)}/diff?per_page=100", missing_ok=True)
    except Exception:                    # noqa: BLE001 -- an API that cannot answer says nothing
        return None
    if not isinstance(info, dict) or not isinstance(rows, list):
        return None
    if len(rows) > MAX_FILES:
        return str(info.get("title") or ""), None
    return str(info.get("title") or ""), {r.get("new_path") or r.get("old_path"): r.get("diff") or "" for r in rows if isinstance(r, dict)}


def _hidden(path: str) -> bool:
    """A file or folder whose name starts with a dot is configuration or bookkeeping (a pick-status file, a CI farm list), not
    the change the reverted commit made: the trial on Mesa's backports showed one such file in nearly every one."""
    return any(part.startswith(".") for part in path.split("/"))


def compare(reverted: dict[str, str], files: list[dict], copy: bool = False) -> dict:
    """{"left": [{path, missing, of}], "touched": [path]} for one reverted commit ({path: patch}) against the change's files.
    A file whose diff either side could not give (no patch: too large or binary) is never named as left. With `copy` the change
    should add and remove the same lines as the commit (a cherry-pick or backport) instead of the opposite ones."""
    mine = {f.get("filename"): f for f in files}
    left = []
    for path, patch in reverted.items():
        x_add, x_rem = sides(patch)
        need = sum(x_add.values()) + sum(x_rem.values())
        if need == 0:
            continue
        f = mine.get(path)
        if f is not None and not f.get("patch") and f.get("status") != "removed":
            continue                      # the file is in the change but its diff is not given (too large, binary): no claim
        m_add, m_rem = sides(f.get("patch", "")) if f else (Counter(), Counter())
        got = (sum((x_add & m_add).values()) + sum((x_rem & m_rem).values()) if copy
               else sum((x_add & m_rem).values()) + sum((x_rem & m_add).values()))
        if need - got >= (MIN_MISSING if f else 1):
            left.append({"path": path, "missing": need - got, "of": need})
    return {"left": left, "touched": sorted(reverted)}


def find(repo: str, text: str, files: list[dict], api, pid, warnings: list, copy: bool = False) -> dict | None:
    """{"left": [{id, title, files: [{path, missing, of}]}], "beyond": [path], "copy": bool} for the commits `text` says it
    reverts, or (`copy`) says it is a copy of (cherry-pick -x, stable "commit <id> upstream"), or None when there is nothing to say
    (nothing cited, the text says "partial", a faithful copy or undo, or a commit that cannot be read)."""
    if _PARTIAL.search(text or ""):
        return None
    hows = ("cherry-pick", "upstream") if copy else ("revert",)
    ids = [c["id"] for c in RF.cited(text) if c["how"] in hows][:MAX_REVERTED]
    left, touched, read = [], set(), 0
    for h in ids:
        got = _local(repo, h) or (_remote(api, pid, h) if api is not None else None)
        if got is None or got[1] is None:
            if got is not None or api is not None:
                warnings.append(f"no {'copy' if copy else 'revert'} check on {h[:12]}: the commit could not be read")
            continue
        read += 1
        c = compare(got[1], files, copy)
        touched |= set(c["touched"])
        if c["left"]:
            left.append({"id": h[:12], "title": FE.tidy(got[0]), "files": c["left"]})
    if not read:
        return None
    beyond = sorted(f["filename"] for f in files if f.get("filename") not in touched
                    and f.get("previous_filename") not in touched and not _hidden(f.get("filename", "")))
    return {"left": left, "beyond": beyond, "copy": copy} if (left or beyond) else None


def sentence(d: dict) -> str:
    copy = d.get("copy", False)
    parts = []
    for c in d["left"][:SHOWN]:
        shown = []
        for f in c["files"][:SHOWN]:
            shown.append(f"`{f['path']}` ({f['missing']} of {f['of']} lines {'missing' if copy else 'still in place'})")
        more = f" and {len(c['files']) - SHOWN} more files" if len(c["files"]) > SHOWN else ""
        what = "is a copy of" if copy else "reverts"
        gap = "but parts of it are missing here" if copy else "but leaves part of it in place"
        parts.append(f"it says it {what} `{c['id']}` (\"{c['title']}\") {gap}: {', '.join(shown)}{more}")
    if d["beyond"]:
        n = len(d["beyond"])
        names = ", ".join(f"`{p}`" for p in d["beyond"][:SHOWN]) + (f" and {n - SHOWN} more" if n > SHOWN else "")
        parts.append(f"it also changes {names}, which the {'original' if copy else 'reverted'} commit did not touch")
    return f"As a {'copy' if copy else 'revert'}, this change differs from what it {'copies' if copy else 'reverts'}: " + "; ".join(parts) + "."
