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
    for key in (*card, "checked_line", "cost_line"):
        assert f"FACTS.card.{key}, copied character for character" in t, key
    assert "only if the key is present and its value is not null" in t


def step(t, n):
    """The text of one numbered step."""
    start = t.index(f"        Step {n}. ")
    nxt = t.find(f"        Step {n + 1}. ", start)
    return t[start:nxt if nxt != -1 else len(t)]


def test_the_pipeline_comes_from_the_merge_request_answer_and_the_listing_is_only_the_fallback():
    t = text()
    assert "head_pipeline (its id and sha)" in step(t, 2)
    three = step(t, 3)
    assert "head_pipeline from step 2" in three and "Only otherwise call" in three
    assert three.index("head_pipeline from step 2") < three.index("/merge_requests/<IID>/pipelines")
    assert t.count("/merge_requests/<IID>/pipelines") == 1


def test_the_jobs_listing_and_the_duplicate_search_are_asked_for_in_one_turn_before_any_write():
    t = text()
    three = step(t, 3)
    assert "in the same turn, together" in three and "the search call of step 6" in three
    assert "/pipelines/<pipeline id>/jobs" in three
    six = step(t, 6)
    assert '"/api/v4/projects/<project_id>/search"' in six and '"search": "itemator:head=<HEAD>"' in six
    assert "Never list the merge request's notes" in six and "Card already posted for this head." in six
    assert t.index("Step 6. ") < t.index("Step 7. ")                        # the decision to stop comes before the first write


def test_the_card_and_every_thread_are_written_in_one_turn_and_the_label_comes_last():
    t = text()
    assert "together in one turn, this one first" in step(t, 7)
    assert t.index("Step 7. ") < t.index("Step 8. ") < t.index("Step 9. ")
    assert "update_merge_request" in step(t, 9) and "update_merge_request" not in step(t, 8)


def test_the_flow_sets_no_cycle_cap_because_the_catalog_schema_refuses_it():
    assert "max_cycles" not in text()          # "/components/0/max_cycles is a disallowed additional property" (aiCatalogFlowUpdate, 2026-10-19)
