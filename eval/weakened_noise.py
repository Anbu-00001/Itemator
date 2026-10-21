"""How often does the weakened-tests check (itemator/hollow.py) speak on real agent pull requests, and on what?
Reads the replay cache (eval/cache/<pr id>.json, the files of the AIDev pull requests the replays sampled) with an
empty issue text, so every firing is shown; each firing is listed with the lines that made it, for reading.
usage: python3 eval/weakened_noise.py --out results/weakened_noise_v1.json"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from itemator import extras as X  # noqa: E402
from itemator import hollow as H  # noqa: E402

CACHE = ROOT / "eval" / "cache"
# The builder's reading of each firing, by its coding agent (a model, one reader), with the public page it checked
LABELS = {"3242243860": "looks right: GitHub Copilot skipped the test of the feature it was building; the pull request "
                        "(https://github.com/backstage/backstage/pull/30586) closed without merging"}


def lines(f: dict) -> list[str]:
    """The added and removed lines of a firing file that the check read: vacuous, skips, and the assertions lost."""
    out = []
    for s, t in X._lines(f.get("patch")):
        if s == "+" and (H._VACUOUS.search(t) or H._SKIP.search(t)) or s == "-" and (H._SKIP.search(t) or (
                X._ASSERT.search(t) and not H._VACUOUS.search(t))):
            out.append(f"{s}{t.strip()[:120]}")
    return out[:8]


def measure(cache: pathlib.Path) -> dict:
    read = with_tests = 0
    firings = []
    for p in sorted(cache.glob("*.json")):
        try:
            files = json.loads(p.read_text()).get("files") or []
        except (ValueError, AttributeError):
            continue
        read += 1
        tests = [f for f in files if X.is_test_file(f.get("filename") or "") and f.get("status") == "modified"]
        with_tests += bool(tests)
        listed = {e.path for e in X.extras("", files) if e.kind == "tests_removed"}
        for e in H.find("", files, listed):
            f = next(f for f in files if f["filename"] == e.path)
            firings.append({"pull_request": p.stem, "path": e.path, "why": e.why, "lines": lines(f),
                            "label": LABELS.get(p.stem, "not labelled")})
    prs = len({x["pull_request"] for x in firings})
    return {"what": __doc__.split("\n")[0], "pull_requests_read": read, "with_a_modified_test_file": with_tests,
            "pull_requests_spoken_on": prs, "files_named": len(firings), "firings": firings}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    res = measure(pathlib.Path(a.cache))
    pathlib.Path(a.out).write_text(json.dumps(res, indent=2) + "\n")
    print(f"{res['pull_requests_spoken_on']} of {res['pull_requests_read']} pull requests "
          f"({res['with_a_modified_test_file']} change a test file), {res['files_named']} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
