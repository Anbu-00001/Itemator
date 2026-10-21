"""The sealed forward test page, built from fixtures and from the committed sealed file."""
import hashlib

from itemator import sealedpage as S


def pr(n_extras=2, url="https://github.com/o/r/pull/1"):
    return {"url": url, "agent": "copilot", "created_at": "2026-10-20T02:09:02Z", "files": ["a", "b", "c"],
            "extras": [{"kind": "tests_removed", "path": f"t{k}.py"} for k in range(n_extras)]}


def test_a_row_links_to_github_and_lists_the_files():
    got = S.row(pr())
    assert '<a href="https://github.com/o/r/pull/1">o/r/pull/1</a>' in got and "<code>t0.py</code>" in got and "3 files changed" in got


def test_only_github_links_are_kept_and_text_is_escaped():
    got = S.row(dict(pr(), url="javascript:alert(1)", agent="<b>x</b>"))
    assert "href" not in got and "&lt;b&gt;x&lt;/b&gt;" in got


def test_long_lists_are_cut_and_counted():
    got = S.row(pr(S.SHOWN + 3))
    assert got.count("<li><code>") == S.SHOWN and "and 3 more" in got
    assert "more" not in S.row(pr(S.SHOWN))


def test_the_page_shows_the_hash_the_predictions_and_no_outcome():
    sealed = {"searched_at": "2026-10-20T20:16:00Z", "summary": {"listed_files": 2, "files": 3, "read_on": "2026-10-25"},
              "pull_requests": [pr()]}
    got = S.page(sealed, "ab" * 32, {"one <b>": "0.70"})
    assert "ab" * 32 in got and "one &lt;b&gt;: 0.70" in got and "2026-10-25" in got and "listed 2 of their 3" in got
    assert "1 agent pull requests" in got
    assert "What we predicted" not in S.page(sealed, "x", {})


def test_the_committed_file_builds_and_its_hash_is_the_sealed_one(tmp_path):
    assert S.main(["--out", str(tmp_path)]) == 0
    html = (tmp_path / "index.html").read_text()
    assert hashlib.sha256(S.SEALED.read_bytes()).hexdigest() in html
    assert "2f66a63deb0ec00b017e509fd93c0c001fb3b735d464e45e3162cacfcc379532" in html     # the hash in the sealing commit's message


def read_fixture(sha="x" * 64):
    files = [{"pr": "https://github.com/o/r/pull/1", "path": "t0.py", "listed": True, "objected": False, "state": "landed", "silent_landing": True},
             {"pr": "https://github.com/o/r/pull/1", "path": "t1.py", "listed": True, "objected": True, "state": "removed", "silent_landing": False},
             {"pr": "javascript:alert(1)", "path": "<b>t2</b>", "listed": True, "objected": False, "state": "landed", "silent_landing": True},
             {"pr": "https://github.com/o/r/pull/1", "path": "t3.py", "listed": True, "objected": False, "state": "removed", "silent_landing": False},
             {"pr": "https://github.com/o/r/pull/1", "path": "a", "listed": False, "objected": False, "state": "landed", "silent_landing": True}]
    return {"sealed_cases_sha256": sha, "read_on": "2026-10-25", "files": files,
            "summary": {"readable": 1, "merged": 1, "closed_unmerged": 0, "open": 0,
                        "listed": {"files": 3, "objected_or_removed": 1}, "unlisted": {"files": 1, "objected_or_removed": 0}}}


def sealed_with(sha="x" * 64):
    return {"summary": {"cases_sha256": sha, "read_on": "2026-10-25"}, "pull_requests": [pr()]}


def test_the_outcome_puts_the_misses_first_and_compares_listed_with_unlisted():
    got = "\n".join(S.outcome(read_fixture(), sealed_with()))
    assert got.index("Misses first") < got.index("objected to or the author removed (2)")
    assert "nobody objected (2)</h3>" in got and "<code>a</code>" not in got and "<code>t0.py</code>" in got and "&lt;b&gt;t2&lt;/b&gt;" in got and "javascript" not in got
    assert "1 of 3 (33%) of the files the rules listed, against 0 of 1 (0%)" in got
    assert "objected · removed" in got and "<code>t3.py</code> <span class=\"m\">removed</span>" in got and "read on 2026-10-25" in got


def test_no_outcome_before_the_read_and_none_for_another_sealed_list():
    assert S.outcome({}, sealed_with()) == []
    got = "\n".join(S.outcome(read_fixture("y" * 64), sealed_with()))
    assert "different sealed list" in got and "t0.py" not in got


def test_the_page_carries_the_outcome_when_given_a_read():
    page = S.page(sealed_with(), "f" * 64, {}, read_fixture())
    assert "Misses first" in page and page.index("What happened") < page.index("The pull requests and what the rules listed")
    assert "Misses first" not in S.page(sealed_with(), "f" * 64, {})


def test_the_committed_sentence_comes_first_and_is_escaped():
    got = "\n".join(S.outcome(dict(read_fixture(), sentence="By 2026-10-25, <b>3</b> of 10."), sealed_with()))
    assert got.index("By 2026-10-25, &lt;b&gt;3&lt;/b&gt; of 10.") < got.index("Of the 1 pull requests")
    assert "eval/prospective_sentences.json" in got
    assert "eval/prospective_sentences.json" not in "\n".join(S.outcome(read_fixture(), sealed_with()))


def test_the_page_says_how_long_before_the_read_the_sentences_were_sealed():
    base = dict(read_fixture(), sentence="x", read_on="2026-10-25")
    assert "sealed on 2026-10-22, 3 days before the read" in "\n".join(S.outcome(dict(base, sentences_frozen_on="2026-10-22"), sealed_with()))
    assert "1 day before the read" in "\n".join(S.outcome(dict(base, sentences_frozen_on="2026-10-24"), sealed_with()))
    assert "before the read" not in "\n".join(S.outcome(dict(base, sentences_frozen_on="soon"), sealed_with()))
