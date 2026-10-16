"""The maintainer study's summary of two labellers' readings (eval/maintainer_summary.py)."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import maintainer_summary as M  # noqa: E402


def test_key_of_takes_either_packet_form():
    assert M.key_of("C__247146__3656108151.json", 3656108151) == ("C", "gitlab-org/gitlab!247146", 3656108151)
    assert M.key_of("C__247146", "3656108151") == ("C", "gitlab-org/gitlab!247146", 3656108151)
    assert M.key_of("C__247146.json", 1) == ("C", "gitlab-org/gitlab!247146", 1)


def test_load_reads_every_chunk_of_one_labeller(tmp_path):
    for name, model, label in (("L3_notes_a", "m3", "other"), ("L3_notes_b", None, "unsure"), ("L4_notes_a", "m4", "other")):
        (tmp_path / f"{name}.json").write_text(json.dumps({"model": model, "labels": [{"packet": "G__1", "note_id": len(name) + ord(name[-1]), "label": label}]}))
    got, model = M.load(tmp_path, "L3")
    assert model == "m3" and sorted(e["label"] for e in got.values()) == ["other", "unsure"]


def test_lists_a_file_or_a_directory_that_holds_it():
    extras = [{"path": "app/a.rb"}, {"path": "spec/"}, {"path": "lib"}]
    assert M.lists("app/a.rb", extras)
    assert M.lists("spec/x_spec.rb", extras)
    assert not M.lists("lib/b.rb", extras)
    assert not M.lists("app/a.rb.orig", extras)


def test_note_file():
    assert M.note_file("app/a.rb", {"file": "x"}, {"file": "y"}) == "app/a.rb"
    assert M.note_file(None, {"file": "x"}, {"file": "x"}) == "x"
    assert M.note_file(None, {"file": "x"}, {"file": "y"}) is None
    assert M.note_file(None, {"file": None}, {"file": None}) is None


def test_summary():
    g1, g2, h, c = ("gitlab-org/gitlab!" + n for n in ("1", "2", "3", "4"))
    frame = {"counts": {"G": {"merge_requests": 2}, "H": {"merge_requests": 1}, "C": {"merge_requests": 1}},
             "notes": [{"ref": g1, "note_id": 10, "path": "app/x.rb", "candidate": True},
                       {"ref": g1, "note_id": 11, "path": None, "candidate": True},
                       {"ref": g1, "note_id": 12, "path": "app/v.rb", "candidate": True},
                       {"ref": g2, "note_id": 20, "path": "app/z.rb", "candidate": True},
                       {"ref": h, "note_id": 30, "path": "app/y.rb", "candidate": True},
                       {"ref": h, "note_id": 31, "path": "app/w.rb", "candidate": True},
                       {"ref": c, "note_id": 40, "path": None, "candidate": False},
                       {"ref": c, "note_id": 41, "path": None, "candidate": False}]}
    lab = lambda label, file=None: {"label": label, "file": file}
    l3 = {("G", g1, 10): lab("scope_request"), ("G", g1, 11): lab("scope_request", "app/x.rb"), ("G", g1, 12): lab("scope_request"),
          ("G", g2, 20): lab("scope_request"), ("H", h, 30): lab("scope_request"), ("H", h, 31): lab("scope_request"),
          ("C", c, 40): lab("scope_request"), ("C", c, 41): lab("other"), ("G", g2, 21): lab("other")}
    l4 = {("G", g1, 10): lab("scope_request"), ("G", g1, 11): lab("scope_request", "app/x.rb"), ("G", g1, 12): lab("scope_request"),
          ("G", g2, 20): lab("other"), ("H", h, 30): lab("scope_request"), ("H", h, 31): lab("scope_request"),
          ("C", c, 40): lab("scope_request"), ("C", c, 41): lab("other"), ("H", h, 32): lab("other")}
    cards = {("G", g1): [{"path": "app/x.rb"}], ("H", h): [{"path": "app/y.rb"}, {"path": "app/w.rb"}]}
    final = {g1: set(), h: {"app/w.rb"}}
    s = M.summarize(l3, l4, frame, lambda pop, ref: cards.get((pop, ref), []), lambda ref: final.get(ref, set()),
                    lambda ref: {"app/x.rb"} if ref == g1 else set())
    a = s["agreement"]
    assert (a["notes"], a["only_one_labeller"], a["same_label"]) == (8, 2, 7)
    assert a["kappa"] == 0.6
    assert a["labels"] == {"L3": {"scope_request": 7, "other": 1}, "L4": {"scope_request": 6, "other": 2}}
    assert a["disputed"] == [{"pop": "G", "ref": g2, "note_id": 20, "L3": "scope_request", "L4": "other"}]
    p = s["per_population"]
    assert p["G"] == {"merge_requests": 2, "with_a_scope_request": 1, "wilson95": [0.095, 0.905], "either_labeller": 2}
    assert p["H"]["with_a_scope_request"] == 1 and p["C"]["with_a_scope_request"] == 0
    assert s["control"] == {"notes": 2, "both_scope_request": 1}
    assert [(r["ref"], r["note_id"], r["file"], r["candidate"]) for r in s["scope_requests"]] == [
        (c, 40, None, False), (g1, 10, "app/x.rb", True), (g1, 11, "app/x.rb", True), (g1, 12, "app/v.rb", True), (h, 30, "app/y.rb", True), (h, 31, "app/w.rb", True)]
    assert s["files"]["G"] == {"files": 2, "in_final_diff": 0, "card_listed": 1,
                               "rows": [{"ref": g1, "file": "app/v.rb", "in_final_diff": False, "card_listed": False, "in_agent_version": False},
                                        {"ref": g1, "file": "app/x.rb", "in_final_diff": False, "card_listed": True, "in_agent_version": True}]}
    assert {k: v for k, v in s["files"]["H"].items() if k != "rows"} == {"files": 2, "in_final_diff": 1, "card_listed": 1}
    assert "in_agent_version" not in s["files"]["H"]["rows"][0]
