"""A correction to the weight study, registered before it ran (ana 5f6458, 1ac2e3; audit T60): the study's PyPI sizes came from a
wheel choice that took a pure wheel before a compiled cp312 one, which pip does the other way round. This re-reads every weighed PyPI
line at the same version with the fixed choice (itemator/weight.py now); npm lines are unchanged (the fix touches PyPI only). The first
run stays as it was in results/aidev_weight_v1.json; this writes results/aidev_weight_v1_corrected.json beside it.

usage: python3 eval/aidev_weight_correct.py"""
from __future__ import annotations

import copy
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
import aidev_weight as A  # noqa: E402
from itemator import registry as RG, weight as W  # noqa: E402


def main() -> int:
    first = json.loads((ROOT / "results" / "aidev_weight_v1.json").read_text())
    rows, changed = copy.deepcopy(first["rows"]), []
    day = datetime.date.today().isoformat()
    for r in rows:
        w = r.get("weight") or {}
        if r["ecosystem"] != "PyPI" or w.get("weight") != "ok":
            continue
        new = W.weigh(RG.Run(RG.fetch, day)._ask, "PyPI", RG._pep503(r["name"]), w["version"])
        if new.get("weight") != "ok":
            r["correction"] = {"not_reweighed": new.get("reason") or new.get("weight")}
            continue
        changed.append({"pr": r["pr"], "name": r["name"], "before": w["bytes"], "after": new["bytes"],
                        "packages_before": w["packages"], "packages_after": new["packages"]})
        r["weight"] = {**new, "of_version": w.get("of_version")}
    summary = A.summarize(rows)
    two_x = sum(1 for c in changed if c["before"] and (c["after"] / c["before"] > 2 or c["after"] / c["before"] < 0.5))
    out = {"what": __doc__.split("\n\n")[0], "checked": day, "first_run": "results/aidev_weight_v1.json",
           "pypi_lines_reweighed": len(changed), "pypi_lines_changed_more_than_2x": two_x,
           "pypi_bytes_before": sum(c["before"] for c in changed), "pypi_bytes_after": sum(c["after"] for c in changed),
           "summary": summary,
           "readme": {"lines_weighed": summary["weighed"], "median_packages": summary["all"]["median_packages"],
                      "median_mb": round(summary["all"]["median_bytes"] / 1e6, 2), "threshold_packages": 10, "threshold_mb": 10,
                      "ten_or_more_packages": summary["all"]["ten_or_more_packages"], "ten_mb_or_more": summary["all"]["ten_mb_or_more"],
                      "scanned_pull_requests": first["scanned_pull_requests"]},
           "changed": sorted(changed, key=lambda c: -abs(c["after"] - c["before"])), "rows": rows}
    (ROOT / "results" / "aidev_weight_v1_corrected.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("pypi_lines_reweighed", "pypi_lines_changed_more_than_2x", "pypi_bytes_before", "pypi_bytes_after")}),
          json.dumps(out["readme"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
