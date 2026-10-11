"""T18: how often a merged agent pull request had a human review, from the AIDev v3 tables.

Data: AIDev v3 by Hao Li, Haoxiang Zhang and Ahmed E. Hassan (CC BY 4.0, arXiv 2507.15003), see NOTICE.
Tables read: pull_request, pr_reviews, pr_review_comments (plus the four tables that build the pool).
The two review tables are downloaded once, from the pinned dataset commit, into data/ (gitignored) and
checked against the sha256 values under `review_tables` in eval/inputs.lock.json.

Pool: the same pool as the rules replay (eval/replay_aidev.py build_pool, not changed): agent pull requests
linked to an issue, in repositories with a permissive licence.

Run from the repository root (DuckDB read-only, no network once the files are in data/):
    .venv/bin/python -I eval/review_stats.py

Writes results/review_stats.json: every number, and the definition of each. This is a description of what
GitHub recorded for these pull requests. It says nothing about the care of whoever merged them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import platform
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
DATA = REPO / "data"
OUT = REPO / "results" / "review_stats.json"
MIN_GROUP = 30
POOL_TABLES = ("related_issue", "issue", "pull_request", "repository")
REVIEW_TABLES = ("pr_reviews", "pr_review_comments")
NEEDED = {
    "pull_request": ("id", "agent", "user", "created_at", "merged_at", "html_url"),
    "pr_reviews": ("id", "pr_id", "user", "user_type", "state", "body"),
    "pr_review_comments": ("id", "pull_request_review_id", "user", "user_type"),
}
FLAGGED_SOURCES = ("results/replay_v4_devABC.json", "results/replay_v4_sampleD.json")

TERMS = {
    "human": "A review row in pr_reviews, or an inline comment row in pr_review_comments, whose user_type is "
             "'User'. The dataset's own user_type column is the only marker used; no list of names was made.",
    "bot": "user_type is 'Bot' (the dataset's marker). A missing user_type is neither human nor bot.",
    "human review": "At least one pr_reviews row of the pull request (pr_id) with user_type 'User', in any state "
                    "(APPROVED, COMMENTED, CHANGES_REQUESTED, DISMISSED).",
    "human inline comment": "At least one pr_review_comments row with user_type 'User' that belongs, through "
                            "pull_request_review_id = pr_reviews.id, to a review of the pull request.",
    "merged": "pull_request.merged_at is not null.",
    "pool": "Pull requests from eval/replay_aidev.py build_pool: linked to an issue in related_issue, in a "
            "repository with a permissive licence, the linked issue a real issue with a non-empty body.",
    "author": "pull_request.user, compared with the reviewer's user name ignoring case. For Copilot and Devin the "
              "author is the agent's own account, so every human is someone else; for the other agents it is "
              "the person who ran the agent.",
    "empty approval": "A review with state APPROVED whose body is null or only whitespace.",
    "timing": "Seconds from pull_request.created_at to merged_at, both ISO-8601 UTC. A negative gap or a value "
              "that does not parse is counted and left out of the time figures. 'Within 10 min' and 'within "
              "60 min' include the limit.",
}

DEFINITIONS = {
    "pool_prs": "Pool pull requests in the group, merged or not.",
    "merged": "Pool pull requests with merged_at set.",
    "merged_with_human_review": "Merged, and at least one human review.",
    "merged_no_human_review": "Merged, and no pr_reviews row with user_type 'User' (bot-only reviews and no "
                              "reviews both land here).",
    "merged_no_human_inline_comment": "Merged, and no human inline comment.",
    "merged_no_human_review_and_no_human_inline_comment": "Merged, no human review and no human inline comment.",
    "merged_no_human_review_by_anyone_but_the_author": "Merged, and no human review by an account other than the "
                                                        "author's (includes the ones with no human review).",
    "merged_no_human_review_or_inline_comment_by_anyone_but_the_author":
        "Merged, and no human review and no human inline comment by an account other than the author's.",
    "merged_human_reviewed_only_empty_approvals": "Merged, with at least one human review, every human review "
                                                  "being an empty approval.",
    "time.timed": "Merged pull requests with a parseable, non-negative time from created_at to merged_at.",
    "time.negative_durations_left_out": "Merged pull requests whose merged_at is before created_at; left out.",
    "time.unparseable_left_out": "Merged pull requests whose created_at or merged_at did not parse; left out.",
    "time.median_minutes": "Median of the timed gaps, in minutes (linear interpolation), rounded to 3 decimals.",
    "time.merged_within_10_min": "Timed pull requests merged 10 minutes or less after creation.",
    "time.merged_within_60_min": "Timed pull requests merged 60 minutes or less after creation.",
    "time.share_within_10_min": "merged_within_10_min divided by timed, rounded to 4 decimals.",
    "time.share_within_60_min": "merged_within_60_min divided by timed, rounded to 4 decimals.",
    "flagged.listed": "Distinct pull request URLs flagged by rules v4 (a non-empty extras list) in "
                      "results/replay_v4_devABC.json (samples A, B, C) and results/replay_v4_sampleD.json.",
    "flagged.found_in_pool": "Listed URLs that match a pool pull request.",
    "flagged.not_in_pool": "Listed URLs that match no pool pull request.",
    "flagged.merged": "Flagged pool pull requests that were merged.",
    "flagged.not_merged": "Flagged pool pull requests that were not merged.",
    "flagged.merged_with_human_inline_comment": "Flagged and merged, with at least one human inline comment.",
    "flagged.merged_with_human_review": "Flagged and merged, with at least one human review.",
    "flagged.merged_with_neither": "Flagged and merged, with no human review and no human inline comment.",
}
# Count metrics that also get a share, and what the share divides by.
SHARES = {
    "merged_with_human_review": "merged",
    "merged_no_human_review": "merged",
    "merged_no_human_inline_comment": "merged",
    "merged_no_human_review_and_no_human_inline_comment": "merged",
    "merged_no_human_review_by_anyone_but_the_author": "merged",
    "merged_no_human_review_or_inline_comment_by_anyone_but_the_author": "merged",
    "merged_human_reviewed_only_empty_approvals": "merged_with_human_review",
}
for _k, _d in SHARES.items():
    DEFINITIONS[f"shares.{_k}"] = f"{_k} divided by {_d}, rounded to 4 decimals."

FEATURES = """
CREATE OR REPLACE TEMP TABLE _rs_feat AS
WITH m AS (
    SELECT p.id, p.agent, p.user AS author, p.created_at, p.merged_at, p.html_url,
           p.merged_at IS NOT NULL AS is_merged
    FROM pull_request p JOIN pool ON pool.pr_id = p.id),
