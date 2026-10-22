"""Exact questions with another checker in the threads (eval/combined_exact_rubric.json, pushed before the run): Overreach
and the Scope Creep Detector re-run on the head-to-head's 454 snapshots, their named files passed through
itemator.other.apply as the CI job does, one question per extra.

usage (local processes only, nothing fetched): python3 eval/combined_exact.py --overreach PATH/overreach --scd PATH/scope_creep.py
  ->  results/combined_exact_v1.json"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import aidev_recall as R  # noqa: E402
import head_to_head as H  # noqa: E402
from itemator import extras as X  # noqa: E402
from itemator import other as OTHER  # noqa: E402

ROOT = H.ROOT
OUT = ROOT / "results" / "combined_exact_v1.json"
SETUPS = {"itemator": (), "with_overreach": ("overreach",), "with_scope_creep_detector": ("scope_creep_detector",),
          "with_both": ("overreach", "scope_creep_detector")}
TOOL = {"overreach": "Overreach", "scope_creep_detector": "the Scope Creep Detector"}


def setup_extras(analysis, rival: dict, files: list, tools: tuple):
    """Itemator's analysis after each rival in `tools` adds its files, in that order, the way ci.py calls other.apply."""
    for t in tools:
        analysis = OTHER.apply(analysis, [(p, "", TOOL[t]) for p in sorted(rival[t])], files)
    return analysis


def listed(analysis, path: str) -> bool:
    return R.listed(analysis.extras, path)


def summarize(rows: list, snaps: list, v1: dict | None = None) -> dict:
    n = len(rows)
    out = {"cases": n, "snapshots": len(snaps), "setups": {}}
    for s in SETUPS:
        q = sum(x["questions"][s] for x in snaps)
        k = sum(r["named"][s] for r in rows)
        out["setups"][s] = {"questions": q, "cases_named": k, "wilson95": H.wilson(k, n),
                            "questions_per_case_named": round(q / k, 1) if k else None}
    if v1:
        out["rerun_check"] = {t: {"files_named_now": sum(x["rival_files"][t] for x in snaps),
                                  "files_named_v1": v1["summary"]["tools"][t]["files_named"]} for t in TOOL}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--overreach", required=True)
    ap.add_argument("--scd", required=True)
    ap.add_argument("--limit", type=int, default=0, help="first N snapshots only (a smoke run; never the result)")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    env = {"PATH": os.environ["PATH"], "OVERREACH_TELEMETRY": "0"}
    rows, snaps = [], []
    with tempfile.TemporaryDirectory() as tmp:
        env["HOME"] = tmp
        items = list(H.snapshots().items())[: a.limit or None]
        for i, ((url, sha), s) in enumerate(items):
            diff = pathlib.Path(tmp) / "change.diff"
            diff.write_text(H.unified_diff(s["files"]))
            o = H.run_json([a.overreach, "-p", s["task"], "--diff", str(diff), "--json", "--no-cache"], env)
            d = H.run_json([sys.executable, "-I", a.scd, "--diff", str(diff), "--intent", s["task"], "--json"], env)
            changed = {f["filename"] for f in s["files"] if f["filename"]}
            rival = {"overreach": H.overreach_named(o) & changed, "scope_creep_detector": H.scd_named(d) & changed}
            files = [f for f in s["files"] if f["filename"]]
            base = X.analyse(s["task"], files, repo=s["repo"], version=6)
            by = {k: setup_extras(base, rival, files, t) for k, t in SETUPS.items()}
            snaps.append({"pr": url, "sha": sha, "questions": {k: len(v.extras) for k, v in by.items()},
                          "rival_files": {t: len(rival[t]) for t in TOOL},
                          "errors": {"overreach": o is None, "scope_creep_detector": d is None}})
            for c in s["cases"]:
                rows.append({"comment_id": c["comment_id"], "pr": url, "path": c["path"],
                             "named": {k: listed(v, c["path"]) for k, v in by.items()}})
            if (i + 1) % 50 == 0:
                print(f"{i + 1}/{len(items)}", file=sys.stderr)
    v1 = json.loads((ROOT / "results" / "head_to_head_v1.json").read_text())
    out = {"rubric": "eval/combined_exact_rubric.json", "limit": a.limit or None,
           "summary": summarize(rows, snaps, None if a.limit else v1), "snapshots": snaps, "rows": rows}
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
