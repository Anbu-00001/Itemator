"""Is a changed Python file provably behaviour-neutral? Standard library only; no model, no network.

`classify(old_source, new_source)` returns the strongest level the rules can prove, and the reason, or says it could
not prove anything. Levels, strongest first:

  same_syntax                  the two files parse to the same syntax tree: only layout, comments and blank lines
                               changed. Line numbers (tracebacks) are the one thing that can differ.
  comments_or_docstrings_only  the trees are the same once docstrings are removed. A docstring can still be read at run
                               time (help text, doctests, __doc__), so the reason says so.
  reordered_functions          the same top-level statements, with plain functions moved only among their neighbours:
                               no statement that runs code is crossed, no function is decorated, and defaults and
                               annotations are constants, so only the order of name bindings changed.
  not_proved                   anything else. It does NOT mean the change alters behaviour, only that these rules cannot
                               show it does not.
  unreadable                   one side does not parse (or is not Python 3.12 syntax).

Everything outside Python, a rename, a function moved to another file and a body edit are `not_proved` for now."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass

SAME_SYNTAX = "same_syntax"
DOCS_ONLY = "comments_or_docstrings_only"
REORDERED = "reordered_functions"
NOT_PROVED = "not_proved"
UNREADABLE = "unreadable"
LEVELS = (SAME_SYNTAX, DOCS_ONLY, REORDERED, NOT_PROVED, UNREADABLE)
PROVED = (SAME_SYNTAX, DOCS_ONLY, REORDERED)


@dataclass(frozen=True)
class Verdict:
    level: str
    reason: str

    @property
    def proved(self) -> bool:
        return self.level in PROVED


def _parse(source: str):
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def _dump(node) -> str:
    return ast.dump(node, annotate_fields=True, include_attributes=False)


def _strip_docstrings(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return tree


def _constant_only(node) -> bool:
    return node is None or isinstance(node, ast.Constant)


def _movable(stmt) -> bool:
    """A function whose definition runs no code of its own: undecorated, constant defaults, no annotations."""
    if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) or stmt.decorator_list:
        return False
    a = stmt.args
    every = [*a.posonlyargs, *a.args, *a.kwonlyargs, *([a.vararg] if a.vararg else []), *([a.kwarg] if a.kwarg else [])]
    return (all(_constant_only(d) for d in [*a.defaults, *a.kw_defaults])
            and all(x.annotation is None for x in every) and stmt.returns is None and not getattr(stmt, "type_params", None))


def _runs(body):
    """The module body as alternating fixed statements and runs of movable functions."""
    out, run = [], []
    for s in body:
        if _movable(s):
            run.append(s)
        else:
            if run:
                out.append(("run", run))
                run = []
            out.append(("fixed", s))
    if run:
        out.append(("run", run))
    return out


def _reordered(old_tree, new_tree) -> bool:
    a, b = _runs(old_tree.body), _runs(new_tree.body)
    if len(a) != len(b):
        return False
    for (ka, xa), (kb, xb) in zip(a, b):
        if ka != kb:
            return False
        if ka == "fixed":
            if _dump(xa) != _dump(xb):
                return False
            continue
        names = [s.name for s in xa]
        if len(set(names)) != len(names) or sorted(map(_dump, xa)) != sorted(map(_dump, xb)):
            return False
    return True


_COOKIE = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*([-\w.]+)")


def _cookie(source: str) -> str | None:
    """The encoding named in a PEP 263 comment on the first two lines. It decides how the file's bytes are read, so a
    change to it is not a comment change."""
    for line in source.splitlines()[:2]:
        m = _COOKIE.match(line)
        if m:
            return m.group(1).lower().replace("_", "-")
    return None


def classify(old_source: str, new_source: str) -> Verdict:
    old, new = _parse(old_source), _parse(new_source)
    if old is None or new is None:
        return Verdict(UNREADABLE, "one side is not Python the rules can parse")
    if _cookie(old_source) != _cookie(new_source):
        return Verdict(NOT_PROVED, "the encoding comment on the first lines changed; it decides how the file is read")
    if _dump(old) == _dump(new):
        return Verdict(SAME_SYNTAX, "same syntax tree: layout, comments and blank lines only")
    old, new = _strip_docstrings(old), _strip_docstrings(new)
    if _dump(old) == _dump(new):
        return Verdict(DOCS_ONLY, "same code once docstrings are removed; a docstring can still be read at run time")
    if _reordered(old, new):
        return Verdict(REORDERED, "same statements; only plain functions moved among their neighbours")
    return Verdict(NOT_PROVED, "the rules cannot show that this change leaves behaviour alone")


def _code_equal(a, b) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, tuple):
        return len(a) == len(b) and all(_code_equal(x, y) for x, y in zip(a, b))
    if hasattr(a, "co_code"):
        fields = ("co_code", "co_names", "co_varnames", "co_freevars", "co_cellvars", "co_argcount", "co_posonlyargcount",
                  "co_kwonlyargcount", "co_flags")
        return all(getattr(a, f) == getattr(b, f) for f in fields) and _code_equal(a.co_consts, b.co_consts)
    return a == b


def compiled_same(old_source: str, new_source: str) -> bool | None:
    """An independent check on `same_syntax`: CPython compiles both sources to the same code, ignoring line numbers.
    None when either side does not compile."""
    try:
        return _code_equal(compile(old_source, "<old>", "exec", dont_inherit=True),
                           compile(new_source, "<new>", "exec", dont_inherit=True))
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
