"""results/real_catches.md: the 24 files of results/real_catches_v1.json as a page a stranger can check, one row each, with the
reviewer's own words and a link to the comment. Read-only: GET requests through `gh api -X GET`; nothing is posted.

The cases, the outcomes and their counts are the registered study's (eval/real_catches_rubric.json); this adds only the text
of the comment each case was chosen by, cut to QUOTE characters, and no user names. Comments are read once and cached under
eval/cache/ (gitignored).

usage (repository root):  python3 eval/real_catches_page.py"""
from __future__ import annotations

import json, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import real_catches as RC  # noqa: E402

STUDY = ROOT / "results" / "real_catches_v1.json"
LABELS = ROOT / "eval" / "real_catches_labels.json"
CACHE = ROOT / "eval" / "cache" / "real_catches_comments.json"
REASONS = ROOT / "eval" / "cache" / "real_catches_reasons.json"
OUT = ROOT / "results" / "real_catches.md"
QUOTE = 180            # characters of a comment shown

ORDER = ("file_removed", "closed_unmerged", "landed_with_the_file")
HEADING = {"file_removed": "Taken out of the pull request", "closed_unmerged": "Pull request closed without merging",
           "landed_with_the_file": "Merged (or still open) with the file in it"}
KIND = {"dependency": "a new dependency", "ci_or_config": "a CI or config file", "binary": "a binary file",
        "generated": "a generated file", None: "listed by the rules"}
READING = {"yes": "asks to take it out", "no": "does not ask to take it out", "unclear": "unclear"}


def quote(body: str) -> str:
    """One line, quoted text and code blocks dropped, cut at a word, and safe inside a table cell."""
    lines = [l for l in body.splitlines() if not l.lstrip().startswith(">")]
    text = re.sub(r"```.*?```", " ", "\n".join(lines), flags=re.S)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > QUOTE:
        text = text[:QUOTE].rsplit(" ", 1)[0] + " ..."
    return text.replace("|", "\\|").replace("`", "'")


def reason(why: str | None) -> str | None:
    """The rule's reason without the file list a whole-change reason ends with."""
    return why.split(": ", 1)[0].replace("|", "\\|") if why else None


def short(pr_url: str) -> str:
    owner, repo, n = RC.pr_parts(pr_url)
    return f"{owner}/{repo}#{n}"


def render(study: dict, comments: dict, labels: dict, reasons: dict | None = None) -> str:
    """`comments`: {pair key: {"body", "html_url"}} for the earliest comment of each pair; `labels`: {pair key: yes|no|unclear};
    `reasons`: {pair key: the rules' own words for the extra that lists the file}, from the same replay as leg 1."""
    reasons = reasons or {}
    s = study["summary"]
    out = ["# Real cases: a reviewer objected, and the rules listed the file", "",
           "Each row is a file in a public agent pull request (the AIDev dataset) where a human reviewer wrote an inline comment "
           "calling it unrelated, out of scope, unnecessary or for a separate pull request, and where Itemator's frozen rules (v6) "
           "also list that file as an extra. Comments were picked by keyword, not by reading them; outcomes were read once, "
           f"on {study.get('read_on', 'the date in the results file')}, under a plan written before the run "
           "([eval/real_catches_rubric.json](../eval/real_catches_rubric.json)).", "",
           f"Of {s['read']} files, {s['file_removed']} were taken out, {s['closed_unmerged']} sat in pull requests closed without "
           f"merging, and {s['landed_with_the_file']} landed with the file. This is not a catch rate: it says nothing about the "
           "files reviewers objected to that the rules do not list (most of them, see results/aidev_recall_v6.json), and the "
           "reviewers saw no card. \"Reading\" is one model's reading of the comment, not a person's.", ""]
    by = {o: [c for c in study["cases"] if c.get("outcome") == o] for o in ORDER}
    for o in ORDER:
        out += [f"## {HEADING[o]} ({len(by[o])})", "", "| Pull request | Agent | File | What the rules say | Reviewer's words | Reading |", "|---|---|---|---|---|---|"]
        for c in sorted(by[o], key=lambda c: c["key"]):
            cm = comments.get(c["key"]) or {}
            words = f"[\"{quote(cm['body'])}\"]({cm['html_url']})" if cm.get("body") else "(comment not readable)"
            out.append(f"| [{short(c['pr'])}]({c['pr']}) | {c['agent'].replace('_', ' ')} | `{c['path'].rsplit('/', 1)[-1]}` | "
                       f"{reason(reasons.get(c['key'])) or KIND.get(c['kind'], KIND[None])} | {words} | {READING.get(labels.get(c['key']), 'not read')} |")
        out.append("")
    unread = [c for c in study["cases"] if c.get("outcome") not in ORDER]
    if unread:
        out += [f"{len(unread)} more could not be read.", ""]
    return "\n".join(out)


