"""results/real_catches.md (eval/real_catches_page.py): the pure parts, and that the committed page matches the study."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import real_catches_page as P  # noqa: E402

PR = "https://github.com/o/r/pull/7"


def case(path, outcome, kind=None):
    return {"key": f"{PR}#{path}", "pr": PR, "path": path, "agent": "OpenAI_Codex", "kind": kind, "outcome": outcome}


def study(*cases):
    return {"read_on": "2026-10-19", "summary": {"read": len(cases), "file_removed": 1, "closed_unmerged": 0, "landed_with_the_file": 1},
            "cases": list(cases)}


def test_quote_drops_quoted_lines_and_code_and_cuts_at_a_word():
    body = "> old text\nPlease remove `x`.\n```\ncode here\n```\n" + "word " * 60
    q = P.quote(body)
    assert "old text" not in q and "code here" not in q and q.startswith("Please remove 'x'.")
    assert q.endswith(" ...") and len(q) <= P.QUOTE + 4 and not q[:-4].endswith(" ")


def test_a_long_quote_ends_on_a_whole_word():
    q = P.quote("abcdefghij " * 30)
    assert q.endswith("abcdefghij ...") and q.count("abcdefghij") == P.QUOTE // 11


def test_an_empty_comment_reads_as_not_readable():
    page = P.render(study(case("a", "file_removed")), {f"{PR}#a": {"body": "", "html_url": "https://c/1"}}, {})
    assert "(comment not readable)" in page and "https://c/1" not in page


def test_quote_escapes_a_table_bar():
    assert P.quote("a | b") == "a \\| b"


def test_a_short_comment_is_kept_whole():
    assert P.quote("not needed") == "not needed"


def test_reason_drops_the_file_list():
    assert P.reason("11 files whose changes are whitespace only (x): a.go, b.go") == "11 files whose changes are whitespace only (x)"
    assert P.reason(None) is None


def test_rows_go_under_their_outcome_with_the_rules_reason_and_the_reading():
    s = study(case("a/x.png", "file_removed", "binary"), case("b/y.yml", "landed_with_the_file"))
    page = P.render(s, {f"{PR}#a/x.png": {"body": "this file is not needed", "html_url": "https://c/1"}},
                    {f"{PR}#a/x.png": "yes"}, {f"{PR}#b/y.yml": "Changes CI config; the issue does not mention it"})
    removed, landed = page.split("## Taken out")[1].split("## Pull request closed")[0], page.split("## Merged")[1]
    assert "`x.png` | a binary file | [\"this file is not needed\"](https://c/1) | asks to take it out |" in removed
    assert "`y.yml` | Changes CI config; the issue does not mention it | (comment not readable) | not read |" in landed
    assert "| OpenAI Codex |" in removed and "## Pull request closed without merging (0)" in page


def test_the_counts_come_from_the_study():
    page = P.render(study(case("a", "file_removed")), {}, {})
    assert "Of 1 files, 1 were taken out, 0 sat in pull requests closed without merging, and 1 landed with the file." in page


def test_an_unread_case_is_counted():
    page = P.render(study(case("a", None)), {}, {})
    assert "1 more could not be read." in page


def test_the_committed_page_has_every_case_of_the_study():
    s = json.loads((ROOT / "results" / "real_catches_v1.json").read_text())
    page = (ROOT / "results" / "real_catches.md").read_text()
    assert page.count("\n| [") == s["summary"]["read"]
    for o in P.ORDER:
        assert f"({s['summary'][o]})" in page.split(P.HEADING[o])[1].split("\n")[0]
