"""How often do the card's newest no-model checks speak on ordinary commits, and on real reverts and real backports?
The rules are in eval/mesa_noise_rubric.json, written before any commit was read. Read-only; standard library only.

usage: python3 eval/mesa_noise.py --repo work/mesa-replay/mesa.git --out results/mesa_noise_v1.json [--limit N]"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
import incident_replay as IR  # noqa: E402
from itemator import moving as MV  # noqa: E402
from itemator import record as RC  # noqa: E402
from itemator import refs as RF  # noqa: E402
from itemator import revert as RV  # noqa: E402
from itemator import shapes as SH  # noqa: E402
from itemator import untrusted as UT  # noqa: E402

SEED = 20261018
ORDINARY, REVERTS, BACKPORTS = 1500, 1000, 1000
WINDOW = ("2024-01-01", "2026-09-30")
MAX_FILES = 300
BAR_SHARE, BAR_UPPER = 0.03, 0.05
EXAMPLES = 10


def git(repo: str, *args: str, timeout: int = 120) -> str:
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, errors="replace", timeout=timeout)
    return out.stdout if out.returncode == 0 else ""


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def shuffled(ids: list[str], limit: int) -> list[str]:
    ids = sorted(ids)
    random.Random(SEED).shuffle(ids)
    return ids[:limit]


def ordinary_ids(repo: str) -> list[str]:
    return git(repo, "log", "--no-merges", f"--since={WINDOW[0]}", f"--until={WINDOW[1]}", "--format=%H").split()


def quoting_ids(repo: str, grep: str, how: str, need: int) -> list[str]:
    """The first `need` commits, in the seeded shuffle of all commits (any branch) whose message has `grep`, whose message names a
    commit that exists in the clone in the way `how` reads."""
    out = []
    for sha in shuffled(git(repo, "log", "--all", "--no-merges", f"--grep={grep}", "--format=%H", timeout=600).split(), 10 ** 9):
        msg = git(repo, "show", "-s", "--format=%B", sha)
        if any(c["how"] == how and RV._local(repo, c["id"]) for c in RF.cited(msg)):
            out.append(sha)
            if len(out) >= need:
                break
    return out


def read_commit(repo: str, sha: str):
    """(message, files) of a non-merge commit against its first parent, or None when it has too many files."""
    names = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha).split("\n")
    if len([n for n in names if n]) > MAX_FILES:
        return None
    msg = git(repo, "show", "-s", "--format=%B", sha)
    files = IR.files_of(git(repo, "show", "--format=", "-U3", "--no-color", sha))
    return msg, files


def speaks(check: str, repo: str, sha: str, msg: str, files: list[dict]):
    """What the check says about this commit (a small JSON-able summary), or None when it says nothing."""
    if check == "moving":
        r = MV.find(files)
        return [{"path": d["path"], "kind": d["kind"]} for d in r] or None
    if check == "shapes":
        r = SH.find(files)
        return [{"path": d["path"], "line": d["line"], "kind": d["kind"]} for d in r] or None
    if check == "untrusted":
        r = UT.find(files)
        return [{"path": d["path"], "line": d["line"], "kind": d["kind"]} for d in r] or None
    if check == "record":
        r = RC.find(repo, sha + "^", files, frozenset(), msg)
        return {"kind": r["kind"], "shipped": len(r["shipped"])} if r else None
    r = RV.find(repo, msg, files, None, None, [], copy=(check == "copy"))
    if not r:
        return None
    return {"left": [{"id": c["id"], "files": c["files"][:5]} for c in r["left"]], "beyond": r["beyond"][:5]}


def readable(check: str, files: list[dict]) -> bool:
    if check in ("moving", "untrusted"):
        return any((UT.is_target(f["filename"]) if check == "untrusted" else MV.is_build_file(f["filename"])) and f["patch"] for f in files)
    return any(f["patch"] for f in files)


def measure(repo: str, shas: list[str], checks: tuple[str, ...], started: float) -> dict:
    rows = {c: {"spoke": 0, "read": 0, "readable": 0, "readable_spoke": 0, "examples": []} for c in checks}
    skipped = 0
    for i, sha in enumerate(shas, 1):
        got = read_commit(repo, sha)
        if got is None:
            skipped += 1
            continue
        msg, files = got
        for c in checks:
            row = rows[c]
            row["read"] += 1
            ok = readable(c, files)
            row["readable"] += ok
            try:
                said = speaks(c, repo, sha, msg, files)
            except Exception as e:                      # noqa: BLE001 -- counted, never hidden
                row["errors"] = row.get("errors", 0) + 1
                said = None
                if row["errors"] <= 3:
                    row.setdefault("error_kinds", []).append(type(e).__name__)
            if said:
                row["spoke"] += 1
                row["readable_spoke"] += ok
                if len(row["examples"]) < EXAMPLES:
                    row["examples"].append({"commit": sha[:12], "said": said})
        if i % 100 == 0:
            print(f"{i} read, {time.time() - started:.0f}s", flush=True)
    for row in rows.values():
        lo, hi = wilson(row["spoke"], row["read"])
        rl, rh = wilson(row["readable_spoke"], row["readable"])
        row.update({"share": round(row["spoke"] / row["read"], 4) if row["read"] else None, "wilson": [round(lo, 4), round(hi, 4)],
                    "share_of_readable": round(row["readable_spoke"] / row["readable"], 4) if row["readable"] else None, "wilson_readable": [round(rl, 4), round(rh, 4)]})
    return {"skipped_too_many_files": skipped, "checks": rows}


def verdict(row: dict) -> str:
    if row["read"] == 0:
        return "no commits read"
    return "met" if row["share"] <= BAR_SHARE and row["wilson"][1] <= BAR_UPPER else "not met"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="read only this many commits per sample (a trial of the script, not the registered run)")
    a = ap.parse_args(argv)
    t0 = time.time()
    n = lambda full: a.limit or full                      # noqa: E731
    out = {"rubric": "eval/mesa_noise_rubric.json", "seed": SEED, "limit_trial": a.limit or None}
    ordinary = shuffled(ordinary_ids(a.repo), n(ORDINARY))
    out["ordinary"] = {"sampled": len(ordinary), **measure(a.repo, ordinary, ("moving", "shapes", "untrusted", "record"), t0)}
    for row in out["ordinary"]["checks"].values():
        row["rule"] = verdict(row)
    reverts = quoting_ids(a.repo, "This reverts commit", "revert", n(REVERTS))
    out["reverts"] = {"sampled": len(reverts), **measure(a.repo, reverts, ("revert",), t0)}
    backports = quoting_ids(a.repo, "cherry picked from commit", "cherry-pick", n(BACKPORTS))
    out["backports"] = {"sampled": len(backports), **measure(a.repo, backports, ("copy",), t0)}
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1)
    for part in ("ordinary", "reverts", "backports"):
        for c, row in out[part]["checks"].items():
            print(f"{part}/{c}: spoke on {row['spoke']} of {row['read']} (wilson {row['wilson']})" + (f" -> {row['rule']}" if "rule" in row else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
