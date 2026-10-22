"""itemator/setupdeps.py: packages added to setup.cfg's or setup.py's setuptools requirement lists."""
from itemator import after as AF
from itemator import extras as X
from itemator import registry as R
from itemator import setupdeps as SD


def f(path, body, status="modified"):
    return {"filename": path, "status": status, "patch": "@@ -1,4 +1,5 @@\n" + body}


CFG = " [options]\n install_requires =\n     flask\n+    reqeusts>=2\n [options.entry_points]\n console_scripts =\n+    tool = x:main\n"


def names(files, issue="Fix the typo in README.md"):
    return [(e.path, e.name) for e in SD.find(issue, files)]


def test_a_package_added_under_install_requires_is_a_new_dependency_and_the_old_one_is_not():
    assert names([f("setup.cfg", CFG)]) == [("setup.cfg", "reqeusts")]
    e = SD.find("x", [f("setup.cfg", CFG)])[0]
    assert e.kind == "new_dependency" and SD.ecosystem(e) == "PyPI"


def test_inline_values_and_extras_require_count_and_other_sections_do_not():
    body = (" [options]\n-install_requires = flask\n+install_requires = flask, httpx\n [options.extras_require]\n+dev = pytest>=8\n"
            "+docs =\n+    sphinx\n [metadata]\n+name = notapackage\n")
    assert names([f("setup.cfg", body)]) == [("setup.cfg", "httpx"), ("setup.cfg", "pytest"), ("setup.cfg", "sphinx")]


def test_a_hunk_that_starts_inside_a_list_is_not_read():
    assert names([f("setup.cfg", "     flask\n+    reqeusts\n")]) == []


def test_setup_py_lists_but_not_extras_keys_or_other_strings():
    body = (" setup(\n     name=\"x\",\n     install_requires=[\n         \"flask\",\n+        \"reqeusts>=2\",\n     ],\n"
            "+    extras_require={\"dev\": [\"pytest\"]},\n+    description=\"rich text\",\n )\n")
    assert names([f("setup.py", body)]) == [("setup.py", "reqeusts"), ("setup.py", "pytest")]


def test_a_named_moved_or_removed_package_is_not_new():
    moved = " [options]\n install_requires =\n-    Flask_Login\n+    flask-login>=1\n"
    assert names([f("setup.cfg", moved)]) == []
    assert names([f("setup.cfg", CFG)], issue="Add reqeusts to the install list") == []
    assert names([f("setup.cfg", CFG, status="removed")]) == [] and names([f("other.cfg", CFG)]) == []


def test_it_runs_after_the_rules_once_and_the_registry_looks_it_up_on_pypi():
    files = [f("setup.cfg", CFG)]
    a, _ = AF.analyse("Fix the typo in README.md", files)
    deps = [e for e in a.extras if e.kind == "new_dependency"]
    assert [(e.path, e.name) for e in deps] == [("setup.cfg", "reqeusts")]
    assert any(e.kind == "ci_or_config" and e.path == "setup.cfg" for e in a.extras)    # the rules' own extra stays
    assert R.request_for(deps[0], {"setup.cfg": files[0]})["ecosystem"] == "PyPI"
    assert SD.ecosystem(X.Extra("new_dependency", "requirements.txt", "x", "adds package x; the issue does not name it")) is None
