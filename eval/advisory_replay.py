"""Does the untrusted-text check name the vulnerable line of real advisories about GitHub Actions workflows?
The rules are in eval/advisory_replay_rubric.json, written before the check was run on these cases. Read-only; the diffs are fetched
from the GitHub API at run time and are not stored. Standard library only (needs the `gh` tool or network access).

usage: python3 eval/advisory_replay.py --out results/advisory_replay_v1.json"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from itemator import moving as MV  # noqa: E402
from itemator import shapes as SH  # noqa: E402
from itemator import untrusted as UT  # noqa: E402

RUBRIC = ROOT / "eval" / "advisory_replay_rubric.json"
_HUNK = re.compile(r"^@@ -(\d+(?:,\d+)?) \+(\d+(?:,\d+)?) @@(.*)$")
_SWAP = {"added": "removed", "removed": "added"}


def reverse_patch(patch: str) -> str:
    """The unified hunks of the opposite change: added lines become removed ones and the other way round, hunk ranges swapped."""
    out = []
    for line in (patch or "").split("\n"):
        m = _HUNK.match(line)
        if m:
            out.append(f"@@ -{m.group(2)} +{m.group(1)} @@{m.group(3)}")
        elif line.startswith("+"):
            out.append("-" + line[1:])
        elif line.startswith("-"):
            out.append("+" + line[1:])
        else:
            out.append(line)
    return "\n".join(out)


def turned_round(files: list[dict]) -> list[dict]:
    return [{"filename": f["filename"], "status": _SWAP.get(f.get("status"), f.get("status", "modified")), "patch": reverse_patch(f.get("patch", ""))} for f in files]


def fetch(repo: str, sha: str) -> list[dict]:
    """The files of a commit as the checks read them: {filename, status, patch}."""
    url = f"repos/{repo}/commits/{sha}"
    got = subprocess.run(["gh", "api", url], capture_output=True, text=True)
    text = got.stdout if got.returncode == 0 else urllib.request.urlopen(urllib.request.Request("https://api.github.com/" + url, headers={"User-Agent": "itemator-eval"}), timeout=30).read().decode()
    return [{"filename": f["filename"], "status": f.get("status", "modified"), "patch": f.get("patch", "")} for f in json.loads(text).get("files", [])]


def says(files: list[dict]) -> dict:
    return {"untrusted": UT.find(files), "shapes": SH.find(files), "moving": MV.find(files)}


def summarise(case: dict, files: list[dict]) -> dict:
    back, fixed = says(turned_round(files)), says(files)
    cut = lambda rows: [{k: v for k, v in r.items() if k != "text"} for r in rows]       # noqa: E731 -- no diff text is published
    return {"advisory": case["advisory"], "repo": case["repo"], "fix": case["fix"][:12], "files": [f["filename"] for f in files],
            "vulnerable_diff": {k: cut(v) for k, v in back.items()}, "fix_as_committed": {k: cut(v) for k, v in fixed.items()},
            "caught": bool(back["untrusted"]), "silent_on_fix": not fixed["untrusted"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    cases = json.loads(RUBRIC.read_text())["cases"]
    rows = [summarise(c, fetch(c["repo"], c["fix"])) for c in cases]
    out = {"rubric": "eval/advisory_replay_rubric.json", "cases": len(rows), "caught": sum(r["caught"] for r in rows), "silent_on_fix": sum(r["silent_on_fix"] for r in rows), "rows": rows}
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1)
    for r in rows:
        print(r["advisory"], r["repo"], "caught" if r["caught"] else "MISSED", "| fix silent" if r["silent_on_fix"] else "| FIX NAMED", [(h["path"], h["line"], h["kind"]) for h in r["vulnerable_diff"]["untrusted"]][:2])
    print(f"caught {out['caught']} of {out['cases']}; silent on the fix {out['silent_on_fix']} of {out['cases']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
