"""eval/patchday_replay.py: each pull request's row and the summary sentence, from the registered rubric."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import patchday_replay as R  # noqa: E402
from test_patchday import BUMP, CODE, ISSUE, SCRIPT  # noqa: E402

RUBRIC = json.loads((pathlib.Path(R.ROOT) / "eval" / "patchday_rubric.json").read_text())


def test_each_reason_it_stays_off():
    assert R.judge(ISSUE, None)["why_not"] == "unreadable"
    assert R.judge("Update PHP to 8.3.36.", [BUMP])["why_not"] == "no_cve_in_task_text"
    assert R.judge(ISSUE + "\n```itemator-scope\npaths: src/**\n```\n", [BUMP])["why_not"] == "own_scope_block"
    assert R.judge(ISSUE, [CODE])["why_not"] == "no_version_only_file"


def test_switched_on_lists_the_fix_and_the_asked_files():
    r = R.judge(ISSUE, [BUMP, SCRIPT, CODE])
    assert r["switched_on"] and r["fix_files"] == ["Dockerfile"]
    assert r["asked_files"] == ["docker/install-ext.sh", "src/app.php"]


def test_the_sentence_follows_the_rubric():
    on = dict(R.judge(ISSUE, [BUMP, SCRIPT]), url="u")
    off = dict(R.judge(ISSUE, [CODE]), url="v")
    s = R.summarise([on, off, dict(off)], RUBRIC)
    assert s["switched_on"] == 1 and s["asked_files"] == 1 and s["why_not"] == {"no_version_only_file": 2}
    assert s["sentence"].startswith("Patch-day mode switched on for 1 of 3")
    none = R.summarise([off], RUBRIC)
    assert none["sentence"].startswith("Patch-day mode switched on for none of 1") and "no version only file" in none["sentence"]
