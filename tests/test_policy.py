"""The team policy file (T20): .itemator.toml read from the target branch. It can quiet extras or tighten who may
name them, never add one; a merge request that edits it gets a policy_changed extra. Real git repositories in tmp,
a fake GitLab API, no network."""
import pathlib
import re
import subprocess

import pytest

from itemator import ci, policy as POL
from itemator.extras import Extra
from test_ci import FIXED, FakeHttp, isolated, issue, job, mr, repo, routes  # noqa: F401  (fixtures)

KEEP = "To keep it, reply with its exact name; a line under the name can say why."
OTHER = "A reply from the merge request author does not count."
FULL = """# the team's rules
[names]
other_person_required = true

[ignore]
kinds = ["version_bump", "new_dependency"]
paths = ["*.yml", "assets/**"]
"""
PYPROJECT = '[project]\nname = "demo"\nversion = "1.0.0"\n'
ASKS_OTHER = "The team policy asks for someone other than the author to name each extra."
BIG = bytes(range(256)) * 8000          # 2,048,000 bytes: binary_or_large_added


def with_policy(repo, text):
    """The target branch carries `text` as its policy (None: no file); the merge request starts from there."""
    files = {"pyproject.toml": PYPROJECT}
    if text is not None:
        files[".itemator.toml"] = text
    repo.base = repo.commit(files, "target branch")
    return repo


def facts(repo, head, tmp_path, monkeypatch, **kw):
    code, out = job(repo, head, FakeHttp(routes(mr(), [issue()])), tmp_path, monkeypatch, **kw)
    assert code == 0
    return out


def everything(repo):
    """Inside the ask (the parser) plus four extras: a new dependency the registry does not know, a CI change,
    a large binary and a version bump."""
    return repo.commit({"src/parser.py": FIXED, "requirements.txt": "requests==2.31.0\nleftpad-py==1.0.0\n",
                        ".gitlab-ci.yml": "test:\n  script: [pytest, ruff]\n", "assets/logo.png": BIG,
                        "pyproject.toml": PYPROJECT.replace("1.0.0", "1.1.0")})


def kinds(out):
    return [(e["kind"], e["name"]) for e in out["extras"]]


# ---- the file on the target branch

def test_missing_file_changes_nothing(repo, tmp_path, monkeypatch):
    head = everything(with_policy(repo, None))
    out = facts(repo, head, tmp_path, monkeypatch)
    assert kinds(out) == [("new_dependency", "leftpad-py"), ("ci_or_config", ".gitlab-ci.yml"),
                          ("binary_or_large_added", "assets/logo.png"), ("version_bump", "1.1.0")]
    assert out["state"] == "extras" and out["card"]["caveat_line"] is None
    assert out["policy"] == {"source": "target_branch", "sha": repo.base, "file": ".itemator.toml", "found": False,
                             "ignored": None, "paths_line_ok": False,
                             "active": {"other_person_required": False, "hold_until_named": False, "asker_required": False, "ignore_kinds": [],
                                                        "ignore_paths": [], "ignores_every_path": []},
                             "ignored_extras": []}
    assert all(OTHER not in e["thread_stub"] for e in out["extras"])
    assert out["checker"] == {"source": "base", "sha": repo.base}


def test_valid_file_quiets_kinds_and_paths_but_never_the_built_in_exceptions(repo, tmp_path, monkeypatch):
    head = everything(with_policy(repo, FULL))
    out = facts(repo, head, tmp_path, monkeypatch)
    # leftpad-py is unknown to the registry and the logo is a large binary: both stay although the policy names them
    assert kinds(out) == [("new_dependency", "leftpad-py"), ("binary_or_large_added", "assets/logo.png")]
    assert out["state"] == "extras"
    assert out["card"]["final_line"] == ("2 things beyond #12: `leftpad-py` (new dependency), "
                                         "`assets/logo.png` (binary or large file).")
    assert out["card"]["todo_line"] == ci.WELCOME + ' Type each name in its thread to keep it, or reply "split" to move it to its own MR, "remove" to drop it. ' + ci.CONSENT
    p = out["policy"]
    assert p["found"] is True and p["ignored"] is None and p["sha"] == repo.base
    assert p["active"] == {"other_person_required": True, "hold_until_named": False, "asker_required": False, "ignore_kinds": ["version_bump", "new_dependency"],
                           "ignore_paths": ["*.yml", "assets/**"], "ignores_every_path": []}
    assert p["ignored_extras"] == [
        {"name": ".gitlab-ci.yml", "kind": "ci_or_config", "why": "its files match ignore.paths `*.yml`"},
        {"name": "1.1.0", "kind": "version_bump", "why": "ignore.kinds lists version_bump"}]
    assert out["card"]["caveat_line"] == ("The team policy (.itemator.toml on the target branch) quieted 2 extras: "
                                          "`.gitlab-ci.yml` (CI change), `1.1.0` (version bump). " + ASKS_OTHER)


def test_other_person_required_puts_the_sentence_in_the_visible_stub(repo, tmp_path, monkeypatch):
    head = everything(with_policy(repo, FULL))
    for e in facts(repo, head, tmp_path, monkeypatch)["extras"]:
        stub = e["thread_stub"]
        assert stub.split("`")[1] == e["name"] and "reply with its exact name" in stub
        assert stub.count(OTHER) == 1 and stub.index(OTHER) < stub.index(KEEP)
        assert f"{OTHER} {KEEP}" in stub


