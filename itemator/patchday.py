"""Patch day: an issue that names a CVE asks for a version change, so the version change is the fix and every other
file is an extra.

It applies only when the linked issue names a CVE (`CVE-2026-109618`), carries no `itemator-scope` block (which wins),
and the change has at least one file whose every hunk only swaps versions: removed and added lines pair up one to one
and are the same once dotted versions and hex digests are blanked out. When the issue lists dotted versions (php.net's
"fixed in 8.3.36"), each new version must be one of them, or that file is not the fix and is asked about. Those files,
plus a lockfile in the same directory, become the scope (scope.Scope); scope.apply does the rest. It never judges
whether a version is safe: dependency and container scanning do that. Fixed rules, no model.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import replace

from itemator import extras as X
from itemator import scope as SCOPE

_CVE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.I)
_DIGEST = re.compile(r"(?:sha(?:256|384|512)[-:])?[A-Za-z0-9+/]{40,}={0,2}|\b[0-9a-f]{12,}\b")
NOTE = "The issue names {cves}, so the check took its version change as the fix and asked about every other file."


def cves(text: str) -> tuple:
    return tuple(sorted({m.upper() for m in _CVE.findall(text or "")}))


def listed_versions(text: str) -> set:
    """Dotted versions the issue names (a CVE id has no dots, so it is never one)."""
    return set(X._DOTTED_VERSION.findall(text or ""))


def _blank(line: str) -> str:
    return X._DOTTED_VERSION.sub("V", _DIGEST.sub("D", line))


def _hunks(patch: str | None) -> list:
    out, cur = [], None
    for line in (patch or "").splitlines():
        if line.startswith("@@"):
            cur = ([], [])
            out.append(cur)
        elif cur is not None and line[:1] == "-" and not line.startswith("---"):
            cur[0].append(line[1:])
        elif cur is not None and line[:1] == "+" and not line.startswith("+++"):
            cur[1].append(line[1:])
    return out


def version_swap(f: dict, listed: set) -> bool:
    """Every hunk of the file swaps versions and nothing else; with versions listed, each new one is among them."""
    if f.get("status") not in (None, "modified"):
        return False
    hunks = _hunks(f.get("patch"))
    if not hunks:
        return False
    for old, new in hunks:
        if not old or len(old) != len(new):
            return False
        for a, b in zip(old, new):
            if a == b or _blank(a) != _blank(b):
                return False
            moved = set(X._DOTTED_VERSION.findall(b)) - set(X._DOTTED_VERSION.findall(a))
            if not moved or (listed and not moved <= listed):
                return False
    return True


def derive(issue_text: str, files: list[dict]) -> SCOPE.Scope | None:
    """The scope a CVE issue implies, or None: no CVE, a scope block of its own, or no file that only swaps versions."""
    found = cves(issue_text)
    if not found or SCOPE.read(issue_text) is not None:
        return None
    listed = listed_versions(issue_text)
    fix = [f["filename"] for f in files if f.get("filename") and version_swap(f, listed)]
    if not fix:
        return None
    dirs = {posixpath.dirname(p) for p in fix}
    locks = [f["filename"] for f in files if f.get("filename") and posixpath.basename(f["filename"]) in X._LOCKFILES
             and posixpath.dirname(f["filename"]) in dirs]
    return SCOPE.Scope(paths=tuple(sorted(set(fix + locks))), cves=found)


def reword(scope: SCOPE.Scope | None, analysis: X.Analysis) -> X.Analysis:
    """Say why a file outside a patch-day scope is asked about: the issue's CVE, and which files were the fix."""
    if scope is None or not scope.cves:
        return analysis
    why = lambda p: (f"changes {p}, more than the version change; the issue names {', '.join(scope.cves)}, "
                     f"whose fix is the version change in {', '.join(scope.paths)}")
    return replace(analysis, extras=[replace(e, why=why(e.path)) if e.kind == SCOPE.KIND else e for e in analysis.extras])
