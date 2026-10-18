"""The pure parts of eval/mesa_fixes.py (the registered Mesa replay): which later commits count as a repair, the bands, and the rule."""
import importlib.util
import pathlib
import subprocess

import pytest

SPEC = importlib.util.spec_from_file_location("mesa_fixes", pathlib.Path(__file__).resolve().parent.parent / "eval" / "mesa_fixes.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

A = "a" * 40
B = "b" * 40
DAY = 86400


def log(*records):
    return "".join(f"{sha}\x1f{at}\x1f{body}\x1e\n" for sha, at, body in records)


def test_fixes_and_reverts_lines_name_commits():
    rows = M.parse_log(log(("c" * 40, 10, "subject\n\nFixes: ABCDEF1234567 (\"x\")\nFixes: 1234567\n"),
                           ("d" * 40, 11, "Revert \"x\"\n\nThis reverts commit 0123456789abcdef0123456789abcdef01234567.\n"),
                           ("e" * 40, 12, "no tag here, mentions Fixes: in prose only\n")))
    assert rows[0][2] == ["abcdef1234567", "1234567"] and rows[1][2] == ["0123456789abcdef0123456789abcdef01234567"] and rows[2][2] == []


def test_a_short_hash_is_not_a_fix_tag():
    assert M.parse_log(log(("c" * 40, 1, "Fixes: abc123\n")))[0][2] == []


def test_a_repair_must_come_later_but_within_a_year_and_not_from_itself():
    idx = M.index_repairs([("f" * 40, 100 * DAY, [A[:12]]), ("e" * 40, 100 * DAY + 400 * DAY, [A[:12]]), (A, 120 * DAY, [A[:12]]),
                           ("9" * 40, 50 * DAY, [A[:12]])])
    assert M.repaired(A, 90 * DAY, idx)                       # f repairs within a year
    assert not M.repaired(A, 10 * DAY, {k: [x for x in v if x[1] == "e" * 40] for k, v in idx.items()})   # 390 days later is too late
    assert not M.repaired(A, 130 * DAY, idx)                  # every repair is before the commit
    assert not M.repaired(B, 90 * DAY, idx)                   # another commit


def test_the_commit_is_not_repaired_by_naming_itself():
    idx = M.index_repairs([(A, 120 * DAY, [A[:12]])])
    assert not M.repaired(A, 90 * DAY, idx)


def test_bands():
    assert [M.band(n) for n in (1, 2, 3, 4, 10, 11, 40, 41, 0)] == [0, 1, 1, 2, 2, 3, 3, None, None]


def rows(spec):
    return [{"band": b, "flagged": f, "repaired": r} for b, f, r, n in spec for _ in range(n)]


def test_the_ratio_is_stratified_by_band():
    # band 0: flagged 2 of 10 repaired, unflagged 1 of 10; band 1: flagged 4 of 10, unflagged 2 of 10 (ratio 2 in both)
    r = rows([(0, True, True, 2), (0, True, False, 8), (0, False, True, 1), (0, False, False, 9),
              (1, True, True, 4), (1, True, False, 6), (1, False, True, 2), (1, False, False, 8)])
    assert M.mh_ratio(r) == pytest.approx(2.0)


def test_a_mix_that_hides_a_difference_in_the_bands_is_not_fooled():
    # the flagged commits are mostly in the higher-risk band, so the crude ratio looks above 1; inside the bands it is below 1
    r = rows([(0, True, False, 10), (0, False, True, 1), (0, False, False, 9), (1, True, True, 5), (1, True, False, 5), (1, False, True, 5), (1, False, False, 5)])
    crude = (5 / 15) / (6 / 20)
    assert crude > 1.1 and M.mh_ratio(r) == pytest.approx(5 / 6)


def test_no_repairs_among_the_unflagged_gives_no_ratio():
    assert M.mh_ratio(rows([(0, True, True, 3), (0, False, False, 5)])) is None


def test_the_bootstrap_is_fixed_by_its_seed():
    r = rows([(0, True, True, 20), (0, True, False, 80), (0, False, True, 10), (0, False, False, 190)])
    assert M.bootstrap(r) == M.bootstrap(r)
    lo, hi = M.bootstrap(r)
    assert lo is not None and hi is not None and lo < M.mh_ratio(r) < hi


def test_the_rule_needs_enough_flagged_commits_a_big_enough_ratio_and_an_interval_above_one():
    big = rows([(0, True, True, 30), (0, True, False, 70), (0, False, True, 20), (0, False, False, 380)])
    assert M.verdict(big)["verdict"] == "met"
    few = rows([(0, True, True, 10), (0, True, False, 20), (0, False, True, 20), (0, False, False, 380)])
    assert M.verdict(few)["verdict"] == "too few flagged"
    same = rows([(0, True, True, 5), (0, True, False, 95), (0, False, True, 25), (0, False, False, 475)])
    assert M.verdict(same)["verdict"] == "not met"
    wide = rows([(0, True, True, 6), (0, True, False, 34), (0, False, True, 3), (0, False, False, 57)])    # ratio 3 on 40 flagged: the interval still reaches below 1
    assert M.verdict(wide)["verdict"] == "not met" and M.verdict(wide)["ratio"] == pytest.approx(3.0)


def test_wilson_interval():
    assert M.wilson(0, 0) is None
    lo, hi = M.wilson(10, 100)
    assert 0.05 < lo < 0.1 < hi < 0.18


def test_commit_files_reads_status_and_patch_from_a_real_repository(tmp_path):
    def g(*a):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=a@b.c", "-c", "user.name=t", "-c", "commit.gpgsign=false", *a], check=True, capture_output=True)
    g("init", "-q", "-b", "main")
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "gone.txt").write_text("bye\n")
    g("add", "."); g("commit", "-qm", "one")
    (tmp_path / "a.py").write_text("x = 2\n")
    (tmp_path / "gone.txt").unlink()
    (tmp_path / "new.c").write_text("int y;\n")
    g("add", "-A"); g("commit", "-qm", "two")
    sha = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    got = {f["filename"]: f for f in M.commit_files(str(tmp_path), sha)}
    assert {k: v["status"] for k, v in got.items()} == {"a.py": "modified", "gone.txt": "removed", "new.c": "added"}
    assert got["a.py"]["patch"].startswith("@@") and "-x = 1" in got["a.py"]["patch"] and "+x = 2" in got["a.py"]["patch"]
    assert got["new.c"]["patch"] == ""


def test_the_sample_is_the_same_shuffle_every_time_and_keeps_to_the_window(tmp_path):
    def commit(name, date):
        env = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date, "PATH": "/usr/bin:/bin"}
        (tmp_path / name).write_text(name)
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True, capture_output=True, env=env)
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=a@b.c", "-c", "user.name=t", "-c", "commit.gpgsign=false", "commit", "-qm", name],
                       check=True, capture_output=True, env=env)
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    commit("early", "2018-06-01T12:00:00")
    for i in range(12):
        commit(f"in{i}", f"2020-0{1 + i % 9}-1{i % 9}T12:00:00")
    commit("late", "2024-01-01T12:00:00")
    first = M.sample(str(tmp_path))
    assert first == M.sample(str(tmp_path)) and len(first) == 12 and first not in (sorted(first), sorted(first, reverse=True))


def test_a_fix_tag_needs_seven_hex_digits_in_the_pattern_itself():
    assert M._FIXES.findall("Fixes: abcdef\n") == [] and M._FIXES.findall("Fixes: abcdef1\n") == ["abcdef1"]
    assert M._REVERTS.findall("This reverts commit abcdef.") == []