def test_every_extra_quieted_is_inside_the_ask_with_one_visible_line(repo, tmp_path, monkeypatch):
    with_policy(repo, '[ignore]\nkinds = ["ci_or_config"]\n')
    head = repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": "test:\n  script: [pytest, ruff]\n"})
    out = facts(repo, head, tmp_path, monkeypatch)
    assert out["state"] == "inside_ask" and out["extras"] == []
    assert out["card"]["final_line"] == "Nothing beyond #12." and out["card"]["todo_line"] == "Approve as usual."
    assert out["card"]["caveat_line"] == ("The team policy (.itemator.toml on the target branch) quieted 1 extra: "
                                          "`.gitlab-ci.yml` (CI change).")
    assert out["policy"]["ignored_extras"] == [{"name": ".gitlab-ci.yml", "kind": "ci_or_config",
                                                "why": "ignore.kinds lists ci_or_config"}]


def test_quieting_keeps_the_other_findings(repo, tmp_path, monkeypatch):
    """The policy quiets extras only: the author-wrote-the-issue finding still holds."""
    with_policy(repo, '[ignore]\nkinds = ["ci_or_config"]\n')
    head = repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": "test:\n  script: [pytest, ruff]\n"})
    code, out = job(repo, head, FakeHttp(routes(mr(author_id=1), [issue(author_id=1)])), tmp_path, monkeypatch)
    assert out["state"] == "author_wrote_issue" and out["extras"] == []


def test_a_merge_request_that_edits_the_policy_is_still_judged_by_the_target_branch(repo, tmp_path, monkeypatch):
    with_policy(repo, '[names]\nother_person_required = true\n[ignore]\nkinds = ["ci_or_config"]\npaths = ["*"]\n')
    head = repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": "test:\n  script: [pytest, ruff]\n",
                        ".itemator.toml": '[names]\nother_person_required = false\n'})
    out = facts(repo, head, tmp_path, monkeypatch)
    assert out["policy"]["active"]["other_person_required"] is True          # from the base, not from the MR
    assert kinds(out) == [("policy_changed", ".itemator.toml")]              # never quieted, even by `*`
    assert out["state"] == "extras" and ".itemator.toml" not in out["unplaced"]
    e = out["extras"][0]
    assert e["anchor"] is not None and OTHER in e["thread_stub"]
    assert e["thread_stub"].startswith("`.itemator.toml` (team policy change): ")
    assert out["card"]["final_line"] == "1 thing beyond #12: `.itemator.toml` (team policy change)."
    assert out["policy"]["active"]["ignores_every_path"] == ["*"]
    assert "The team policy ignores every path (`*`)." in out["card"]["caveat_line"]


def test_a_merge_request_that_adds_or_deletes_the_policy_is_an_extra(repo, tmp_path, monkeypatch):
    head = repo.commit({"src/parser.py": FIXED, ".itemator.toml": '[ignore]\nkinds = ["ci_or_config"]\n'})
    out = facts(repo, head, tmp_path, monkeypatch)
    assert kinds(out) == [("policy_changed", ".itemator.toml")]     # not also a stray_file extra on the same file
    assert out["card"]["final_line"] == "1 thing beyond #12: `.itemator.toml` (team policy change)."
    with_policy(repo, "")
    head = repo.commit({"src/parser.py": FIXED, ".itemator.toml": None})
    out = facts(repo, head, tmp_path, monkeypatch)
    assert kinds(out) == [("policy_changed", ".itemator.toml")] and out["policy"]["found"] is True
    with_policy(repo, "[names]\nother_person_required = false\n")
    head = repo.commit({"src/parser.py": FIXED, ".itemator.toml": None, "old-policy.toml": "[names]\nother_person_required = false\n"})
    out = facts(repo, head, tmp_path, monkeypatch)                         # renamed away: still the policy file
    assert kinds(out) == [("policy_changed", ".itemator.toml")] and out["extras"][0]["path"] == "old-policy.toml"
    assert "old-policy.toml" not in out["unplaced"]


def test_a_policy_edit_asks_for_a_name_even_when_no_issue_describes_it(repo, tmp_path, monkeypatch):
    # T41: the merge request `always` opens has no linked issue; its one-line policy edit still needs a typed name
    head = repo.commit({".itemator.toml": "[names]\n"})
    code, out = job(repo, head, FakeHttp(routes(mr(description=""), [])), tmp_path, monkeypatch)
    assert out["state"] == "no_issue"                      # the card still says nobody described the change
    assert kinds(out) == [("policy_changed", ".itemator.toml")] and out["unplaced"] == []
    e = out["extras"][0]
    assert e["anchor"] is not None and e["thread_stub"].startswith("`.itemator.toml` (team policy change): ")
    assert out["card"]["final_line"] == "No one described this change."
    assert out["card"]["todo_line"] == "Link the issue it answers, or say why it needs none."


def test_no_issue_without_a_policy_edit_still_has_no_extras(repo, tmp_path, monkeypatch):
    head = repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": "test:\n  script: [pytest, ruff]\n"})
    code, out = job(repo, head, FakeHttp(routes(mr(description=""), [])), tmp_path, monkeypatch)
    assert out["state"] == "no_issue" and out["extras"] == [] and out["unplaced"] == []


