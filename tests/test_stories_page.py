"""eval/stories_page.py: one story per outcome, the longest wait among comments that ask to take the file out."""
import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location("stories_page", pathlib.Path(__file__).parent.parent / "eval" / "stories_page.py")
SP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SP)

HEAD = "| Pull request | Agent | File | What the rules say | Reviewer's words | Reading |\n|---|---|---|---|---|---|\n"


def row(pr, f, reading="asks to take it out", agent="Copilot"):
    return (f"| [o/r#{pr}](https://github.com/o/r/pull/{pr}) | {agent} | `{f}` | Adds a thing | "
            f"[\"not needed\"](https://github.com/o/r/pull/{pr}#discussion_r1) | {reading} |\n")


PAGE = ("# Real cases\n\n| Legend | asks to take it out |\n" + row(9, "intro.md") + "\n## Other notes\n\n" + row(8, "z.md")
        + "\n## Taken out of the pull request (3)\n\n" + HEAD
        + row(1, "a.md") + row(2, "dir/b.md") + row(3, "c.md", reading="unclear")
        + "\n## Pull request closed without merging (2)\n\n" + HEAD + row(4, "d.cpp") + row(5, "e.cpp")
        + "\n## Merged (or still open) with the file in it (1)\n\n" + HEAD + row(6, "f.toml", agent="OpenAI_Codex"))


def timing(h=None):
    cases = [{"pr": f"https://github.com/o/r/pull/{n}", "path": p, "hours": v}
             for (n, p), v in {(1, "a.md"): 2.0, (2, "x/dir/b.md"): 30.0, (3, "c.md"): 99.0, (4, "d.cpp"): 5.0,
                               (5, "e.cpp"): 5.0, (6, "f.toml"): 150.04, **(h or {})}.items()]
    return {"summary": {"read": 6, "median_hours": 5.0, "over_24h": 3}, "cases": cases}


C = "https://github.com/o/r/pull/{}#discussion_r1"
WHOLE = {C.format(n): {"subject_type": "file", "original_line": 1} for n in range(1, 10)}


def test_rows_are_read_by_section_and_rows_outside_the_three_sections_are_not():
    rs = SP.rows(PAGE)
    assert [(r["outcome"], r["file"]) for r in rs] == [
        ("removed", "a.md"), ("removed", "dir/b.md"), ("removed", "c.md"), ("closed", "d.cpp"), ("closed", "e.cpp"),
        ("landed", "f.toml")]
    assert rs[5]["agent"] == "OpenAI Codex" and rs[0]["comment"].endswith("#discussion_r1") and rs[0]["quote"] == "not needed"


def test_the_longest_wait_among_asks_to_take_it_out_and_a_tie_keeps_the_first():
    told = SP.pick(SP.rows(PAGE), SP.hours_of(timing()), WHOLE)
    assert [(t["outcome"], t["file"], t["hours"]) for t in told] == [
        ("removed", "dir/b.md", 30.0), ("closed", "d.cpp", 5.0), ("landed", "f.toml", 150.04)]


def test_a_case_with_no_hours_is_skipped_and_an_outcome_with_none_left_tells_no_story():
    told = SP.pick(SP.rows(PAGE), SP.hours_of(timing({(6, "f.toml"): None, (2, "x/dir/b.md"): None})), WHOLE)
    assert [(t["outcome"], t["file"]) for t in told] == [("removed", "a.md"), ("closed", "d.cpp")]


def test_merged_and_still_open_are_told_apart_and_long_waits_are_in_days():
    page = SP.render(PAGE, timing(), WHOLE, {"cases": [{"pr": "https://github.com/o/r/pull/6", "merged": True}]})
    assert "merged with the file still changed" in page and "150 hours (6.3 days)" in page and "30 hours (1.2 days)" not in page
    assert "30.0 hours" in page and "The file was taken out" in page and "closed without merging" in page
    page = SP.render(PAGE, timing(), WHOLE, {"cases": [{"pr": "https://github.com/o/r/pull/6", "merged": False}]})
    assert "still open with the file in it" in page and "merged with" not in page
    assert "the 6 real cases" in page and "was 5.0 hours; 3 waited" in page


def test_only_comments_on_the_whole_file_tell_a_story_and_a_missing_outcome_is_said():
    scope = dict(WHOLE)
    scope[C.format(2)] = {"subject_type": "line", "original_line": 7}       # about one line: not told
    scope[C.format(1)] = {"subject_type": "line", "original_line": 1}       # on the first line: about the whole file
    scope[C.format(6)] = {"subject_type": "line", "original_line": 24}
    scope[C.format(4)] = {"subject_type": "file", "original_line": None}    # a file comment with no line
    told = SP.pick(SP.rows(PAGE), SP.hours_of(timing()), scope)
    assert [(t["outcome"], t["file"]) for t in told] == [("removed", "a.md"), ("closed", "d.cpp")]
    page = SP.render(PAGE, timing(), scope)
    assert "No story for: merged (or still open) with the file in it." in page and "f.toml" not in page
    assert "No story for" not in SP.render(PAGE, timing(), WHOLE)
    assert SP.pick(SP.rows(PAGE), SP.hours_of(timing()), {}) == []
