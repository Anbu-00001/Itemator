"""Run the card's added-line checks on public diffs of real supply-chain incidents. A demonstration, not a measure: the rules
were written after reading these diffs, so "fires" here says the rule matches the shape it was written for.

The diffs are fetched at run time from their public pages and are not stored in this repository (they are other people's code);
the result file keeps the address, the SHA-256 of the fetched text, the files, and what each check said. Run:
    python3 eval/incident_replay.py --out results/incident_replay_v1.json
Standard library only. GET requests only. The base rules (itemator/extras.py) run with an empty issue text."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request

from itemator import diffreader as DR
from itemator import extras as X
from itemator import moving as MV
from itemator import shapes as SH
from itemator import untrusted as UT

INCIDENTS = (
    {"id": "amazon-q-1.84.0", "what": "a build script that downloads a file and writes it over a source file",
     "page": "https://github.com/aws/aws-toolkit-vscode/commit/678851bbe9776228f55e0460e66a6167ac2a1685",
     "expects": "shapes"},
    {"id": "nx-s1ngularity", "what": "a workflow that pastes a pull request title into a shell line",
     "page": "https://github.com/nrwl/nx/pull/32458",
     "expects": "untrusted"},
    {"id": "xz-test-files", "what": "five binary files added as test data (the build-script half was only in the release tarball)",
     "page": "https://github.com/tukaani-project/xz/commit/cf44e4b7f5dfdbf8c78aef377c10f71e274f63c0",
     "expects": "binary"},
)

NOT_REPLAYED = (
    {"id": "xz-release-tarball", "why": "the build-script half of the xz attack was only in the release tarball, never in a git change, so no merge request check can see it"},
    {"id": "tj-actions-changed-files", "why": "the malicious commit page is gone, so there is no public diff to run"},
    {"id": "account-and-registry takeovers", "why": "ua-parser-js, colors.js and the torchtriton package arrived through a stolen account or a package registry, not a merge request"},
)


def fetch(page: str) -> str:
    req = urllib.request.Request(page + ".patch", headers={"User-Agent": "itemator-replay"})
    with urllib.request.urlopen(req, timeout=60) as r:           # noqa: S310 -- fixed https addresses above
        return r.read().decode("utf-8", "replace")


def files_of(patch: str) -> list[dict]:
    return DR.files_of(patch)


def run(incident: dict, text: str) -> dict:
    files = files_of(text)
    return {"id": incident["id"], "what": incident["what"], "page": incident["page"], "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "files": [{"path": f["filename"], "status": f["status"], "binary": f["binary"]} for f in files],
            "shapes": [{k: v for k, v in d.items() if k != "text"} for d in SH.find(files)],
            "untrusted": [{k: v for k, v in d.items() if k != "text"} for d in UT.find(files)],
            "moving": [{k: v for k, v in d.items() if k != "text"} for d in MV.find(files)],
            "extras": [{"kind": e.kind, "path": e.path} for e in X.extras("", [{**f, "additions": 0, "deletions": 0} for f in files])]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rows = [run(i, fetch(i["page"])) for i in INCIDENTS]
    for r, i in zip(rows, INCIDENTS):
        r["expected_check"] = i["expects"]
        r["fired"] = (any(e["kind"] == "binary_or_large_added" for e in r["extras"]) if i["expects"] == "binary" else bool(r[i["expects"]]))
    with open(args.out, "w") as fh:
        json.dump({"note": "a demonstration: the rules were written after reading these diffs", "incidents": rows, "not_replayed": list(NOT_REPLAYED)}, fh, indent=1)
    for r in rows:
        print(f"{r['id']}: {'fires' if r['fired'] else 'does not fire'} ({r['expected_check']}); files: {len(r['files'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
