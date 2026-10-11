"""The CI job: compute Itemator's facts for one merge request and save itemator.json.

Run in a merge request pipeline as `python -m itemator.ci [--out itemator.json]`.
Standard library only. The job only reads: git, and the GitLab API, anonymously
first (the project is public) and with the job token only when that read is
refused. It never writes to the merge request (the job token cannot); the Duo
flow reads itemator.json and posts the card.

Exit 0 whatever the facts say: they are information, not a merge condition.
Exit 2 when the job itself breaks: a missing CI variable, a git command or an
API read that fails. The message says which.

Inputs (GitLab's predefined variables): CI_API_V4_URL, CI_PROJECT_ID,
CI_PROJECT_PATH, CI_MERGE_REQUEST_IID, CI_MERGE_REQUEST_DIFF_BASE_SHA,
CI_COMMIT_SHA (or CI_MERGE_REQUEST_SOURCE_BRANCH_SHA in a merged results
pipeline, where CI_COMMIT_SHA is the merge commit), CI_JOB_TOKEN.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import posixpath
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

from itemator import extras as X

STATES = ("inside_ask", "extras", "no_issue", "author_wrote_issue", "unplaced_only")
INJECTION_LINE = "This MR contains text addressed to automated reviewers; it was not followed."


class JobError(Exception):
    """The job could not compute the facts (not a finding about the MR)."""


# -------------------------------------------------------------------- git

_STATUS = {"A": "added", "D": "removed", "M": "modified", "R": "renamed", "C": "copied", "T": "changed"}


def _git(repo: str, *args: str) -> bytes:
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, check=False)
    except OSError as e:
        raise JobError(f"git could not start: {e}") from e
    if r.returncode != 0:
        raise JobError(f"git {args[0]} failed (exit {r.returncode}): "
                       f"{r.stderr.decode('utf-8', 'replace').strip()[:500]}")
    return r.stdout


def _hunk_lines(chunk: str):
    """The lines of one file's diff from its first hunk header on, or None when it has no hunk."""
    lines = chunk.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for k, line in enumerate(lines):
        if line.startswith("@@"):
            return lines[:k], lines[k:]
    return lines, None


def diff_files(repo: str, base: str, head: str) -> list[dict]:
    """`git diff --find-renames base head` as the file list extras() takes (GitHub's field names)."""
    raw = _git(repo, "diff", "--find-renames", "--no-ext-diff", "--name-status", "-z", base, head).split(b"\0")
    entries, i = [], 0
    while i < len(raw) and raw[i]:
        code = raw[i].decode()[0]
        if code in "RC":
            old, new, i = raw[i + 1], raw[i + 2], i + 3
        else:
            old = new = raw[i + 1]
            i += 2
        entries.append((code, old.decode("utf-8", "replace"), new.decode("utf-8", "replace")))
    patch = _git(repo, "diff", "--find-renames", "--no-ext-diff", "--no-color", "-p", base, head)
    chunks = [c for c in re.split(r"(?m)^(?=diff --git )", patch.decode("utf-8", "replace"))
              if c.startswith("diff --git ")]
    if len(chunks) != len(entries):
        raise JobError(f"git diff listed {len(entries)} files but printed {len(chunks)} patches")
    sizes = {}
    if any(code == "A" for code, _, _ in entries):
        for row in _git(repo, "ls-tree", "-r", "-l", "-z", head).split(b"\0"):
            meta, _, path = row.partition(b"\t")
            parts = meta.split()
            if len(parts) == 4 and parts[3].isdigit():
                sizes[path.decode("utf-8", "replace")] = int(parts[3])
    files = []
    for (code, old, new), chunk in zip(entries, chunks):
        header, hunks = _hunk_lines(chunk)
        f = {"filename": new, "status": _STATUS.get(code, "modified"),
             "patch": "\n".join(hunks) + "\n" if hunks else None,
             "additions": sum(1 for line in hunks or () if line.startswith("+")),
             "deletions": sum(1 for line in hunks or () if line.startswith("-"))}
        if code in "RC":
            f["previous_filename"] = old
        if any(line.startswith("Binary files ") for line in header):
            f["binary"] = True
        if code == "A" and new in sizes:
            f["size"] = sizes[new]
        files.append(f)
    return files


def added_lines(patch: str | None):
    """Yield (line number in the new file, text) for each added line of a patch."""
    if not patch:
        return
    n = 0
    for line in patch.split("\n"):
        if line.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            n = int(m.group(1)) if m else 0
        elif line.startswith("+"):
            yield n, line[1:]
            n += 1
        elif line.startswith(" "):
            n += 1


