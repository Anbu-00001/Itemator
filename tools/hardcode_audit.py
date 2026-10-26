#!/usr/bin/env python3
"""Hardcode audit: prove the repository's public claims are traceable.

Run:  python tools/hardcode_audit.py [--root DIR] [--only N ...]
Exit: 0 when every check passes, 1 on any FAIL.  Python 3.12, standard library only.

Checks (each prints PASS or FAIL with file:line):
 1. Numbers trace to results. Every number in README.md, AGENTS.md, docs/**/*.md,
    skills/**/*.md and the text of web/*.html (script and style dropped; placeholder,
    title, alt, aria-label and value shown) needs
    `<!-- from: results/<file>.json:<json.path> -->` on the same line, and the value
    at that path must equal the number shown (a % may show value or value*100;
    shown decimals round half up; a comment matching no number is also a FAIL).
    Exempt: years 1900-2099, versions (x.y.z, "Python 3.12", ">=3.12"), dates, times,
    issue/PR numbers (#12, "PR 12"), advisory ids (CVE-2026-109618, MAL-2023-1681), diagram
    colours and widths (rgb(255, 236, 200), 2px), list
    numbering, URLs and link targets, and a line
    marked `<!-- example -->` (a made-up sample, such as a card line in a skill).
    `--also FILE` lists, for a person to review, each number in a file that cannot carry
    source comments (the Devpost draft) that is not a number the repository shows with a
    source. A quoted live output or someone else's figure belongs there, so the list
    never changes the exit code.
 2. Pre-registration holds. A results file whose summary has `predictions_sha256`
    must name the file in `summary.predictions`, and that file must hash to it.
 3. Nothing seeded is shown as live. A file under demo/, fixtures/ or seed/ (any
    depth), or a results entry with `"seeded": true`, that README/docs mention must
    sit in a sentence with "seeded", "imported" or "simulated".
 4. Banned words, case-insensitive, whole words (plus a plural s/es), in README.md,
    AGENTS.md and docs/. "credit" is banned; "credits" only after "GitLab" or in a
    sentence about billing.
 5. Commit hygiene. No `Co-Authored-By:` trailer, and a `Signed-off-by:` trailer on
    every commit reachable from HEAD. Three kinds of commit are exempt from the sign-off
    only: the platform's own first commit, GitLab's merge-button commit ("See merge
    request" in a message with two parents and no change of its own, so a clean merge) and a
    commit authored by one of this project's flow accounts
    (service_account_group_121124982_<hash>@noreply.gitlab.com).
 6. Licences. Every dependency in pyproject.toml (including optional extras,
    dependency-groups and build requires) is in tools/licences.json with SPDX "MIT",
    or is `"dev_only": true` with a reason and used only in dev-like groups.
 7. No secrets. GitLab/GitHub token patterns, private keys, tracked `.env` files.
 8. Attribution. If a results file names hao-li/AIDev, NOTICE must say "AIDev" and
    "CC BY 4.0", and README must link NOTICE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.message}" if self.line else f"{self.file}: {self.message}"


# ---------------------------------------------------------------- helpers
def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)


SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}


def project_files(root: Path, tracked_only: bool = False) -> list[str]:
    """Tracked (and, unless tracked_only, untracked-not-ignored) files; walks the tree outside git."""
    args = ["ls-files", "-z"] if tracked_only else ["ls-files", "-z", "-co", "--exclude-standard"]
    done = git(root, *args)
    if done.returncode == 0:
        return sorted({p for p in done.stdout.split("\0") if p and (root / p).is_file()})
    return sorted(
        rel(root, p) for p in root.rglob("*")
        if p.is_file() and not (set(p.relative_to(root).parts) & SKIP_DIRS)
    )


def numbers_files(root: Path) -> list[Path]:
    found = [root / "README.md", root / "AGENTS.md"] + sorted((root / "docs").glob("**/*.md"))
    found += sorted((root / "skills").glob("**/*.md")) + sorted((root / "web").glob("*.html"))
    return [p for p in found if p.is_file()]


def banned_files(root: Path) -> list[Path]:
    found = [root / "README.md", root / "AGENTS.md"]
    found += sorted(p for p in (root / "docs").glob("**/*") if p.is_file() and p.stat().st_size < 1_000_000)
    return [p for p in found if p.is_file()]


def results_files(root: Path) -> list[Path]:
    return sorted((root / "results").glob("**/*.json"))


FROM_ANY = re.compile(r"<!--\s*from:.*?-->", re.S)
FROM_OK = re.compile(r"<!--\s*from:\s*(results/[^\s:]+\.json):(\S+?)\s*-->")
ALL_COMMENTS = re.compile(r"<!--.*?-->", re.S)
EXAMPLE = re.compile(r"<!--\s*example\s*-->")
HTML_DROP = re.compile(r"<(script|style)\b.*?</\1\s*>", re.I | re.S)
HTML_TAG = re.compile(r"<(?!!--)[^>]*>", re.S)
HTML_SHOWN = re.compile(r"""\b(?:placeholder|title|alt|aria-label|value)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)


