"""The install-time study (eval/install_time_rubric.json, registered before it ran): how long does a fresh install of a dependency an
agent added take on a GitLab-hosted runner? For the first 40 weighed lines of each ecosystem in results/aidev_weight_v1.json, at the
version the weight study weighed: a new empty environment, no cache, then one timed install of that version with what it brings along.
No package code runs: pip takes wheels only (--only-binary=:all:; a line that needs a source build is not measured) and npm runs no
install scripts (--ignore-scripts). Meant for the manual CI jobs `install-time-pypi` and `install-time-npm` (.gitlab-ci.yml).

usage: python3 eval/install_time.py --ecosystem PyPI|npm [--lines 40]"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINES = 40
TIMEOUT = 600
BASELINE = {"PyPI": ("six", "1.16.0"), "npm": ("ms", "2.1.3")}     # one tiny package with nothing to bring: the tool's own start-up


# ---------------------------------------------------------------- pure parts (tests/test_install_time.py)

def sample(result: dict, ecosystem: str, lines: int = LINES) -> list[dict]:
    ok = [r for r in result["rows"] if r["ecosystem"] == ecosystem and (r.get("weight") or {}).get("weight") == "ok"]
    return [{"pr": r["pr"], "name": r["name"], "version": r["weight"]["version"], "packages": r["weight"]["packages"],
             "bytes": r["weight"]["bytes"], "state": r["state"]} for r in ok[:lines]]


def command(ecosystem: str, name: str, version: str, env_dir: str, cache_dir: str) -> list[str]:
    if name.startswith("-") or version.startswith("-"):
        raise ValueError("a name or version that reads as an option")
    if ecosystem == "PyPI":
        return [str(pathlib.Path(env_dir) / "bin" / "pip"), "install", "--no-cache-dir", "--only-binary=:all:", "--disable-pip-version-check",
                "--no-input", "--quiet", f"{name}=={version}"]
    return ["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund", "--no-package-lock", "--no-save", "--loglevel=error",
            "--cache", cache_dir, f"{name}@{version}"]


def ranks(xs: list) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(xs: list, ys: list) -> float | None:
    if len(xs) < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 3) if den else None


def summarize(rows: list, baseline: float | None) -> dict:
    ok = [r for r in rows if r["status"] == "installed"]
    secs = [r["seconds"] for r in ok]
    return {"lines": len(rows), "measured": len(ok), "not_measured": {k: sum(1 for r in rows if r["status"] == k)
                                                                       for k in sorted({r["status"] for r in rows} - {"installed"})},
            "median_seconds": round(statistics.median(secs), 2) if secs else None,
            "p90_seconds": round(sorted(secs)[min(len(secs) - 1, int(0.9 * (len(secs) - 1) + 0.5))], 2) if secs else None,
            "total_seconds": round(sum(secs), 1), "baseline_seconds": baseline,
            "median_seconds_above_baseline": round(statistics.median(max(0.0, s - baseline) for s in secs), 2) if secs and baseline is not None else None,
            "spearman_bytes_seconds": spearman([r["bytes"] for r in ok], secs),
            "slowest": sorted(({"name": r["name"], "version": r["version"], "seconds": r["seconds"], "bytes": r["bytes"], "pr": r["pr"]} for r in ok),
                              key=lambda r: -r["seconds"])[:3]}


# ---------------------------------------------------------------- the run

def install(ecosystem: str, name: str, version: str) -> dict:
    work = tempfile.mkdtemp(prefix="itemator-install-")
    try:
        env_dir, cache_dir = os.path.join(work, "env"), os.path.join(work, "cache")
        os.makedirs(cache_dir)
        if ecosystem == "PyPI":
            subprocess.run([sys.executable, "-m", "venv", env_dir], check=True, timeout=TIMEOUT)       # not timed
        else:
            os.makedirs(env_dir)
        t0 = time.monotonic()
        try:
            p = subprocess.run(command(ecosystem, name, version, env_dir, cache_dir), cwd=env_dir, capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "seconds": None}
        took = round(time.monotonic() - t0, 2)
        if p.returncode:
            needs_build = "only-binary" in p.stderr or "No matching distribution" in p.stderr
            return {"status": "needs_source_build" if needs_build else "failed", "seconds": took, "error": p.stderr.strip()[-300:]}
        return {"status": "installed", "seconds": took}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ecosystem", required=True, choices=("PyPI", "npm"))
    ap.add_argument("--lines", type=int, default=LINES)
    a = ap.parse_args(argv)
    todo = sample(json.loads((ROOT / "results" / "aidev_weight_v1.json").read_text()), a.ecosystem, a.lines)
    base = install(a.ecosystem, *BASELINE[a.ecosystem])
    rows = []
    for i, p in enumerate(todo, 1):
        rows.append({**p, **install(a.ecosystem, p["name"], p["version"])})
        print(f"{i}/{len(todo)} {p['name']} {p['version']}: {rows[-1]['status']} {rows[-1]['seconds']} s", flush=True)
    out = {"rubric": "eval/install_time_rubric.json", "ecosystem": a.ecosystem, "checked": datetime.date.today().isoformat(),
           "runner": {"description": os.environ.get("CI_RUNNER_DESCRIPTION"), "cpus": os.cpu_count(), "job": os.environ.get("CI_JOB_URL"),
                      "tool": subprocess.run(["npm", "--version"] if a.ecosystem == "npm" else [sys.executable, "-m", "pip", "--version"],
                                             capture_output=True, text=True).stdout.strip()},
           "baseline": {"name": BASELINE[a.ecosystem][0], "version": BASELINE[a.ecosystem][1], **base},
           "summary": summarize(rows, base["seconds"] if base["status"] == "installed" else None), "rows": rows}
    path = ROOT / "results" / f"install_time_{a.ecosystem.lower()}_v1.json"
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
