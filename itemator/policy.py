"""The team policy file (T20): `.itemator.toml` at the repository root, read from the tip of the target branch
(ci.target_tip, T26 F1; the merge base when that ref cannot be read, and the card says so), never from the merge
request, so a merge request cannot weaken the rules it is judged by. A merge request that edits the file gets a `policy_changed` extra instead (itemator/ci.py).

    [names]
    other_person_required = true      # a name typed by the merge request author does not count
    asker_required = true             # only the person who wrote the linked issue can keep an extra (T45)
    [ignore]
    kinds = ["version_bump"]          # extras of these kinds never need a name
    paths = ["docs/**", "*.md"]       # extras whose files all match one of these never need a name
    [reasons]                         # optional; one line of why per ignore entry (the entry text is the key)
    version_bump = "we release by script and review the bump there"
    "docs/**" = "documentation is reviewed by the docs team"

The policy can only quiet extras or tighten who may name one; it never adds an extra. Patterns are fnmatch
style, case-sensitive, and `*` crosses `/`. The schema is strict: an unknown table or key, a wrong type, an
unknown kind or a bad pattern makes the whole file ignored, with the reason on the card. Nothing here raises.
Standard library only.
"""
from __future__ import annotations

import fnmatch
import re
import subprocess
import tomllib
from dataclasses import dataclass

from itemator import extras as X

FILE = ".itemator.toml"
MAX_BYTES = 64 * 1024
MAX_PATTERNS = 20
MAX_PATTERN_CHARS = 200
MAX_REASON_CHARS = 200
TIMEOUT = 10            # seconds per git call
SCHEMA = {"names": {"other_person_required": bool, "hold_until_named": bool, "asker_required": bool}, "ignore": {"kinds": list, "paths": list}}

# Built-in exceptions: no policy quiets these.
# - policy_changed: the merge request edits the rules the next merge requests are judged by.
# - binary_or_large_added: nobody can read a binary or a huge file in review, so a name is the only sign
#   that someone looked.
# - agent_instructions (T37): a file that changes what coding agents are told or may use; a policy that hid it would
#   let the next agent change its own instructions unseen.
# A new dependency is quieted only when the registry found every package (why_ignored): one the registry does not
# know may be a typo or a name taken by someone else; one whose facts could not be read (past the lookup cap, an
# invalid name, a network error) proves nothing; and (T26 B3) neither does a URL, git or local-path source or an
# ecosystem with no lookup (go, gem, maven, gradle). The only exception is the package the merge request declares
# itself (reason own_package).
NEVER_IGNORED = ("policy_changed", "binary_or_large_added", "agent_instructions")

