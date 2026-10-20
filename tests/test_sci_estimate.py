"""The SCI bracket (eval/sci_estimate.py): its arithmetic by hand, its inputs read from the live thread, and the results file it wrote."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import sci_estimate as S  # noqa: E402

THREAD = ("with what it brings along, 6 packages (5 more than the line names) and about 31 MB to download on every fresh install; "
          "this project ran 936 pipelines in the last 30 days, so about 29 GB a month")


def test_one_install_by_hand():
    got = S.per_install(31, (1.21, 1.65))
    low_kwh = 0.031 * 0.001 + 2 * 0.71 * 1.1 * 1.21 / 3600 / 1000
    high_kwh = 0.031 * 0.114 + (2 * 4.26 + 8 * 0.392) * 1.1 * 1.65 / 3600 / 1000
    assert got["low"]["operational_g"] == pytest.approx(low_kwh * 432)
    assert got["high"]["operational_g"] == pytest.approx(high_kwh * 579)
    assert got["low"]["embodied_g"] == pytest.approx(1230e3 * 1.21 / (4 * 365.25 * 86400) * 2 / 32)
    assert got["high"]["sci_g_per_install"] == pytest.approx(got["high"]["operational_g"] + got["high"]["embodied_g"])


def test_the_live_case_is_read_from_the_thread_and_a_changed_thread_stops_it():
    assert S.live_case({"thread": THREAD}) == (31.0, 936)
    with pytest.raises(AssertionError, match="no longer says"):
        S.live_case({"thread": THREAD.replace("936 pipelines", "many pipelines")})


def test_the_results_file_is_what_the_script_computes_now():
    load = lambda n: json.loads((S.RES / n).read_text())                           # noqa: E731
    got = S.compute(load("weight_live.json"), load("aidev_weight_v1_corrected.json"), load("install_time_pypi_v1.json"), load("install_time_npm_v1.json"))
    saved = json.loads(S.OUT.read_text())
    assert {k: saved[k] for k in got} == got
    assert got["inputs"]["seconds_added"] == [1.21, 1.65] and got["readme"]["live_g_low"] < got["readme"]["live_g_high"]
    assert saved["coefficients"]["network_kwh_per_gb"] == [0.001, pytest.approx(0.114)]
