"""The CI job: compute Itemator's facts for one merge request and save itemator.json.

Run in a merge request pipeline as `python -m itemator.ci [--out itemator.json]`.
Standard library only. The job only reads: git, and the GitLab API, anonymously
first (the project is public) and with the job token only when that read is
refused, and, for each new dependency, its public registry and OSV (itemator/registry.py). It never writes to the merge request (the job token cannot); the Duo
flow reads itemator.json and posts the card.

Exit 0 whatever the facts say: they are information, not a merge condition.
Exit 2 when the job itself breaks: a missing CI variable, a git command or an
API read that fails. The message says which.

Inputs (GitLab's predefined variables): CI_API_V4_URL, CI_PROJECT_ID,
CI_PROJECT_PATH, CI_MERGE_REQUEST_IID, CI_MERGE_REQUEST_DIFF_BASE_SHA,
CI_COMMIT_SHA (or CI_MERGE_REQUEST_SOURCE_BRANCH_SHA in a merged results
pipeline, where CI_COMMIT_SHA is the merge commit), CI_JOB_TOKEN, CI_MERGE_REQUEST_TARGET_BRANCH_NAME; and from the
job script (T20) ITEMATOR_CHECKER ("base" when this code was exported from the target branch) and ITEMATOR_CHECKER_SHA.
The team policy (.itemator.toml, itemator/policy.py) is read from the tip of the target branch
(origin/<CI_MERGE_REQUEST_TARGET_BRANCH_NAME>, T26 F1), or from CI_MERGE_REQUEST_DIFF_BASE_SHA when that ref cannot be
resolved, and the card then says so. The diff always starts at CI_MERGE_REQUEST_DIFF_BASE_SHA.
"""
from __future__ import annotations

import argparse
import dataclasses
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
from itemator import policy as POL
from itemator import registry as RG
from itemator import said as SAID

STATES = ("inside_ask", "extras", "no_issue", "author_wrote_issue", "unplaced_only")
INJECTION_LINE = "This MR contains text addressed to automated reviewers; it was not followed."


class JobError(Exception):
    """The job could not compute the facts (not a finding about the MR)."""


# -------------------------------------------------------------------- git

_STATUS = {"A": "added", "D": "removed", "M": "modified", "R": "renamed", "C": "copied", "T": "changed"}


ATTR_SOURCE = True      # T26 B1: on git 2.40 or later, read .gitattributes from the base, never from the checkout
FIRST_FEW_BYTES = 8000  # git's own test for a binary file: a NUL among the first 8000 bytes
_DIFF = ("--find-renames", "--no-ext-diff", "--no-textconv")
_INDEX = re.compile(r"index ([0-9a-f]+)\.\.([0-9a-f]+)")


def _git(repo: str, *args: str, attr_source: str | None = None) -> bytes:
    """git with no attributes from outside the stored commits (T26 B1): no core.attributesFile, no system file and,
    with `attr_source` (honoured by git 2.40 or later), that commit's .gitattributes instead of the checkout's.
    $GIT_DIR/info/attributes cannot be switched off; diff_files does not trust git's word on "binary" anyway."""
    env = {**os.environ, "GIT_ATTR_NOSYSTEM": "1", "GIT_LITERAL_PATHSPECS": "1"}
    env.pop("GIT_ATTR_SOURCE", None)
    if attr_source:
        env["GIT_ATTR_SOURCE"] = attr_source
    try:
        r = subprocess.run(["git", "-c", "core.attributesFile=/dev/null", "-C", repo, *args], capture_output=True,
                           check=False, env=env)
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


