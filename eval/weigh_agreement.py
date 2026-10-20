"""Does web/weigh.js (the browser page) measure what itemator/weight.py (the CI job) measures? The rules are in
eval/weigh_agreement_rubric.json, written before the run. Needs node 18 or later and the network. Read-only.

usage: python3 eval/weigh_agreement.py [--lines 30]"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from itemator import registry as RG, weight as W  # noqa: E402

KEYS = ("packages", "direct", "sized", "of", "bytes", "capped")


def sample(result: dict, lines: int) -> list[dict]:
    ok = [r for r in result["rows"] if (r.get("weight") or {}).get("weight") == "ok"]
    return [{"eco": r["ecosystem"], "name": r["name"], "version": r["weight"]["version"]} for r in ok[:lines]]


def compare(py: list, js: list) -> list[dict]:
    out = []
    for a, b in zip(py, js):
        same = a.get("weight") == b.get("weight") == "ok" and all(a[k] == b[k] for k in KEYS)
        out.append({"identical": same, "python": {k: a.get(k) for k in ("weight",) + KEYS}, "browser": {k: b.get(k) for k in ("weight",) + KEYS}})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=int, default=30)
    ap.add_argument("--out", default="results/weigh_agreement_v1.json")
    a = ap.parse_args(argv)
    todo = sample(json.loads((ROOT / "results" / "aidev_weight_v1.json").read_text()), a.lines)
    day = datetime.date.today().isoformat()
    py = [W.weigh(RG.Run(RG.fetch, day)._ask, p["eco"], RG._pep503(p["name"]) if p["eco"] == "PyPI" else p["name"], p["version"]) for p in todo]
    js = json.loads(subprocess.run(["node", str(ROOT / "eval" / "weigh_node.js"), json.dumps(todo)], capture_output=True, text=True,
                                   check=True, timeout=900).stdout)
    rows = compare(py, js)
    out = {"rubric": "eval/weigh_agreement_rubric.json", "checked": datetime.date.today().isoformat(), "lines": len(rows),
           "identical": sum(r["identical"] for r in rows), "all_identical": all(r["identical"] for r in rows),
           "rows": [dict(p, **r) for p, r in zip(todo, rows)]}
    (ROOT / a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"{out['identical']} of {out['lines']} identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
