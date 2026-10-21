"""How often does the new-powers line (itemator/powers.py) speak on real agent pull requests, and on what?
Reads the replay cache (eval/cache/<pr id>.json). The cache holds patches, not the files' base text, so a file's removed
and context lines stand in for what it did before: the count is an upper bound on what the CI job, which reads the base
text, would say. Each firing is listed with its line and the builder's reading of it.
usage: python3 eval/powers_noise.py --out results/powers_noise_v1.json"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from itemator import powers as P  # noqa: E402

CACHE = ROOT / "eval" / "cache"
# The builder's coding agent read each line (a model, one reader): is it the power the line names?
LABELS = {
    ("3006276172", "process"): "wrong: the words are inside a log message, not a call",
    ("3091643325", "environment"): "right: copies the whole environment to pass to a child process",
    ("3091643325", "process"): "right: runs a test command",
    ("3177549523", "process"): "right: imports execSync to run commands",
    ("3193634550", "dynamic"): "right: imports a module by a name built at run time",
    ("3225499913", "network"): "right: sends an HTTP DELETE",
    ("3236144651", "network"): "right: fetches a URL",
    ("3238111966", "network"): "right: holds an HTTP client",
}


def measure(cache: pathlib.Path) -> dict:
    read, firings = 0, []
    for p in sorted(cache.glob("*.json")):
        try:
            files = json.loads(p.read_text()).get("files") or []
        except (ValueError, AttributeError):
            continue
        read += 1
        for d in P.find(files):
            firings.append({"pull_request": p.stem, **d, "label": LABELS.get((p.stem, d["power"]), "not labelled")})
    right = sum(x["label"].startswith("right") for x in firings)
    return {"what": __doc__.split("\n")[0], "bound": "upper: removed and context lines stand in for the base text",
            "pull_requests_read": read, "pull_requests_spoken_on": len({x["pull_request"] for x in firings}),
            "lines_named": len(firings), "lines_read_as_right": right, "firings": firings}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    res = measure(pathlib.Path(a.cache))
    pathlib.Path(a.out).write_text(json.dumps(res, indent=2) + "\n")
    print(f"{res['pull_requests_spoken_on']} of {res['pull_requests_read']} pull requests; "
          f"{res['lines_read_as_right']} of {res['lines_named']} lines read as right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