def _binary_blobs(repo: str, oids) -> set:
    """The blobs among `oids` whose first FIRST_FEW_BYTES bytes hold a NUL: git's own test for a binary file, run on
    the stored blob, so no attribute changes the answer (T26 B1). One `git cat-file --batch`; the rest of each blob
    is read and dropped, never kept."""
    want = sorted({o for o in oids if o.strip("0")})
    if not want:
        return set()
    out = set()
    try:
        p = subprocess.Popen(["git", "-C", repo, "cat-file", "--batch"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            for oid in want:
                p.stdin.write(oid.encode("ascii") + b"\n")
                p.stdin.flush()
                meta = p.stdout.readline().split()
                if len(meta) != 3 or not meta[2].isdigit():
                    continue                      # "<oid> missing": a submodule's commit, not a blob here
                size = int(meta[2])
                first = p.stdout.read(min(size, FIRST_FEW_BYTES))
                left = size - len(first) + 1      # the rest of the blob and the newline after it
                while left > 0:
                    piece = p.stdout.read(min(left, 1 << 20))
                    if not piece:
                        break
                    left -= len(piece)
                if b"\0" in first:
                    out.add(oid)
        finally:
            p.stdin.close()
            p.stdout.close()
            p.wait()
    except OSError as e:
        raise JobError(f"git cat-file could not run: {e}") from e
    return out


def _patches(text: bytes) -> list[str]:
    return [c for c in re.split(r"(?m)^(?=diff --git )", text.decode("utf-8", "replace")) if c.startswith("diff --git ")]


def diff_files(repo: str, base: str, head: str) -> list[dict]:
    """`git diff --find-renames base head` as the file list extras() takes (GitHub's field names).

    T26 B1: attributes the merge request controls (.gitattributes at any depth, and on git before 2.40 every
    attribute file) can make git print "Binary files differ" for a text file, or a text patch for a binary. So a file
    is binary here only when one of its stored blobs fails git's own test, and a text file git called binary is
    diffed again with --text."""
    src = base if ATTR_SOURCE else None
    raw = _git(repo, "diff", *_DIFF, "--name-status", "-z", base, head, attr_source=src).split(b"\0")
    entries, i = [], 0
    while i < len(raw) and raw[i]:
        code = raw[i].decode()[0]
        if code in "RC":
            old, new, i = raw[i + 1], raw[i + 2], i + 3
        else:
            old = new = raw[i + 1]
            i += 2
        entries.append((code, old.decode("utf-8", "replace"), new.decode("utf-8", "replace")))
    chunks = _patches(_git(repo, "diff", *_DIFF, "--no-color", "--full-index", "-p", base, head, attr_source=src))
    if len(chunks) != len(entries):
        raise JobError(f"git diff listed {len(entries)} files but printed {len(chunks)} patches")
    sizes = {}
    if any(code == "A" for code, _, _ in entries):
        for row in _git(repo, "ls-tree", "-r", "-l", "-z", head).split(b"\0"):
            meta, _, path = row.partition(b"\t")
            parts = meta.split()
            if len(parts) == 4 and parts[3].isdigit():
                sizes[path.decode("utf-8", "replace")] = int(parts[3])
    parsed = [_hunk_lines(c) for c in chunks]
    blobs = [next((m.groups() for m in map(_INDEX.match, header) if m), ()) for header, _ in parsed]
    binary = _binary_blobs(repo, [o for pair in blobs for o in pair])
    files = []
    for (code, old, new), (header, hunks), pair in zip(entries, parsed, blobs):
        is_binary = any(o in binary for o in pair)
        if not is_binary and any(line.startswith("Binary files ") for line in header):
            again = _patches(_git(repo, "diff", *_DIFF, "--no-color", "--text", "-p", base, head, "--",
                                  *dict.fromkeys((old, new)), attr_source=src))
            if len(again) != 1:
                raise JobError(f"git diff --text printed {len(again)} patches for one file")
            header, hunks = _hunk_lines(again[0])
        if is_binary:
            hunks = None
        f = {"filename": new, "status": _STATUS.get(code, "modified"),
             "patch": "\n".join(hunks) + "\n" if hunks else None,
             "additions": sum(1 for line in hunks or () if line.startswith("+")),
             "deletions": sum(1 for line in hunks or () if line.startswith("-"))}
        if code in "RC":
            f["previous_filename"] = old
        if is_binary:
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
          "build_output_added": "build output", "stray_file": "stray file", "policy_changed": "team policy change",
          "agent_instructions": "agent instructions",
          "whitespace_only": "whitespace only"}
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
           "build_output_added": "build output directories", "stray_file": "stray file entries",
           "policy_changed": "team policy changes", "whitespace_only": "whitespace-only groups",
           "agent_instructions": "agent instruction extras"}


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
               author_wrote: bool = False, notes: tuple = ()) -> dict:
    """`notes` (T20): more visible sentences for the caveat line (where the checker came from, the team policy)."""
    refs = ", ".join(i["ref"] for i in issues)
    if state == "no_issue":
        final, todo = "No one described this change.", "Link the issue it answers, or say why it needs none."
    elif state == "author_wrote_issue":
        final, todo = AUTHOR_CAVEAT, f"A second person reads {refs} before approving."
    elif state == "extras":
        names = ", ".join(f"{_code(e.name)} ({_label(e)})" for e in extras)
        final = f"{len(extras)} {'thing' if len(extras) == 1 else 'things'} beyond {refs}: {names}."
        todo = 'Type each name in its thread to keep it, or reply "split" to move it to its own MR, "remove" to drop it.'
    elif state == "unplaced_only":
        n = len(unplaced)
        final = f"{n} {'file' if n == 1 else 'files'} the rules could not place."
        todo = "Skim this file." if n == 1 else f"Skim these {n} files."
    else:
        final, todo = f"Nothing beyond {refs}.", "Approve as usual."
    caveat = AUTHOR_CAVEAT if author_wrote and state in ("extras", "unplaced_only", "inside_ask") else None
    caveat = " ".join(c for c in (caveat, *notes) if c) or None
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


