"""itemator/catchespage.py: the real-catches page says only what results/real_catches.md says."""
import re

from itemator import catchespage as C

STUDY = C.parse(C.SOURCE.read_text(encoding="utf-8"))


def test_every_case_of_the_study_is_one_card():
    counts = [int(re.search(r"\((\d+)\)$", s["heading"]).group(1)) for s in STUDY["sections"]]
    assert [len(s["rows"]) for s in STUDY["sections"]] == counts and sum(counts) == 24
    assert C.page(STUDY).count("<article>") == 24
    assert "csharp-sdk#645" in C.page(STUDY)


def test_the_studys_own_caveat_is_on_the_page():
    out = C.page(STUDY)
    assert "This is not a catch rate" in out and "the reviewers saw no card" in out


def test_text_is_escaped_and_only_github_or_repo_links_survive():
    got = C.inline('[x](javascript:alert(1)) [ok](https://github.com/a/b) <b> `<i>` [r](../eval/x.json)')
    assert "javascript" not in got and "<b>" not in got and "<code>&lt;i&gt;</code>" in got
    assert '<a href="https://github.com/a/b">ok</a>' in got and f'<a href="{C.REPO}eval/x.json">r</a>' in got


def test_a_row_with_the_wrong_number_of_cells_is_left_out():
    md = "# T\n\nintro\n\n## A (1)\n\n| a | b | c | d | e | f |\n| --- | --- | --- | --- | --- | --- |\n| 1 | 2 | 3 | 4 | 5 | 6 |\n| short | row |\n"
    s = C.parse(md)
    assert s["intro"] == ["intro"] and [r["agent"] for r in s["sections"][0]["rows"]] == ["2"]


def test_the_page_builds(tmp_path):
    assert C.main(["--out", str(tmp_path)]) == 0
    assert (tmp_path / "index.html").read_text().startswith("<!doctype html>")
