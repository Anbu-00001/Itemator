"""The image trial compares only what must not depend on the image (eval/image_trial.py); no network."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import image_trial as T  # noqa: E402

RUN = {"rules_version": 6, "state": "extras", "issue_iids": [3], "unplaced": [], "truncated": False, "generated_at": "t1",
       "card": "this project ran 1000 pipelines", "extras": [{"kind": "new_dependency", "path": "pyproject.toml", "name": "rich", "why": "w", "detail": [1]},
                                                              {"kind": "ci_or_config", "path": "a.yml", "name": "a.yml", "why": "v"}]}


def test_the_same_answer_in_another_order_and_at_another_time_is_the_same():
    other = dict(RUN, generated_at="t2", card="this project ran 1001 pipelines", extras=list(reversed(RUN["extras"])))
    assert T.compare(RUN, other) == {"same": True, "differs_in": [], "extras": 2}


def test_a_lost_extra_or_another_state_is_a_difference():
    assert T.compare(RUN, dict(RUN, extras=RUN["extras"][:1]))["differs_in"] == ["extras"]
    assert T.compare(RUN, dict(RUN, state="error", truncated=True))["differs_in"] == ["state", "truncated"]
    assert T.compare(RUN, dict(RUN, extras=[dict(RUN["extras"][0], why="x"), RUN["extras"][1]]))["same"] is False


def test_fetched_bytes_reads_du_output():
    assert T.fetched_bytes("7340032\t/tmp/apk\n") == 7_340_032
    assert T.fetched_bytes("  12 x") == 12
    assert T.fetched_bytes("du: cannot access") is None and T.fetched_bytes("") is None


def test_log_seconds_spans_the_first_and_last_stamp():
    log = "2026-10-21T07:16:02.065002Z 00O start\nno stamp here\n2026-10-21T07:16:10Z 00O mid\n2026-10-21T07:16:22.899236Z 00O end\n"
    assert T.log_seconds(log) == 20.8
    assert T.log_seconds("2026-10-21T07:16:02Z only one") is None and T.log_seconds("") is None
    assert T.log_seconds("x 2026-10-21T07:16:02Z\n2026-10-21T07:16:05Z y\n2026-10-21T07:16:09Z z") == 4.0   # a stamp mid-line is not a line start


def test_images_lists_each_image_and_its_git_download_in_mb():
    got = T.images({"image_compressed_bytes": 411_620_271}, {"image_compressed_bytes": 43_300_000, "apt_bytes": 23_800_000}, 20_640_000, 9_769_586)
    assert got == {"full": {"image": "python:3.12", "image_mb": 411.6, "git_mb_per_run": 0},
                   "slim": {"image": "python:3.12-slim", "image_mb": 43.3, "git_mb_per_run": 23.8},
                   "alpine": {"image": "python:3.12-alpine", "image_mb": 20.6, "git_mb_per_run": 9.8}}
