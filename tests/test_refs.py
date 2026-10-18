"""itemator/refs.py: the commits a change cites must exist, and a quoted title must be that commit's title."""
import subprocess

import pytest

from itemator import checked as C
from itemator import ci
from itemator import refs as RF

REAL = "1a2b3c4d5e6f"


class Api:
    """Answers GET /projects/7/repository/commits/<id>: {id: title}; any other id is a 404; ids in `down` raise."""
    def __init__(self, known=None, down=()):
        self.known, self.down, self.asked = known or {}, set(down), []

    def get(self, path, missing_ok=False):
        h = path.rsplit("/", 1)[-1]
        self.asked.append(h)
        if h in self.down:
            raise ci.JobError("HTTP 500")
        if h in self.known:
            return {"id": h, "title": self.known[h]}
        if missing_ok:
            return None
        raise ci.JobError("HTTP 404")


@pytest.fixture
def repo(tmp_path):
    def g(*a):
        return subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=a@b.c", "-c", "user.name=t", "-c", "commit.gpgsign=false", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    g("init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("a")
    g("add", "-A")
    g("commit", "-qm", "Keep the connection alive")
    return tmp_path, g("rev-parse", "HEAD")


def test_the_ways_a_commit_is_cited():
    text = (f"Fixes: {REAL} (\"Keep the connection alive\")\n\nThis reverts commit {'ab12cd34' * 5}.\n"
            f"(cherry picked from commit deadbee1)\nSee commit 9f8e7d6c5 for why.\n")
    got = {d["id"]: (d["how"], d["quoted"]) for d in RF.cited(text)}
    assert got == {REAL: ("fixes", "Keep the connection alive"), "ab12cd34" * 5: ("revert", None), "deadbee1": ("cherry-pick", None), "9f8e7d6c5": ("commit", None)}
    assert [d["id"] for d in RF.cited(text)][0] == REAL                                   # in order of first mention
    later = f"first see commit 9f8e7d6c5, then\nFixes: {REAL} (\"x\")"
    assert [d["id"] for d in RF.cited(later)] == ["9f8e7d6c5", REAL]


def test_words_and_short_ids_are_not_citations():
    assert RF.cited("the commit defaced is bad; commit abc12; Fixes: abc123") == []
    assert RF.cited("commit decadeed") == []                                                # seven or more letters and no digit: a word
    assert RF.cited("commit decadeed12") != []


def test_one_id_cited_twice_is_read_once_in_its_most_specific_form():
    got = RF.cited(f"Fixes: {REAL} (\"x\")\nand commit {REAL} again")
    assert len(got) == 1 and got[0]["how"] == "fixes"


def test_titles_agree_when_one_starts_with_the_other():
    assert RF.same_title("Keep the connection alive", "Keep the connection alive")
    assert RF.same_title("keep the connection", "Keep the connection alive!")          # a tool truncated it
    assert RF.same_title("Keep the connection alive (v2)", "Keep the connection alive")
    assert not RF.same_title("Remove the socket", "Keep the connection alive")
    assert not RF.same_title("", "Keep the connection alive")


def test_a_commit_that_exists_in_the_checkout_is_fine_and_the_api_is_not_asked(repo):
    path, sha = repo
    api = Api()
    assert RF.find(str(path), f"Fixes: {sha[:12]} (\"Keep the connection alive\")", api, 7, []) == [] and api.asked == []


def test_a_commit_the_checkout_lacks_but_the_api_knows_is_fine():
    api = Api({REAL: "Keep the connection alive"})
    assert RF.find("/nonexistent", f"This reverts commit {REAL}", api, 7, []) == [] and api.asked == [REAL]


def test_a_commit_nobody_has_is_missing(repo):
    path, _ = repo
    got = RF.find(str(path), f"This reverts commit {REAL}", Api(), 7, [])
    assert got == [{"id": REAL, "how": "revert", "kind": "missing", "quoted": None, "title": None}]
    assert "`1a2b3c4d5e6f` (as the commit it reverts) is not a commit of this project" in RF.sentence(got)


def test_a_quoted_title_that_is_another_commits_is_named_with_both(repo):
    path, sha = repo
    got = RF.find(str(path), f"Fixes: {sha[:12]} (\"Remove the socket\")", Api(), 7, [])
    assert got == [{"id": sha[:12], "how": "fixes", "kind": "title_differs", "quoted": "Remove the socket", "title": "Keep the connection alive"}]
    s = RF.sentence(got)
    assert "quoted as \"Remove the socket\"" in s and "titled \"Keep the connection alive\"" in s


def test_an_api_that_cannot_answer_says_nothing_and_warns(repo):
    path, _ = repo
    warn = []
    assert RF.find(str(path), f"This reverts commit {REAL}", Api(down={REAL}), 7, warn) == []
    assert warn and REAL[:12] in warn[0]
    before = len(warn)
    assert RF.find(str(path), f"This reverts commit {REAL}", None, 7, warn) == [] and len(warn) == before      # no API at all: nothing is claimed, nothing to warn about


def test_at_most_a_fixed_number_of_ids_are_looked_up(repo, monkeypatch):
    path, _ = repo
    text = "\n".join(f"commit {i:07x}f1" for i in range(1, 40))
    api = Api()
    RF.find(str(path), text, api, 7, [])
    assert len(api.asked) == RF.MAX_CITED


def test_the_card_sentence_lists_three_and_counts_the_rest():
    found = [{"id": f"{i:012x}", "how": "commit", "kind": "missing", "quoted": None, "title": None} for i in range(5)]
    s = RF.sentence(found)
    assert s.count("is not a commit of this project") == 3 and s.endswith("and 2 more.")
    out = C.sentence([], [], cites=found)
    assert out is not None and out.startswith("Also checked, with no model: The commit messages or the description cite")
    assert C.sentence([], [], cites=[]) is None


def test_stable_style_upstream_lines_are_their_own_kind():
    h = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
    for text in (f"commit {h} upstream.", f"[ Upstream commit {h} ]"):
        assert [(c["id"], c["how"]) for c in RF.cited(text)] == [(h, "upstream")]
    assert RF.cited(f"commit {h} fixed this")[0]["how"] == "commit"
    assert RF.sentence([{"id": h[:12], "how": "upstream", "kind": "missing", "quoted": None, "title": None}]).count("as the upstream commit") == 1
