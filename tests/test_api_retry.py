"""One slow or busy GitLab read must not fail the whole job (it did, twice, on 2026-10-17: closes_issues timed out)."""
import json

import pytest

from itemator import ci


class Script:
    """An http callable that plays a list of outcomes: an int status (body {}), a (status, body) pair or an exception."""
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def __call__(self, url, headers):
        self.calls.append(dict(headers))
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return (o, b"{}") if isinstance(o, int) else (o[0], json.dumps(o[1]).encode())


@pytest.fixture
def waits(monkeypatch):
    slept = []
    monkeypatch.setattr(ci.time, "sleep", slept.append)
    return slept


def api(http, token=None):
    return ci.Api("https://x/api/v4", token, http)


def test_a_timeout_twice_then_success_returns_the_answer(waits):
    http = Script(ci.JobError("timed out"), ci.JobError("timed out"), (200, [1]))
    assert api(http).get("/p") == [1] and len(http.calls) == 3 and waits == [3, 10]


def test_a_timeout_every_time_still_fails_after_three_tries(waits):
    http = Script(ci.JobError("a"), ci.JobError("b"), ci.JobError("c"))
    with pytest.raises(ci.JobError, match="c"):
        api(http).get("/p")
    assert len(http.calls) == 3 and waits == [3, 10]


def test_a_busy_server_is_tried_again(waits):
    http = Script(503, 502, (200, {"ok": True}))
    assert api(http).get("/p") == {"ok": True} and waits == [3, 10]


def test_a_server_busy_every_time_reports_the_status(waits):
    http = Script(503, 503, 503)
    with pytest.raises(ci.JobError, match="HTTP 503"):
        api(http).get("/p")
    assert len(http.calls) == 3


def test_an_answer_that_is_final_is_not_retried(waits):
    http = Script(404)
    with pytest.raises(ci.JobError, match="HTTP 404"):
        api(http).get("/p")
    assert len(http.calls) == 1 and waits == []
    assert api(Script(404)).get("/p", missing_ok=True) is None


def test_the_job_token_goes_first_and_a_refusal_falls_back_to_anonymous_with_its_own_tries(waits):
    http = Script(ci.JobError("blip"), 403, ci.JobError("blip"), (200, {"a": 1}))
    assert api(http, token="T").get("/p") == {"a": 1}
    assert [c.get("JOB-TOKEN") for c in http.calls] == ["T", "T", None, None]