_UNTYPED = re.compile(r"[`\x00-\x1f\x7f-\x9f]")


def shown_name(name: str) -> str:
    """The name as the stub and the card show it, and as the approver types it (T22, T21 FIX 2): each backtick or
    control character becomes an apostrophe, so the text between the first pair of backticks is always the whole name."""
    return _UNTYPED.sub("'", name)


def _code(text: str) -> str:
    """An inline code span on one line, for a name."""
    return f"`{shown_name(text)}`"


OTHER_PERSON = "A reply from the merge request author does not count."
MAX_LISTED = 1000       # characters of package names a grouped dependency thread lists; past it, no split or remove (T26 B2)
_MANIFEST = re.compile(r"pyproject\.toml|package\.json|requirements(?:-[^/]*)?\.txt|go\.mod|Cargo\.toml|Gemfile")
_CONFIG_EXT = (".yml", ".yaml", ".toml", ".json", ".cfg", ".ini")
_ADDED_KINDS = ("stray_file", "binary_or_large_added", "build_output_added", "agent_instructions")   # T37: an added
# agent instruction file named by its path can be removed; a modified, deleted or grouped one offers neither (the flow
# refuses whole-file and multi-file edits of existing files)


def _manifest(path: str) -> bool:
    return bool(_MANIFEST.fullmatch(posixpath.basename(path)))


def _config_file(path: str) -> bool:
    name = posixpath.basename(path)
    return not _manifest(path) and (
        name in (".gitlab-ci.yml", "Dockerfile") or name.startswith("Dockerfile.") or name.endswith(_CONFIG_EXT))


ALWAYS = ("To keep it and stop asking about this file, reply `always`; that opens a merge request that changes the "
          "team policy.")
# T40: `always` keeps the extra and opens a merge request (react Step 5b) that adds its path to ignore.paths in the
# target branch's .itemator.toml, so later merge requests stop asking. A path there quiets every quietable extra on
# that exact file, so it is offered only where that is narrow and safe to write: a CI/config or stray file named by its
# path, one file and not a group; never a package manifest (it would quiet later dependencies and version bumps); a path
# fnmatch reads literally (no * ? [ ] ! { }) and TOML needs no escape for (no quote, backslash, space or backtick), at
# most 120 characters; never a kind the policy cannot quiet; and only while the target branch's policy file was read,
# used and has room for one more path (always_allowed), so the flow has a valid file and line to extend.
ALWAYS_KINDS = ("ci_or_config", "stray_file")
ALWAYS_PATH = re.compile(r"[A-Za-z0-9._/@+-]{1,120}")


def always_allowed(policy: dict | None) -> bool:
    """T40: from the `policy` object of itemator.json (Policy.to_dict): the file was found on the target branch tip,
    used (no reason it was ignored) and lists fewer than MAX_PATTERNS paths. Missing, invalid or read from the merge
    base: `always` is not offered."""
    return bool(policy and policy.get("found") is True and policy.get("ignored") is None
                and policy.get("paths_line_ok") is True                 # T42: the flow can make the one-line edit
                and policy.get("source") == "target_branch"
                and len((policy.get("active") or {}).get("ignore_paths") or ()) < POL.MAX_PATTERNS)


