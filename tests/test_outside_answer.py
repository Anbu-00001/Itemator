"""The live outside-answer run starts the reaction flow only on a reply from a person who is not one of the owner's accounts."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import outside_answer_live as O  # noqa: E402


def n(who, uid, system=False):
    return {"author": {"username": who, "id": uid}, "system": system, "body": "pyproject.toml"}


def test_owner_accounts_bots_and_system_notes_are_skipped():
    card = n("ai-itemator-card-gitlab-ai-hackathon", 1)
    people = {4, 5}   # 4 is the reaction account: its name alone must keep it out
    thread = {"notes": [card, n("anbuchelvanganesan.cse2024", 2), n("anbuchelvannew", 3), n("ai-itemator-react-gitlab-ai-hackathon", 4),
                        n("friend", 6), n("someone", 5, system=True), n("friend2", 5)]}
    got = O.outside_reply(thread, is_person=lambda uid: uid in people)
    assert got["author"]["username"] == "friend2"


def test_no_outside_reply_means_none():
    thread = {"notes": [n("card", 1), n("anbuchelvannew", 3)]}
    assert O.outside_reply(thread, is_person=lambda uid: True) is None


def test_the_rubric_names_both_owner_accounts():
    assert O.RUBRIC["owner_accounts"] == ["anbuchelvanganesan.cse2024", "anbuchelvannew"]
