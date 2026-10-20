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


def fetch_pr(repo: str, number: int) -> list[dict]:
    """The files of a pull request, page by page (100 a page, at most 30 pages), in the same shape as fetch()."""
    files: list[dict] = []
    for page in range(1, 31):
        got = subprocess.run(["gh", "api", f"repos/{repo}/pulls/{number}/files?per_page=100&page={page}"], capture_output=True, text=True, check=True)
        rows = json.loads(got.stdout)
        files += [{"filename": f["filename"], "status": f.get("status", "modified"), "patch": f.get("patch", "")} for f in rows]
        if len(rows) < 100:
            break
    return files


def added_lines(files: list[dict]) -> int:
    return sum(1 for f in files for line in (f.get("patch") or "").split("\n") if line.startswith("+") and not line.startswith("+++"))


def says(files: list[dict]) -> dict:
    return {"untrusted": UT.find(files), "shapes": SH.find(files), "moving": MV.find(files)}


def summarise(case: dict, files: list[dict]) -> dict:
    back, fixed = says(turned_round(files)), says(files)
    cut = lambda rows: [{k: v for k, v in r.items() if k != "text"} for r in rows]       # noqa: E731 -- no diff text is published
    return {"advisory": case["advisory"], "repo": case["repo"], "fix": case["fix"][:12] if "fix" in case else f"pull request {case['pr']}", "files": [f["filename"] for f in files],
            "vulnerable_diff": {k: cut(v) for k, v in back.items()}, "fix_as_committed": {k: cut(v) for k, v in fixed.items()},
            "caught": bool(back["untrusted"]), "silent_on_fix": not fixed["untrusted"],
            **({"pattern": case["pattern"], "kind": case["kind"], "fix_added_lines": added_lines(files)} if "pattern" in case else {})}


def by(rows: list[dict], key: str) -> dict:
    out: dict = {}
    for r in rows:
        o = out.setdefault(r[key], {"cases": 0, "caught": 0})
        o["cases"] += 1
        o["caught"] += r["caught"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--rubric", default=str(RUBRIC), help="the rubric file; the cases may name a fix commit or a pull request (pr)")
    a = ap.parse_args(argv)
    rubric = pathlib.Path(a.rubric).resolve()
    cases = json.loads(rubric.read_text())["cases"]
    rows = [summarise(c, fetch_pr(c["repo"], c["pr"]) if "pr" in c else fetch(c["repo"], c["fix"])) for c in cases]
    out = {"rubric": str(rubric.relative_to(ROOT)), "cases": len(rows), "caught": sum(r["caught"] for r in rows), "silent_on_fix": sum(r["silent_on_fix"] for r in rows), "rows": rows}
    if rows and "pattern" in rows[0]:
        out["silent_on_fix_with_added_lines"] = {"cases": sum(r["fix_added_lines"] > 0 for r in rows), "silent": sum(r["silent_on_fix"] for r in rows if r["fix_added_lines"] > 0)}
        out["by_pattern"], out["by_kind"] = by(rows, "pattern"), by(rows, "kind")
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1)
    for r in rows:
        print(r["advisory"], r["repo"], "caught" if r["caught"] else "MISSED", "| fix silent" if r["silent_on_fix"] else "| FIX NAMED", [(h["path"], h["line"], h["kind"]) for h in r["vulnerable_diff"]["untrusted"]][:2])
    for k in ("silent_on_fix_with_added_lines", "by_pattern", "by_kind"):
        if k in out:
            print(k, json.dumps(out[k]))
    print(f"caught {out['caught']} of {out['cases']}; silent on the fix {out['silent_on_fix']} of {out['cases']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
