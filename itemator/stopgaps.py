"""Stopgaps: an extra kept "until #N" is asked about again by the merge request that closes #N.

A workaround is often merged on purpose: a pinned old library, a patch script, a CI job turned off, "until the real fix
lands". The fix lands months later and the workaround stays, because nobody remembers it was meant to go. A person who
answers an extra's thread with `until #N` keeps it, and the reaction flow writes one note on issue #N (RECORD). When a
later merge request closes #N, the CI job reads those notes, checks whether the stopgap is still in the code at that
merge request's head, and opens one thread per stopgap still there. Its answers: the name (it stays, on purpose),
`not an extra`, or `taken out` once the merge request removes it (the flow checks that the line is gone).

Only notes written by the reaction account count (anyone can comment on a public issue), and only a stopgap from a
merge request that was merged (one that was closed never reached the code, and the one being checked is still open). "Still there" is measured on the lines the
stopgap's merge request added to the file: a file that is gone, or that holds none of its longer added lines, is taken
out. Information for the card; standard library only; no model."""
from __future__ import annotations

import re

KIND = "stopgap_due"
MIN_LINE = 12             # an added line shorter than this ("fi", "}", "end") says nothing about whether the stopgap is there
MAX_RECORDS = 10          # stopgap notes read per issue
RECORD = re.compile(r"^Stopgap from !(\d+): `([^`\n]+)` was kept until this issue is fixed, by @([A-Za-z0-9_.-]+)\.")
UNTIL_OFFER = "To keep it only until an issue is fixed, reply `until #` followed by that issue's number."
TAKE_OUT = "To take it out, change `{path}` in this merge request so that `{line}` is gone, then reply `taken out`."


def records(notes: list, react_bot: str) -> list[dict]:
    """[{"from", "path", "who", "note"}]: the stopgap notes on one issue, oldest first, one per (merge request, path)."""
    out, seen = [], set()
    for n in sorted(notes or [], key=lambda n: (n.get("created_at") or "", n.get("id") or 0)):
        if n.get("system") or (n.get("author") or {}).get("username") != react_bot:
            continue
        m = RECORD.match(n.get("body") or "")
        if not m or (m.group(1), m.group(2)) in seen:
            continue
        seen.add((m.group(1), m.group(2)))
        out.append({"from": int(m.group(1)), "path": m.group(2), "who": m.group(3), "note": n.get("id")})
        if len(out) >= MAX_RECORDS:
            break
    return out


def added_lines(diffs: list, path: str) -> list[str] | None:
    """The lines the stopgap's merge request added to `path` (stripped), or None when its diff does not touch `path`.
    GitLab's diff text starts at the first hunk header, so no "+++" line is in it."""
    entry = next((d for d in diffs or [] if d.get("new_path") == path), None)
    if entry is None:
        return None
    return [ln[1:].strip() for ln in (entry.get("diff") or "").split("\n") if ln.startswith("+")]


def still_there(added: list[str], head_text: str | None) -> str | None:
    """The first longer added line still in the file at the head (the line `taken out` is checked against), or None
    when the file is gone or holds none of them. A line with a backtick is passed over: the thread quotes it."""
    if head_text is None:
        return None
    lines = {ln.strip() for ln in head_text.split("\n")}
    return next((a for a in added if len(a) >= MIN_LINE and "`" not in a and a in lines), None)


def why(rec: dict, issue_ref: str) -> str:
    return (f"was kept in !{rec['from']} until {issue_ref} is fixed, by @{rec['who']}; this merge request closes {issue_ref}, "
            f"and the stopgap is still in the file")
