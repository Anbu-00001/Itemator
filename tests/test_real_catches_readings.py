"""eval/real_catches_readings.py: the reading column of results/real_catches.md, counted."""
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("rcr", ROOT / "eval" / "real_catches_readings.py")
RCR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RCR)


def test_only_case_rows_are_counted_by_their_last_cell():
    page = ("| Pull request | Agent | File | What | Words | Reading |\n|---|---|---|---|---|---|\n"
            "| [a#1](u) | X | `f` | w | [\"not needed\"](u) | asks to take it out |\n"
            "| [a#2](u) | X | `g` | w | [\"why?\"](u) | unclear |\n"
            "| [a#3](u) | X | `h` | w | [\"later\"](u) | does not ask to take it out |\n"
            "| Legend | asks to take it out |\n")
    assert RCR.count(page) == {"asks_to_take_it_out": 1, "does_not_ask": 1, "unclear": 1, "rows": 3}


def test_the_committed_counts_match_the_page_and_cover_every_case():
    got = RCR.count((ROOT / "results" / "real_catches.md").read_text())
    assert json.loads((ROOT / "results" / "real_catches_readings.json").read_text())["summary"] == got
    assert got["rows"] == json.loads((ROOT / "results" / "real_catches_v1.json").read_text())["summary"]["read"]
