"""eval/aidev_population.py's own parts: thread buckets, shares with intervals, and the counts of what is unreadable."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import aidev_population as P  # noqa: E402


def row(i, n, agent="Copilot", state="merged", task="linked_issue", readable=True, kinds=None, api_error=False):
    return {"id": i, "agent": agent, "state": state, "task_from": task, "readable": readable, "n": n,
            "kinds": kinds if kinds is not None else ["other"] * n, "api_error": api_error}


def test_threads_fall_in_the_registered_buckets_at_their_edges():
    assert [P.bucket(n) for n in (0, 1, 2, 3, 5, 6, 40)] == ["0", "1", "2", "3 to 5", "3 to 5", "6 or more", "6 or more"]


def test_the_overall_share_counts_readable_pull_requests_with_an_extra_and_keeps_unreadable_apart():
    rows = [row(1, 0), row(2, 1), row(3, 4), row(4, 0, readable=False), row(5, 0, readable=False, api_error=True)]
    s = P.summarize(rows)
    assert (s["pull_requests"], s["readable"], s["unreadable"], s["unreadable_with_api_error"]) == (5, 3, 2, 1)
    assert s["overall"]["with_an_extra"] == 2 and s["overall"]["pull_requests"] == 3 and s["overall"]["share"] == 0.6667
    assert s["overall"]["wilson95"][0] < 0.6667 < s["overall"]["wilson95"][1]


def test_threads_are_counted_per_bucket_with_three_or_more_and_the_most_on_one():
    s = P.summarize([row(1, 0), row(2, 1), row(3, 2), row(4, 3), row(5, 5), row(6, 9)])
    assert s["threads"] == {"0": 1, "1": 1, "2": 1, "3 to 5": 2, "6 or more": 1}
    assert s["with_three_or_more"] == {"pull_requests": 3, "share": 0.5} and s["most_threads_on_one_pull_request"] == 9


def test_groups_by_agent_state_and_task_and_extras_by_kind_and_no_linked_issue():
    s = P.summarize([row(1, 1, agent="Devin", kinds=["dependency"]), row(2, 0, agent="Copilot", state="closed", task="pr_text"),
                     row(3, 2, agent="Devin", kinds=["dependency", "ci_or_config"])])
    assert s["by_agent"]["Devin"]["with_an_extra"] == 2 and s["by_agent"]["Copilot"]["pull_requests"] == 1
    assert s["by_state"]["closed"]["pull_requests"] == 1 and s["by_task"]["pr_text"]["with_an_extra"] == 0
    assert s["extras_by_kind"] == {"dependency": 2, "ci_or_config": 1} and s["no_linked_issue"] == 1


def test_an_empty_or_all_unreadable_run_gives_no_share_not_a_division_error():
    s = P.summarize([row(1, 0, readable=False)])
    assert s["overall"]["share"] is None and s["with_three_or_more"]["share"] is None and s["most_threads_on_one_pull_request"] == 0


def test_chunks_cover_every_id_once_in_order():
    assert [c for c in P.chunks(list(range(7)), 3)] == [[0, 1, 2], [3, 4, 5], [6]]
