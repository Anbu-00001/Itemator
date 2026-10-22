"""Itemator with another checker's findings in the same threads (itemator/other.py), counted from the registered head-to-head
rows (results/head_to_head_v1.json): how many of the files reviewers objected to does the pair name. Read after the
head-to-head; no tool is re-run, so the questions a person would answer are given only as bounds.

usage: python3 eval/combined.py  ->  results/combined_v1.json"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "results" / "head_to_head_v1.json"
OUT = ROOT / "results" / "combined_v1.json"
PAIRS = {"itemator": ("itemator",), "itemator_with_overreach": ("itemator", "overreach"),
         "itemator_with_scope_creep_detector": ("itemator", "scope_creep_detector"),
         "itemator_with_both": ("itemator", "overreach", "scope_creep_detector")}


def named(rows: list, tools: tuple) -> int:
    return sum(1 for r in rows if r.get("path") and any(r["named"].get(t) for t in tools))


def questions(q: dict, tools: tuple) -> dict:
    """At least Itemator's own questions; at most those plus every file the other tools named (each one question)."""
    return {"at_least": q["itemator"], "at_most": q["itemator"] + sum(q[t] for t in tools if t != "itemator")}


def build(h2h: dict) -> dict:
    rows = [r for r in h2h["rows"] if r.get("path")]
    q = h2h["exploratory_questions"]
    return {"what": "Files reviewers objected to that Itemator names alone, and with another checker's findings added "
                    "(itemator/other.py), from the registered head-to-head rows; read after that study, nothing re-run.",
            "cases": len(rows),
            "named": {k: named(rows, t) for k, t in PAIRS.items()},
            "questions": {k: questions(q, t) for k, t in PAIRS.items()},
            "limits": "The exact number of questions needs the rivals re-run with their file lists kept; a rival file that an "
                      "Itemator extra already covers asks nothing, so the true count lies between the bounds."}


def main() -> int:
    out = build(json.loads(SRC.read_text()))
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["named"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
