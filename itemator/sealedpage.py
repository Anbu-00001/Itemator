"""Build the sealed forward test page: `python -m itemator.sealedpage --out public/sealed`.

results/prospective_v1_sealed.json (written by eval/prospective.py under eval/prospective_rubric.json) as a page: the open agent pull
requests, what the frozen rules listed in each, the SHA-256 of that list and the predictions committed before the sample was drawn.
Once the read date's results/prospective_v1_read.json exists and names the same sealed SHA-256, the page also shows what happened, the
misses first: listed files that merged with nobody objecting. Every string from the files is escaped, and only links to GitHub are
kept. Standard library only."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import html
import json
import pathlib

from itemator.tryit import REPO

ROOT = pathlib.Path(__file__).resolve().parent.parent
SEALED = ROOT / "results" / "prospective_v1_sealed.json"
RUBRIC = ROOT / "eval" / "prospective_rubric.json"
READ = ROOT / "results" / "prospective_v1_read.json"
SHOWN = 5                  # listed files shown per pull request; the rest are counted


def _gh(url) -> str | None:
    return url if isinstance(url, str) and url.startswith("https://github.com/") else None


def row(pr: dict) -> str:
    e = html.escape
    url = _gh(pr.get("url"))
    label = e(str(url or "?").removeprefix("https://github.com/"))
    head = f'<a href="{e(url)}">{label}</a>' if url else label
    extras = [x for x in pr.get("extras") or [] if isinstance(x, dict)]
    items = "".join(f"<li><code>{e(str(x.get('path') or x.get('name') or ''))}</code> <span class=\"m\">{e(str(x.get('kind', '')))}</span></li>"
                    for x in extras[:SHOWN])
    more = f"<li class=\"m\">and {len(extras) - SHOWN} more</li>" if len(extras) > SHOWN else ""
    return (f"<article><p class=\"pr\">{head} <span class=\"m\">· {e(str(pr.get('agent', '')))} · opened "
            f"{e(str(pr.get('created_at', ''))[:10])} · {len(pr.get('files') or [])} files changed</span></p><ul>{items}{more}</ul></article>")


def _days_before(read: dict) -> str:
    try:
        d = (date.fromisoformat(read["read_on"]) - date.fromisoformat(read["sentences_frozen_on"])).days
    except (KeyError, TypeError, ValueError):
        return ""
    return f", {d} day{'s' if d != 1 else ''} before the read"


def _share(c: dict) -> str:
    n, k = c.get("files") or 0, c.get("objected_or_removed") or 0
    return f"{k} of {n} ({round(100 * k / n)}%)" if n else "none"


def outcome(read: dict, sealed: dict) -> list:
    """The outcome section, misses first; empty before the read, or when the read is of a different sealed list."""
    e = html.escape
    if not read:
        return []
    if read.get("sealed_cases_sha256") != (sealed.get("summary") or {}).get("cases_sha256"):
        return ["<h2>What happened</h2><p>The read on file is of a different sealed list, so it is not shown.</p>"]
    s = read.get("summary") or {}
    listed, unlisted = s.get("listed") or {}, s.get("unlisted") or {}
    rows = [r for r in read.get("files") or [] if isinstance(r, dict)]
    misses = [r for r in rows if r.get("listed") and r.get("silent_landing")]
    said = (f"<p><strong>{e(str(read['sentence']))}</strong> <span class=\"m\">(sentence chosen by the rule "
            f"<a href=\"{REPO}eval/prospective_sentences.json\">eval/prospective_sentences.json</a>, sealed on "
            f"{e(str(read.get('sentences_frozen_on', '?')))}{_days_before(read)}; nobody wrote it after)</span></p>"
            if read.get("sentence") else "")
    out = [f"<h2>What happened, read on {e(str(read.get('read_on', '?')))}</h2>", said,
           f"<p>Of the {e(str(s.get('readable', '?')))} pull requests we could read, {e(str(s.get('merged', '?')))} merged, "
           f"{e(str(s.get('closed_unmerged', '?')))} closed without merging and {e(str(s.get('open', '?')))} are still open. "
           f"A reviewer objected to, or the author removed, {_share(listed)} of the files the rules listed, against {_share(unlisted)} "
           "of the files they did not list.</p>",
           f"<h3>Misses first: listed files that merged and nobody objected ({len(misses)})</h3>"]
    if misses:
        out.append("<ul>" + "".join(f"<li><code>{e(str(r.get('path', '')))}</code> <span class=\"m\">in "
                                    + (f'<a href="{e(_gh(r.get("pr")))}">{e(str(r.get("pr")).removeprefix("https://github.com/"))}</a>'
                                       if _gh(r.get("pr")) else "?") + "</span></li>" for r in misses) + "</ul>")
    else:
        out.append("<p>None.</p>")
    hits = [r for r in rows if r.get("listed") and (r.get("objected") or r.get("state") == "removed")]
    out.append(f"<h3>Listed files a reviewer objected to or the author removed ({len(hits)})</h3>")
    out.append("<ul>" + "".join(f"<li><code>{e(str(r.get('path', '')))}</code> <span class=\"m\">"
                                + ("objected" if r.get("objected") else "") + (" · " if r.get("objected") and r.get("state") == "removed" else "")
                                + ("removed" if r.get("state") == "removed" else "") + "</span></li>" for r in hits) + "</ul>" if hits else "<p>None.</p>")
    out.append(f"<p class=\"m\">From <a href=\"{REPO}results/prospective_v1_read.json\">results/prospective_v1_read.json</a>, read by "
               "<code>eval/prospective.py read</code> under the rules committed before the sample.</p>")
    return out


def page(sealed: dict, file_sha: str, predictions: dict, read: dict | None = None) -> str:
    e = html.escape
    s = sealed.get("summary") or {}
    prs = [p for p in sealed.get("pull_requests") or [] if isinstance(p, dict)]
    out = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
           "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">",
           "<title>Sealed forward test</title><style>body{font:16px/1.5 system-ui,sans-serif;max-width:56rem;margin:2rem auto;padding:0 1rem}"
           "article{border:1px solid #ddd;border-radius:8px;padding:.5rem .8rem;margin:.6rem 0}.pr{font-weight:600;margin:.2rem 0}"
           ".m{color:#555;font-weight:400}code{overflow-wrap:anywhere}ul{margin:.2rem 0}</style></head><body>",
           "<h1>Sealed forward test: what the rules listed before anyone answered</h1>",
           f"<p>{len(prs)} agent pull requests still open on GitHub when we searched ({e(str(sealed.get('searched_at', ''))[:16].replace('T', ' '))} UTC). "
           f"The frozen rules listed {e(str(s.get('listed_files', '?')))} of their {e(str(s.get('files', '?')))} changed files. This list was committed "
           f"before any outcome existed; we read what happened on {e(str(s.get('read_on') or sealed.get('read_on') or '?'))}: which listed files a "
           "reviewer objected to or the author removed, and which merged with no word.</p>",
           f"<p class=\"m\">SHA-256 of the sealed file: <code>{e(file_sha)}</code>. Check it: download "
           f"<a href=\"{REPO}results/prospective_v1_sealed.json\">results/prospective_v1_sealed.json</a> and run <code>sha256sum</code> on it.</p>"]
    out += outcome(read or {}, sealed)
    if predictions:
        out.append("<h2>What we predicted, before drawing the sample</h2><ul>" + "".join(
            f"<li>{e(str(k))}: {e(str(v))}</li>" for k, v in predictions.items()) + "</ul>"
            f"<p class=\"m\">From <a href=\"{REPO}eval/prospective_rubric.json\">eval/prospective_rubric.json</a>, committed before the search.</p>")
    out.append("<h2>The pull requests and what the rules listed</h2>")
    out += [row(p) for p in prs]
    out.append("<p class=\"m\"><a href=\"../\">What shipped</a> · <a href=\"../catches/\">past real catches</a></p></body></html>")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="itemator.sealedpage", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--out", default="public/sealed")
    a = ap.parse_args(argv)
    raw = SEALED.read_bytes()
    rubric = json.loads(RUBRIC.read_text()) if RUBRIC.is_file() else {}
    read = json.loads(READ.read_text()) if READ.is_file() else None
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page(json.loads(raw), hashlib.sha256(raw).hexdigest(), rubric.get("predictions_before_sampling") or {}, read),
                                    encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
