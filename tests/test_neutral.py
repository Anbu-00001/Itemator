"""itemator/neutral.py: what the rules can prove about a changed Python file, and what they must refuse to prove."""
import pytest

from itemator import neutral as N
from itemator.neutral import classify, compiled_same


def level(old, new):
    return classify(old, new).level


def test_layout_comments_and_blank_lines_are_the_same_syntax():
    assert level("x=1\nif x:\n  print( x )\n", "x = 1\n\n# why\nif x:\n    print(x)  # show\n") == N.SAME_SYNTAX
    assert level("x = 1\n", "x = 1\n") == N.SAME_SYNTAX


def test_a_changed_value_name_or_operator_is_not_proved():
    for old, new in (("x = 1\n", "x = 2\n"), ("x = 1\n", "y = 1\n"), ("x = a + b\n", "x = a - b\n"),
                     ("f(a, b)\n", "f(b, a)\n"), ("x = 'a'\n", "x = 'b'\n"), ("if a:\n    f()\n", "if a:\n    f()\nelse:\n    g()\n")):
        assert level(old, new) == N.NOT_PROVED, (old, new)


def test_a_docstring_edit_is_named_as_such():
    v = classify('def f():\n    """one"""\n    return 1\n', 'def f():\n    """two, longer"""\n    return 1\n')
    assert v.level == N.DOCS_ONLY and "run time" in v.reason
    assert level('"""mod"""\nx = 1\n', 'x = 1\n') == N.DOCS_ONLY                       # a module docstring added or removed
    assert level('class A:\n    "a"\n    x = 1\n', 'class A:\n    x = 1\n') == N.DOCS_ONLY


def test_a_string_that_is_not_the_first_statement_is_code_not_a_docstring():
    assert level('def f():\n    x = 1\n    "note"\n', 'def f():\n    x = 1\n    "other"\n') == N.NOT_PROVED


def test_a_function_that_holds_only_a_docstring_equals_pass():
    assert level('def f():\n    "only"\n', 'def f():\n    pass\n') == N.DOCS_ONLY


def test_plain_functions_moved_among_neighbours_are_reordered():
    old = "import os\n\ndef a():\n    return 1\n\ndef b(x=2):\n    return os.sep\n\nVALUE = 3\n"
    new = "import os\n\ndef b(x=2):\n    return os.sep\n\ndef a():\n    return 1\n\nVALUE = 3\n"
    assert level(old, new) == N.REORDERED


def test_a_function_moved_across_a_statement_that_runs_code_is_not_proved():
    old = "def a():\n    return 1\n\nVALUE = a()\n"
    new = "VALUE = a()\n\ndef a():\n    return 1\n"            # would raise NameError at import
    assert level(old, new) == N.NOT_PROVED


def test_decorated_annotated_and_non_constant_default_functions_are_never_reordered():
    for header in ("@deco\ndef {n}():", "def {n}(x: int):", "def {n}() -> int:", "def {n}(x=OTHER):", "def {n}(x=[]):"):
        a, b = header.format(n="a"), header.format(n="b")
        old = f"{a}\n    return 1\n{b}\n    return 2\n"
        new = f"{b}\n    return 2\n{a}\n    return 1\n"
        assert level(old, new) == N.NOT_PROVED, header


def test_two_definitions_of_one_name_are_never_reordered():
    old = "def a():\n    return 1\n\ndef a():\n    return 2\n"
    new = "def a():\n    return 2\n\ndef a():\n    return 1\n"            # the last one wins, so this changes behaviour
    assert level(old, new) == N.NOT_PROVED


def test_classes_are_not_reordered():
    assert level("class A:\n    pass\n\nclass B:\n    pass\n", "class B:\n    pass\n\nclass A:\n    pass\n") == N.NOT_PROVED


def test_a_body_edit_while_reordering_is_not_proved():
    old = "def a():\n    return 1\n\ndef b():\n    return 2\n"
    new = "def b():\n    return 2\n\ndef a():\n    return 3\n"
    assert level(old, new) == N.NOT_PROVED


