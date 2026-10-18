"""itemator/scanners.py: GitLab's SAST and secret-detection reports joined to the change."""
import json

import pytest

from itemator import checked as C
from itemator import ci
from itemator import scanners as SC


def report(tmp_path, rows, name="gl-sast-report.json"):
    (tmp_path / name).write_text(json.dumps({"version": "15.0.7", "vulnerabilities": rows}))


def row(path, line, severity="High", name="SQL Injection", scanner="Semgrep", end=None):
    loc = {"file": path, "start_line": line}
    if end:
        loc["end_line"] = end
    return {"category": "sast", "name": name, "severity": severity, "scanner": {"id": "semgrep", "name": scanner}, "location": loc}


def change(path, *added_at, status="modified"):
    """A file whose patch adds one line at each given line number."""
    body = "".join(f"@@ -{n},0 +{n},1 @@\n+x = {n}\n" for n in added_at)
    return {"filename": path, "status": status, "patch": body}


def test_a_finding_on_an_added_line_is_introduced_by_the_change(tmp_path):
    report(tmp_path, [row("a.py", 12)])
    d = SC.find(str(tmp_path), [change("a.py", 12)])
    assert [x["line"] for x in d["introduced"]] == [12] and d["touched"] == []


def test_a_finding_elsewhere_in_a_touched_file_is_marked_so(tmp_path):
    report(tmp_path, [row("a.py", 40)])
    d = SC.find(str(tmp_path), [change("a.py", 12)])
    assert d["introduced"] == [] and [x["line"] for x in d["touched"]] == [40]


def test_a_range_that_overlaps_an_added_line_counts(tmp_path):
    report(tmp_path, [row("a.py", 10, end=14)])
    assert len(SC.find(str(tmp_path), [change("a.py", 14)])["introduced"]) == 1
    assert SC.find(str(tmp_path), [change("a.py", 15)])["introduced"] == []


def test_a_finding_in_a_file_the_change_does_not_touch_is_left_out(tmp_path):
    report(tmp_path, [row("other.py", 1)])
    assert SC.find(str(tmp_path), [change("a.py", 1)]) is None


def test_a_removed_file_has_no_lines_to_join(tmp_path):
    report(tmp_path, [row("a.py", 1)])
    assert SC.find(str(tmp_path), [change("a.py", 1, status="removed")]) is None


def test_both_reports_are_read_and_the_most_severe_comes_first(tmp_path):
    report(tmp_path, [row("a.py", 3, "Low", "Weak hash"), row("a.py", 4, "Critical", "Injection")])
    report(tmp_path, [{"category": "secret_detection", "name": "AWS key", "severity": "Critical", "location": {"file": "a.py", "start_line": 2}}],
           "gl-secret-detection-report.json")
    d = SC.find(str(tmp_path), [change("a.py", 2, 3, 4)])
    assert [(x["severity"], x["line"]) for x in d["introduced"]] == [("critical", 2), ("critical", 4), ("low", 3)]
    assert d["introduced"][0]["scanner"] == "secret_detection"


def test_the_extras_list_naming_a_file_is_shown(tmp_path):
    report(tmp_path, [row("a.py", 1), row("b.py", 1)])
    d = SC.find(str(tmp_path), [change("a.py", 1), change("b.py", 1)], {"a.py"})
    assert {x["path"]: x["named"] for x in d["introduced"]} == {"a.py": True, "b.py": False}
    s = SC.sentence(d)
    assert s.count("a file the extras list does not name") == 1 and "`b.py` line 1" in s


@pytest.mark.parametrize("content", ["not json", "[]", '{"vulnerabilities": 3}', '{"version": 1}', '{"vulnerabilities": [{"location": {}}, 5, null]}'])
def test_an_odd_report_gives_nothing(tmp_path, content):
    (tmp_path / "gl-sast-report.json").write_text(content)
    assert SC.find(str(tmp_path), [change("a.py", 1)]) is None


