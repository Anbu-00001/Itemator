"""T18: how often a merged agent pull request had a human look at it. A tiny in-memory DuckDB stands in for the
AIDev tables; nothing here touches the network or data/."""
import importlib.util
import pathlib

import duckdb
import pytest

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("review_stats", HERE.parent / "eval" / "review_stats.py")
RS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RS)

URL = "https://github.com/o/r/pull/{}"


def build(prs, reviews=(), comments=(), pool=None):
    """prs: (id, agent, author, created_at, merged_at); reviews: (id, pr_id, user, user_type, state, body);
    comments: (id, review_id, user, user_type)."""
    con = duckdb.connect()
    con.execute("CREATE TABLE pull_request(id BIGINT, agent VARCHAR, user VARCHAR, created_at VARCHAR, "
                "merged_at VARCHAR, html_url VARCHAR)")
    con.execute("CREATE TABLE pr_reviews(id BIGINT, pr_id BIGINT, user VARCHAR, user_type VARCHAR, "
                "state VARCHAR, body VARCHAR)")
    con.execute("CREATE TABLE pr_review_comments(id BIGINT, pull_request_review_id BIGINT, user VARCHAR, "
                "user_type VARCHAR)")
    con.execute("CREATE TABLE pool(pr_id BIGINT)")
    for p in prs:
        con.execute("INSERT INTO pull_request VALUES (?, ?, ?, ?, ?, ?)", [*p, URL.format(p[0])])
    for r in reviews:
        con.execute("INSERT INTO pr_reviews VALUES (?, ?, ?, ?, ?, ?)", list(r))
    for c in comments:
        con.execute("INSERT INTO pr_review_comments VALUES (?, ?, ?, ?)", list(c))
    for pid in (pool if pool is not None else [p[0] for p in prs if p[0] != 7]):
        con.execute("INSERT INTO pool VALUES (?)", [pid])
    return con


def T(minutes):
    """A merged_at that many minutes after the fixed created_at."""
    h, m = divmod(minutes, 60)
    return f"2025-07-26T{h:02d}:{m:02d}:00Z"


C0 = "2025-07-26T00:00:00Z"
PRS = [
    (1, "Codex", "alice", C0, T(5)),        # merged in 5 min, no review at all
    (2, "Copilot", "Copilot", C0, T(30)),   # one human approval with an empty body
    (3, "Copilot", "Copilot", C0, T(120)),  # human comment review + a human inline comment
    (4, "Codex", "alice", C0, T(20)),       # only the author's own review, plus a bot review
    (5, "Copilot", "Copilot", C0, T(61)),   # bot review only
    (6, "Codex", "alice", C0, None),        # not merged
    (7, "Codex", "alice", C0, T(5)),        # merged but not in the pool
    (8, "Codex", "alice", T(10), T(5)),     # merged before it was created
    (9, "Copilot", "Copilot", C0, T(60)),   # empty approval + approval with a body
    (10, "Codex", "alice", C0, T(10)),      # review whose user_type is unknown
    (11, "Devin", "devin[bot]", C0, T(15)),  # comment-state review with an empty body
    (12, "Copilot", "Copilot", C0, T(40)),  # empty approvals only: NULL, empty and blank bodies
]
REVIEWS = [
    (101, 2, "bob", "User", "APPROVED", None),
    (102, 3, "bob", "User", "COMMENTED", "please rename"),
    (103, 4, "alice", "User", "COMMENTED", "self note"),
    (104, 4, "ci[bot]", "Bot", "COMMENTED", "lint"),
    (105, 5, "ci[bot]", "Bot", "APPROVED", ""),
    (106, 9, "bob", "User", "APPROVED", ""),
    (107, 9, "carol", "User", "APPROVED", "LGTM"),
    (108, 10, None, None, "APPROVED", None),
    (109, 11, "bob", "User", "COMMENTED", ""),
    (110, 12, "bob", "User", "APPROVED", None),
    (111, 12, "carol", "User", "APPROVED", ""),
    (112, 12, "dave", "User", "APPROVED", "   "),
    (113, 6, "bob", "User", "APPROVED", None),
    (114, 7, "bob", "User", "APPROVED", None),
]
COMMENTS = [
    (201, 102, "bob", "User"),
    (202, 104, "ci[bot]", "Bot"),
    (203, 103, "alice", "User"),
    (204, 109, "Bob", "User"),
]


@pytest.fixture
def con():
    return build(PRS, REVIEWS, COMMENTS)


def test_merged_counts_only_pool_pull_requests_with_a_merge_time(con):
    s = RS.compute(con, [], min_group=1)["overall"]
    assert s["merged"] == 10          # 1,2,3,4,5,8,9,10,11,12 (6 is open, 7 is outside the pool)


def test_no_human_review_means_no_review_row_by_a_user_typed_account(con):
    s = RS.compute(con, [], min_group=1)["overall"]
    # no human review: 1 (none), 5 (bot only), 8 (none), 10 (unknown type)
    assert s["merged_no_human_review"] == 4
    assert s["merged_with_human_review"] == 6


