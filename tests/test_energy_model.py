import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import energy_model as E  # noqa: E402


def data(before, after):
    return {"before": [{"model_calls": n, "extras": 3} for n in before], "after": after}


def test_calls_avoided_are_compared_like_for_like():
    d = data([9, 9, 8], [{"model_calls": 6, "extras": 3}, {"model_calls": 5, "extras": 1}, {"model_calls": 5, "extras": 0}])
    s = E.compute(d)
    assert (s["model_calls_after"], s["model_calls_avoided_per_run"], s["share_avoided"]) == (6, 2.67, 0.308)
    assert (s["wh_per_run_avoided_low"], s["wh_per_run_avoided_high"]) == (0.27, 80.0)


def test_a_different_shape_of_input_is_refused():
    with pytest.raises(AssertionError):
        E.compute(data([9, 9], [{"model_calls": 6, "extras": 3}]))


def test_the_committed_result_is_what_the_script_computes():
    root = pathlib.Path(E.ROOT)
    assert json.loads((root / "results" / "energy_modelled_v1.json").read_text())["summary"] == \
        E.compute(json.loads(E.CALLS.read_text()))


def test_the_spread_is_stated_and_no_single_figure_is_given():
    out = json.loads((pathlib.Path(E.ROOT) / "results" / "energy_modelled_v1.json").read_text())
    assert out["wh_per_call"]["spread"] == 300 and "kWh" in out["limits"] and "middle" not in out["summary"]