def test_a_policy_edit_with_no_issue_is_not_quieted_by_the_policy(repo, tmp_path, monkeypatch):
    with_policy(repo, '[ignore]\nkinds = ["ci_or_config"]\npaths = ["*"]\n')
    head = repo.commit({".itemator.toml": '[ignore]\nkinds = ["ci_or_config"]\npaths = ["*", "a.yml"]\n'})
    code, out = job(repo, head, FakeHttp(routes(mr(description=""), [])), tmp_path, monkeypatch)
    assert out["state"] == "no_issue" and kinds(out) == [("policy_changed", ".itemator.toml")]


@pytest.mark.parametrize("text, reason", [
    ('[names]\nother_person_required = "yes"\n', "names.other_person_required must be true or false"),
    ('[ignore]\nkinds = ["nope"]\n', "ignore.kinds lists an unknown kind `nope`"),
])
def test_a_broken_file_is_ignored_with_a_visible_reason(repo, tmp_path, monkeypatch, text, reason):
    head = everything(with_policy(repo, text))
    out = facts(repo, head, tmp_path, monkeypatch)
    assert len(out["extras"]) == 4 and out["policy"]["ignored"] == reason and out["policy"]["found"] is True
    assert out["policy"]["active"]["other_person_required"] is False
    assert out["card"]["caveat_line"] == f"The team policy file .itemator.toml on the target branch was not used: {reason}."


def test_oversize_file_is_ignored_unread(repo, tmp_path, monkeypatch):
    head = everything(with_policy(repo, "# " + "x" * 70_000 + "\n[ignore]\nkinds = [\"ci_or_config\"]\n"))
    out = facts(repo, head, tmp_path, monkeypatch)
    assert out["policy"]["ignored"] == "it is larger than 64 KB" and len(out["extras"]) == 4


def test_a_symlink_or_a_directory_is_not_a_policy(repo, tmp_path):
    (repo.path / ".itemator.toml").symlink_to("README.md")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "link")
    sha = repo.git("rev-parse", "HEAD")
    assert POL.read(str(repo.path), sha).ignored == "it is not a regular file"
    (repo.path / ".itemator.toml").unlink()
    sha = repo.commit({".itemator.toml/x": "[names]\n"})
    assert POL.read(str(repo.path), sha).ignored == "it is not a regular file"


# ---- the schema

@pytest.mark.parametrize("text, reason", [
    ("[other]\na = 1\n", "unknown table `other`"),
    ("names = 1\n", "names must be a table"),
    ("[[names]]\n", "names must be a table"),
    ("[names]\nextra = true\n", "unknown key names.`extra`"),
    ("[ignore]\nnames = []\n", "unknown key ignore.`names`"),
    ('[names]\nother_person_required = "yes"\n', "names.other_person_required must be true or false"),
    ("[names]\nother_person_required = 1\n", "names.other_person_required must be true or false"),
    ('[ignore]\nkinds = "version_bump"\n', "ignore.kinds must be a list"),
    ('[ignore]\nkinds = ["nope"]\n', "ignore.kinds lists an unknown kind `nope`"),
    ("[ignore]\nkinds = [1]\n", "ignore.kinds lists an unknown kind `1`"),
    ('[ignore]\nkinds = [["version_bump"]]\n', "ignore.kinds lists an unknown kind `['version_bump']`"),
    ('[ignore]\nkinds = ["policy_changed"]\n', "ignore.kinds lists policy_changed, which is never ignored"),
    ('[ignore]\nkinds = ["binary_or_large_added"]\n', "ignore.kinds lists binary_or_large_added, which is never ignored"),
    ('[ignore]\npaths = "docs/**"\n', "ignore.paths must be a list"),
    ("[ignore]\npaths = [1]\n", "ignore.paths must list non-empty strings"),
    ('[ignore]\npaths = [""]\n', "ignore.paths must list non-empty strings"),
    ('[ignore]\npaths = ["docs/\\u0001x"]\n', "an ignore.paths pattern contains a control character"),
    ('[ignore]\npaths = ["a\\u0085"]\n', "an ignore.paths pattern contains a control character"),
    ("[ignore]\npaths = [\"" + "a" * 201 + "\"]\n", "an ignore.paths pattern is longer than 200 characters"),
    ("[ignore]\npaths = [" + ", ".join(f'"d{i}/**"' for i in range(21)) + "]\n", "ignore.paths has 21 patterns; at most 20"),
    ("[ignore]\npaths = [" + ",".join(['"*"'] * 10_000) + "]\n", "ignore.paths has 10000 patterns; at most 20"),
    ("[ignore]\npaths = [" + ", ".join(f'"d{i}/**"' for i in range(10_000)) + "]\n", "it is larger than 64 KB"),
])
def test_every_schema_violation_ignores_the_whole_file(text, reason):
    assert POL.parse(text.encode()) == reason


@pytest.mark.parametrize("text", ["[names\n", "[ignore]\nkinds = []\n[ignore]\n", "a = \"\x01\"\n",
                                  "[names]\nother_person_required = true\nother_person_required = false\n"])
def test_invalid_toml_ignores_the_whole_file(text):
    reason = POL.parse(text.encode())
    assert reason.startswith("it is not valid TOML (") and reason.endswith(")") and "\n" not in reason