def shown_text(path: Path, text: str) -> str:
    """What a reader sees, line for line. A page keeps its comments (so it carries sources the same way) and the attribute
    values a browser shows; a hand-typed placeholder count got past the audit when it read only Markdown."""
    if path.suffix != ".html":
        return text
    keep = lambda m: "\n" * m.group(0).count("\n")                                   # noqa: E731
    text = HTML_DROP.sub(keep, text)
    return HTML_TAG.sub(lambda m: " " + " ".join(a or b for a, b in HTML_SHOWN.findall(m.group(0))) + " " + keep(m), text)
PATH_OK = re.compile(r"(?:[A-Za-z0-9_][\w-]*|\[\d+\])(?:\.[A-Za-z0-9_][\w-]*|\[\d+\])*")


def blank(m: re.Match) -> str:
    return re.sub(r"[^\n]", " ", m.group(0))


def mask_from_comments(text: str) -> str:
    return FROM_ANY.sub(blank, text)


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Offsets of sentences: a bullet, table row or heading is its own unit; else split at . ! ?"""
    spans, group_start, pos = [], None, 0
    groups: list[tuple[int, int]] = []
    for ln in text.split("\n"):
        end = pos + len(ln)
        if not ln.strip():
            if group_start is not None:
                groups.append((group_start, pos - 1))
                group_start = None
        elif group_start is None:
            group_start = pos
        elif re.match(r"\s*(?:[-*+]\s|\d+[.)]\s|\||#)", ln):
            groups.append((group_start, pos - 1))
            group_start = pos
        pos = end + 1
    if group_start is not None:
        groups.append((group_start, len(text)))
    for gs, ge in groups:
        cut = gs
        for m in re.finditer(r"(?<=[.!?])\s+(?=[A-Z`\"(\[*])", text[gs:ge]):
            spans.append((cut, gs + m.start()))
            cut = gs + m.end()
        spans.append((cut, ge))
    return spans


def sentence_at(text: str, spans: list[tuple[int, int]], offset: int) -> str:
    for s, e in spans:
        if s <= offset <= e:
            return text[s:e]
    return text[offset:offset + 1]


def resolve_json_path(data, path: str):
    """Value at `a.b[0].c`; raises KeyError/IndexError/ValueError when absent or malformed."""
    if not PATH_OK.fullmatch(path):
        raise ValueError(f"malformed json path {path!r}")
    cur = data
    for idx, key in re.findall(r"\[(\d+)\]|([A-Za-z0-9_][\w-]*)", path):
        cur = cur[int(idx)] if idx else cur[key]
    return cur


def path_through_seeded(data, path: str) -> bool:
    cur = data
    for idx, key in re.findall(r"\[(\d+)\]|([A-Za-z0-9_][\w-]*)", path):
        if isinstance(cur, dict) and cur.get("seeded") is True:
            return True
        try:
            cur = cur[int(idx)] if idx else cur[key]
        except (KeyError, IndexError, TypeError):
            return False
    return isinstance(cur, dict) and cur.get("seeded") is True


class Results:
    """Lazy cache of parsed results/*.json."""

    def __init__(self, root: Path):
        self.root, self._cache = root, {}

    def get(self, relpath: str):
        if relpath not in self._cache:
            p = self.root / relpath
            try:
                self._cache[relpath] = json.loads(read(p)) if p.is_file() else None
            except json.JSONDecodeError:
                self._cache[relpath] = None
        return self._cache[relpath]


# ---------------------------------------------------------------- check 1
MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December"
NUM_RE = re.compile(r"(?<![\w.#!@])(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?(?P<suf>%|[A-Za-z]{1,3})?(?![\w])")
VERSION_PREFIX = re.compile(r"\b(?:c?python|py|version|ver|release|v)\s*$", re.I)
COMPARATOR_PREFIX = re.compile(r"(?:==|>=|<=|~=|!=|>|<)\s*$")
VERSION_NAME_PREFIX = re.compile(r"\b(?:gitlab|duckdb|pytest|node|go|rust|ruby)\s*$", re.I)   # only with a decimal part
ISSUE_PREFIX = re.compile(r"(?:\b(?:issues?|prs?|mrs?|pull requests?|merge requests?|pull)\s*|[#!]\s*)$", re.I)


@dataclass(frozen=True)
class Shown:
    text: str       # as printed, e.g. "26.7%"
    value: Decimal
    decimals: int
    pct: bool
    mult: tuple     # extra multipliers for k / M suffixes


def neutralise(line: str) -> str:
    s = re.sub(r"^\s*(?:>\s*)*(?:#{1,6}\s+)?\d+[.)]\s", " ", line)              # list / heading numbering
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s)                              # link targets
    s = re.sub(r"<[^>\n]*>", " ", s)
    s = re.sub(r"\b(?:https?|ftp)://\S+", " ", s)
    s = re.sub(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?Z?)?", " ", s)    # ISO dates
    s = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", s)                            # times
    s = re.sub(rf"\b(?:{MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?\b", " ", s)
    s = re.sub(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\b(?:,?\s+\d{{4}})?", " ", s)
    s = re.sub(r"\bv?\d+\.\d+\.\d+\S*", " ", s)                                    # x.y.z versions
    s = re.sub(r"\b(?:sha|utf|md|rfc|iso|ipv|gpt)-?\d+\b", " ", s, flags=re.I)     # names with a number in them
    s = re.sub(r"\b(?:CVE|MAL|PYSEC|RUSTSEC|GO)-\d{4}-\d+\b", " ", s)               # advisory ids: names, not counts
    s = re.sub(r"\brgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(?:,\s*[\d.]+\s*)?\)|\b\d+px\b", " ", s)   # diagram colours and widths
    s = re.sub(r"\b(?:CC[- ]BY(?:[- ](?:SA|NC|ND))*|Apache|L?GPL|AGPL|MPL|EPL)[- ]v?\d+(?:\.\d+)?\b", " ", s, flags=re.I)  # licence versions
    return s


def number_tokens(line: str) -> list[Shown]:
    s = neutralise(line)
    out = []
    for m in NUM_RE.finditer(s):
        whole, frac, suf = m["int"], m["frac"], m["suf"] or ""
        prefix, nxt = s[:m.start()], s[m.end():m.end() + 1]
        if suf.lower() in {"st", "nd", "rd", "th"}:
            continue
        if not frac and not suf and "," not in whole and 1900 <= int(whole) <= 2099:
            continue                                                               # year
        if VERSION_PREFIX.search(prefix) or (frac and (COMPARATOR_PREFIX.search(prefix) or VERSION_NAME_PREFIX.search(prefix) or nxt == "+")):
            continue                                                               # version
        if ISSUE_PREFIX.search(prefix):
            continue                                                               # issue / PR number
        mult = (Decimal(1000),) if suf in ("k", "K") else (Decimal(1_000_000),) if suf == "M" else ()
        out.append(Shown(m.group(0), Decimal(whole.replace(",", "") + (frac or "")), len(frac) - 1 if frac else 0, suf == "%", mult))
    return out


def shown_equals(shown: Shown, value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    v = Decimal(str(value))
    cands = [(v, False)] + [(v / m, False) for m in shown.mult] + ([(v * 100, True)] if shown.pct else [])
    for c, scaled in cands:
        if c == shown.value:
            return True
        if (shown.pct or shown.decimals) and c.quantize(Decimal(1).scaleb(-shown.decimals), rounding=ROUND_HALF_UP) == shown.value:
            return True
    return False


def check_numbers(root: Path) -> list[Finding]:
    res, found = Results(root), []
    for path in numbers_files(root):
        name, text = rel(root, path), shown_text(path, read(path))
        examples = {line_of(text, m.start()) for m in EXAMPLE.finditer(text)}
        by_line: dict[int, list[str]] = {}
        for m in FROM_ANY.finditer(text):
            by_line.setdefault(line_of(text, m.start()), []).append(m.group(0))
        body = ALL_COMMENTS.sub(lambda m: "\n" * m.group(0).count("\n"), text)
        lines = body.split("\n")
        for no in sorted(set(by_line) | set(range(1, len(lines) + 1))):
            tokens = number_tokens(lines[no - 1]) if no <= len(lines) and no not in examples else []
            values = []
            for c in by_line.get(no, []):
                ok = FROM_OK.fullmatch(c)
                if not ok:
                    found.append(Finding(name, no, f"malformed source comment {c!r}; use <!-- from: results/<file>.json:<json.path> -->"))
                    continue
                file, jpath = ok.groups()
                data = res.get(file)
                if ".." in file or data is None:
                    found.append(Finding(name, no, f"{file} is missing or not valid JSON"))
                    continue
                try:
                    val = resolve_json_path(data, jpath)
                except (KeyError, IndexError, ValueError, TypeError) as err:
                    found.append(Finding(name, no, f"{file}:{jpath} does not resolve ({type(err).__name__}: {err})"))
                    continue
                values.append((f"{file}:{jpath}", val))
            for t in tokens:
                if any(shown_equals(t, v) for _, v in values):
                    continue
                if values:
                    got = ", ".join(f"{src}={v!r}" for src, v in values)
                    found.append(Finding(name, no, f"{t.text!r} equals none of the sourced values ({got})"))
                else:
                    found.append(Finding(name, no, f"{t.text!r} has no <!-- from: results/<file>.json:<json.path> --> on this line"))
            for src, v in values:
                if not any(shown_equals(t, v) for t in tokens):
                    found.append(Finding(name, no, f"source {src}={v!r} matches no number shown on this line"))
    return found


# ---------------------------------------------------------------- check 2
def sourced_values(root: Path) -> list:
    res, out = Results(root), []
    for path in numbers_files(root):
        for m in FROM_OK.finditer(read(path)):
            data = res.get(m.group(1))
            try:
                out.append(resolve_json_path(data, m.group(2)))
            except (KeyError, IndexError, ValueError, TypeError):
                pass                                                        # check 1 reports it
    return out


def check_also(root: Path, paths: list[Path]) -> list[Finding]:
    """A file that cannot carry source comments (the Devpost text): every number in it must be one the repository shows with a
    source. It cannot tell two equal numbers apart, so it catches a stale or hand-typed count, not a number put in the wrong place."""
    values, found = sourced_values(root), []
    for path in paths:
        text = ALL_COMMENTS.sub(lambda m: "\n" * m.group(0).count("\n"), read(path))
        examples = {line_of(read(path), m.start()) for m in EXAMPLE.finditer(read(path))}
        for no, line in enumerate(text.split("\n"), 1):
            for t in [] if no in examples else number_tokens(line):
                if not any(shown_equals(t, v) for v in values):
                    found.append(Finding(str(path), no, f"{t.text!r} is not a number the repository shows with a source"))
    return found


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_prereg(root: Path) -> list[Finding]:
    found = []
    for path in results_files(root):
        name = rel(root, path)
        try:
            data = json.loads(read(path))
        except json.JSONDecodeError as err:
            found.append(Finding(name, err.lineno, f"not valid JSON: {err.msg}"))
            continue
        summary = data.get("summary") if isinstance(data, dict) else None
        if not isinstance(summary, dict) or "predictions_sha256" not in summary:
            continue
        declared, target = summary["predictions_sha256"], summary.get("predictions")
        line = next((i for i, ln in enumerate(read(path).split("\n"), 1) if "predictions_sha256" in ln), 0)
        if not isinstance(target, str) or not isinstance(declared, str):
            found.append(Finding(name, line, "predictions_sha256 needs a summary.predictions path and a string hash"))
        elif ".." in target or not (root / target).is_file():
            found.append(Finding(name, line, f"summary.predictions names {target}, which does not exist"))
        else:
            actual = sha256_file(root / target)
            if actual != declared:
                found.append(Finding(name, line, f"{target} hashes to {actual}, but the pre-registered hash is {declared}"))
    return found


# ---------------------------------------------------------------- check 3
SEED_DIRS = {"demo", "fixtures", "seed"}
SEED_WORD = re.compile(r"\b(?:seeded|imported|simulated)\b", re.I)
ID_KEYS = ("id", "name", "title", "pr_url", "url", "path", "file", "label", "slug")


def seed_tokens(relpath: str) -> set[str]:
    parts = relpath.split("/")
    idx = next((i for i, p in enumerate(parts[:-1]) if p in SEED_DIRS), None)
    if idx is None:
        return set()
    toks = set()
    for start in {0, idx}:
        for end in range(idx, len(parts)):
            toks.add("/".join(parts[start:end + 1]) + ("/" if end < len(parts) - 1 else ""))
    return toks


def find_seeded(data) -> list[dict]:
    out = []
    if isinstance(data, dict):
        if data.get("seeded") is True:
            out.append(data)
        for k, v in data.items():
            out += find_seeded(v)
    elif isinstance(data, list):
        for v in data:
            out += find_seeded(v)
    return out


def mentions(text: str, token: str) -> list[int]:
    return [m.start() for m in re.finditer(r"(?<![\w-])" + re.escape(token), text)]


def check_seeded(root: Path) -> list[Finding]:
    res, found = Results(root), []
    seed_files = {f: seed_tokens(f) for f in project_files(root)}
    seed_files = {f: t for f, t in seed_files.items() if t}
    result_names = [rel(root, p) for p in results_files(root)]
    seeded_entries = {n: find_seeded(res.get(n)) for n in result_names}
    for path in numbers_files(root):
        name, raw = rel(root, path), read(path)
        text = mask_from_comments(raw)
        spans = sentence_spans(text)
        probes: list[tuple[int, str, str]] = []                      # (offset, what, token)
        for f, toks in seed_files.items():
            for tok in toks:
                probes += [(o, f, tok) for o in mentions(text, tok)]
        for n, entries in seeded_entries.items():
            if entries:
                probes += [(o, n, n) for o in mentions(text, n)]
            for e in entries:
                for k in ID_KEYS:
                    v = e.get(k)
                    if isinstance(v, str) and len(v) >= 4:
                        probes += [(o, f"{n} entry {v!r}", v) for o in mentions(text, v)]
        for m in FROM_ANY.finditer(raw):                              # numbers sourced from a seeded entry
            ok = FROM_OK.fullmatch(m.group(0))
            if ok and res.get(ok[1]) is not None and path_through_seeded(res.get(ok[1]), ok[2]):
                probes.append((m.start(), f"{ok[1]}:{ok[2]} (a seeded entry)", ""))
        seen = set()
        for off, what, _ in sorted(probes):
            sentence = sentence_at(text, spans, off)
            key = (line_of(text, off), what)
            if key in seen or SEED_WORD.search(sentence):
                continue
            seen.add(key)
            found.append(Finding(name, line_of(text, off), f"mentions {what} without saying seeded, imported or simulated in the same sentence"))
    return found


# ---------------------------------------------------------------- check 4
BANNED = ("guardian", "gate", "proof", "receipt", "evidence", "ledger", "witness", "canary",
          "trust", "earned", "calibrated", "autopilot", "sentinel", "verdict")
BANNED_RE = re.compile(r"\b(?:" + "|".join(BANNED) + r")(?:e?s)?\b|\brisk[\s-]+scores?\b", re.I)
CREDIT_RE = re.compile(r"\bcredit\b", re.I)
CREDITS_RE = re.compile(r"\bcredits\b", re.I)
GITLAB_BEFORE = re.compile(r"gitlab\s+$", re.I)
BILLING = re.compile(r"\b(?:bill\w*|cost\w*|usage|budget\w*|cap|spend|spent|quota|prices?|pricing|charged?|monthly|per month|dollars?)\b|\$", re.I)


def check_banned(root: Path) -> list[Finding]:
    found = []
    for path in banned_files(root):
        name, raw = rel(root, path), read(path)
        text = mask_from_comments(raw)
        spans = sentence_spans(text)
        for m in BANNED_RE.finditer(text):
            found.append(Finding(name, line_of(text, m.start()), f"banned word {m.group(0)!r}"))
        for m in CREDIT_RE.finditer(text):
            if not GITLAB_BEFORE.search(text[:m.start()]):
                found.append(Finding(name, line_of(text, m.start()), "banned word 'credit' (only 'GitLab Credits' or billing 'credits' are allowed)"))
        for m in CREDITS_RE.finditer(text):
            if GITLAB_BEFORE.search(text[:m.start()]) or BILLING.search(sentence_at(text, spans, m.start())):
                continue
            found.append(Finding(name, line_of(text, m.start()), "'credits' outside a billing sentence or 'GitLab Credits'"))
    return found


# ---------------------------------------------------------------- check 5
UNSIGNED_PLATFORM_COMMIT = "36891e91"
# Only this project's own flow accounts (group 121124982 is the top-level group that owns the Duo service accounts):
SERVICE_ACCOUNT_EMAIL = re.compile(r"service_account_group_121124982_[0-9a-f]{32}@noreply\.gitlab\.com")


def _merge_is_git_own(root: Path, sha: str, parents: list[str]) -> bool:
    """True when the merge commit holds exactly what git itself makes of its two parents (so no hand-made change, which a
    sign-off would cover). Two edits to neighbouring lines of one file merge cleanly yet show in `diff-tree --cc`, so that
    diff alone is not the test; it is the fallback for a git too old to have `merge-tree --write-tree`."""
    if len(parents) == 2:
        made = git(root, "merge-tree", "--write-tree", *parents)
        if made.returncode == 0:
            return made.stdout.split("\n")[0].strip() == git(root, "rev-parse", f"{sha}^{{tree}}").stdout.strip()
    return not git(root, "diff-tree", "--cc", "--no-commit-id", "-p", "-r", sha).stdout.strip()


def check_commits(root: Path) -> list[Finding]:
    done = git(root, "log", "--format=%H%x1f%P%x1f%ae%x1f%B%x1e")
    if done.returncode != 0:
        return [Finding("git", 0, f"cannot read the commit log: {done.stderr.strip() or 'not a git repository'}")]
    found = []
    for record in done.stdout.split("\x1e"):
        if not record.strip():
            continue
        sha, parents, email, body = record.strip("\n").split("\x1f", 3)
        where = f"commit {sha[:8]}"
        if re.search(r"^\s*co-authored-by\s*:", body, re.I | re.M):
            found.append(Finding(where, 0, "has a Co-Authored-By trailer"))
        # The hackathon platform created this project with its own unsigned "Initial commit"; we did not write it
        # and never rewrite published history, so it is the one commit allowed without a sign-off.
        if sha.startswith(UNSIGNED_PLATFORM_COMMIT):
            continue
        # Two more kinds are not written by a person: the merge commit GitLab makes when the Merge button is used
        # (it holds no change of its own; its parents are checked) and a commit made by a flow's service account
        # (a person who does not sign it off has not accepted the DCO for it; the merge request they approve is theirs).
        if len(parents.split()) > 1 and "See merge request " in body and _merge_is_git_own(root, sha, parents.split()):
            continue                                   # a merge that adds changes of its own needs a sign-off like any commit
        if SERVICE_ACCOUNT_EMAIL.fullmatch(email):
            continue
        if not re.search(r"^\s*signed-off-by\s*:\s*\S.*<[^>\s]+>", body, re.I | re.M):
            found.append(Finding(where, 0, f"has no Signed-off-by trailer ({body.strip().splitlines()[0][:50] if body.strip() else 'empty message'})"))
    return found


# ---------------------------------------------------------------- check 6
DEV_GROUPS = {"dev", "test", "tests", "lint", "docs", "ci", "typing"}


def norm_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def collect_deps(py: dict) -> list[tuple[str, str, str]]:
    """(normalised name, raw requirement, group); group 'runtime', an extra/group name, or 'build'."""
    deps = [(r, "runtime") for r in py.get("project", {}).get("dependencies", [])]
    for g, reqs in py.get("project", {}).get("optional-dependencies", {}).items():
        deps += [(r, g.lower()) for r in reqs]
    for g, reqs in py.get("dependency-groups", {}).items():
        deps += [(r, g.lower()) for r in reqs if isinstance(r, str)]
    deps += [(r, "build") for r in py.get("build-system", {}).get("requires", [])]
    out = []
    for raw, group in deps:
        m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", raw)
        if m:
            out.append((norm_name(m.group(1)), raw, group))
    return out


def check_licences(root: Path) -> list[Finding]:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return []
    try:
        py = tomllib.loads(read(pyproject))
    except tomllib.TOMLDecodeError as err:
        return [Finding("pyproject.toml", 0, f"not valid TOML: {err}")]
    deps = collect_deps(py)
    if not deps:
        return []
    allow_path = root / "tools" / "licences.json"
    try:
        allow = {norm_name(k): v for k, v in json.loads(read(allow_path)).items() if not k.startswith("_")}
    except (OSError, json.JSONDecodeError) as err:
        return [Finding("tools/licences.json", 0, f"allow-list missing or invalid: {err}")]
    lines = read(pyproject).split("\n")
    found = []
    for name, raw, group in deps:
        line = next((i for i, ln in enumerate(lines, 1) if raw in ln), 0)
        entry = allow.get(name)
        if not isinstance(entry, dict) or not entry.get("spdx"):
            found.append(Finding("pyproject.toml", line, f"{name} is not in tools/licences.json with an spdx id"))
        elif entry["spdx"] == "MIT":
            continue
        elif entry.get("dev_only") is not True:
            found.append(Finding("pyproject.toml", line, f"{name} is {entry['spdx']}, not MIT, and not marked dev_only"))
        elif not str(entry.get("reason", "")).strip():
            found.append(Finding("tools/licences.json", 0, f"{name} is dev_only but gives no reason"))
        elif group not in DEV_GROUPS:
            found.append(Finding("pyproject.toml", line, f"{name} is {entry['spdx']} and dev_only, but used in {group!r}, not a dev group"))
    return found


# ---------------------------------------------------------------- check 7
SECRET_PATTERNS = (
    ("GitLab token", re.compile(r"glpat-[0-9A-Za-z_\-]{20,}")),
    ("GitHub token", re.compile(r"gh[pousr]_[0-9A-Za-z]{36,}")),
    ("GitHub fine-grained token", re.compile(r"github_pat_[0-9A-Za-z_]{22,}")),
    ("private key", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY(?: BLOCK)?-----")),
)
ENV_OK = {".env.example", ".env.sample", ".env.template"}


def check_secrets(root: Path) -> list[Finding]:
    found = []
    for f in project_files(root, tracked_only=True):
        base = f.rsplit("/", 1)[-1]
        if (base == ".env" or base.startswith(".env.")) and base not in ENV_OK:
            found.append(Finding(f, 0, "a .env file is tracked in git"))
    for f in project_files(root):
        p = root / f
        if p.stat().st_size > 2_000_000:
            continue
        data = p.read_bytes()
        if b"\0" in data[:8000]:
            continue
        text = data.decode("utf-8", errors="replace")
        for label, rx in SECRET_PATTERNS:
            for m in rx.finditer(text):
                found.append(Finding(f, line_of(text, m.start()), f"looks like a {label}"))
    return found


# ---------------------------------------------------------------- check 8
def check_attribution(root: Path) -> list[Finding]:
    users = [rel(root, p) for p in results_files(root) if "hao-li/aidev" in read(p).lower()]
    if not users:
        return []
    found = []
    notice = next((root / n for n in ("NOTICE", "NOTICE.md", "NOTICE.txt") if (root / n).is_file()), None)
    if notice is None:
        found.append(Finding("NOTICE", 0, f"missing, but {users[0]} names hao-li/AIDev"))
    else:
        text = read(notice)
        for needle in ("AIDev", "CC BY 4.0"):
            if needle not in text:
                found.append(Finding(notice.name, 0, f"does not contain {needle!r}, required because {users[0]} names hao-li/AIDev"))
    readme = root / "README.md"
    link = re.compile(r"\]\((?:[^)\s]*/)?NOTICE(?:\.(?:md|txt))?(?:#[^)\s]*)?\)|^\[[^\]]+\]:\s*(?:\S*/)?NOTICE(?:\.(?:md|txt))?\s*$", re.M)
    if not readme.is_file() or not link.search(read(readme)):
        found.append(Finding("README.md", 0, "does not link NOTICE"))
    return found


# ---------------------------------------------------------------- main
CHECKS = (
    ("Numbers trace to results", check_numbers),
    ("Pre-registration holds", check_prereg),
    ("Nothing seeded is shown as live", check_seeded),
    ("Banned words", check_banned),
    ("Commit hygiene", check_commits),
    ("Licences", check_licences),
    ("No secrets", check_secrets),
    ("Attribution", check_attribution),
)


def run(root: Path, only: set[int] | None = None) -> list[tuple[int, str, list[Finding]]]:
    return [(i, name, fn(root)) for i, (name, fn) in enumerate(CHECKS, 1) if not only or i in only]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Prove the repository's claims are not hardcoded.")
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--only", type=int, nargs="+", metavar="N", help="run only these check numbers")
    ap.add_argument("--also", type=Path, nargs="+", default=[], metavar="FILE", help="more text whose numbers must be sourced ones")
    args = ap.parse_args(argv)
    results = run(args.root.resolve(), set(args.only or []))
    review = check_also(args.root.resolve(), args.also) if args.also else []
    for i, name, findings in results:
        print(f"{'FAIL' if findings else 'PASS'}  {i}. {name}")
        for f in findings:
            print(f"      {f}")
    failed = [i for i, _, f in results if f]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed" + (f" (checks {', '.join(map(str, failed))})" if failed else ""))
    if args.also:
        print(f"\nREVIEW  {len(review)} number(s) in --also files that the repository does not show with a source:")
        for f in review:
            print(f"      {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
