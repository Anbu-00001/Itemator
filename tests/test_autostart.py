from datetime import datetime, timezone

from itemator import autostart as A

BEFORE = datetime(2026, 10, 24, tzinfo=timezone.utc)
ENV = {"CI_PIPELINE_SOURCE": "merge_request_event", "CI_MERGE_REQUEST_IID": "7", "CI_PROJECT_ID": "87943563",
       "CI_MERGE_REQUEST_SOURCE_BRANCH_NAME": "duo/feature/7-slug-tests", "ITEMATOR_CARD_CONSUMER_ID": "12955856",
       "ITEMATOR_START_TOKEN": "t"}


def test_starts_only_on_an_agent_branch_with_its_settings():
    assert A.should_start(ENV, BEFORE) == (True, "agent merge request")
    for key, value in [("CI_MERGE_REQUEST_SOURCE_BRANCH_NAME", "fix/slug"), ("CI_PIPELINE_SOURCE", "push"),
                       ("ITEMATOR_CARD_CONSUMER_ID", ""), ("ITEMATOR_START_TOKEN", ""), ("ITEMATOR_AUTOSTART", "Off")]:
        assert A.should_start(dict(ENV, **{key: value}), BEFORE)[0] is False, key


def test_never_starts_at_or_after_the_deadline():
    assert A.should_start(ENV, A.DEADLINE) == (False, "the hackathon deadline has passed")
    assert A.should_start(ENV, datetime(2026, 10, 27, 12, 59, tzinfo=timezone.utc))[0] is True


def test_payload_names_the_card_and_the_merge_request():
    assert A.payload(ENV) == {"project_id": 87943563, "ai_catalog_item_consumer_id": 12955856, "merge_request_id": 7,
                              "goal": "7", "start_workflow": True, "environment": "ambient"}


def test_a_failed_session_is_restarted_once():
    assert A.next_step("RUNNING", False) == "wait" and A.next_step(None, False) == "wait"
    assert A.next_step("FAILED", False) == "restart"
    assert A.next_step("FAILED", True) == "give_up"
    assert A.next_step("FINISHED", True) == "done" and A.next_step("STOPPED", False) == "done"


def test_main_restarts_a_dropped_session_and_stops_when_it_ends(monkeypatch):
    calls, statuses = [], iter(["FAILED", "RUNNING", "FINISHED"])
    monkeypatch.setattr(A, "_call", lambda url, token, body=None: calls.append(url) or {"id": 100 + len(calls)})
    monkeypatch.setattr(A, "_status", lambda api, token, path, wid: next(statuses))
    env = dict(ENV, CI_API_V4_URL="https://gitlab.com/api/v4", CI_PROJECT_PATH="g/p")
    assert A.main(env, BEFORE, sleep=lambda s: None) == 0
    assert calls == ["https://gitlab.com/api/v4/ai/duo_workflows/workflows", "https://gitlab.com/api/v4/ai/duo_workflows/workflows/101/restart"]


def test_main_does_nothing_when_it_should_not_start(monkeypatch, capsys):
    monkeypatch.setattr(A, "_call", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
    assert A.main(dict(ENV, ITEMATOR_START_TOKEN=""), BEFORE) == 0
    assert "not starting: ITEMATOR_START_TOKEN is not set" in capsys.readouterr().out
