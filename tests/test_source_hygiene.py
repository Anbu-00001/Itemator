"""No source file of the checker spells a bidirectional-control or invisible character literally: written as an escape it means
the same, and a literal one is what a trojan-source scan (and the SAST job) reports. (The tests may hold them: they are the
hostile inputs.)"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
RANGES = ((0x202A, 0x202E), (0x2066, 0x2069), (0x200B, 0x200F), (0x2060, 0x2060), (0xFEFF, 0xFEFF), (0x061C, 0x061C), (0xE0000, 0xE007F))
RISKY = re.compile("[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in RANGES) + "]")


def test_no_python_file_of_the_checker_holds_a_literal_control_or_invisible_character():
    bad = [f"{p.relative_to(ROOT)}:{n}" for d in ("itemator", "tools", "eval", "examples")
           for p in sorted((ROOT / d).rglob("*.py")) for n, line in enumerate(p.read_text(encoding="utf-8").split("\n"), 1) if RISKY.search(line)]
    assert not bad, bad


def test_the_pattern_finds_what_it_is_meant_to():
    assert RISKY.search("a" + chr(0x202E) + "b") and RISKY.search(chr(0xFEFF)) and not RISKY.search("plain text, accents: \u00e9")
