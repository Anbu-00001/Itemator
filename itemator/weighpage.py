"""Build the page where a visitor weighs any PyPI or npm package in the browser: `python -m itemator.weighpage --out public/weigh`.

web/weigh.html is the page and web/weigh.js the measure (the same as itemator/weight.py; eval/weigh_agreement.py compares the two on
real packages). The study table is read from results/aidev_weight_v1_corrected.json at build time, so the page cannot say more than the file
does. The page's Content-Security-Policy lets it reach only api.deps.dev, pypi.org and registry.npmjs.org. Standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

from itemator.tryit import REPO, safe_json

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
RESULTS = ROOT / "results"
EXAMPLES = [{"eco": "PyPI", "name": "requests"}, {"eco": "npm", "name": "express"}, {"eco": "PyPI", "name": "pandas"},
            {"eco": "npm", "name": "jest"}]


def study(result: dict) -> dict:
    """The study's sentence and its three heaviest lines, from the results file only."""
    s, r = result["summary"], result["readme"]
    rows = {(x["pr"], x["name"]): x for x in result["rows"]}
    heaviest = []
    for h in s["heaviest"]:
        w = (rows.get((h["pr"], h["name"])) or {}).get("weight") or {}
        heaviest.append({**h, "at_least": bool(w.get("capped") or w.get("of", 0) > w.get("sized", 0))})
    sentence = (f"AI agents' pull requests in the public AIDev data set: of {r['lines_weighed']} dependencies the rules flagged as added beyond the task "
                f"({len(result['rows'])} sampled at random from {r['scanned_pull_requests']:,} pull requests, one per pull request; "
                f"{r['weighed_at_latest']} weighed at today's latest version because the line pinned none), the median brought {r['median_packages']} "
                f"packages and {r['median_mb']} MB; {r['ten_or_more_packages']} brought {r['threshold_packages']} or more packages and "
                f"{r['ten_mb_or_more']} weighed {r['threshold_mb']} MB or more. Measured {result['checked']}. The three heaviest:")
    note = ("Today's graphs and sizes, not the ones the pull request saw. Nothing here says a dependency was wrong to add; it says what "
            f"keeping it costs. Every line, and what was not weighed and why: {REPO}results/aidev_weight_v1_corrected.json (PyPI sizes re-read after a "
            f"fix to the wheel choice; the first run is {REPO}results/aidev_weight_v1.json)")
    return {"sentence": sentence, "heaviest": heaviest, "note": note, "least_note": True}


def page() -> str:
    js = (WEB / "weigh.js").read_text(encoding="utf-8")
    result = json.loads((RESULTS / "aidev_weight_v1_corrected.json").read_text(encoding="utf-8"))
    payload = {"examples": EXAMPLES, "study": study(result),
               "footer": f"Measure version {hashlib.sha256(js.encode()).hexdigest()[:12]} (web/weigh.js), the same as the CI job's "
                         "(itemator/weight.py). Standard HTML and JavaScript; no library, no model, no cookie."}
    html = (WEB / "weigh.html").read_text(encoding="utf-8")
    browser_js = js.replace('if (typeof module !== "undefined") module.exports', "if (false) module.exports")
    for marker, text in (("/*PAYLOAD*/", safe_json(payload)), ("/*WEIGH*/", browser_js.replace("</script", "<\\/script"))):
        assert html.count(marker) == 1
        html = html.replace(marker, text, 1)
    return html


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="itemator.weighpage", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--out", default="public/weigh")
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page(), encoding="utf-8")
    print(f"wrote {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