def can_always(e, items: tuple = ()) -> bool:
    return (e.kind in ALWAYS_KINDS and e.kind not in POL.NEVER_IGNORED and e.name == e.path and not e.detail
            and not items and bool(ALWAYS_PATH.fullmatch(e.path)) and not _manifest(e.path))


def answers(e, items: tuple, by_path: dict, always: bool = False) -> tuple:
    """`split` and `remove` where the react flow accepts them (_split_remove), then `always` (T40) when the target
    branch's policy file can take one more path (`always`, from always_allowed) and the extra qualifies (can_always)."""
    offers = _split_remove(e, items, by_path)
    return (*offers, "always") if always and can_always(e, items) else offers


def _split_remove(e, items: tuple, by_path: dict) -> tuple:
    """Which of `split` and `remove` the react flow accepts for this extra (its Step 5a part 3), so a stub never
    offers what the flow would refuse (T26 F4): both for a CI or config file named by its path, and for a manifest
    dependency alone or in a group whose thread lists every package (B2: the flow checks each changed line against
    that list); `remove` alone for a file this merge request adds (T37: an agent instruction file too)."""
    if e.kind == "ci_or_config" and e.name == e.path and not e.detail and _config_file(e.path):
        return ("split", "remove")
    if e.kind == "new_dependency" and _manifest(e.path) and (
            not e.detail or (items and len(", ".join(shown_name(i.name) for i in items)) <= MAX_LISTED)):
        return ("split", "remove")
    if e.kind in _ADDED_KINDS and e.name == e.path and (by_path.get(e.path) or {}).get("status") == "added":
        return ("remove",)
    return ()


def thread_stub(e, registry_line: str | None = None, other_person: bool = False,
                offers: tuple = ("split", "remove"), said: str | None = None) -> str:
    """The opening text of the extra's thread; the flow may post it as it is. `registry_line` (T17): the sentence of
    registry facts for a new dependency, placed before the replies. `other_person` (T20, names.other_person_required):
    OTHER_PERSON before the replies, as visible text, because the react flow cannot read markdown comments.
    `offers` (T26 F4, from answers()): which of `split`, `remove` and `always` (T40) it names; the default names split and remove. `said` (T35,
    said.said): one of three fixed sentences on whether the MR's own text names the extra, never the author's words."""
    why = shown_name(e.why).strip()
    if not why.endswith((".", "!", "?")):
        why += "."
    facts = f" {registry_line}" if registry_line else ""
    facts += f" {SAID.SENTENCE[said]}" if said else ""
    facts += f" {OTHER_PERSON}" if other_person else ""
    split = "To move it into its own MR, reply `split`. " if "split" in offers else ""
    remove = "To drop it from this MR, reply `remove`. " if "remove" in offers else ""
    always = f"{ALWAYS} " if "always" in offers else ""
    return (f"{_code(e.name)} ({_label(e)}): {why}{facts} To keep it, reply with its exact name. "
            f"{split}{remove}{always}If this is not really an extra, reply `not an extra`.")


def describe_extra(e, by_path: dict, items: tuple = (), registry: dict | None = None, other_person: bool = False,
                   said: str | None = None, always: bool = False) -> dict:
    """A grouped extra (`items`, from group_extras) anchors where its first item does, and keeps every item in
    plain_facts.detail. `registry` (T17, from registry.look_up) goes to plain_facts and its sentence to the stub."""
    anchor, reason = anchor_for(items[0] if items else e, by_path)
    plain = {"kind": e.kind, "name": shown_name(e.name), "why": e.why, "detail_count": len(e.detail), "path": e.path}
    if items:
        plain["detail"] = [i.to_dict() for i in items]
    if registry is not None:
        plain["registry"] = registry
    if said:
        plain["said"] = said
    rec = {**e.to_dict(), "detail": list(e.detail), "anchor": anchor, "anchorless_reason": reason,
           "thread_stub": thread_stub(e, RG.sentence(registry), other_person, answers(e, items, by_path, always), said),
           "plain_facts": plain}
    if rec["name"] != plain["name"]:          # T22: `name` is what the approver sees and types; `raw_name` is the manifest's
        rec["name"], rec["raw_name"] = plain["name"], e.name
    return rec


# ---------------------------------------------------------------- team policy and checker (T20)

