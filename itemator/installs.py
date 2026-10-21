"""Packages a change installs from a command line: `pip install`, `npm install`, `gem install` and the like, in a
Dockerfile, a Makefile, a shell script or a CI file.

Rule 1 reads package manifests only, so `RUN pip install requests` in a Dockerfile was just a container config
change, with no registry facts and no weight (an outside reviewer showed this). This reads the added lines of those
files and lists each package a command installs by name, as a new dependency on that file, unless the issue names
it or a line the change removes installed it already. The registry lookup then treats it like a manifest's
(registry.request_for asks `ecosystem`). It only adds extras, so the rules (extras.py, RULES_VERSION) are unchanged.
"""
from __future__ import annotations

import posixpath
import re
import shlex

from itemator import extras as X

# command words -> ecosystem; the package names follow, flags and their values skipped
_COMMANDS = (
    (re.compile(r"(?:^|[\s;&|(])pip\d?(?:\.\d+)?\s+install\s+(.*)"), "PyPI"),      # python -m pip too
    (re.compile(r"(?:^|[\s;&|(])uv\s+(?:pip\s+install|add)\s+(.*)"), "PyPI"),
    (re.compile(r"(?:^|[\s;&|(])npm\s+(?:install|i|add)\s+(.*)"), "npm"),
    (re.compile(r"(?:^|[\s;&|(])(?:yarn|pnpm)\s+(?:global\s+)?add\s+(.*)"), "npm"),
    (re.compile(r"(?:^|[\s;&|(])cargo\s+install\s+(.*)"), "crates.io"),
    (re.compile(r"(?:^|[\s;&|(])go\s+install\s+(.*)"), "Go"),
    (re.compile(r"(?:^|[\s;&|(])gem\s+install\s+(.*)"), "RubyGems"),
)
# flags whose next word is a value, not a package
_VALUE_FLAGS = {"-r", "--requirement", "-c", "--constraint", "-e", "--editable", "-i", "--index-url", "--extra-index-url",
                "-f", "--find-links", "--target", "-t", "--prefix", "--root", "--registry", "--prefix", "--version",
                "--cache-dir", "--python", "-p", "--source", "--path", "--git", "--branch", "--tag", "--rev"}
_NAME = re.compile(r"(?:@[a-z0-9][\w.-]*/)?[A-Za-z0-9][\w.-]*")
INSTALL = "installed by a command in this file"
_SCRIPT_EXT = {"sh", "bash", "zsh", "ps1", "mk"}


def is_install_file(path: str) -> bool:
    b = posixpath.basename(path)
    return (b == "Dockerfile" or b.startswith("Dockerfile.") or b.endswith(".dockerfile") or b in ("Makefile", "makefile",
            "GNUmakefile", "Containerfile", "Jenkinsfile", "Procfile") or X._ext(path) in _SCRIPT_EXT
            or (X._config_kind(path) or ("",))[0] == "CI config")


def _words(rest: str) -> list[str]:
    rest = re.split(r"\s*(?:&&|\|\||;|\||\)|#\s)", rest)[0]
    try:
        return shlex.split(rest)
    except ValueError:
        return rest.split()


def _package(word: str, eco: str) -> str | None:
    if word.startswith(("$", ".", "/", "~", "-")) or word.endswith((".txt", ".whl", ".tar.gz", ".zip", ".tgz")):
        return None
    if eco == "Go":
        return word.split("@", 1)[0] if "/" in word else None
    if eco == "npm":
        name = word if word.startswith("@") and word.count("@") == 1 else (
            "@" + word[1:].split("@", 1)[0] if word.startswith("@") else word.split("@", 1)[0])
    else:
        name = re.split(r"[=<>!~\[;@ ]", word, 1)[0]
    return name if _NAME.fullmatch(name) else None


def installed(line: str) -> list[tuple[str, str]]:
    """[(ecosystem, package)] a command on this line installs by name."""
    out = []
    for rx, eco in _COMMANDS:
        for m in rx.finditer(line):
            skip = False
            for w in _words(m.group(1)):
                if skip:
                    skip = False
                    continue
                if w in _VALUE_FLAGS:
                    skip = True
                    continue
                name = _package(w, eco)
                if name:
                    out.append((eco, name))
    return list(dict.fromkeys(out))


def ecosystem(e) -> str | None:
    """The ecosystem of an extra this module made, from its why; None for any other extra."""
    m = re.search(r"from ([\w.]+); " + re.escape(INSTALL) + "$", e.why) if e.kind == "new_dependency" else None
    return m.group(1) if m else None


def find(issue_text: str, files: list[dict]) -> list:
    out = []
    for f in files:
        path = f.get("filename") or ""
        if f.get("status") == "removed" or not f.get("patch") or not is_install_file(path):
            continue
        old = {p for s, t in X._lines(f["patch"]) if s in ("-", " ") for _, p in installed(t)}
        for eco, name in dict.fromkeys(p for s, t in X._lines(f["patch"]) if s == "+" and not t.lstrip().startswith("#")
                                       for p in installed(t)):
            short = name.rsplit("/", 1)[-1]
            if name in old or X._mentions(issue_text or "", name) or (short != name and X._mentions(issue_text or "", short)):
                continue
            out.append(X.Extra("new_dependency", path, name,
                               f"adds package {name}; the issue does not name it; from {eco}; {INSTALL}"))
    return out


def apply(analysis: X.Analysis, issue_text: str, files: list[dict]) -> X.Analysis:
    more = find(issue_text, files)      # rule 1 reads no file this reads, so nothing is listed twice
    if not more:
        return analysis
    return X.Analysis(**{**analysis.__dict__, "extras": X.sort_extras(analysis.extras + more)})