rv AS (
    SELECT r.pr_id,
           count(*) FILTER (WHERE r.user_type = 'User') AS human_reviews,
           count(*) FILTER (WHERE r.user_type = 'User' AND lower(r.user) <> lower(m.author)) AS other_reviews,
           count(*) FILTER (WHERE r.user_type = 'User' AND r.state = 'APPROVED'
                              AND trim(coalesce(r.body, '')) = '') AS human_empty_approvals
    FROM pr_reviews r JOIN m ON m.id = r.pr_id GROUP BY r.pr_id),
cm AS (
    SELECT r.pr_id,
           count(*) FILTER (WHERE c.user_type = 'User') AS human_comments,
           count(*) FILTER (WHERE c.user_type = 'User' AND lower(c.user) <> lower(m.author)) AS other_comments
    FROM pr_review_comments c
    JOIN pr_reviews r ON r.id = c.pull_request_review_id
    JOIN m ON m.id = r.pr_id GROUP BY r.pr_id)
SELECT m.*,
       coalesce(rv.human_reviews, 0) AS human_reviews,
       coalesce(rv.other_reviews, 0) AS other_reviews,
       coalesce(rv.human_empty_approvals, 0) AS human_empty_approvals,
       coalesce(cm.human_comments, 0) AS human_comments,
       coalesce(cm.other_comments, 0) AS other_comments,
       epoch(try_cast(m.merged_at AS TIMESTAMPTZ)) - epoch(try_cast(m.created_at AS TIMESTAMPTZ)) AS secs
