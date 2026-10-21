"""The CI job's record (itemator.json) in two of GitLab's own report formats, so the extras also show where GitLab shows findings:
`python -m itemator.glreports itemator.json --codequality gl-code-quality-report.json --metrics metrics.txt`.

- Code Quality (artifacts:reports:codequality): one finding per extra, on the line its thread is on, so the merge request's widget
  lists the extras and the Changes tab marks their lines. Severity "info": an extra is a question for a person, not a defect.
- Metrics (artifacts:reports:metrics): how many extras, and what the weighed new dependencies the issue did not ask for bring along
  (packages, MB, and the SCI bracket of itemator/sci.py), so the widget shows the change against the target branch.

Read from the record only; nothing is checked again and nothing is posted. Standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

from itemator import sci as SCI

ASK = "Reply in its thread: its exact name to keep it, `remove` to drop it."


def _weights(extra: dict) -> list[dict]:
    reg = (extra.get("plain_facts") or {}).get("registry") or {}
    return [p["weight"] for p in reg.get("packages") or () if (p.get("weight") or {}).get("weight") == "ok"]


def codequality(record: dict) -> list[dict]:
    out = []
    for e in record.get("extras") or ():
        anchor = e.get("anchor") or {}
        path = anchor.get("new_path") or anchor.get("old_path") or e["path"]
        line = anchor.get("new_line") or anchor.get("old_line") or 1
        key = f"{e['kind']}\0{e['path']}\0{e['name']}"
        out.append({"description": f"Extra beyond the issue: {e['name']} ({e['why']}). {ASK}",
                    "check_name": f"itemator/{e['kind']}", "categories": ["Clarity"],
                    "fingerprint": hashlib.sha256(key.encode()).hexdigest(), "severity": "info",
                    "location": {"path": path, "lines": {"begin": int(line)}}})
    return out


def metrics(record: dict) -> str:
    extras = record.get("extras") or []
    deps = [e for e in extras if e["kind"] == "new_dependency"]
    weighed = [w for e in deps for w in _weights(e)]
    lines = [f"itemator_extras {len(extras)}", f"itemator_new_dependencies {len(deps)}",
             f"itemator_unasked_dependencies_weighed {len(weighed)}"]
    if weighed:
        g = [SCI.per_install(w["bytes"] / 1e6, SCI.SECONDS) for w in weighed]
        lines += [f"itemator_unasked_dependency_packages {sum(w['packages'] for w in weighed)}",
                  f"itemator_unasked_dependency_download_mb {round(sum(w['bytes'] for w in weighed) / 1e6, 1)}",
                  f"itemator_unasked_dependency_co2e_g_per_install_low {sum(x['low']['sci_g_per_install'] for x in g):.2g}",
                  f"itemator_unasked_dependency_co2e_g_per_install_high {sum(x['high']['sci_g_per_install'] for x in g):.2g}"]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="itemator.glreports", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("record")
    ap.add_argument("--codequality", default="gl-code-quality-report.json")
    ap.add_argument("--metrics", default="metrics.txt")
    a = ap.parse_args(argv)
    record = json.loads(pathlib.Path(a.record).read_text(encoding="utf-8"))
    pathlib.Path(a.codequality).write_text(json.dumps(codequality(record), indent=1) + "\n", encoding="utf-8")
    pathlib.Path(a.metrics).write_text(metrics(record), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
