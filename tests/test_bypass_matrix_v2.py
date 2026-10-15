"""The v2 bypass matrix: the cases file was written before the run, and every scenario in it has the edit it names."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import bypass_matrix_v2 as M  # noqa: E402

CASES = json.loads((ROOT / "eval" / "bypass_matrix_v2_cases.json").read_text())["scenarios"]
CI, README, JOB, CHECKER = "unit-tests:\n  script: [pytest]\n", "# r\n", "itemator:\n  script: [x]\n", "def main():\n    pass\n"


def edit(name):
    return M.edits(name, CI, README, JOB, CHECKER)


def test_ids_are_unique_and_all_attempts_are_expected_to_be_blocked():
    assert [s["id"] for s in CASES] == list(range(1, len(CASES) + 1))
    assert {s["expected"] for s in CASES} == {"blocked"}


def test_every_scenario_edits_the_project_ci_file_or_the_files_it_names():
    for s in CASES:
        assert ".gitlab-ci.yml" in edit(s["name"]), s["name"]


def test_the_scenarios_change_what_they_say():
    assert edit("project jobs deleted")[".gitlab-ci.yml"] == 'noop:\n  script: ["true"]\n'
    assert "itemator:\n  allow_failure: true" in edit("fake itemator allowed to fail")[".gitlab-ci.yml"]
    assert "\nitemator:\n  script: [\"true\"]" in edit("fake itemator passes")[".gitlab-ci.yml"]
    assert edit("workflow never")[".gitlab-ci.yml"].startswith("workflow:\n  rules:\n    - when: never\n")
    assert edit("job file edited")["ci/itemator-job.yml"] == M.JOB_FILE_NOOP
    assert edit("checker edited")["itemator/ci.py"].startswith("import sys\nsys.exit(0)\n") and CHECKER in edit("checker edited")["itemator/ci.py"]
    assert f"ITEMATOR_REACT_BOT: {M.OWNER}" in edit("bot variable overridden")[".gitlab-ci.yml"]
    assert set(edit("plain")) == {".gitlab-ci.yml"} and edit("plain")[".gitlab-ci.yml"].endswith(CI)


def test_the_cases_file_names_every_scenario_the_runner_handles():
    names = {s["name"] for s in CASES}
    assert {"plain", "ci skip", "retry without names", "forged summary", "bot variable overridden", "job file edited", "checker edited",
            "workflow never", "project jobs deleted", "fake itemator allowed to fail", "fake itemator passes"} == names
