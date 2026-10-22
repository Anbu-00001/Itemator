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
