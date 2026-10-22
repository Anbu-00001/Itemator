"""Build the page where a visitor pastes a diff and three checks run in the browser: `python -m itemator.tryit --out public/try`.

web/try.html is the page, web/try_checks.js holds the checks (the same rules as moving.py, shapes.py and untrusted.py; eval/try_agreement.py
compares the two) and web/try_examples.json the example diffs. The numbers beside each check are read from the results files at build
time, so the page cannot say more than the files do. The page forbids itself every network request with a Content-Security-Policy.
Standard library only."""
from __future__ import annotations

import argparse
import hashlib
import html as H
import json
import pathlib
import re

from itemator import diffreader as DR
from itemator import extras as X
from itemator import moving as MV
from itemator import shapes as SH
from itemator import untrusted as UT

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
RESULTS = ROOT / "results"
REPO = "https://gitlab.com/gitlab-ai-hackathon/transcend-october-2026/39194174/showcase/-/blob/main/"


def safe_json(data) -> str:
    """JSON for inside a <script> tag: no sequence in the data can close the tag or open a comment."""
    return json.dumps(data, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def _ratio(row: dict) -> str:
    if row.get("readable", row["read"]) == row["read"]:
        return f"{row['spoke']} of {row['read']}"
    return f"{row['spoke']} of {row['read']} ({row['readable']} changed a file it reads)"


def evidence(mesa: dict, agents: dict, incidents: dict, agreement: dict) -> dict:
    """The table beside the checks, from the results files only."""
    by_check: dict[str, list[dict]] = {}
    for i in incidents["incidents"]:
        by_check.setdefault(i["expected_check"], []).append(i)
    reads = {"moving": "Added lines of CI files and Dockerfiles", "shapes": "Added lines of any file but tests, docs and lock files",
             "untrusted": "Added lines of CI files and shell scripts"}
    rows = []
    for c in ("shapes", "untrusted", "moving"):
        inc = by_check.get(c, [])
        rows.append({"check": c, "reads": reads[c], "ordinary": _ratio(mesa["ordinary"]["checks"][c]), "agents": _ratio(agents["checks"][c]),
                     "incidents": f"{sum(1 for i in inc if i['fired'])} of {len(inc)}" if inc else "none in the set"})
    units = sum(agreement[k]["units"] for k in ("agent_commits", "mesa_commits", "line_corpus", "page_examples"))
    notes = [
        {"text": f"Ordinary commits: {mesa['ordinary']['checks']['moving']['read']} commits of the Mesa project, 2024 to 2026, drawn at random. Agent-written commits: commits of AI agents' pull requests in the public AIDev data set, read from the pull requests that had human review comments, so riskier than average."},
        {"text": "Public incident diffs: the Amazon Q extension, the Nx workflow and the xz backdoor were read before the rules were written, so this column shows that the rules can see them, not that they will find the next one."},
        {"text": "Mesa and agent-commit results", "href": REPO + "results/mesa_noise_v1.json"},
        {"text": "Agent-written commits", "href": REPO + "results/agent_noise_v1.json"},
        {"text": "Incident diffs", "href": REPO + "results/incident_replay_v1.json"},
        {"text": f"This page's checks agree with the Python on all {units} units tried", "href": REPO + "results/try_agreement_v2.json"},
    ]
    return {"rows": rows, "notes": notes, "units": units}


def what(checks_js: str) -> dict:
    """The plain words for each finding, read from the page's own WHAT table so the two cannot drift apart."""
    m = re.search(r"var WHAT = \{(.*?)\};", checks_js, re.S)
    return dict(re.findall(r'"([a-z-]+)": "([^"]*)"', m.group(1))) if m else {}


def static(examples: list[dict], words: dict) -> str:
    """The examples' results as plain HTML, worked out here by the Python checks (the reference the page's JavaScript is
    compared with), for a reader without scripts. The page removes this block when its script runs."""
    e = H.escape
    out = ["<h2>The examples, as the checks read them</h2>",
           "<p class=\"muted\">Worked out by the Python version of the checks when this page was built. With scripts on, "
           "the buttons above run them again in this tab.</p>"]
    for ex in examples:
        files = DR.files_of(ex["diff"])
        found = [d for mod in (SH, UT, MV) for d in mod.find(files)]
        extras = X._new_dependencies(ex.get("issue") or "", files)
        out.append(f"<h3>{e(ex['title'])}</h3><p class=\"muted\">{e(ex['note'])}</p>")
        if ex.get("issue"):
            out.append(f"<p class=\"muted\">Issue: {e(ex['issue'].splitlines()[0])}</p>")
        if not found and not extras:
            out.append("<p>Nothing named.</p>")
            continue
        out.append("<ul>" + "".join(f"<li><code>{e(x.path)}</code>: an extra, {e(x.why)}</li>" for x in extras) + "".join(
            f"<li><code>{e(d['path'])}</code>{', line ' + str(d['line']) if d.get('line') else ''}: {e(words.get(d['kind'], d['kind']))}"
            f"<pre>{e(d['text'])}</pre></li>" for d in found) + "</ul>")
    return "\n".join(out)


def table(ev: dict) -> tuple[str, str]:
    """The evidence rows and notes as HTML, so the table reads the same without scripts."""
    e = H.escape
    rows = "".join("<tr><td>" + e(r["check"]) + "</td><td>" + e(r["reads"]) + "</td>"
                   + "".join(f'<td class="n">{e(r[k])}</td>' for k in ("ordinary", "agents", "incidents")) + "</tr>" for r in ev["rows"])
    texts = "".join(e(n["text"]) + "<br>" for n in ev["notes"] if not n.get("href"))
    links = " \u00b7 ".join(f'<a href="{e(n["href"])}" rel="noopener">{e(n["text"])}</a>' for n in ev["notes"] if n.get("href"))
    return rows, texts + f"<span>{links}</span>"


def page() -> str:
    mesa, agents = _load("mesa_noise_v1.json"), _load("agent_noise_v1.json")
    incidents, agreement = _load("incident_replay_v1.json"), _load("try_agreement_v2.json")
    deps_agree = _load("green_agreement_v2.json")
    if not (agreement["all_identical"] and deps_agree["all_identical"]):
        raise SystemExit("itemator.tryit: the browser checks and the Python checks disagree (results/try_agreement_v2.json or results/green_agreement_v2.json); not building")
    checks = (WEB / "try_checks.js").read_text(encoding="utf-8")
    ev = evidence(mesa, agents, incidents, agreement)
    payload = {"examples": json.loads((WEB / "try_examples.json").read_text(encoding="utf-8")), "evidence": ev,
               "footer": f"Checks version {hashlib.sha256(checks.encode()).hexdigest()[:12]} (web/try_checks.js). Standard HTML and JavaScript; no library, no network, no model."}
    rows, notes = table(ev)
    html = (WEB / "try.html").read_text(encoding="utf-8")
    for marker, text in (("/*ROWS*/", rows), ("/*EVNOTE*/", notes), ("/*PAYLOAD*/", safe_json(payload)), ("/*CHECKS*/", checks.replace("</script", "<\\/script")),
                         ("/*STATIC*/", static(payload["examples"], what(checks))),
                         ("/*DEPS*/", (WEB / "deps_rule.js").read_text(encoding="utf-8").replace("</script", "<\\/script"))):
        assert html.count(marker) == 1
        html = html.replace(marker, text, 1)
    return html


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="itemator.tryit", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--out", default="public/try")
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page(), encoding="utf-8")
    print(f"wrote {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