def test_an_unreadable_report_warns_and_a_missing_one_does_not(tmp_path):
    warn = []
    assert SC.find(str(tmp_path), [change("a.py", 1)], warnings=warn) is None and warn == []
    (tmp_path / "gl-sast-report.json").write_text("not json")
    SC.find(str(tmp_path), [change("a.py", 1)], warnings=warn)
    assert warn == ["no scanner join on gl-sast-report.json: the report could not be read"]


def test_an_oversize_report_is_not_read(tmp_path, monkeypatch):
    report(tmp_path, [row("a.py", 1)])
    monkeypatch.setattr(SC, "MAX_BYTES", 10)
    warn = []
    assert SC.find(str(tmp_path), [change("a.py", 1)], warnings=warn) is None and "larger than" in warn[0]


def test_findings_per_report_are_capped(tmp_path, monkeypatch):
    report(tmp_path, [row("a.py", i + 1) for i in range(10)])
    monkeypatch.setattr(SC, "MAX_FINDINGS", 4)
    assert len(SC.read(str(tmp_path))) == 4


def test_the_sentence_names_three_of_each_kind_and_counts_the_rest(tmp_path):
    report(tmp_path, [row("a.py", i + 1) for i in range(5)] + [row("a.py", 100 + i) for i in range(4)])
    d = SC.find(str(tmp_path), [change("a.py", *range(1, 6), 200)])
    s = SC.sentence(d)
    assert s.startswith("GitLab's scanners in this pipeline report 5 on lines this change adds") and "and 2 more" in s and "; and 4 in files this change touches" in s and "and 1 more" in s


def test_names_are_made_safe_for_the_card(tmp_path):
    report(tmp_path, [row("a.py", 1, name="Bad <script>`x`‮ name")])
    assert SC.read(str(tmp_path))[0]["name"] == "Bad script'x' name"


def test_the_card_carries_the_scanner_line_first_among_the_added_line_checks():
    d = {"introduced": [{"path": "a.py", "line": 1, "severity": "high", "name": "n", "scanner": "Semgrep", "named": True}], "touched": []}
    u = [{"path": "c.yml", "line": 1, "kind": "interpreter", "text": ""}]
    s = C.sentence([], [], [], [], None, [], [], None, [], None, None, [], u, d)
    assert s.startswith("Also checked, with no model: GitLab's scanners") and s.index("scanners") < s.index("treat a title")


def test_also_checked_reports_scanner_findings_and_never_changes_the_state(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    report(tmp_path, [row("a.py", 1)])
    r = {"extras": [{"path": "a.py", "detail": []}], "warnings": [], "card": {}, "state": "clean"}
    ci.also_checked(r, str(tmp_path), "b" * 40, "h" * 40, [change("a.py", 1)], None, None)
    assert r["checked"]["scanners"]["introduced"][0]["named"] is True and "GitLab's scanners" in r["card"]["checked_line"] and r["state"] == "clean"


def test_a_report_of_exactly_the_size_limit_is_read(tmp_path, monkeypatch):
    report(tmp_path, [row("a.py", 1)])
    monkeypatch.setattr(SC, "MAX_BYTES", (tmp_path / "gl-sast-report.json").stat().st_size)
    assert len(SC.read(str(tmp_path))) == 1


def test_the_sentence_shows_three_findings_of_a_kind(tmp_path):
    report(tmp_path, [row("a.py", i + 1) for i in range(5)])
    s = SC.sentence(SC.find(str(tmp_path), [change("a.py", *range(1, 6))]))
    assert s.count("`a.py` line") == 3


def test_a_finding_with_only_a_message_and_no_severity_is_still_joined(tmp_path):
    (tmp_path / "gl-sast-report.json").write_text(json.dumps({"vulnerabilities": [{"message": "Hard-coded key", "location": {"file": "a.py", "start_line": 1}}]}))
    d = SC.find(str(tmp_path), [change("a.py", 1)])["introduced"][0]
    assert (d["name"], d["severity"], d["scanner"]) == ("Hard-coded key", "unknown", "scanner")
