import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import aidev_weight as AW  # noqa: E402
from itemator.extras import Extra  # noqa: E402
from itemator import registry as RG  # noqa: E402
from test_weight import ROUTES, GRAPH  # noqa: E402,F401
from test_registry import Fake, OSV, pypi_doc  # noqa: E402


def F(path, patch, status="modified"):
    return {"filename": path, "status": status, "patch": patch}


def test_first_line_takes_the_first_pypi_or_npm_dependency_the_registry_can_be_asked():
    by_path = {"go.mod": F("go.mod", "@@ -1 +1,2 @@\n module x\n+require github.com/a/b v1.0.0\n"),
               "requirements.txt": F("requirements.txt", "@@ -1 +1,2 @@\n flask==3.0\n+leftpad-py==1.2.0\n")}
    extras = [Extra("ci_or_config", ".gitlab-ci.yml", ".gitlab-ci.yml", "x"),
              Extra("new_dependency", "go.mod", "github.com/a/b", "adds package github.com/a/b; the issue does not name it"),
              Extra("new_dependency", "requirements.txt", "leftpad-py", "adds package leftpad-py; the issue does not name it")]
    assert AW.first_line(extras, by_path) == {"ecosystem": "PyPI", "name": "leftpad-py", "version": "1.2.0"}
    assert AW.first_line(extras[:2], by_path) is None


def row(state, packages, size, eco="PyPI", ok=True, why=None):
    return {"pr": f"u{packages}{size}", "agent": "Devin", "state": state, "ecosystem": eco, "name": f"p{packages}",
            "weight": {"weight": "ok", "packages": packages, "bytes": size} if ok else {"weight": "unavailable"}, "why_not": why}


def test_summarize_counts_medians_and_heaviest():
    rows = [row("merged", 1, 1_000), row("merged", 12, 20_000_000), row("closed", 5, 3_000_000, "npm"),
            row("open", 0, 0, ok=False, why="not_on_registry")]
    s = AW.summarize(rows)
    assert (s["sampled_lines"], s["weighed"], s["not_weighed"]) == (4, 3, {"not_on_registry": 1})
    assert (s["all"]["median_packages"], s["all"]["median_bytes"], s["all"]["ten_or_more_packages"], s["all"]["ten_mb_or_more"]) == (5, 3_000_000, 1, 1)
    assert s["merged"]["lines"] == 2 and s["merged"]["total_bytes"] == 20_001_000 and s["brings_others"] == 2
    assert [h["bytes"] for h in s["heaviest"]] == [20_000_000, 3_000_000, 1_000]
    assert set(s["by_ecosystem"]) == {"PyPI", "npm"} and s["total_bytes"] == 23_001_000


def test_pct_and_why_not():
    assert AW.pct([], 0.9) is None and AW.pct([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9) == 9
    assert AW.why_not({"lookup": "unavailable"}) == "lookup_unavailable"
    assert AW.why_not({"lookup": "ok", "found": False}) == "not_on_registry"
    assert AW.why_not({"lookup": "ok", "found": True, "weight": {"weight": "unavailable", "reason": "graph_http_404"}}) == "weight_graph_http_404"
    assert AW.why_not({"lookup": "ok", "found": True, "weight": {"weight": "ok"}}) is None


def test_look_up_one_weighs_a_found_package():
    fake = Fake({"https://pypi.org/pypi/leftpad-py/json": (200, pypi_doc()), OSV: (200, {}), **ROUTES})
    p = RG.look_up_one({"ecosystem": "PyPI", "name": "leftpad-py", "version": "1.2.0"}, fake, datetime.datetime(2026, 10, 19))
    assert p["weight"]["weight"] == "ok" and p["weight"]["bytes"] == 30_012_000
    gone = RG.look_up_one({"ecosystem": "PyPI", "name": "nope", "version": None}, Fake({}), datetime.datetime(2026, 10, 19))
    assert gone["found"] is False and "weight" not in gone
