"""T35 Part 1: does the agent's own PR title or body name each extra the rules found? Counts only, no network.

    .venv/bin/python -I eval/silent_extras.py          # writes results/silent_extras.json

Inputs: the flagged PRs in results/replay_v4_devABC.json (samples A to C, rules v4), results/replay_v4_sampleD.json
(D, rules v4) and results/replay_v5_sampleE.json (E, rules v5), one counting unit per extra record as the replay
wrote it (before the card groups six or more of a kind); each PR's title and body from the pinned
data/pull_request.parquet (sha256 and duckdb version checked against eval/inputs.lock.json).

The test is itemator/said.py's, the one the CI job uses (T38 rule): a name counts when nothing that continues it
touches it (no letter, digit or _, and no - . / @ + ~ followed or preceded by one), in the visible title or body (closed
HTML comments, link destinations, reference definitions and HTML attributes dropped); for a path extra its base name
(no / before it) or full path also count; for an extra with a detail list, its file's or directory's base name and each
item. "named" = a strong match (in code, a full path, or the exact case of a name that is not an ordinary word);
"weak" = only an ordinary word (lowercase letters, 8 or fewer, or a generic directory) outside code: the job shows no
sentence then. "listed" = a list item or the first paragraph under "Beyond the issue". A paraphrase never counts.
These are counts, not a rate.
"""
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from itemator import said as S  # noqa: E402

LOCK = json.loads((ROOT / "eval/inputs.lock.json").read_text())
PARQUET = ROOT / "data/pull_request.parquet"
SOURCES = [("results/replay_v4_devABC.json", "v4"), ("results/replay_v4_sampleD.json", None),
           ("results/replay_v5_sampleE.json", None)]
AUDIT_D = ROOT / "results/audits/sample-D-rules-v4.md"
DEADLINE = 30.0      # an offline count: no extra may go unchecked for time (the job's own deadline is 0.5 s)


def check_inputs():
    import duckdb
    want = LOCK["parquet"]["pull_request.parquet"]["sha256"]
    got = hashlib.sha256(PARQUET.read_bytes()).hexdigest()
    if got != want or duckdb.__version__ != LOCK["duckdb"]:
        sys.exit(f"inputs differ from eval/inputs.lock.json: parquet {got}, duckdb {duckdb.__version__}")
    return got, duckdb.__version__


def flagged():
    """[(sample, record, extras)] for every PR with at least one extra."""
    out = []
    for path, key in SOURCES:
        for rec in json.loads((ROOT / path).read_text())["prs"]:
            extras = (rec[key] if key else rec)["extras"]
            if extras:
                sample = rec.get("sample") or ("D" if "sampleD" in path else "E")
                out.append((sample, rec, extras))
    return out


def texts(urls):
    import duckdb
    rows = duckdb.connect().execute("select html_url, title, body from read_parquet(?) where html_url in "
                                    "(select unnest(?))", [str(PARQUET), list(urls)]).fetchall()
    found = {}
    for url, title, body in rows:
        if url in found:
            sys.exit(f"{url} appears twice in the parquet")
        found[url] = (title or "", body or "")
    return found


def audit_d_real():
    """(PR suffix, kind) of each extra the sample D audit's per-extra table labels plainly `real`."""
    rows = re.findall(r"^\| ([\w.-]+)#(\d+) \| (\w+) \| [^|]+ \| real \|", AUDIT_D.read_text(), re.M)
    return [(f"/{repo}/pull/{n}", kind) for repo, n, kind in rows]


def outcome(title, body, extra):
    names = S.names(extra["name"], extra["path"], extra["detail"])
    if body.strip():
        got = S.said_detail(title, body, [names], deadline=DEADLINE)[0]
    else:                                       # no body: the title alone is read, as the description
        got = S.said_detail("", title, [names], deadline=DEADLINE)[0]
        got = "named" if got == "listed" else got
    return got or "not_read"


def main():
    sha, ddb = check_inputs()
    prs = flagged()
    text = texts([r["pr_url"] for _, r, _ in prs])
    missing = [r["pr_url"] for _, r, _ in prs if r["pr_url"] not in text]
    if missing:
        sys.exit(f"{len(missing)} PRs not in the parquet: {missing[:3]}")
    rows, per = [], {}
    for sample, rec, extras in prs:
        title, body = text[rec["pr_url"]]
        for e in extras:
            got = outcome(title, body, e)
            rows.append({"sample": sample, "pr_url": rec["pr_url"], "kind": e["kind"], "name": e["name"],
                         "detail_count": len(e["detail"]), "body_empty": not body.strip(), "said": got})
    for sample in sorted({r["sample"] for r in rows}) + ["total"]:
        sel = [r for r in rows if sample in ("total", r["sample"])]
        per[sample] = {"flagged_prs": len({r["pr_url"] for r in sel}), "extras": len(sel),
                       "named": sum(r["said"] in ("listed", "named") for r in sel),
                       "listed_under_beyond_the_issue": sum(r["said"] == "listed" for r in sel),
                       "named_strong": sum(r["said"] == "named" for r in sel),
                       "weak_only_no_sentence": sum(r["said"] == "weak" for r in sel),
                       "not_named": sum(r["said"] == "silent" for r in sel),
                       "not_read": sum(r["said"] == "not_read" for r in sel),
                       "prs_with_empty_body": len({r["pr_url"] for r in sel if r["body_empty"]})}
    real = []
    for suffix, kind in audit_d_real():
        hit = [r for r in rows if r["sample"] == "D" and r["pr_url"].endswith(suffix) and r["kind"] == kind]
        if len(hit) != 1:
            sys.exit(f"audit row {suffix} {kind} matches {len(hit)} extras")
        real.append({"pr_url": hit[0]["pr_url"], "kind": kind, "name": hit[0]["name"], "said": hit[0]["said"]})
    out = {"summary": {
        "what": "Whether each extra the rules found is named in the agent's own PR title or body (T35 Part 1).",
        "rule": ("itemator/said.py after T38: a name counts when nothing that continues it touches it (no letter, digit "
                 "or _, and no - . / @ + ~ followed or preceded by one); for a path extra also its base name (no / "
                 "before it) or full path; for an extra with a detail list also its file's or directory's base name "
                 "and any listed item; closed HTML comments, link destinations, reference definitions and HTML "
                 "attributes dropped. named = strong match (in code, a full path, or exact case of a name that is not "
                 "an ordinary word); weak = only an ordinary word (lowercase letters, 8 or fewer, or a generic "
                 "directory) outside code, which gets no sentence. Names under 3 characters or without a letter or "
                 "digit never match. Paraphrases are not counted. A PR with no body is judged on its title alone."),
        "unit": "one extra record as the replay files hold it (rules v4 for A to D, v5 for E), before card grouping",
        "not_claimed": "No precision, no rate of agents hiding changes: small samples, string matching only.",
        "inputs": {"pull_request.parquet_sha256": sha, "duckdb": ddb,
                   "replays": [p for p, _ in SOURCES], "audit": str(AUDIT_D.relative_to(ROOT))},
        "per_sample": per,
        "sample_D_audit_clearly_real": real},
        "extras": rows}
    (ROOT / "results/silent_extras.json").write_text(json.dumps(out, indent=1, ensure_ascii=True) + "\n")
    for k, v in per.items():
        print(k, v)
    print("D clearly real:", [(r["name"][:40], r["said"]) for r in real])


if __name__ == "__main__":
    main()