# -------------------------------------------------------------------- API

def http_get(url: str, headers: dict) -> tuple[int, bytes]:
    """One GET. Returns (status, body); raises JobError when the server cannot be reached."""
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "itemator-ci", **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise JobError(f"GET {url} failed: {e}") from e


class Api:
    def __init__(self, base_url: str, token: str | None, http):
        self.base, self.token, self.http = base_url.rstrip("/"), token, http

    def get(self, path: str, missing_ok: bool = False):
        url = self.base + path
        status, body = self.http(url, {})
        if status in (401, 403, 404) and self.token:
            status, body = self.http(url, {"JOB-TOKEN": self.token})
        if status == 404 and missing_ok:
            return None
        if status != 200:
            raise JobError(f"GET {path} returned HTTP {status}")
        try:
            return json.loads(body)
        except ValueError as e:
            raise JobError(f"GET {path} did not return JSON") from e


_CLOSING = re.compile(
    r"\b(?:clos(?:e|es|ed|ing)|fix(?:es|ed|ing)?|resolv(?:e|es|ed|ing)|implement(?:s|ed|ing)?)\b:?\s+"
    r"(#\d+(?:(?:\s*,\s*(?:and\s+)?|\s+and\s+)#\d+)*)", re.I)


def closing_refs(text: str | None) -> list[int]:
    """Issue numbers after 'Closes/Fixes/Resolves/Implements' (this project's issues only)."""
    out = []
    for m in _CLOSING.finditer(text or ""):
        for n in re.findall(r"#(\d+)", m.group(1)):
            if int(n) not in out:
                out.append(int(n))
    return out


def _issue(raw: dict, project_id: str) -> dict:
    iid = raw.get("iid")
    if str(raw.get("project_id")) == str(project_id):
        ref = f"#{iid}"
    else:
        m = re.search(r"://[^/]+/(.+?)/-/(?:issues|work_items)/\d+", raw.get("web_url") or "")
        ref = f"{m.group(1)}#{iid}" if m else f"#{iid}"
    author = raw.get("author") or {}
    return {"iid": iid, "ref": ref, "title": raw.get("title") or "",
            "description": raw.get("description") or "", "author_id": author.get("id")}


def linked_issues(api: Api, project_id: str, mr_iid: str, description: str, warnings: list):
    """The MR's issues: GitLab's closes_issues, else closing words in the description."""
    closes = api.get(f"/projects/{project_id}/merge_requests/{mr_iid}/closes_issues?per_page=100")
    if closes:
        return [_issue(i, project_id) for i in closes], "closes_issues"
    issues = []
    for n in closing_refs(description):
        raw = api.get(f"/projects/{project_id}/issues/{n}", missing_ok=True)
        if raw is None:
            warnings.append(f"#{n} is named in the description but was not found")
            continue
        issues.append(_issue(raw, project_id))
    return issues, ("description" if issues else "none")


# -------------------------------------------------------------- injection
# Text in the MR aimed at automated reviewers. A flag on the card, never a block.

_PHRASES = (
    ("ignore_previous", r"\b(?:ignore|disregard|forget)\s+(?:(?:all|any|the|your|of)\s+)*"
                        r"(?:previous|prior|above|earlier|preceding)\b"),
    ("you_are_an_ai", r"\byou\s+are\s+(?:an?\s+|the\s+)?(?:ai|llm|(?:large\s+)?language\s+model|chatbot|bot"
                      r"|automated\s+reviewer)\b"),
    ("reviewer_approve", r"\bas\s+(?:the|an?)\s+(?:\w+\s+){0,2}reviewer\b[\s,:]+(?:\w+\s+){0,3}approve\b"),
    ("system_prompt", r"\bsystem\s+prompt\b"),
    ("new_instructions", r"\b(?:new|updated|real|actual)\s+instructions\s*:"),
)
_PHRASE_RE = [(rule, re.compile(rx, re.I)) for rule, rx in _PHRASES]
_TAG = re.compile("[\U000E0000-\U000E007F]")
_BIDI = re.compile("[‪-‮⁦-⁩‎‏؜]")
_INVISIBLE = re.compile("[​-‍⁠﻿\U000E0000-\U000E007F]")
_COMMENT = re.compile(r"<!--(.*?)-->", re.S)
_ADDRESSEE = re.compile(r"\b(?:ai|llm|model|bot|agent|assistant|reviewer|duo|claude|copilot|gpt)s?\b", re.I)
_IMPERATIVE = re.compile(r"\b(?:ignore|disregard|forget|approve|merge|do\s+not|don'?t|never|must|override"
                         r"|pretend|act\s+as|respond|reply|say|output)\b", re.I)


