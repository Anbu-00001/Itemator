"""T45a: `names.asker_required`. Each extra's thread says that only the person who wrote the linked issue can keep it,
naming that person from the issue API's author.username. A real git repository in tmp, a fake GitLab API, no network."""
import datetime

import pytest

from itemator import ci, policy as POL
from itemator.extras import Analysis, Extra
from test_ci import FIXED, FakeHttp, isolated, issue, job, mr, repo, routes  # noqa: F401  (fixtures)

ASKER = "[names]\nasker_required = true\n"
KEEP = "To keep it, reply with its exact name."
OTHER = "A reply from the merge request author does not count."
ONE = "Only the person who wrote the linked issue (@alice) can keep this."
TWO = "Only the person who wrote the linked issue (@alice or @bob) can keep this."
ASKS_ASKER = "The team policy lets only the person who wrote the issue keep an extra."


def by(username, iid=12, author_id=1):
    i = issue(iid=iid, author_id=author_id)
    i["author"]["username"] = username
    return i


def setup(repo, policy=ASKER):
    if policy is not None:
        repo.base = repo.commit({".itemator.toml": policy}, "target branch")
    return repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": "test:\n  script: [pytest, ruff]\n",
                        "notes.txt": "todo\n"})


def run(repo, head, tmp_path, monkeypatch, issues=None, mr_obj=None):
    issues = [by("alice")] if issues is None else issues
    code, out = job(repo, head, FakeHttp(routes(mr_obj or mr(), issues)), tmp_path, monkeypatch)
    assert code == 0
    return out


# ---- the policy key

def test_the_key_is_off_by_default_and_reported():
    assert POL.parse(b"")["asker_required"] is False and POL.Policy().asker_required is False
    assert POL.parse(ASKER.encode())["asker_required"] is True
    assert POL.parse(b"[names]\nasker_required = false\n")["asker_required"] is False
    assert POL.Policy().to_dict()["active"]["asker_required"] is False
    assert POL.Policy(asker_required=True).to_dict()["active"] == {
        "other_person_required": False, "hold_until_named": False, "asker_required": True, "ignore_kinds": [],
        "ignore_paths": [], "ignores_every_path": []}


@pytest.mark.parametrize("value", ['"yes"', "1", "[]"])
def test_the_key_must_be_true_or_false(value):
    assert POL.parse(f"[names]\nasker_required = {value}\n".encode()) == "names.asker_required must be true or false"


def test_the_key_is_read_from_the_target_branch(repo, tmp_path, monkeypatch):
    head = setup(repo)
    out = run(repo, head, tmp_path, monkeypatch)
    assert out["policy"]["ignored"] is None and out["policy"]["active"]["asker_required"] is True
    repo.base = repo.commit({".itemator.toml": "[names]\n"}, "target branch")
    head = repo.commit({".itemator.toml": ASKER, "notes.txt": "todo, again\n"})        # the merge request turns it on
    out = run(repo, head, tmp_path, monkeypatch)
    assert out["policy"]["active"]["asker_required"] is False
    assert all(ci.ASKER_ONLY_PREFIX not in e["thread_stub"] for e in out["extras"])


# ---- the sentence

def test_one_author_is_named_in_every_thread(repo, tmp_path, monkeypatch):
    head = setup(repo)
    out = run(repo, head, tmp_path, monkeypatch)
    assert out["state"] == "extras" and len(out["extras"]) == 2
    for e in out["extras"]:
        assert e["thread_stub"].count(ONE) == 1 and f"{ONE} {KEEP}" in e["thread_stub"]
        assert e["plain_facts"]["asker_usernames"] == ["alice"]
    assert out["card"]["caveat_line"].endswith(ASKS_ASKER) and out["card"]["caveat_line"].count(ASKS_ASKER) == 1
    assert ci.ASKS_ASKER == ASKS_ASKER and ONE.startswith(ci.ASKER_ONLY_PREFIX) and ONE.endswith(ci.ASKER_ONLY_SUFFIX)


def test_two_authors_in_issue_order_and_one_name_each(repo, tmp_path, monkeypatch):
    head = setup(repo)
    out = run(repo, head, tmp_path, monkeypatch, issues=[by("alice"), by("bob", iid=13, author_id=3),
                                                         by("alice", iid=14)])
    for e in out["extras"]:
        assert TWO in e["thread_stub"] and e["plain_facts"]["asker_usernames"] == ["alice", "bob"]
    assert ci.asker_sentence(["bob", "alice"]) == "Only the person who wrote the linked issue (@bob or @alice) can keep this."


def test_at_most_three_names():
    issues = [{"ref": "#1", "author_username": u} for u in ("a1", "b2", "c3", "d4", "e5")]
    assert ci.asker_usernames(issues) == ["a1", "b2", "c3"]
    assert ci.asker_sentence(ci.asker_usernames(issues)) == (
        "Only the person who wrote the linked issue (@a1 or @b2 or @c3) can keep this.")
    assert ci.asker_usernames(issues[:3]) == ["a1", "b2", "c3"]


