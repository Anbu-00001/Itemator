"""Build the green check, where a visitor pastes a change and its issue: `python -m itemator.greenpage --out public/green`.

web/green.html is the page. It lists a change's new dependencies with web/deps_rule.js (rule 1 of itemator/extras.py; eval/green_agreement.py
compares the two on real manifest diffs), weighs the ones the issue did not ask for with web/weigh.js (the same as itemator/weight.py), and
turns their download into grams CO2e with web/green.js (eval/sci_estimate.py's per_install). The coefficients, the install seconds and the
agreement sentence are read from the results files at build time, so the page cannot say more than they do. Standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

from itemator.tryit import REPO, safe_json

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
RESULTS = ROOT / "results"
AGREEMENT = "green_agreement_v2.json"


def payload() -> dict:
    sci = json.loads((RESULTS / "sci_estimate_v1.json").read_text(encoding="utf-8"))
    agree = json.loads((RESULTS / AGREEMENT).read_text(encoding="utf-8"))
    secs = sci["inputs"]["seconds_added"]
    c = sci["coefficients"]
    files = [WEB / n for n in ("deps_rule.js", "weigh.js", "green.js")]
    version = hashlib.sha256(b"".join(f.read_bytes() for f in files)).hexdigest()[:12]
    return {
        "examples": json.loads((WEB / "green_examples.json").read_text(encoding="utf-8")),
        "coefficients": c, "seconds": secs,
        "agreement": (f"{agree['identical']:,} of {agree['units']:,} real and test manifest diffs it lists exactly what the Python lists "
                      f"({REPO}results/{AGREEMENT}, checked {agree['checked']})"),
        "sci": (f"the Green Software Foundation's SCI method, as a delta: the same install with and without the dependency. Per fresh install, "
                f"the download costs network energy ({c['network_kwh_per_gb'][0]} to {round(c['network_kwh_per_gb'][1], 3)} kWh per GB) and the "
                f"install costs runner time ({secs[0]} to {secs[1]} s per added line, the medians of our install-time studies, on a {c['vcpu']}-vCPU "
                f"runner), at {c['grid_g_per_kwh'][0]} to {c['grid_g_per_kwh'][1]} g CO2e per kWh, plus the runner's embodied share. Download sizes are "
                f"measured here; every coefficient is borrowed and listed with its source in {REPO}results/sci_estimate_v1.json. It counts only "
                "if someone says \"remove\", and only for installs without a cache."),
        "range_note": ("The low and high ends pair low with low and high with high; they are the ends of a range, not an average. The install "
                       "seconds are medians for one added line on a shared runner, not this package's own."),
        "footer": (f"Page version {version} (web/deps_rule.js, web/weigh.js, web/green.js). Rules v6, the same as the CI job's. "
                   "Standard HTML and JavaScript; no library, no model, no cookie."),
    }


def page() -> str:
    html = (WEB / "green.html").read_text(encoding="utf-8")
    weigh = (WEB / "weigh.js").read_text(encoding="utf-8").replace('if (typeof module !== "undefined") module.exports', "if (false) module.exports")
    parts = (("/*PAYLOAD*/", safe_json(payload())), ("/*DIFF*/", (WEB / "try_checks.js").read_text(encoding="utf-8")),
             ("/*RULE*/", (WEB / "deps_rule.js").read_text(encoding="utf-8")), ("/*WEIGH*/", weigh),
             ("/*GREEN*/", (WEB / "green.js").read_text(encoding="utf-8")))
    for marker, text in parts:
        assert html.count(marker) == 1, marker
        html = html.replace(marker, text.replace("</script", "<\\/script"), 1)
    return html


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="itemator.greenpage", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--out", default="public/green")
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page(), encoding="utf-8")
    print(f"wrote {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
