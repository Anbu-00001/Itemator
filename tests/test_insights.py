"""T47: .gitlab/insights.yml names only labels that the two flows really apply, and charts only documented keys."""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILE = ROOT / ".gitlab" / "insights.yml"
FLOWS = ROOT / "flows"


def needs_files():
    if not FILE.exists() or not FLOWS.exists():
        pytest.skip("no .gitlab/insights.yml or flows/ in this copy")


def labels_in(text):
    return set(re.findall(r"itemator::[a-z-]+", text))


def test_every_label_in_the_charts_is_one_a_flow_applies():
    needs_files()
    applied = set()
    for f in FLOWS.glob("*.yml"):
        applied |= labels_in(f.read_text())
    charted = labels_in("\n".join(l for l in FILE.read_text().splitlines() if not l.lstrip().startswith("#")))
    assert charted and charted <= applied, sorted(charted - applied)


def test_every_label_a_flow_applies_is_charted_or_a_known_exception():
    needs_files()
    applied = set()
    for f in FLOWS.glob("*.yml"):
        applied |= labels_in(f.read_text())
    charted = labels_in(FILE.read_text())
    assert applied <= charted, sorted(applied - charted)


def test_only_documented_keys_and_values_are_used():
    needs_files()
    text = FILE.read_text()
    assert "data_source: issuables" in text and "issuable_type: merge_request" in text
    assert set(re.findall(r"^\s+type: (\S+)", text, re.M)) <= {"bar", "line", "stacked-bar"}
    assert set(re.findall(r"group_by: (\S+)", text)) <= {"day", "week", "month"}
    assert set(re.findall(r"issuable_state: (\S+)", text)) <= {"opened", "closed", "locked", "merged", "all"}
    assert all(1 <= int(n) <= 52 for n in re.findall(r"period_limit: (\d+)", text))


def test_the_file_parses_as_yaml_when_a_parser_is_here():
    needs_files()
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(FILE.read_text())
    assert list(doc) == ["itemator"] and all("query" in c and "title" in c for c in doc["itemator"]["charts"])
