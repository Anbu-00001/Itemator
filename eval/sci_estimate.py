"""What one `remove` of an unasked dependency avoids, stated with the Green Software Foundation's SCI method (v1.1.0,
https://sci.greensoftware.foundation/: SCI = (O + M) per R, O = E * I). Run: python3 eval/sci_estimate.py (writes results/sci_estimate_v1.json).

Measured (ours): the download of the live case and this project's pipelines (the thread on !219, results/weight_live.json), the
median download of the 289 weighed agent dependencies (results/aidev_weight_v1_corrected.json), and the seconds a fresh install
of one line adds above an empty install on GitLab's small Linux runner (results/install_time_*_v1.json). Borrowed: every
coefficient below, with its source. R = one fresh CI install; the baseline is the same install after the `remove`, under the
same assumptions, as the specification asks. The span is almost all the network coefficient, which outside papers dispute, so the
output is a bracket, never one number. Nothing here measures energy: the output says so."""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RES = ROOT / "results"
OUT = RES / "sci_estimate_v1.json"

sys.path.insert(0, str(ROOT))
from itemator.sci import (EL_S, GRID_G_PER_KWH, HOST_VCPU, MEM_GB, MEM_W_PER_GB, NET_KWH_PER_GB, PUE, SOURCES, TE_G,  # noqa: E402,F401
                          VCPU, VCPU_W, per_install)


def live_case(weight_live: dict) -> tuple[float, int]:
    """The download and the pipeline count, as the live thread printed them (the card's own words, rounded to whole MB)."""
    t = weight_live["thread"]
    mb = re.search(r"about (\d+(?:\.\d+)?) MB to download on every fresh install", t)
    pipes = re.search(r"this project ran (\d+) pipelines in the last 30 days", t)
    assert mb and pipes, "the live thread no longer says the download and the pipeline count"
    return float(mb.group(1)), int(pipes.group(1))


def compute(weight_live: dict, weight: dict, pypi: dict, npm: dict) -> dict:
    mb, pipelines = live_case(weight_live)
    secs = tuple(sorted((pypi["summary"]["median_seconds_above_baseline"], npm["summary"]["median_seconds_above_baseline"])))
    live, median = per_install(mb, secs), per_install(weight["readme"]["median_mb"], secs)
    r = lambda x, n=3: float(f"{x:.{n}g}")                                         # noqa: E731
    return {
        "inputs": {"live_mb": mb, "pipelines_30_days": pipelines, "median_mb": weight["readme"]["median_mb"], "seconds_added": list(secs)},
        "live": {k: {x: r(v) for x, v in d.items()} for k, d in live.items()},
        "median": {k: {x: r(v) for x, v in d.items()} for k, d in median.items()},
        "readme": {
            "live_g_low": round(live["low"]["sci_g_per_install"], 3), "live_g_high": round(live["high"]["sci_g_per_install"], 1),
            "live_month_g_low": round(live["low"]["sci_g_per_install"] * pipelines), "live_month_kg_high": round(live["high"]["sci_g_per_install"] * pipelines / 1000, 1),
            "median_g_low": round(median["low"]["sci_g_per_install"], 4), "median_g_high": round(median["high"]["sci_g_per_install"], 3),
            "network_share_low": round(live["low"]["network_kwh"] / (live["low"]["network_kwh"] + live["low"]["runner_kwh"]), 3),
            "network_share_high": round(live["high"]["network_kwh"] / (live["high"]["network_kwh"] + live["high"]["runner_kwh"]), 3),
        },
    }


def main():
    load = lambda n: json.loads((RES / n).read_text())                             # noqa: E731
    out = {"what": "Grams CO2e one `remove` avoids per fresh CI install (R), as an SCI delta: the same install with and without the dependency. "
                   "Downloads, pipelines and install seconds are measured; every coefficient is borrowed. Energy is not measured here.",
           "coefficients": {"network_kwh_per_gb": list(NET_KWH_PER_GB), "vcpu": VCPU, "mem_gb": MEM_GB, "pue": PUE, "vcpu_w": list(VCPU_W),
                            "mem_w_per_gb": MEM_W_PER_GB, "grid_g_per_kwh": list(GRID_G_PER_KWH), "embodied_total_g": TE_G, "life_s": EL_S,
                            "host_vcpu": HOST_VCPU},
           "sources": SOURCES,
           **compute(load("weight_live.json"), load("aidev_weight_v1_corrected.json"), load("install_time_pypi_v1.json"), load("install_time_npm_v1.json")),
           "limits": ["a delta in a pipeline's SCI, not a full SCI score of the pipeline",
                      "a monthly figure multiplies a rate by this project's pipelines; it holds only if each pipeline installs without a cache",
                      "it counts only when a reviewer actually replies `remove`",
                      "the low and high ends pair low with low and high with high; they are ends of a range, not an average",
                      "install seconds are medians of single lines on a shared runner, not the live case's own",
                      "the embodied figure reads Cloud Carbon Footprint's unitless file as kg; it is a small share of the live case and most of the low end of the median case, so that end is the least certain",
                      "the card flow's model calls are outside this figure: Duo's model energy is not disclosed"]}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["readme"]))


if __name__ == "__main__":
    main()
