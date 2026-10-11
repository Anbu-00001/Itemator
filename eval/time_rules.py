"""How long do Itemator's rules take on real agent PRs? Writes results/timing_rules.json.

Reads the cached changed-file lists of the replayed PRs under eval/cache/ (no network) and times
`extras()` on each. The issue text is a fixed generic sentence (the real issue texts are not cached),
and the rules' cost depends on the size of the patches, not on the issue text. Run it on an idle
machine; the numbers move a little between runs.

    .venv/bin/python -I eval/time_rules.py
"""
import glob, json, pathlib, platform, statistics, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from itemator import extras as E  # noqa: E402

ISSUE = "Fix the login page wording in src/login.py"
REPEATS = 3                       # best of three per PR, to damp noise


def cpu_model() -> str:
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


rows = []
for path in sorted(glob.glob(str(ROOT / "eval/cache/*.json"))):
    try:
        files = json.load(open(path)).get("files")
    except (OSError, ValueError):
        continue
    if not isinstance(files, list) or not files:
        continue
    times = []
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        E.extras(ISSUE, files)
        times.append(time.perf_counter() - t0)
    rows.append({"cache_file": pathlib.Path(path).name, "files": len(files),
                 "patch_chars": sum(len(f.get("patch") or "") for f in files), "seconds": min(times)})

secs = sorted(r["seconds"] for r in rows)
big = max(rows, key=lambda r: r["seconds"])
out = {
    "what": "time of itemator.extras on cached real agent PRs (best of 3 each)",
    "issue_text": "fixed generic sentence (real issue texts are not cached)",
    "rules_version": E.RULES_VERSION, "python": platform.python_version(), "cpu": cpu_model(),
    "prs_timed": len(rows),
    "median_ms": round(statistics.median(secs) * 1000, 2),
    "p95_ms": round(secs[int(0.95 * (len(secs) - 1))] * 1000, 1),
    "max_ms": round(secs[-1] * 1000, 1),
    "total_s": round(sum(secs), 3),
    "slowest": {"files": big["files"], "patch_chars": big["patch_chars"], "ms": round(big["seconds"] * 1000, 1)},
}
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results/timing_rules.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps(out, indent=2))