def test_parse_reasons_are_one_safe_line():
    assert POL.parse(b"\xff\xfe") == "it is not UTF-8 text"
    assert POL.parse(b"x" * (64 * 1024 + 1)) == "it is larger than 64 KB"
    assert POL.parse(('[names]\n"' + "k" * 300 + '" = 1\n').encode()) == "unknown key names.`" + "k" * 40 + "`"
    assert POL.parse(b'[names]\n"a`\\u0007\\u0085b" = 1\n') == "unknown key names.`a'''b`"


def test_valid_files():
    assert POL.parse(b"") == {"other_person_required": False, "hold_until_named": False, "asker_required": False, "kinds": (), "paths": (), "reasons": ()}
    assert POL.parse(FULL.encode()) == {"other_person_required": True, "hold_until_named": False, "asker_required": False, "kinds": ("version_bump", "new_dependency"),
                                        "paths": ("*.yml", "assets/**"), "reasons": ()}
    assert POL.parse(("[ignore]\npaths = [" + ", ".join(f'"d{i}/**"' for i in range(20)) + "]\n").encode())["paths"][19] == "d19/**"
    assert POL.parse(b'[ignore]\npaths = ["' + b"a" * 200 + b'"]\n')["paths"] == ("a" * 200,)


@pytest.mark.parametrize("pattern, every", [("*", True), ("**", True), ("***", True), ("**/*", False),
                                            ("docs/**", False), ("*.md", False), ("?*", True),
                                            ("*[!/]*", True), ("?", False), ("[!.]*", False),
                                            ("*?*", True), ("a*", False)])
def test_a_glob_that_matches_everything_is_allowed_and_reported(pattern, every):
    p = POL.Policy(sha="a" * 40, found=True, paths=(pattern,))
    assert p.to_dict()["active"]["ignores_every_path"] == ([pattern] if every else [])


# ---- reading: a fixed argv, a timeout, a checked sha, never a crash

@pytest.mark.parametrize("sha", ["HEAD", "a" * 39, "A" * 40, "a" * 40 + "\n", "a" * 41, "--output=x" + "a" * 30, None])
def test_the_sha_is_checked_before_git_runs(sha, monkeypatch):
    monkeypatch.setattr(POL.subprocess, "run", lambda *a, **k: pytest.fail("git ran"))
    p = POL.read("/nowhere", sha)
    assert p.ignored == "the target commit is not a 40-character sha" and p.found is False


def test_git_runs_with_a_fixed_argv_and_a_timeout(repo, monkeypatch):
    with_policy(repo, FULL)
    calls, real = [], subprocess.run

    def spy(argv, **kw):
        calls.append((list(argv), kw))
        return real(argv, **kw)
    monkeypatch.setattr(POL.subprocess, "run", spy)
    p = POL.read(str(repo.path), repo.base)
    assert p.ignored is None and p.other_person_required is True
    assert [c[0][:4] for c in calls] == [["git", "-C", str(repo.path), "ls-tree"], ["git", "-C", str(repo.path), "cat-file"]]
    assert calls[0][0][4:] == ["-l", "-z", repo.base, "--", ".itemator.toml"]
    assert all(kw.get("timeout") == 10 and not kw.get("shell") for _, kw in calls)


def test_an_oversize_file_is_never_read(repo, monkeypatch):
    with_policy(repo, "#" * (64 * 1024 + 1))
    calls, real = [], subprocess.run
    monkeypatch.setattr(POL.subprocess, "run", lambda argv, **kw: calls.append(argv[3]) or real(argv, **kw))
    assert POL.read(str(repo.path), repo.base).ignored == "it is larger than 64 KB" and calls == ["ls-tree"]
    with_policy(repo, "#" * (64 * 1024) + "\n")
    assert POL.read(str(repo.path), repo.base).ignored == "it is larger than 64 KB"
    with_policy(repo, "#" * (64 * 1024 - 1) + "\n")
    assert POL.read(str(repo.path), repo.base).ignored is None


def test_a_slow_or_failing_git_is_a_reason_not_a_crash(repo, monkeypatch):
    with_policy(repo, FULL)
    assert POL.read(str(repo.path), "b" * 40).ignored == "it could not be read (git ls-tree failed)"

    def slow(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw.get("timeout"))
    monkeypatch.setattr(POL.subprocess, "run", slow)
    assert POL.read(str(repo.path), repo.base).ignored == "it could not be read (git ls-tree timed out)"


# ---- which extras a policy may quiet

def dep(registry):
    return Extra("new_dependency", "requirements.txt", "leftpad-py", "adds package leftpad-py"), (), registry


def pkg(**kw):
    return {"ecosystem": "PyPI", "name": "leftpad-py", **kw}


