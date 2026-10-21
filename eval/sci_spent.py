"""What the check itself costs, by the same SCI method and coefficients as eval/sci_estimate.py, set against what one `remove`
saves: `python3 eval/sci_spent.py --fetch` (reads this project's job records and Docker Hub, writes results/sci_spent_inputs_v1.json)
then `python3 eval/sci_spent.py` (writes results/sci_spent_v1.json). `--version 2` does the same for the slim image the policy
switched to on 2026-10-21 (jobs after that commit only; git then comes from apt on every run, so its download counts even
when the image is cached) and writes the _v2 files; v1 stays as the before.

Spent per merge request pipeline = the `itemator` job: its runner seconds (GitLab's own job durations), the repository clone it
makes (GIT_DEPTH 0, measured as a bare clone's pack), and the python:3.12 image, which a runner either has cached (0 MB) or pulls
(Docker Hub's compressed size). The card flow's model calls are counted, not converted: Duo publishes no energy per call, so they
are left out of the grams and said to be left out. Saved per fresh install after a `remove` = results/sci_estimate_v1.json."""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
RES = ROOT / "results"
sys.path.insert(0, str(ROOT))
from itemator.sci import per_install  # noqa: E402

INPUTS, OUT = RES / "sci_spent_inputs_v1.json", RES / "sci_spent_v1.json"

PROJECT = "87291130"
VERSIONS = {1: {"image": "python:3.12", "hub": "library/python/tags/3.12", "after": "", "apt_bytes": 0},
            # the policy commit that switched the injected job (policy project 87623122, 4b032ceb); apt's "Need to get" on the
            # trial job 17337337762 (merge request !282), the only run that printed it
            2: {"image": "python:3.12-slim", "hub": "library/python/tags/3.12-slim", "after": "2026-10-21T05:32:14Z",
                "apt_bytes": 23800000},
            # the policy commit that switched it to Alpine (557f22c0); apk's packages for git measured on trial job 17339280561
            3: {"image": "python:3.12-alpine", "hub": "library/python/tags/3.12-alpine", "after": "2026-10-21T07:40:04Z",
                "apt_bytes": 9769586}}


def paths(version: int):
    return RES / f"sci_spent_inputs_v{version}.json", RES / f"sci_spent_v{version}.json"


def fetch(version: int = 1) -> dict:
    v = VERSIONS[version]
    jobs = []
    for page in range(1, 6):
        r = subprocess.run(["glab", "api", f"projects/{PROJECT}/jobs?scope[]=success&per_page=100&page={page}"], capture_output=True, text=True, check=True)
        jobs += [j for j in json.loads(r.stdout) if j["name"] == "itemator" and j.get("duration") and j["created_at"] > v["after"]]
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "clone", "-q", "--bare", "https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/39194174/showcase.git", d + "/r"], check=True)
        pack = sum(p.stat().st_size for p in pathlib.Path(d, "r", "objects", "pack").iterdir())
    hub = json.load(urllib.request.urlopen(f"https://hub.docker.com/v2/repositories/{v['hub']}", timeout=30))
    image = [i["size"] for i in hub["images"] if i.get("architecture") == "amd64" and i.get("os") == "linux"]
    return {"read_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "job_seconds": sorted(round(j["duration"], 1) for j in jobs),
            "job_ids": sorted(j["id"] for j in jobs), "clone_bytes": pack, "image": v["image"], "image_compressed_bytes": image[0],
            "apt_bytes": v["apt_bytes"]}


def compute(inputs: dict, saved: dict) -> dict:
    secs = inputs["job_seconds"]
    s = (statistics.median(secs), statistics.median(secs))
    clone_mb, apt_mb, image_mb = inputs["clone_bytes"] / 1e6, inputs.get("apt_bytes", 0) / 1e6, inputs["image_compressed_bytes"] / 1e6
    cached, pulled = per_install(clone_mb + apt_mb, s), per_install(clone_mb + apt_mb + image_mb, s)
    live, median = saved["live"], saved["median"]
    out = {"inputs": {"jobs": len(secs), "median_job_seconds": s[0], "clone_mb": round(clone_mb, 2), "image_mb": round(image_mb)},
           "spent_g_per_check": {"image_cached": {e: round(cached[e]["sci_g_per_install"], 4) for e in ("low", "high")},
                                 "image_pulled": {e: round(pulled[e]["sci_g_per_install"], 3) for e in ("low", "high")}},
           "saved_g_per_install_live": {e: live[e]["sci_g_per_install"] for e in ("low", "high")},
           "saved_g_per_install_median": {e: median[e]["sci_g_per_install"] for e in ("low", "high")}}
    # installs of the dependency that one `remove` must avoid to repay one check, at the same end of the bracket
    for case in ("live", "median"):
        out[f"installs_to_repay_one_check_{case}"] = {
            k: {e: round(out["spent_g_per_check"][k][e] / out[f"saved_g_per_install_{case}"][e], 1) for e in ("low", "high")}
            for k in ("image_cached", "image_pulled")}
    if apt_mb:
        out["inputs"].update(image=inputs["image"], apt_mb=round(apt_mb, 1))
    out["left_out"] = "the card flow's model calls (about 6 per card; Duo publishes no energy per call) and the Pages and API requests"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--version", type=int, choices=sorted(VERSIONS), default=1)
    a = ap.parse_args(argv)
    inputs_path, out_path = paths(a.version)
    if a.fetch:
        inputs_path.write_text(json.dumps(fetch(a.version), indent=1) + "\n")
    res = compute(json.loads(inputs_path.read_text()), json.loads((RES / "sci_estimate_v1.json").read_text()))
    out_path.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k.startswith("installs_")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