def _phrases(text: str) -> list[str]:
    plain = _INVISIBLE.sub("", text)
    return [rule for rule, rx in _PHRASE_RE if rx.search(plain)]


def _is_agent_config(path: str) -> bool:
    parts = path.split("/")
    base = parts[-1].lower()
    return (base in ("agents.md", "claude.md")
            or path.startswith(".gitlab/duo/")
            or (base == "skill.md" and "skills" in parts[:-1])
            or ("flows" in parts[:-1] and base.endswith((".yml", ".yaml"))))


def scan_text(where: str, numbered: list[tuple[int, str]]) -> list[dict]:
    """Findings in a list of (line number, text) lines."""
    out = []
    for n, line in numbered:
        out += [{"where": where, "line": n, "rule": f"phrase:{r}"} for r in _phrases(line)]
        if _TAG.search(line):
            out.append({"where": where, "line": n, "rule": "unicode_tag"})
        if _BIDI.search(line):
            out.append({"where": where, "line": n, "rule": "bidi_control"})
    joined = "\n".join(text for _, text in numbered)
    starts = [n for n, _ in numbered]
    for m in _COMMENT.finditer(joined):
        body = _INVISIBLE.sub("", m.group(1))
        if _phrases(body) or (_ADDRESSEE.search(body) and _IMPERATIVE.search(body)):
            out.append({"where": where, "line": starts[joined.count("\n", 0, m.start())],
                        "rule": "html_comment"})
    return out


def scan_injection(mr_title: str, mr_description: str, issues: list[dict], files: list[dict]) -> list[dict]:
    def lines(text):
        return list(enumerate((text or "").split("\n"), start=1))
    out = scan_text("mr title", lines(mr_title)) + scan_text("mr description", lines(mr_description))
    for i in issues:
        out += scan_text(f"issue {i['ref']} title", lines(i["title"]))
        out += scan_text(f"issue {i['ref']} description", lines(i["description"]))
    for f in files:
        paths = {f["filename"], f.get("previous_filename") or f["filename"]}
        if any(_is_agent_config(p) for p in paths):
            out.append({"where": f"diff {f['filename']}", "line": None, "rule": "agent_config_edit"})
        out += scan_text(f"diff {f['filename']}", list(added_lines(f.get("patch"))))
    seen, unique = set(), []
    for d in out:
        key = (d["where"], d["line"], d["rule"])
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


# ------------------------------------------------------------ state, card

AUTHOR_CAVEAT = "No one but the author described this change."


def _author_wrote(issues: list[dict], mr_author_id) -> bool:
    return bool(issues) and mr_author_id is not None and all(i["author_id"] == mr_author_id for i in issues)


def decide_state(issues: list[dict], mr_author_id, analysis) -> str:
    if not issues:
        return "no_issue"
    if analysis.extras:                      # the extras are the point; the author note rides along as a caveat
        return "extras"
    if _author_wrote(issues, mr_author_id):
        return "author_wrote_issue"
    if analysis.unplaced:
        return "unplaced_only"
    return "inside_ask"


_LABEL = {"new_dependency": "new dependency", "ci_or_config": "config change", "tests_removed": "tests removed",
          "generated_code_removed": "generated code removed", "public_api_removed": "public API removed",
          "binary_or_large_added": "binary or large file", "version_bump": "version bump",
          "build_output_added": "build output", "stray_file": "stray file"}
_UNIT = {"new_dependency": "packages"}      # what a grouped extra's detail lists when it is not files


def _label(e) -> str:
    label = _LABEL.get(e.kind, e.kind)
    if e.kind == "ci_or_config" and (X._config_kind(e.path) or ("",))[0] == "CI config":
        label = "CI change"
    if not e.detail:
        return label
    unit = "files" if e.path.endswith("/") or e.kind == "version_bump" else _UNIT.get(e.kind, "names")
    return f"{label}, {len(e.detail)} {unit}"


# ---------------------------------------------------------------- grouping (rules v4)

GROUP = 6   # extras of one kind from one file or one directory shown as one card line with a count (brief T15 item 7;
            # T10 audit of sample C, table 2: single manifests put 7 and 8 dependency lines on one card)
