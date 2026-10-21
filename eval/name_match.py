"""How often does an issue's wording stop the new-dependency rule, and how did the issue name the package?

An outside review found that an issue merely containing the word "requests" or "pandas" in another sense keeps the rule
from listing those packages. This counts how often that can happen on real data: the 300 held-out agent pull requests of
samples B to F (results/replay_v*_sample*.json), files from the replay cache, issue text from AIDev as eval/replay_aidev.py
reads it. For each pull request the rule runs twice, with an empty issue and with the real one; a dependency listed only
with the empty issue was silenced by the issue's words. Each silencing is sorted by how the issue names the package:
in code formatting, next to a package word (install, package, library, dependency, import, ...) or with a version, or
as a bare word. Read-only, offline. usage: .venv/bin/python -I eval/name_match.py   (writes results/name_match_v1.json)"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
from itemator import extras as X  # noqa: E402

OUT = ROOT / "results" / "name_match_v1.json"
SAMPLES = ("replay_v2_sampleB", "replay_v3_sampleC", "replay_v4_sampleD", "replay_v5_sampleE", "replay_v6_sampleF")
PACKAGE_WORDS = r"(?:install(?:ed|ing|s)?|package|packages|library|libraries|lib|dependency|dependencies|dep|deps|module|crate|gem|import|pip|npm|yarn|pnpm|cargo|poetry|uv|requirements(?:\.txt)?|pyproject(?:\.toml)?|package\.json)"
WINDOW = 3


def how_named(issue: str, name: str) -> str:
    """'code' (in backticks or a fenced block), 'package_context' (a package word or a version within WINDOW words), or 'bare'."""
    low, n = issue.lower(), re.escape(name.lower())
    word = rf"(?<![a-z0-9]){n}(?![a-z0-9])"
    fences = " ".join(re.findall(r"```.*?```", low, re.S))
    if re.search(word, fences) or re.search(rf"`[^`\n]*{word}[^`\n]*`", low):
        return "code"
    for m in re.finditer(word, low):
        before = re.findall(r"[\w.\-]+", low[max(0, m.start() - 80):m.start()])[-WINDOW:]
        after_text = low[m.end():m.end() + 80]
        after = re.findall(r"[\w.\-]+", after_text)[:WINDOW]
        if any(re.fullmatch(PACKAGE_WORDS, w) for w in before + after) or re.match(r"\s*(?:==|>=|<=|~=|\^|@|\s+v?\d)", after_text):
            return "package_context"
    return "bare"


def silenced(issue: str, files: list[dict]) -> list[str]:
    """Dependency names the rule lists with an empty issue but not with this one."""
    alone = {e.name for e in X._new_dependencies("", files)}
    return sorted(alone - {e.name for e in X._new_dependencies(issue, files)})


def main() -> int:
    import replay_aidev as R
    urls = {p["pr_url"] for s in SAMPLES for p in json.loads((ROOT / "results" / f"{s}.json").read_text())["prs"]}
    pool = {p["pr_url"]: p for p in R.build_pool()[0] if p["pr_url"] in urls}
    rows, missing = [], []
    for url in sorted(urls):
        p = pool.get(url)
        cached = R.CACHE / f"{p['pr_id']}.json" if p else None
        if not p or not cached.exists():
            missing.append(url)
            continue
        files = json.loads(cached.read_text())["files"]
        for name in silenced(p["issue_text"], files):
            rows.append({"pr_url": url, "name": name, "named": how_named(p["issue_text"], name)})
    count = {k: sum(r["named"] == k for r in rows) for k in ("code", "package_context", "bare")}
    res = {"what": __doc__.split("\n")[0], "samples": list(SAMPLES), "pull_requests": len(urls) - len(missing),
           "not_readable": len(missing), "silenced": len(rows), "by_how_named": count,
           "prs_with_a_bare_silencing": len({r["pr_url"] for r in rows if r["named"] == "bare"}), "rows": rows}
    OUT.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
