"""Per-commit file rows of AIDev pull requests, read from the dataset's own pr_commit_details parquet file instead of the
dataset-viewer API (eval/aidev_revert_rubric.json, amendment 3). Same table, same rows, in file order; one scan of the file
for all pull requests asked for."""
from __future__ import annotations

KEYS = ("sha", "filename", "status", "patch")


def commit_rows(parquet_file: str, pr_ids) -> dict:
    """{pr_id: [{sha, filename, status, patch}, ...]} in the file's row order (which is commit order, as the API serves it).
    A pull request with no rows in the file is absent from the result."""
    import duckdb
    ids = sorted({int(i) for i in pr_ids})
    cur = duckdb.connect().execute(
        "SELECT CAST(pr_id AS BIGINT), sha, filename, status, patch FROM read_parquet(?, file_row_number=true) "
        "WHERE pr_id = ANY(?) ORDER BY file_row_number", [str(parquet_file), ids])
    out: dict = {}
    for pid, *vals in cur.fetchall():
        out.setdefault(int(pid), []).append(dict(zip(KEYS, vals)))
    return out
