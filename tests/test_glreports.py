"""itemator/glreports.py: the job's record as GitLab Code Quality and Metrics reports."""
import json

from itemator import glreports as G


def extra(kind="stray_file", path="install-python.sh", name="install-python.sh", anchor=None, registry=None):
    e = {"kind": kind, "path": path, "name": name, "why": "the issue does not ask for it",
         "anchor": anchor if anchor is not None else {"old_path": path, "new_path": path, "old_line": None, "new_line": 7},
         "plain_facts": {"kind": kind}}
    if registry is not None:
        e["plain_facts"]["registry"] = registry
    return e


def weighed(packages, bytes_, ok="ok"):
    return {"packages": [{"name": "x", "weight": {"weight": ok, "packages": packages, "bytes": bytes_}}]}


def test_each_extra_is_one_info_finding_on_its_thread_line():
    got = G.codequality({"extras": [extra(), extra("ci_or_config", ".gitlab-ci.yml", ".gitlab-ci.yml",
                                                   {"old_path": ".gitlab-ci.yml", "new_path": None, "old_line": 4, "new_line": None})]})
    assert [(f["location"]["path"], f["location"]["lines"]["begin"], f["check_name"], f["severity"]) for f in got] == [
        ("install-python.sh", 7, "itemator/stray_file", "info"), (".gitlab-ci.yml", 4, "itemator/ci_or_config", "info")]
    assert got[0]["description"] == ("Extra beyond the issue: install-python.sh (the issue does not ask for it). "
                                     "Reply in its thread: its exact name to keep it, `remove` to drop it.")
    assert len({f["fingerprint"] for f in got}) == 2 and all(len(f["fingerprint"]) == 64 for f in got)


def test_an_extra_without_a_line_sits_on_line_one_of_its_path():
    f = G.codequality({"extras": [extra(path="docs/", name="docs/", anchor={})]})[0]
    assert f["location"] == {"path": "docs/", "lines": {"begin": 1}}


def test_a_grouped_extra_sits_where_its_thread_does():
    f = G.codequality({"extras": [extra(path="docs/", name="docs/", anchor={"old_path": "docs/a.md", "new_path": "docs/a.md", "new_line": 3})]})[0]
    assert f["location"] == {"path": "docs/a.md", "lines": {"begin": 3}}


def test_the_fingerprint_is_stable_across_runs_and_differs_by_name():
    a = G.codequality({"extras": [extra()]})[0]["fingerprint"]
    assert a == G.codequality({"extras": [extra(anchor={"new_path": "install-python.sh", "new_line": 9})]})[0]["fingerprint"]
    assert a != G.codequality({"extras": [extra(name="other")]})[0]["fingerprint"]


def test_a_decision_from_another_project_is_in_the_finding_so_the_widget_shows_it():
    e = extra(name="scratch.bak", path="scratch.bak")
    e["plain_facts"]["decided_before"] = {"decision": "removed", "iid": 17, "who": "lee", "on": "2026-10-11",
                                          "project": "team/one", "differ": [{"decision": "kept", "iid": 14}]}
    d = G.codequality({"extras": [e]})[0]["description"]
    assert d.endswith("Decided in team/one: removed on team/one!17 by lee on 2026-10-11 (its public answer log)."
                      " Earlier answers differ: kept on team/one!14.")
    assert "Decided" not in G.codequality({"extras": [extra()]})[0]["description"]


def test_no_extras_is_an_empty_report():
    assert G.codequality({"extras": []}) == G.codequality({}) == []
    assert G.metrics({}) == "itemator_extras 0\nitemator_new_dependencies 0\nitemator_unasked_dependencies_weighed 0\n"


def test_metrics_add_up_only_the_weighed_dependencies():
    r = {"extras": [extra(), extra("new_dependency", "requirements.txt", "pandas", registry=weighed(6, 30562008)),
                    extra("new_dependency", "package.json", "lodash", registry=weighed(1, 319000)),
                    extra("new_dependency", "package.json", "left", registry=weighed(9, 10**9, ok="unavailable")),
                    extra("new_dependency", "go.mod", "x/y")]}
    assert G.metrics(r).splitlines() == ["itemator_extras 5", "itemator_new_dependencies 4", "itemator_unasked_dependencies_weighed 2",
                                         "itemator_unasked_dependency_packages 7", "itemator_unasked_dependency_download_mb 30.9",
                                         "itemator_unasked_dependency_co2e_g_per_install_low 0.015",
                                         "itemator_unasked_dependency_co2e_g_per_install_high 2"]


def test_the_command_writes_both_files(tmp_path):
    rec = tmp_path / "itemator.json"
    rec.write_text(json.dumps({"extras": [extra()]}))
    assert G.main([str(rec), "--codequality", str(tmp_path / "cq.json"), "--metrics", str(tmp_path / "m.txt")]) == 0
    assert json.loads((tmp_path / "cq.json").read_text())[0]["check_name"] == "itemator/stray_file"
    assert (tmp_path / "m.txt").read_text().startswith("itemator_extras 1\n")
