"""T26 B2 and F4: a thread offers `split` and `remove` only where the react flow accepts them (its Step 5a part 3),
and a grouped dependency thread lists every package it stands for, so the flow can tell a listed manifest line from
one the issue asked for. Real git repositories in tmp, a fake GitLab API, no network."""
import pytest

from itemator import ci
from itemator.extras import Extra
from test_ci import FIXED, FakeHttp, isolated, issue, job, mr, repo, routes  # noqa: F401  (fixtures)

KEEP = "To keep it, reply with its exact name."
SPLIT = "To move it into its own MR, reply `split`."
REMOVE = "To drop it from this MR, reply `remove`."
TAIL = "If this is not really an extra, reply `not an extra`."
BOTH, REMOVE_ONLY, NEITHER = ("split", "remove"), ("remove",), ()


def added(path):
    return {path: {"filename": path, "status": "added"}}


def modified(path):
    return {path: {"filename": path, "status": "modified"}}


def check_stub(stub, name, offers):
    assert stub.split("`")[1] == ci.shown_name(name) and stub.count(KEEP) == 1 and stub.endswith(TAIL)
    assert (SPLIT in stub) is ("split" in offers) and (REMOVE in stub) is ("remove" in offers)
    at = [stub.index(s) for s in (KEEP, SPLIT, REMOVE, TAIL) if s in stub]
    assert at == sorted(at)


@pytest.mark.parametrize("e, by_path, offers", [
    (Extra("ci_or_config", ".gitlab-ci.yml", ".gitlab-ci.yml", "x"), modified(".gitlab-ci.yml"), BOTH),
    (Extra("ci_or_config", "deploy/Dockerfile", "deploy/Dockerfile", "x"), {}, BOTH),
    (Extra("ci_or_config", "conf/app.ini", "conf/app.ini", "x"), added("conf/app.ini"), BOTH),
    (Extra("ci_or_config", "package.json", "build", "x"), {}, NEITHER),               # an npm script: one line of a manifest
    (Extra("ci_or_config", "pyproject.toml", "pyproject.toml", "x"), {}, NEITHER),    # a manifest is not a config file here
    (Extra("ci_or_config", "Makefile", "Makefile", "x"), {}, NEITHER),
    (Extra("ci_or_config", "conf/", "conf/", "x", ("conf/a.yml", "conf/b.yml")), {}, NEITHER),
    (Extra("new_dependency", "requirements.txt", "colorama", "x"), {}, BOTH),
    (Extra("new_dependency", "api/requirements-dev.txt", "colorama", "x"), {}, BOTH),
    (Extra("new_dependency", "go.mod", "github.com/a/b", "x"), {}, BOTH),
    (Extra("new_dependency", "setup.py", "colorama", "x"), {}, NEITHER),
    (Extra("new_dependency", "requirements.txt", "requirements.txt", "x", ("a", "b")), {}, NEITHER),  # a list without its items
    (Extra("stray_file", "notes.txt", "notes.txt", "x"), added("notes.txt"), REMOVE_ONLY),
    (Extra("stray_file", "notes.txt", "notes.txt", "x"), modified("notes.txt"), NEITHER),
    (Extra("stray_file", "notes.txt", "notes.txt", "x"), {}, NEITHER),
    (Extra("stray_file", "./", "stray files", "x", ("a", "b")), added("./"), NEITHER),
    (Extra("binary_or_large_added", "assets/logo.png", "assets/logo.png", "x"), added("assets/logo.png"), REMOVE_ONLY),
    (Extra("build_output_added", "dist/app.js", "dist/app.js", "x"), added("dist/app.js"), REMOVE_ONLY),
    (Extra("build_output_added", "dist/", "dist/", "x", ("dist/a.js",)), {}, NEITHER),
    (Extra("tests_removed", "tests/test_a.py", "tests/test_a.py", "x"), added("tests/test_a.py"), NEITHER),
    (Extra("public_api_removed", "src/m.py", "parse", "x"), {}, NEITHER),
    (Extra("generated_code_removed", "gen/a.pb.go", "gen/a.pb.go", "x"), {}, NEITHER),
    (Extra("version_bump", "pyproject.toml", "1.1.0", "x"), {}, NEITHER),
    (Extra("policy_changed", ".itemator.toml", ".itemator.toml", "x"), added(".itemator.toml"), NEITHER),
])
def test_a_thread_offers_only_what_the_react_flow_accepts(e, by_path, offers):
    assert ci.answers(e, (), by_path) == offers
    check_stub(ci.describe_extra(e, by_path)["thread_stub"], e.name, offers)


def group(n, width):
    deps = [Extra("new_dependency", "requirements.txt", f"pkg{i}-" + "x" * width, f"adds pkg{i}") for i in range(n)]
    [(e, items)] = ci.group_extras(deps)
    return e, items


def test_a_grouped_dependency_thread_lists_every_package_and_offers_both():
    e, items = group(7, 3)
    assert e.name == e.path == "requirements.txt" and len(items) == 7
    stub = ci.describe_extra(e, {}, items)["thread_stub"]
    listed = stub.split("new dependencies in requirements.txt: ")[1].split(". ")[0].split(", ")
    assert listed == [i.name for i in items]
    check_stub(stub, "requirements.txt", BOTH)


def test_a_grouped_thread_too_long_to_list_offers_neither():
    e, items = group(6, 160)                    # 6 names of 165 characters and 5 separators: exactly MAX_LISTED
    assert len(", ".join(i.name for i in items)) == ci.MAX_LISTED and ci.answers(e, items, {}) == BOTH
    e, items = group(6, 161)
    assert ci.answers(e, items, {}) == NEITHER
    check_stub(ci.describe_extra(e, {}, items)["thread_stub"], "requirements.txt", NEITHER)


def test_the_in_scope_dependency_is_never_named_by_the_extra_thread(repo, tmp_path, monkeypatch):
    """The T24 case: the issue asks for requests-cache; colorama is the extra. The colorama thread names only
    colorama, so the react flow's part 3(b) refuses to split or remove a requirements.txt that also adds
    requests-cache (the prompt is read by the audit; this is the data it relies on)."""
    head = repo.commit({"src/parser.py": FIXED,
                        "requirements.txt": "requests==2.31.0\nrequests-cache==1.2.0\ncolorama==0.4.6\n"})
    code, out = job(repo, head, FakeHttp(routes(mr(), [issue(title="Fix the parser and add requests-cache")])),
                    tmp_path, monkeypatch)
    assert code == 0 and [(e["kind"], e["name"]) for e in out["extras"]] == [("new_dependency", "colorama")]
    stub = out["extras"][0]["thread_stub"]
    assert "requests-cache" not in stub and "requests_cache" not in stub
    check_stub(stub, "colorama", BOTH)
