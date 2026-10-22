import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import combined_exact as CE  # noqa: E402
from itemator import extras as X  # noqa: E402

FILES = [{"filename": "src/a.py", "status": "modified", "patch": "@@ -1 +1 @@\n-x = 1\n+x = 2\n"},
         {"filename": "notes.txt", "status": "added", "patch": "@@ -0,0 +1 @@\n+hello\n"},
         {"filename": "tools/run.sh", "status": "added", "patch": "@@ -0,0 +1 @@\n+echo hi\n"}]


def base():
    return X.analyse("Fix x in src/a.py", FILES, repo="o/r", version=6)


def test_each_rival_file_the_rules_missed_becomes_one_question():
    b = base()
    rival = {"overreach": {"tools/run.sh"}, "scope_creep_detector": {"tools/run.sh", "src/a.py"}}
    n0 = len(b.extras)
    assert len(CE.setup_extras(b, rival, FILES, ()).extras) == n0
    assert len(CE.setup_extras(b, rival, FILES, ("overreach",)).extras) == n0 + (0 if CE.listed(b, "tools/run.sh") else 1)
    both = CE.setup_extras(b, rival, FILES, ("overreach", "scope_creep_detector"))
    assert CE.listed(both, "tools/run.sh") and CE.listed(both, "src/a.py")
    assert len(both.extras) == len({e.path for e in both.extras})        # a file two rivals name asks once


def test_summary_counts_questions_and_named_cases_per_setup():
    snaps = [{"questions": {"itemator": 1, "with_overreach": 3, "with_scope_creep_detector": 2, "with_both": 4},
              "rival_files": {"overreach": 2, "scope_creep_detector": 1}}]
    rows = [{"named": {"itemator": False, "with_overreach": True, "with_scope_creep_detector": False, "with_both": True}},
            {"named": {"itemator": True, "with_overreach": True, "with_scope_creep_detector": True, "with_both": True}}]
    v1 = {"summary": {"tools": {"overreach": {"files_named": 5}, "scope_creep_detector": {"files_named": 1}}}}
    s = CE.summarize(rows, snaps, v1)
    assert s["setups"]["itemator"] == {"questions": 1, "cases_named": 1, "wilson95": s["setups"]["itemator"]["wilson95"],
                                       "questions_per_case_named": 1.0}
    assert s["setups"]["with_both"]["questions"] == 4 and s["setups"]["with_both"]["cases_named"] == 2
    assert s["setups"]["with_overreach"]["questions_per_case_named"] == 1.5
    assert s["rerun_check"]["overreach"] == {"files_named_now": 2, "files_named_v1": 5}
    assert "rerun_check" not in CE.summarize(rows, snaps, None)
