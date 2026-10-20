"""The GitLab scope-comment study's own parts (eval/gitlab_scope.py): which notes count as people's, how a note is tied
to a file, how the labellers' lines are read and combined, and which diff version a note is scored against."""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import gitlab_scope as S  # noqa: E402


def note(who, body="x", system=False, path=None, nid=1):
    n = {"id": nid, "author": {"username": who}, "system": system, "body": body, "created_at": "2026-09-01T00:00:00Z"}
    if path:
        n["type"], n["position"] = "DiffNote", {"new_path": path}
    return n


def test_only_people_other_than_the_author_count():
    mr = {"author": {"username": "alice"}}
    kept = S.human_notes(mr, [note("alice"), note("bob", system=True), note("review-bot"), note("duo-developer-gitlab-org"),
                              note("carol", path="Gemfile", nid=7)])
    assert [(k["author"], k["file"], k["note_id"]) for k in kept] == [("carol", "Gemfile", 7)]


def test_a_general_note_is_tied_to_a_file_only_when_it_names_exactly_one():
    paths = ["Gemfile", "app/models/user.rb"]
    assert S.tie({"file": "x.rb", "body": "Gemfile"}, paths) == "x.rb"
    assert S.tie({"file": None, "body": "why is `Gemfile` changed?"}, paths) == "Gemfile"
    assert S.tie({"file": None, "body": "Gemfile and app/models/user.rb"}, paths) is None
    assert S.tie({"file": None, "body": "looks good"}, paths) is None


def test_the_keyword_route_matches_leg_ones_phrases_ignoring_case():
    assert S.keyword("This is UNRELATED to the issue") and S.keyword("please open a separate MR")
    assert not S.keyword("this is related") and not S.keyword("needed")


def write_reports(tmp, h, s, adj=None):
    (tmp / "L-H-01-01.md").write_text("STATUS: done\n" + "\n".join(h) + "\nCOUNTS x\n")
    (tmp / "L-S-01-01.md").write_text("STATUS: done\n" + "\n".join(s) + "\n")
    if adj is not None:
        (tmp / "ADJ.md").write_text("STATUS: done\n" + "\n".join(adj) + "\n")


def test_labels_are_read_from_note_lines_and_a_note_labelled_twice_is_an_error(tmp_path):
    write_reports(tmp_path, ['NOTE 1 | yes | Gemfile | "not needed here"', "`NOTE 2 | no | - | -`", "NOTE 3 | maybe | - | -"],
                  ["NOTE 1 | yes | - | -"])
    got = S.labels(tmp_path, "H")
    assert got == {1: {"answer": "yes", "file": "Gemfile", "quote": '"not needed here"'}, 2: {"answer": "no", "file": "-", "quote": "-"}}
    (tmp_path / "L-H-02-02.md").write_text("NOTE 2 | yes | - | -\n")
    with pytest.raises(AssertionError):
        S.labels(tmp_path, "H")


def test_agreement_stands_and_a_split_takes_the_adjudicators_answer(tmp_path):
    write_reports(tmp_path, ["NOTE 1 | yes | a | q", "NOTE 2 | yes | b | q", "NOTE 3 | no | - | -"],
                  ["NOTE 1 | yes | a | q", "NOTE 2 | no | - | -", "NOTE 3 | no | - | -"],
                  ["NOTE 2 | no | - | agrees: sonnet | a style comment", "NOTE 3 | yes | c | agrees: neither | sample only"])
    final = S.final_labels(tmp_path, tmp_path)
    assert final[1] == {"answer": "yes", "by": "both", "file": "a"}
    assert final[2] == {"answer": "no", "by": "adjudicator", "file": "-"}
    assert final[3]["answer"] == "no" and final[3]["by"] == "both"      # the sample re-read audits, it does not relabel


def test_a_split_with_no_adjudication_stops_the_scoring(tmp_path):
    write_reports(tmp_path, ["NOTE 1 | yes | a | q"], ["NOTE 1 | no | - | -"], [])
    with pytest.raises(AssertionError):
        S.final_labels(tmp_path, tmp_path)


def test_a_note_is_scored_against_the_newest_version_made_before_it(monkeypatch):
    versions = [{"id": 1, "created_at": "2026-09-01T00:00:00Z"}, {"id": 3, "created_at": "2026-09-03T00:00:00Z"},
                {"id": 2, "created_at": "2026-09-02T00:00:00Z"}]
    def get(path):
        return versions if path.endswith("/versions") else {"id": int(path.rsplit("/", 1)[1])}
    monkeypatch.setattr(S.G, "get", get)
    monkeypatch.setattr(S.G, "rebuilt", lambda pid, d: d)
    assert S.version_at(5, "2026-09-02T12:00:00Z")["id"] == 2
    assert S.version_at(5, "2026-09-03T00:00:00Z")["id"] == 3
    assert S.version_at(5, "2026-08-01T00:00:00Z")["id"] == 1          # older than every version: the oldest
    monkeypatch.setattr(S.G, "get", lambda path: [])
    assert S.version_at(5, "2026-09-02T00:00:00Z") is None


def test_the_adjudication_file_holds_every_split_and_every_seventh_note(tmp_path):
    items = [{"position": n, "iid": 9, "state": "closed", "title": "t", "author": "bob", "file": None, "changed_paths": ["a"],
              "body": f"note {n}"} for n in range(1, 16)]
    (tmp_path / "sample.json").write_text(json.dumps(items))
    write_reports(tmp_path, [f"NOTE {n} | {'yes' if n == 3 else 'no'} | - | -" for n in range(1, 16)],
                  [f"NOTE {n} | no | - | -" for n in range(1, 16)])
    r = S.adjudication(tmp_path, tmp_path)
    assert r["split"] == [3] and r["sample"] == [7, 14] and r["agree"] == 14 and r["missing"] == {"H": [], "S": []}
    heads = [line for line in r["lines"] if line.startswith("## Note")]
    assert heads == ["## Note 3", "## Note 7 (sample)", "## Note 14 (sample)"]
