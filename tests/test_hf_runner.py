"""hf_runner/server.py's pure parts: who is let in, and which jobs exist."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hf_runner"))
import server as S  # noqa: E402


def test_only_the_exact_token_is_let_in_and_never_when_none_is_set():
    assert S.authorized("abc", "abc")
    assert not S.authorized("abd", "abc") and not S.authorized("", "abc") and not S.authorized(None, "abc")
    assert not S.authorized("", "") and not S.authorized(None, "") and not S.authorized("x", "") and not S.authorized(" ", "")


def test_only_a_listed_job_has_a_command_and_it_reads_the_parquet_from_the_data_folder():
    cmd, result = S.job_command("leg2", "/d")
    assert cmd[1:] == ["eval/aidev_revert.py", "--score", "--commit-details", "/d/pr_commit_details.parquet"] and result == "results/aidev_revert_v6.json"
    assert S.job_command("check", "/d")[1] == "results/hf_check.json"
    assert S.job_command("rm -rf", "/d") is None and S.job_command("", "/d") is None


def test_the_stage_script_copies_the_runner_and_the_rules_but_not_the_caches(tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import hf_runner_stage as T
    fake = tmp_path / "repo"
    for rel in ("itemator/extras.py", "eval/aidev_revert.py", "eval/cache/big.json", "eval/__pycache__/x.pyc", "hf_runner/server.py",
                "hf_runner/Dockerfile", "hf_runner/README.md", "results/aidev_revert_frame.json"):
        (fake / rel).parent.mkdir(parents=True, exist_ok=True)
        (fake / rel).write_text("x")
    old, T.ROOT = T.ROOT, fake
    try:
        files = T.stage(tmp_path / "out")
    finally:
        T.ROOT = old
    assert {"hf_runner/server.py", "Dockerfile", "README.md", "itemator/extras.py", "eval/aidev_revert.py", "results/aidev_revert_frame.json"} <= set(files)
    assert not any("cache" in f for f in files)


def test_every_job_script_exists_relative_to_the_app_folder_the_server_runs_in():
    for job in ("leg2", "check", "population", "weight"):
        script = next(a for a in S.job_command(job, "/d")[0] if a.endswith(".py"))
        assert (S.APP / script).is_file()


def test_the_population_job_reads_the_result_file_the_script_writes():
    sys.path.insert(0, str(ROOT / "eval"))
    import aidev_population as P
    assert S.job_command("population", "/d")[1] == "results/" + P.OUT.name


def test_the_check_compares_row_by_row_in_order_and_flags_any_difference():
    sys.path.insert(0, str(ROOT / "eval"))
    import hf_check as C
    rows = [{"sha": "a", "filename": "x", "status": "added", "patch": "p"}, {"sha": "b", "filename": "y", "status": "added", "patch": "q"}]
    exp = {"1": C.fingerprint(rows)}
    assert C.compare(exp, {1: rows}) == {"1": True}
    assert C.compare(exp, {1: rows[::-1]}) == {"1": False}
    assert C.compare(exp, {1: rows[:1]}) == {"1": False}
    assert C.compare(exp, {1: [dict(rows[0], patch="P"), rows[1]]}) == {"1": False}
    assert C.compare(exp, {}) == {"1": False}


def test_the_weight_job_reads_the_result_file_the_script_writes():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
    import aidev_weight as W
    assert S.job_command("weight", "/d")[1] == "results/" + W.OUT.name