CHECKER_CAVEAT = "These facts come from this merge request's own copy of the checker, not the target branch's."
TARGET_CAVEAT = ("The target branch could not be read in this job, so the team policy and the checker come from the "
                 "commit this branch started from.")
ASKS_OTHER = "The team policy asks for someone other than the author to name each extra."
AT_TARGET, AT_FORK = "on the target branch", "at the commit this branch started from"
_SHOWN_QUIETED = 10
_SHA40 = re.compile(r"[0-9a-f]{40}")


def target_tip(repo: str, env, base: str) -> tuple[str, bool]:
    """(sha, True): the tip of the target branch, refs/remotes/origin/<CI_MERGE_REQUEST_TARGET_BRANCH_NAME> in the
    checkout, where the team policy is read (T26 F1: the merge base is the author's choice, so a branch cut before a
    stricter policy would be judged by the old one). (base, False) when that ref does not resolve to a full sha."""
    name = env.get("CI_MERGE_REQUEST_TARGET_BRANCH_NAME") or ""
    if name:
        try:
            sha = _git(repo, "rev-parse", "-q", "--verify", f"refs/remotes/origin/{name}^{{commit}}")
        except JobError:
            sha = b""
        sha = sha.decode("ascii", "replace").rstrip("\n")
        if _SHA40.fullmatch(sha):
            return sha, True
    return base, False


def policy_edit(files: list[dict], at: str = AT_TARGET):
    """A `policy_changed` extra when the merge request adds, edits, renames or deletes the team policy file: it
    always needs a name, and this merge request is still judged by the target branch's copy."""
    for f in files:
        if POL.FILE in (f["filename"], f.get("previous_filename")):
            return X.Extra("policy_changed", f["filename"], POL.FILE,
                           f"changes the team policy file {POL.FILE}; this merge request is still judged by the "
                           f"copy {at}")
    return None


def policy_note(policy, quieted: list, at: str = AT_TARGET, asks_other: bool = False) -> str | None:
    """The visible sentences about the team policy: why it was not used, what it quieted, a pattern that ignores
    every path, and (T26 F8) that someone other than the author must name each extra still open."""
    if policy is None:
        return None
    if policy.ignored:
        return f"The team policy file {POL.FILE} {at} was not used: {policy.ignored}."
    out = []
    if quieted:
        n = len(quieted)
        shown = ", ".join(f"{_code(e.name)} ({_label(e)})" for e in quieted[:_SHOWN_QUIETED])
        more = f", and {n - _SHOWN_QUIETED} more" if n > _SHOWN_QUIETED else ""
        out.append(f"The team policy ({POL.FILE} {at}) quieted {n} "
                   f"{'extra' if n == 1 else 'extras'}: {shown}{more}.")
    every = [p for p in policy.paths if POL.matches_everything(p)]
    if every:
        out.append("The team policy ignores every path (" + ", ".join(_code(p) for p in every) + ").")
    if asks_other:
        out.append(ASKS_OTHER)
    return " ".join(out) or None


def checker_of(env, target: str, head: str) -> dict:
    """Where the code computing these facts came from: "base" only when the job script says it exported it from
    `target` (target_tip: the target branch tip, or the merge base when that cannot be read)."""
    if env.get("ITEMATOR_CHECKER") == "base" and env.get("ITEMATOR_CHECKER_SHA") == target:
        return {"source": "base", "sha": target}
    return {"source": "merge_request", "sha": head}


