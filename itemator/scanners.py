"""GitLab's own scanner results, set beside the change. Standard library only; no model.

The project's SAST and secret-detection jobs upload `gl-sast-report.json` and `gl-secret-detection-report.json`; the Itemator job
runs in a later stage of the same pipeline, so GitLab downloads them into the checkout (read on the job log of a merge request
pipeline). This joins them to the change: a finding on a line the change adds is "introduced by this change", and a finding in a
file the change touches but on another line is "in a touched file"; either is also marked when the extras list does not name
that file. The reports are the scanners' output, run by the project's own pipeline: this reads them, it does not scan, and a
merge request that edits the scanner job can change what they say. Missing, oversize or odd reports give nothing. Information only."""
from __future__ import annotations

import json
import os

from itemator import fence as FE
from itemator import shapes as SH

REPORTS = ("gl-sast-report.json", "gl-secret-detection-report.json")
MAX_BYTES = 5 * 2 ** 20
MAX_FINDINGS = 2000       # findings read per report
SHOWN = 3
_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "unknown": 5}


def read(repo_dir: str, warnings: list | None = None) -> list[dict]:
    """[{path, line, end, severity, name, scanner}] from the report files in the checkout; nothing for a file that is missing, too
    large, not JSON or not shaped like a report."""
    out = []
    for name in REPORTS:
        path = os.path.join(repo_dir, name)
        try:
            if not os.path.isfile(path):
                continue
            if os.path.getsize(path) > MAX_BYTES:
                if warnings is not None:
                    warnings.append(f"no scanner join on {name}: the report is larger than {MAX_BYTES // 2 ** 20} MB")
                continue
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            rows = data["vulnerabilities"]
        except (OSError, ValueError, KeyError, TypeError):
            if warnings is not None:
                warnings.append(f"no scanner join on {name}: the report could not be read")
            continue
        if not isinstance(rows, list):
            continue
        for v in rows[:MAX_FINDINGS]:
            try:
                loc = v["location"]
                line = int(loc.get("start_line") or 0)
                out.append({"path": str(loc["file"]), "line": line, "end": int(loc.get("end_line") or line), "severity": str(v.get("severity", "Unknown")).lower(),
                            "name": FE.tidy(str(v.get("name") or v.get("message") or "finding")),
                            "scanner": str((v.get("scanner") or {}).get("name") or v.get("category") or "scanner")})
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
    return out


def find(repo_dir: str, files: list[dict], listed: set | frozenset = frozenset(), warnings: list | None = None) -> dict | None:
    """{"introduced": [finding], "touched": [finding]} for findings in the files the change touches, most severe first, each with
    "named" (the extras list names the file); None when there are none."""
    findings = read(repo_dir, warnings)
    if not findings:
        return None
    changed = {f.get("filename"): f for f in files if f.get("status") != "removed"}
    new_lines = {p: {n for n, _ in SH.added(f.get("patch") or "")} for p, f in changed.items()}
    introduced, touched = [], []
    for d in findings:
        if d["path"] not in changed:
            continue
        d = {**d, "named": d["path"] in listed}
        (introduced if any(n in new_lines[d["path"]] for n in range(d["line"], max(d["line"], d["end"]) + 1)) else touched).append(d)
    if not (introduced or touched):
        return None
    key = lambda d: (_RANK.get(d["severity"], 5), d["path"], d["line"])          # noqa: E731
    return {"introduced": sorted(introduced, key=key), "touched": sorted(touched, key=key)}


def sentence(d: dict) -> str:
    def one(x):
        tail = "" if x["named"] else ", a file the extras list does not name"
        return f"{x['severity']} `{x['path']}` line {x['line']} ({x['name']}; {x['scanner']}{tail})"
    parts = []
    for label, rows in (("on lines this change adds", d["introduced"]), ("in files this change touches", d["touched"])):
        if rows:
            more = f" and {len(rows) - SHOWN} more" if len(rows) > SHOWN else ""
            parts.append(f"{len(rows)} {label}: " + "; ".join(one(x) for x in rows[:SHOWN]) + more)
    return "GitLab's scanners in this pipeline report " + "; and ".join(parts) + "."
