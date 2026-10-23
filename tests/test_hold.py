"""T44: `names.hold_until_named`. The job fails while a kept extra has no name, and passes when the reaction account has
posted its summary for this exact head commit. A real git repository in tmp, a fake GitLab API, no network."""
import json

import pytest

from itemator import ci
from itemator import replycheck
from test_ci import FIXED, MR, FakeHttp, isolated, issue, job, mr, repo, routes  # noqa: F401  (fixtures)

NOTES = "/projects/7/merge_requests/5/notes?per_page=100&page={}&sort=desc"
REACT = "ai-itemator-react-gitlab-ai-hackathon"
DISC = "/projects/7/merge_requests/5/discussions?per_page=100&page=1"
CARD_Q = "`.gitlab-ci.yml` is beyond the issue. To keep it, reply with its exact name."


def thread(*replies):
    first = {"id": 1, "author": {"id": 100, "username": replycheck.CARD_BOT}, "body": CARD_Q, "system": False,
             "created_at": "2026-10-24T01:00:00Z"}
    rs = [{"id": 2 + i, "author": {"id": 2, "username": "ann"}, "body": b, "system": False,
           "created_at": f"2026-10-24T01:0{i + 1}:00Z"} for i, b in enumerate(replies)]
    return {"id": "t1", "notes": [first, *rs]}


ANSWERED = (200, [thread(".gitlab-ci.yml")])
HOLD = "[names]\nhold_until_named = true\n"


def summary(head, user=REACT, system=False):
    return {"body": f"Every extra has an answer: 1 kept.\n\n[//]: # (itemator:named={head})", "author": {"username": user},
            "system": system}


def setup(repo, policy=HOLD):
    if policy is not None:
        repo.base = repo.commit({".itemator.toml": policy}, "target branch")
    return repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": "test:\n  script: [pytest, ruff]\n"})


def run(repo, head, tmp_path, monkeypatch, notes=None, pages=None, discussions=ANSWERED, **kw):
    r = routes(dict(mr(), author={"id": 2, "username": "ann"}), [issue()])
    r["/users/2"] = (200, {"id": 2, "bot": False})
    if discussions is not None:
        r[DISC] = discussions
    if notes is not None:
        r[NOTES.format(1)] = notes
    for n, got in (pages or {}).items():
        r[NOTES.format(n)] = got
    http = FakeHttp(r)
    code, out = job(repo, head, http, tmp_path, monkeypatch, **kw)
    return code, out, http


def test_an_unnamed_extra_fails_the_job_and_says_what_to_do(repo, tmp_path, monkeypatch, capsys):
    head = setup(repo)
    code, out, _ = run(repo, head, tmp_path, monkeypatch, notes=(200, []))
    assert code == 1 and out["state"] == "extras"          # the artifact is written, so the card can still be posted
    assert out["hold"] == {"enabled": True, "blocked": True, "reason": "no summary note for this commit yet"}
    assert out["card"]["todo_line"].endswith(ci.HOLD_LINE) and out["extras"]
    assert "held: 1 extra is not named yet" in capsys.readouterr().err


def test_the_summary_for_this_commit_releases_the_hold(repo, tmp_path, monkeypatch):
    head = setup(repo)
    code, out, _ = run(repo, head, tmp_path, monkeypatch, notes=(200, [summary(head)]))
    assert code == 0 and out["hold"] == {"enabled": True, "blocked": False, "reason": None}
    assert ci.HOLD_LINE not in out["card"]["todo_line"]


@pytest.mark.parametrize("note", [
    lambda head: summary(head, user="mallory"),                       # anyone can type the marker
    lambda head: summary(head, user=REACT + "-2"),                    # a name that only starts like the reaction account (audit pass 3)
    lambda head: summary(head, user="ai-itemator-react"),
    lambda head: summary(head, user="ai-itemator-card-gitlab-ai-hackathon"),
    lambda head: summary(head, system=True),
    lambda head: summary("b" * 40),                                   # a summary for another commit
    lambda head: {"body": "itemator:named=" + head, "author": None, "system": False},
])
def test_only_the_reaction_accounts_summary_for_this_commit_counts(repo, tmp_path, monkeypatch, note):
    head = setup(repo)
    code, out, _ = run(repo, head, tmp_path, monkeypatch, notes=(200, [note(head)]))
    assert code == 1 and out["hold"]["blocked"] is True


