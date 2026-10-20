"""eval/aidev_local.py: file rows from a parquet file keep file order and cover only the pull requests asked for."""
import pathlib
import sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import aidev_local as L  # noqa: E402


def make(tmp_path, rows):
    f = tmp_path / "pr_commit_details.parquet"
    con = duckdb.connect()
    con.execute("CREATE TABLE t(sha VARCHAR, pr_id BIGINT, filename VARCHAR, status VARCHAR, patch VARCHAR, author VARCHAR)")
    con.executemany("INSERT INTO t VALUES (?,?,?,?,?,?)", [(s, p, fn, st, pa, "x") for s, p, fn, st, pa in rows])
    con.execute("COPY t TO ? (FORMAT PARQUET)", [str(f)])
    return f


def test_rows_come_back_per_pull_request_in_file_order_with_only_the_four_keys(tmp_path):
    f = make(tmp_path, [("b", 2, "z.py", "added", "p1"), ("a", 1, "y.py", "modified", "p2"), ("c", 2, "a.py", "added", "p3")])
    got = L.commit_rows(f, [2, 1])
    assert [r["sha"] for r in got[2]] == ["b", "c"] and got[1] == [{"sha": "a", "filename": "y.py", "status": "modified", "patch": "p2"}]


def test_a_pull_request_not_in_the_file_is_absent_and_others_are_not_returned(tmp_path):
    f = make(tmp_path, [("a", 1, "y.py", "added", "p"), ("b", 3, "z.py", "added", "p")])
    got = L.commit_rows(f, [1, 2])
    assert set(got) == {1}


def test_ids_may_repeat_or_be_strings(tmp_path):
    f = make(tmp_path, [("a", 5, "y.py", "added", "p")])
    assert list(L.commit_rows(f, ["5", 5])) == [5]

