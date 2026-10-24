"""The card's pipeline line (itemator/pipeline.py): what a change does to the project's merged CI configuration."""
import pytest

from itemator import checked as C
from itemator import ci
from itemator import pipeline as PL

BASE = '''---
variables:
  A: '1'
".hidden":
  stage: test
secret_detection:
  stage: test
  allow_failure: false
  script:
  - "/analyzer run"
  - echo "a folded
    line"
unit-tests:
  image: python:3.12
  script:
  - pytest
'''
HEAD = BASE.replace("allow_failure: false", "allow_failure: true")


def test_paths_that_can_change_the_pipeline():
    for p in (".gitlab-ci.yml", "sub/.gitlab-ci.yml", "ci/itemator-job.yml", ".gitlab/ci/test.yml", "x.gitlab-ci.yml"):
        assert PL.is_ci_path(p), p
    for p in ("README.md", "src/ci.py", "ci/notes.txt", "docs/.gitlab-ci.yaml.md", "gitlab-ci.yml"):
        assert not PL.is_ci_path(p), p


def test_blocks_cut_the_merged_text_by_job_and_key():
    b = PL.blocks(BASE)
    assert list(b) == ["variables", ".hidden", "secret_detection", "unit-tests"]
    assert b["secret_detection"]["allow_failure"] == "false"
    assert b["secret_detection"]["script"].count("\n") == 3 and "folded" in b["secret_detection"]["script"]   # list items and the folded line stay with their key
    assert b["variables"] == {"A": "'1'"}


def test_a_check_turned_into_a_warning_is_named_with_both_values():
    d = PL.diff(BASE, HEAD)
    assert d["added"] == [] and d["removed"] == [] and d["global"] == []
    assert d["changed"] == [{"job": "secret_detection", "parts": ["allow_failure"], "values": {"allow_failure": ("false", "true")}}]
    assert "`secret_detection`: allow_failure (false to true)" in PL.sentence(d)


def test_added_removed_and_global_changes():
    head = BASE.replace("unit-tests:", "tests-renamed:").replace("A: '1'", "A: '2'") + "deploy:\n  script:\n  - ./push\n"
    d = PL.diff(BASE, head)
    assert d["added"] == ["deploy", "tests-renamed"] and d["removed"] == ["unit-tests"] and d["global"] == ["variables"]
    s = PL.sentence(d)
    assert "new jobs `deploy`, `tests-renamed`" in s and "removed job `unit-tests`" in s and "global settings: `variables`" in s
    assert s.endswith("Jobs that a pipeline execution policy adds are not in this view.")


def test_a_global_key_that_appears_or_goes_is_global_never_a_job():
    d = PL.diff(BASE, BASE.replace("variables:\n  A: '1'\n", "workflow:\n  rules:\n  - when: always\n"))
    assert d["added"] == [] and d["removed"] == [] and d["global"] == ["variables", "workflow"]


def test_the_same_configuration_has_no_diff():
    assert PL.empty(PL.diff(BASE, BASE))
    assert PL.empty(PL.diff(BASE, BASE + "\n\n"))                       # blank lines are not a change


def test_a_job_that_gains_a_key_is_changed():
    d = PL.diff(BASE, BASE.replace("  image: python:3.12\n", "  image: python:3.12\n  rules:\n  - when: never\n"))
    assert d["changed"] == [{"job": "unit-tests", "parts": ["rules"], "values": {}}]


def test_many_jobs_are_capped_and_counted():
    head = BASE + "".join(f"j{i}:\n  script:\n  - x\n" for i in range(5))
    s = PL.sentence(PL.diff(BASE, head))
    assert s.count("`j") == 3 and "and 2 more" in s


class Lint:
    def __init__(self, *answers):
        self.answers, self.paths = list(answers), []

    def get(self, path, missing_ok=False):    # noqa: ARG002 -- the signature of ci.Api.get
        self.paths.append(path)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def files(*names):
    return [{"filename": n, "status": "modified"} for n in names]


def test_no_lint_call_when_no_ci_file_changed():
    api, warn = Lint(), []
    assert PL.find(api, 7, "b" * 40, "h" * 40, files("src/a.py"), warn) is None and api.paths == [] and warn == []


def test_the_merge_base_and_the_head_are_both_read():
    api, warn = Lint({"valid": True, "merged_yaml": BASE}, {"valid": True, "merged_yaml": HEAD}), []
    d = PL.find(api, 7, "b" * 40, "h" * 40, files(".gitlab-ci.yml"), warn)
    assert d is not None and d["changed"][0]["job"] == "secret_detection" and warn == []
    assert api.paths == [f"/projects/7/ci/lint?content_ref={'b' * 40}&include_jobs=true", f"/projects/7/ci/lint?content_ref={'h' * 40}&include_jobs=true"]


def test_an_invalid_configuration_is_not_compared_even_when_it_carries_text():
    warn = []
    api = Lint({"valid": False, "errors": ["x"], "merged_yaml": BASE}, {"valid": True, "merged_yaml": HEAD})
    assert PL.find(api, 7, "b", "h", files(".gitlab-ci.yml"), warn) is None and warn and "invalid" in warn[0]


def test_an_unchanged_pipeline_gives_nothing():
    api = Lint({"valid": True, "merged_yaml": BASE}, {"valid": True, "merged_yaml": BASE})
    assert PL.find(api, 7, "b", "h", files("ci/x.yml"), []) is None


