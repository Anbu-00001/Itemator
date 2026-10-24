"""itemator/replycheck.py: the reaction flow's answer tests, run as code on hand-made discussions."""
import pytest

from itemator import replycheck as V

CARD, REACT = V.CARD_BOT, V.REACT_BOT
PEOPLE = {1: "ann", 2: "bob", 3: "cy", 9: "helper-bot"}


def note(uid, body, at, nid=None, system=False, user=None):
    return {"id": nid or hash((uid, body, at)) % 10**9, "author": {"id": uid, "username": user or PEOPLE.get(uid, CARD)},
            "body": body, "created_at": f"2026-10-22T10:{at:02d}:00Z", "system": system}


def card_note(name, extra=""):
    return {"id": 50, "author": {"id": 100, "username": CARD}, "created_at": "2026-10-22T10:00:00Z", "system": False,
            "body": f"`{name}` is beyond the issue. To keep it, reply with its exact name.{extra}"}


def mr(author="ann", reviewers=("bob",)):
    return {"author": {"username": author}, "assignees": [], "reviewers": [{"username": r} for r in reviewers]}


def is_person(uid):
    return uid in (1, 2, 3)


def run(name, replies, extra="", author="ann", reviewers=("bob",), card_replies=()):
    ds = [{"id": "t", "notes": [card_note(name, extra), *replies]}]
    if card_replies:
        ds.append({"id": "c", "notes": [{"id": 60, "author": {"id": 100, "username": CARD}, "created_at": "2026-10-22T10:00:00Z",
                                         "system": False, "body": "2 files beyond #1."}, *card_replies]})
    return V.audit(mr(author, reviewers), ds, is_person)[0]


@pytest.mark.parametrize("reply, want", [
    ("`rich`", "named"), ("rich.", "named"), ("rich @ai-itemator-react-gitlab-ai-hackathon", "named"),
    ("Not an extra.", "dismissed"), ("@ai-itemator-react-gitlab-ai-hackathon not an extra", "dismissed"),
    ("split", "split"), ("Remove", "remove"),
    ("Rich", None), ("rich please", None), ("keep rich?", None), ("not an extra really", None)])
def test_a_reply_counts_only_by_the_string_tests(reply, want):
    got = run("rich", [note(2, reply, 5)])["tests"]
    assert (got and got["answer"]) == want


def test_split_and_remove_count_only_from_the_crew_and_after_the_last_refusal():
    assert run("rich", [note(3, "remove", 5)])["tests"] is None                     # cy is not author, reviewer or assignee
    refused = [note(2, "remove", 5), note(0, "Cannot remove: `rich` holds more.", 6, user=REACT), note(2, "remove", 7, nid=7)]
    assert run("rich", refused[:2])["tests"] is None
    assert run("rich", refused)["tests"] == {"answer": "remove", "who": "bob", "note": 7}


def test_other_only_leaves_out_the_author_and_bots_never_count():
    extra = "\nA reply from the merge request author does not count."
    assert run("rich", [note(1, "rich", 5)], extra)["tests"] is None
    assert run("rich", [note(1, "rich", 5), note(2, "rich", 6, nid=6)], extra)["tests"]["who"] == "bob"
    assert run("rich", [note(9, "rich", 5)])["tests"] is None                       # not a person
    assert run("rich", [note(2, "rich", 5, system=True)])["tests"] is None


def test_asker_only_keeps_only_for_the_named_askers():
    extra = "\nOnly the person who wrote the linked issue (@cy) can keep this."
    assert run("rich", [note(2, "rich", 5)], extra)["tests"] is None
    assert run("rich", [note(3, "rich", 5)], extra)["tests"]["who"] == "cy"
    assert run("rich", [note(2, "not an extra", 5)], extra)["tests"] is None
    assert run("rich", [note(2, "remove", 5)], extra)["tests"]["answer"] == "remove"   # remove still works
    assert V.askers("Only the person who wrote the linked issue (@cy or bad name) can keep this.") == []


def test_always_needs_the_offer_and_a_name_reply_beats_a_word_that_is_the_name():
    offer = "\nTo keep it and stop asking about this file, reply `always`; that opens a merge request that changes the team policy."
    assert run("rich", [note(2, "always", 5)])["tests"] is None
    assert run("rich", [note(2, "always", 5)], offer)["tests"]["always"] is True
    assert run("remove", [note(2, "remove", 5)])["tests"]["answer"] == "named"        # NAME "remove" typed is a name


def test_a_card_reply_can_only_keep():
    got = run("rich", [], card_replies=[note(2, "not an extra", 5), note(3, "`rich`,\nand more", 6, nid=6)])["tests"]
    assert got == {"answer": "named", "who": "cy", "note": 6, "from_card": True}


