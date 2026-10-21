"""itemator/hollow.py: tests kept but made to pass whatever the code does."""
import json
import sys
import pathlib

import pytest

from itemator import ci
from itemator import extras as X
from itemator import hollow as H
from itemator import scope as S

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import weakened_noise as WN  # noqa: E402

ISSUE = "Fix the parser."


def f(path, patch, status="modified"):
    return {"filename": path, "status": status, "patch": "@@ -1,3 +1,3 @@\n" + patch}


def why(*files, issue=ISSUE):
    return [(e.path, e.why) for e in H.find(issue, list(files))]


@pytest.mark.parametrize("line", [
    "    assert True", "    assert 1", "    assert not False", "    assert 1 == 1", "    assert True, 'later'",
    "        self.assertTrue(True)", "        self.assertEqual(1, 1)", "  expect(true).toBe(true);", "  expect(1).toEqual(1)",
    "  expect(true).toBeTruthy()", "  assert.ok(true)", "  assert(true)", "  assert.equal(true, true)",
    "    assertTrue(true);", "    Assertions.assertEquals(1, 1);", "    assert!(true);", "    assert_eq!(1, 1);",
    "\tassert.True(t, true)", "\trequire.True(t, true)", "    XCTAssertTrue(true)", "    expect(true).to eq(true)",
])
def test_an_assertion_that_cannot_fail_in_place_of_one_that_could_is_named(line):
    got = why(f("tests/test_p.py", f"-    assert parse('a') == ['a']\n+{line}\n"))
    assert got == [("tests/test_p.py", "adds 1 assertion that cannot fail and removes 1 that could; the issue does not name this file")]


@pytest.mark.parametrize("line", [
    "    assert x", "    assert ok is True", "    assert result == 1", "  expect(result).toBe(true)", "    assert_eq!(n, 1);",
    "    assertTrue(isValid(x));", "    # assert True", "  // expect(true).toBe(true)", "    assert True_value",
])
def test_a_real_assertion_is_not(line):
    assert why(f("tests/test_p.py", f"-    assert parse('a') == ['a']\n+{line}\n")) == []


def test_an_assertion_that_cannot_fail_added_beside_the_real_ones_is_not():
    assert why(f("tests/test_p.py", " def test_a():\n+    assert True\n     assert parse('a') == ['a']\n")) == []


def test_removing_only_vacuous_assertions_is_not_a_loss():
    assert why(f("tests/test_p.py", "-    assert True\n+    assert True  # still\n")) == []


@pytest.mark.parametrize("line", [
    "@pytest.mark.skip(reason='flaky')", "@pytest.mark.skip", "@unittest.skip('later')", "it.skip('parses', () => {",
    "describe.skip('parser', () => {", "xit('parses', () => {", "@Disabled", "@Ignore", "#[ignore]", "[Ignore]",
])
def test_an_unconditional_skip_is_named(line):
    assert why(f("tests/test_p.py", f"+{line}\n def test_a():\n")) == [
        ("tests/test_p.py", "switches off 1 test with an unconditional skip; the issue does not name this file")]


@pytest.mark.parametrize("line", ["@pytest.mark.skipif(sys.platform == 'win32', reason='x')", "@unittest.skipIf(PY2, 'x')",
                                  "    t.Skip()", "  it('parses', () => {", "# @pytest.mark.skip"])
def test_a_conditional_or_commented_skip_is_not(line):
    assert why(f("tests/test_p.py", f"+{line}\n def test_a():\n")) == []


def test_moving_a_skip_is_not_and_two_skips_are_counted():
    assert why(f("tests/test_p.py", "-@pytest.mark.skip\n+@pytest.mark.skip(reason='x')\n")) == []
    got = why(f("tests/test_p.py", "+it.skip('a', () => {\n+xit('b', () => {\n-  expect(a).toBe(1)\n+  expect(true).toBe(true)\n"))
    assert got[0][1] == ("adds 1 assertion that cannot fail and removes 1 that could; switches off 2 tests with an "
                         "unconditional skip; the issue does not name this file")


def test_only_modified_test_files_the_issue_does_not_name_are_read():
    p = "-    assert parse('a') == ['a']\n+    assert True\n"
    assert why(f("src/p.py", p), f("tests/test_p.py", p, status="added"), f("tests/test_q.py", p, status="removed"),
               {"filename": "tests/test_r.py", "status": "modified"}) == []
    assert why(f("tests/test_p.py", p), issue="Rewrite test_p.py.") == []
    assert H.find(ISSUE, [f("tests/test_p.py", p)], {"tests/test_p.py"}) == []


def test_apply_adds_after_rule_3_and_never_twice():
    hollowed = f("tests/test_p.py", "-    assert parse('a') == ['a']\n+    assert True\n")
    gutted = f("tests/test_q.py", "-def test_q():\n-    assert parse('a') == ['a']\n+def test_q2():\n+    pass\n")
    a = H.apply(X.analyse(ISSUE, [hollowed, gutted]), ISSUE, [hollowed, gutted])
    assert [(e.kind, e.path) for e in a.extras] == [("tests_removed", "tests/test_q.py"), ("tests_weakened", "tests/test_p.py")]
    assert "tests/test_p.py" not in a.unplaced
    both = f("tests/test_r.py", "-    assert parse('a') == ['a']\n-    assert parse('b') == ['b']\n+    assert True\n")
    a = H.apply(X.analyse(ISSUE, [both]), ISSUE, [both])
    assert [(e.kind, e.path) for e in a.extras] == [("tests_removed", "tests/test_r.py")]          # rule 3 lists it, once
    plain = X.analyse(ISSUE, [f("src/p.py", "+x = 1\n")])
    assert H.apply(plain, ISSUE, [f("src/p.py", "+x = 1\n")]) is plain


def test_a_scope_that_allows_the_path_does_not_allow_the_weakening():
    files = [f("tests/test_p.py", "-    assert parse('a') == ['a']\n+    assert True\n")]
    text = ISSUE + "\n```itemator-scope\npaths: tests/**\n```\n"
    a = S.apply(S.read(text), H.apply(X.analyse(text, files), text, files), files)
    assert [e.kind for e in a.extras] == ["tests_weakened"]


def test_the_card_labels_it():
    e = X.Extra("tests_weakened", "tests/test_p.py", "tests/test_p.py", "x")
    assert ci._label(e) == "tests weakened"


def test_the_measurement_file_is_what_the_script_writes():
    path = pathlib.Path(__file__).resolve().parent.parent / "results" / "weakened_noise_v1.json"
    got = json.loads(path.read_text())
    assert got["files_named"] == len(got["firings"]) and got["pull_requests_spoken_on"] <= got["pull_requests_read"]
    assert all(x["label"] != "not labelled" for x in got["firings"])
