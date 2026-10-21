"""Git hooks: files that run on the machine of everyone who commits, pushes or checks out.

A new `.githooks/pre-commit` was only a file the rules "could not place" (an outside reviewer showed this), yet git
runs it on each contributor's machine once the project points `core.hooksPath` at it, and hook managers (Husky,
Lefthook, pre-commit's own hooks directory) install them by themselves. This names an added or changed hook file, and
an added line that points `core.hooksPath` somewhere, unless the issue says "hook" or names the file. It only adds
extras, so the rules (extras.py, RULES_VERSION) are unchanged.
"""
from __future__ import annotations

import posixpath
import re

from itemator import extras as X

KIND = "git_hook"
HOOK_NAMES = {"applypatch-msg", "pre-applypatch", "post-applypatch", "pre-commit", "pre-merge-commit",
              "prepare-commit-msg", "commit-msg", "post-commit", "pre-rebase", "post-checkout", "post-merge",
              "pre-push", "post-rewrite", "pre-auto-gc", "reference-transaction", "push-to-checkout"}
_HOOK_DIRS = {".githooks", ".git-hooks", "githooks", "git-hooks", ".husky", ".hooks", "hooks"}
_MANAGERS = {"lefthook.yml", ".lefthook.yml", "lefthook.yaml", ".lefthook.yaml", ".huskyrc", ".huskyrc.json"}
_HOOKS_PATH = re.compile(r"\bcore\.hooks[Pp]ath\b")


def is_hook(path: str) -> bool:
    b, parts = posixpath.basename(path), path.split("/")[:-1]
    if b in _MANAGERS:
        return True
    if not parts or parts[-1] not in _HOOK_DIRS:      # so .husky/_/, Husky's own generated helper, is not one
        return False
    stem = b.rsplit(".", 1)[0] if "." in b[1:] else b
    return stem in HOOK_NAMES or parts[-1] in (".githooks", ".git-hooks", "githooks", "git-hooks", ".husky")


def _asked(issue_text: str, path: str) -> bool:
    return any(X._mentions(issue_text or "", w) for w in ("hook", "hooks", "husky", "lefthook", X._base(path)))


def find(issue_text: str, files: list[dict]) -> list:
    out = []
    for f in files:
        path = f.get("filename") or ""
        if f.get("status") == "removed" or _asked(issue_text, path):
            continue
        if is_hook(path):
            verb = "adds" if f.get("status") == "added" else "changes"
            out.append(X.Extra(KIND, path, path, f"{verb} a git hook, which runs on the machine of everyone who works "
                                                 "on the project; the issue does not ask for it"))
        elif any(s == "+" and _HOOKS_PATH.search(t) for s, t in X._lines(f.get("patch"))):
            out.append(X.Extra(KIND, path, path, "points git's hooks directory somewhere new, so the hooks there run on "
                                                 "every contributor's machine; the issue does not ask for it"))
    return out


def apply(analysis: X.Analysis, issue_text: str, files: list[dict]) -> X.Analysis:
    more = find(issue_text, files)
    if not more:
        return analysis
    paths = {e.path for e in more}
    kept = [e for e in analysis.extras if not (e.kind == "stray_file" and e.path in paths)]    # the hook says more
    return X.Analysis(**{**analysis.__dict__, "extras": X.sort_extras(kept + more),
                         "unplaced": [u for u in analysis.unplaced if u not in paths]})
