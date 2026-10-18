"""Which files in a change have never changed together with any other file in it? Standard library only; no model.

`strangers(histories)` takes, for each modified file, the ids of the earlier commits that touched it, and says for each
file one of:

  stranger         the file has history (at least MIN_HISTORY commits) and shares no commit with any other file here
  partnered        it shares at least one commit with another file here
  too_new          fewer than MIN_HISTORY earlier commits: "never changed together" would mean nothing yet
  not_enough_files fewer than three files with any history, so there is nothing to compare with

A commit found in the history of more than half of the files is dropped first: a sweeping rename or reformat touches
everything and says nothing about which files belong together. A stranger is a fact about the repository's past, not a
verdict: a new feature may well touch a file that has never moved with its neighbours."""
from __future__ import annotations

import subprocess

HISTORY_LIMIT = 100        # commits read per file, newest first; a busy file's older partners are missed
MAX_FILES = 40             # a change touching more modified files is not read (eval/stranger_spike_rubric.json)
MIN_HISTORY = 3
SWEEP_SHARE = 0.5
MIN_FILES = 3

STRANGER, PARTNERED, TOO_NEW, NOT_ENOUGH = "stranger", "partnered", "too_new", "not_enough_files"


def strangers(histories: dict[str, list[str]]) -> dict[str, str]:
    with_history = {f: set(h) for f, h in histories.items() if h}
    if len(with_history) < MIN_FILES:
        return {f: NOT_ENOUGH for f in histories}
    counts: dict[str, int] = {}
    for shas in with_history.values():
        for s in shas:
            counts[s] = counts.get(s, 0) + 1
    sweeping = {s for s, n in counts.items() if n > SWEEP_SHARE * len(with_history)}
    kept = {f: shas - sweeping for f, shas in with_history.items()}
    out = {}
    for f, hist in histories.items():
        if len(set(hist)) < MIN_HISTORY:
            out[f] = TOO_NEW
        else:
            shares = any(kept[f] & kept[g] for g in kept if g != f)
            out[f] = PARTNERED if shares else STRANGER
    return out


def history(repo: str, ref: str, path: str, limit: int = HISTORY_LIMIT) -> list[str]:
    """The ids of up to `limit` commits that touched `path`, newest first, from `ref` backwards; [] when git cannot say."""
    out = subprocess.run(["git", "-C", repo, "log", f"--max-count={limit}", "--format=%H", ref, "--", path], capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []
