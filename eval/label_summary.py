"""Summary of the two labellers' readings of the public replay's extras, by the rubric written before any label existed
(eval/public_replay_label_rubric.json). The labels themselves hold other projects' text, so they stay outside the
repository; this writes counts (an extra the card listed twice, same path and kind, counts once), Cohen's kappa, the disputed extras and, for GitLab's own projects, references and paths.

usage: python3 eval/label_summary.py --labels <dir with L1_labels.json and L2_labels.json> [--raw results/public_replay_a1_raw.json]"""
from __future__ import annotations

import argparse, collections, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import replay_gitlab as G

LABELS = ("real", "borderline", "not_an_extra")
OUT = G.ROOT / "results" / "public_replay_labels.json"


def ref_of(packet: str) -> tuple[str, str]:
    """'G_flagged__gitlab-org_gitlab_242496.json' -> ('G_flagged', 'gitlab-org/gitlab!242496'); a field project's hash
    has no underscore, so 'F_flagged__1566bdff_1.json' -> ('F_flagged', '1566bdff!1')."""
    group, rest = packet.split("__", 1)
    project, iid = rest.removesuffix(".json").rsplit("_", 1)
    return group, f"{project.replace('_', '/')}!{iid}"


def kappa(pairs: list) -> float | None:
    """Cohen's kappa for two labellers over the same items."""
    n = len(pairs)
    if not n:
        return None
    seen = sum(a == b for a, b in pairs) / n
    one, two = collections.Counter(a for a, _ in pairs), collections.Counter(b for _, b in pairs)
    chance = sum(one[x] * two[x] for x in set(one) | set(two)) / n / n
    return None if chance == 1 else round((seen - chance) / (1 - chance), 3)


def per_merge_request(rows: list) -> dict:
    """rows: (packet, l1, l2) per extra. Strict: both call the same extra real. Lenient: either calls any extra real or
    borderline."""
    out = {}
    for packet, a, b in rows:
        s = out.setdefault(packet, {"strict": False, "lenient": False})
        s["strict"] |= a == b == "real"
        s["lenient"] |= a in ("real", "borderline") or b in ("real", "borderline")
    return out


def summarize(l1: dict, l2: dict, raw: list, description_of=None) -> dict:
    key = lambda e: (e["packet"], e["path"], e["kind"])
    one, two = {key(e): e for e in l1["extras"]}, {key(e): e for e in l2["extras"]}
    both = sorted(set(one) & set(two))
    rows = [(k[0], one[k]["label"], two[k]["label"]) for k in both]
    mrs = per_merge_request(rows)
    groups = {}
    for packet, s in sorted(mrs.items()):
        g = groups.setdefault(ref_of(packet)[0], {"merge_requests": 0, "strict": 0, "lenient": 0})
        g["merge_requests"] += 1
        g["strict"] += s["strict"]
        g["lenient"] += s["lenient"]
    for g in groups.values():
        g["strict_wilson95"], g["lenient_wilson95"] = G.wilson(g["strict"], g["merge_requests"]), G.wilson(g["lenient"], g["merge_requests"])
    kinds = collections.defaultdict(collections.Counter)
    for k in both:
        for lab in (one[k]["label"], two[k]["label"]):
            kinds[k[2]][lab] += 1

    def shown(k):                       # field projects: counts only
        group, ref = ref_of(k[0])
        e = {"group": group, "kind": k[2], "L1": one[k]["label"], "L2": two[k]["label"]}
        return e if group.startswith("F") else {"ref": ref, "path": k[1], **e}
    disputed = [shown(k) for k in both if one[k]["label"] != two[k]["label"]]
    issue_of = {r["ref"]: r for r in raw if r["pop"] == "G" and r["version"] == "agent"}

    def named(ref):                     # found after labelling: does the description name the issue the replay read?
        r = issue_of.get(ref)
        if not r or not r.get("issue_refs") or description_of is None:
            return None
        return G.CI.mentions_issue(description_of(ref), int(r["issue_refs"][0].lstrip("#")), "gitlab-org/gitlab")
    m2 = {e["packet"]: e["answer"] for e in l2["misses"]}
    misses = [{"ref": ref_of(e["packet"])[1], "L1": e["answer"], "L2": m2.get(e["packet"]),
               "issue_named_in_description": named(ref_of(e["packet"])[1])} for e in l1["misses"]]
    both_yes = [m for m in misses if m["L1"] == m["L2"] == "yes"]
    return {
        "what": "The public replay's listed extras, read by two labellers by the rubric written before any label existed.",
        "rubric": "eval/public_replay_label_rubric.json",
        "labellers": {"L1": l1.get("model"), "L2": l2.get("model")},
        "agreement": {"entries": {"L1": len(l1["extras"]), "L2": len(l2["extras"])}, "extras": len(both), "only_one_labeller": len(set(one) ^ set(two)), "same_label": sum(a == b for _, a, b in rows),
                      "kappa": kappa([(a, b) for _, a, b in rows]), "disputed": disputed},
        "per_merge_request": groups,
        "G_flagged_issue_named_in_description": {ref_of(p)[1]: named(ref_of(p)[1]) for p in sorted(mrs) if p.startswith("G_flagged")},
        "labels_by_kind": {k: dict(v) for k, v in sorted(kinds.items())},
        "extras": [shown(k) for k in both if not ref_of(k[0])[0].startswith("F")],
        "misses": {"sampled": len(misses), "both_yes": len(both_yes), "either_yes": sum("yes" in (m["L1"], m["L2"]) for m in misses),
                   "both_yes_with_the_issue_not_named_in_the_description": sum(m["issue_named_in_description"] is False for m in both_yes),
                   "rows": misses},
        "found_after_labelling": "Not in the rubric. For the replay's G rows the issue came from the flow's note or the number in its branch name; "
                                 "issue_named_in_description says whether the merge request's description names that issue of gitlab-org/gitlab "
                                 "(as #N or its URL). Where it does not, the labellers may have read the merge request against an unrelated issue, "
                                 "so a 'yes' there is a linking error of the replay more than a missed extra. The CI job reads a branch's issue only "
                                 "when the description names it too (itemator.ci.mentions_issue).",
        "limits": "Model readings, not maintainers; one diff each; the rules were not changed after reading these labels.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--labels", required=True)
    ap.add_argument("--raw", default=str(G.ROOT / "results" / "public_replay_a1_raw.json"))
    a = ap.parse_args(argv)
    d = pathlib.Path(a.labels)
    l1, l2 = (json.loads((d / f"L{i}_labels.json").read_text()) for i in (1, 2))
    raw = json.loads(pathlib.Path(a.raw).read_text())
    describe = lambda ref: (G.get(f"projects/{G.GITLAB}/merge_requests/{ref.split('!')[1]}") or {}).get("description") or ""
    s = summarize(l1, l2, raw, describe)
    OUT.write_text(json.dumps(s, indent=1) + "\n")
    print(json.dumps({k: s[k] for k in ("per_merge_request",)}, indent=1), {k: v for k, v in s["agreement"].items() if k != "disputed"},
          {k: v for k, v in s["misses"].items() if k != "rows"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
