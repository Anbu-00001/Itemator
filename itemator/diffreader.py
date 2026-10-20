"""Read a git diff or patch into the files the added-line checks take: {filename, status, patch (hunks only), binary}.
The browser page (web/try_checks.js, parseDiff) does the same; eval/try_agreement.py compares the two. Standard library only."""
from __future__ import annotations

import re


def files_of(patch: str) -> list[dict]:
    """The files of a git patch as the checks read them: {filename, status, patch (hunks only)}."""
    out = []
    for block in re.split(r"(?m)^diff --git ", patch)[1:]:
        m = re.match(r"a/(\S+) b/(\S+)", block)
        if not m:
            continue
        hunks = block[block.find("\n@@"):].lstrip("\n") if "\n@@" in block else ""
        hunks = re.split(r"(?m)^-- $", hunks)[0]                  # the trailer of a format-patch mail
        status = "added" if re.search(r"(?m)^new file mode", block) else "removed" if re.search(r"(?m)^deleted file mode", block) else "modified"
        out.append({"filename": m.group(2), "status": status, "patch": hunks, "binary": bool(re.search(r"(?m)^(?:Binary files|GIT binary patch)", block))})
    return out