@pytest.mark.parametrize("registry, quiet", [
    ({"count": 1, "packages": [pkg(lookup="ok", found=True)]}, True),
    ({"count": 1, "packages": [pkg(lookup="not_supported")]}, False),                       # T26 B3: go, gem, maven
    ({"count": 1, "packages": [pkg(lookup="not_from_registry", reason="local_path")]}, False),
    ({"count": 1, "packages": [pkg(lookup="not_from_registry", reason="url_source")]}, False),
    ({"count": 1, "packages": [pkg(lookup="not_from_registry", reason="own_package")]}, True),
    ({"count": 1, "packages": [pkg(lookup="ok", reason="own_package")]}, False),
    ({"count": 2, "packages": [pkg(lookup="ok", found=True), pkg(lookup="not_from_registry", reason="url_source")]}, False),
    ({"count": 2, "packages": [pkg(lookup="ok", found=True), pkg(lookup="not_from_registry", reason="own_package")]}, True),
    ({"count": 2, "packages": [pkg(lookup="ok", found=True), pkg(lookup="not_supported")]}, False),
    ({"count": 1, "packages": [pkg(lookup="ok", found=False)]}, False),       # built-in: no such package
    ({"count": 1, "packages": [pkg(lookup="unavailable", reason="package_cap")]}, False),
    ({"count": 2, "packages": [pkg(lookup="ok", found=True), pkg(lookup="ok", found=False)]}, False),
    ({"count": 9, "packages": [pkg(lookup="ok", found=True)]}, False),         # packages past the lookup cap
    (None, False),
])
def test_a_dependency_is_quieted_only_when_the_registry_knows_every_package(registry, quiet):
    p = POL.Policy(sha="a" * 40, found=True, kinds=("new_dependency",))
    e, items, r = dep(registry)
    assert (POL.why_ignored(p, e, items, r, {}) is not None) is quiet


def test_built_in_exceptions_hold_whatever_the_policy_says():
    p = POL.Policy(sha="a" * 40, found=True, kinds=("binary_or_large_added", "policy_changed"), paths=("*",))
    for kind in ("binary_or_large_added", "policy_changed"):
        assert POL.why_ignored(p, Extra(kind, "a.bin", "a.bin", "x"), (), None, {}) is None


def test_every_file_of_an_extra_must_match():
    p = POL.Policy(sha="a" * 40, found=True, paths=("docs/**",))
    one = Extra("ci_or_config", "docs/x.yml", "docs/x.yml", "x")
    assert POL.why_ignored(p, one, (), None, {}) == "its files match ignore.paths `docs/**`"
    assert POL.why_ignored(p, Extra("ci_or_config", "DOCS/x.yml", "DOCS/x.yml", "x"), (), None, {}) is None
    moved = {"docs/x.yml": {"filename": "docs/x.yml", "previous_filename": "src/x.yml"}}
    assert POL.why_ignored(p, one, (), None, moved) is None                # renamed in from outside docs/
    mass = Extra("ci_or_config", "docs/", "docs/", "x", ("docs/a.yml", "src/b.yml"))
    assert POL.why_ignored(p, mass, (), None, {}) is None
    assert POL.why_ignored(p, Extra("ci_or_config", "docs/", "docs/", "x", ("docs/a.yml", "docs/b.yml")), (), None, {})
    group = Extra("public_api_removed", "docs/m.py", "docs/m.py", "x", ("a", "b"))
    items = (Extra("public_api_removed", "docs/m.py", "a", "x"), Extra("public_api_removed", "lib/m.py", "b", "x"))
    assert POL.why_ignored(p, group, items, None, {}) is None
    two = POL.Policy(sha="a" * 40, found=True, paths=("*.md", "docs/**", "*.yml"))
    assert POL.why_ignored(two, one, (), None, {}) == "its files match ignore.paths `docs/**`, `*.yml`"
    names = Extra("version_bump", "pyproject.toml", "1.1.0", "x", ("pyproject.toml", "docs/conf.py"))
    assert POL.why_ignored(POL.Policy(sha="a" * 40, paths=("pyproject.toml",)), names, (), None, {}) is None


def test_no_policy_quiets_nothing():
    assert POL.why_ignored(POL.Policy(), Extra("ci_or_config", "a.yml", "a.yml", "x"), (), None, {}) is None


# ---- the stub sentence

def test_stub_sentence_sits_before_the_replies():
    e = Extra("tests_removed", "t.py", "n", "x")
    assert ci.thread_stub(e, other_person=True) == (
        f"`n` (tests removed): x. {OTHER} {KEEP} To move it into its own MR, reply `split`. "
        "To drop it from this MR, reply `remove`. "
        "If this is not really an extra, reply `not an extra`.")
    assert ci.thread_stub(e, "PyPI: x.", other_person=True).startswith(f"`n` (tests removed): x. PyPI: x. {OTHER} {KEEP}")
    assert OTHER not in ci.thread_stub(e)


def test_policy_lines_are_capped():
    quiet = [Extra("ci_or_config", f"n{i}", f"n{i}", "x") for i in range(12)]
    line = ci.policy_note(POL.Policy(sha="a" * 40, found=True), quiet)
    assert line.endswith("`n9` (config change), and 2 more.") and "quieted 12 extras" in line


# ---- the checker's origin (item 8)

@pytest.mark.parametrize("kw, source", [({}, "base"), ({"ITEMATOR_CHECKER": "merge_request"}, "merge_request"),
                                        ({"ITEMATOR_CHECKER": ""}, "merge_request"),
                                        ({"ITEMATOR_CHECKER_SHA": "c" * 40}, "merge_request")])
