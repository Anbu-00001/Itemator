"""Mesa replay, pre-registered in eval/mesa_fixes_rubric.json: is a commit that the fence check or the stranger check flags
repaired or reverted later (a 'Fixes: <hash>' line or 'This reverts commit <hash>' within 365 days) more often than a commit
it does not flag? Reads a local bare clone only. The result holds commit ids, labels and counts; no diff text, no messages.

usage: python3 eval/mesa_fixes.py --repo work/mesa-replay/mesa.git --out results/mesa_fixes_v1.json [--limit N]"""
from __future__ import annotations

import argparse, collections, datetime, json, math, pathlib, random, re, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from itemator import cochange as CC  # noqa: E402
from itemator import fence as FE  # noqa: E402

SEED = 20261018
WINDOW = ("2019-01-01", "2023-06-30")
YEAR = 365 * 86400
MAX_FILES, MAX_TOTAL_FILES, FLAGGED_MIN, STEP, CAP = 40, 300, 40, 1000, 3000
BANDS = ((1, 1), (2, 3), (4, 10), (11, 40))
TIME_LIMIT = 120
RATIO_MIN, RESAMPLES = 1.5, 2000

_FIXES = re.compile(r"^\s*Fixes:\s*([0-9a-f]{7,40})\b", re.I | re.M)
_REVERTS = re.compile(r"This reverts commit\s+([0-9a-f]{7,40})\b", re.I)


# ---------------------------------------------------------------- pure parts (tests/test_mesa_fixes.py)

def parse_log(text: str) -> list[tuple[str, int, list[str]]]:
    """`git log --format=%H%x1f%at%x1f%B%x1e` as (sha, author time, [hashes it says it fixes or reverts])."""
    out = []
    for rec in text.split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        sha, at, body = rec.split("\x1f", 2)
        out.append((sha.strip(), int(at), [h.lower() for h in _FIXES.findall(body) + _REVERTS.findall(body)]))
    return out


def index_repairs(rows) -> dict[str, list[tuple[int, str, str]]]:
    """{first 7 hex digits of the named commit: [(author time, repairing commit, the hash it names)]}."""
    idx: collections.defaultdict[str, list[tuple[int, str, str]]] = collections.defaultdict(list)
    for sha, at, named in rows:
        for h in named:
            idx[h[:7]].append((at, sha, h))
    return dict(idx)


def repaired(sha: str, at: int, idx) -> bool:
    """A later commit (after `at`, within a year) names `sha` by 7 or more hex digits."""
    return any(at < t <= at + YEAR and sha.startswith(h) and by != sha for t, by, h in idx.get(sha[:7], ()))


def band(n: int) -> int | None:
    for i, (lo, hi) in enumerate(BANDS):
        if lo <= n <= hi:
            return i
    return None


def mh_ratio(rows: list[dict]) -> float | None:
    """Mantel-Haenszel risk ratio of the repaired share, flagged over unflagged, over the bands. Rows: band, flagged, repaired."""
    num = den = 0.0
    for b in {r["band"] for r in rows}:
        g = [r for r in rows if r["band"] == b]
        n1, n0 = sum(r["flagged"] for r in g), sum(not r["flagged"] for r in g)
        a = sum(r["flagged"] and r["repaired"] for r in g)
        c = sum((not r["flagged"]) and r["repaired"] for r in g)
        n = len(g)
        num += a * n0 / n
        den += c * n1 / n
    return num / den if den else None


