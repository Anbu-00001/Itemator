"""The card model-call comparison's own parts (eval/card_model_calls.py): counting model calls in a session record, the lines the
flow copies, what a posted card must equal, and the registered outcome."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import card_model_calls as M  # noqa: E402


def ai(model="claude-sonnet-5-5", tools=1):
    return {"type": "AIMessage", "tool_calls": [{}] * tools, "response_metadata": {"model_name": model}}


def tool():
    return {"type": "ToolMessage"}


def snapshot(msgs, wrapped=False):
    conv = {"card": [{"kwargs": m} if wrapped else m for m in msgs]}
    return {"checkpoint": json.dumps({"channel_values": {"conversation_history": conv}})}


def test_model_calls_are_the_ai_messages_of_the_fullest_snapshot_and_tool_calls_what_they_asked_for():
    msgs = [{"type": "HumanMessage"}, ai(tools=1), tool(), ai(tools=4), tool(), tool(), tool(), tool(), ai(tools=0)]
    got = M.count_calls([snapshot(msgs[:3]), snapshot(msgs, wrapped=True), snapshot(msgs[:6])])
    assert got == {"model_calls": 3, "tool_calls": 5, "models": ["claude-sonnet-5-5"]}


def test_a_message_without_a_model_name_is_unknown_and_an_empty_record_is_zero_calls():
    assert M.count_calls([snapshot([{"type": "AIMessage", "tool_calls": None}])]) == {"model_calls": 1, "tool_calls": 0, "models": ["unknown"]}
    assert M.count_calls([]) == {"model_calls": 0, "tool_calls": 0, "models": []}


def test_the_copied_keys_are_those_the_flow_names_once_each_in_order():
    assert M.copied_keys("a FACTS.card.final_line b FACTS.card.todo_line FACTS.card.final_line") == ["final_line", "todo_line"]
    keys = M.copied_keys(M.FLOW.read_text())
    assert keys[:2] == ["final_line", "todo_line"] and "cost_line" in keys and len(keys) == len(set(keys))


FACTS = {"state": "extras", "extras": [{}, {}], "card": {"final_line": "F", "todo_line": "T", "caveat_line": None}}


def test_a_card_must_hold_every_copied_line_and_a_missing_one_is_named():
    ok = M.check_run(FACTS, ["final_line", "todo_line", "caveat_line"], "x F y T z", 2, ["itemator::needs-names"], "Draft: t")
    assert ok["card_matches"] and ok["card_lines_missing"] == [] and ok["items_match"] and ok["label_ok"] and ok["draft_ok"]
    bad = M.check_run(FACTS, ["final_line", "todo_line"], "x F y", 2, ["itemator::needs-names"], "Draft: t")
    assert bad["card_lines_missing"] == ["todo_line"] and not bad["card_matches"]


def test_threads_label_and_draft_state_must_follow_the_state():
    r = M.check_run(FACTS, [], "", 1, ["other"], "title")
    assert M.check_run(FACTS, [], "", 3, [], "t")["items_match"] is False                       # one note too many is a miss too
    assert not r["items_match"] and r["label_ok"] is False and r["draft_ok"] is False
    inside = M.check_run({"state": "inside_ask", "extras": [], "card": {}}, [], "", 0, ["itemator::inside-ask"], "title")
    assert inside["label_ok"] and inside["draft_ok"] and inside["items_match"]            # no Draft for this state
    assert M.check_run({"state": "mystery", "extras": [], "card": {}}, [], "", 0, [], "t")["label_ok"] is None


def run(session, calls, extras=None, tools=10):
    return {"session": session, "model_calls": calls, "tool_calls": tools, "extras": extras}


def test_the_summary_gives_the_mean_the_max_and_the_modelled_credits():
    s = M.summarise([run("a", 9), run("b", 8), run("c", 9)])
    assert s == {"runs": 3, "model_calls": [9, 8, 9], "tool_calls": [10, 10, 10], "mean_model_calls": 8.67, "max_model_calls": 9,
                 "modelled_credits": 8.12}
    assert M.summarise([])["mean_model_calls"] is None


def test_a_cut_needs_every_after_run_below_its_comparable_before_run_and_a_lower_mean():
    before = [run("b1", 9, 3), run("b2", 8, 1), run("b3", 9, 0)]
    good = M.verdict(before, [run("a1", 6, 3), run("a2", 6, 1), run("a3", 6, 0)])
    assert good["cut"] and all(good["each_after_run_below_its_comparable_before_run"].values())
    one_high = M.verdict(before, [run("a1", 6, 3), run("a2", 6, 1), run("a3", 9, 0)])           # a run with 0 extras must beat the 0-extra run
    assert not one_high["cut"] and one_high["each_after_run_below_its_comparable_before_run"]["a3"] is False
    equal_mean = M.verdict([run("b", 6, 0)], [run("a", 6, 0)])
    assert not equal_mean["cut"]
    assert M.verdict(before, [run("a", 7, None)])["each_after_run_below_its_comparable_before_run"]["a"] is True    # extras unknown: all before runs count
    assert M.verdict([], [run("a", 1, 0)])["each_after_run_below_its_comparable_before_run"]["a"] is False


def test_only_before_runs_with_the_same_or_fewer_extras_set_the_bar():
    before = [run("b1", 9, 3), run("b3", 7, 0)]
    assert M.verdict(before, [run("a", 8, 1)])["each_after_run_below_its_comparable_before_run"]["a"] is False     # the 0-extra run (7 calls) is the bar
    assert M.verdict(before, [run("a", 6, 1)])["each_after_run_below_its_comparable_before_run"]["a"] is True


def test_the_platforms_started_note_is_not_one_of_the_flows_notes():
    assert M.is_progress_note("✅ Itemator card has started. You can view progress here") and not M.is_progress_note("3 things beyond #71")
    assert not M.is_progress_note(None)


def test_when_no_before_run_is_comparable_the_registered_rule_is_not_met_and_the_post_hoc_line_says_so_apart():
    before = [run("b1", 9, 3), run("b2", 9, 3), run("b3", 8, 3)]
    v = M.verdict(before, [run("a1", 6, 3), run("a2", 5, 1)])
    assert v["each_after_run_below_its_comparable_before_run"] == {"a1": True, "a2": False} and v["cut"] is False
    assert v["post_hoc"]["each_after_run_below_the_smallest_before_run"] == {"a1": True, "a2": True}
    assert "not registered" in v["post_hoc"]["note"]
    assert M.verdict(before, [run("a1", 8, 3)])["post_hoc"]["each_after_run_below_the_smallest_before_run"] == {"a1": False}
    assert M.verdict([], [run("a1", 1, 0)])["post_hoc"]["each_after_run_below_the_smallest_before_run"] == {"a1": False}
