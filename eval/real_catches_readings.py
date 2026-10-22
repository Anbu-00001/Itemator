"""How the one-model reading splits the real cases in results/real_catches.md (written by eval/real_catches_page.py):
how many comments ask to take the file out, how many do not, how many are unclear. Writes results/real_catches_readings.json,
so a number quoted from it can be traced. usage: python3 eval/real_catches_readings.py"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "results" / "real_catches.md"
OUT = ROOT / "results" / "real_catches_readings.json"
READINGS = {"asks to take it out": "asks_to_take_it_out", "does not ask to take it out": "does_not_ask", "unclear": "unclear"}


def count(page: str) -> dict:
    out = {v: 0 for v in READINGS.values()}
    for line in page.splitlines():
        if line.startswith("| [") and line.rstrip().endswith("|"):
            cell = line.rstrip().rstrip("|").rsplit("|", 1)[-1].strip()
            if cell in READINGS:
                out[READINGS[cell]] += 1
    out["rows"] = sum(out.values())
    return out


def main() -> int:
    OUT.write_text(json.dumps({"source": "results/real_catches.md", "reader": "one model's reading of each comment, not a person's",
                               "summary": count(PAGE.read_text())}, indent=1) + "\n")
    print(OUT.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