def test_the_flow_record_is_read_and_replies_after_it_do_not_count():
    rows = run("rich", [note(2, "rich", 5), note(0, "Kept: `rich`, named by @bob.", 6, user=REACT), note(3, "not an extra", 7)])
    assert rows["recorded"]["answer"] == "named" and rows["recorded"]["who"] == "bob" and rows["agree"] is True
    wrong = run("rich", [note(2, "rich", 5), note(0, "Dismissed: `rich` is not an extra, said @bob.", 6, user=REACT)])
    assert wrong["agree"] is False
    other = run("rich", [note(2, "rich", 5), note(0, "Kept: `rich`, named by @cy.", 6, user=REACT)])
    assert other["agree"] is False                                               # right answer, wrong person
    assert run("rich", [note(2, "rich?", 5)])["agree"] is None
    late = run("rich", [note(2, "rich?", 5), note(0, "Kept: `rich`, named by @bob.", 6, user=REACT), note(2, "rich", 7)])
    assert late["agree"] is False and late["tests"] is None                      # a reply written after the record cannot explain it


def test_the_live_audit_found_no_answer_the_tests_would_not_give():
    import json, pathlib
    d = json.loads((pathlib.Path(__file__).resolve().parent.parent / "results/react_audit_v1.json").read_text())
    assert d["count"]["differ"] == 0 and d["count"]["missed"] == 0 and d["recorded"] == d["count"]["agree"] > 0
    assert d["extras"] == len(d["rows"]) == sum(d["count"].values())


# ---- members only (the card's ci.MEMBERS_ONLY sentence)

MEMBERS = "\n" + V.MEMBERS_ONLY
ROLES = {1: {"access_level": 40, "state": "active", "expires_at": None}, 2: {"access_level": 30, "state": "active", "expires_at": "2026-12-31"},
         3: {"access_level": 20, "state": "active", "expires_at": None}}


def members_run(replies, card_replies=(), roles=ROLES):
    ds = [{"id": "t", "notes": [card_note("rich", MEMBERS), *replies]}]
    if card_replies:
        ds.append({"id": "c", "notes": [{"id": 60, "author": {"id": 100, "username": CARD}, "created_at": "2026-10-22T10:00:00Z",
                                         "system": False, "body": "2 files beyond #1."}, *card_replies]})
    return V.audit(mr(), ds, is_person, is_member=lambda uid, at: V.member(roles.get(uid), at))[0]["tests"]


def test_the_card_sentence_is_the_one_the_tests_read():
    from itemator import ci
    assert V.MEMBERS_ONLY == ci.MEMBERS_ONLY and ci.MEMBERS_ONLY in ci.thread_stub(V_extra())


def V_extra():
    from itemator.extras import Extra
    return Extra("ci_or_config", ".gitlab-ci.yml", ".gitlab-ci.yml", "x")


def test_a_reporter_or_a_stranger_cannot_keep_or_dismiss_but_a_developer_can():
    assert members_run([note(3, "rich", 5)]) is None                                  # Reporter
    assert members_run([note(3, "not an extra", 5)]) is None
    assert members_run([note(3, "rich", 5), note(2, "rich", 6, nid=6)])["who"] == "bob"   # Developer, later
    assert members_run([note(1, "not an extra", 5)])["answer"] == "dismissed"           # Maintainer
    assert members_run([note(3, "rich", 5)], roles={}) is None                         # no member record at all


def test_a_card_reply_from_a_non_member_does_not_keep_either():
    assert members_run([], card_replies=[note(3, "rich", 5)]) is None
    assert members_run([], card_replies=[note(2, "rich", 5)])["from_card"] is True


def test_without_a_member_check_nobody_counts_in_a_members_only_thread():
    ds = [{"id": "t", "notes": [card_note("rich", MEMBERS), note(1, "rich", 5)]}]
    assert V.audit(mr(), ds, is_person)[0]["tests"] is None
    assert V.audit(mr(), [{"id": "t", "notes": [card_note("rich"), note(3, "rich", 5)]}], is_person)[0]["tests"]["who"] == "cy"   # an older card: as before


@pytest.mark.parametrize("m, at, ok", [
    ({"access_level": 30, "state": "active", "expires_at": None}, "2026-10-22T10:00:00Z", True),
    ({"access_level": 29, "state": "active", "expires_at": None}, "2026-10-22T10:00:00Z", False),
    ({"access_level": 50, "state": "blocked", "expires_at": None}, "2026-10-22T10:00:00Z", False),
    ({"access_level": 30, "state": "active", "expires_at": "2026-10-22"}, "2026-10-22T10:00:00Z", False),   # expires that day
    ({"access_level": 30, "state": "active", "expires_at": "2026-10-23"}, "2026-10-22T23:59:00Z", True),
    ({"access_level": "30", "state": "active", "expires_at": None}, "2026-10-22T10:00:00Z", False),
    ({"state": "active"}, "2026-10-22T10:00:00Z", False), (None, "2026-10-22T10:00:00Z", False), ([], "x", False),
])
def test_who_counts_as_a_member(m, at, ok):
    assert V.member(m, at) is ok