def bootstrap(rows: list[dict], resamples: int = RESAMPLES, seed: int = SEED) -> tuple[float | None, float | None]:
    """2.5th and 97.5th percentile of mh_ratio over resamples drawn inside each band (ratios that cannot be computed are dropped)."""
    rng = random.Random(seed)
    by = collections.defaultdict(list)
    for r in rows:
        by[r["band"]].append(r)
    vals = []
    for _ in range(resamples):
        v = mh_ratio([r for g in by.values() for r in rng.choices(g, k=len(g))])
        if v is not None:
            vals.append(v)
    if len(vals) < resamples // 2:
        return None, None
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if not n:
        return None
    p, d = k / n, 1 + z * z / n
    c, h = p + z * z / (2 * n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round((c - h) / d, 4), round((c + h) / d, 4)


def verdict(rows: list[dict]) -> dict:
    """The pre-registered rule for one check."""
    flagged = sum(r["flagged"] for r in rows)
    ratio = mh_ratio(rows)
    lo, hi = bootstrap(rows)
    if flagged < FLAGGED_MIN:
        say = "too few flagged"
    elif ratio is not None and ratio >= RATIO_MIN and lo is not None and lo > 1:
        say = "met"
    else:
        say = "not met"
    f = [r for r in rows if r["flagged"]]
    u = [r for r in rows if not r["flagged"]]
    return {"verdict": say, "ratio": None if ratio is None else round(ratio, 3), "ci95": [lo and round(lo, 3), hi and round(hi, 3)],
            "flagged": flagged, "unflagged": len(u),
            "flagged_repaired": sum(r["repaired"] for r in f), "unflagged_repaired": sum(r["repaired"] for r in u),
            "flagged_share_ci95": wilson(sum(r["repaired"] for r in f), len(f)), "unflagged_share_ci95": wilson(sum(r["repaired"] for r in u), len(u))}


def status_letter(code: str) -> str | None:
    return {"M": "modified", "A": "added", "D": "removed", "R": "renamed", "T": "modified"}.get(code[:1])


# ---------------------------------------------------------------- reading the clone

class Slow(Exception):
    pass


_real_run = subprocess.run
_deadline = [math.inf]                   # set per commit by label(); no limit outside it


def _timed_run(*a, **k):
    left = _deadline[0] - time.monotonic()
    if left <= 0:
        raise Slow()
    k.setdefault("timeout", None if left == math.inf else left)
    try:
        return _real_run(*a, **k)
    except subprocess.TimeoutExpired as e:
        raise Slow() from e


def git(repo: str, *args: str) -> str:
    return _timed_run(["git", "-C", repo, *args], capture_output=True, text=True, errors="replace").stdout


def commit_files(repo: str, sha: str) -> list[dict]:
    """The commit's files against its first parent, in the shape the checks read (filename, status, patch)."""
    out = git(repo, "diff-tree", "--no-commit-id", "-r", "-M", "--name-status", f"{sha}^", sha)
    files = []
    for line in out.splitlines():
        cols = line.split("\t")
        st, path = status_letter(cols[0]), cols[-1]
        if st is None:
            continue
        patch = ""
        if st == "modified":
            raw = git(repo, "diff", "-U3", "--no-color", f"{sha}^", sha, "--", path)
            patch = raw[raw.find("@@"):] if "@@" in raw else ""
        files.append({"filename": path, "status": st, "patch": patch})
    return files


def sample(repo: str) -> list[str]:
    ids = git(repo, "log", "--no-merges", f"--since={WINDOW[0]}", f"--until={WINDOW[1]}T23:59:59", "--format=%H").split()
    ids.sort()
    random.Random(SEED).shuffle(ids)
    return ids


def label(repo: str, sha: str, at: int, idx) -> dict:
    row = {"sha": sha, "status": "read", "band": None, "fence": None, "stranger": None, "repaired": repaired(sha, at, idx)}
    _deadline[0] = time.monotonic() + TIME_LIMIT
    try:
        files = commit_files(repo, sha)
        if len(files) > MAX_TOTAL_FILES:
            return dict(row, status="too_many_files")
        modified = [f for f in files if f["status"] == "modified"]
        row["band"] = band(len(files))
        if row["band"] is None:
            return dict(row, status="too_many_files")
        if any(not FE._SKIP_PATH.search(f["filename"]) for f in modified):          # eligible for the fence check
            row["fence"] = bool(FE.find(repo, f"{sha}^", files)["fenced"])
        if 3 <= len(modified) <= MAX_FILES:
            hist = {f["filename"]: CC.history(repo, f"{sha}^", f["filename"]) for f in modified}
            row["stranger"] = any(v == CC.STRANGER for v in CC.strangers(hist).values())
    except Slow:
        return dict(row, status="timed_out")
    return row


def summarise(rows: list[dict], key: str) -> dict:
    use = [dict(band=r["band"], flagged=r[key], repaired=r["repaired"]) for r in rows if r["status"] == "read" and r[key] is not None]
    out = verdict(use)
    out["eligible"] = len(use)
    out["by_band"] = {str(i): {"flagged": sum(r["flagged"] for r in use if r["band"] == i), "eligible": sum(r["band"] == i for r in use)}
                      for i in range(len(BANDS))}
    return out


def main(argv=None) -> int:
    subprocess.run = _timed_run              # the checks call subprocess.run; give each commit's reads one deadline
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="read only this many commits (a trial of the script, not the registered run)")
    a = ap.parse_args(argv)
    log = parse_log(git(a.repo, "log", "--no-merges", "--format=%H%x1f%at%x1f%B%x1e"))
    idx, at = index_repairs(log), {s: t for s, t, _ in log}
    order, rows, started = sample(a.repo), [], time.time()
    want = a.limit or STEP
    while True:
        for sha in order[len(rows):want]:
            rows.append(label(a.repo, sha, at[sha], idx))
            if len(rows) % 50 == 0:
                print(f"{len(rows)} read, {time.time() - started:.0f}s", file=sys.stderr)
        fence, stranger = summarise(rows, "fence"), summarise(rows, "stranger")
        low = min(fence["flagged"], stranger["flagged"]) < FLAGGED_MIN
        if a.limit or not low or want >= CAP:
            break
        want = min(CAP, want + STEP)
    res = {"rubric": "eval/mesa_fixes_rubric.json", "repo_head": git(a.repo, "rev-parse", "HEAD").strip(), "sampled": len(rows),
           "status": dict(collections.Counter(r["status"] for r in rows)), "fence": fence, "stranger": stranger,
           "trial_only": bool(a.limit), "rows": [{k: r[k] for k in ("sha", "status", "band", "fence", "stranger", "repaired")} for r in rows],
           "made": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    pathlib.Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: res[k] for k in ("sampled", "status", "fence", "stranger")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
