"""Rules v3 on samples A and B, v4 on samples A, B and C, v5 on A to D: the development sets they were fixed on.
Development scores, not test scores.

Run from the repository root, after the rules are final (the output is never overwritten):
    .venv/bin/python -I eval/rescore_dev.py              # v3 on A and B: results/replay_v3_devAB.json
    .venv/bin/python -I eval/rescore_dev.py --rules 4    # v4 on A, B and C: results/replay_v4_devABC.json
    .venv/bin/python -I eval/rescore_dev.py --rules 5    # v5 on A, B, C and D: results/replay_v5_devABCD.json
No network: issue text comes from the pinned dataset (data/, checked against eval/inputs.lock.json),
file lists from eval/cache. For every PR it first checks that the cached files hash to the committed v2
record and that rules v2, run again, give the committed v2 extras and unplaced files; any mismatch is
listed in the summary. Writes results/replay_v3_devAB.json.
With --rules 4 the baseline is rules v3 as committed (replay_v3_devAB.json for A and B, replay_v3_sampleC.json for
C): the cached files must hash the same and frozen v3, run again, must give the same extras, unplaced files and
anchoring. Precision needs a human or model audit; these files hold counts only.
With --rules 5 the baseline is rules v4 as committed (replay_v4_devABC.json for A to C, replay_v4_sampleD.json for D):
the cached files must hash the same and frozen v4, run again, must give the same extras, unplaced files, named files,
stray files and anchoring.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "eval"), str(REPO)]
import replay_aidev as R  # noqa: E402
from itemator import ci  # noqa: E402
from itemator import extras as V5  # noqa: E402
from itemator import extras_v4 as V4  # noqa: E402
from itemator import extras_v3 as V3  # noqa: E402

OUT = REPO / "results" / "replay_v3_devAB.json"
OUT_V4 = REPO / "results" / "replay_v4_devABC.json"
OUT_V5 = REPO / "results" / "replay_v5_devABCD.json"
V4_DEV, V4_D = REPO / "results/replay_v4_devABC.json", REPO / "results/replay_v4_sampleD.json"
V3_DEV, V3_C = REPO / "results/replay_v3_devAB.json", REPO / "results/replay_v3_sampleC.json"
SAMPLES = {"A": (R.SEED, REPO / "results/replay_v2_sampleA.json"),
           "B": (R.SEED_B, REPO / "results/replay_v2_sampleB.json")}
V2_KINDS = ("new_dependency", "ci_or_config", "tests_removed", "public_api_removed", "file_outside_ask")


def tally(records, key):
    kinds = V3.KINDS if key == "v3" else V2_KINDS
    per_kind = {k: {"extras": sum(r[key]["counts"].get(k, 0) for r in records),
                    "prs": sum(1 for r in records if r[key]["counts"].get(k, 0))} for k in kinds}
    return {"flagged_prs": sum(1 for r in records if r[key]["extras"]),
            "extras": sum(len(r[key]["extras"]) for r in records),
            "extras_with_mass_events_expanded": sum(len(e.get("detail") or ()) or 1
                                                    for r in records for e in r[key]["extras"]),
            "unanchored": sum(1 for r in records if not r["anchored"]),
            "prs_with_unplaced_files": sum(1 for r in records if r[key]["unplaced"]),
            "unplaced_files": sum(len(r[key]["unplaced"]) for r in records),
            "per_kind": per_kind}


def main() -> int:
    if OUT.exists():
        sys.exit(f"{OUT} exists; this run happens once (move the file away to repeat it)")
    R.check_inputs()
    pool, _ = R.build_pool()
    by_url = {p["pr_url"]: p for p in pool}
    records, mismatches = [], []
    for sample, (seed, v2_file) in SAMPLES.items():
        for r2 in json.loads(v2_file.read_text())["prs"]:
            pr = by_url[r2["pr_url"]]
            files = json.loads((R.CACHE / f"{pr['pr_id']}.json").read_text())["files"]
            digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
            again = V3.analyse(pr["issue_text"], files, repo=pr["repo"], version=2)
            if (digest != r2["files_sha256"] or [e.to_dict() for e in again.extras] != r2["extras"]
                    or again.unplaced != r2["unplaced"] or again.anchored != r2["anchored"]):
                mismatches.append(r2["pr_url"])
            a = V3.analyse(pr["issue_text"], files, repo=pr["repo"])
            records.append({
                "sample": sample, "seed": seed, "pr_url": r2["pr_url"], "repo": r2["repo"], "agent": r2["agent"],
                "files_changed": len(files), "files_sha256": digest, "anchored": a.anchored,
                "v2": {"extras": [[e["kind"], e["name"]] for e in r2["extras"]], "counts": r2["counts"],
                       "unplaced": r2["unplaced"]},
                "v3": {"extras": [e.to_dict() for e in a.extras], "named_paths": a.named_paths, "unplaced": a.unplaced,
                       "counts": {k: sum(1 for e in a.extras if e.kind == k) for k in V3.KINDS}},
            })
    for r in records:      # normalise for tally(): v2 entries carry no detail
        r["v2"]["extras"] = [{"kind": k, "name": n} for k, n in r["v2"]["extras"]]
    changed = [{"pr_url": r["pr_url"], "sample": r["sample"],
                "v2": sorted({e["kind"] for e in r["v2"]["extras"]}), "v2_extras": len(r["v2"]["extras"]),
                "v3": sorted({e["kind"] for e in r["v3"]["extras"]}), "v3_extras": len(r["v3"]["extras"]),
                "v3_names": [e["name"] for e in r["v3"]["extras"]], "v3_unplaced": len(r["v3"]["unplaced"])}
               for r in records if [e["name"] for e in r["v2"]["extras"]] != [e["name"] for e in r["v3"]["extras"]]
               or [e["kind"] for e in r["v2"]["extras"]] != [e["kind"] for e in r["v3"]["extras"]]]
    summary = {
        "score": "development score: rules v3 were fixed on these 120 PRs (samples A and B); not a test score",
        "dataset_revision": R.LOCK["dataset_revision"], "inputs_lock_sha256": R.sha256(R.LOCK_FILE),
        "rules_v3_sha256": R.sha256(REPO / "itemator/extras_v3.py"),
        "rules_v2_sha256": R.sha256(REPO / "itemator/extras_v2.py"),
        "v2_results_sha256": {s: R.sha256(f) for s, (_, f) in SAMPLES.items()},
        "v2_reproduced": not mismatches, "v2_mismatches": mismatches,
        "by_sample": {s: {"prs": sum(1 for r in records if r["sample"] == s),
                          "v2": tally([r for r in records if r["sample"] == s], "v2"),
                          "v3": tally([r for r in records if r["sample"] == s], "v3")} for s in SAMPLES},
        "both": {"prs": len(records), "v2": tally(records, "v2"), "v3": tally(records, "v3")},
        "prs_whose_extras_changed": changed,
    }
    OUT.write_text(json.dumps({"summary": summary, "prs": records}, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: summary[k] for k in ("v2_reproduced", "v2_mismatches", "by_sample", "both")}, indent=1))
    print(f"wrote {OUT}")
    return 0


def tally4(records, key):
    t = {"flagged_prs": sum(1 for r in records if r[key]["extras"]),
         "extras": sum(len(r[key]["extras"]) for r in records),
         "extras_with_mass_events_expanded": sum(len(e.get("detail") or ()) or 1 for r in records for e in r[key]["extras"]),
         "unanchored": sum(1 for r in records if not r[key]["anchored"]),
         "prs_with_unplaced_files": sum(1 for r in records if r[key]["unplaced"]),
         "unplaced_files": sum(len(r[key]["unplaced"]) for r in records),
         "per_kind": {k: {"extras": sum(r[key]["counts"].get(k, 0) for r in records),
                          "prs": sum(1 for r in records if r[key]["counts"].get(k, 0))}
                      for k in (V3.KINDS if key == "v3" else V4.KINDS)}}
    if key == "v4":
        t["card_lines_after_grouping"] = sum(r["v4"]["card_lines"] for r in records)
        t["prs_with_stray_files"] = sum(1 for r in records if r["v4"]["stray"])
    return t


def main_v4() -> int:
    if OUT_V4.exists():
        sys.exit(f"{OUT_V4} exists; this run happens once (move the file away to repeat it)")
    R.check_inputs()
    pool, _ = R.build_pool()
    by_url = {p["pr_url"]: p for p in pool}
    ref = [(r["sample"], r["seed"], r["pr_url"], r["v3"]["extras"], r["v3"]["unplaced"], r["anchored"], r["files_sha256"])
           for r in json.loads(V3_DEV.read_text())["prs"]]
    ref += [("C", R.SEED_C, r["pr_url"], r["extras"], r["unplaced"], r["anchored"], r["files_sha256"])
            for r in json.loads(V3_C.read_text())["prs"]]
    records, mismatches = [], []
    for sample, seed, url, v3_extras, v3_unplaced, v3_anchored, v3_sha in ref:
        pr = by_url[url]
        files = json.loads((R.CACHE / f"{pr['pr_id']}.json").read_text())["files"]
        digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        again = V3.analyse(pr["issue_text"], files, repo=pr["repo"])
        if (digest != v3_sha or json.loads(json.dumps([e.to_dict() for e in again.extras])) != v3_extras
                or again.unplaced != v3_unplaced or again.anchored != v3_anchored):
            mismatches.append(url)
        a = V4.analyse(pr["issue_text"], files, repo=pr["repo"])
        records.append({
            "sample": sample, "seed": seed, "pr_url": url, "repo": pr["repo"], "agent": pr["agent"],
            "files_changed": len(files), "files_sha256": digest,
            "v3": {"extras": v3_extras, "unplaced": v3_unplaced, "anchored": v3_anchored,
                   "counts": {k: sum(1 for e in v3_extras if e["kind"] == k) for k in V3.KINDS}},
            "v4": {"extras": [e.to_dict() for e in a.extras], "named_paths": a.named_paths, "unplaced": a.unplaced,
                   "anchored": a.anchored, "stray": a.stray, "card_lines": len(ci.group_extras(a.extras)),
                   "counts": {k: sum(1 for e in a.extras if e.kind == k) for k in V4.KINDS}},
        })
    changed = [{"pr_url": r["pr_url"], "sample": r["sample"],
                "v3": [[e["kind"], e["name"]] for e in r["v3"]["extras"]],
                "v4": [[e["kind"], e["name"]] for e in r["v4"]["extras"]],
                "v4_card_lines": r["v4"]["card_lines"], "v4_stray": r["v4"]["stray"]}
               for r in records if [[e["kind"], e["name"]] for e in r["v3"]["extras"]]
               != [[e["kind"], e["name"]] for e in r["v4"]["extras"]]]
    samples = ("A", "B", "C")
    summary = {
        "score": "development score: rules v4 were fixed on these 180 PRs (samples A, B and C); not a test score. "
                 "These are counts, not precision: precision needs a human or model audit of the extras",
        "dataset_revision": R.LOCK["dataset_revision"], "inputs_lock_sha256": R.sha256(R.LOCK_FILE),
        "rules_v4_sha256": R.sha256(REPO / "itemator/extras_v4.py"), "rules_v3_sha256": R.sha256(REPO / "itemator/extras_v3.py"),
        "ci_sha256": R.sha256(REPO / "itemator/ci.py"), "card_group_threshold": ci.GROUP,
        "v3_results_sha256": {"A+B": R.sha256(V3_DEV), "C": R.sha256(V3_C)},
        "v3_reproduced": not mismatches, "v3_mismatches": mismatches,
        "by_sample": {s: {"prs": sum(1 for r in records if r["sample"] == s),
                          "v3": tally4([r for r in records if r["sample"] == s], "v3"),
                          "v4": tally4([r for r in records if r["sample"] == s], "v4")} for s in samples},
        "all": {"prs": len(records), "v3": tally4(records, "v3"), "v4": tally4(records, "v4")},
        "prs_whose_extras_changed": changed,
    }
    OUT_V4.write_text(json.dumps({"summary": summary, "prs": records}, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: summary[k] for k in ("v3_reproduced", "v3_mismatches", "by_sample", "all")}, indent=1))
    print(f"wrote {OUT_V4}")
    return 0


def tally5(records, key):
    kinds = V4.KINDS if key == "v4" else V5.KINDS
    return {"flagged_prs": sum(1 for r in records if r[key]["extras"]),
            "extras": sum(len(r[key]["extras"]) for r in records),
            "extras_with_mass_events_expanded": sum(len(e.get("detail") or ()) or 1 for r in records for e in r[key]["extras"]),
            "card_lines_after_grouping": sum(r[key]["card_lines"] for r in records),
            "unanchored": sum(1 for r in records if not r[key]["anchored"]),
            "prs_with_unplaced_files": sum(1 for r in records if r[key]["unplaced"]),
            "unplaced_files": sum(len(r[key]["unplaced"]) for r in records),
            "prs_with_stray_entries": sum(1 for r in records if r[key]["stray"]),
            "per_kind": {k: {"extras": sum(r[key]["counts"].get(k, 0) for r in records),
                             "prs": sum(1 for r in records if r[key]["counts"].get(k, 0))} for k in kinds}}


def _record(a, kinds):
    return {"extras": json.loads(json.dumps([e.to_dict() for e in a.extras])), "named_paths": a.named_paths,
            "unplaced": a.unplaced, "anchored": a.anchored, "stray": a.stray, "card_lines": len(ci.group_extras(a.extras)),
            "counts": {k: sum(1 for e in a.extras if e.kind == k) for k in kinds}}


def main_v5() -> int:
    if OUT_V5.exists():
        sys.exit(f"{OUT_V5} exists; this run happens once (move the file away to repeat it)")
    R.check_inputs()
    pool, _ = R.build_pool()
    by_url = {p["pr_url"]: p for p in pool}
    ref = [(r["sample"], r["seed"], r["pr_url"], r["v4"], r["files_sha256"]) for r in json.loads(V4_DEV.read_text())["prs"]]
    ref += [("D", R.SEED_D, r["pr_url"], r, r["files_sha256"]) for r in json.loads(V4_D.read_text())["prs"]]
    records, mismatches = [], []
    for sample, seed, url, v4, v4_sha in ref:
        pr = by_url[url]
        files = json.loads((R.CACHE / f"{pr['pr_id']}.json").read_text())["files"]
        digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        again = _record(V4.analyse(pr["issue_text"], files, repo=pr["repo"]), V4.KINDS)
        if digest != v4_sha or any(again[k] != v4[k] for k in ("extras", "unplaced", "anchored", "named_paths", "stray")):
            mismatches.append(url)
        records.append({"sample": sample, "seed": seed, "pr_url": url, "repo": pr["repo"], "agent": pr["agent"],
                        "files_changed": len(files), "files_sha256": digest, "v4": again,
                        "v5": _record(V5.analyse(pr["issue_text"], files, repo=pr["repo"]), V5.KINDS)})
    pairs = lambda r, key: [[e["kind"], e["name"]] for e in r[key]["extras"]]
    changed = [{"pr_url": r["pr_url"], "sample": r["sample"], "v4": pairs(r, "v4"), "v5": pairs(r, "v5"),
                "v5_card_lines": r["v5"]["card_lines"], "v5_stray": r["v5"]["stray"]}
               for r in records if pairs(r, "v4") != pairs(r, "v5")]
    anchoring = [{"pr_url": r["pr_url"], "sample": r["sample"], "v4": r["v4"]["anchored"], "v5": r["v5"]["anchored"],
                  "v5_named_paths": r["v5"]["named_paths"]} for r in records if r["v4"]["anchored"] != r["v5"]["anchored"]]
    samples = ("A", "B", "C", "D")
    summary = {
        "score": "development score: rules v5 were fixed on these 240 PRs (samples A, B, C and D); not a test score. "
                 "These are counts, not precision: precision needs a human or model audit of the extras",
        "dataset_revision": R.LOCK["dataset_revision"], "inputs_lock_sha256": R.sha256(R.LOCK_FILE),
        "rules_v5_sha256": R.sha256(REPO / "itemator/extras.py"), "rules_v4_sha256": R.sha256(REPO / "itemator/extras_v4.py"),
        "ci_sha256": R.sha256(REPO / "itemator/ci.py"), "card_group_threshold": ci.GROUP,
        "whitespace_group_threshold": V5.WHITESPACE_GROUP,
        "v4_results_sha256": {"A+B+C": R.sha256(V4_DEV), "D": R.sha256(V4_D)},
        "v4_reproduced": not mismatches, "v4_mismatches": mismatches,
        "by_sample": {s: {"prs": sum(1 for r in records if r["sample"] == s),
                          "v4": tally5([r for r in records if r["sample"] == s], "v4"),
                          "v5": tally5([r for r in records if r["sample"] == s], "v5")} for s in samples},
        "all": {"prs": len(records), "v4": tally5(records, "v4"), "v5": tally5(records, "v5")},
        "prs_whose_extras_changed": changed, "prs_whose_anchoring_changed": anchoring,
    }
    OUT_V5.write_text(json.dumps({"summary": summary, "prs": records}, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: summary[k] for k in ("v4_reproduced", "v4_mismatches", "all")}, indent=1))
    print(f"wrote {OUT_V5}")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] not in ([], ["--rules", "3"], ["--rules", "4"], ["--rules", "5"]):
        sys.exit("usage: rescore_dev.py [--rules 3|4|5]")
    sys.exit({"4": main_v4, "5": main_v5}.get(sys.argv[2] if sys.argv[1:] else "", main)())
