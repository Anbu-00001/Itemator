import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import e2e_live as E  # noqa: E402
import react_study as R  # noqa: E402

CARD = "ai-itemator-card-gitlab-ai-hackathon"
OP = "anbuchelvanganesan.cse2024"
OFF = {R.TRIG["card"]: False, R.TRIG["react"]: False}


def note(body, author=CARD, system=False):
    return {"body": body, "author": author, "system": system}


def good():
    threads = {"rich": "`rich` ... " + E.LINE + "x. " + E.DECIDED,
               "examples/usage_ping.py": "`examples/usage_ping.py` (named by another checker): Overreach named it (x). " + E.LINE + "y."}
    notes = [note("opened", "anbuchelvanganesan.cse2024", True), note("2 things beyond #1"),
             note("marked this merge request as **draft**", system=True)]
    return notes, threads


def test_all_pass():
    notes, threads = good()
    assert all(E.checks(notes, threads, OFF, OP).values())


def test_review_request_before_card_fails_e1():
    notes, threads = good()
    notes.insert(1, note("requested review from someone", "anbuchelvanganesan.cse2024", True))
    assert not E.checks(notes, threads, OFF, OP)["E1_started_by_itself"]


def test_mention_before_card_fails_e1_but_flow_mention_after_does_not():
    notes, threads = good()
    assert E.checks(notes + [note("@ai-itemator-react check", "anbuchelvanganesan.cse2024")], threads, OFF, OP)["E1_started_by_itself"]
    notes.insert(1, note("@ai-itemator-card go", "anbuchelvanganesan.cse2024"))
    assert not E.checks(notes, threads, OFF, OP)["E1_started_by_itself"]


def test_no_card_fails_e1():
    assert not E.checks([note("opened", "x", True)], {}, OFF, OP)["E1_started_by_itself"]


def test_missing_parts():
    notes, threads = good()
    c = E.checks(notes, {**threads, "rich": "`rich` " + E.LINE}, OFF, OP)
    assert not c["E2_decided_before"] and c["E3_other_checker"]
    c = E.checks(notes, {**threads, "examples/usage_ping.py": "named by another checker " + E.LINE}, OFF, OP)
    assert not c["E3_other_checker"]
    assert not E.checks(notes, {**threads, "x": "no line"}, OFF, OP)["E4_read_line"]
    assert not E.checks(notes, {}, OFF, OP)["E4_read_line"]


def test_draft_must_be_by_card():
    notes, threads = good()
    notes[2] = note("marked this merge request as **draft**", "anbuchelvanganesan.cse2024", True)
    assert not E.checks(notes, threads, OFF, OP)["E5_draft"]


def test_trigger_left_on_or_other_flow_fails_e6():
    notes, threads = good()
    assert not E.checks(notes, threads, {**OFF, R.TRIG["react"]: True}, OP)["E6_nothing_else"]
    assert not E.checks(notes + [note("review", "duo-code-review-bot")], threads, OFF, OP)["E6_nothing_else"]


def test_words_requested_review_in_a_comment_are_not_a_request():
    notes, threads = good()
    notes.insert(1, note("nobody requested review here", "anbuchelvanganesan.cse2024"))
    assert E.checks(notes, threads, OFF, OP)["E1_started_by_itself"]
