from textkit import count_words, slug, title_case, truncate


def test_slug():
    assert slug("Hello, World!") == "hello-world"


def test_truncate():
    assert truncate("abcdef", 4) == "abc…"
    assert truncate("abc", 4) == "abc"


def test_title_case():
    assert title_case("hello world") == "Hello World"


def test_count_words():
    assert count_words("one two  three") == 3