def test_no_human_inline_comment_goes_through_the_review_it_belongs_to(con):
    s = RS.compute(con, [], min_group=1)["overall"]
    # human inline comments sit on PRs 3 (bob), 4 (alice, the author) and 11 (Bob); the bot's on PR 4 does not count
    assert s["merged_no_human_inline_comment"] == 7
    assert s["merged_no_human_review_and_no_human_inline_comment"] == 4


def test_a_review_by_the_authors_own_account_is_not_a_second_person(con):
    s = RS.compute(con, [], min_group=1)["overall"]
    # PR 4: the only human review and the only human inline comment are alice's, the author's
    assert s["merged_no_human_review_by_anyone_but_the_author"] == s["merged_no_human_review"] + 1
    assert s["merged_no_human_review_or_inline_comment_by_anyone_but_the_author"] == \
        s["merged_no_human_review_and_no_human_inline_comment"] + 1


def test_author_comparison_ignores_case(con):
    # PR 2's only human review is by "bob": once its author is "BOB" that is the author's own account
    con.execute("UPDATE pull_request SET user = 'BOB' WHERE id = 2")
    s = RS.compute(con, [], min_group=1)["overall"]
    assert s["merged_no_human_review_by_anyone_but_the_author"] == s["merged_no_human_review"] + 2


def test_only_empty_approvals(con):
    s = RS.compute(con, [], min_group=1)["overall"]
    # PR 2 (NULL body) and PR 12 (NULL, empty, blank) only; 9 has a body, 11 is not an approval, 3 is a comment
    assert s["merged_human_reviewed_only_empty_approvals"] == 2


def test_time_to_merge(con):
    s = RS.compute(con, [], min_group=1)["overall"]
    # timed: 1:5, 2:30, 3:120, 4:20, 5:61, 9:60, 10:10, 11:15, 12:40 (PR 8 is negative and left out)
    assert s["time"]["timed"] == 9
    assert s["time"]["negative_durations_left_out"] == 1
    assert s["time"]["median_minutes"] == 30.0
    assert s["time"]["merged_within_10_min"] == 2        # 5 and 10 (inclusive)
    assert s["time"]["merged_within_60_min"] == 7        # 60 included, 61 and 120 not
    assert s["time"]["share_within_10_min"] == pytest.approx(2 / 9, abs=1e-4)
    assert s["time"]["share_within_60_min"] == pytest.approx(7 / 9, abs=1e-4)


def test_unparseable_time_is_counted_not_guessed(con):
    con.execute("UPDATE pull_request SET merged_at = 'soon' WHERE id = 1")
    s = RS.compute(con, [], min_group=1)["overall"]
    assert s["merged"] == 10
    assert s["time"]["timed"] == 8
    assert s["time"]["unparseable_left_out"] == 1


def test_groups_under_the_minimum_are_listed_but_not_tabulated(con):
    out = RS.compute(con, [], min_group=4)
    assert set(out["by_agent"]) == {"Copilot", "Codex"}      # merged: Copilot 5, Codex 4 (1,4,8,10), Devin 1
    assert out["agents_below_min"] == {"Devin": 1}
    assert out["by_agent"]["Copilot"]["merged"] == 5
    assert out["by_agent"]["Copilot"]["merged_no_human_review"] == 1
    assert out["by_agent"]["Codex"]["merged_no_human_review"] == 3


def test_flagged_counts_are_counts_of_merged_flagged_pull_requests(con):
    flagged = [URL.format(n) for n in (1, 2, 3, 6)] + [URL.format(3), "https://github.com/o/r/pull/999"]
    f = RS.compute(con, flagged, min_group=1)["flagged"]
    assert f == {"listed": 5, "found_in_pool": 4, "merged": 3, "not_merged": 1,
                 "merged_with_human_inline_comment": 1, "merged_with_human_review": 2,
                 "merged_with_neither": 1, "not_in_pool": 1}


def test_every_metric_has_a_definition(con):
    out = RS.compute(con, [], min_group=1)

    def keys(d, prefix=""):
        for k, v in d.items():
            if isinstance(v, dict):
                yield from keys(v, f"{prefix}{k}.")
            else:
                yield f"{prefix}{k}"
    for k in keys(out["overall"]):
        assert k in RS.DEFINITIONS, f"no definition for {k}"
    for k in keys(out["flagged"]):
        assert f"flagged.{k}" in RS.DEFINITIONS, f"no definition for flagged.{k}"


def test_compute_is_deterministic(con):
    assert RS.compute(con, [URL.format(1)], min_group=1) == RS.compute(con, [URL.format(1)], min_group=1)


def test_missing_columns_are_reported():
    con = build(PRS)
    con.execute("ALTER TABLE pr_reviews DROP COLUMN user_type")
    assert RS.missing_columns(con, "pr_reviews", ("user", "user_type", "state")) == ["user_type"]
    assert RS.missing_columns(con, "pr_reviews", ("user", "state")) == []


