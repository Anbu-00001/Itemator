"""Packages a change adds to setuptools' own lists: `install_requires` and `[options.extras_require]` in setup.cfg,
`install_requires=[...]` and `extras_require={...}` in setup.py.

Rule 1 reads requirements files and pyproject.toml, not these lists, so a package added to setup.cfg was only
"changes build config", with no registry facts (a blind judge, round 9, added `reqeusts` there and it was not named).
This reads the lists in the diff and lists each package the added lines bring in as a new dependency on that file,
unless the issue names it or the old side already had it. The registry lookup then treats it as a PyPI package
(registry.request_for asks `ecosystem`). A hunk that starts inside a list, with no key line above it, is not read.
It only adds extras, so the rules (extras.py, RULES_VERSION) are unchanged.
"""
from __future__ import annotations

import posixpath
import re

from itemator import extras as X

LISTED = "listed in the setuptools requirements"
_CFG_KEY = re.compile(r"^(\w[\w.\-]*)\s*=\s*(.*)$")
_PY_OPEN = re.compile(r"\b(install_requires|extras_require)\s*=\s*([\[{])")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _cfg(patch: str):
    """(sign, package) for each requirement in install_requires or [options.extras_require], context lines included."""
    section, listing = None, False
    for sign, text in X._lines(patch):
        if sign == "@":
            section, listing = None, False
            continue
        s = text.strip()
        if not s or s.startswith(("#", ";")):
            continue
        if s.startswith("[") and s.endswith("]"):
            section, listing = s[1:-1].strip(), False
            continue
        if text[:1] in (" ", "\t"):                     # a continuation line belongs to the key above it
            if listing:
                m = X._REQ_LINE.match(s)
                if m:
                    yield sign, m.group(1)
            continue
        m = _CFG_KEY.match(s)
        if not m:
            listing = False
            continue
        key, value = m.groups()
        listing = (section == "options" and key == "install_requires") or section == "options.extras_require"
        if listing and value:
            for part in value.split(","):               # an inline value: `install_requires = a, b`
                r = X._REQ_LINE.match(part.strip())
                if r:
                    yield sign, r.group(1)


def _py(patch: str):
    """(sign, package) for each quoted requirement between install_requires=[ or extras_require={ and its close."""
    depth = 0
    for sign, text in X._lines(patch):
        if sign == "@":
            depth = 0
            continue
        m = _PY_OPEN.search(text)
        rest = text[m.end() - 1:] if m else (text if depth else "")
        if not rest:
            continue
        for q in X._QUOTED_REQ.finditer(rest):
            if not rest[q.end():].lstrip().startswith(":"):     # an extras_require key ("dev": [...]) is not a package
                yield sign, q.group(1)
        depth = max(depth + rest.count("[") + rest.count("{") - rest.count("]") - rest.count("}"), 0)


_READERS = {"setup.cfg": _cfg, "setup.py": _py}


def ecosystem(e) -> str | None:
    """'PyPI' for an extra this module made, None for any other extra."""
    return "PyPI" if e.kind == "new_dependency" and e.why.endswith(LISTED) else None


def find(issue_text: str, files: list[dict]) -> list:
    out = []
    for f in files:
        path = f.get("filename") or ""
        read = _READERS.get(posixpath.basename(path))
        if not read or f.get("status") == "removed" or not f.get("patch"):
            continue
        pairs = list(read(f["patch"]))
        old = {_norm(n) for s, n in pairs if s in ("-", " ")}
        for name in dict.fromkeys(n for s, n in pairs if s == "+"):
            if _norm(name) in old or X._mentions(issue_text or "", name):
                continue
            out.append(X.Extra("new_dependency", path, name,
                               f"adds package {name}; the issue does not name it; from PyPI; {LISTED}"))
    return out


def apply(analysis: X.Analysis, issue_text: str, files: list[dict]) -> X.Analysis:
    have = {(e.path, _norm(e.name)) for e in analysis.extras if e.kind == "new_dependency"}
    more = [e for e in find(issue_text, files) if (e.path, _norm(e.name)) not in have]
    if not more:
        return analysis
    return X.Analysis(**{**analysis.__dict__, "extras": X.sort_extras(analysis.extras + more)})
