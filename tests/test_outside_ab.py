"""eval/outside_ab.py: the registered outcome rule of the outside reviewer test, applied by code."""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("outside_ab", pathlib.Path(__file__).parent.parent / "eval" / "outside_ab.py")
AB = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AB)


def note(body, author="someone", system=False):
    return {"author": author, "body": body, "system": system}


def thread(name, *replies):
    return {"notes": [note(f"`{name}` ...\n\n[//]: # (itemator:extra={name})", author="ai-itemator-card-two-x"), *replies]}


def test_the_first_participants_words_catch_the_package_and_leave_the_ci_change_unsettled():
    said = "Approved the slug fix; please remove the unrelated `leftpad-py` dependency and split or drop the CI changes."
    s = AB.score([{"notes": [note(said)]}])
    assert s["caught"] == {"package": True, "ci": False}
    assert s["unsettled"] == [said] and s["replies"] == [said]


def test_a_one_word_answer_counts_only_in_its_own_thread():
    s = AB.score([thread("leftpad-py", note("remove")), thread(".gitlab-ci.yml", note("split"))])
    assert s["caught"] == {"package": True, "ci": True} and s["unsettled"] == []
    assert AB.score([{"notes": [note("remove")]}])["caught"] == {"package": False, "ci": False}


def test_naming_without_asking_and_keeping_by_name_are_not_catches():
    s = AB.score([{"notes": [note("LGTM, the .gitlab-ci.yml job looks fine")]}, thread("leftpad-py", note("leftpad-py"))])
    assert s["caught"] == {"package": False, "ci": False} and s["unsettled"] == []


def test_a_question_naming_the_file_is_a_catch_and_owner_and_bot_notes_never_count():
    s = AB.score([{"notes": [note("Why does this touch .gitlab-ci.yml?")]}])
    assert s["caught"]["ci"] is True
    for who in ("anbuchelvanganesan.cse2024", "anbuchelvannew", "ai-itemator-card-two-x", "duo-developer-x"):
        assert AB.score([{"notes": [note("please remove leftpad-py", author=who)]}])["replies"] == []
    assert AB.score([{"notes": [note("please remove leftpad-py", system=True)]}])["replies"] == []


def test_the_summary_counts_only_people_who_replied_and_claims_a_difference_only_at_five_each():
    r = lambda arm, p, c, replied=True: {"arm": arm, "replied": replied, "caught": {"package": p, "ci": c}}
    rows = [r("with_itemator", True, False), r("without", False, False), r("without", True, True, replied=False)]
    s = AB.summarise(rows)
    assert s["with_itemator"] == {"participants": 1, "planted": 2, "caught": 1, "share": 0.5}
    assert s["without"] == {"participants": 1, "planted": 2, "caught": 0, "share": 0.0}
    assert s["difference_claimed"] is False
    assert AB.summarise([r("with_itemator", 1, 1)] * 5 + [r("without", 0, 0)] * 5)["difference_claimed"] is True