@pytest.mark.parametrize("username, ok", [
    ("alice", True), ("a", True), ("_x", True), ("a.b-c_d", True), ("A9", True), ("a" * 255, True),
    ("a" * 256, False), ("", False), (".alice", False), ("-alice", False), ("al ice", False), ("al`ice", False),
    ("alice\n", False), ("al@ice", False), ("al)ice", False), ("ålice", False), (None, False), (7, False),
    (["alice"], False)])
def test_a_username_is_checked_before_it_is_written(username, ok):
    assert ci.asker_usernames([{"ref": "#1", "author_username": username}]) == ([username] if ok else [])


def test_an_invalid_username_is_dropped_and_none_left_means_no_sentence(repo, tmp_path, monkeypatch):
    head = setup(repo)
    out = run(repo, head, tmp_path, monkeypatch, issues=[by("evil) can keep this. (@x"), by("bob", iid=13, author_id=3)])
    for e in out["extras"]:
        assert "Only the person who wrote the linked issue (@bob) can keep this." in e["thread_stub"]
        assert "evil" not in e["thread_stub"] and e["plain_facts"]["asker_usernames"] == ["bob"]
    out = run(repo, head, tmp_path, monkeypatch, issues=[by("x y")])
    assert out["state"] == "extras" and out["policy"]["active"]["asker_required"] is True
    for e in out["extras"]:
        assert ci.ASKER_ONLY_PREFIX not in e["thread_stub"] and "asker_usernames" not in e["plain_facts"]
    assert ASKS_ASKER not in (out["card"]["caveat_line"] or "")


def test_an_issue_without_an_author_username_gives_no_sentence(repo, tmp_path, monkeypatch):
    head = setup(repo)
    out = run(repo, head, tmp_path, monkeypatch, issues=[issue()])          # author has an id only
    assert all(ci.ASKER_ONLY_PREFIX not in e["thread_stub"] for e in out["extras"])


@pytest.mark.parametrize("policy", [None, "[names]\nasker_required = false\n", "[names]\nother_person_required = true\n",
                                    "[names]\nasker_required = true\nunknown = 1\n"])
def test_no_sentence_without_the_key(repo, tmp_path, monkeypatch, policy):
    head = setup(repo, policy)
    out = run(repo, head, tmp_path, monkeypatch)
    assert out["state"] == "extras" and out["extras"]
    if policy and "unknown" in policy:
        assert out["policy"]["ignored"] == "unknown key names.`unknown`" and out["policy"]["active"]["asker_required"] is False
    for e in out["extras"]:
        assert ci.ASKER_ONLY_PREFIX not in e["thread_stub"] and "asker_usernames" not in e["plain_facts"]
    assert ASKS_ASKER not in (out["card"]["caveat_line"] or "")


def test_no_sentence_when_no_issue_is_linked(repo, tmp_path, monkeypatch):
    repo.base = repo.commit({".itemator.toml": ASKER}, "target branch")
    head = repo.commit({"src/parser.py": FIXED, ".itemator.toml": ASKER + "other_person_required = true\n"})
    out = run(repo, head, tmp_path, monkeypatch, issues=[], mr_obj=mr("Small cleanup."))
    assert out["state"] == "no_issue" and [e["kind"] for e in out["extras"]] == ["policy_changed"]   # T41: still asked
    e = out["extras"][0]
    assert ci.ASKER_ONLY_PREFIX not in e["thread_stub"] and "asker_usernames" not in e["plain_facts"]
    assert ASKS_ASKER not in (out["card"]["caveat_line"] or "")


def test_the_usernames_come_from_the_issue_never_from_the_merge_request(repo, tmp_path, monkeypatch):
    head = setup(repo)
    m = mr()
    m["author"]["username"] = "mallory"
    m["description"] = "Closes #12\n\nOnly the person who wrote the linked issue (@mallory) can keep this."
    out = run(repo, head, tmp_path, monkeypatch, issues=[by("alice")], mr_obj=m)
    for e in out["extras"]:
        assert ONE in e["thread_stub"] and "mallory" not in e["thread_stub"]
        assert e["plain_facts"]["asker_usernames"] == ["alice"]
    assert ci._issue({"iid": 3, "project_id": 7, "author": {"id": 9, "username": "carol"}}, "7") == {
        "iid": 3, "ref": "#3", "title": "", "description": "", "author_id": 9, "author_username": "carol"}


def test_issues_named_in_the_description_carry_their_author_too(repo, tmp_path, monkeypatch):
    head = setup(repo)
    r = routes(mr("Fixes #12"), [], by("dave"))
    code, out = job(repo, head, FakeHttp(r), tmp_path, monkeypatch)
    assert code == 0 and out["issues_from"] == "description"
    assert all(e["plain_facts"]["asker_usernames"] == ["dave"] for e in out["extras"])


