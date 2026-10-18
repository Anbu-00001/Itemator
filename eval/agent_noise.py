"""How often do the card's newest added-line checks speak on commits that AI coding agents made?
The rules are in eval/agent_noise_rubric.json, written before the checks were run on this data. Read-only; local files only;
standard library only.

usage: python3 eval/agent_noise.py --out results/agent_noise_v1.json [--data eval/cache/aidev/commit_details.json]"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
import mesa_noise as MN  # noqa: E402

CHECKS = ("moving", "shapes", "untrusted")
DATA = ROOT / "eval" / "cache" / "aidev" / "commit_details.json"
EXAMPLES = MN.EXAMPLES
NOTE = ("'agent' and by_agent are the commit author field of the AIDev rows: bot accounts (for example Copilot, devin-ai-integration[bot]) "
        "and also people whose pull request an agent worked on, so the split is by commit author, not a verified split by agent.")
# The builder's reading of each firing commit's added lines, a model's judgement and not a human's: does it match what the check says?
LABELS = {"0f1c4884fa73": "looks right: image tagged latest", "c733757b724e": "looks right: wget piped to sh", "ec71cb0333ef": "looks right: curl piped to sh",
          "a176959fbbf8": "looks right: a pull request's head ref is put into a shell echo"}


def commits(rows: list[dict]) -> dict[str, dict]:
    """{sha: {pr, author, files}}: the file rows grouped by commit, in the shape the CI job reads (filename, status, patch)."""
    out: dict[str, dict] = {}
    for r in rows:
        c = out.setdefault(r["sha"], {"pr": r.get("pr_id"), "author": r.get("author") or "unknown", "files": []})
        c["files"].append({"filename": r.get("filename") or "", "status": r.get("status") or "modified", "patch": r.get("patch") or ""})
    return out


def measure(grouped: dict[str, dict]) -> dict:
    rows = {c: {"spoke": 0, "read": 0, "readable": 0, "readable_spoke": 0, "examples": [], "by_agent": {}} for c in CHECKS}
    no_patch = 0
    for sha in sorted(grouped):
        g = grouped[sha]
        if not any(f["patch"] for f in g["files"]):
            no_patch += 1
            continue
        for c in CHECKS:
            row = rows[c]
            row["read"] += 1
            ok = MN.readable(c, g["files"])
            row["readable"] += ok
            agent = row["by_agent"].setdefault(g["author"], {"read": 0, "spoke": 0})
            agent["read"] += 1
            try:
                said = MN.speaks(c, "", sha, "", g["files"])
            except Exception as e:                      # noqa: BLE001 -- counted, never hidden
                row["errors"] = row.get("errors", 0) + 1
                row.setdefault("error_kinds", []).append(type(e).__name__)
                said = None
            if said:
                row["spoke"] += 1
                row["readable_spoke"] += ok
                agent["spoke"] += 1
                if len(row["examples"]) < EXAMPLES:
                    row["examples"].append({"commit": sha[:12], "pull_request": g["pr"], "agent": g["author"], "said": said})
    for row in rows.values():
        lo, hi = MN.wilson(row["spoke"], row["read"])
        rl, rh = MN.wilson(row["readable_spoke"], row["readable"])
        row.update({"share": round(row["spoke"] / row["read"], 4) if row["read"] else None, "wilson": [round(lo, 4), round(hi, 4)],
                    "share_of_readable": round(row["readable_spoke"] / row["readable"], 4) if row["readable"] else None,
                    "wilson_readable": [round(rl, 4), round(rh, 4)]})
        row["rule"] = MN.verdict(row)
        row["by_agent"] = dict(sorted(row["by_agent"].items(), key=lambda kv: -kv[1]["read"]))
    for row in rows.values():
        for e in row["examples"]:
            e["label"] = LABELS.get(e["commit"], "not labelled")
    return {"note": NOTE, "commits": len(grouped), "commits_without_patch": no_patch, "checks": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--data", default=str(DATA))
    a = ap.parse_args(argv)
    rows = json.load(open(a.data))
    out = {"rubric": "eval/agent_noise_rubric.json", "file_rows": len(rows), **measure(commits(rows))}
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"{out['file_rows']} file rows, {out['commits']} commits, {out['commits_without_patch']} without a patch")
    for c, row in out["checks"].items():
        print(f"{c}: spoke on {row['spoke']} of {row['read']} (wilson {row['wilson']}) -> {row['rule']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
