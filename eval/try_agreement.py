"""Does the browser version of three checks (web/try_checks.js) say exactly what the Python checks say?
The rules are in eval/try_agreement_rubric.json, written before the two were compared. Needs node. Read-only.

usage: python3 eval/try_agreement.py --repo work/mesa-replay/mesa.git --out results/try_agreement_v1.json"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
import agent_noise as AN  # noqa: E402
import incident_replay as IR  # noqa: E402
import mesa_noise as MN  # noqa: E402
from itemator import moving as MV  # noqa: E402
from itemator import shapes as SH  # noqa: E402
from itemator import untrusted as UT  # noqa: E402

MESA_COMMITS = 400
KEYWORDS = ("curl", "wget", "base64", "eval", "atob", "environ", "process.env", "${{", "CI_", "image:", "FROM", "ref:", "remote:", "component:",
            "writeFile", "fetch(", "download")
LINE_PATHS = (".github/workflows/x.yml", ".gitlab-ci.yml", "Dockerfile", "scripts/x.sh", "src/x.ts", "src/x.py", "scripts/x.bash", "docs/x.yml", "tests/test_x.sh")
REMOVED_PATHS = (".github/workflows/x.yml", "Dockerfile", "src/x.ts")      # also sent as a deleted file
MAX_LINES, GROUP = 6000, 6
CHECKS = (("moving", MV), ("shapes", SH), ("untrusted", UT))
FILE_KEYS = ("filename", "status", "patch", "binary")


def python_says(files: list[dict]) -> dict:
    return {name: mod.find(files) for name, mod in CHECKS}


def examples() -> list[dict]:
    """(C) the page's own example diffs, one file shared by the page and this script."""
    return [{"id": f"example-{e['id']}", "diff": e["diff"]} for e in json.load(open(ROOT / "web" / "try_examples.json"))]


def test_literals() -> list[str]:
    import ast  # noqa: PLC0415
    out = []
    for name in ("test_moving", "test_shapes", "test_untrusted"):
        for node in ast.walk(ast.parse((ROOT / "tests" / f"{name}.py").read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                out += [l for l in node.value.split("\n") if 6 <= len(l) <= 300]
    return out


def keyword_lines(patches: list[str]) -> list[str]:
    seen, out = set(), []
    for patch in patches:
        for line in patch.split("\n"):
            if line.startswith("+") and not line.startswith("+++") and 6 <= len(line) - 1 <= 300 and any(k in line for k in KEYWORDS) and line[1:] not in seen:
                seen.add(line[1:])
                out.append(line[1:])
                if len(out) >= MAX_LINES:
                    return out
    return out


def line_units(lines: list[str]) -> list[dict]:
    units = []
    for path in LINE_PATHS:
        for i in range(0, len(lines), GROUP):
            chunk = lines[i:i + GROUP]
            patch = f"@@ -0,0 +1,{len(chunk)} @@\n" + "".join("+" + l + "\n" for l in chunk)
            units.append({"id": f"{path}#{i}", "files": [{"filename": path, "status": "added", "patch": patch}]})
            if path in REMOVED_PATHS:
                units.append({"id": f"{path}#{i}:removed", "files": [{"filename": path, "status": "removed", "patch": patch}]})
    return units


def compare(units: list[dict], js: dict) -> dict:
    parse_bad, check_bad, spoke = [], [], {n: 0 for n, _ in CHECKS}
    for u in units:
        mine = js[u["id"]]
        files = IR.files_of(u["diff"]) if "diff" in u else u["files"]
        if "diff" in u and [{k: f[k] for k in FILE_KEYS} for f in files] != [{k: f[k] for k in FILE_KEYS} for f in mine["files"]]:
            parse_bad.append(u["id"][:12])
        py = python_says(files)
        for name, _ in CHECKS:
            spoke[name] += bool(py[name])
            if py[name] != mine[name]:
                check_bad.append({"unit": u["id"][:12], "check": name, "python": len(py[name]), "javascript": len(mine[name])})
    return {"units": len(units), "diff_reader_disagreements": parse_bad, "check_disagreements": check_bad, "python_spoke_on": spoke}


def run_js(units: list[dict]) -> dict:
    with tempfile.TemporaryDirectory() as d:
        src, dst = pathlib.Path(d, "units.json"), pathlib.Path(d, "out.json")
        src.write_text(json.dumps(units))
        subprocess.run(["node", str(ROOT / "web" / "try_agree.js"), str(src), str(dst)], check=True)
        return json.loads(dst.read_text())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="a trial of the script on this many units per corpus, not the registered run")
    a = ap.parse_args(argv)
    lim = lambda n: a.limit or n                              # noqa: E731
    out = {"rubric": "eval/try_agreement_rubric.json", "limit_trial": a.limit or None}
    grouped = AN.commits(json.load(open(AN.DATA)))
    agent = [{"id": sha, "files": g["files"]} for sha, g in sorted(grouped.items()) if any(f["patch"] for f in g["files"])][:lim(10 ** 9)]
    out["agent_commits"] = compare(agent, run_js(agent))
    pool = [f["patch"] for u in agent for f in u["files"]]
    del grouped, agent
    ids = MN.shuffled(MN.ordinary_ids(a.repo), lim(MESA_COMMITS))
    mesa = []
    for sha in ids:
        names = [n for n in MN.git(a.repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha).split("\n") if n]
        if len(names) <= MN.MAX_FILES:
            diff = MN.git(a.repo, "show", "--format=", "-U3", "--no-color", sha)
            mesa.append({"id": sha, "diff": diff})
            mesa.append({"id": sha + ":mail", "diff": diff + "-- \n2.43.0\n"})           # the trailer of a format-patch mail
    out["mesa_commits"] = compare(mesa, run_js(mesa))
    pool += [u["diff"] for u in mesa]
    lines = test_literals() + keyword_lines(pool)
    del pool
    lu = line_units(lines[:lim(10 ** 9)] if a.limit else lines)
    out["line_corpus"] = {**compare(lu, run_js(lu)), "lines": len(lines)}
    ex = examples()
    out["page_examples"] = compare(ex, run_js(ex))
    out["all_identical"] = all(not (out[k]["diff_reader_disagreements"] or out[k]["check_disagreements"]) for k in ("agent_commits", "mesa_commits", "line_corpus", "page_examples"))
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1)
    for k in ("agent_commits", "mesa_commits", "line_corpus", "page_examples"):
        print(k, out[k]["units"], "units;", len(out[k]["diff_reader_disagreements"]), "reader and", len(out[k]["check_disagreements"]), "check disagreements; python spoke", out[k]["python_spoke_on"])
    print("all identical:", out["all_identical"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
