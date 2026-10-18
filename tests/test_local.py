"""The local command (itemator/local.py): the same rules on a git diff, with no GitLab and no network."""
import io
import subprocess

import pytest

from itemator import local


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=t", *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "app.py").write_text("print(1)\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "work")
    (tmp_path / "app.py").write_text("print(1)\nprint(2)\n")
    (tmp_path / "requirements.txt").write_text("requests==2.0\n")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "change")
    return tmp_path


def run(*argv):
    out = io.StringIO()
    return local.main(list(argv), out=out), out.getvalue()


def test_lists_what_the_issue_did_not_ask_for(repo):
    code, text = run("--repo", str(repo), "--issue-text", "Print 2 in app.py")
    assert code == 0
    assert "3 changed file(s), issue text read" in text
    assert "- new_dependency requirements.txt:" in text and "- ci_or_config .github/workflows/ci.yml:" in text
    assert "app.py:" not in text            # the file the issue names is not an extra


def test_an_issue_that_names_the_files_leaves_no_extras(repo):
    code, text = run("--repo", str(repo), "--issue-text", "Print 2 in app.py, add requests to requirements.txt and run on push in .github/workflows/ci.yml")
    assert code == 0 and "No extras" in text


def test_issue_from_a_file_and_the_missing_issue_note(repo, tmp_path_factory):
    f = tmp_path_factory.mktemp("i") / "issue.txt"
    f.write_text("Print 2 in app.py")
    assert run("--repo", str(repo), "--issue", str(f))[1] == run("--repo", str(repo), "--issue-text", "Print 2 in app.py")[1]
    assert "no issue text given" in run("--repo", str(repo))[1]


def test_explicit_base_and_head(repo):
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "main"], capture_output=True, text=True).stdout.strip()
    assert run("--repo", str(repo), "--base", base, "--head", "work", "--issue-text", "x")[1] == run("--repo", str(repo), "--issue-text", "x")[1]
    assert "0 changed file(s)" in run("--repo", str(repo), "--base", "work", "--head", "work")[1]


def test_bad_refs_exit_2_with_a_message(repo, capsys):
    assert run("--repo", str(repo), "--base", "nope")[0] == 2
    assert "itemator.local:" in capsys.readouterr().err
    assert run("--repo", str(repo), "--target", "nope")[0] == 2
    assert "no merge base between nope and HEAD" in capsys.readouterr().err
    assert run("--repo", str(repo), "--issue", str(repo / "missing.txt"))[0] == 2


def test_does_not_touch_the_network(repo, monkeypatch):
    import socket
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))
    assert run("--repo", str(repo), "--issue-text", "x")[0] == 0


def test_a_mass_event_lists_its_files(repo):
    for i in range(12):
        (repo / "img").mkdir(exist_ok=True)
        (repo / "img" / f"p{i}.png").write_bytes(b"\x89PNG\0\0\0" + bytes([i]))
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "more")
    text = run("--repo", str(repo), "--issue-text", "Print 2 in app.py")[1]
    assert "12 binary or large files added under img/" in text
    assert "    img/p0.png" in text and "    img/p11.png" in text


