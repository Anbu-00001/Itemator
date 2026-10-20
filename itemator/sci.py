"""What keeping a weighed dependency costs in grams CO2e, by the Green Software Foundation's SCI method (v1.1.0,
https://sci.greensoftware.foundation/: SCI = (O + M) per R, O = E * I), with R = one fresh CI install and the baseline the same
install after a `remove`. The download is measured (itemator/weight.py); the install seconds are the medians of our own
install-time studies (results/install_time_*_v1.json); every coefficient is borrowed, with its source in SOURCES. The span is almost
all the network coefficient, which outside papers dispute, so the answer is a bracket, never one number. Nothing here measures
energy. eval/sci_estimate.py uses the same code for results/sci_estimate_v1.json. Standard library only; information only.
"""
from __future__ import annotations

import math

# kWh per GB transferred. The low end leaves out the access network; the high end is a whole-system figure that says it overestimates.
NET_KWH_PER_GB = (0.001, 0.055 + 0.059)
# GitLab's small hosted Linux runner: 2 vCPU, 8 GB, Google Cloud us-east1 (docs.gitlab.com/ci/runners/hosted_runners/linux/).
VCPU, MEM_GB, PUE = 2, 8, 1.1
VCPU_W = (0.71, 4.26)              # Cloud Carbon Footprint, GCP, idle and full load per vCPU
MEM_W_PER_GB = 0.392               # Cloud Carbon Footprint, per GB of memory (counted only in the high case)
GRID_G_PER_KWH = (432, 579)        # Google Cloud region table, 2025: us-central1, us-east1
# Embodied: M = TE * (TiR / EL) * (RR / ToR). TE from Cloud Carbon Footprint's GCP mean (its file gives no unit; read as kg).
TE_G, EL_S, HOST_VCPU = 1230 * 1000, 4 * 365.25 * 86400, 32
# Seconds one added line adds to a fresh install above an empty one, low and high: the PyPI and npm medians of
# results/install_time_pypi_v1.json and results/install_time_npm_v1.json (a test keeps them equal).
SECONDS = (1.21, 1.65)
SOURCES = {
    "sci": "Green Software Foundation, SCI specification v1.1.0, https://sci.greensoftware.foundation/ (read 2026-10-20)",
    "network_low": "Cloud Carbon Footprint methodology, 0.001 kWh/GB, data-centre traffic only, https://www.cloudcarbonfootprint.org/docs/methodology/",
    "network_high": "Sustainable Web Design v4: data centres 0.055 + networks 0.059 kWh/GB, which it says will overestimate, https://sustainablewebdesign.org/estimating-digital-emissions/ (read 2026-10-20)",
    "network_disputed": "Mytton, Lunden and Malmodin, Journal of Industrial Ecology 28(4), 2024, doi 10.1111/jiec.13512: kWh/GB figures are not accurate enough",
    "runner_power": "Cloud Carbon Footprint methodology, GCP per-vCPU and per-GB-memory watts, PUE 1.1",
    "grid": "Google Cloud region carbon table, 2025 data, https://cloud.google.com/sustainability/region-carbon",
    "embodied": "Cloud Carbon Footprint embodied-emissions method, 4-year life, https://www.cloudcarbonfootprint.org/docs/embodied-emissions/",
}


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


def grams(g: float) -> str:
    """Two significant figures, in kg from a kilogram up."""
    def two(x):
        if x <= 0:
            return 0, 0
        digits = 1 - math.floor(math.log10(x))
        if round(x, digits) >= 10 ** (2 - digits):        # 9.97 rounds to 10: one digit fewer
            digits -= 1
        return round(x, digits), max(digits, 0)
    (v, d), unit = two(g), "g"
    if v >= 1000:
        (v, d), unit = two(g / 1000), "kg"
    return f"{v:.{d}f} {unit}"


def part(w: dict | None) -> str | None:
    """The card's words for a weight from itemator/weight.py, or None when nothing was sized. Unknown sizes make it "at least"."""
    if not w or w.get("weight") != "ok" or not w.get("sized"):
        return None
    g = per_install(w["bytes"] / 1e6, SECONDS)
    lo, hi = g["low"]["sci_g_per_install"], g["high"]["sci_g_per_install"]
    least = "at least " if w["capped"] or w["of"] > w["sized"] else ""
    words = f"by the SCI method, a bracket from borrowed coefficients: {least}{grams(lo)} to {grams(hi)} CO2e per fresh install"
    runs = w.get("pipelines") or {}
    if runs.get("count"):
        month = "at least " if least or runs.get("at_least") else ""
        words += f" and {month}{grams(lo * runs['count'])} to {grams(hi * runs['count'])} a month at those pipelines"
    return words