def rule_reasons(study: dict) -> dict:
    """The rules (v6) re-run on leg 1's cached files for each case: the reason of the extra that lists the file. Needs
    eval/cache/aidev/ (written by eval/aidev_recall.py); {} without it."""
    if REASONS.exists():
        return json.loads(REASONS.read_text())
    import collections
    import aidev_recall as A
    from itemator import extras as X
    if not (A.CACHE / "commit_details.json").exists():
        return {}
    keys = {c["key"] for c in study["cases"]}
    cases = [c for c in json.loads(A.CASES.read_text())["comments"] if f"{A.html_url(c['pull_request_url'])}#{c['path']}" in keys]
    prs = {r["html_url"]: r for r in json.loads((A.CACHE / "pull_request.json").read_text())}
    want = {prs[A.html_url(c["pull_request_url"])]["id"] for c in cases}
    commits = collections.defaultdict(list)
    for r in json.loads((A.CACHE / "commit_details.json").read_text()):
        if r["pr_id"] in want:
            commits[r["pr_id"]].append({k: r.get(k) for k in ("sha", "filename", "status", "patch")})
    links = {r["pr_id"]: r["issue_id"] for r in json.loads((A.CACHE / "related_issue.json").read_text())}
    issues = {r["id"]: r for r in json.loads((A.CACHE / "issue.json").read_text())}
    out = {}
    for c in sorted(cases, key=lambda c: c["original_commit_id"]):
        pr = prs[A.html_url(c["pull_request_url"])]
        key = f"{pr['html_url']}#{c['path']}"
        files = A.net_files(commits.get(pr["id"], []), c["original_commit_id"])
        if key in out or files is None:
            continue
        repo = "/".join(pr["html_url"].split("/")[3:5])
        task = A.task_text(issues.get(links.get(pr["id"])), pr)
        hit = [e for e in X.analyse(task[0], files, repo=repo, version=6).extras if A.listed([e], c["path"])]
        if hit:
            out[key] = hit[0].why[0].upper() + hit[0].why[1:]
    REASONS.write_text(json.dumps(out, indent=1))
    return out


def gh(path: str):
    r = subprocess.run(["gh", "api", "-X", "GET", path], capture_output=True, text=True, timeout=90)
    return json.loads(r.stdout) if r.returncode == 0 else None


def fetch(study: dict) -> dict:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    rows = json.loads((ROOT / "results" / "aidev_recall_v6.json").read_text())["rows"]
    ids = {f"{p['pr']}#{p['path']}": p["comment_ids"] for p in RC.pairs(rows)}
    for c in study["cases"]:
        if c["key"] in cache:
            continue
        owner, repo, _ = RC.pr_parts(c["pr"])
        got = [g for g in (gh(f"repos/{owner}/{repo}/pulls/comments/{i}") for i in ids.get(c["key"], [])) if g]
        first = min(got, key=lambda g: g["created_at"]) if got else None
        cache[c["key"]] = {"body": first["body"], "html_url": first["html_url"]} if first else {}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1))
    return cache


def main() -> int:
    study = json.loads(STUDY.read_text())
    OUT.write_text(render(study, fetch(study), json.loads(LABELS.read_text()), rule_reasons(study)) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
