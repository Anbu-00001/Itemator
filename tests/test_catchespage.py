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


TIMING_FILE = {"summary": {"read": 2, "median_hours": 4.5, "over_24h": 1},
               "cases": [{"pr": "https://github.com/NVIDIA/cuda-python/pull/884", "path": "docs/logo-dark-mode.png", "hours": 4.5},
                         {"pr": "https://github.com/go-vikunja/vikunja/pull/1358", "path": "example-force-availability.yml", "hours": 1.0},
                         {"pr": "https://github.com/x/y/pull/1", "path": "z", "hours": None}]}


def test_cards_with_a_known_wait_say_it_and_the_intro_gives_the_median(tmp_path):
    f = tmp_path / "t.json"
    f.write_text(__import__("json").dumps(TIMING_FILE))
    t = C.load_timing(f)
    out = C.page(STUDY, t)
    assert out.count("Objection came") == 2
    assert "Objection came 4.5 hours after the pull request opened." in out and "Objection came 1 hour after" in out
    assert "The median wait from a pull request opening to the reviewer&#x27;s objection was 4.5 hours (1 of 2 waited" in out


def test_a_missing_or_broken_timing_file_leaves_the_page_as_before(tmp_path):
    assert C.load_timing(tmp_path / "none.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert C.load_timing(bad) == {}
    out = C.page(STUDY, C.load_timing(bad))
    assert "Objection came" not in out and "median wait" not in out and out.count("<article>") == 24


def test_the_real_timing_file_reaches_every_card():
    out = C.page(STUDY, C.load_timing())
    assert out.count("Objection came") == 24 and "median wait" in out


def test_the_built_file_carries_the_waits(tmp_path):
    C.main(["--out", str(tmp_path)])
    assert (tmp_path / "index.html").read_text().count("Objection came") == 24
