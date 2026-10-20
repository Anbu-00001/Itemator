"""Untrusted v2 on the same ordinary Mesa commits that results/mesa_noise_v1.json used (same seed, same sample), untrusted check only.
The rules are in eval/untrusted_v2_rubric.json (run C), written before this was run. Read-only; standard library only.

usage: python3 eval/untrusted_v2_noise.py --repo work/mesa-replay/mesa.git --out results/untrusted_v2_noise.json"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mesa_noise as MN  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="a trial of the script on this many commits, not the registered run")
    a = ap.parse_args(argv)
    ids = MN.shuffled(MN.ordinary_ids(a.repo), a.limit or MN.ORDINARY)
    ran = MN.measure(a.repo, ids, ("untrusted",), time.time())
    row = ran["checks"]["untrusted"]
    row["rule"] = MN.verdict(row)
    out = {"rubric": "eval/untrusted_v2_rubric.json", "seed": MN.SEED, "limit_trial": a.limit or None, "ordinary": {"sampled": len(ids), **ran}}
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"ordinary/untrusted: spoke on {row['spoke']} of {row['read']} (wilson {row['wilson']}) -> {row['rule']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
