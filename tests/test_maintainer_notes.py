"""The maintainer study's frame: which notes count as a reviewer's, which the word filter picks, and the control draw."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import maintainer_notes as M  # noqa: E402


def note(i, user, body="Please remove this change.", **kw):
    return {"id": i, "author": {"username": user}, "body": body, **kw}


def test_the_word_filter():
    for text in ("Can we remove this?", "Please revert the lockfile", "This is unrelated to the issue", "out of scope here",
                 "Could you move it to a separate MR?", "Let's split this out", "This is not needed", "unnecessary change",
                 "Do this in a follow-up", "Why is this here?", "why did we change the timeout"):
        assert M.SCOPE.search(text), text
    for text in ("LGTM", "Nice, thanks!", "Please add a test for the nil case", "removal", "This scoped label", "Why not?"):
        assert not M.SCOPE.search(text), text


def test_only_other_peoples_notes_count():
    mr = {"author": {"username": "alice"}}
    notes = [note(1, "alice"), note(2, "bob"), note(3, "gitlab-bot"), note(4, "duo-developer-gitlab-org"), note(5, "GitLabDuo"),
             note(6, "carol", system=True), note(7, "dave", body="  "), note(8, "project_278964_bot_1"), note(9, "erin")]
    assert [n["id"] for n in M.reviewer_notes(mr, notes)] == [2, 9]


def test_a_diff_notes_path():
    assert M.note_path({"type": "DiffNote", "position": {"new_path": "app/a.rb"}}) == "app/a.rb"
    assert M.note_path({"type": None, "position": {"new_path": "app/a.rb"}}) is None and M.note_path({"type": "DiffNote"}) is None


def test_rows_frame_and_control():
    a1 = [{"pop": "G", "version": "agent", "ref": "g!1"}, {"pop": "G", "version": "merged", "ref": "g!1"},
          {"pop": "G", "version": "agent", "ref": "g!2", "excluded": "no agent-only version"},
          {"pop": "H", "version": "merged", "ref": "h!3"}, {"pop": "F", "version": "agent", "ref": "f!4"}]
    a2 = [{"pop": "C", "version": "merged", "ref": "c!5"}]
    rows = M.rows_of(a1, a2)
    assert [(r["pop"], r["ref"], r["version"]) for r in rows] == [("G", "g!1", "agent"), ("H", "h!3", "merged"), ("C", "c!5", "merged")]
    notes = {"g!1": [note(10, "bob"), note(11, "bob", "LGTM", type="DiffNote", position={"new_path": "x.rb"})],
             "h!3": [note(12, "zed", "Thanks")], "c!5": []}
    out, counts = M.frame(rows, lambda r: {"author": {"username": "alice"}}, lambda r: notes[r["ref"]])
    assert counts == {"G": {"merge_requests": 1, "reviewer_notes": 2, "candidates": 1},
                      "H": {"merge_requests": 1, "reviewer_notes": 1, "candidates": 0},
                      "C": {"merge_requests": 1, "reviewer_notes": 0, "candidates": 0}}
    assert [(x["note_id"], x["candidate"], x["path"]) for x in out] == [(10, True, None), (11, False, "x.rb"), (12, False, None)]
    many = [{"note_id": i, "candidate": i % 3 == 0} for i in range(400)]
    drawn = M.control(many, 50)
    assert len(drawn) == 50 and not any(x["candidate"] for x in drawn) and drawn == M.control(many, 50)
    assert [x["note_id"] for x in drawn] == sorted(x["note_id"] for x in drawn)
    assert len(M.control(many[:6], 50)) == 4