_PLURAL = {"new_dependency": "new dependencies", "ci_or_config": "config changes", "tests_removed": "test files that lose tests",
           "generated_code_removed": "generated files deleted", "public_api_removed": "public names removed",
           "binary_or_large_added": "binary or large files added", "version_bump": "version changes",
           "build_output_added": "build output directories", "stray_file": "stray file entries"}


def _group_key(e):
    if e.detail:
        return None                    # a mass event or a group already
    return e.kind, (e.path if e.name != e.path else posixpath.dirname(e.path) + "/")


def group_extras(extras: list) -> list:
    """[(extra, items)]: GROUP or more extras of one kind from one file (the dependencies of a manifest, the names
    of a module) or, for kinds named by their path, from one directory become one extra at the first one's place,
    named by that file or directory, with the names as detail; `items` keeps the extras it stands for."""
    pools = {}
    for e in extras:
        pools.setdefault(_group_key(e), []).append(e)
    out = []
    for e in extras:
        key = _group_key(e)
        if key is None or len(pools[key]) < GROUP:
            out.append((e, ()))
        elif pools[key][0] is e:
            items, where = tuple(pools[key]), (key[1] if key[1] != "/" else "./")
            why = f"{len(items)} {_PLURAL.get(e.kind, e.kind)} in {where}: " + ", ".join(i.name for i in items)
            out.append((X.Extra(e.kind, where, where, why, tuple(i.name for i in items)), items))
    return out


def card_lines(state: str, issues: list[dict], extras: list, unplaced: list, injection: list,
               author_wrote: bool = False) -> dict:
    refs = ", ".join(i["ref"] for i in issues)
    if state == "no_issue":
        final, todo = "No one described this change.", "Link the issue it answers, or say why it needs none."
    elif state == "author_wrote_issue":
        final, todo = AUTHOR_CAVEAT, f"A second person reads {refs} before approving."
    elif state == "extras":
        names = ", ".join(f"`{e.name}` ({_label(e)})" for e in extras)
        final = f"{len(extras)} {'thing' if len(extras) == 1 else 'things'} beyond {refs}: {names}."
        todo = 'Type each name in its thread to keep it, or reply "split" to move it to its own MR.'
    elif state == "unplaced_only":
        n = len(unplaced)
        final = f"{n} {'file' if n == 1 else 'files'} the rules could not place."
        todo = "Skim this file." if n == 1 else f"Skim these {n} files."
    else:
        final, todo = f"Nothing beyond {refs}.", "Approve as usual."
    caveat = AUTHOR_CAVEAT if author_wrote and state in ("extras", "unplaced_only", "inside_ask") else None
    return {"final_line": final, "todo_line": todo, "caveat_line": caveat,
            "injection_line": INJECTION_LINE if injection else None}


# ---------------------------------------------------------------- anchors
# Where each extra sits in the diff, so the flow can open a thread on that line
# (create_merge_request_diff_note: old_path, new_path, and old_line for a removed
# line or new_line for an added one) without computing anything itself.

