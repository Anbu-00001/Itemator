import importlib.util, pathlib

spec = importlib.util.spec_from_file_location("check_mirror", pathlib.Path(__file__).parent.parent / "tools" / "check_mirror.py")
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)

A, B = "a" * 40, "b" * 40


def test_reads_the_last_trailer():
    msg = f"Mirror GitLab main (3 commits, up to bbbbbbb)\n\n- x\n\nGitLab-commit: {A}\n\nGitLab-commit: {B}\n\nSigned-off-by: Anbu <x>\n"
    assert cm.gitlab_commit(msg) == B


def test_trailer_must_be_a_whole_line_of_a_full_sha():
    assert cm.gitlab_commit(f"see GitLab-commit: {A}") is None
    assert cm.gitlab_commit("GitLab-commit: abc123") is None
    assert cm.gitlab_commit("no trailer") is None


def test_same_trees_pass():
    code, line = cm.verdict(A, A, B)
    assert code == 0 and line.startswith("same files") and "bbbbbbbb" in line


def test_different_trees_fail():
    code, line = cm.verdict(A, B, B)
    assert code == 1 and line.startswith("DIFFERENT")
