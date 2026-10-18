"""Does this project keep a written record per change, and does this change add one? Standard library only; no model.

Tor, Apache httpd, OpenSSL, FreeBSD and OpenBSD all ask for a short note with every change a user could notice, and exempt
the rest (changes to files that are not shipped, moves, comment edits). Here the project's own history says whether it keeps such a
record: among its last commits that changed shipped files, enough added a file under a record directory (`changes/`,
`changelog.d/`, `newsfragments/`, `.changeset/`) or edited a changelog file (`CHANGELOG.md`, `NEWS`, `HISTORY`). If it does, and this
change touches shipped files and adds no record, the card says so, with the files the layout check already proved layout-only and
the files that are not shipped (tests, documentation, pipeline files) left out. Nothing is configured. It is information only: a
project without the habit gets nothing, and a text that says no record is needed gets nothing."""
from __future__ import annotations

import re
import subprocess
from collections import Counter

from itemator import fence as FE
from itemator import pipeline as PL

HISTORY = 100             # commits read from the target branch
MIN_CODE_COMMITS = 10     # commits that changed shipped files before a habit can be seen
MIN_WITH_RECORD = 5
MIN_SHARE = 0.4
SHOWN = 3

_DIR = re.compile(r"^(?:.*/)?(?P<d>changes|changelog\.d|changelog|newsfragments|news\.d|\.changes|\.changeset|releasenotes/notes)/[^/]+$", re.I)
_EXT = r"(?:\.(?:md|markdown|rst|txt|adoc|org))?"
_FILE = re.compile(rf"^(?:.*/)?(?P<f>CHANGELOG{_EXT}|CHANGES{_EXT}|NEWS{_EXT}|HISTORY{_EXT}|RELEASE[-_]?NOTES{_EXT})$", re.I)
_SKIP_WORDS = re.compile(r"\b(?:no|skip|without|not? needed|n/a)\W+(?:change ?log|changes? file|news|release notes?|record)\b|\[(?:skip|no)[- ]?(?:change ?log|news)\]|\bno_news_changes_needed\b", re.I)


def kind_of(path: str) -> str | None:
    """The record a path belongs to ("changes/" or "CHANGELOG.md"), or None."""
    m = _DIR.match(path)
    if m:
        return m.group("d").lower() + "/"
    m = _FILE.match(path)
    return m.group("f") if m else None


def shipped(path: str) -> bool:
    """A file whose change a user could notice: not a test, documentation, lock, pipeline, record or hidden configuration file."""
    name = path.rsplit("/", 1)[-1]
    return not (FE._SKIP_PATH.search(path) or PL.is_ci_path(path) or kind_of(path) or name.startswith(".")
                or path.startswith((".github/", ".gitlab/")))


def convention(repo: str, base: str) -> dict | None:
    """{"kind", "of", "with"}: the record most commits use, among the last HISTORY commits that changed shipped files, or None
    when the project shows no habit."""
    out = subprocess.run(["git", "-C", repo, "log", "--no-merges", f"--max-count={HISTORY}", "--name-only", "--format=%x1e", base],
                         capture_output=True, text=True, errors="replace")
    if out.returncode != 0:
        return None
    code = with_record = 0
    kinds: Counter = Counter()
    for block in out.stdout.split("\x1e"):
        paths = [p for p in block.split("\n") if p.strip()]
        if not any(shipped(p) for p in paths):
            continue
        code += 1
        got = {k for k in map(kind_of, paths) if k}
        if got:
            with_record += 1
            kinds.update(got)
    if code < MIN_CODE_COMMITS or with_record < MIN_WITH_RECORD or with_record / code < MIN_SHARE:
        return None
    return {"kind": kinds.most_common(1)[0][0], "of": code, "with": with_record}


def find(repo: str, base: str, files: list[dict], layout_only: set | frozenset = frozenset(), text: str = "") -> dict | None:
    """{"kind", "of", "with", "shipped": [path], "exempt": n} when the project keeps a record per change and this change touches
    shipped files without adding one; else None. `layout_only`: paths the layout check proved; `text`: title, description, commits."""
    if _SKIP_WORDS.search(text or ""):
        return None
    if any(kind_of(f.get("filename", "")) for f in files):
        return None
    touched = [f.get("filename", "") for f in files if shipped(f.get("filename", ""))]
    mine = [p for p in touched if p not in layout_only]
    if not mine:
        return None
    conv = convention(repo, base)
    if conv is None:
        return None
    return {**conv, "shipped": mine, "exempt": len(files) - len(mine)}


def sentence(d: dict) -> str:
    n = len(d["shipped"])
    names = ", ".join(f"`{p}`" for p in d["shipped"][:SHOWN]) + (f" and {n - SHOWN} more" if n > SHOWN else "")
    return (f"This project keeps a record per change ({d['with']} of the last {d['of']} commits that changed shipped files added or "
            f"edited one, in {d['kind']}); this change touches {names} and adds none.")
