"""The checks that run after the frozen rules (extras.analyse, RULES_VERSION), in order. Each only adds extras,
except the issue's own scope block, which goes last because it can also take extras away (scope.py)."""
from __future__ import annotations

from itemator import extras as X
from itemator import hollow, hooks, installs, packed, scope, setupdeps

ADDERS = (hollow, packed, installs, setupdeps, hooks)


def analyse(issue_text: str, files: list[dict], *, repo: str | None = None) -> tuple[X.Analysis, scope.Scope | None]:
    """The rules' analysis with every later check applied, and the issue's scope block (None without one)."""
    a = X.analyse(issue_text, files, repo=repo)
    for m in ADDERS:
        a = m.apply(a, issue_text, files)
    s = scope.read(issue_text)
    return scope.apply(s, a, files), s