def test_unreadable_notes_fail_closed(repo, tmp_path, monkeypatch):
    head = setup(repo)
    for got in ((500, {"message": "x"}), (200, {"not": "a list"})):
        code, out, _ = run(repo, head, tmp_path, monkeypatch, notes=got)
        assert code == 1 and out["hold"] == {"enabled": True, "blocked": True, "reason": "the notes could not be read"}


def test_the_summary_may_be_on_a_later_page(repo, tmp_path, monkeypatch):
    head = setup(repo)
    filler = [{"body": "x", "author": {"username": "bob"}, "system": False}] * 100
    code, out, http = run(repo, head, tmp_path, monkeypatch, notes=(200, filler), pages={2: (200, [summary(head)])})
    assert code == 0 and out["hold"]["blocked"] is False
    assert [c for c, _ in http.calls if "page=2" in c]


def test_no_extras_means_nothing_to_hold(repo, tmp_path, monkeypatch):
    repo.base = repo.commit({".itemator.toml": HOLD}, "target branch")
    head = repo.commit({"src/parser.py": FIXED})
    code, out, http = run(repo, head, tmp_path, monkeypatch)
    assert code == 0 and out["state"] == "inside_ask" and out["hold"] == {"enabled": True, "blocked": False}
    assert not [c for c, _ in http.calls if "/notes" in c]            # nothing to look up


@pytest.mark.parametrize("policy", [None, "[names]\nhold_until_named = false\n", "[names]\nother_person_required = true\n"])
def test_without_the_setting_nothing_changes(repo, tmp_path, monkeypatch, policy):
    head = setup(repo, policy)
    code, out, http = run(repo, head, tmp_path, monkeypatch)
    assert code == 0 and out["state"] == "extras" and out["hold"]["blocked"] is False
    assert not [c for c, _ in http.calls if "/notes" in c]


def test_a_policy_that_is_ignored_does_not_hold(repo, tmp_path, monkeypatch):
    head = setup(repo, "[names]\nhold_until_named = true\nunknown = 1\n")
    code, out, _ = run(repo, head, tmp_path, monkeypatch)
    assert code == 0 and out["policy"]["ignored"] and out["hold"]["enabled"] is False


def test_the_setting_must_be_true_or_false(repo, tmp_path, monkeypatch):
    head = setup(repo, '[names]\nhold_until_named = "yes"\n')
    code, out, _ = run(repo, head, tmp_path, monkeypatch)
    assert code == 0 and out["policy"]["ignored"] == "names.hold_until_named must be true or false"


def test_the_setting_is_read_from_the_target_not_the_merge_request(repo, tmp_path, monkeypatch):
    repo.base = repo.commit({".itemator.toml": "[names]\nother_person_required = false\n"}, "target branch")
    head = repo.commit({".itemator.toml": HOLD, ".gitlab-ci.yml": "test:\n  script: [pytest, ruff]\n"})
    code, out, _ = run(repo, head, tmp_path, monkeypatch)
    assert out["hold"]["enabled"] is False and code == 0


@pytest.mark.parametrize("discussions, why", [
    ((200, [thread()]), "no answer the tests accept for: .gitlab-ci.yml"),          # the thread was resolved by hand
    ((200, [thread("keep it please")]), "no answer the tests accept for: .gitlab-ci.yml"),
    ((200, []), "no extra thread found to check"),
])
def test_the_summary_alone_does_not_release_the_hold_code_rechecks_the_answers(repo, tmp_path, monkeypatch, discussions, why):
    head = setup(repo)
    code, out, _ = run(repo, head, tmp_path, monkeypatch, notes=(200, [summary(head)]), discussions=discussions)
    assert code == 1 and out["hold"] == {"enabled": True, "blocked": True, "reason": why}


def test_a_bot_reply_is_not_an_answer(repo, tmp_path, monkeypatch):
    head = setup(repo)
    d = thread(".gitlab-ci.yml")
    d["notes"][1]["author"] = {"id": 9, "username": "helper-bot"}
    code, out, _ = run(repo, head, tmp_path, monkeypatch, notes=(200, [summary(head)]), discussions=(200, [d]))
    assert code == 1 and out["hold"]["blocked"] is True


@pytest.mark.parametrize("discussions", [(500, {"message": "x"}), (403, {"message": "403 Forbidden"}), (200, {"not": "a list"}), None])
def test_threads_the_token_cannot_read_leave_the_summary_rule_and_say_so(repo, tmp_path, monkeypatch, discussions):
    head = setup(repo)
    code, out, _ = run(repo, head, tmp_path, monkeypatch, notes=(200, [summary(head)]), discussions=discussions)
    assert code == 0 and out["hold"] == {"enabled": True, "blocked": False, "reason": None, "checked": False}
