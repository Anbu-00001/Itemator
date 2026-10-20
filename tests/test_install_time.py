"""The install-time study's pure parts (eval/install_time.py): its sample, its commands (no package code may run) and its summary."""
import sys

sys.path.insert(0, "eval")
import install_time as T  # noqa: E402


def test_the_commands_never_run_package_code_and_never_use_a_cache():
    pip = T.command("PyPI", "pandas", "2.2.3", "/e", "/c")
    assert pip[0] == "/e/bin/pip" and "--only-binary=:all:" in pip and "--no-cache-dir" in pip and pip[-1] == "pandas==2.2.3"
    npm = T.command("npm", "@types/node", "20.11.0", "/e", "/c")
    assert "--ignore-scripts" in npm and npm[npm.index("--cache") + 1] == "/c" and npm[-1] == "@types/node@20.11.0"


def test_the_sample_is_the_first_weighed_lines_of_one_ecosystem_in_file_order():
    rows = [{"pr": i, "name": f"p{i}", "ecosystem": "npm" if i % 2 else "PyPI", "state": "merged",
             "weight": {"weight": "ok", "version": "1", "packages": 1, "bytes": i} if i != 3 else {"weight": "unavailable"}} for i in range(8)]
    assert [r["pr"] for r in T.sample({"rows": rows}, "npm", 2)] == [1, 5]
    assert [r["pr"] for r in T.sample({"rows": rows}, "PyPI", 9)] == [0, 2, 4, 6]


def test_spearman_and_the_summary():
    assert T.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0 and T.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert T.spearman([1, 2], [1, 2]) is None and T.ranks([5, 1, 5]) == [2.5, 1.0, 2.5]
    rows = [{"name": "a", "version": "1", "pr": "x", "bytes": b, "status": "installed", "seconds": s} for b, s in ((1, 2.0), (2, 4.0), (3, 9.0))]
    rows.append({"name": "z", "version": "1", "pr": "y", "bytes": 9, "status": "needs_source_build", "seconds": 1.0})
    s = T.summarize(rows, 1.5)
    assert (s["measured"], s["median_seconds"], s["total_seconds"], s["median_seconds_above_baseline"]) == (3, 4.0, 15.0, 2.5)
    assert s["not_measured"] == {"needs_source_build": 1} and s["spearman_bytes_seconds"] == 1.0 and s["slowest"][0]["seconds"] == 9.0


def test_a_name_that_reads_as_an_option_is_refused():
    import pytest
    with pytest.raises(ValueError):
        T.command("npm", "--registry=https://evil.example", "1", "/e", "/c")