def test_added_or_removed_function_is_not_reordering():
    assert level("def a():\n    pass\n", "def a():\n    pass\n\ndef b():\n    pass\n") == N.NOT_PROVED
    assert level("def a():\n    pass\n\ndef b():\n    pass\n", "def a():\n    pass\n") == N.NOT_PROVED


def test_async_functions_move_like_plain_ones():
    old = "async def a():\n    return 1\n\nasync def b():\n    return 2\n"
    new = "async def b():\n    return 2\n\nasync def a():\n    return 1\n"
    assert level(old, new) == N.REORDERED


def test_unreadable_either_side():
    assert level("def (:\n", "x = 1\n") == N.UNREADABLE and level("x = 1\n", "def (:\n") == N.UNREADABLE
    assert level("x = 1\0\n", "x = 1\n") == N.UNREADABLE                       # a null byte
    assert level("", "") == N.SAME_SYNTAX


def test_proved_flag():
    assert classify("x=1\n", "x = 1\n").proved and not classify("x=1\n", "x=2\n").proved and not classify("(", "x").proved


def test_compiled_code_is_the_independent_check_for_same_syntax():
    assert compiled_same("x=1\nif x:\n  f(x)\n", "x = 1\n\n# c\nif x:\n    f( x )\n") is True
    assert compiled_same("x = 1\n", "x = 2\n") is False
    assert compiled_same("def f():\n    return (1, 2)\n", "def f():\n    return (1, 3)\n") is False   # inside a function body
    assert compiled_same("def (:\n", "x = 1\n") is None
    # a changed function name or argument list shows in the compiled code
    assert compiled_same("def f(a):\n    return a\n", "def g(a):\n    return a\n") is False
    assert compiled_same("def f(a):\n    return a\n", "def f(b):\n    return b\n") is False


def test_every_same_syntax_verdict_also_compiles_the_same():
    pairs = [("x=1\n", "x = 1  # c\n"), ("def f(a, b):\n    return a+b\n", "def f(a, b):\n\n    return a + b\n"),
             ("class A:\n  y = [1,2]\n", "class A:\n    y = [1, 2]\n"), ("print('a' 'b')\n", "print('ab')\n")]
    for old, new in pairs:
        if classify(old, new).level == N.SAME_SYNTAX:
            assert compiled_same(old, new) is True, (old, new)


def test_a_number_first_in_a_body_is_not_a_docstring():
    assert level("def f():\n    1\n    return 2\n", "def f():\n    return 2\n") == N.NOT_PROVED


def test_a_removed_or_added_statement_is_not_reordering():
    assert level("x = 1\ny = 2\n", "x = 1\n") == N.NOT_PROVED
    assert level("x = 1\n", "x = 1\ny = 2\n") == N.NOT_PROVED


def test_names_differ_by_case():
    assert level("x = 1\n", "X = 1\n") == N.NOT_PROVED


def test_compiled_code_tells_apart_equal_looking_constants():
    assert compiled_same("x = 1\n", "x = True\n") is False and compiled_same("x = 1\n", "x = 1.0\n") is False
    assert compiled_same("x = (1, 2)\n", "x = (1,)\n") is False and compiled_same("x = (1,)\n", "x = (1, 2)\n") is False


def test_a_changed_encoding_comment_is_not_a_comment_change():
    old = "# -*- coding: latin-1 -*-\nx = 1\n"
    assert level(old, "# -*- coding: utf-8 -*-\nx = 1\n") == N.NOT_PROVED
    assert level(old, "x = 1\n") == N.NOT_PROVED
    assert level(old, "# -*- coding: Latin_1 -*-\nx = 1\n") == N.SAME_SYNTAX      # same encoding, spelled differently
    assert level("x = 1\ny = 2\n# coding: latin-1\n", "x = 1\ny = 2\n") == N.SAME_SYNTAX  # third line on: not a cookie
    assert level("# a note\nx = 1\n", "# another note\nx = 1\n") == N.SAME_SYNTAX
