"""Asked again: a file the team policy quiets (`ignore.paths`, often written by an `always` answer) is asked about again
when the change adds a line of a shape that has carried attacks to it.

`always` on `.gitlab-ci.yml` means "stop asking about routine edits to our CI file"; it never meant "let a download piped
into a shell in". An amended bot merge request that slipped a CI edit past review, and an AI reviewer that passed a
workflow injection, are the cases this answers. The shapes are the card's own fixed-rule checks, read from the added
lines only: itemator.moving (a download piped into a shell; an include, remote include or component on a branch),
itemator.shapes (decode and run, download and run, the environment sent to a server, a download written over a source
file) and itemator.untrusted (text a stranger writes handed to a shell, an interpreter or an AI tool). Standard library
only; no model."""
from __future__ import annotations

from itemator import moving as MV
from itemator import shapes as SP
from itemator import untrusted as UT

MOVING_KINDS = ("pipe-to-shell", "include-branch", "remote-branch", "component-branch")
SHOWN = 2


def find(files: list[dict]) -> dict:
    """{path: [what, ...]}: for each changed file, the shapes its added lines carry, in the order the checks found them."""
    out: dict = {}
    for d in MV.find(files):
        if d["kind"] in MOVING_KINDS:
            out.setdefault(d["path"], []).append(MV._WHAT[d["kind"]])
    for d in SP.find(files):
        out.setdefault(d["path"], []).append(f"a line that {SP._WHAT[d['kind']]} (line {d['line']})")
    for d in UT.find(files):
        out.setdefault(d["path"], []).append(f"a line that {UT._WHAT[d['kind']]} (line {d['line']})")
    return {p: list(dict.fromkeys(w)) for p, w in out.items()}


def hits(found: dict, paths) -> list[tuple[str, list[str]]]:
    """(path, what) for each of `paths` that `found` names, in the order of `paths`."""
    return [(p, found[p]) for p in dict.fromkeys(paths) if p in found]


def sentence(hit: list[tuple[str, list[str]]]) -> str:
    path, what = hit[0]
    more = f" and {len(what) - SHOWN} more" if len(what) > SHOWN else ""
    also = f" (and {len(hit) - 1} more of its files)" if len(hit) > 1 else ""
    return (f"The team policy stops asking about `{path}`{also}, but this change adds {'; '.join(what[:SHOWN])}{more} to it, "
            "so it is asked again.")
