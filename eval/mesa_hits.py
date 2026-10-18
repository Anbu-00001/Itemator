"""Which Mesa reverts and backports does the revert or copy check speak on, and what does it say? Lists every hit of the noise run.
The rules for reading them are in eval/mesa_hit_labels_rubric.json. Read-only; standard library only.

usage: python3 eval/mesa_hits.py --repo work/mesa-replay/mesa.git --out results/mesa_hits_v1.json"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
import mesa_noise as MN  # noqa: E402

SAMPLE = 25
SEED = MN.SEED


def hits(repo: str, shas: list[str], check: str) -> list[dict]:
    out = []
    for sha in shas:
        got = MN.read_commit(repo, sha)
        if got is None:
            continue
        msg, files = got
        said = MN.speaks(check, repo, sha, msg, files)
        if said:
            out.append({"commit": sha, "said": said})
    return out


def sample(rows: list[dict], n: int = SAMPLE) -> list[str]:
    ids = sorted(r["commit"] for r in rows)
    random.Random(SEED).shuffle(ids)
    return ids[:n]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = {"rubric": "eval/mesa_hit_labels_rubric.json", "seed": SEED}
    for part, grep, how, need, check in (("reverts", "This reverts commit", "revert", MN.REVERTS, "revert"),
                                         ("backports", "cherry picked from commit", "cherry-pick", MN.BACKPORTS, "copy")):
        shas = MN.quoting_ids(a.repo, grep, how, need)
        rows = hits(a.repo, shas, check)
        out[part] = {"read": len(shas), "spoke": len(rows), "sample": sample(rows), "hits": rows}
        print(part, len(shas), "read,", len(rows), "spoke", flush=True)
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