def test_the_card_says_where_the_checker_came_from(repo, tmp_path, monkeypatch, kw, source):
    head = repo.commit({"src/parser.py": FIXED})
    out = facts(repo, head, tmp_path, monkeypatch, **kw)
    assert out["checker"] == {"source": source, "sha": repo.base if source == "base" else head}
    assert out["card"]["caveat_line"] == (None if source == "base" else ci.CHECKER_CAVEAT)
    assert out["state"] == "inside_ask"


def test_the_log_copy_cuts_a_long_quieted_list_and_says_so():
    quiet = [{"name": f"n{i:03d}" + "x" * 80, "kind": "ci_or_config", "why": "ignore.kinds lists ci_or_config"}
             for i in range(300)]
    report = {"extras": [], "unplaced": [], "injection": [], "card": {}, "truncated": False,
              "policy": {**POL.Policy(sha="a" * 40, found=True).to_dict(), "ignored_extras": quiet}}
    c = __import__("json").loads(ci.log_block(report, limit=5_000).split("\n")[1])
    assert c["policy"]["ignored_extras"] == quiet[:20] and c["policy"]["ignored_extras_total"] == 300
    assert "policy.ignored_extras[20:]" in c["truncated"]
    assert __import__("json").loads(ci.log_block(report).split("\n")[1])["policy"]["ignored_extras"] == quiet



# ---- T26

@pytest.mark.parametrize("files", [
    {"requirements.txt": "requests==2.31.0\nfoo @ https://evil.example/foo-1.0.tar.gz\n"},
    {"requirements.txt": "requests==2.31.0\ngit+https://github.com/evil/foo.git#egg=foo\n"},
    {"go.mod": "module example.com/demo\n\ngo 1.22\n\nrequire github.com/evil/x v1.0.0\n"},
], ids=["url", "git", "go"])
def test_a_dependency_from_outside_a_registry_is_never_quieted(repo, tmp_path, monkeypatch, files):
    with_policy(repo, '[ignore]\nkinds = ["new_dependency"]\n')
    repo.base = repo.commit({"go.mod": "module example.com/demo\n\ngo 1.22\n"})
    head = repo.commit({"src/parser.py": FIXED, **files})
    out = facts(repo, head, tmp_path, monkeypatch)
    assert [e["kind"] for e in out["extras"]] == ["new_dependency"] and out["policy"]["ignored_extras"] == []
    assert out["card"]["final_line"].startswith("1 thing beyond #12: ")


def fork_and_tip(repo):
    """The merge base quiets CI changes; the target branch has since dropped that line; the merge request
    started before."""
    with_policy(repo, '[ignore]\nkinds = ["ci_or_config"]\n')
    fork = repo.base
    tip = repo.commit({".itemator.toml": None, "README.md": "# demo, stricter\n"}, "target branch moves on")
    repo.git("checkout", "-q", "-b", "mr", fork)
    head = repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": "test:\n  script: [pytest, ruff]\n"})
    return fork, tip, head


def test_policy_and_checker_come_from_the_target_branch_tip(repo, tmp_path, monkeypatch):
    fork, tip, head = fork_and_tip(repo)
    out = facts(repo, head, tmp_path, monkeypatch, target=tip, ITEMATOR_CHECKER_SHA=tip)
    assert out["base_sha"] == fork and out["policy"]["sha"] == tip and out["policy"]["source"] == "target_branch"
    assert kinds(out) == [("ci_or_config", ".gitlab-ci.yml")] and out["policy"]["ignored_extras"] == []
    assert out["checker"] == {"source": "base", "sha": tip} and out["card"]["caveat_line"] is None
    out = facts(repo, head, tmp_path, monkeypatch, target=tip, ITEMATOR_CHECKER_SHA=fork)   # an older job script
    assert out["checker"] == {"source": "merge_request", "sha": head}


def test_without_the_target_ref_the_merge_base_is_used_and_the_card_says_so(repo, tmp_path, monkeypatch):
    fork, tip, head = fork_and_tip(repo)
    out = facts(repo, head, tmp_path, monkeypatch, target=None)
    assert out["policy"]["sha"] == fork and out["policy"]["source"] == "merge_base" and out["extras"] == []
    assert out["checker"] == {"source": "base", "sha": fork}
    assert out["card"]["caveat_line"] == (
        ci.TARGET_CAVEAT + " The team policy (.itemator.toml at the commit this branch started from) quieted 1 extra: "
        "`.gitlab-ci.yml` (CI change).")
    assert "target branch" not in out["card"]["caveat_line"].replace(ci.TARGET_CAVEAT, "")
    head = repo.commit({".itemator.toml": "[names]\n"})
    e = facts(repo, head, tmp_path, monkeypatch, target=None)["extras"][0]
    assert e["kind"] == "policy_changed" and e["why"].endswith("still judged by the copy at the commit this branch started from")


@pytest.mark.parametrize("answer", [b"A" * 40 + b"\n", b"HEAD\n", b"a" * 39 + b"\n", b"a" * 40 + b"\nx\n", b""])
def test_a_target_ref_that_is_not_a_full_sha_is_not_used(repo, monkeypatch, answer):
    real = ci._git
    monkeypatch.setattr(ci, "_git", lambda r, *a, **k: answer if a[0] == "rev-parse" else real(r, *a, **k))
    assert ci.target_tip(str(repo.path), {"CI_MERGE_REQUEST_TARGET_BRANCH_NAME": "main"}, repo.base) == (repo.base, False)