MAX_PATCH_BYTES = 204_800     # GitLab's default per-file patch limit (diff_max_patch_bytes); over it, no lines to comment on
_HUNK = re.compile(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def diff_lines(patch: str | None):
    """Yield (sign, old_no, new_no, text) for each line of a patch that starts at a hunk header.

    '+' has only new_no, '-' only old_no, ' ' (context) both. The header sets the counters, so a hunk
    that starts mid-file is numbered from its own start. The "\\ No newline at end of file" marker
    is not a line."""
    if not patch:
        return
    lines = patch.split("\n")
    if lines[-1] == "":
        lines.pop()
    old = new = 0
    for line in lines:
        if line.startswith("@@"):
            m = _HUNK.match(line)
            if m:
                old, new = int(m.group(1)), int(m.group(2))
            continue
        if line.startswith("\\"):
            continue
        if line.startswith("+"):
            yield "+", None, new, line[1:]
            new += 1
        elif line.startswith("-"):
            yield "-", old, None, line[1:]
            old += 1
        else:
            yield " ", old, new, line[1:]
            old += 1
            new += 1


def _first_line(f: dict, signs: str, matches=None):
    """The first added ('+') or removed ('-') line of f's patch that `matches`, as an anchor, else None."""
    for sign, old, new, text in diff_lines(f.get("patch")):
        if sign in signs and (matches is None or matches(text)):
            return {"old_path": f.get("previous_filename") or f["filename"], "new_path": f["filename"],
                    "old_line": old, "new_line": new}
    return None


def _names(name: str):
    """A test for a line that names a package: case, '-', '_' and '.' are interchangeable, and the
    name is not a piece of a longer one."""
    parts = [re.escape(p) for p in re.split(r"[-_.]+", name) if p]
    if not parts:
        return None
    return re.compile(r"(?<![A-Za-z0-9])" + r"[-_.]*".join(parts) + r"(?![A-Za-z0-9])", re.I).search


def anchor_for(e, by_path: dict):
    """(anchor, None) or (None, reason): the line of the diff an extra sits on.

    Added-line kinds (dependency, config, binary or large) anchor on an added line, the first one that
    names the package; removed-line kinds (tests, public API, generated code) on the first removed line
    that carries the test or the symbol. Either falls back to the first line of the other sign (a deleted
    CI file has only removed lines). A mass event anchors on the first file of its detail list."""
    f = by_path.get(e.detail[0] if e.detail else e.path)
    if f is None:
        return None, "file not in the diff"
    patch = f.get("patch")
    if f.get("binary") or not patch:
        return None, "no text patch"
    if len(patch.encode("utf-8", "replace")) > MAX_PATCH_BYTES:
        return None, "patch over GitLab's size limit"
    if e.kind == "tests_removed":
        signs, matches = "-", (X._ASSERT if "assertion lines" in e.why else X._TEST_DEF).search
    elif e.kind == "public_api_removed":
        ext = X._ext(f["filename"])
        signs, matches = "-", lambda text: e.name in X._symbols(text, ext)
    elif e.kind == "generated_code_removed":
        signs, matches = "-", None
    else:
        signs, matches = "+", None
        if e.kind == "new_dependency":
            matches = _names(e.name)
        elif e.kind == "version_bump":
            matches = lambda text: e.name in text
        elif e.kind == "ci_or_config" and not e.detail and e.name != e.path:      # an npm script: its own line
            matches = lambda text: f'"{e.name}"' in text
    other = "+-".replace(signs, "")
    a = _first_line(f, signs, matches) or _first_line(f, signs) or _first_line(f, other)
    return (a, None) if a else (None, "no text patch")


def _code(text: str) -> str:
    """An inline code span that holds any text, backticks included, on one line."""
    text = re.sub(r"[\r\n]+", " ", text)
    fence = "`" * (max((len(run) for run in re.findall(r"`+", text)), default=0) + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def thread_stub(e) -> str:
    """The opening text of the extra's thread; the flow may post it as it is."""
    why = re.sub(r"[\r\n]+", " ", e.why).strip()
    if not why.endswith((".", "!", "?")):
        why += "."
    return (f"{_code(e.name)} ({_label(e)}): {why} To keep it, reply with its exact name. "
            "To move it into its own MR, reply `split`. If this is not really an extra, reply `not an extra`.")


def describe_extra(e, by_path: dict, items: tuple = ()) -> dict:
    """A grouped extra (`items`, from group_extras) anchors where its first item does, and keeps every item in
    plain_facts.detail."""
    anchor, reason = anchor_for(items[0] if items else e, by_path)
    plain = {"kind": e.kind, "name": e.name, "why": e.why, "detail_count": len(e.detail), "path": e.path}
    if items:
        plain["detail"] = [i.to_dict() for i in items]
    return {**e.to_dict(), "detail": list(e.detail), "anchor": anchor, "anchorless_reason": reason,
            "thread_stub": thread_stub(e), "plain_facts": plain}


def facts(*, mr_iid: int, mr_title: str, mr_description: str, mr_author_id, issues: list[dict],
          issues_from: str, files: list[dict], repo: str | None, base_sha: str, head_sha: str,
          warnings: list, now: datetime.datetime) -> dict:
    issue_text = "\n\n".join(f"{i['title']}\n{i['description']}" for i in issues)
    analysis = X.analyse(issue_text, files, repo=repo)
    state = decide_state(issues, mr_author_id, analysis)
    found = [] if state == "no_issue" else analysis.extras      # no ask, so nothing is "beyond" it
    grouped = group_extras(found)
    unplaced = [] if state == "no_issue" else analysis.unplaced
    injection = scan_injection(mr_title, mr_description, issues, files)
    by_path = {f["filename"]: f for f in files}
    return {
        "rules_version": X.RULES_VERSION,
        "mr_iid": mr_iid,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "issue_iids": [i["iid"] for i in issues],
        "issues_from": issues_from,
        "state": state,
        "extras": [describe_extra(e, by_path, items) for e, items in grouped],
        "unplaced": list(unplaced),
        "injection": injection,
        "card": card_lines(state, issues, [e for e, _ in grouped], unplaced, injection, _author_wrote(issues, mr_author_id)),
        "warnings": warnings,
        "truncated": False,        # the job log carries a compact copy when the full one is over LOG_LIMIT
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------- job log
# The flow can read the facts from the job log when it may not download the artifact.

LOG_LIMIT = 100_000           # characters of JSON in the log
LOG_BEGIN, LOG_END = "<<<ITEMATOR-JSON", "ITEMATOR-JSON>>>"


def _one_line(obj) -> str:
    """Compact ASCII JSON. '<' and '>' are escaped, so no name in the data can spell a marker."""
    return json.dumps(obj, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e")


def log_block(report: dict, limit: int = LOG_LIMIT) -> str:
    """The report between the markers. Over `limit`, a compact copy whose `truncated` names what was cut."""
    text = _one_line(report)
    if len(text) > limit:
        c = {**report, "extras": [{k: v for k, v in e.items() if k != "detail"} for e in report["extras"]]}
        cut = ["extras[].detail"]

        def size():
            return len(_one_line({**c, "truncated": cut}))
        for key in ("unplaced", "injection"):
            if size() > limit and len(c[key]) > 20:
                c[f"{key}_total"], c[key] = len(c[key]), c[key][:20]
                cut.append(f"{key}[20:]")
        if size() > limit:
            c["extras"] = [{k: v for k, v in e.items() if k != "plain_facts"} for e in c["extras"]]
            cut.append("extras[].plain_facts")
        n = len(c["extras"])
        while c["extras"] and size() > limit:
            c["extras"] = c["extras"][:len(c["extras"]) // 2]
        if len(c["extras"]) < n:
            c["extras_total"] = n
            cut.append(f"extras[{len(c['extras'])}:]")
        text = _one_line({**c, "truncated": cut})
    return f"{LOG_BEGIN}\n{text}\n{LOG_END}"


# ------------------------------------------------------------------- main

def run(env, repo_dir: str, http) -> dict:
    need = ("CI_API_V4_URL", "CI_PROJECT_ID", "CI_MERGE_REQUEST_IID", "CI_MERGE_REQUEST_DIFF_BASE_SHA")
    missing = [k for k in need if not env.get(k)]
    head = env.get("CI_MERGE_REQUEST_SOURCE_BRANCH_SHA") or env.get("CI_COMMIT_SHA")
    if missing or not head:
        raise JobError("not a merge request pipeline: missing " + ", ".join(missing or ["CI_COMMIT_SHA"]))
    pid, iid, base = env["CI_PROJECT_ID"], env["CI_MERGE_REQUEST_IID"], env["CI_MERGE_REQUEST_DIFF_BASE_SHA"]
    files = diff_files(repo_dir, base, head)
    api = Api(env["CI_API_V4_URL"], env.get("CI_JOB_TOKEN") or None, http)
    mr = api.get(f"/projects/{pid}/merge_requests/{iid}")
    description = mr.get("description") or env.get("CI_MERGE_REQUEST_DESCRIPTION") or ""
    warnings: list[str] = []
    issues, issues_from = linked_issues(api, pid, iid, description, warnings)
    return facts(mr_iid=int(iid), mr_title=mr.get("title") or env.get("CI_MERGE_REQUEST_TITLE") or "",
                 mr_description=description, mr_author_id=(mr.get("author") or {}).get("id"),
                 issues=issues, issues_from=issues_from, files=files, repo=env.get("CI_PROJECT_PATH"),
                 base_sha=base, head_sha=head, warnings=warnings,
                 now=datetime.datetime.now(datetime.timezone.utc))


def main(argv=None, env=None) -> int:
    p = argparse.ArgumentParser(prog="python -m itemator.ci", description=__doc__.split("\n")[0])
    p.add_argument("--out", default="itemator.json")
    p.add_argument("--repo", default=".", help="the git checkout (default: the current directory)")
    args = p.parse_args(argv)
    try:
        report = run(os.environ if env is None else env, args.repo, http_get)
    except JobError as e:
        print(f"itemator: {e}", file=sys.stderr)
        return 2
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    print(f"itemator: {report['state']}: {len(report['extras'])} extras, {len(report['unplaced'])} unplaced, "
          f"{len(report['injection'])} injection flags -> {args.out}")
    print(report["card"]["final_line"])
    print(report["card"]["todo_line"])
    print(log_block(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
