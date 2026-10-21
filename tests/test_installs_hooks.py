"""itemator/installs.py (packages a command installs) and itemator/hooks.py (git hooks)."""
import pytest

from itemator import extras as X
from itemator import hooks as HK
from itemator import installs as IN


def f(path, *added, status="modified", removed=(), context=()):
    body = "".join(f" {c}\n" for c in context) + "".join(f"-{r}\n" for r in removed) + "".join(f"+{a}\n" for a in added)
    return {"filename": path, "status": status, "patch": f"@@ -1,1 +1,1 @@\n{body}"}


@pytest.mark.parametrize("line,want", [
    ("RUN pip install --no-cache-dir requests==2.31 \"flask>=2\" -r req.txt && rm -rf /x", [("PyPI", "requests"), ("PyPI", "flask")]),
    ("RUN python3 -m pip install -e . pyyaml", [("PyPI", "pyyaml")]),
    ("uv pip install httpx", [("PyPI", "httpx")]),
    ("uv add rich", [("PyPI", "rich")]),
    ("pip install 'black[jupyter]~=24.0'", [("PyPI", "black")]),
    ("RUN npm install -g @angular/cli@17 left-pad", [("npm", "@angular/cli"), ("npm", "left-pad")]),
    ("npm i @types/node", [("npm", "@types/node")]), ("yarn global add lodash", [("npm", "lodash")]), ("pnpm add zod@3", [("npm", "zod")]),
    ("cargo install ripgrep --version 13", [("crates.io", "ripgrep")]),
    ("go install golang.org/x/tools/cmd/goimports@latest", [("Go", "golang.org/x/tools/cmd/goimports")]),
    ("gem install bundler", [("RubyGems", "bundler")]),
    ("cd app; pip install six", [("PyPI", "six")]),
])
def test_installed(line, want):
    assert IN.installed(line) == want


@pytest.mark.parametrize("line", ["RUN apt-get install -y curl", "pip install $PKG", "pip install -r requirements.txt",
                                  "RUN pip install https://x.example/y.whl", "npm install", "npm ci", "go install ./cmd/...",
                                  "pip install ./local", "go install tool", "pip install dist/a.tar.gz", "echo pip-install six",
                                  "pip install git+https://github.com/a/b", "pip install --upgrade"])
def test_not_installed_by_name(line):
    assert IN.installed(line) == []


def test_only_install_files_are_read_and_old_installs_and_named_ones_are_not_new():
    assert [p for p in ("Dockerfile", "Dockerfile.dev", "x.dockerfile", "Makefile", "Containerfile", "Jenkinsfile",
                        "a/run.sh", ".gitlab-ci.yml", "src/a.py", "README.md", "build.mk", "Procfile") if IN.is_install_file(p)] == [
        "Dockerfile", "Dockerfile.dev", "x.dockerfile", "Makefile", "Containerfile", "Jenkinsfile", "a/run.sh", ".gitlab-ci.yml",
        "build.mk", "Procfile"]
    line = "RUN pip install six"
    assert IN.find("Fix a", [f("README.md", line)]) == []
    assert IN.find("Fix a", [f("Dockerfile", line, status="removed")]) == []
    assert IN.find("Fix a", [{"filename": "Dockerfile", "status": "modified"}]) == []
    assert IN.find("Fix a", [f("Dockerfile", "RUN pip install six==2", removed=(line,))]) == []                  # a bump
    assert IN.find("Fix a", [f("Dockerfile", line, context=("RUN pip install six",))]) == []
    assert IN.find("Use six for it", [f("Dockerfile", line)]) == []
    assert IN.find("Add the cli", [f("Dockerfile", "RUN npm install -g @angular/cli")]) == []                  # its short name
    assert IN.find("Fix a", [f("Dockerfile", "# RUN pip install six")]) == []
    [e] = IN.find("Fix a", [f("Dockerfile", line)])
    assert e == X.Extra("new_dependency", "Dockerfile", "six", f"adds package six; the issue does not name it; from PyPI; {IN.INSTALL}")
    assert IN.ecosystem(e) == "PyPI" and IN.ecosystem(X.Extra("new_dependency", "requirements.txt", "six", "adds package six")) is None
    assert IN.ecosystem(X.Extra("stray_file", "Dockerfile", "six", e.why)) is None


def test_apply_adds_in_order_once_and_returns_the_same_analysis_when_nothing_is_added():
    files = [f("Dockerfile", "RUN pip install six"), f(".gitlab-ci.yml", "  - pip install six")]
    a = IN.apply(X.analyse("Fix a", files), "Fix a", files)
    assert [(e.kind, e.path, e.name) for e in a.extras if e.kind == "new_dependency"] == [
        ("new_dependency", ".gitlab-ci.yml", "six"), ("new_dependency", "Dockerfile", "six")]
    plain = X.analyse("Fix a", [f("src/a.py", "x = 1")])
    assert IN.apply(plain, "Fix a", [f("src/a.py", "x = 1")]) is plain


@pytest.mark.parametrize("path,yes", [
    (".githooks/pre-commit", True), (".githooks/anything", True), (".husky/pre-push", True), (".husky/_/husky.sh", False),
    ("hooks/post-checkout", True), ("hooks/commit-msg.sh", True), ("src/hooks/useAuth.ts", False), ("lefthook.yml", True),
    ("git-hooks/x", True), ("pre-commit", False), (".pre-commit-config.yaml", False), ("docs/hooks/pre-commit.md", True),
])
def test_is_hook(path, yes):
    assert HK.is_hook(path) is yes


def test_hooks_found_asked_and_removed():
    added = f(".githooks/pre-commit", "make lint", status="added")
    [e] = HK.find("Fix a", [added])
    assert e.kind == "git_hook" and e.why.startswith("adds a git hook")
    assert HK.find("Fix a", [f(".husky/pre-push", "npm test")])[0].why.startswith("changes a git hook")
    assert HK.find("Add a pre-commit hook", [added]) == [] and HK.find("Set up husky", [f(".husky/pre-push", "x")]) == []
    assert HK.find("Fix a", [f(".githooks/pre-commit", "x", status="removed")]) == []
    assert HK.find("Fix a", [f("setup.sh", "# git config core.hooksPath x", removed=("git config core.hooksPath y",))]) != []
    assert HK.find("Fix a", [f("setup.sh", "echo ok", removed=("git config core.hooksPath y",))]) == []


def test_apply_replaces_a_stray_file_and_unplaces_nothing():
    files = [f("lefthook.yml", "pre-commit: {}", status="added"), f("src/a.py", "x = 1")]
    a = X.analyse("Fix a", files)
    b = HK.apply(a, "Fix a", files)
    assert [(e.kind, e.path) for e in b.extras] == [("git_hook", "lefthook.yml")] and "lefthook.yml" not in b.unplaced
    plain = X.analyse("Fix a", [f("src/a.py", "x = 1")])
    assert HK.apply(plain, "Fix a", [f("src/a.py", "x = 1")]) is plain
