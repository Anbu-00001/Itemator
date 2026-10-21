"""Tests kept but made to pass whatever the code does: an assertion that cannot fail, or a test switched off.

Rule 3 (tests_removed) counts test definitions and assertion lines, so a change that swaps `assert add(1, 2) == 3`
for `assert True` keeps both counts and says nothing. This check reads the same modified test files for two shapes:

- an added assertion that cannot fail (`assert True`, `expect(true).toBe(true)`, `assertTrue(true)`, `assert!(true)`)
  in a file that also loses an assertion that could;
- more unconditional skips added than removed (`@pytest.mark.skip`, `it.skip(`, `xit(`, `@Disabled`, `#[ignore]`).

Conditional skips (`skipif`, `t.Skip()` under an `if`) are left alone: the line alone cannot say whether they always run.
An issue that names the test file asks for it, as in rule 3. A file rule 3 already lists is not listed twice.
It only adds extras, so the rules (extras.py, RULES_VERSION) are unchanged.
"""
from __future__ import annotations

import re

from itemator import extras as X

KIND = "tests_weakened"
_T, _ONE = r"(?:True|true|1)", r"(?:1|true|True)"
_VACUOUS = re.compile("|".join((
    rf"^\s*assert\s+(?:{_T}|not\s+(?:False|0)|{_ONE}\s*==\s*{_ONE})\s*(?:,.*)?(?:#.*)?$",       # Python
    rf"\bself\.assert(?:True|Equal|Equals)\(\s*(?:{_T}|{_ONE}\s*,\s*{_ONE})\s*\)",            # unittest
    rf"\bexpect\(\s*{_T}\s*\)\s*\.\s*(?:toBe|toEqual|toStrictEqual)\(\s*{_T}\s*\)",           # Jest, Vitest
    rf"\bexpect\(\s*{_T}\s*\)\s*\.\s*toBeTruthy\(\s*\)",
    rf"\bassert(?:\.ok)?\(\s*{_T}\s*\)", rf"\bassert\.(?:equal|strictEqual|deepEqual)\(\s*{_T}\s*,\s*{_T}\s*\)",
    rf"\bAssert(?:ions)?\.assert(?:True|Equals)\(\s*(?:{_T}|{_ONE}\s*,\s*{_ONE})\s*\)",        # JUnit, qualified
    rf"^\s*assert(?:True|Equals)\(\s*(?:{_T}|{_ONE}\s*,\s*{_ONE})\s*\)",
    rf"\bassert!\(\s*true\s*\)", rf"\bassert_eq!\(\s*{_T}\s*,\s*{_T}\s*\)",                  # Rust
    r"\bassert\.True\(\s*t\s*,\s*true\s*\)", r"\brequire\.True\(\s*t\s*,\s*true\s*\)",         # Go testify
    r"\bXCTAssertTrue\(\s*true\s*\)",                                                         # Swift
    rf"\bexpect\(\s*{_T}\s*\)\s*\.to\s*(?:eq|be)\(?\s*{_T}\s*\)?",                            # RSpec
)))
_SKIP = re.compile("|".join((
    r"^\s*@pytest\.mark\.skip\b", r"^\s*@unittest\.skip\b",       # \b already leaves out skipif, skipIf
    r"^\s*(?:it|test|describe|context)\.skip\s*\(", r"^\s*x(?:it|describe|test)\s*\(",
    r"^\s*@(?:Ignore|Disabled)\b", r"^\s*#\[ignore\]", r"^\s*\[(?:Ignore|Skip)\b",
)))


def _code(text: str) -> bool:
    s = text.strip()
    return bool(s) and not (s.startswith(("//", "/*", "*")) or s.startswith("#") and not s.startswith("#["))   # Rust attribute


def _count(patch, sign, rx, but=None) -> int:
    return sum(1 for s, t in X._lines(patch) if s == sign and _code(t) and rx.search(t) and not (but and but.search(t)))


def find(issue_text: str, files: list[dict], listed: frozenset | set = frozenset()) -> list:
    """Extras for modified test files that keep their tests but make them pass whatever the code does.
    `listed`: paths rule 3 already lists."""
    out = []
    for f in files:
        path = f.get("filename") or ""
        if f.get("status") in ("added", "removed") or not f.get("patch") or path in listed or not X.is_test_file(path):
            continue
        b = X._base(path)
        if X._mentions(issue_text or "", b) or X._mentions(issue_text or "", b.split(".")[0]):
            continue
        p = f["patch"]
        vacuous, gone = _count(p, "+", _VACUOUS), _count(p, "-", X._ASSERT, _VACUOUS)
        skips = _count(p, "+", _SKIP) - _count(p, "-", _SKIP)
        why = []
        if vacuous and gone:
            why.append(f"adds {vacuous} assertion{'s' if vacuous > 1 else ''} that cannot fail and removes "
                       f"{gone} that could")
        if skips > 0:
            why.append(f"switches off {skips} test{'s' if skips > 1 else ''} with an unconditional skip")
        if why:
            out.append(X.Extra(KIND, path, path, "; ".join(why) + "; the issue does not name this file"))
    return out


def apply(analysis: X.Analysis, issue_text: str, files: list[dict]) -> X.Analysis:
    listed = {p for e in analysis.extras if e.kind == "tests_removed" for p in (e.detail or ()) + (e.path,)}
    more = find(issue_text, files, listed)
    if not more:
        return analysis
    return X.Analysis(**{**analysis.__dict__, "extras": X.sort_extras(analysis.extras + more),
                         "unplaced": [u for u in analysis.unplaced if u not in {e.path for e in more}]})