def test_review_table_files_are_checked_against_the_lock(tmp_path):
    (tmp_path / "pr_reviews.parquet").write_bytes(b"abc")
    import hashlib
    good = hashlib.sha256(b"abc").hexdigest()
    lock = {"pr_reviews.parquet": {"sha256": good}, "pr_review_comments.parquet": {"sha256": good}}
    problems = RS.check_review_tables(tmp_path, lock)
    assert len(problems) == 1 and "pr_review_comments.parquet" in problems[0] and "missing" in problems[0]
    lock["pr_reviews.parquet"]["sha256"] = "0" * 64
    problems = RS.check_review_tables(tmp_path, lock)
    assert any("pr_reviews.parquet" in p and "sha256" in p for p in problems)
    (tmp_path / "pr_review_comments.parquet").write_bytes(b"abc")
    lock["pr_reviews.parquet"]["sha256"] = good
    assert RS.check_review_tables(tmp_path, lock) == []


def test_flagged_urls_are_the_pull_requests_with_a_v4_extra_in_both_files():
    dev = {"prs": [{"pr_url": "u1", "v4": {"extras": [{"kind": "x"}]}}, {"pr_url": "u2", "v4": {"extras": []}}]}
    held = {"prs": [{"pr_url": "u3", "extras": [{"kind": "x"}]}, {"pr_url": "u1", "extras": [{"kind": "x"}]},
                    {"pr_url": "u4", "extras": []}]}
    assert RS.flagged_pr_urls(dev, held) == ["u1", "u3"]


def test_integrity_checks_count_what_the_reading_relies_on():
    con = duckdb.connect()
    con.execute("CREATE TABLE pull_request(id BIGINT, repo_url VARCHAR, number BIGINT)")
    con.execute("CREATE TABLE pr_reviews(id BIGINT, pr_id BIGINT, user VARCHAR, user_type VARCHAR, state VARCHAR)")
    con.execute("CREATE TABLE pr_review_comments(id BIGINT, pull_request_review_id BIGINT, user VARCHAR, "
                "user_type VARCHAR, pull_request_url VARCHAR)")
    repo = "https://api.github.com/repos/o/r"
    con.execute(f"INSERT INTO pull_request VALUES (1, '{repo}', 5), (2, '{repo}', 6)")
    con.execute("INSERT INTO pr_reviews VALUES (10, 1, 'bob', 'User', 'APPROVED'), (11, 2, 'x[bot]', 'Bot', 'COMMENTED'), "
                "(12, 99, 'ghost', 'User', 'COMMENTED'), (13, 1, 'y[bot]', 'User', 'COMMENTED'), "
                "(14, 1, 'zed', 'Bot', 'COMMENTED'), (15, 1, 'n', NULL, 'COMMENTED'), (10, 1, 'bob', 'User', 'APPROVED')")
    con.execute(f"INSERT INTO pr_review_comments VALUES (20, 10, 'bob', 'User', '{repo}/pulls/5'), "
                f"(21, 11, 'x[bot]', 'Bot', '{repo}/pulls/5'), (22, 777, 'q', 'User', '{repo}/pulls/5'), "
                f"(23, 15, 'n', NULL, '{repo}/pulls/5')")
    c = RS.integrity_checks(con)
    assert c["review_rows"] == 7 and c["review_comment_rows"] == 4
    assert c["reviews_whose_pr_is_not_in_pull_request"] == 1
    assert c["review_comments_whose_review_is_not_in_pr_reviews"] == 1
    assert c["review_comments_whose_url_names_another_pull_request_than_their_review"] == 1
    assert c["review_ids_that_repeat"] == 1
    assert c["review_rows_with_user_type_missing"] == 1 and c["review_comment_rows_with_user_type_missing"] == 1
    assert c["user_type_User_but_name_ends_in_[bot]"] == 1
    assert c["user_type_Bot_but_name_has_no_[bot]_suffix"] == 1
    assert c["review_state_values"] == ["APPROVED", "COMMENTED"] and c["user_type_values"] == ["Bot", "User"]


def test_a_zero_second_gap_is_timed_and_not_negative():
    con = build([(1, "Codex", "alice", C0, C0)])
    t = RS.compute(con, [], min_group=1)["overall"]["time"]
    assert (t["timed"], t["negative_durations_left_out"], t["merged_within_10_min"]) == (1, 0, 1)
    assert t["median_minutes"] == 0.0


def test_inline_comment_author_comparison_ignores_case_too():
    con = build([(1, "Codex", "Zed", C0, T(5))], [(1, 1, "zed", "User", "COMMENTED", None)], [(1, 1, "ZED", "User")])
    s = RS.compute(con, [], min_group=1)["overall"]
    assert s["merged_no_human_review_or_inline_comment_by_anyone_but_the_author"] == 1
    assert s["merged_no_human_inline_comment"] == 0
