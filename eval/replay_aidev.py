"""Kill test 1, offline replay: the extras rules on real agent PRs from AIDev v3.

Data: AIDev v3 by Hao Li, Haoxiang Zhang and Ahmed E. Hassan (CC BY 4.0,
arXiv 2507.15003). This script downloads four tables into data/ (gitignored);
the data is never committed or redistributed. Changed files come from the
GitHub REST API (GET only), cached under eval/cache/ (gitignored).

Run from the repository root (each run refuses to overwrite its output file):
    # v1 on sample A, again, from the cache (the committed file is never overwritten)
    .venv/bin/python -I eval/replay_aidev.py --rules 1 --seed 20261010 --offline
    # v2 on sample A: the development-set score
    .venv/bin/python -I eval/replay_aidev.py --rules 2 --seed 20261010 --offline
    # v2 on sample B: run once, after the rules and SEED_B are committed
    .venv/bin/python -I eval/replay_aidev.py --rules 2 --seed 20261011 --exclude-sample-a
    # v3 on sample C: run once, after rules v3 and SEED_C are committed
    .venv/bin/python -I eval/replay_aidev.py --rules 3 --seed 20261012 --exclude-sample-a --exclude-sample-b
    # v4 on sample D: run once, after rules v4 and SEED_D are committed
    .venv/bin/python -I eval/replay_aidev.py --rules 4 --seed 20261013 --exclude-sample-a --exclude-sample-b --exclude-sample-c
    # v5 on sample E: run once, after rules v5 and SEED_E are committed
    .venv/bin/python -I eval/replay_aidev.py --rules 5 --seed 20261014 --exclude-sample-a --exclude-sample-b --exclude-sample-c --exclude-sample-d
(v3 on samples A and B, and v4 on samples A, B and C, the development sets: eval/rescore_dev.py.)

Inputs are pinned in eval/inputs.lock.json: the dataset commit (downloads use
it, not the movable ref v3), the parquet sha256 values and the duckdb version.
A mismatch stops the run before any sampling.

Pool: agent PRs in AIDev v3 `pull_request` (repos with > 100 stars), linked to
an issue in `related_issue` (AIDev: a hyperlink in the PR body; not GitHub's
closing keywords), whose linked issue is an issue (not a PR) with a non-empty
body, in a repository whose GitHub-detected licence is in PERMISSIVE.
Kill test 1a passes when the pool has at least 150 PRs.

Sample: the pool sorted by PR id, shuffled with SEED; walk that order and keep
the first SAMPLE PRs whose changed files can be fetched (fetch failures are
listed, not replaced by choice). Kill test 1b passes when 6 to 30 of the
SAMPLE have at least one extra.

v1 wrote results/replay_predictions.json (sample A). Upstream outcomes (merged, reverted,
objected to) are deliberately not read here: they are looked up only after
the predictions are committed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import platform
import random
import subprocess
import sys
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from itemator import extras as extras_v5, extras_v1, extras_v2, extras_v3, extras_v4  # noqa: E402
from itemator.extras import analyse  # noqa: E402

RULES = {1: extras_v1, 2: extras_v2, 3: extras_v3, 4: extras_v4, 5: extras_v5}   # each version's own module: its KINDS and its file

SEED = 20261010          # sample A, fixed on 2026-10-10 before the first run; the v2 development set
SEED_B = 20261011        # sample B, fixed on 2026-10-11 before rules v2 meet it; with A, the v3 development set
SEED_C = 20261012        # sample C, fixed before rules v3 meet it; excludes A and B; with A and B, the v4 development set
SEED_D = 20261013        # sample D, fixed before rules v4 meet it; excludes A, B and C; with A to C, the v5 development set
SEED_E = 20261014        # sample E, fixed before rules v5 meet it; excludes A, B, C and D
SAMPLE = 60
MAX_FETCHES = 120        # GitHub API calls this run may make (pages count)
DATASET = "hao-li/AIDev@v3"
LOCK_FILE = REPO / "eval" / "inputs.lock.json"
LOCK = json.loads(LOCK_FILE.read_text())
BASE_URL = f"https://huggingface.co/datasets/hao-li/AIDev/resolve/{LOCK['dataset_revision']}/"
TABLES = ("related_issue", "issue", "pull_request", "repository")
PERMISSIVE = ("MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "Unlicense")
DATA = REPO / "data"
CACHE = REPO / "eval" / "cache"
SAMPLE_A = REPO / LOCK["sample_a_predictions"]
SAMPLE_B = REPO / LOCK["sample_b_predictions"]
SAMPLE_C = REPO / LOCK["sample_c_predictions"]
SAMPLE_D = REPO / LOCK["sample_d_predictions"]
DEFAULT_OUT = {(1, SEED, False, False, False, False): "replay_v1_sampleA_rerun.json",     # (rules, seed, exclude A, B, C, D)
               (2, SEED, False, False, False, False): "replay_v2_sampleA.json",
               (2, SEED_B, True, False, False, False): "replay_v2_sampleB.json",
               (3, SEED_C, True, True, False, False): "replay_v3_sampleC.json",
               (4, SEED_D, True, True, True, False): "replay_v4_sampleD.json",
               (5, SEED_E, True, True, True, True): "replay_v5_sampleE.json"}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_inputs() -> None:
    """Stop unless the parquet files and duckdb match eval/inputs.lock.json."""
    import duckdb
    bad = [f"duckdb {duckdb.__version__} != {LOCK['duckdb']}"] if duckdb.__version__ != LOCK["duckdb"] else []
    for name, want in LOCK["parquet"].items():
        got = sha256(DATA / name)
        if got != want["sha256"]:
            bad.append(f"{name} sha256 {got} != {want['sha256']}")
    if bad:
        sys.exit("inputs do not match eval/inputs.lock.json: " + "; ".join(bad))


def sample_a_urls() -> set[str]:
    """The 62 PRs walked for sample A (60 scored + 2 without files), from the committed file."""
    if sha256(SAMPLE_A) != LOCK["sample_a_predictions_sha256"]:
        sys.exit(f"{SAMPLE_A.name} does not match its pinned sha256")
    d = json.loads(SAMPLE_A.read_text())
    return {p["pr_url"] for p in d["prs"]} | {s["pr_url"] for s in d["summary"]["skipped_fetch_failed"]}


def sample_b_urls() -> set[str]:
    """The PRs walked for sample B (60 scored + the skipped), from the committed file."""
    if sha256(SAMPLE_B) != LOCK["sample_b_predictions_sha256"]:
        sys.exit(f"{SAMPLE_B.name} does not match its pinned sha256")
    d = json.loads(SAMPLE_B.read_text())
    return {p["pr_url"] for p in d["prs"]} | {s["pr_url"] for s in d["summary"]["skipped_fetch_failed"]}


def sample_c_urls() -> set[str]:
    """The PRs walked for sample C (60 scored + the skipped), from the committed file."""
    if sha256(SAMPLE_C) != LOCK["sample_c_predictions_sha256"]:
        sys.exit(f"{SAMPLE_C.name} does not match its pinned sha256")
    d = json.loads(SAMPLE_C.read_text())
    return {p["pr_url"] for p in d["prs"]} | {s["pr_url"] for s in d["summary"]["skipped_fetch_failed"]}


def sample_d_urls() -> set[str]:
    """The PRs walked for sample D (60 scored + the skipped), from the committed file."""
    if sha256(SAMPLE_D) != LOCK["sample_d_predictions_sha256"]:
        sys.exit(f"{SAMPLE_D.name} does not match its pinned sha256")
    d = json.loads(SAMPLE_D.read_text())
    return {p["pr_url"] for p in d["prs"]} | {s["pr_url"] for s in d["summary"]["skipped_fetch_failed"]}


def download() -> None:
    DATA.mkdir(exist_ok=True)
    for t in TABLES:
        dest = DATA / f"{t}.parquet"
        if not dest.exists():
            print(f"downloading {t}.parquet", file=sys.stderr)
            urllib.request.urlretrieve(BASE_URL + f"{t}.parquet", dest)   # pinned commit, then sha256-checked


def build_pool() -> tuple[list[dict], dict]:
    import duckdb
    con = duckdb.connect()
    con.execute("SET memory_limit='1GB'; SET threads=2;")
    d = {t: str(DATA / f"{t}.parquet") for t in TABLES}
    lic = ", ".join(f"'{x}'" for x in PERMISSIVE)
    one = lambda sql: con.execute(sql).fetchone()[0]
    funnel = {
        "pull_request_rows": one(f"SELECT count(*) FROM '{d['pull_request']}'"),
        "prs_linked_to_an_issue": one(f"SELECT count(DISTINCT pr_id) FROM '{d['related_issue']}'"),
        "linked_prs_in_permissive_repos": one(f"""
            SELECT count(DISTINCT p.id) FROM '{d['pull_request']}' p
            JOIN '{d['related_issue']}' ri ON ri.pr_id = p.id
            JOIN '{d['repository']}' r ON r.id = p.repo_id WHERE r.license IN ({lic})"""),
        "linked_prs_whose_repo_is_missing": one(f"""
            SELECT count(DISTINCT p.id) FROM '{d['pull_request']}' p
            JOIN '{d['related_issue']}' ri ON ri.pr_id = p.id
            ANTI JOIN '{d['repository']}' r ON r.id = p.repo_id"""),
        "linked_issues_that_are_prs": one(f"""
            SELECT count(*) FROM '{d['related_issue']}' ri
            JOIN '{d['issue']}' i ON i.id = CAST(ri.issue_id AS BIGINT)
            WHERE i.html_url NOT LIKE '%/issues/%'"""),
    }
    rows = con.execute(f"""
        SELECT p.id, p.html_url, p.agent, r.full_name, r.license,
               list(i.html_url ORDER BY i.id),
               string_agg(coalesce(i.title, '') || chr(10) || i.body, chr(10) || chr(10) ORDER BY i.id)
        FROM '{d['pull_request']}' p
        JOIN '{d['related_issue']}' ri ON ri.pr_id = p.id
        JOIN '{d['issue']}' i ON i.id = CAST(ri.issue_id AS BIGINT)
        JOIN '{d['repository']}' r ON r.id = p.repo_id
        WHERE r.license IN ({lic})
          AND i.body IS NOT NULL AND trim(i.body) <> ''
          AND i.html_url LIKE '%/issues/%'
        GROUP BY p.id, p.html_url, p.agent, r.full_name, r.license
        ORDER BY p.id""").fetchall()
    keys = ("pr_id", "pr_url", "agent", "repo", "license", "issue_urls", "issue_text")
    pool = [dict(zip(keys, r)) for r in rows]
    funnel["pool"] = len(pool)
    funnel["pool_by_agent"] = {}
    for p in pool:
        funnel["pool_by_agent"][p["agent"]] = funnel["pool_by_agent"].get(p["agent"], 0) + 1
    return pool, funnel


def _json_stream(text: str) -> list:
    """gh --paginate prints one JSON value per page; read them all."""
    dec, i, out = json.JSONDecoder(), 0, []
    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        value, i = dec.raw_decode(text, i)
        out.append(value)
    return out


class Fetcher:
    def __init__(self, offline: bool = False):
        self.calls = 0
        self.offline = offline

    def files(self, pr: dict) -> dict:
        CACHE.mkdir(parents=True, exist_ok=True)
        cached = CACHE / f"{pr['pr_id']}.json"
        if cached.exists():
            return json.loads(cached.read_text())
        if self.offline:
            raise RuntimeError(f"--offline and {cached.name} is not cached")
        if self.calls >= MAX_FETCHES:
            raise RuntimeError(f"MAX_FETCHES ({MAX_FETCHES}) reached")
        parts = pr["pr_url"].split("/")          # https://github.com/<owner>/<repo>/pull/<n>
        owner, repo, number = parts[3], parts[4], parts[6]
        cmd = ["gh", "api", "--method", "GET", "--paginate",
               f"repos/{owner}/{repo}/pulls/{number}/files?per_page=100",
               "--jq", "[.[] | {filename, status, patch, previous_filename, additions, deletions}]"]
        self.calls += 1
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            result = {"error": (r.stderr.strip().splitlines() or ["unknown"])[0][:200]}
        else:
            pages = _json_stream(r.stdout)
            self.calls += max(0, len(pages) - 1)
            result = {"files": [f for page in pages for f in page]}
        cached.write_text(json.dumps(result))
        return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rules", type=int, choices=tuple(RULES), required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--exclude-sample-a", action="store_true", help="skip the 62 PRs walked for sample A")
    ap.add_argument("--exclude-sample-b", action="store_true", help="skip the PRs walked for sample B")
    ap.add_argument("--exclude-sample-c", action="store_true", help="skip the PRs walked for sample C")
    ap.add_argument("--exclude-sample-d", action="store_true", help="skip the PRs walked for sample D")
    ap.add_argument("--offline", action="store_true", help="read the GitHub cache only; never fetch")
    ap.add_argument("--out", help="output path (default: from rules, seed and exclusion)")
    args = ap.parse_args()
    if args.seed == SEED_B and not args.exclude_sample_a:
        sys.exit("sample B must exclude sample A: add --exclude-sample-a")
    if args.seed == SEED_C and not (args.exclude_sample_a and args.exclude_sample_b):
        sys.exit("sample C must exclude samples A and B: add --exclude-sample-a --exclude-sample-b")
    if args.seed == SEED_D and not (args.exclude_sample_a and args.exclude_sample_b and args.exclude_sample_c):
        sys.exit("sample D must exclude samples A, B and C: add --exclude-sample-a --exclude-sample-b --exclude-sample-c")
    if args.seed == SEED_E and not (args.exclude_sample_a and args.exclude_sample_b and args.exclude_sample_c
                                    and args.exclude_sample_d):
        sys.exit("sample E must exclude samples A, B, C and D: add --exclude-sample-a --exclude-sample-b "
                 "--exclude-sample-c --exclude-sample-d")
    name = args.out or DEFAULT_OUT.get((args.rules, args.seed, args.exclude_sample_a, args.exclude_sample_b,
                                        args.exclude_sample_c, args.exclude_sample_d))
    if not name:
        sys.exit("give --out for this combination")
    out = pathlib.Path(name) if args.out else REPO / "results" / name
    if out.exists():
        sys.exit(f"{out} exists; this run happens once (move the file away to repeat it)")
    download()
    check_inputs()
    excluded = ((sample_a_urls() if args.exclude_sample_a else set())
                | (sample_b_urls() if args.exclude_sample_b else set())
                | (sample_c_urls() if args.exclude_sample_c else set())
                | (sample_d_urls() if args.exclude_sample_d else set()))
    pool, funnel = build_pool()
    print(f"pool (kill test 1a, passes at >= 150): {len(pool)} -> {'PASS' if len(pool) >= 150 else 'FAIL'}")
    order = sorted(pool, key=lambda p: p["pr_id"])
    random.Random(args.seed).shuffle(order)
    fetcher, sample, skipped, passed_over = Fetcher(args.offline), [], [], 0
    for pr in order:
        if len(sample) == SAMPLE:
            break
        if pr["pr_url"] in excluded:
            passed_over += 1
            continue
        got = fetcher.files(pr)
        if "error" in got or not got.get("files"):
            skipped.append({"pr_url": pr["pr_url"], "error": got.get("error", "no files")})
            continue
        sample.append((pr, got["files"]))
    records, KINDS = [], RULES[args.rules].KINDS
    for pr, files in sample:
        a = analyse(pr["issue_text"], files, repo=pr["repo"], version=args.rules)
        records.append({
            "pr_url": pr["pr_url"], "issue_urls": pr["issue_urls"], "agent": pr["agent"],
            "repo": pr["repo"], "license": pr["license"],
            "files_changed": len(files),
            "files_without_patch": sum(1 for f in files if not f.get("patch")),
            "files_sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
            "anchored": a.anchored, "unplaced": a.unplaced,
            "extras": [e.to_dict() for e in a.extras],
            "counts": {k: sum(1 for e in a.extras if e.kind == k) for k in KINDS},
            **({"named_paths": a.named_paths} if args.rules >= 3 else {}),
            **({"stray": a.stray} if args.rules >= 4 else {}),
        })
    flagged = sum(1 for r in records if r["extras"])
    strict = sum(1 for r in records if r["extras"] or r["unplaced"])
    per_kind = {k: {"extras": sum(r["counts"][k] for r in records),
                    "prs": sum(1 for r in records if r["counts"][k])} for k in KINDS}
    rules_file = pathlib.Path(RULES[args.rules].__file__)
    label = {(SEED, 1): "sample A", (SEED, 2): "sample A (development set for rules v2)",
             (SEED, 3): "sample A (development set for rules v3)",
             (SEED_B, 2): "sample B (held out: rules v2 frozen before this run)",
             (SEED_B, 3): "sample B (development set for rules v3)",
             (SEED_C, 3): "sample C (held out: rules v3 frozen before this run)",
             (SEED, 4): "sample A (development set for rules v4)", (SEED_B, 4): "sample B (development set for rules v4)",
             (SEED_C, 4): "sample C (development set for rules v4)",
             (SEED_D, 4): "sample D (held out: rules v4 frozen before this run)",
             **{(s, 5): f"sample {n} (development set for rules v5)" for s, n in ((SEED, "A"), (SEED_B, "B"),
                                                                                 (SEED_C, "C"), (SEED_D, "D"))},
             (SEED_E, 5): "sample E (held out: rules v5 frozen before this run)"}.get((args.seed, args.rules), "other seed")
    summary = {
        "dataset": DATASET, "seed": args.seed, "sample": label, "sample_size": len(records),
        "rules_version": args.rules, "rules_file": rules_file.name, "rules_sha256": sha256(rules_file),
        "inputs_lock_sha256": sha256(LOCK_FILE), "dataset_revision": LOCK["dataset_revision"],
        "python": platform.python_version(),
        **({"excluded_sample_a_prs_passed_over": passed_over} if not args.exclude_sample_b else
           {"excluded_prs_passed_over": passed_over,
            "excluded_samples": [s for s, on in (("A", args.exclude_sample_a), ("B", True), ("C", args.exclude_sample_c),
                                           ("D", args.exclude_sample_d)) if on]}),
        **({"prs_with_unplaced_files": sum(1 for r in records if r["unplaced"])} if args.rules >= 3 else {}),
        "funnel": funnel,
        "kill_test_1a": {"pool": len(pool), "threshold": ">= 150", "pass": len(pool) >= 150},
        "kill_test_1b": {"flagged": flagged, "of": len(records), "threshold": "6..30",
                         "pass": 6 <= flagged <= 30},
        "per_kind": per_kind,
        "unanchored": sum(1 for r in records if not r["anchored"]),
        "flagged_if_rule5_never_abstained": strict,
        "prs_with_a_file_missing_its_patch": sum(1 for r in records if r["files_without_patch"]),
        "skipped_fetch_failed": skipped, "github_api_calls_this_run": fetcher.calls,
    }
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "prs": records}, indent=1, sort_keys=True) + "\n")
    print(f"{label}, rules v{args.rules}: {len(records)} of {len(pool)}, seed {args.seed}; "
          f"excluded PRs passed over: {passed_over}; skipped (fetch failed): {len(skipped)}; "
          f"API calls this run: {fetcher.calls}")
    print(f"flagged (kill test 1b, passes at 6..30): {flagged} of {len(records)} -> "
          f"{'PASS' if 6 <= flagged <= 30 else 'FAIL'}")
    for k in KINDS:
        print(f"  {k}: {per_kind[k]['prs']} PRs, {per_kind[k]['extras']} extras")
    print(f"unanchored (rule 5 abstained): {summary['unanchored']}; "
          f"flagged if rule 5 never abstained: {strict}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