FROM m LEFT JOIN rv ON rv.pr_id = m.id LEFT JOIN cm ON cm.pr_id = m.id
"""

AGG = """
SELECT count(*),
       count(*) FILTER (WHERE is_merged),
       count(*) FILTER (WHERE is_merged AND human_reviews > 0),
       count(*) FILTER (WHERE is_merged AND human_reviews = 0),
       count(*) FILTER (WHERE is_merged AND human_comments = 0),
       count(*) FILTER (WHERE is_merged AND human_reviews = 0 AND human_comments = 0),
       count(*) FILTER (WHERE is_merged AND other_reviews = 0),
       count(*) FILTER (WHERE is_merged AND other_reviews = 0 AND other_comments = 0),
       count(*) FILTER (WHERE is_merged AND human_reviews > 0 AND human_empty_approvals = human_reviews),
       count(*) FILTER (WHERE is_merged AND secs >= 0),
       count(*) FILTER (WHERE is_merged AND secs < 0),
       count(*) FILTER (WHERE is_merged AND secs IS NULL),
       quantile_cont(secs, 0.5) FILTER (WHERE is_merged AND secs >= 0),
       count(*) FILTER (WHERE is_merged AND secs >= 0 AND secs <= 600),
       count(*) FILTER (WHERE is_merged AND secs >= 0 AND secs <= 3600)
FROM _rs_feat {where}
"""
COUNT_KEYS = ("pool_prs", "merged", "merged_with_human_review", "merged_no_human_review",
              "merged_no_human_inline_comment", "merged_no_human_review_and_no_human_inline_comment",
              "merged_no_human_review_by_anyone_but_the_author",
              "merged_no_human_review_or_inline_comment_by_anyone_but_the_author",
              "merged_human_reviewed_only_empty_approvals")


def _ratio(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def _stats(con, where: str = "", params: tuple = ()) -> dict:
    row = con.execute(AGG.format(where=where), list(params)).fetchone()
    out = dict(zip(COUNT_KEYS, row[:9]))
    timed, negative, unparseable, median, w10, w60 = row[9:]
    out["shares"] = {k: _ratio(out[k], out[d]) for k, d in SHARES.items()}
    out["time"] = {
        "timed": timed, "negative_durations_left_out": negative, "unparseable_left_out": unparseable,
        "median_minutes": None if median is None else round(median / 60, 3),
        "merged_within_10_min": w10, "merged_within_60_min": w60,
        "share_within_10_min": _ratio(w10, timed), "share_within_60_min": _ratio(w60, timed),
    }
    return out


def compute(con, flagged_urls, min_group: int = MIN_GROUP) -> dict:
    """con needs the tables pull_request, pr_reviews, pr_review_comments and pool(pr_id)."""
    con.execute("SET TimeZone = 'UTC'")
    con.execute(FEATURES)
    agents = [r[0] for r in con.execute("SELECT DISTINCT agent FROM _rs_feat ORDER BY agent").fetchall()]
    by_agent, below = {}, {}
    for agent in agents:
        s = _stats(con, "WHERE agent = ?", (agent,))
        if s["merged"] >= min_group:
            by_agent[agent] = s
        else:
            below[agent] = s["merged"]
    urls = sorted(set(flagged_urls))
    con.execute("CREATE OR REPLACE TEMP TABLE _rs_flagged(url VARCHAR)")
    for u in urls:
        con.execute("INSERT INTO _rs_flagged VALUES (?)", [u])
    found, merged, with_comment, with_review, neither = con.execute("""
        SELECT count(*), count(*) FILTER (WHERE x.is_merged),
               count(*) FILTER (WHERE x.is_merged AND x.human_comments > 0),
               count(*) FILTER (WHERE x.is_merged AND x.human_reviews > 0),
               count(*) FILTER (WHERE x.is_merged AND x.human_reviews = 0 AND x.human_comments = 0)
        FROM _rs_flagged f JOIN _rs_feat x ON x.html_url = f.url""").fetchone()
    return {
        "min_group": min_group,
        "overall": _stats(con),
        "by_agent": by_agent,
        "agents_below_min": below,
        "flagged": {"listed": len(urls), "found_in_pool": found, "not_in_pool": len(urls) - found,
                    "merged": merged, "not_merged": found - merged,
                    "merged_with_human_inline_comment": with_comment,
                    "merged_with_human_review": with_review, "merged_with_neither": neither},
    }


def missing_columns(con, table: str, needed) -> list[str]:
    have = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {table}").fetchall()}
    return [c for c in needed if c not in have]


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_review_tables(data_dir: pathlib.Path, lock_entry: dict) -> list[str]:
    """Problems (empty list when none) between the review parquet files and the lock's `review_tables`."""
    problems = []
    for name, want in lock_entry.items():
        path = data_dir / name
        if not path.exists():
            problems.append(f"{name} missing")
        elif sha256(path) != want["sha256"]:
            problems.append(f"{name} sha256 {sha256(path)} != {want['sha256']}")
    return problems


