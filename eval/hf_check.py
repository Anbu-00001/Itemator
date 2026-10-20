"""Before the leg-2 run (rubric amendment 3): do the parquet file's rows for three pull requests equal, row for row, the rows the
dataset API gave earlier? Compares fingerprints (SHA-256 of sha, filename, status, patch per row), so no patch text is stored.

usage: python3 eval/hf_check.py PARQUET_FILE   |   python3 eval/hf_check.py --make-expected CACHED_API_ROWS_JSON"""
import hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import aidev_local  # noqa: E402

EXPECTED = ROOT / "eval" / "hf_check_expected.json"
OUT = ROOT / "results" / "hf_check.json"


def fingerprint(rows):
    """One digest per row, in order."""
    return [hashlib.sha256(json.dumps([r.get(k) for k in aidev_local.KEYS]).encode()).hexdigest() for r in rows]


def compare(expected, got_rows):
    """{pr id: True/False} whether the rows read now fingerprint exactly as the expected list, same order, same length."""
    return {pid: fingerprint(got_rows.get(int(pid), [])) == fps for pid, fps in expected.items()}


def make_expected(cached_rows, pr_ids):
    by = {}
    for r in cached_rows:
        by.setdefault(r["pr_id"], []).append(r)
    return {str(i): fingerprint(by[i]) for i in pr_ids}


def main(argv):
    if len(argv) >= 3 and argv[1] == "--make-expected":
        exp = make_expected(json.loads(pathlib.Path(argv[2]).read_text()), [2767657628, 2768570229, 2811846298])
        EXPECTED.write_text(json.dumps(exp) + "\n")
        print({k: len(v) for k, v in exp.items()})
        return 0
    exp = json.loads(EXPECTED.read_text())
    res = compare(exp, aidev_local.commit_rows(argv[1], [int(i) for i in exp]))
    OUT.write_text(json.dumps({"rows_equal_to_the_api_pages": res, "all_equal": all(res.values())}) + "\n")
    print(res)
    return 0 if all(res.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
