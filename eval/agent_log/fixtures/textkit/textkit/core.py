import re
import textwrap

_NON_WORD = re.compile(r"[^A-Za-z0-9]+")


def slug(text: str) -> str:
    """'Hello, World!' -> 'hello-world'."""
    words = [w for w in _NON_WORD.split(text) if w]
    return "-".join(words).lower()


def wrap(text: str, width: int = 72) -> str:
    return "\n".join(textwrap.wrap(text, width))


def truncate(text: str, n: int) -> str:
    """Cut to at most n characters, ending with an ellipsis when cut."""
    return text if len(text) <= n else text[: n - 1] + "…"


def title_case(text: str) -> str:
    return " ".join(w.capitalize() for w in text.split())


def count_words(text: str) -> int:
    return len(text.split())