def flagged_pr_urls(dev_abc: dict, sample_d: dict) -> list[str]:
    """Pull request URLs with at least one rules-v4 extra: samples A, B, C (dev file) and D."""
    urls = [p["pr_url"] for p in dev_abc["prs"] if p["v4"]["extras"]]
    urls += [p["pr_url"] for p in sample_d["prs"] if p["extras"]]
    return sorted(set(urls))


def integrity_checks(con) -> dict:
    """Facts about the tables that the reading above relies on (all should be zero where named so)."""
    one = lambda sql: con.execute(sql).fetchone()[0]
    return {
        "review_rows": one("SELECT count(*) FROM pr_reviews"),
        "review_comment_rows": one("SELECT count(*) FROM pr_review_comments"),
        "reviews_whose_pr_is_not_in_pull_request": one(
            "SELECT count(*) FROM pr_reviews r ANTI JOIN pull_request p ON p.id = r.pr_id"),
        "review_comments_whose_review_is_not_in_pr_reviews": one(
            "SELECT count(*) FROM pr_review_comments c ANTI JOIN pr_reviews r ON r.id = c.pull_request_review_id"),
        "review_comments_whose_url_names_another_pull_request_than_their_review": one("""
            SELECT count(*) FROM pr_review_comments c
            JOIN pr_reviews r ON r.id = c.pull_request_review_id JOIN pull_request p ON p.id = r.pr_id
            WHERE c.pull_request_url <> p.repo_url || '/pulls/' || CAST(p.number AS VARCHAR)"""),
        "review_ids_that_repeat": one("SELECT count(*) - count(DISTINCT id) FROM pr_reviews"),
        "review_rows_with_user_type_missing": one("SELECT count(*) FROM pr_reviews WHERE user_type IS NULL"),
        "review_comment_rows_with_user_type_missing": one(
            "SELECT count(*) FROM pr_review_comments WHERE user_type IS NULL"),
        "user_type_User_but_name_ends_in_[bot]": one(
            "SELECT (SELECT count(*) FROM pr_reviews WHERE user_type = 'User' AND user LIKE '%[bot]') + "
            "(SELECT count(*) FROM pr_review_comments WHERE user_type = 'User' AND user LIKE '%[bot]')"),
        "user_type_Bot_but_name_has_no_[bot]_suffix": one(
            "SELECT (SELECT count(*) FROM pr_reviews WHERE user_type = 'Bot' AND user NOT LIKE '%[bot]') + "
            "(SELECT count(*) FROM pr_review_comments WHERE user_type = 'Bot' AND user NOT LIKE '%[bot]')"),
        "review_state_values": sorted(r[0] for r in con.execute(
            "SELECT DISTINCT state FROM pr_reviews WHERE state IS NOT NULL").fetchall()),
        "user_type_values": sorted(r[0] for r in con.execute(
            "SELECT DISTINCT user_type FROM (SELECT user_type FROM pr_reviews UNION ALL "
            "SELECT user_type FROM pr_review_comments) WHERE user_type IS NOT NULL").fetchall()),
    }


def ensure_review_tables(lock_entry: dict, base_url: str) -> None:
    DATA.mkdir(exist_ok=True)
    for name in lock_entry:
        dest = DATA / name
        if not dest.exists():
            print(f"downloading {name}", file=sys.stderr)
            part = dest.with_suffix(".part")
            urllib.request.urlretrieve(base_url + name, part)    # pinned commit, then sha256-checked
            part.rename(dest)


