"""T48: the card flow reads the itemator job also when it FAILED. With names.hold_until_named the job fails on purpose until every
extra is named and still writes itemator.json; a card that stops on "not success" would never post the threads that unlock it."""
import pathlib

import pytest

FLOW = pathlib.Path(__file__).resolve().parent.parent / "flows" / "itemator_card.yml"
NEW = 'is neither "success" nor "failed" (a held job fails on purpose and still writes its facts), reply "No finished itemator job." and stop.'


def text():
    if not FLOW.exists():
        pytest.skip("no flows/ in this copy")
    return FLOW.read_text()


def test_a_failed_job_is_read_in_both_places():
    t = text()
    assert t.count(NEW) == 2                                  # the webhook payload (step 1) and the pipeline list (step 3)


def test_no_place_still_demands_success_alone():
    t = text()
    assert 'its status is not "success", reply "No finished itemator job."' not in t
    assert 'status is not "success", reply' not in t


def test_the_pipeline_status_gate_already_accepts_failed():
    assert 'neither "success" nor "failed"' in text()


def test_every_line_of_the_card_is_copied_by_the_flow():
    """The flow prints each card line it knows by name; a line the CI job adds and the flow does not name never reaches the merge request."""
    from itemator import ci
    t = text()
    card = ci.card_lines("extras", [{"ref": "#1"}], [], [], [])
    for key in (*card, "checked_line"):
        assert f"FACTS.card.{key}, copied character for character" in t, key
    assert "only if the key is present and its value is not null" in t
