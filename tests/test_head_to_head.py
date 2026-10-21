"""The head-to-head with two offline scope checkers: the pure parts of eval/head_to_head.py."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import head_to_head as H  # noqa: E402

FILES = [{"filename": "src/a.py", "status": "modified", "patch": "@@ -1 +1 @@\n-x\n+y"},
         {"filename": "install.sh", "status": "added", "patch": "@@ -0,0 +1 @@\n+curl x"},
         {"filename": "old.txt", "status": "removed", "patch": None}]


def test_the_diff_has_a_header_per_file_and_marks_added_and_removed():
    d = H.unified_diff(FILES)
    assert d.count("diff --git ") == 3
    assert "--- /dev/null\n+++ b/install.sh\nnew file mode" not in d          # mode line comes before the --- line
    assert "new file mode 100644\n--- /dev/null\n+++ b/install.sh\n@@ -0,0 +1 @@" in d
    assert "deleted file mode 100644\n--- a/old.txt\n+++ /dev/null" in d
    assert "--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@" in d
    assert H.unified_diff([{"filename": None, "status": "added", "patch": "x"}]) == "\n"   # a row with no filename is skipped


def test_overreach_names_only_its_findings_not_its_advice():
    out = {"findings": [{"file": "install.sh"}, {"kind": "x"}], "blast_radius": {"warnings": [{"files": ["package.json"]}]}}
    assert H.overreach_named(out) == {"install.sh"}
    assert H.overreach_advice(out) == {"package.json"}
    assert H.overreach_named(None) == set() and H.overreach_advice(None) == set()


def test_the_scope_creep_detector_names_everything_outside_in_scope():
    out = {"in_scope": [{"path": "src/a.py"}], "likely_creep": [{"path": "install.sh"}], "config_edits": [{"path": "ci.yml"}],
           "new_deps": [{"file": "package.json", "name": "left-pad"}, "bare-string"], "api_renames": []}
    assert H.scd_named(out) == {"install.sh", "ci.yml", "package.json"}
    assert H.scd_named(None) == set()


def test_wilson_matches_a_known_value_and_handles_zero():
    assert H.wilson(27, 587) == [0.032, 0.066]                                 # the recall study's interval
    assert H.wilson(0, 0) == [0.0, 0.0]


def test_the_summary_counts_cases_files_density_and_disagreements():
    rows = [{"named": {"itemator": True, "overreach": False, "scope_creep_detector": True}},
            {"named": {"itemator": False, "overreach": True, "scope_creep_detector": True}}]
    snaps = [{"changed": 5, "named": {"itemator": 1, "overreach": 2, "scope_creep_detector": 4}, "errors": {"overreach": True}},
             {"changed": 3, "named": {"itemator": 1, "overreach": 0, "scope_creep_detector": 2}, "errors": {}}]
    s = H.summarize(rows, snaps)
    assert (s["cases"], s["snapshots"], s["files_changed"]) == (2, 2, 8)
    i, o, c = (s["tools"][t] for t in H.TOOLS)
    assert (i["cases_named"], i["files_named"], i["density"]) == (1, 2, 0.5)
    assert (o["cases_named"], o["files_named"], o["errors"], o["median_named_per_snapshot"]) == (1, 2, 1, 1.0)
    assert (c["cases_named"], c["files_named"], c["density"]) == (2, 6, 0.333)
    assert (o["only_this_not_itemator"], o["only_itemator_not_this"]) == (1, 1)
    assert (c["only_this_not_itemator"], c["only_itemator_not_this"]) == (1, 0)