def test_an_unplaced_file_is_named(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "app.py").write_text("print(1)\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "work")
    (tmp_path / "app.py").write_text("print(1)\nprint(2)\n")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "ci.yml").write_text("on: push\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "change")
    assert "Could not place 1 file(s) against the issue: .github/ci.yml" in run("--repo", str(tmp_path), "--issue-text", "Print 2 in app.py")[1]


def test_issue_from_standard_input(repo, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("Print 2 in app.py"))
    assert run("--repo", str(repo), "--issue", "-")[1] == run("--repo", str(repo), "--issue-text", "Print 2 in app.py")[1]


def test_lint_policy(repo):
    code, text = run("--repo", str(repo), "--lint-policy")
    assert (code, text) == (0, f"No .itemator.toml in {repo}: the default rules apply, nothing to check.\n")
    (repo / ".itemator.toml").write_text('[ignore]\nkinds = ["version_bump"]\npaths = ["gone/**", "app.py"]\n[reasons]\nversion_bump = "scripted"\n"app.py" = "ok"\n')
    git(repo, "add", ".")
    code, text = run("--repo", str(repo), "--lint-policy")
    assert code == 1
    assert text == "- ignore entry `gone/**` has no reason; add it under [reasons]\n- ignore.paths `gone/**` matches no file in the repository; remove it or fix it\n"
    (repo / ".itemator.toml").write_text('[ignore]\npaths = ["app.py"]\n[reasons]\n"app.py" = "ok"\n')
    git(repo, "add", ".")
    assert run("--repo", str(repo), "--lint-policy") == (0, ".itemator.toml is clean: every ignore entry has a reason and matches a file.\n")
    (repo / ".itemator.toml").write_text("[ignore\n")
    assert run("--repo", str(repo), "--lint-policy")[0] == 1


def test_lint_policy_outside_a_repository_exits_2(tmp_path, capsys):
    (tmp_path / ".itemator.toml").write_text("")
    assert run("--repo", str(tmp_path), "--lint-policy")[0] == 2
    assert "itemator.local:" in capsys.readouterr().err


def test_map_labels_every_file(repo):
    text = run("--repo", str(repo), "--issue-text", "Print 2 in app.py", "--map")[1]
    assert "Reviewer's map: 3 file(s), +3 -0 lines." in text
    rows = {ln.split()[1]: ln for ln in text.splitlines() if ln.startswith("  ")}
    assert rows["app.py"].endswith("matches a word in the request") and "+1 -0" in rows["app.py"]
    cols = {ln.index("+") for ln in rows.values()}
    assert len(cols) == 1                    # the columns line up
    assert rows["requirements.txt"].endswith("extra: new_dependency")
    assert rows[".github/workflows/ci.yml"].endswith("extra: ci_or_config")


def test_map_is_off_unless_asked(repo):
    assert "Reviewer's map" not in run("--repo", str(repo), "--issue-text", "Print 2 in app.py")[1]


def test_map_names_an_unplaced_and_an_unlisted_file(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "app.py").write_text("print(1)\n")
    (tmp_path / "util.py").write_text("x = 1\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "work")
    (tmp_path / "app.py").write_text("print(1)\nprint(2)\n")
    (tmp_path / "util.py").write_text("x = 2\n")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "ci.yml").write_text("on: push\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "change")
    text = run("--repo", str(tmp_path), "--issue-text", "Print 2 in app.py", "--map")[1]
    rows = {ln.split()[1]: ln for ln in text.splitlines() if ln.startswith("  ")}
    assert rows[".github/ci.yml"].endswith("not placed against the request")
    assert rows["util.py"].endswith("no match in the request, and no rule lists it") and "+1 -1" in rows["util.py"]


def test_map_lists_the_files_of_a_mass_event_and_binaries(repo):
    for i in range(12):
        (repo / "img").mkdir(exist_ok=True)
        (repo / "img" / f"p{i}.png").write_bytes(b"\x89PNG\0\0\0" + bytes([i]))
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "more")
    text = run("--repo", str(repo), "--issue-text", "Print 2 in app.py", "--map")[1]
    row = next(ln for ln in text.splitlines() if ln.startswith("  added img/p3.png"))
    assert " binary " in row and "extra: binary_or_large_added" in row


def commit_repo(tmp_path, message):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "app.py").write_text("print(1)\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "work")
    (tmp_path / "app.py").write_text("print(1)\nprint(2)\n")
    (tmp_path / "requirements.txt").write_text("requests==2.0\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", message)
    return tmp_path


def test_commits_reads_the_commit_messages_as_the_request(tmp_path):
    repo = commit_repo(tmp_path, "Print 2 in app.py")
    text = run("--repo", str(repo), "--commits")[1]
    assert "2 changed file(s), commit messages read." in text
    assert "- new_dependency requirements.txt:" in text and "app.py:" not in text
    assert run("--repo", str(repo), "--commits")[1].replace("commit messages", "issue text") == run("--repo", str(repo), "--issue-text", "Print 2 in app.py")[1]


def test_a_commit_message_that_names_the_dependency_leaves_no_extra(tmp_path):
    repo = commit_repo(tmp_path, "Print 2 in app.py and add requests to requirements.txt")
    assert "No extras" in run("--repo", str(repo), "--commits")[1]


def test_commits_only_reads_commits_after_the_base(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "app.py").write_text("print(1)\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "app.py").write_text("print(2)\n")
    git(tmp_path, "commit", "-qam", "add requests to requirements.txt")        # an earlier commit's claim
    mid = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (tmp_path / "app.py").write_text("print(3)\n")
    (tmp_path / "requirements.txt").write_text("requests==2.0\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "Print 3 in app.py")
    assert "- new_dependency requirements.txt:" in run("--repo", str(tmp_path), "--commits", "--base", mid)[1]
    assert "No extras" in run("--repo", str(tmp_path), "--commits", "--base", "HEAD~2")[1]     # that claim is read when the range includes it


def test_commits_with_no_message_text_says_so(tmp_path):
    repo = commit_repo(tmp_path, "x")
    assert "no commit messages given" in run("--repo", str(repo), "--commits", "--base", "work", "--head", "work")[1]


def test_commits_and_an_issue_cannot_be_combined(tmp_path, capsys):
    repo = commit_repo(tmp_path, "x")
    with pytest.raises(SystemExit):
        run("--repo", str(repo), "--commits", "--issue-text", "y")
    assert "not allowed with" in capsys.readouterr().err


def test_commits_with_a_bad_ref_exits_2(tmp_path, capsys):
    repo = commit_repo(tmp_path, "x")
    assert run("--repo", str(repo), "--commits", "--base", "nope")[0] == 2


def test_map_says_what_a_layout_only_python_change_and_an_added_binary_are(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "tidy.py").write_text("x=1\ndef f( a ):\n  return a\n")
    (tmp_path / "real.py").write_text("x = 1\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "work")
    (tmp_path / "tidy.py").write_text("x = 1\n\n\ndef f(a):\n    return a  # same\n")
    (tmp_path / "real.py").write_text("x = 2\n")
    (tmp_path / "blob.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    (tmp_path / "fake.png").write_bytes(b"\x7fELF\x02\x01\x01" + b"\x00" * 60)
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "change")
    rows = {ln.split()[1]: ln for ln in run("--repo", str(tmp_path), "--issue-text", "x", "--map")[1].splitlines() if ln.startswith("  ")}
    assert "checked: same syntax tree" in rows["tidy.py"]
    assert "checked" not in rows["real.py"] and "opened" not in rows["real.py"]       # an edit the rules cannot prove says nothing
    assert "opened: " in rows["blob.png"] and "PNG" in rows["blob.png"].upper()
    assert "opened: " in rows["fake.png"] and "name says png" in rows["fake.png"]     # the name disagrees with the bytes


def test_file_facts_skips_what_it_cannot_read(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.py").write_bytes(b"x = '\xe9'\n")                                    # not UTF-8
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "a.py").write_bytes(b"x = '\xe9'  # c\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "change")
    files = [{"filename": "a.py", "status": "modified"}, {"filename": "gone.bin", "status": "added", "binary": True}]
    assert local.file_facts(str(tmp_path), "HEAD~1", "HEAD", files) == {}


def test_file_facts_an_added_python_file_and_a_changed_binary(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "logo.png").write_bytes(b"\x7fELF\x02\x01\x01" + b"\x00" * 60)
    (tmp_path / "new.py").write_text("x = 1\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "change")
    files = [{"filename": "new.py", "status": "added"}, {"filename": "logo.png", "status": "modified", "binary": True}]
    facts = local.file_facts(str(tmp_path), "HEAD~1", "HEAD", files)
    assert list(facts) == ["logo.png"] and "name says png" in facts["logo.png"]
