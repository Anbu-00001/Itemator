"""New npm dependencies in a package.json written on one line, or with a dependency object on one line.

Rule 1 reads package.json line by line, one `"name": "version"` pair per line, so the same new dependency goes
silent when the file is minified (an outside reviewer showed this). This reads each side of the patch as text and
takes every pair inside a `dependencies`, `devDependencies`, `optionalDependencies` or `peerDependencies` object
that opens and closes on the lines shown. A name on the new side that is not on the old side, that rule 1 did not
already list, and that the issue does not name, is a new dependency. Other manifest formats were checked by hand
and already read inline forms (a pyproject array on one line, a Cargo inline table). It only adds extras, so the
rules (extras.py, RULES_VERSION) are unchanged.
"""
from __future__ import annotations

import posixpath
import re

from itemator import extras as X

ONE_LINE = "it sits on one line with its object's braces, so taking it out is left to a person"
_OBJECT = re.compile(r'"(?:dependencies|devDependencies|optionalDependencies|peerDependencies)"\s*:\s*\{([^{}]*)\}')
_PAIR = re.compile(r'"((?:@[^"/\s]+/)?[^"@\s][^"\s]*)"\s*:\s*"[^"]*"')


def _names(text: str) -> list[str]:
    """The pairs of every dependency object that opens and closes on one line of `text`, in order, once each."""
    return list(dict.fromkeys(n for line in text.splitlines() for m in _OBJECT.finditer(line) for n in _PAIR.findall(m.group(1))))


def _side(patch: str, signs: tuple) -> str:
    return "\n".join(t for s, t in X._lines(patch) if s in signs)


def find(issue_text: str, files: list[dict], listed: frozenset | set = frozenset()) -> list:
    """Extras for new npm dependencies rule 1 cannot see. `listed`: (path, name) pairs rule 1 already lists."""
    out = []
    for f in files:
        path = f.get("filename") or ""
        if posixpath.basename(path) != "package.json" or not f.get("patch") or f.get("status") == "removed":
            continue
        new = _names(_side(f["patch"], ("+",)))
        old = set(_PAIR.findall(_side(f["patch"], ("-", " "))))       # any pair the old side shows, in an object or not
        for name in new:
            low = name.lower()
            if low in {o.lower() for o in old} or (path, low) in listed:      # a move, a bump, or rule 1's
                continue
            short = name.rsplit("/", 1)[-1]
            if X._mentions(issue_text or "", name) or (short != name and X._mentions(issue_text or "", short)):
                continue
            out.append(X.Extra("new_dependency", path, name, f"adds package {name}; the issue does not name it; {ONE_LINE}"))
    return out


def one_line(e) -> bool:
    return e.kind == "new_dependency" and e.why.endswith(ONE_LINE)


def apply(analysis: X.Analysis, issue_text: str, files: list[dict]) -> X.Analysis:
    listed = {(e.path, e.name.lower()) for e in analysis.extras if e.kind == "new_dependency"}
    more = find(issue_text, files, listed)
    if not more:
        return analysis
    return X.Analysis(**{**analysis.__dict__, "extras": X.sort_extras(analysis.extras + more)})
