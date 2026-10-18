"""Do the commits a change cites exist? Standard library only; no model.

Agents (and people) write "Fixes: 1a2b3c4 (\"title\")", "This reverts commit ...", "cherry picked from commit ..." and
"commit ..." in commit messages and descriptions. A cited id that this project has no commit for, or a quoted title that is not
the title of the commit with that id, is worth a reviewer's second look: it was copied wrongly, comes from another project, or
was never there. The kernel's checkpatch and linux-next checks do this for kernel history; this reads the change's own
commit messages, its title and its description.

Existence is asked of the local checkout first and then of the project's API, because a CI checkout can be shallow and a real
commit would look missing. A commit the API cannot be asked about is left out, never reported."""
from __future__ import annotations

import re
import subprocess
import urllib.parse

from itemator import fence as FE

MAX_CITED = 25            # distinct ids looked up per change
SHOWN = 3

_HEX = r"[0-9a-f]{7,40}"
_PATTERNS = (
    ("fixes", re.compile(rf"\bFixes:[ \t]*({_HEX})\b(?:[ \t]*\(?[\"'](.+?)[\"']\)?)?", re.I)),
    ("revert", re.compile(rf"\bThis reverts commit[ \t]+({_HEX})\b()", re.I)),
    ("cherry-pick", re.compile(rf"\bcherry[- ]picked from commit[ \t]+({_HEX})\b()", re.I)),
    ("upstream", re.compile(rf"\bcommit[ \t]+({_HEX})[ \t]+upstream\b()", re.I)),
    ("upstream", re.compile(rf"\bupstream commit[ \t]+({_HEX})\b()", re.I)),
    ("commit", re.compile(rf"\bcommit[ \t]+`?({_HEX})\b`?()", re.I)),
)
_WORDS = re.compile(r"[^a-z0-9]+")


def cited(text: str) -> list[dict]:
    """[{id, how, quoted}] in order of first mention, one per id (the most specific way it is cited wins)."""
    found: dict[str, dict] = {}
    for how, pat in _PATTERNS:
        for m in pat.finditer(text or ""):
            h = m.group(1).lower()
            if not re.search(r"[0-9]", h) and len(h) < 10:        # a word like "defaced" is not an id
                continue
            if h not in found:
                found[h] = {"id": h, "how": how, "quoted": (m.group(2) or "").strip() or None, "at": m.start()}
    return sorted(found.values(), key=lambda d: d["at"])


def same_title(quoted: str, title: str) -> bool:
    """A quoted title agrees when, ignoring case and punctuation, one starts with the other (tools truncate)."""
    a, b = _WORDS.sub(" ", quoted.lower()).strip(), _WORDS.sub(" ", title.lower()).strip()
    return bool(a) and (a.startswith(b) or b.startswith(a))


def _local(repo: str, h: str) -> str | None:
    """The title of the commit `h` in the checkout, or None when the checkout has no such commit."""
    out = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%s", f"{h}^{{commit}}"], capture_output=True, text=True, errors="replace")
    return out.stdout.strip() if out.returncode == 0 else None


def _remote(api, pid, h: str):
    """(known, title): known is False when the API could not be asked or the answer was not clear."""
    try:
        got = api.get(f"/projects/{pid}/repository/commits/{urllib.parse.quote(h)}", missing_ok=True)
    except Exception:                 # noqa: BLE001 -- an API that cannot answer says nothing
        return False, None
    if got is None:
        return True, None
    if isinstance(got, dict) and isinstance(got.get("title"), str):
        return True, got["title"]
    return False, None


def find(repo: str, text: str, api, pid, warnings: list) -> list[dict]:
    """[{id, how, kind, quoted, title}] with kind "missing" (no such commit) or "title_differs" (the quoted title is another commit's)."""
    out = []
    for c in cited(text)[:MAX_CITED]:
        title = _local(repo, c["id"])
        if title is None:
            if api is None:
                continue
            known, title = _remote(api, pid, c["id"])
            if not known:
                warnings.append(f"no reference check on {c['id'][:12]}: the API could not say")
                continue
        if title is None:
            out.append({"id": c["id"][:12], "how": c["how"], "kind": "missing", "quoted": c["quoted"], "title": None})
        elif c["quoted"] and not same_title(c["quoted"], title):
            out.append({"id": c["id"][:12], "how": c["how"], "kind": "title_differs", "quoted": FE.tidy(c["quoted"]), "title": FE.tidy(title)})
    return out


_HOW = {"fixes": "as the commit it fixes", "revert": "as the commit it reverts", "cherry-pick": "as the source of a cherry-pick", "upstream": "as the upstream commit", "commit": "by id"}


def sentence(found: list[dict]) -> str:
    parts = []
    for d in found[:SHOWN]:
        if d["kind"] == "missing":
            parts.append(f"`{d['id']}` ({_HOW[d['how']]}) is not a commit of this project")
        else:
            parts.append(f"`{d['id']}` is quoted as \"{d['quoted']}\" but the commit with that id is titled \"{d['title']}\"")
    more = f" and {len(found) - SHOWN} more" if len(found) > SHOWN else ""
    return "The commit messages or the description cite commits that do not check out: " + "; ".join(parts) + more + "."