def facts(*, mr_iid: int, mr_title: str, mr_description: str, mr_author_id, issues: list[dict],
          issues_from: str, files: list[dict], repo: str | None, base_sha: str, head_sha: str,
          warnings: list, now: datetime.datetime, registry_fetch=None, policy=None, checker=None,
          fallback: bool = False, description_cut: bool = False) -> dict:
    """`policy` (T20, policy.read; None when not read) quiets extras and sets who may name one; `checker`
    (checker_of) says where this code came from; `fallback` (T26 F1): the target branch could not be read, so
    both came from the merge base, and the card says so. `description_cut` (T35): the description may be truncated,
    so no thread says it does not mention an extra."""
    at = AT_FORK if fallback else AT_TARGET
    issue_text = "\n\n".join(f"{i['title']}\n{i['description']}" for i in issues)
    analysis = X.analyse(issue_text, files, repo=repo)
    state = decide_state(issues, mr_author_id, analysis)
    found = [] if state == "no_issue" else analysis.extras      # no ask, so nothing is "beyond" it
    unplaced = [] if state == "no_issue" else analysis.unplaced
    edit = policy_edit(files, at)       # T41: a change to the team policy always asks for a typed name, also when no
    if edit:                            # issue describes it (the policy merge request `always` opens has none)
        # it replaces an extra the rules found on that one file (an added policy is a stray_file); with no issue there
        # is no ask, so nothing else is "beyond" it and the policy edit is the only extra
        found = [e for e in found if not e.name == e.path == edit.path] + [edit]
        unplaced = [u for u in unplaced if u != edit.path]
    grouped = group_extras(found)
    by_path = {f["filename"]: f for f in files}
    registry = RG.look_up(grouped, by_path, registry_fetch, now) if registry_fetch else [None] * len(grouped)
    kept, quieted = [], []
    for (e, items), r in zip(grouped, registry):
        why = POL.why_ignored(policy, e, items, r, by_path) if policy else None
        if why:
            quieted.append((e, why))
        else:
            kept.append(((e, items), r))
    if state != "no_issue":
        state = decide_state(issues, mr_author_id, X.Analysis([e for (e, _), _ in kept], unplaced=unplaced))
    said = SAID.said(mr_title, mr_description, [SAID.names(e.name, e.path, e.detail) for (e, _), _ in kept],
                     cut=description_cut)             # T35: the extras the description does not mention come first
    ranked = sorted(zip(said, kept), key=lambda p: p[0] != SAID.SILENT)
    said, kept = [s for s, _ in ranked], [k for _, k in ranked]
    injection = scan_injection(mr_title, mr_description, issues, files)
    other = bool(policy and policy.other_person_required)
    always = always_allowed(policy.to_dict() if policy else None)       # T40
    notes = (CHECKER_CAVEAT if checker and checker["source"] != "base" else None,
             TARGET_CAVEAT if fallback else None,
             policy_note(policy, [e for e, _ in quieted], at, asks_other=other and bool(kept)))
    report = {
        "rules_version": X.RULES_VERSION,
        "mr_iid": mr_iid,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "issue_iids": [i["iid"] for i in issues],
        "issues_from": issues_from,
        "state": state,
        "extras": [describe_extra(e, by_path, items, r, other, s, always) for ((e, items), r), s in zip(kept, said)],
        "unplaced": list(unplaced),
        "injection": injection,
        "card": card_lines(state, issues, [e for (e, _), _ in kept], unplaced, injection,
                           _author_wrote(issues, mr_author_id), notes),
        "warnings": warnings,
        "truncated": False,        # the job log carries a compact copy when the full one is over LOG_LIMIT
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if policy is not None:
        report["policy"] = {**policy.to_dict(), "ignored_extras": [
            {"name": shown_name(e.name), "kind": e.kind, "why": why} for e, why in quieted]}
    if checker is not None:
        report["checker"] = checker
    return report


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
        quiet = (c.get("policy") or {}).get("ignored_extras") or []
        if size() > limit and len(quiet) > 20:          # T20
            c["policy"] = {**c["policy"], "ignored_extras": quiet[:20], "ignored_extras_total": len(quiet)}
            cut.append("policy.ignored_extras[20:]")
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

def run(env, repo_dir: str, http, registry_fetch=None) -> dict:
    need = ("CI_API_V4_URL", "CI_PROJECT_ID", "CI_MERGE_REQUEST_IID", "CI_MERGE_REQUEST_DIFF_BASE_SHA")
    missing = [k for k in need if not env.get(k)]
    head = env.get("CI_MERGE_REQUEST_SOURCE_BRANCH_SHA") or env.get("CI_COMMIT_SHA")
    if missing or not head:
        raise JobError("not a merge request pipeline: missing " + ", ".join(missing or ["CI_COMMIT_SHA"]))
    pid, iid, base = env["CI_PROJECT_ID"], env["CI_MERGE_REQUEST_IID"], env["CI_MERGE_REQUEST_DIFF_BASE_SHA"]
    try:
        files = diff_files(repo_dir, base, head)
    except JobError as e:
        try:
            _git(repo_dir, "cat-file", "-e", f"{base}^{{commit}}")
        except JobError:
            raise JobError(f"{e}; the base commit is not in this clone (a shallow clone? set GIT_DEPTH to 0)") from e
        raise
    api = Api(env["CI_API_V4_URL"], env.get("CI_JOB_TOKEN") or None, http)
    mr = api.get(f"/projects/{pid}/merge_requests/{iid}")
    description = mr.get("description") or env.get("CI_MERGE_REQUEST_DESCRIPTION") or ""
    # T35: the API gives the whole description. CI_MERGE_REQUEST_DESCRIPTION, the fallback, is cut by GitLab (to 2700
    # characters, per GitLab's CI variable docs; not re-checked offline), so a description from it never says silent.
    cut = not mr.get("description") and bool(description)
    warnings: list[str] = []
    issues, issues_from = linked_issues(api, pid, iid, description, warnings)
    target, resolved = target_tip(repo_dir, env, base)
    policy = POL.read(repo_dir, target)       # T20, T26 F1: from the target branch tip, never from the merge request
    if not resolved:
        policy = dataclasses.replace(policy, source="merge_base")
    report = facts(mr_iid=int(iid), mr_title=mr.get("title") or env.get("CI_MERGE_REQUEST_TITLE") or "",
                 mr_description=description, mr_author_id=(mr.get("author") or {}).get("id"),
                 issues=issues, issues_from=issues_from, files=files, repo=env.get("CI_PROJECT_PATH"),
                 base_sha=base, head_sha=head, warnings=warnings,
                 now=datetime.datetime.now(datetime.timezone.utc), registry_fetch=registry_fetch,
                 policy=policy, checker=checker_of(env, target, head), fallback=not resolved, description_cut=cut)
    report["hold"] = hold(report, api, pid, iid, head)
    if report["hold"]["blocked"]:
        report["card"]["todo_line"] = f'{report["card"]["todo_line"]} {HOLD_LINE}'
    return report


REACT_PREFIX = "ai-itemator-react"
HOLD_LINE = ("This project holds the pipeline until every extra is named: after the last name, retry the `itemator` job.")
_NAMED_MARK = "itemator:named="


def hold(report: dict, api, pid, iid, head: str) -> dict:
    """T44: with `names.hold_until_named` in the target branch's policy, the job fails while a kept extra has no name, so
    a merge armed inside the pipeline (the organisers' reference loop) cannot go through before the card exists. It
    passes when the reaction account has posted its summary for this exact head commit (the summary is posted only
    when every extra has an answer). Only a note by an account whose name starts with `ai-itemator-react` counts, and
    a note that cannot be read counts as not named: the hold fails closed."""
    if not (report.get("policy") or {}).get("active", {}).get("hold_until_named") or not report["extras"]:
        return {"enabled": bool((report.get("policy") or {}).get("active", {}).get("hold_until_named")), "blocked": False}
    named, why = False, "no summary note for this commit yet"
    try:
        for page in (1, 2, 3):
            notes = api.get(f"/projects/{pid}/merge_requests/{iid}/notes?per_page=100&page={page}&sort=desc", missing_ok=True)
            if not isinstance(notes, list):
                why = "the notes could not be read"
                break
            for n in notes:
                who = str((n.get("author") or {}).get("username", ""))
                if not n.get("system") and who.startswith(REACT_PREFIX) and f"{_NAMED_MARK}{head}" in str(n.get("body", "")):
                    named = True
            if named or len(notes) < 100:
                break
    except JobError:
        named, why = False, "the notes could not be read"
    return {"enabled": True, "blocked": not named, "reason": None if named else why}


def main(argv=None, env=None, registry_fetch=None) -> int:
    p = argparse.ArgumentParser(prog="python -m itemator.ci", description=__doc__.split("\n")[0])
    p.add_argument("--out", default="itemator.json")
    p.add_argument("--repo", default=".", help="the git checkout (default: the current directory)")
    args = p.parse_args(argv)
    try:
        report = run(os.environ if env is None else env, args.repo, http_get, registry_fetch or RG.fetch)
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
    if report.get("hold", {}).get("blocked"):
        print(f"itemator: held: {len(report['extras'])} extras are not named yet ({report['hold']['reason']}). "
              f"{HOLD_LINE}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
