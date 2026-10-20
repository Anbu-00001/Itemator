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

ROOT = pathlib.Path(__file__).resolve().parent.parent
RES = ROOT / "results"
OUT = RES / "sci_estimate_v1.json"

# kWh per GB transferred. The low end leaves out the access network; the high end is a whole-system figure that says it overestimates.
NET_KWH_PER_GB = (0.001, 0.055 + 0.059)
# GitLab's small hosted Linux runner: 2 vCPU, 8 GB, Google Cloud us-east1 (docs.gitlab.com/ci/runners/hosted_runners/linux/).
VCPU, MEM_GB, PUE = 2, 8, 1.1
VCPU_W = (0.71, 4.26)              # Cloud Carbon Footprint, GCP, idle and full load per vCPU
MEM_W_PER_GB = 0.392               # Cloud Carbon Footprint, per GB of memory (counted only in the high case)
GRID_G_PER_KWH = (432, 579)        # Google Cloud region table, 2025: us-central1, us-east1
# Embodied: M = TE * (TiR / EL) * (RR / ToR). TE from Cloud Carbon Footprint's GCP mean (its file gives no unit; read as kg).
TE_G, EL_S, HOST_VCPU = 1230 * 1000, 4 * 365.25 * 86400, 32
SOURCES = {
    "sci": "Green Software Foundation, SCI specification v1.1.0, https://sci.greensoftware.foundation/ (read 2026-10-20)",
    "network_low": "Cloud Carbon Footprint methodology, 0.001 kWh/GB, data-centre traffic only, https://www.cloudcarbonfootprint.org/docs/methodology/",
    "network_high": "Sustainable Web Design v4: data centres 0.055 + networks 0.059 kWh/GB, which it says will overestimate, https://sustainablewebdesign.org/estimating-digital-emissions/ (read 2026-10-20)",
    "network_disputed": "Mytton, Lunden and Malmodin, Journal of Industrial Ecology 28(4), 2024, doi 10.1111/jiec.13512: kWh/GB figures are not accurate enough",
    "runner_power": "Cloud Carbon Footprint methodology, GCP per-vCPU and per-GB-memory watts, PUE 1.1",
    "grid": "Google Cloud region carbon table, 2025 data, https://cloud.google.com/sustainability/region-carbon",
    "embodied": "Cloud Carbon Footprint embodied-emissions method, 4-year life, https://www.cloudcarbonfootprint.org/docs/embodied-emissions/",
}


def live_case(weight_live: dict) -> tuple[float, int]:
    """The download and the pipeline count, as the live thread printed them (the card's own words, rounded to whole MB)."""
    t = weight_live["thread"]
    mb = re.search(r"about (\d+(?:\.\d+)?) MB to download on every fresh install", t)
    pipes = re.search(r"this project ran (\d+) pipelines in the last 30 days", t)
    assert mb and pipes, "the live thread no longer says the download and the pipeline count"
    return float(mb.group(1)), int(pipes.group(1))


def per_install(mb: float, seconds: tuple[float, float]) -> dict:
    """Grams CO2e avoided per fresh install by not downloading `mb` and not spending `seconds` of runner time, low and high."""
    gb = mb / 1000
    runner_w = (VCPU * VCPU_W[0] * PUE, (VCPU * VCPU_W[1] + MEM_GB * MEM_W_PER_GB) * PUE)
    out = {}
    for end, i in (("low", 0), ("high", 1)):
        e_net = gb * NET_KWH_PER_GB[i]
        e_run = runner_w[i] * seconds[i] / 3600 / 1000
        o = (e_net + e_run) * GRID_G_PER_KWH[i]
        m = TE_G * (seconds[i] / EL_S) * (VCPU / HOST_VCPU)
        out[end] = {"network_kwh": e_net, "runner_kwh": e_run, "operational_g": o, "embodied_g": m, "sci_g_per_install": o + m}
    return out


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
