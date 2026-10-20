"""Build the real-catches page: `python -m itemator.catchespage --out public/catches`.

results/real_catches.md (written by eval/real_catches.py and eval/real_catches_page.py under eval/real_catches_rubric.json) as one
card per case: what an AI agent added that its task did not ask for, what a real reviewer said about it, and what Itemator's frozen
rules say about the same file. The page reads only that committed file, so it cannot say more than the study does; every string
from it is escaped, and only links to GitHub or to this repository are kept. Standard library only."""
from __future__ import annotations

import argparse
import html
import pathlib
import re

from itemator.tryit import REPO

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "results" / "real_catches.md"
_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
_CODE = re.compile(r"`([^`]+)`")
_COLUMNS = ("pr", "agent", "file", "rule", "words", "reading")


def _href(url: str) -> str | None:
    if url.startswith("https://github.com/"):
        return url
    if url.startswith("../"):
        return REPO + url[3:]
    return None


def inline(text: str) -> str:
    """Markdown links and code spans to HTML; everything else escaped. A link to anywhere else keeps only its text."""
    out, at = [], 0
    for m in _LINK.finditer(text):
        out.append(_codes(text[at:m.start()]))
        href = _href(m.group(2))
        label = _codes(m.group(1))
        out.append(f'<a href="{html.escape(href)}">{label}</a>' if href else label)
        at = m.end()
    out.append(_codes(text[at:]))
    return "".join(out)


def _codes(text: str) -> str:
    parts = _CODE.split(text)
    return "".join(f"<code>{html.escape(p)}</code>" if i % 2 else html.escape(p) for i, p in enumerate(parts))


def parse(md: str) -> dict:
    """{title, intro: [paragraph], sections: [{heading, rows: [{pr, agent, file, rule, words, reading}]}]} from the study's page."""
    title, intro, sections = "", [], []
    for block in re.split(r"\n\s*\n", md.strip()):
        lines = block.strip().splitlines()
        if lines[0].startswith("# "):
            title = lines[0][2:].strip()
        elif lines[0].startswith("## "):
            sections.append({"heading": lines[0][3:].strip(), "rows": []})
        elif lines[0].startswith("|") and sections:
            for line in lines[2:]:
                cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
                if len(cells) == len(_COLUMNS):
                    sections[-1]["rows"].append(dict(zip(_COLUMNS, cells)))
        elif not sections:
            intro.append(" ".join(lines))
    return {"title": title, "intro": intro, "sections": sections}


def card(r: dict) -> str:
    return ("<article><p class=\"pr\">" + inline(r["pr"]) + f" <span class=\"muted\">· {html.escape(r['agent'])}</span></p>"
            f"<p><span class=\"k\">File</span> {inline(r['file'])}</p>"
            f"<p><span class=\"k\">Reviewer</span> {inline(r['words'])} <span class=\"muted\">({html.escape(r['reading'])})</span></p>"
            f"<p><span class=\"k\">Itemator</span> {inline(r['rule'])}</p></article>")


def page(study: dict) -> str:
    out = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
           "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">",
           "<title>Real catches</title><style>"
           ":root{--bg:#fbfbfa;--fg:#1c1c1a;--muted:#5d5d58;--line:#d9d8d2;--card:#fff;--code:#f1f0ec;--accent:#4b3fa8}"
           "@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){--bg:#151514;--fg:#ecebe6;--muted:#a6a59d;--line:#3a3a36;--card:#1d1d1b;--code:#262622;--accent:#b7aef5}}"
           ":root[data-theme=\"dark\"]{--bg:#151514;--fg:#ecebe6;--muted:#a6a59d;--line:#3a3a36;--card:#1d1d1b;--code:#262622;--accent:#b7aef5}"
           "*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif}"
           "main{max-width:880px;margin:0 auto;padding:28px 16px 72px}h1{font-size:1.6rem;line-height:1.25;margin:0 0 8px}"
           "h2{font-size:1.05rem;margin:32px 0 8px}a{color:var(--accent);overflow-wrap:anywhere}"
           "code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:.9em;overflow-wrap:anywhere}"
           "article{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}"
           "article p{margin:.25em 0}.pr{font-weight:600}.k{display:inline-block;min-width:5.5em;color:var(--muted);font-size:.88rem}"
           ".muted{color:var(--muted)}</style></head><body><main>",
           "<h1>Real catches: a reviewer objected to a file an AI agent changed, and Itemator's rules named the same file</h1>"]
    out += [f"<p>{inline(p)}</p>" for p in study["intro"]]
    for s in study["sections"]:
        out.append(f"<h2>{html.escape(s['heading'])}</h2>")
        out += [card(r) for r in s["rows"]]
    out.append(f"<p class=\"muted\">Source: <a href=\"{REPO}results/real_catches.md\">results/real_catches.md</a>, which this page is built "
               "from. Try the rules on a change of your own: <a href=\"../try/\">paste a diff</a> or <a href=\"../green/\">paste a link</a>.</p>"
               "</main></body></html>")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="itemator.catchespage", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--out", default="public/catches")
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page(parse(SOURCE.read_text(encoding="utf-8"))), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
