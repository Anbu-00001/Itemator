"""eval/name_match.py sorts how an issue names a package; no network, no data."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import name_match as N  # noqa: E402


def dep(name):
    return [{"filename": "requirements.txt", "status": "modified", "patch": f"@@ -1,0 +1,1 @@\n+{name}==1.0\n"}]


def test_how_named_sorts_code_package_context_and_bare():
    assert N.how_named("Please use `requests` here", "requests") == "code"
    assert N.how_named("```\nimport requests\n```", "requests") == "code"
    assert N.how_named("Install the requests library", "requests") == "package_context"
    assert N.how_named("pin requests>=2.31", "requests") == "package_context"
    assert N.how_named("Handle more requests per second", "requests") == "bare"
    assert N.how_named("a b c d requests", "requests") == "bare"
    assert N.how_named("library a b c requests", "requests") == "bare"            # a package word more than WINDOW words away


def test_silenced_lists_what_the_issue_words_hid():
    assert N.silenced("Handle more requests per second", dep("requests")) == ["requests"]
    assert N.silenced("Fix the typo", dep("requests")) == []
    assert N.silenced("", dep("requests")) == []


def test_the_committed_result_counts_its_rows():
    import json
    d = json.loads(N.OUT.read_text())
    assert d["silenced"] == len(d["rows"]) and sum(d["by_how_named"].values()) == d["silenced"] and d["pull_requests"] == 300
    assert d["prs_with_a_bare_silencing"] == len({r["pr_url"] for r in d["rows"] if r["named"] == "bare"})
