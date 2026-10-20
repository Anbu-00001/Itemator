"""The cost line of the card: wall time, reads and no model call, counted by the job itself."""
from itemator import ci


def test_the_line_says_time_reads_and_that_no_model_was_used():
    d = ci.cost(4.24, 9, 3)
    assert d["line"] == "Cost of finding these facts: 4.2 s on the CI runner, 9 GitLab reads and 3 package-registry lookups, no model call."
    assert d["seconds"] == 4.2 and d["gitlab_reads"] == 9 and d["registry_reads"] == 3 and d["model_calls"] == 0


def test_one_read_is_singular_a_tiny_time_is_not_shown_as_zero_and_no_lookups_are_not_mentioned():
    d = ci.cost(0.01, 1, 0)
    assert d["line"] == "Cost of finding these facts: under 0.1 s on the CI runner, 1 GitLab read, no model call."
    assert ci.cost(0.06, 1, 0)["line"].startswith("Cost of finding these facts: 0.1 s") and "under" not in ci.cost(0.06, 1, 0)["line"]
    assert "lookup" not in d["line"] and ci.cost(1.0, 2, 1)["line"].endswith("2 GitLab reads and 1 package-registry lookup, no model call.")


def test_the_api_counts_each_read_once_even_when_it_is_tried_again(monkeypatch):
    answers = iter([(503, b"busy"), (200, b"[]")])
    monkeypatch.setattr(ci.time, "sleep", lambda _s: None)
    api = ci.Api("https://gitlab.example/api/v4", None, lambda url, headers: next(answers))
    api.get("/a")
    assert api.reads == 1
    api.http = lambda url, headers: (404, b"")
    api.get("/b", missing_ok=True)
    assert api.reads == 2


FLOW = {"calls": 6, "credits": 1.9}


def test_with_the_flow_estimate_a_second_sentence_says_what_the_flow_after_the_job_typically_costs():
    d = ci.cost(1.0, 2, 0, FLOW)
    assert d["line"] == ("Cost of finding these facts: 1.0 s on the CI runner, 2 GitLab reads, no model call. The flow after it typically makes"
                         " about 6 model calls, up to about 1.9 GitLab Credits at the model's list price (an estimate).")
    assert d["model_calls"] == 0 and ci.cost(1.0, 2, 0)["line"].endswith("no model call.")


def test_the_estimate_file_is_read_and_a_missing_or_broken_one_leaves_the_line_without_it(tmp_path, monkeypatch):
    assert ci.flow_cost() == FLOW
    monkeypatch.setattr(ci.pathlib, "Path", lambda *a: tmp_path / "x.py")          # itemator/flow_cost.json is not there
    assert ci.flow_cost() is None
    (tmp_path / "flow_cost.json").write_text("{not json")
    assert ci.flow_cost() is None
    (tmp_path / "flow_cost.json").write_text('{"calls": 6, "credits": "x"}')
    assert ci.flow_cost() is None
    (tmp_path / "flow_cost.json").write_text('{"calls": 6}')       # a key missing
    assert ci.flow_cost() is None
    (tmp_path / "flow_cost.json").write_text('{"calls": "6", "credits": 2}')
    assert ci.flow_cost() is None


def test_the_estimate_shipped_with_the_job_equals_the_results_file_the_readme_cites():
    import json, pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    r = json.loads((root / "results" / "cost_per_run.json").read_text())
    assert ci.flow_cost() == {"calls": r["card_run_model_calls"]["typical"], "credits": r["card_run_credits"]["list_price"]}
    assert r["card_run_credits"]["list_price"] == round(r["card_run_model_calls"]["typical"] * r["credits_per_model_call_list_price"] + 1e-9, 1)
