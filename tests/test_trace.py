"""itemator/trace.py: the path of every changed file through the checks, as JSON."""
import json
import subprocess

import pytest

from itemator import neutral as N
from itemator import trace as T


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=t", *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "tidy.py").write_text("x=1\ndef f( a ):\n  return a\n")
    (tmp_path / "app.py").write_text("print(1)\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "work")
    (tmp_path / "tidy.py").write_text("x = 1\n\n\ndef f(a):\n    return a  # same\n")
    (tmp_path / "app.py").write_text("print(1)\nprint(2)\n")
    (tmp_path / "requirements.txt").write_text("requests==2.0\n")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "change")
    return tmp_path


def run(repo, tmp_path, *argv):
    out = tmp_path / "trace.json"
    code = T.main(["--repo", str(repo), "--out", str(out), *argv])
    return code, json.loads(out.read_text()) if out.exists() else None


def test_each_file_lands_in_one_bin_with_its_route(repo, tmp_path):
    code, d = run(repo, tmp_path, "--issue-text", "Print 2 in app.py")
    assert code == 0 and d["schema"] == 2
    by = {f["path"]: f for f in d["files"]}
    assert by["requirements.txt"]["landing"] == "listed"
    assert by["logo.png"]["landing"] == "listed"                               # a committed binary is itself an extra
    assert by["tidy.py"]["landing"] == "neutral"
    assert by["app.py"]["landing"] == "ordinary"
    assert d["totals"] == {"listed": 2, "opened": 0, "neutral": 1, "noted": 0, "ordinary": 1}
    assert [s["check"] for s in by["app.py"]["route"]] == ["request", "extras", "neutral", "unwrap", "history", "fence"]
    assert by["app.py"]["route"][0]["outcome"] == "pass"                       # app.py is named by the request
    assert by["app.py"]["route"][2]["outcome"] == "not_proved"                 # a body edit: nothing proved
    assert by["logo.png"]["route"][3]["outcome"] == "hit" and "PNG" in by["logo.png"]["route"][3]["say"].upper()
    assert by["tidy.py"]["route"][2]["outcome"] == "hit"
    assert by["requirements.txt"]["route"][2]["outcome"] == "not_applicable"


def test_a_listed_file_stays_listed_even_when_the_opener_read_it(repo, tmp_path):
    assert T.landing("listed", None, object()) == "listed"
    assert T.landing("none", None, object()) == "opened"
    assert T.landing("none", N.Verdict(N.NOT_PROVED, "x"), None) == "ordinary"
    assert T.landing("none", N.Verdict(N.REORDERED, "x"), None) == "neutral"


def test_the_same_inputs_give_the_same_file(repo, tmp_path):
    a = run(repo, tmp_path, "--issue-text", "Print 2 in app.py")[1]
    b = run(repo, tmp_path, "--issue-text", "Print 2 in app.py")[1]
    assert a == b
    assert a["source"]["head_sha"] == git(repo, "rev-parse", "HEAD").strip() and len(a["source"]["input_sha256"]) == 64
    assert a["source"]["base_sha"] == git(repo, "rev-parse", "main").strip()


def test_commits_flag_and_unknown_ref(repo, tmp_path, capsys):
    assert run(repo, tmp_path, "--commits")[0] == 0
    assert T.main(["--repo", str(repo), "--base", "nope", "--out", str(tmp_path / "x.json")]) == 2
    assert "unknown commit" in capsys.readouterr().err


def test_the_rules_say_listed_is_not_ordinary_and_ordinary_is_not_safe(repo, tmp_path):
    d = run(repo, tmp_path, "--issue-text", "x")[1]
    ordinary = [f for f in d["files"] if f["landing"] == "ordinary"][0]
    assert "safe" not in json.dumps(ordinary).lower()


