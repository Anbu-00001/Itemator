"""Every relative link in the README and the docs points at a file that exists (a judge clicks them)."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILES = [ROOT / "README.md", ROOT / "AGENTS.md", *sorted((ROOT / "docs").glob("*.md"))]


def broken(text, base):
    out = []
    for m in re.finditer(r"\]\(([^)#\s]+)(#[^)]*)?\)", text):
        u = m.group(1)
        if not u.startswith(("http://", "https://", "mailto:")) and not (base / u).exists():
            out.append(u)
    return out


def test_no_relative_link_is_broken():
    assert {str(f.relative_to(ROOT)): broken(f.read_text(), f.parent) for f in FILES if broken(f.read_text(), f.parent)} == {}


def test_the_checker_finds_a_broken_link():
    assert broken("see [x](results/nothing-here.json) and [y](https://example.org/a)", ROOT) == ["results/nothing-here.json"]
