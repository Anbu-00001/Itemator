"""The wide card (itemator/ci.py wide): past WIDE listed files in two or more threads, the card asks one question."""
import datetime
import importlib.util
import pathlib

from itemator import ci
from itemator import precedent as PRE
from itemator.extras import Analysis, Extra

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("aidev_recall", ROOT / "eval" / "aidev_recall.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def added(path):
    return {"filename": path, "status": "added", "patch": "@@ -0,0 +1 @@\n+x"}


def strays(n, start=0):
    # each in its own directory, so group_extras leaves them as separate threads
    return [Extra("stray_file", f"d{i}/m.py", f"d{i}/m.py", "a file the issue does not ask for") for i in range(start, start + n)]


def kept(extras):
    return [((e, ()), None) for e in extras]


def test_eleven_listed_files_in_two_or_more_threads_become_one_question_with_every_file():
    ex = strays(11)
    files = [added(e.path) for e in ex]
    (e, items), registry = ci.wide(kept(ex), files)
    assert (e.kind, e.name, e.detail, items, registry) == ("too_wide", "all-11-files", tuple(f["filename"] for f in files), tuple(ex), None)
    assert ci._label(e) == "too wide, 11 files"
    rec = ci.describe_extra(e, {f["filename"]: f for f in files}, items)
    assert rec["anchor"] is not None and rec["plain_facts"]["detail_count"] == 11
    assert ci.answers(e, items, {f["filename"]: f for f in files}, always=True) == ()        # only its name or `not an extra`
    stub = rec["thread_stub"]
    assert "`split`" not in stub and "`remove`" not in stub and "`always`" not in stub and "`not an extra`" in stub
    assert "d10/m.py" in stub and "In smaller merge requests each file gets its own thread" in stub


def test_ten_files_or_one_thread_stay_as_they_were():
    ex = strays(10)
    assert ci.wide(kept(ex), [added(e.path) for e in ex]) is None
    paths = tuple(f"vendor/f{i}.bin" for i in range(30))
    mass = Extra("binary_or_large_added", "vendor/", "vendor/", "30 binary files added under vendor/", paths)
    assert ci.wide(kept([mass]), [added(p) for p in paths]) is None                           # a mass event is one question already
    assert ci.wide(kept([mass, *strays(1)]), [added(p) for p in paths] + [added("d0/m.py")])[0][0].name == "all-31-files"


def test_only_twenty_names_are_written_and_the_rest_are_counted():
    ex = strays(25)
    e = ci.wide(kept(ex), [added(x.path) for x in ex])[0][0]
    assert "d19/m.py, and 5 more." in ci.thread_stub(e, offers=()) and "d20/m.py" not in ci.thread_stub(e, offers=())
    assert len(e.detail) == 25


def test_a_file_counts_as_listed_exactly_as_the_forward_test_counts_it():
    ex = [Extra("new_dependency", "requirements.txt", "leftpad-py", "adds package leftpad-py"),
          Extra("build_output_added", "dist/", "dist/", "build output", ("dist/a.js", "dist/b.js")),
          Extra("ci_or_config", "x/", "x/", "3 config files changed under x/", ("x/1.yml", "x/2.yml", "x/3.yml")),
          *strays(2)]
    files = [added(p) for p in ("requirements.txt", "dist/a.js", "dist/b.js", "dist/c.js", "x/1.yml", "x/2.yml", "x/3.yml",
                                "d0/m.py", "d1/m.py", "src/other.py", "README.md")]
    assert ci.listed_files(ex, files) == [f["filename"] for f in files if R.listed(ex, f["filename"])]
    assert "dist/c.js" in ci.listed_files(ex, files) and "src/other.py" not in ci.listed_files(ex, files)


def test_the_card_asks_to_split_or_keep_every_one_by_its_name():
    e = ci.wide(kept(strays(12)), [added(x.path) for x in strays(12)])[0][0]
    c = ci.card_lines("extras", [{"ref": "#5"}], [e], [], [])
    assert c["final_line"] == "12 files beyond #5, too many to ask about one by one."
    assert "Split this merge request into smaller ones, or type `all-12-files` in its thread to keep every one." in c["todo_line"]
    assert c["todo_line"].endswith(ci.CONSENT)
    assert ci.card_lines("extras", [{"ref": "#5"}], strays(2), [], [])["final_line"].startswith("2 things beyond #5")


def test_facts_give_one_thread_for_a_wide_merge_request(monkeypatch):
    ex = strays(12)
    files = [added(e.path) for e in ex]
    monkeypatch.setattr(ci.X, "analyse", lambda *_, **__: Analysis(ex, unplaced=[]))
    monkeypatch.setattr(ci.AFTER, "ADDERS", ())
    issues = [{"iid": 5, "ref": "#5", "title": "t", "description": "d", "author_id": 1}]
    r = ci.facts(mr_iid=7, mr_title="t", mr_description="", mr_author_id=2, issues=issues, issues_from="closes_issues",
                 files=files, repo=None, base_sha="a" * 40, head_sha="b" * 40, warnings=[],
                 now=datetime.datetime(2026, 10, 22, tzinfo=datetime.timezone.utc))
    assert [x["name"] for x in r["extras"]] == ["all-12-files"] and r["state"] == "extras"
    assert ci.group_extras([Extra("stray_file", f"src/m{i}.py", f"src/m{i}.py", "w") for i in range(12)])[0][0].name == "src/"   # one directory: one thread already
    assert r["card"]["final_line"].startswith("12 files beyond #5")
    monkeypatch.setattr(ci, "WIDE", 12)
    r = ci.facts(mr_iid=7, mr_title="t", mr_description="", mr_author_id=2, issues=issues, issues_from="closes_issues",
                 files=files, repo=None, base_sha="a" * 40, head_sha="b" * 40, warnings=[],
                 now=datetime.datetime(2026, 10, 22, tzinfo=datetime.timezone.utc))
    assert len(r["extras"]) == 12


def test_decided_before_never_matches_the_wide_thread_whose_name_is_only_a_count(monkeypatch):
    asked = []
    monkeypatch.setattr(PRE, "find", lambda log, names, iid: asked.append(list(names)) or {})
    stub = {"name": "all-12-files", "kind": "too_wide", "thread_stub": "s", "plain_facts": {}}
    other = {"name": "d0/m.py", "kind": "stray_file", "thread_stub": "s", "plain_facts": {}}
    PRE.apply({"extras": [stub, other]}, {"ITEMATOR_ANSWERS_URL": "https://x.invalid/a.json"}, 7, get=lambda u: {})
    assert asked == [["d0/m.py"]] and stub["thread_stub"] == "s"