_SHA = re.compile(r"[0-9a-f]{40}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_UNSAFE = re.compile(r"[`\x00-\x1f\x7f-\x9f]")
_AT = re.compile(r"\(at line (\d+), column (\d+)\)\s*$")
_PROBES = ("a", "a/b/c.d", ".x", "-", "Dockerfile")
TOO_DEEP = "it is nested too deeply or is too complex to read"


def _clean(value) -> str:
    """A piece of the file shown in a reason: one line, no backtick, at most 40 characters."""
    return _UNSAFE.sub("'", str(value))[:40]


def matches_everything(pattern: str) -> bool:
    """A pattern that matches every sample path (`*`, `**`, `?*`, `*[!/]*`, ...; fnmatch's `*` crosses `/`): probed,
    not read, so no spelling hides it (T26 F7)."""
    return all(fnmatch.fnmatchcase(p, pattern) for p in _PROBES)


@dataclass(frozen=True)
class Policy:
    sha: str | None = None
    source: str = "target_branch"       # or "merge_base" when the target branch could not be read (T26 F1)
    found: bool = False
    ignored: str | None = None          # why the file was not used; the defaults apply
    other_person_required: bool = False
    hold_until_named: bool = False      # T44: the itemator job fails while an extra has no name (see ci.hold)
    asker_required: bool = False        # T45: only the linked issue's author can keep an extra (see ci.asker_usernames)
    kinds: tuple = ()
    paths: tuple = ()
    reasons: tuple = ()                 # ((ignore entry, why), ...) from the optional [reasons] table; `lint` reads it, no extra depends on it
    paths_line_ok: bool = False         # T42: the react flow can extend the file with a one-line edit (see paths_line_ok)

    def to_dict(self) -> dict:
        return {"source": self.source, "sha": self.sha, "file": FILE, "found": self.found, "ignored": self.ignored,
                "paths_line_ok": self.paths_line_ok,
                "active": {"other_person_required": self.other_person_required, "hold_until_named": self.hold_until_named,
                           "asker_required": self.asker_required, "ignore_kinds": list(self.kinds),
                           "ignore_paths": list(self.paths),
                           "ignores_every_path": [p for p in self.paths if matches_everything(p)]}}


_PATHS_LINE = re.compile(r" *paths = \[([^#\[\]\n]*)\][^\n]*")        # no # and no bracket inside the list: "*.[ch]" would make its end ambiguous


def paths_line_ok(text: str) -> bool:
    """T42: the react flow's `always` edits one line, so it needs exactly one line in the [ignore] table that starts
    (after spaces) with `paths = [` and closes the list on the same line, with no # in the list and no trailing comma,
    and that line must occur once in the whole file. Anything else (`paths=[]`, a list over several lines, no [ignore]
    table, dotted keys) is valid TOML that the flow refuses, so the offer is not made (the audit's fix 6)."""
    lines = text.split("\n")
    start = next((i for i, ln in enumerate(lines) if ln == "[ignore]"), None)
    if start is None:
        return False
    table = []
    for ln in lines[start + 1:]:
        if ln.startswith("["):
            break
        table.append(ln)
    hits = [ln for ln in table if re.match(r" *paths = \[", ln)]
    if len(hits) != 1:
        return False
    m = _PATHS_LINE.fullmatch(hits[0])
    return bool(m) and not m.group(1).rstrip().endswith(",") and text.count(hits[0]) == 1


def parse(data: bytes):
    """The settings ({"other_person_required", "hold_until_named", "asker_required", "kinds", "paths"}), or the reason the whole file is ignored. A file
    nested too deeply for the parser is a reason too, never a crash (T26 F2)."""
    try:
        return _parse(data)
    except (RecursionError, MemoryError, OverflowError, ValueError):
        return TOO_DEEP


def _parse(data: bytes):
    if len(data) > MAX_BYTES:
        return f"it is larger than {MAX_BYTES // 1024} KB"
    try:
        doc = tomllib.loads(data.decode("utf-8"))
    except UnicodeDecodeError:
        return "it is not UTF-8 text"
    except tomllib.TOMLDecodeError as e:          # only where, never the parser's words: they quote the file (T26 F9)
        m = _AT.search(str(e))
        where = f"line {m.group(1)}, column {m.group(2)}" if m else "at the end of the file"
        return f"it is not valid TOML ({where})"
    for table, value in doc.items():
        if table not in SCHEMA and table != "reasons":
            return f"unknown table `{_clean(table)}`"
        if not isinstance(value, dict):
            return f"{table} must be a table"
        for key, v in value.items():
            if table == "reasons":
                continue
            want = SCHEMA[table].get(key)
            if want is None:
                return f"unknown key {table}.`{_clean(key)}`"
            if type(v) is not want:
                return f"{table}.{key} must be " + ("true or false" if want is bool else "a list")
    names, ignore = doc.get("names", {}), doc.get("ignore", {})
    kinds, paths = ignore.get("kinds", []), ignore.get("paths", [])
    for k in kinds:
        if k in NEVER_IGNORED:
            return f"ignore.kinds lists {k}, which is never ignored"
        if type(k) is not str or k not in X.KINDS:
            return f"ignore.kinds lists an unknown kind `{_clean(k)}`"
    if len(paths) > MAX_PATTERNS:
        return f"ignore.paths has {len(paths)} patterns; at most {MAX_PATTERNS}"
    for p in paths:
        if type(p) is not str or not p:
            return "ignore.paths must list non-empty strings"
        if _CONTROL.search(p):
            return "an ignore.paths pattern contains a control character"
        if len(p) > MAX_PATTERN_CHARS:
            return f"an ignore.paths pattern is longer than {MAX_PATTERN_CHARS} characters"
    reasons = doc.get("reasons", {})
    for key, why in reasons.items():
        if key not in kinds and key not in paths:
            return f"reasons names `{_clean(key)}`, which is not an ignore entry"
        if type(why) is not str or not why.strip():
            return f"the reason for `{_clean(key)}` must be a non-empty string"
        if _CONTROL.search(why) or len(why) > MAX_REASON_CHARS:
            return f"the reason for `{_clean(key)}` has a control character or is longer than {MAX_REASON_CHARS} characters"
    return {"other_person_required": names.get("other_person_required", False),
            "hold_until_named": names.get("hold_until_named", False),
            "asker_required": names.get("asker_required", False), "kinds": tuple(kinds),
            "paths": tuple(paths), "reasons": tuple(reasons.items())}


class _Unreadable(Exception):
    pass


def _git(repo: str, *args: str) -> bytes:
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, check=False, timeout=TIMEOUT)
    except subprocess.TimeoutExpired as e:
        raise _Unreadable(f"git {args[0]} timed out") from e
    except OSError as e:
        raise _Unreadable(f"git {args[0]} could not start") from e
    if r.returncode != 0:
        raise _Unreadable(f"git {args[0]} failed")
    return r.stdout


def read(repo: str, sha) -> Policy:
    """The policy at commit `sha` of the checkout `repo`. A missing file gives the defaults; a file that cannot be
    used gives the defaults and the reason."""
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        return Policy(ignored="the target commit is not a 40-character sha")
    try:
        listing = _git(repo, "ls-tree", "-l", "-z", sha, "--", FILE)
        meta, _, path = listing.split(b"\0")[0].partition(b"\t")
        if path != FILE.encode():
            return Policy(sha=sha)
        mode, kind, oid, size = (meta.split() + [b""] * 4)[:4]
        if kind != b"blob" or mode not in (b"100644", b"100755") or not _SHA.fullmatch(oid.decode("ascii", "replace")):
            return Policy(sha=sha, found=True, ignored="it is not a regular file")
        if not size.isdigit() or int(size) > MAX_BYTES:
            return Policy(sha=sha, found=True, ignored=f"it is larger than {MAX_BYTES // 1024} KB")
        data = _git(repo, "cat-file", "blob", oid.decode("ascii"))
    except _Unreadable as e:
        return Policy(sha=sha, found=False, ignored=f"it could not be read ({e})")
    settings = parse(data)
    if isinstance(settings, str):
        return Policy(sha=sha, found=True, ignored=settings)
    return Policy(sha=sha, found=True, paths_line_ok=paths_line_ok(data.decode("utf-8")), **settings)


# ---------------------------------------------------------------- which extras it quiets

def _registry_knows_every_package(registry) -> bool:
    if not registry or not registry.get("packages") or registry.get("count") != len(registry["packages"]):
        return False
    return all((p.get("lookup") == "ok" and p.get("found") is True)
               or (p.get("lookup") == "not_from_registry" and p.get("reason") == "own_package")
               for p in registry["packages"])


def _files(e, items, by_path: dict) -> set[str]:
    """Every path an extra stands for, with the old path of a renamed file."""
    if items:
        paths = [i.path for i in items]
    elif e.detail and (e.path.endswith("/") or e.kind == "version_bump"):    # the detail lists files (ci._label)
        paths = list(e.detail)
    else:
        paths = [e.path]
    out = set(paths)
    for p in paths:
        old = (by_path.get(p) or {}).get("previous_filename")
        if old:
            out.add(old)
    return out


def why_ignored(policy: Policy, e, items, registry, by_path: dict) -> str | None:
    """Why the policy quiets this extra (one of ci.group_extras, with its registry facts), or None."""
    if e.kind in NEVER_IGNORED:
        return None
    if e.kind == "new_dependency" and not _registry_knows_every_package(registry):
        return None
    if e.kind in policy.kinds:
        return f"ignore.kinds lists {e.kind}"
    if not policy.paths:
        return None
    files = _files(e, items, by_path)
    if not all(any(fnmatch.fnmatchcase(f, g) for g in policy.paths) for f in files):
        return None
    used = [g for g in policy.paths if any(fnmatch.fnmatchcase(f, g) for f in files)]
    return "its files match ignore.paths " + ", ".join(f"`{_clean(g)}`" for g in used)


# ---------------------------------------------------------------- the lint (itemator.local --lint-policy)

def lint(data: bytes, tracked: list[str]) -> list[str]:
    """What is wrong with a policy file, one plain sentence each; [] when nothing is. `tracked`: the repository's files.
    Checked: the file is usable, every ignore entry has a reason, no path pattern is dead (matches no file), none matches
    every path. Nothing here changes what the rules do; it only tells the team what to tidy."""
    settings = parse(data)
    if isinstance(settings, str):
        return [f"{FILE} would be ignored: {settings}"]
    said = dict(settings["reasons"])
    out = [f"ignore entry `{_clean(e)}` has no reason; add it under [reasons]" for e in (*settings["kinds"], *settings["paths"]) if e not in said]
    out += [f"ignore.paths `{_clean(p)}` matches no file in the repository; remove it or fix it" for p in settings["paths"]
            if not any(fnmatch.fnmatchcase(f, p) for f in tracked)]
    out += [f"ignore.paths `{_clean(p)}` matches every path, so no extra would ever need a name" for p in settings["paths"] if matches_everything(p)]
    return out
