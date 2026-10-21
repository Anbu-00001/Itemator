"""Another checker's findings: files a different scope tool named, asked about the same way as Itemator's own extras.

The head-to-head (results/head_to_head_v1.json) found two offline scope checkers that name more of the files reviewers
objected to than Itemator's rules do. So a project can run one in an earlier CI job and point ITEMATOR_OTHER_CHECKER at
its JSON output: each changed file it names, and the rules did not, becomes an extra (`named_by_other_checker`) with its
own thread, typed answer, hold and log entry. Read formats: Overreach `--json` (findings[].file), the Scope Creep
Detector skill's `--json` (likely_creep, config_edits, new_deps, api_renames), and a plain
{"tool": NAME, "files": [{"path": P, "why": TEXT}]}. An issue with its own `itemator-scope` block is not changed: the issue
writer's declaration wins (scope.py). The rules (extras.py, RULES_VERSION) are unchanged.
"""
from __future__ import annotations

import json
import os
import re

from itemator import extras as X

KIND = "named_by_other_checker"
_SCD = ("likely_creep", "config_edits", "new_deps", "api_renames")
_WHY = 160                 # a checker's own words are cut to this many characters
_UNSAFE = re.compile(r"[`@<>\[\]]")   # the job that writes the file can be edited by the merge request: no mention, link or code span


def parse(data) -> list[tuple[str, str, str]]:
    """(path, why, tool) per named file, first mention kept; [] for anything it cannot read."""
    if not isinstance(data, dict):
        return []
    found = []
    if isinstance(data.get("findings"), list):
        found += [(f.get("file"), f.get("detail") or f.get("kind") or "", "Overreach") for f in data["findings"] if isinstance(f, dict)]
    if any(isinstance(data.get(k), list) for k in _SCD):
        for k in _SCD:
            for x in data.get(k) or ():
                if isinstance(x, dict):
                    found.append((x.get("path") or x.get("file"), "; ".join(map(str, x.get("reasons") or ())) or k.replace("_", " "),
                                  "the Scope Creep Detector"))
    if isinstance(data.get("files"), list):
        tool = str(data.get("tool") or "another checker")
        found += [(f.get("path"), f.get("why") or "", tool) for f in data["files"] if isinstance(f, dict)]
    out, seen = [], set()
    for path, why, tool in found:
        if isinstance(path, str) and path and path not in seen:
            seen.add(path)
            out.append((path, _UNSAFE.sub("", " ".join(str(why).split()))[:_WHY], _UNSAFE.sub("", tool)[:40]))
    return out


def read(path: str | None, repo_dir: str | None = None) -> list[tuple[str, str, str]] | bool | None:
    """The named files from the JSON file at `path` (relative to `repo_dir`, the checkout: the policy job runs the
    checker from another directory); None when no file is set, False when it cannot be read, [] when it names nothing."""
    if not path:
        return None
    if repo_dir and not os.path.isabs(path):
        path = os.path.join(repo_dir, path)
    try:
        with open(path, encoding="utf-8") as fh:
            return parse(json.load(fh))
    except (OSError, ValueError):
        return False


def covered(analysis: X.Analysis, path: str) -> bool:
    """An extra already names the file, a directory holding it, or lists it among a mass event's files."""
    for e in analysis.extras:
        names = [e.path] + [d for d in (e.detail or ()) if isinstance(d, str)]
        if any(n == path or (n.endswith("/") and path.startswith(n)) for n in names if n):
            return True
    return False


def apply(analysis: X.Analysis, named: list | None, files: list[dict], scope=None) -> X.Analysis:
    if not named or scope is not None:
        return analysis
    changed = {f["filename"] for f in files}
    more = [X.Extra(KIND, p, p, f"{tool} named it ({why or 'no reason given'}); Itemator's own rules did not")
            for p, why, tool in named if p in changed and not covered(analysis, p)]
    if not more:
        return analysis
    paths = {e.path for e in more}
    return X.Analysis(**{**analysis.__dict__, "extras": X.sort_extras(list(analysis.extras) + more),
                         "unplaced": [u for u in analysis.unplaced if u not in paths]})
