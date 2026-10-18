"""eval/mesa_noise.py: sampling, reading commits and counting what the checks say, on a small real git repository."""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import mesa_noise as MN  # noqa: E402
from tests.test_reland import Repo  # noqa: E402


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def wide_window(monkeypatch):
    monkeypatch.setattr(MN, "WINDOW", ("2000-01-01", "2030-01-01"))      # the test commits are made today


def build(tmp_path):
    r = Repo(tmp_path)
    r.commit({"src/a.py": "x = 0\n", ".gitlab-ci.yml": "build:\n  script:\n  - make\n"}, "start")
    for i in range(1, 6):
        r.commit({"src/a.py": f"x = {i}\n"}, f"change {i}")
    bad = r.commit({"src/b.py": "def one():\n    return 1\n\n\ndef two():\n    return 2\n"}, "Add b")
    r.g("revert", "--no-edit", bad)
    r.commit({".gitlab-ci.yml": "build:\n  image: node:latest\n  script:\n  - make\n"}, "Use a moving image")
    r.g("checkout", "-q", "-b", "stable")
    r.g("cherry-pick", "-x", bad)
    r.g("checkout", "-q", "main")
    return r, bad


def test_wilson_matches_known_values():
    assert MN.wilson(0, 0) == (0.0, 1.0)
    lo, hi = MN.wilson(3, 100)
    assert round(lo, 3) == 0.010 and round(hi, 3) == 0.085
    assert MN.wilson(0, 50)[0] == 0.0 and round(MN.wilson(0, 50)[1], 3) == 0.071


def test_the_shuffle_is_seeded_and_stable():
    ids = [f"{i:040x}" for i in range(50)]
    assert MN.shuffled(ids, 10) == MN.shuffled(list(reversed(ids)), 10) and MN.shuffled(ids, 10) != sorted(ids)[:10]


def test_a_real_revert_and_a_real_backport_are_found_and_read(tmp_path):
    r, bad = build(tmp_path)
    reverts = MN.quoting_ids(str(tmp_path), "This reverts commit", "revert", 10)
    backports = MN.quoting_ids(str(tmp_path), "cherry picked from commit", "cherry-pick", 10)
    assert len(reverts) == 1 and len(backports) == 1
    msg, files = MN.read_commit(str(tmp_path), reverts[0])
    assert "This reverts commit" in msg and [f["filename"] for f in files] == ["src/b.py"]


def test_the_checks_say_nothing_on_a_faithful_revert_and_backport(tmp_path):
    build(tmp_path)
    out = tmp_path / "out.json"
    assert MN.main(["--repo", str(tmp_path), "--out", str(out), "--limit", "50"]) == 0
    d = json.loads(out.read_text())
    assert d["reverts"]["checks"]["revert"]["spoke"] == 0 and d["reverts"]["checks"]["revert"]["read"] == 1
    assert d["backports"]["checks"]["copy"]["spoke"] == 0 and d["backports"]["checks"]["copy"]["read"] == 1


def test_the_moving_image_is_counted_once_with_its_example(tmp_path):
    build(tmp_path)
    out = tmp_path / "out.json"
    MN.main(["--repo", str(tmp_path), "--out", str(out), "--limit", "50"])
    row = json.loads(out.read_text())["ordinary"]["checks"]["moving"]
    assert row["spoke"] == 1 and row["examples"][0]["said"] == [{"path": ".gitlab-ci.yml", "kind": "image-latest"}]
    assert row["readable"] >= 1 and row["readable_spoke"] == 1 and row["rule"] == "not met"


def test_a_check_that_breaks_is_counted_not_hidden(tmp_path, monkeypatch):
    build(tmp_path)
    monkeypatch.setattr(MN.SH, "find", lambda files: (_ for _ in ()).throw(ValueError("boom")))
    out = tmp_path / "out.json"
    MN.main(["--repo", str(tmp_path), "--out", str(out), "--limit", "50"])
    row = json.loads(out.read_text())["ordinary"]["checks"]["shapes"]
    assert row["errors"] == row["read"] > 0 and row["error_kinds"] == ["ValueError"] * 3 and row["spoke"] == 0


def test_the_bar_needs_both_the_share_and_the_interval():
    assert MN.verdict({"read": 1500, "share": 0.01, "wilson": [0.006, 0.016]}) == "met"
    assert MN.verdict({"read": 100, "share": 0.0, "wilson": [0.0, 0.037]}) == "met"
    assert MN.verdict({"read": 20, "share": 0.0, "wilson": [0.0, 0.16]}) == "not met"
    assert MN.verdict({"read": 1500, "share": 0.04, "wilson": [0.03, 0.05]}) == "not met"
    assert MN.verdict({"read": 0, "share": None, "wilson": [0.0, 1.0]}) == "no commits read"


def test_a_commit_with_too_many_files_is_skipped(tmp_path, monkeypatch):
    r, _ = build(tmp_path)
    monkeypatch.setattr(MN, "MAX_FILES", 0)
    assert MN.read_commit(str(tmp_path), r.g("rev-parse", "HEAD")) is None


def test_the_shuffle_follows_the_registered_seed():
    import random
    ids = [f"{i:040x}" for i in range(30)]
    expected = sorted(ids)
    random.Random(20261018).shuffle(expected)
    assert MN.SEED == 20261018 and MN.shuffled(ids, 7) == expected[:7] and len(MN.shuffled(ids, 7)) == 7


def test_exactly_three_percent_meets_the_bar():
    assert MN.verdict({"read": 100, "share": 0.03, "wilson": [0.01, 0.05]}) == "met"
    assert MN.verdict({"read": 100, "share": 0.03, "wilson": [0.01, 0.0501]}) == "not met"


def test_examples_are_capped_and_a_quoting_commit_is_read_the_way_asked(tmp_path, monkeypatch):
    r, bad = build(tmp_path)
    r.g("checkout", "-q", "stable")
    r.commit({"src/c.py": "def three():\n    return 3\n\n\ndef four():\n    return 4\n"}, "Add c")
    r.g("revert", "--no-edit", "HEAD")
    r.g("checkout", "-q", "main")
    assert len(MN.quoting_ids(str(tmp_path), "This reverts commit", "revert", 10)) == 2
    assert len(MN.quoting_ids(str(tmp_path), "This reverts commit", "revert", 1)) == 1
    assert MN.quoting_ids(str(tmp_path), "cherry picked from commit", "revert", 10) == []
    head = r.g("rev-parse", "HEAD")
    monkeypatch.setattr(MN, "speaks", lambda *a, **k: [{"path": "x"}])
    row = MN.measure(str(tmp_path), [head] * 12, ("moving",), 0.0)["checks"]["moving"]
    assert row["spoke"] == 12 and len(row["examples"]) == MN.EXAMPLES


def test_the_copy_and_revert_checks_are_told_apart(tmp_path):
    r, bad = build(tmp_path)
    msg = f"Backport\n\n(cherry picked from commit {bad})"
    files = [{"filename": "src/z.py", "status": "added", "patch": "@@ -0,0 +1 @@\n+z = 1\n", "binary": False}] + \
            [{"filename": f"extra/f{i}.py", "status": "added", "patch": "@@ -0,0 +1 @@\n+y = 1\n", "binary": False} for i in range(7)]
    said = MN.speaks("copy", str(tmp_path), "x", msg, files)
    assert said["left"][0]["id"] == bad[:12] and len(said["beyond"]) == 5
    assert MN.speaks("revert", str(tmp_path), "x", msg, files) is None
    assert MN.speaks("copy", str(tmp_path), "x", f"This reverts commit {bad}", files) is None
