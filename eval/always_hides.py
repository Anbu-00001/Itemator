"""The always-hides study (eval/always_hides_rubric.json, pushed before it ran): would `always` answers given on earlier agent
pull requests have hidden a file a reviewer later objected to? Reads the repeat study's shard rows and the 24 real catches.

usage: python3 eval/always_hides.py ROWS_FILE [ROWS_FILE ...]"""
from __future__ import annotations

import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "always_hides_v1.json"


# ---------------------------------------------------------------- pure parts (tests/test_always_hides.py)

def order(r: dict) -> tuple:
    return (r["created_at"] or "", r["id"])


def hidden(case_row: dict, repo_rows: list, path: str) -> bool:
    """True when a row of the same repository that sorts before `case_row` asked about `path`."""
    return any(order(r) < order(case_row) and any(p == path for _, p in r["questions"]) for r in repo_rows)


def summarise(rows: list, rubric: dict) -> dict:
    read = [r for r in rows if r["hidden"] is not None]
    h = sum(r["hidden"] for r in read)
    s = {"cases": len(rows), "read": len(read), "unreadable": len(rows) - len(read), "hidden": h}
    s["sentence"] = rubric["sentence"].format(n=len(read), hidden=h, hidden_word="it" if h == 1 else "them")
    return s


# ---------------------------------------------------------------- the run (local files)

def main(argv=None) -> int:
    files = (argv if argv is not None else sys.argv[1:])
    by_id, by_repo = {}, {}
    for f in files:
        for r in json.loads(pathlib.Path(f).read_text())["rows"]:
            by_id[r["id"]] = r
            by_repo.setdefault(r["repo"], []).append(r)
    ids = {p["html_url"]: p["id"] for p in json.loads((ROOT / "eval" / "cache" / "aidev" / "pull_request.json").read_text())}
    cases = json.loads((ROOT / "results" / "real_catches_v1.json").read_text())["cases"]
    rows = []
    for c in cases:
        row = by_id.get(ids.get(c["pr"]))
        rows.append({"key": c["key"], "pr": c["pr"], "path": c["path"], "outcome": c["outcome"],
                     "hidden": None if row is None else hidden(row, by_repo[row["repo"]], c["path"])})
    rubric = json.loads((ROOT / "eval" / "always_hides_rubric.json").read_text())
    out = {"rubric": "eval/always_hides_rubric.json", "shard_files": len(files), "summary": summarise(rows, rubric), "rows": rows}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
