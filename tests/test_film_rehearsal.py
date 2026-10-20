"""The film's safety parts: a trigger switch is read back (eval/react_study.trigger), and `rehearse` checks each step with reads
only (eval/film_real_agent.py). No network: GitLab is faked."""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import film_real_agent as F  # noqa: E402
import react_study as R  # noqa: E402

CARD, REACT = R.TRIG["card"], R.TRIG["react"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(R.subprocess, "run", lambda *a, **k: type("Done", (), {"stdout": "{}", "returncode": 0})())
    monkeypatch.setattr(R.time, "sleep", lambda s: None)


def test_a_switch_that_took_returns():
    R.trigger("card", True, states=lambda: {CARD: True})


def test_a_switch_that_did_not_take_raises():
    with pytest.raises(RuntimeError, match="did not switch off"):
        R.trigger("card", False, states=lambda: {CARD: True})


def test_a_trigger_that_is_missing_raises():
    with pytest.raises(RuntimeError, match="did not switch on"):
        R.trigger("react", True, states=lambda: {})


def test_a_slow_switch_is_waited_for():
    seen = iter([{CARD: False}, {CARD: True}])
    R.trigger("card", True, states=lambda: next(seen))


def fake_gitlab(monkeypatch, *, meter=300.0, states=None, members=("dev", "card", "react"), card_name="ai-itemator-card-x"):
    ids = {F.DEVELOPER: "dev", R.REACT_MENTION.lstrip("@"): "react"}
    writes = []

    def api(path, method="GET", **fields):
        if method != "GET":
            writes.append(path)
            return {}
        if path.startswith("users?username="):
            u = path.split("=", 1)[1]
            return [{"id": ids[u]}] if u in ids else []
        if path == f"users/{R.CARD_USER}":
            return {"username": card_name}
        if "/members/all/" in path:
            who = "card" if path.endswith(str(R.CARD_USER)) else path.rsplit("/", 1)[1]
            if who in members:
                return {"id": who}
            raise RuntimeError("404")
        raise AssertionError(path)

    monkeypatch.setattr(R, "api", api)
    monkeypatch.setattr(R, "meter", lambda: meter)
    monkeypatch.setattr(R, "trigger_states", lambda: {CARD: False, REACT: False} if states is None else states)
    monkeypatch.setattr(R, "trigger", lambda *a, **k: writes.append("trigger"))
    return writes


@pytest.fixture
def rubric(tmp_path):
    p = tmp_path / "rubric.json"
    p.write_text(json.dumps({"issues": [{"id": 1, "title": "T", "description": "D"}]}))
    return p


def test_a_clean_rehearsal_passes_and_writes_nothing(monkeypatch, rubric, capsys):
    writes = fake_gitlab(monkeypatch)
    assert F.rehearse(1, 360, rubric) == 0
    out = capsys.readouterr().out
    assert writes == [] and "FAIL" not in out and "plan  POST projects/" in out and "every check passed" in out


@pytest.mark.parametrize("kw, line", [
    ({"meter": 360.0}, "under the credit stop"),
    ({"meter": None}, "under the credit stop"),
    ({"states": {CARD: True, REACT: False}}, "card trigger exists and is off"),
    ({"states": {CARD: False}}, "react trigger exists and is off"),
    ({"members": ("card", "react")}, f"@{F.DEVELOPER} exists and is a member"),
    ({"members": ("dev", "card")}, "reaction flow's account"),
    ({"members": ("dev", "react")}, "is the card account"),
    ({"card_name": "someone-else"}, "is the card account"),
])
def test_each_missing_factor_fails_the_rehearsal(monkeypatch, rubric, capsys, kw, line):
    writes = fake_gitlab(monkeypatch, **kw)
    assert F.rehearse(1, 360, rubric) == 1
    fails = [l for l in capsys.readouterr().out.splitlines() if l.startswith("FAIL")]
    assert len(fails) == 1 and line in fails[0] and writes == []


def test_an_issue_not_in_the_rubric_fails(monkeypatch, rubric, capsys):
    fake_gitlab(monkeypatch)
    assert F.rehearse(2, 360, rubric) == 1
    assert "plan" not in capsys.readouterr().out
