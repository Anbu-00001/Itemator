"""Writes eval/unwrap_spike_cases.json: AIDev agent pull requests (any title), ordered by a seeded hash, drawn BEFORE any
file of any of them is fetched. Reads only the cached AIDev pull_request table.
usage: python3 eval/unwrap_cases.py   (seed and limit are fixed below)"""
from __future__ import annotations

import hashlib, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
TABLE = ROOT / "eval" / "cache" / "aidev" / "parquet" / "hao-li_AIDev__pull_request.parquet"
OUT = ROOT / "eval" / "unwrap_spike_cases.json"
SEED = 20261018
LIMIT = 800


def order_key(pr_id: int) -> str:
    return hashlib.sha256(f"{SEED}|{pr_id}".encode()).hexdigest()


def pick(rows: list[tuple], limit: int = LIMIT) -> list[dict]:
    """rows: (id, number, agent, html_url). Sorted by the seeded hash of the id; the first `limit`."""
    ranked = sorted(rows, key=lambda r: order_key(r[0]))[:limit]
    return [{"pr_id": r[0], "number": r[1], "agent": r[2], "html_url": r[3]} for r in ranked]


def main() -> None:
    import duckdb          # only this script reads the table; the tests of pick() need no extra package
    rows = duckdb.connect().execute(f"select id, number, agent, html_url from '{TABLE}'").fetchall()
    cases = pick(rows)
    OUT.write_text(json.dumps({"seed": SEED, "table_rows": len(rows), "cases": cases}, indent=1))
    print(f"{len(rows)} pull requests; first {len(cases)} by seeded hash written to {OUT.name}")


if __name__ == "__main__":
    main()