def main() -> int:
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()
    sys.path.insert(0, str(HERE))
    import duckdb
    import replay_aidev as R
    lock = R.LOCK
    if "review_tables" not in lock:
        sys.exit("eval/inputs.lock.json has no `review_tables` entry")
    R.check_inputs()
    ensure_review_tables(lock["review_tables"], R.BASE_URL)
    bad = check_review_tables(DATA, lock["review_tables"])
    if bad:
        sys.exit("review tables do not match eval/inputs.lock.json: " + "; ".join(bad))
    pool, funnel = R.build_pool()

    con = duckdb.connect()
    con.execute("SET memory_limit='1GB'; SET threads=2; SET TimeZone='UTC'")
    for t in ("pull_request", *REVIEW_TABLES):
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{DATA / (t + '.parquet')}')")
    for t, cols in NEEDED.items():
        gone = missing_columns(con, t, cols)
        if gone:
            sys.exit(f"{t}.parquet lacks column(s) {gone}: stop, the metrics that need them cannot be computed")
    con.execute("CREATE TABLE pool(pr_id BIGINT)")
    con.executemany("INSERT INTO pool VALUES (?)", [(p["pr_id"],) for p in pool])

    srcs = {rel: json.loads((REPO / rel).read_text()) for rel in FLAGGED_SOURCES}
    dev, sd = (srcs[r] for r in FLAGGED_SOURCES)
    urls = flagged_pr_urls(dev, sd)
    result = compute(con, urls)
    in_dev = sum(v["v4"]["flagged_prs"] for v in dev["summary"]["by_sample"].values())
    in_d = sd["summary"]["kill_test_1b"]["flagged"]
    result["flagged_sources"] = {
        rel: {"sha256": sha256(REPO / rel), "flagged_pull_requests": n}
        for rel, n in zip(FLAGGED_SOURCES, (in_dev, in_d))}
    checks = integrity_checks(con)
    checks["flagged_list_length_equals_flagged_counts_in_the_two_summaries"] = (len(urls) == in_dev + in_d)
    checks["pull_request_columns"] = [r[0] for r in con.execute("DESCRIBE SELECT * FROM pull_request").fetchall()]
    files = {f"{t}.parquet": {"bytes": (DATA / f"{t}.parquet").stat().st_size,
                              "sha256": sha256(DATA / f"{t}.parquet")} for t in (*POOL_TABLES, *REVIEW_TABLES)}
    report = {
        "dataset": "hao-li/AIDev", "dataset_ref": lock["dataset_ref"], "dataset_revision": lock["dataset_revision"],
        "licence": "CC BY 4.0 (see NOTICE)", "inputs_lock_sha256": R.sha256(R.LOCK_FILE), "files": files,
        "duckdb": duckdb.__version__, "python": platform.python_version(),
        "pool_funnel": funnel, "terms": TERMS, "definitions": DEFINITIONS, **result,
        "checks": checks,
        "not_computed": {
            "no_review_no_inline_comment_no_issue_style_comment":
                "Needs the pr_comments table, which is not in data/ and is not fetched here. "
                "merged_no_human_review_and_no_human_inline_comment is an upper bound for it.",
            "merged_by_the_authors_own_account":
                "pull_request has none of a merger, merged_by or merged-by-user column (checks.pull_request_columns), "
                "so who pressed merge is not in the data. The by_anyone_but_the_author rows are the nearest "
                "available figures; they only look at reviews and review comments.",
        },
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    o = result["overall"]
    print(f"pool {o['pool_prs']}, merged {o['merged']}; merged with no human review {o['merged_no_human_review']} "
          f"({o['shares']['merged_no_human_review']}), no human inline comment {o['merged_no_human_inline_comment']}, "
          f"neither {o['merged_no_human_review_and_no_human_inline_comment']}")
    print(f"only empty approvals among the human-reviewed: {o['merged_human_reviewed_only_empty_approvals']} "
          f"of {o['merged_with_human_review']}; median minutes to merge {o['time']['median_minutes']}; within 10 min "
          f"{o['time']['share_within_10_min']}, within 60 min {o['time']['share_within_60_min']}")
    print(f"agents tabulated: {', '.join(result['by_agent'])}; below the minimum: {result['agents_below_min']}")
    print(f"flagged by rules v4: {result['flagged']}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