def test_the_target_tip_is_resolved_from_the_remote_ref(repo):
    tip = repo.commit({"README.md": "# moved\n"})
    repo.git("update-ref", "refs/remotes/origin/main", tip)
    assert ci.target_tip(str(repo.path), {"CI_MERGE_REQUEST_TARGET_BRANCH_NAME": "main"}, repo.base) == (tip, True)
    for name in ("", "nope", "main^{tree}", "../main"):
        assert ci.target_tip(str(repo.path), {"CI_MERGE_REQUEST_TARGET_BRANCH_NAME": name}, repo.base) == (repo.base, False)
    assert ci.target_tip(str(repo.path), {}, repo.base) == (repo.base, False)


DEEP = ["a=" + "[" * 30_000 + "]" * 30_000 + "\n", "a=" + "{b=" * 400 + "1" + "}" * 400 + "\n",
        "[ignore]\nkinds = " + "[" * 900 + "]" * 900 + "\n"]


@pytest.mark.parametrize("text", DEEP, ids=["array", "inline-table", "kinds"])
def test_deep_toml_is_a_reason_not_a_crash(repo, tmp_path, monkeypatch, text):
    assert len(text.encode()) <= POL.MAX_BYTES
    assert POL.parse(text.encode()) == POL.TOO_DEEP
    head = everything(with_policy(repo, text))
    out = facts(repo, head, tmp_path, monkeypatch)
    assert out["policy"]["ignored"] == POL.TOO_DEEP and len(out["extras"]) == 4


def test_a_toml_error_shows_only_where_it_is():
    for text in (b'["@all"]\n["@all"]\n', b'[names]\n"@all `x`" = = 1\n', b"[names\n", b'a = "@all'):
        reason = POL.parse(text)
        assert "@all" not in reason and "`" not in reason, reason
        assert re.fullmatch(r"it is not valid TOML \((?:line \d+, column \d+|at the end of the file)\)", reason), reason
    assert POL.parse(b'["@all"]\n["@all"]\n') == "it is not valid TOML (line 2, column 8)"


def test_a_pattern_that_matches_every_path_is_reported_however_it_is_written(repo, tmp_path, monkeypatch):
    head = everything(with_policy(repo, '[ignore]\npaths = ["?*"]\n'))
    out = facts(repo, head, tmp_path, monkeypatch)
    assert out["policy"]["active"]["ignores_every_path"] == ["?*"]
    assert "The team policy ignores every path (`?*`)." in out["card"]["caveat_line"]


def test_the_other_person_sentence_shows_only_while_something_needs_a_name(repo, tmp_path, monkeypatch):
    with_policy(repo, '[names]\nother_person_required = true\n[ignore]\nkinds = ["ci_or_config"]\n')
    head = repo.commit({"src/parser.py": FIXED, ".gitlab-ci.yml": "test:\n  script: [pytest, ruff]\n"})
    out = facts(repo, head, tmp_path, monkeypatch)
    assert out["card"]["final_line"] == "Nothing beyond #12." and out["card"]["todo_line"] == "Approve as usual."
    assert ASKS_OTHER not in out["card"]["caveat_line"] and "quieted 1 extra" in out["card"]["caveat_line"]
    head = repo.commit({"notes.txt": "todo\n"})
    out = facts(repo, head, tmp_path, monkeypatch)
    assert out["state"] == "extras" and out["card"]["caveat_line"].endswith(ASKS_OTHER)


# ---- T37 item 2: a file that changes what coding agents are told is never quieted by a team policy
def test_agent_instructions_are_never_quieted():
    e = Extra("agent_instructions", "AGENTS.md", "AGENTS.md", "w")
    stray = Extra("stray_file", "NOTES.md", "NOTES.md", "w")
    by_path = {p: {"filename": p, "status": "added"} for p in ("AGENTS.md", "NOTES.md")}
    by_kind = POL.Policy(sha="a" * 40, found=True, kinds=("agent_instructions",))
    by_md = POL.Policy(sha="a" * 40, found=True, paths=("*.md",))
    assert POL.why_ignored(by_kind, e, (), None, by_path) is None
    assert POL.why_ignored(by_md, e, (), None, by_path) is None
    assert POL.why_ignored(by_md, stray, (), None, by_path) == "its files match ignore.paths `*.md`"     # the control
    group = Extra("agent_instructions", "./", "agent instruction files", "w", ("AGENTS.md", "CLAUDE.md"))
    assert POL.why_ignored(by_md, group, (), None, by_path) is None
    assert POL.parse(b'[ignore]\nkinds = ["agent_instructions"]\n') == "ignore.kinds lists agent_instructions, which is never ignored"
    assert POL.parse(b'[ignore]\nkinds = ["binary_or_large_added"]\n') == \
        "ignore.kinds lists binary_or_large_added, which is never ignored"         # the same visible reason


