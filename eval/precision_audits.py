"""Collect the headline counts of the four model-made label audits into results/precision_audits.json.

Every count below is typed from the audit note named in `note`; none is computed from the rules.
The only computation here is the Wilson 95% interval. Labels are one model's reading of each diff
against the linked issue text; there is no second reader and no upstream outcome.
usage: python3 eval/precision_audits.py            # writes results/precision_audits.json
"""
import json, math, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
Z = 1.959964  # two-sided 95 percent, normal approximation constant


def wilson(k: int, n: int) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


# status: "development" = the rules were tuned on this sample; "held_out" = rules frozen before the sample was drawn.
SAMPLES = [
    dict(sample="A", rules="v1", status="development", seed=20261010, note="results/audits/sample-A-rules-v1.md",
         prs_scored=60, prs_flagged=16, extras=35, extras_real_strict=14, extras_real_lenient=17,
         prs_with_real_strict=9, prs_with_real_lenient=10),
    dict(sample="B", rules="v2", status="held_out", seed=20261011, note="results/audits/sample-B-rules-v2.md",
         prs_scored=60, prs_flagged=12, extras=168, extras_real_strict=10, extras_real_lenient=119,
         prs_with_real_strict=5, prs_with_real_lenient=8),
    dict(sample="C", rules="v3", status="held_out", seed=20261012, note="results/audits/sample-C-rules-v3.md",
         prs_scored=60, prs_flagged=5, extras=49, extras_real_strict=5, extras_real_lenient=5,
         prs_with_real_strict=3, prs_with_real_lenient=3),
    dict(sample="D", rules="v4", status="held_out", seed=20261013, note="results/audits/sample-D-rules-v4.md",
         prs_scored=60, prs_flagged=8, extras=12, extras_real_strict=4, extras_real_lenient=5,
         prs_with_real_strict=4, prs_with_real_lenient=5),
    dict(sample="E", rules="v5", status="held_out", seed=20261014, note="results/audits/sample-E-rules-v5.md",
         prs_scored=60, prs_flagged=3, extras=4, extras_real_strict=3, extras_real_lenient=4,
         prs_with_real_strict=2, prs_with_real_lenient=3),
]


def main() -> None:
    rows = []
    for s in SAMPLES:
        r = dict(s)
        r["pr_strict_interval_95"] = wilson(s["prs_with_real_strict"], s["prs_flagged"])
        r["pr_lenient_interval_95"] = wilson(s["prs_with_real_lenient"], s["prs_flagged"])
        r["share_of_prs_flagged"] = round(s["prs_flagged"] / s["prs_scored"], 3)
        rows.append(r)
    held = [s for s in SAMPLES if s["status"] == "held_out"]
    k = sum(s["prs_with_real_strict"] for s in held)
    kl = sum(s["prs_with_real_lenient"] for s in held)
    n = sum(s["prs_flagged"] for s in held)
    out = {
        "confidence_level": 0.95,
        "flag_count_range": [6, 30],   # the pre-registered range for "flagged PRs of 60" (kill test 1b in every replay file)
        "labeller": "one language model per sample; no second reader; no upstream outcomes (merged, reverted, objected to)",
        "samples": rows,
        "held_out_pooled": {
            "samples": [s["sample"] for s in held], "rules_differ_between_samples": True,
            "prs_flagged": n, "prs_with_real_strict": k, "prs_with_real_lenient": kl,
            "strict_interval_95": wilson(k, n), "lenient_interval_95": wilson(kl, n),
            "prs_scored": sum(s["prs_scored"] for s in held),
            "prs_flagged_share": round(n / sum(s["prs_scored"] for s in held), 3),
        },
        "notes": "Pooled across rule versions for a single plain sentence; the samples are different PRs and the rules changed, so it is not a controlled comparison.",
    }
    path = ROOT / "results" / "precision_audits.json"
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {path.relative_to(ROOT)}: held-out pooled {k} of {n} strict, {kl} of {n} lenient")


if __name__ == "__main__":
    main()
