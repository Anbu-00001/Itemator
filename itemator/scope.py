"""The issue's own scope: a block that lists the paths and dependencies a change may touch.

An issue may carry, anywhere in its description, a fenced block tagged `itemator-scope`:

    ```itemator-scope
    paths: src/parser/**, tests/parser/**
    dependencies: none
    ```

`paths` are globs (`*` stays inside one directory, `**` crosses them); `dependencies` are package names, or `none`.
Either line may be left out. With a block, what it declares replaces the reading of the issue's words for that part:

- `paths`: an extra on a file inside the paths is asked for, so it goes (a new dependency only by the list below); a changed file outside them is an extra
  (`outside_scope`), named by its path; no file is left unplaced.
- `dependencies`: every new dependency not on the list is an extra, whatever the issue's words say; one on the list
  is asked for. Package manifests and lockfiles then follow this list, not the paths.

Four kinds never go: the three a policy cannot quiet either (policy.NEVER_IGNORED: an agent instruction file, a
binary or large file, a team policy change), and a test made to pass whatever the code does (hollow.py): a path the
issue allows is not leave to switch its tests off. A broad glob such as `**` is the issue writer's choice; the card says the
block was used. With no block, nothing here changes what the rules found (extras.analyse, RULES_VERSION).
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, replace

from itemator import extras as X
from itemator import packed as PACKED

KIND = "outside_scope"
KEEP = ("binary_or_large_added", "agent_instructions", "policy_changed", "tests_weakened")
_BLOCK = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*itemator-scope[ \t]*\n(.*?)^[ \t]*\1[ \t]*$", re.M | re.S)
_LINE = re.compile(r"^\s*(paths|dependencies)\s*:\s*(.*?)\s*$", re.I)
_ITEM = re.compile(r"[\s,]+")
NOTE = "The issue declares its scope (an `itemator-scope` block), and the check used it in place of the issue's words."


@dataclass(frozen=True)
class Scope:
    paths: tuple | None = None          # None: not declared
    dependencies: tuple | None = None   # () is `none`
    cves: tuple = ()                    # set only by patchday.derive: the scope came from the CVE the issue names

    def to_dict(self) -> dict:
        d = {"paths": list(self.paths) if self.paths is not None else None,
             "dependencies": list(self.dependencies) if self.dependencies is not None else None}
        if self.cves:
            d["cves"] = list(self.cves)
        return d


def read(issue_text: str) -> Scope | None:
    """The first `itemator-scope` block of the issue text; None with no block, or a block that declares nothing."""
    m = _BLOCK.search(issue_text or "")
    if not m:
        return None
    got = {}
    for line in m.group(2).splitlines():
        k = _LINE.match(line)
        if k and k.group(1).lower() not in got:
            items = tuple(i.strip("`'\"") for i in _ITEM.split(k.group(2)) if i.strip("`'\""))
            got[k.group(1).lower()] = () if [i.lower() for i in items] == ["none"] else items
    if got.get("paths") == ():
        del got["paths"]                # `paths: none` would allow no file at all; it is read as not declared
    return Scope(got.get("paths"), got.get("dependencies")) if got else None


def _rx(glob: str):
    glob = glob.lstrip("/")
    if glob.endswith("/"):
        glob += "**"
    body = "".join("(?:.+/)?" if t == "**/" else ".*" if t == "**" else "[^/]*" if t == "*" else re.escape(t)
                   for t in re.split(r"(\*\*/|\*\*|\*)", glob))
    return re.compile(body)


def inside(scope: Scope, path: str) -> bool:
    return any(_rx(g).fullmatch(path) for g in scope.paths or ())


def _squash(name: str) -> str:
    return re.sub(r"[-_.]+", "", name.lower())


def _dependency_file(path: str) -> bool:
    return bool(X._manifest_kind(path)) or posixpath.basename(path) in X._LOCKFILES


def _all_new_dependencies(files) -> list:
    """Every new dependency, named or not: rule 1's and the one-line package.json reader's."""
    found = X._new_dependencies("", files)
    return found + PACKED.find("", files, {(e.path, e.name.lower()) for e in found})


def _paths_of(e) -> tuple:
    return e.detail if e.detail and e.path.endswith("/") else (e.path,)


def apply(scope: Scope | None, analysis: X.Analysis, files: list[dict]) -> X.Analysis:
    """`analysis` with the scope's declarations in place of the rules' reading of the issue's words."""
    if scope is None:
        return analysis
    deps = scope.dependencies is not None
    found = list(analysis.extras)
    if deps:
        allowed = {_squash(d) for d in scope.dependencies}
        found = [e for e in found if e.kind != "new_dependency"]
        found += [replace(e, why=f"adds package {e.name}; the issue's scope "
                              + (f"lists only {', '.join(scope.dependencies)}" if allowed else "lists no new dependency"))
                  for e in _all_new_dependencies(files) if _squash(e.name) not in allowed]
    unplaced, stray = analysis.unplaced, analysis.stray
    if scope.paths is not None:
        keep = lambda e: (e.kind in KEEP or e.kind == "new_dependency"      # only the dependency list allows a package
                          or not all(inside(scope, p) for p in _paths_of(e)))
        found = [e for e in found if keep(e)]
        covered = {p for e in found for p in (e.detail or ()) + (e.path,)}
        found += [X.Extra(KIND, p, p, f"changes {p}, outside the paths the issue's scope lists ({', '.join(scope.paths)})")
                  for p in sorted(f["filename"] for f in files if f.get("filename"))
                  if p not in covered and not inside(scope, p) and not (deps and _dependency_file(p))]
        unplaced, stray = [], [p for p in analysis.stray if not inside(scope, p)]
    found = X.sort_extras(set(found))
    return replace(analysis, extras=found, unplaced=unplaced, stray=stray)
