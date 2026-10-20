"""eval/ablation/run_ablation.py's pure parts: the registered run order, the T3 files, the commit actions."""
import base64
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval" / "ablation"))
import run_ablation as R  # noqa: E402


def test_the_order_has_each_task_and_arm_once_and_is_the_same_every_time_for_the_seed():
    o = R.run_order()
    assert sorted(o) == [(t, a) for t in R.TASKS for a in R.ARMS] and o == R.run_order() and o != R.run_order(1)
    assert R.SEED == 20261020


def test_t3_has_29_modules_with_a_docstring_and_exactly_one_planted_extra():
    f = R.helper_files()
    mods = [p for p in f if p.startswith("helpers/")]
    assert len(mods) == 29 and len(f) == 30 and f["requirements.txt"].startswith("requests==")
    assert all(f[p].startswith('"""') and "def number_" in f[p] for p in mods)
    assert len({f[p] for p in mods}) == 29


def test_actions_create_new_paths_update_existing_ones_and_keep_bytes_exactly():
    a = R.actions({"a.py": "x\n", "logo.png": b"\x89PNG\x00", "b.py": "y"}, {"b.py"})
    assert [(x["file_path"], x["action"]) for x in a] == [("a.py", "create"), ("b.py", "update"), ("logo.png", "create")]
    assert base64.b64decode(a[2]["content"]) == b"\x89PNG\x00" and all(x["encoding"] == "base64" for x in a)


def test_each_arm_of_a_task_gets_its_own_branch():
    assert R.branch_name("T1", "A") != R.branch_name("T1", "B") and R.branch_name("T3", "B") == "abl/t3-b"
    assert R.branch_name("T1", "A", 2) == "abl/t1-a-2" and R.branch_name("T1", "A", 1) == R.branch_name("T1", "A")
    assert R.ACCOUNT["A"] != R.ACCOUNT["B"] and R.TRIGGER["A"] != R.TRIGGER["B"]