@pytest.mark.parametrize("answer", [ci.JobError("GET /x returned HTTP 401"), {"valid": False, "errors": ["x"]}, ["not a dict"], {"valid": True}])
def test_a_lint_that_cannot_be_read_warns_and_says_nothing(answer):
    warn = []
    assert PL.find(Lint(answer), 7, "b", "h", files(".gitlab-ci.yml"), warn) is None
    assert len(warn) == 1 and warn[0].startswith("no pipeline check")


def test_the_card_sentence_carries_the_pipeline_line_and_keeps_its_order():
    d = PL.diff(BASE, HEAD)
    s = C.sentence(["a.py"], [("t/x.xz", "xz file")], [], [], d)
    assert s is not None and s.index("changed only in layout") < s.index("The project's pipeline") < s.index("Opened `t/x.xz`")
    assert str(C.sentence([], [], [], [], d)).startswith("Also checked, with no model: The project's pipeline")
    assert C.sentence([], [], [], [], None) is None


def test_also_checked_puts_the_pipeline_in_the_report_and_never_changes_the_state(tmp_path):
    report = {"extras": [], "warnings": [], "card": {}}
    api = Lint({"valid": True, "merged_yaml": BASE}, {"valid": True, "merged_yaml": HEAD})
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    ci.also_checked(report, str(tmp_path), "b" * 40, "h" * 40, files(".gitlab-ci.yml"), api, 7)
    assert report["checked"]["pipeline"]["changed"][0]["job"] == "secret_detection"
    assert "The project's pipeline" in report["card"]["checked_line"]
    report2 = {"extras": [], "warnings": [], "card": {}}
    ci.also_checked(report2, str(tmp_path), "b" * 40, "h" * 40, files(".gitlab-ci.yml"), None, None)
    assert report2["checked"]["pipeline"] is None and "checked_line" not in report2["card"]


@pytest.mark.parametrize("version,cves", [
    ("19.4.1", ["CVE-2026-97229", "CVE-2026-110264"]), ("19.4.2", ["CVE-2026-110264"]), ("19.4.3", []),
    ("19.3.5", ["CVE-2026-110264"]), ("19.3.6-ee", []), ("19.2.7", ["CVE-2026-97229", "CVE-2026-110264"]), ("19.2.9", []),
    ("19.5.0", ["CVE-2026-110264"]), ("19.5.1", []), ("19.6.0-pre", []), ("18.11.12", ["CVE-2026-110264"]), ("18.11.13", []),
    ("19.0.9", ["CVE-2026-110264"]), ("19.1.9", []), ("6.9.0", []), ("7.0.0", ["CVE-2026-110264"]), ("19.10.0", []),
    ("19.3.5-internal0", ["CVE-2026-110264"]), ("v19.4.1", ["CVE-2026-97229", "CVE-2026-110264"]),
])
def test_the_lint_guard_follows_gitlabs_patch_notes_at_each_edge(version, cves):
    got = PL.unsafe_server(version)
    assert (got["cves"] if got else []) == cves


@pytest.mark.parametrize("version", ["19.4", "nineteen", "19.4.1.2", "1x.4.1"])
def test_a_version_the_guard_cannot_read_is_not_asked(version):
    assert PL.unsafe_server(version) == {"version": version, "cves": []}


def test_no_version_means_no_guard():
    assert PL.unsafe_server(None) is None and PL.unsafe_server("  ") is None


def test_an_unsafe_gitlab_is_never_sent_the_ci_file_and_the_card_says_why():
    api, warn = Lint(), []
    d = PL.find(api, 7, "b" * 40, "h" * 40, files(".gitlab-ci.yml"), warn, "19.4.1")
    assert api.paths == [] and d == {"skipped": {"version": "19.4.1", "cves": ["CVE-2026-97229", "CVE-2026-110264"]}}
    assert warn == ["no pipeline check: GitLab 19.4.1 is in the range of CVE-2026-97229, CVE-2026-110264"]
    s = PL.sentence(d)
    assert s.startswith("The job did not ask GitLab to merge the pipeline configuration: GitLab's patch notes list 19.4.1")
    assert "CVE-2026-97229 and CVE-2026-110264" in s and s.endswith("Upgrade GitLab to read it.")
    unread = PL.sentence(PL.find(Lint(), 7, "b", "h", files(".gitlab-ci.yml"), [], "19.4"))
    assert "cannot read this GitLab's version (19.4)" in unread


def test_a_patched_gitlab_is_asked_as_before():
    api = Lint({"valid": True, "merged_yaml": BASE}, {"valid": True, "merged_yaml": HEAD})
    assert PL.find(api, 7, "b", "h", files(".gitlab-ci.yml"), [], "19.6.0-pre")["changed"] and len(api.paths) == 2


def test_no_ci_file_changed_needs_no_guard_either():
    warn = []
    assert PL.find(Lint(), 7, "b", "h", files("src/a.py"), warn, "19.4.1") is None and warn == []


def test_also_checked_passes_the_server_version_and_run_reads_it_from_the_job(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    report = {"extras": [], "warnings": [], "card": {}}
    api = Lint()
    ci.also_checked(report, str(tmp_path), "b" * 40, "h" * 40, files(".gitlab-ci.yml"), api, 7, server_version="19.4.1")
    assert api.paths == [] and report["checked"]["pipeline"]["skipped"]["version"] == "19.4.1"
    assert "did not ask GitLab" in report["card"]["checked_line"] and report["extras"] == []
    assert 'env.get("CI_SERVER_VERSION")' in open(ci.__file__).read()