def test_route_outcomes_and_sentences_for_each_placement():
    assert T.route("none", [], None, None)[0]["outcome"] == "not_matched"
    assert T.route("unplaced", [], None, None)[0]["outcome"] == "not_matched"
    assert T.route("named", [], None, None)[0]["outcome"] == "pass"
    listed = T.route("listed", ["new_dependency"], None, None)
    assert (listed[1]["outcome"], listed[1]["say"]) == ("hit", "listed as: new_dependency")
    assert T.route("named", [], None, None)[1] == {"check": "extras", "outcome": "pass", "say": "no extras rule lists it"}


def test_input_hash_is_the_hash_of_the_binary_diff(repo, tmp_path):
    import hashlib
    d = run(repo, tmp_path, "--issue-text", "x")[1]
    diff = subprocess.run(["git", "-C", str(repo), "diff", "--find-renames", "--binary", d["source"]["base_sha"], d["source"]["head_sha"]], capture_output=True).stdout
    assert d["source"]["input_sha256"] == hashlib.sha256(diff).hexdigest()
    (repo / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x01" * 40)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "again")
    assert run(repo, tmp_path, "--issue-text", "x", "--base", d["source"]["base_sha"])[1]["source"]["input_sha256"] != d["source"]["input_sha256"]


# ---- the two history stations (itemator/cochange.py, itemator/fence.py)

FENCED = [{"path": "a.py", "lines": 2, "commit": "abcd1234", "subject": "Fix crash"}]


def test_history_steps_for_every_case():
    h = lambda path, status, labels, fenced=(): {s["check"]: (s["outcome"], s["say"]) for s in T.history_steps(path, status, labels, list(fenced))}
    assert h("a.py", "modified", {"a.py": "stranger"})["history"][0] == "hit"
    assert h("a.py", "modified", {"a.py": "partnered"})["history"][0] == "pass"
    assert h("a.py", "modified", {"a.py": "too_new"})["history"] == ("not_applicable", "fewer than three earlier commits: nothing to compare yet")
    assert h("a.py", "modified", {})["history"][0] == "not_applicable"
    assert h("a.py", "added", {"a.py": "stranger"})["history"] == ("not_applicable", "only modified files have a history to compare")
    assert h("a.py", "modified", {}, FENCED)["fence"] == ("hit", '2 deleted line(s) added by abcd1234, "Fix crash"')
    assert h("b.py", "modified", {}, FENCED)["fence"][0] == "pass"
    assert h("b.py", "added", {}, FENCED)["fence"][0] == "not_applicable"


def test_a_history_hit_lands_in_noted_but_never_ahead_of_a_stronger_bin():
    hit = [{"check": "history", "outcome": "hit", "say": "x"}, {"check": "fence", "outcome": "pass", "say": "y"}]
    miss = [{"check": "history", "outcome": "pass", "say": "x"}, {"check": "fence", "outcome": "pass", "say": "y"}]
    assert T.landing("none", N.Verdict(N.NOT_PROVED, "x"), None, hit) == "noted"
    assert T.landing("none", N.Verdict(N.NOT_PROVED, "x"), None, miss) == "ordinary"
    assert T.landing("none", None, None, None) == "ordinary"
    assert T.landing("listed", None, None, hit) == "listed"
    assert T.landing("none", None, object(), hit) == "opened"
    assert T.landing("none", N.Verdict(N.REORDERED, "x"), None, hit) == "neutral"


def test_a_file_that_never_changed_with_the_others_lands_in_noted(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    for i in range(3):
        for names in (("a.py", "b.py"), ("c.py", "d.py"), ("e.py",)):
            for n in names:
                (tmp_path / n).write_text(f"v{i}\n")
            git(tmp_path, "add", ".")
            git(tmp_path, "commit", "-qm", f"edit {names} {i}")
    git(tmp_path, "checkout", "-qb", "work")
    for n in "abcde":
        (tmp_path / f"{n}.py").write_text("changed\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "change")
    d = run(tmp_path, tmp_path, "--issue-text", "x")[1]
    by = {f["path"]: f for f in d["files"]}
    assert by["e.py"]["landing"] == "noted" and by["e.py"]["route"][4]["outcome"] == "hit"
    assert by["a.py"]["landing"] == "ordinary" and by["a.py"]["route"][4]["outcome"] == "pass"
    assert d["totals"]["noted"] == 1