BUMP = f" {V.BUMP_START}ci/.gitlab-ci.yml`, `image: php:8.3.30-cli` becomes `image: php:8.3.36-cli`."


def test_bump_counts_only_where_offered_from_the_crew_and_after_the_last_refusal():
    assert V.threads([{"id": "t", "notes": [card_note("ci", BUMP)]}])[0]["bump"] == (
        "ci/.gitlab-ci.yml", "image: php:8.3.30-cli", "image: php:8.3.36-cli")
    assert run("ci", [note(2, "bump", 5, nid=5)], BUMP)["tests"] == {"answer": "bump", "who": "bob", "note": 5}
    assert run("ci", [note(2, "Bump.", 5)], BUMP)["tests"]["answer"] == "bump"
    assert run("ci", [note(2, "bump", 5)])["tests"] is None                         # not offered in this thread
    assert run("ci", [note(3, "bump", 5)], BUMP)["tests"] is None                   # cy is not in the crew
    assert run("ci", [note(2, "bump it", 5)], BUMP)["tests"] is None
    refused = [note(2, "bump", 5), note(0, "Cannot bump: `ci` changed.", 6, user=REACT)]
    assert run("ci", refused, BUMP)["tests"] is None
    assert run("ci", [*refused, note(1, "bump", 7, nid=7)], BUMP)["tests"]["who"] == "ann"


def test_a_bump_record_is_read_and_agrees():
    rec = note(0, "Bumped: in `ci/.gitlab-ci.yml`, `image: php:8.3.30-cli` became `image: php:8.3.36-cli`, asked by @bob.", 6, user=REACT)
    row = run("ci", [note(2, "bump", 5), rec], BUMP)
    assert row["recorded"]["answer"] == "bump" and row["recorded"]["who"] == "bob" and row["agree"] is True
    assert V.unanswered([row]) == []


def test_a_bump_offer_with_too_few_backticks_offers_nothing():
    assert V.bump_of(f"{V.BUMP_START}a`, `b`.") is None and V.bump_of("no offer") is None


UNTIL = f" {V.UNTIL_OFFER}"
TAKE = " To take it out, change `ci/x.sh` in this merge request so that `sed -i s/a/b/ in.csv` is gone, then reply `taken out`."


@pytest.mark.parametrize("reply, until", [("until #12", 12), ("Until #7.", 7), ("@ai-itemator-react-gitlab-ai-hackathon until #3", 3),
                                          ("until #0", None), ("until #012", None), ("until 12", None), ("until #12 please", None),
                                          ("until #1234567890", None)])
def test_until_keeps_only_with_an_issue_number_where_offered(reply, until):
    got = run("rich", [note(3, reply, 5)], UNTIL)["tests"]       # anyone may keep: cy is outside the crew
    assert (got and got.get("until")) == until
    assert run("rich", [note(3, "until #12", 5)])["tests"] is None
    refused = [note(2, "until #12", 5), note(0, "Cannot keep until #12: it is not an open issue in this project.", 6, user=REACT)]
    assert run("rich", refused, UNTIL)["tests"] is None


def test_an_until_record_counts_as_kept():
    rec = note(0, "Kept: `rich`, until #12, by @cy.", 6, user=REACT)
    row = run("rich", [note(3, "until #12", 5), rec], UNTIL)
    assert row["recorded"]["answer"] == row["tests"]["answer"] == "named" and row["agree"] is True


def test_taken_out_counts_only_from_the_crew_where_offered_and_after_a_refusal():
    assert V.threads([{"id": "t", "notes": [card_note("ci/x.sh", TAKE)]}])[0]["take_out"] == ("ci/x.sh", "sed -i s/a/b/ in.csv")
    assert run("ci/x.sh", [note(2, "taken out", 5)], TAKE)["tests"]["answer"] == "taken_out"
    assert run("ci/x.sh", [note(3, "taken out", 5)], TAKE)["tests"] is None
    assert run("ci/x.sh", [note(2, "taken out", 5)])["tests"] is None
    refused = [note(2, "taken out", 5), note(0, "Cannot take out: `sed` is still in `ci/x.sh`.", 6, user=REACT)]
    assert run("ci/x.sh", refused, TAKE)["tests"] is None
    rec = note(0, "Taken out: `ci/x.sh` no longer holds the stopgap, said @bob.", 8, user=REACT)
    row = run("ci/x.sh", [*refused, note(2, "taken out", 7), rec], TAKE)
    assert row["recorded"] == {**row["recorded"], "answer": "taken_out", "who": "bob"} and row["agree"] is True