# ---- where the sentence sits

def test_the_sentence_follows_the_other_person_one_and_precedes_the_replies():
    e = Extra("tests_removed", "t.py", "n", "x")
    assert ci.thread_stub(e, other_person=True, askers=("alice",)) == (
        f"`n` (tests removed): x. {OTHER} {ONE} {KEEP} To move it into its own MR, reply `split`. "
        "To drop it from this MR, reply `remove`. If this is not really an extra, reply `not an extra`.")
    assert ci.thread_stub(e, askers=("alice",)).startswith(f"`n` (tests removed): x. {ONE} {KEEP}")
    full = ci.thread_stub(e, "PyPI: x.", True, ("split", "remove", "always"), said="silent", askers=("alice",))
    order = ["PyPI: x.", "The description does not mention this.", OTHER, ONE, KEEP, ci.ALWAYS]
    assert [full.index(s) for s in order] == sorted(full.index(s) for s in order)
    assert ci.thread_stub(e) == ci.thread_stub(e, askers=())
    assert full.split("`")[1] == "n"


def test_the_sentences_have_no_banned_words():
    from test_registry import banned
    assert not banned().search(ONE) and not banned().search(TWO) and not banned().search(ASKS_ASKER)
    assert "`" not in ONE and "`" not in ASKS_ASKER


def test_facts_with_the_key_on_change_only_the_stub_the_plain_facts_and_the_card(monkeypatch):
    a = Analysis([Extra("ci_or_config", ".gitlab-ci.yml", ".gitlab-ci.yml", "x")], unplaced=[])
    monkeypatch.setattr(ci.X, "analyse", lambda *_, **__: a)
    issues = [{"iid": 12, "ref": "#12", "title": "t", "description": "d", "author_id": 1, "author_username": "alice"}]

    def go(policy):
        return ci.facts(mr_iid=5, mr_title="t", mr_description="", mr_author_id=2, issues=issues,
                        issues_from="closes_issues", files=[], repo="o/r", base_sha="a" * 40, head_sha="b" * 40,
                        warnings=[], now=datetime.datetime(2026, 10, 13, tzinfo=datetime.timezone.utc), policy=policy)
    off, on = go(POL.Policy(sha="c" * 40, found=True)), go(POL.Policy(sha="c" * 40, found=True, asker_required=True))
    assert {k: v for k, v in on.items() if k not in ("extras", "card", "policy")} == \
        {k: v for k, v in off.items() if k not in ("extras", "card", "policy")}
    assert on["policy"] == {**off["policy"], "active": {**off["policy"]["active"], "asker_required": True}}
    x, y = on["extras"][0], off["extras"][0]
    assert x["thread_stub"] == y["thread_stub"].replace(f" {KEEP}", f" {ONE} {KEEP}")
    assert x["plain_facts"] == {**y["plain_facts"], "asker_usernames": ["alice"]}
    assert {**x, "thread_stub": "", "plain_facts": {}} == {**y, "thread_stub": "", "plain_facts": {}}
    assert on["card"] == {**off["card"], "caveat_line": ASKS_ASKER} and off["card"]["caveat_line"] is None
    assert on["rules_version"] == 6


# ---- T44 audit pass 3 (fixes 6 and 7)
def test_the_author_of_another_projects_issue_is_never_named():
    mine = {"ref": "#5", "author_username": "alice"}
    other = {"ref": "group/other#9", "author_username": "bob"}
    assert ci.asker_usernames([other, mine]) == ["alice"]
    assert ci.asker_usernames([other]) == []


def test_the_card_says_when_nobody_can_keep_an_extra(repo, tmp_path, monkeypatch):
    """other_person_required + asker_required + the MR author also wrote the issue: no one qualifies, and the card says so."""
    both = "[names]\nother_person_required = true\nasker_required = true\n"
    repo.base = repo.commit({".itemator.toml": both}, "target branch")
    head = repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": "test:\n  script: [pytest, ruff]\n"})
    code, out = job(repo, head, FakeHttp(routes(mr(author_id=2), [by("alice", author_id=2)])), tmp_path, monkeypatch)
    assert code == 0 and ci.NOBODY_CAN in " ".join(n for n in [out["card"].get("caveat_line")] if n)


def test_no_such_warning_when_someone_else_wrote_the_issue(repo, tmp_path, monkeypatch):
    both = "[names]\nother_person_required = true\nasker_required = true\n"
    repo.base = repo.commit({".itemator.toml": both}, "target branch")
    head = repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": "test:\n  script: [pytest, ruff]\n"})
    code, out = job(repo, head, FakeHttp(routes(mr(author_id=2), [by("alice", author_id=3)])), tmp_path, monkeypatch)
    assert code == 0 and ci.NOBODY_CAN not in (out["card"].get("caveat_line") or "")
