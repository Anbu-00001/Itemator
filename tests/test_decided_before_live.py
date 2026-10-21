"""The live decided-before check: the pure part of eval/decided_before_live.py."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import decided_before_live as L  # noqa: E402

GOOD = {"extras": [{"name": "rich", "thread_stub": "`rich` (new dependency): x.\n\n" + L.WANT["rich"]},
                   {"name": "scratch.bak", "thread_stub": "`scratch.bak` (stray file): x.\n\n" + L.WANT["scratch.bak"]}],
        "decided_before": {"read": True, "matched": 2}}
OFF = {"a": False, "b": False}


def test_a_good_run_passes_every_check():
    assert all(L.checks(GOOD, OFF, OFF, 0).values())


def test_each_check_fails_on_its_own_fault():
    assert not L.checks(None, OFF, OFF, 0)["D1_job_ran"]
    bad = {**GOOD, "extras": [dict(GOOD["extras"][0], thread_stub="`rich`: x."), GOOD["extras"][1]]}
    assert not L.checks(bad, OFF, OFF, 0)["D2_rich"]
    bad = {**GOOD, "extras": GOOD["extras"][:1]}
    assert not L.checks(bad, OFF, OFF, 0)["D3_scratch"]
    assert not L.checks({**GOOD, "decided_before": {"read": True, "matched": 1}}, OFF, OFF, 0)["D4_record"]
    assert not L.checks(GOOD, {"a": True}, OFF, 0)["D5_no_flow"] and not L.checks(GOOD, OFF, {"a": True}, 0)["D5_no_flow"]
    assert not L.checks(GOOD, {}, {}, 0)["D5_no_flow"]
    assert not L.checks(GOOD, OFF, OFF, 1)["D6_no_notes"]
