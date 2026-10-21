"""Does the check give the same answer on python:3.12-alpine (with git from apk) as on the policy job's python:3.12-slim (with git
from apt)? Compares, on one merge request pipeline, the policy job's itemator.json with the `alpine-trial` job's
itemator-alpine.json, and records each job's seconds and the bytes each package manager downloaded (the policy job's from the
trial on !282, results/sci_spent_inputs_v2.json; the trial's from the size of the packages it fetched). Read-only (GitLab API GETs).
usage: python3 eval/image_trial.py --mr N   (writes results/alpine_trial_v1.json)"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import pathlib
import re
import subprocess
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "alpine_trial_v1.json"
JOB, ARTIFACT = "alpine-trial", "itemator-alpine.json"
P = "87291130"
SAME = ("rules_version", "state", "issue_iids", "unplaced", "truncated")


def api(path: str, raw: bool = False):
    r = subprocess.run(["glab", "api", f"projects/{P}/{path}"], capture_output=True, text=True, check=True)
    return r.stdout if raw else json.loads(r.stdout)


def answer(record: dict) -> dict:
    """The parts of a run that must not depend on the image: the state, the extras and what could not be placed."""
    out = {k: record.get(k) for k in SAME}
    out["extras"] = sorted((e.get("kind"), e.get("path"), e.get("name"), e.get("why")) for e in record.get("extras") or [])
    return out


def fetched_bytes(text: str) -> int | None:
    """The first number in the trial's apk-bytes.txt (`du -sb` of the packages apk fetched)."""
    m = re.match(r"\s*(\d+)", text)
    return int(m.group(1)) if m else None


def log_seconds(trace: str) -> float | None:
    """Seconds from the first to the last timestamp in a job log: what the job did, without the wait for a runner machine,
    which GitLab's duration includes and which varied by minutes between runs of the same job."""
    stamps = re.findall(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)Z", trace, re.M)
    if len(stamps) < 2:
        return None
    first, last = (datetime.fromisoformat(t) for t in (stamps[0], stamps[-1]))
    return round((last - first).total_seconds(), 1)


def images(v1: dict, v2: dict, alpine_image_bytes: int, apk_bytes: int) -> dict:
    """MB each image downloads when a runner has none (Docker Hub's compressed size), and MB of git downloaded on every run:
    the full image from the v1 footprint inputs, slim from v2, Alpine from Docker Hub and this trial."""
    mb = lambda b: round(b / 1e6, 1)  # noqa: E731
    return {"full": {"image": "python:3.12", "image_mb": mb(v1["image_compressed_bytes"]), "git_mb_per_run": 0},
            "slim": {"image": "python:3.12-slim", "image_mb": mb(v2["image_compressed_bytes"]), "git_mb_per_run": mb(v2["apt_bytes"])},
            "alpine": {"image": "python:3.12-alpine", "image_mb": mb(alpine_image_bytes), "git_mb_per_run": mb(apk_bytes)}}


def hub_bytes(tag: str) -> int:
    hub = json.load(urllib.request.urlopen(f"https://hub.docker.com/v2/repositories/library/python/tags/{tag}", timeout=30))
    return [i["size"] for i in hub["images"] if i.get("architecture") == "amd64" and i.get("os") == "linux"][0]


def compare(full: dict, trial: dict) -> dict:
    a, b = answer(full), answer(trial)
    return {"same": a == b, "differs_in": sorted(k for k in a if a[k] != b[k]), "extras": len(a["extras"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mr", type=int, required=True)
    a = ap.parse_args(argv)
    pipe = api(f"merge_requests/{a.mr}")["head_pipeline"]["id"]
    jobs = {j["name"]: j for j in api(f"pipelines/{pipe}/jobs?per_page=100")}
    full, trial = jobs["itemator"], jobs[JOB]
    policy_apt = json.loads((ROOT / "results" / "sci_spent_inputs_v2.json").read_text())["apt_bytes"]
    rec = {"mr": a.mr, "pipeline": pipe,
           "jobs": {n: {"id": j["id"], "status": j["status"], "seconds": j["duration"],
                        "log_seconds": log_seconds(api(f"jobs/{j['id']}/trace", raw=True))} for n, j in (("itemator", full), (JOB, trial))},
           "downloaded_per_run_bytes": {"itemator (apt git)": policy_apt,
                                        f"{JOB} (apk git)": fetched_bytes(api(f"jobs/{trial['id']}/artifacts/apk-bytes.txt", raw=True))},
           **compare(json.loads(api(f"jobs/{full['id']}/artifacts/itemator.json", raw=True)),
                     json.loads(api(f"jobs/{trial['id']}/artifacts/{ARTIFACT}", raw=True)))}
    v1, v2 = (json.loads((ROOT / "results" / f"sci_spent_inputs_v{v}.json").read_text()) for v in (1, 2))
    rec["images"] = images(v1, v2, hub_bytes("3.12-alpine"), rec["downloaded_per_run_bytes"][f"{JOB} (apk git)"])
    OUT.write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec))
    return 0 if rec["same"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