# T42 (audit pass 1, fix 6): the stub offers `always` only where the react flow's one-line edit can be made
@pytest.mark.parametrize("text, ok", [
    ('[ignore]\nkinds = []\npaths = []\n', True),
    ('[names]\nother_person_required = false\n\n[ignore]\npaths = ["a", "b"]\n', True),
    ('[ignore]\n  paths = ["a"]  # kept\n', True),
    ('[ignore]\npaths=[]\n', False),                                  # valid TOML, but not the spelling the flow reads
    ('[ignore]\npaths\t= []\n', False),
    ('[ignore]\npaths = [\n  "a",\n]\n', False),                      # a list over several lines
    ('[ignore]\nkinds = []\n', False),                                # no paths line
    ('[names]\nother_person_required = false\n', False),              # no [ignore] table
    ('ignore.paths = []\n', False),                                   # dotted key
    ('paths = []\n', False),                                          # a paths line outside any [ignore] table
    ('[ignore]\npaths = ["a",]\n', False),                            # a trailing comma would become ", ,"
    ('[ignore]\npaths = ["a", ]\n', False),
    ('[ignore]\npaths = ["*.[ch]"]\n', False),                     # a glob class makes the closing ] ambiguous
    ('[ignore]\npaths = ["a"]  # [x]\n', True),                    # brackets in a comment after the list are fine
    ('[ignore]\npaths = ["a" # x ]\n]\n', False),                    # a # inside the list
    ('[ignore]\npaths = []\npaths = ["a"]\n', False),                 # two lines (and invalid TOML)
    ('[other]\npaths = []\n[ignore]\nkinds = []\n', False),           # the line is in another table
    ('[ignore]\nkinds = []\n[other]\npaths = []\n', False),
    ('# paths = []\n[ignore]\npaths = []\n', False),                  # the same text in a comment: the edit would hit it
])
def test_paths_line_ok_only_for_the_layout_the_flow_edits(text, ok):
    assert POL.paths_line_ok(text) is ok


def test_read_marks_the_real_policy_file_ok_and_a_policy_without_the_line_not(tmp_path):
    for body, ok in (('[ignore]\npaths = []\n', True), ('[ignore]\npaths=[]\n', False)):
        repo = tmp_path / str(ok)
        repo.mkdir()
        (repo / ".itemator.toml").write_text(body)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x"], check=True)
        sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        pol = POL.read(str(repo), sha)
        assert pol.paths_line_ok is ok and pol.to_dict()["paths_line_ok"] is ok


def test_this_repository_policy_file_can_be_extended_by_always():
    f = pathlib.Path(__file__).resolve().parent.parent / ".itemator.toml"
    if not f.exists():
        pytest.skip("no .itemator.toml in this copy")
    assert POL.paths_line_ok(f.read_text())


REASONED = b'[ignore]\nkinds = ["version_bump"]\npaths = ["docs/**", "*.md"]\n[reasons]\nversion_bump = "we bump by script"\n"docs/**" = "docs team reviews these"\n"*.md" = "readme edits are low risk"\n'


def test_reasons_are_read_and_change_nothing_else():
    s = POL.parse(REASONED)
    assert s["reasons"] == (("version_bump", "we bump by script"), ("docs/**", "docs team reviews these"), ("*.md", "readme edits are low risk"))
    assert (s["kinds"], s["paths"]) == (("version_bump",), ("docs/**", "*.md"))
    assert POL.Policy(**s).to_dict() == POL.Policy(**{**s, "reasons": ()}).to_dict()       # the facts file does not carry them


@pytest.mark.parametrize("text, why", [
    ('[ignore]\nkinds = ["version_bump"]\n[reasons]\nstray_file = "x"\n', "reasons names `stray_file`, which is not an ignore entry"),
    ('[ignore]\nkinds = ["version_bump"]\n[reasons]\nversion_bump = ""\n', "the reason for `version_bump` must be a non-empty string"),
    ('[ignore]\nkinds = ["version_bump"]\n[reasons]\nversion_bump = "  "\n', "the reason for `version_bump` must be a non-empty string"),
    ('[ignore]\nkinds = ["version_bump"]\n[reasons]\nversion_bump = 3\n', "the reason for `version_bump` must be a non-empty string"),
    ('[ignore]\nkinds = ["version_bump"]\n[reasons]\nversion_bump = "' + "a" * 201 + '"\n', "has a control character or is longer than 200"),
    ('[ignore]\nkinds = ["version_bump"]\n[reasons]\nversion_bump = "a\\u0007b"\n', "has a control character or is longer than 200"),
    ('[reasons]\nx = 1\n[bogus]\n', "unknown table `bogus`"),
    ('reasons = 3\n', "reasons must be a table"),
])
def test_a_bad_reasons_table_makes_the_file_ignored(text, why):
    assert why in POL.parse(text.encode())


def test_lint_names_what_to_tidy():
    tracked = ["README.md", "docs/a.md", "src/x.py"]
    assert POL.lint(REASONED, tracked) == []
    bare = b'[ignore]\nkinds = ["version_bump"]\npaths = ["docs/**", "gone/**"]\n'
    assert POL.lint(bare, tracked) == [
        "ignore entry `version_bump` has no reason; add it under [reasons]",
        "ignore entry `docs/**` has no reason; add it under [reasons]",
        "ignore entry `gone/**` has no reason; add it under [reasons]",
        "ignore.paths `gone/**` matches no file in the repository; remove it or fix it"]
    assert POL.lint(b'[ignore]\npaths = ["*"]\n[reasons]\n"*" = "all"\n', tracked) == ["ignore.paths `*` matches every path, so no extra would ever need a name"]
    assert POL.lint(b"[ignore\n", tracked)[0].startswith(".itemator.toml would be ignored: it is not valid TOML")
    assert POL.lint(b"", tracked) == []
