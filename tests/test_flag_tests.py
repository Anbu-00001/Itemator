"""The count of the replay's test-removal flags that come with a deleted feature flag (eval/flag_tests.py)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import flag_tests as T  # noqa: E402


def f(name, status="modified", patch=""):
    return {"filename": name, "status": status, "patch": patch}


def test_deleted_flag_definitions():
    files = [f("config/feature_flags/beta/my_flag.yml", "removed"), f("ee/config/feature_flags/wip/other_flag.yml", "removed"),
             f("config/feature_flags/beta/new_flag.yml", "added"), f("config/feature_flags/kept.yml", "removed"),
             f("doc/feature_flags/x.yml", "removed"), f("config/feature_flags/beta/y.yaml", "removed")]
    assert T.deleted_flags(files) == {"my_flag", "other_flag", "kept"}


def test_only_tests_that_name_a_deleted_flag_count():
    spec = f("spec/a_spec.rb", patch="--- a/spec/a_spec.rb\n-  stub_feature_flags(my_flag: false)\n-  it 'works' do\n+  x\n")
    other = f("spec/b_spec.rb", patch="-  it 'old' do\n")
    header = f("spec/c_spec.rb", patch="--- my_flag\n-  it 'x' do\n")
    files = [f("config/feature_flags/beta/my_flag.yml", "removed"), spec, other, header]
    extras = [{"kind": "tests_removed", "path": "spec/a_spec.rb"}, {"kind": "tests_removed", "path": "spec/b_spec.rb"},
              {"kind": "tests_removed", "path": "spec/c_spec.rb"}, {"kind": "ci_or_config", "path": "spec/a_spec.rb"},
              {"kind": "tests_removed", "path": "spec/missing_spec.rb"}]
    assert T.flag_tests(files, extras) == [extras[0]]
    assert T.flag_tests(files[1:], extras) == []
    assert T.flag_tests([f("config/feature_flags/beta/my_flag_v2.yml", "removed"), spec], extras) == []
    longer = f("spec/a_spec.rb", patch="-  stub_feature_flags(my_flag_v2: false)\n")
    assert T.flag_tests([files[0], longer], extras[:1]) == []


def test_summary():
    rows = [{"extras": [{"kind": "tests_removed", "path": "s.rb"}, {"kind": "ci_or_config", "path": "c.yml"}]},
            {"extras": [{"kind": "tests_removed", "path": "t.rb"}]}]
    files = {0: [f("config/feature_flags/a/fl.yml", "removed"), f("s.rb", patch="- fl\n")], 1: [f("t.rb", patch="- fl\n")]}
    got = T.summarize(rows, lambda r: files[rows.index(r)])
    assert got == {"merge_requests": 2, "deletes_a_flag_definition": 1, "extras": 3, "tests_removed": 2, "tests_naming_a_deleted_flag": 1}
