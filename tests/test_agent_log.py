"""eval/agent_log.py: the answer-log experiment's harness, run on hand-made edits (no agent)."""
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agent_log", ROOT / "eval" / "agent_log.py")
AL = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AL)


@pytest.fixture
def runs(tmp_path, monkeypatch):
    monkeypatch.setattr(AL, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(AL, "RESULTS", tmp_path)
    return tmp_path / "root"


def edit(d, path, text, append=False):
    p = d / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text((p.read_text() if append and p.exists() else "") + text)


def test_every_test_issue_has_a_check_that_fails_on_the_untouched_fixture():
    tests = [i for i in AL.issues().values() if i["phase"] == "test"]
    assert len(tests) == 20 and all(i["check"] for i in tests)
    for i in tests:
        d = AL.HERE / "fixtures" / i["repo"]
        assert AL.run_check(d, i["check"])["result"] == "fail", i["id"]


def test_the_registered_files_are_the_ones_on_disk():
    AL.unchanged()


def test_history_extras_become_remove_answers_and_a_test_run_that_adds_one_again_is_counted(runs):
    d = AL.prepare(runs, "textkit-h1", "history")
    edit(d, "requirements.txt", "Unidecode==1.3.8\n", append=True)
    edit(d, "NOTES.md", "notes\n")
    row = AL.score(runs, "textkit-h1", "history")
    assert {e["name"] for e in row["extras"]} == {"Unidecode", "NOTES.md"} and row["recurred"] == []
    for n in range(2, 6):
        AL.prepare(runs, f"textkit-h{n}", "history")
        AL.score(runs, f"textkit-h{n}", "history")
    log = AL.build_log(runs, "textkit")
    assert [(e["iid"], [i["name"] for i in e["items"]]) for e in log["entries"]] == [(1, ["Unidecode", "NOTES.md"])]
    assert all(i["decision"] == "remove" for e in log["entries"] for i in e["items"])
    w = AL.prepare(runs, "textkit-t1", "with")
    assert json.loads((w / AL.LOG_PATH).read_text()) == log
    edit(w, "requirements.txt", "unidecode\n", append=True)                 # PyPI names ignore case
    assert AL.score(runs, "textkit-t1", "with")["recurred"] == ["unidecode"]
    wo = AL.prepare(runs, "textkit-t1", "without")
    assert not (wo / AL.LOG_PATH).exists()
    edit(wo, "requirements.txt", "requests\n", append=True)
    row = AL.score(runs, "textkit-t1", "without")
    assert row["recurred"] == [] and [e["name"] for e in row["extras"]] == ["requests"]
    assert (AL.RUNS / "textkit-t1-without.json").exists() and "+requests" in row["diff"]


def test_a_run_is_never_prepared_twice_and_the_with_arm_needs_the_log(runs):
    AL.prepare(runs, "textkit-t2", "without")
    with pytest.raises(SystemExit):
        AL.prepare(runs, "textkit-t2", "without")
    with pytest.raises(SystemExit, match="no answer log"):
        AL.prepare(runs, "textkit-t2", "with")
    with pytest.raises(SystemExit):
        AL.prepare(runs, "textkit-h1", "with")                              # a history issue has no test arm


def test_a_change_that_needs_an_uninstalled_package_is_not_called_a_failure(runs):
    d = AL.prepare(runs, "textkit-t1", "without")
    edit(d, "textkit/core.py", "import zz_not_installed_pkg\n" + (d / "textkit/core.py").read_text())
    assert AL.score(runs, "textkit-t1", "without")["check"]["result"] == "needs_package"


def test_a_solved_issue_passes_its_check(runs):
    d = AL.prepare(runs, "textkit-t8", "without")
    core = (d / "textkit/core.py").read_text().replace('def slug(text: str) -> str:', 'def slug(text: str, sep: str = "-") -> str:')
    edit(d, "textkit/core.py", core.replace('return "-".join(words).lower()', 'return sep.join(words).lower()'))
    assert AL.score(runs, "textkit-t8", "without")["check"]["result"] == "pass"


def rows(tmp, with_rec, without_rec, n=20):
    AL.RUNS.mkdir(parents=True, exist_ok=True)
    for k in range(n):
        for arm, rec in (("with", with_rec), ("without", without_rec)):
            r = {"issue": f"x-t{k}", "repo": "x", "phase": "test", "arm": arm, "extras": [], "recurred": ["p"] if k < rec else [],
                 "check": {"result": "pass"}}
            (AL.RUNS / f"x-t{k}-{arm}.json").write_text(json.dumps(r))


@pytest.mark.parametrize("w, wo, n, want", [(2, 6, 20, "holds"), (3, 6, 20, "holds"), (4, 6, 20, "does_not_hold"),
                                             (0, 4, 20, "too_few_to_tell"), (0, 9, 19, "incomplete")])
def test_the_result_follows_the_registered_rule(runs, w, wo, n, want):
    rows(runs, w, wo, n)
    assert AL.summary()["result"] == want


def test_the_prompt_is_the_same_in_both_arms_and_only_asks_the_agent_to_read_the_log():
    p = (AL.HERE / "prompt.md").read_text()
    assert ".itemator/answers.json" in p and "if it exists" in p
    for word in ("remove", "do not add", "avoid", "extra"):
        assert word not in p.lower(), word                                    # it says what the file is, not what to do with it


def test_the_skill_tells_an_agent_to_read_the_answer_log_before_writing():
    s = (ROOT / "skills/stay-inside-the-issue/SKILL.md").read_text()
    assert s.index("## Before you write") < s.index("## Before you finish")
    assert "answers/answers.json" in s and "answered `remove` or `split`" in s


def test_the_harness_runs_from_the_command_line(runs):
    r = subprocess.run([sys.executable, str(ROOT / "eval" / "agent_log.py"), "prepare", "fetchit-t3", "without", "--root", str(runs)],
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip().endswith("fetchit-t3-without/repo")


def test_a_changed_or_extra_fixture_file_stops_every_run(tmp_path, monkeypatch):
    import shutil
    shutil.copytree(AL.HERE, tmp_path / "eval" / "agent_log")
    shutil.copy(ROOT / "eval" / "agent_log_rubric.json", tmp_path / "eval" / "agent_log_rubric.json")
    monkeypatch.setattr(AL, "ROOT", tmp_path)
    monkeypatch.setattr(AL, "HERE", tmp_path / "eval" / "agent_log")
    AL.unchanged()
    core = tmp_path / "eval/agent_log/fixtures/textkit/textkit/core.py"
    core.write_text(core.read_text() + "\n# hint\n")
    with pytest.raises(SystemExit, match="not the registered version"):
        AL.unchanged()
    core.write_text(core.read_text().replace("\n# hint\n", ""))
    AL.unchanged()
    (tmp_path / "eval/agent_log/fixtures/textkit/HINT.md").write_text("x")
    with pytest.raises(SystemExit, match="differ from the registered list"):
        AL.unchanged()
    with pytest.raises(SystemExit, match="differ from the registered list"):
        AL.prepare(tmp_path / "root", "textkit-t1", "without")             # prepare checks before it copies
    assert not (tmp_path / "root").exists() or not any((tmp_path / "root").iterdir())
