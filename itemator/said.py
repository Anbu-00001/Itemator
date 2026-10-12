"""Said or silent (T35, T38): does the merge request's own title or description name each extra?

Facts only, from boolean tests of OUR names for the extra (names()) against the author's text. The thread shows one
of three fixed sentences (SENTENCE) or none; no text of the author's is ever copied out, so a hostile description
can change only which sentence is shown, or whether one is shown.

  listed  a name appears in a list item, or in the first paragraph, under a "Beyond the issue" heading (any level,
          ATX, or setext after a blank line; outside code fences, $$ blocks and HTML blocks), the section the
          stay-inside-the-issue skill asks for. The section ends at the next heading, a thematic break, a bold-only
          line, a short "Label:" line after its first block, or a line starting with an HTML block tag.
  named   a STRONG match anywhere else in the title or the description: inside a code span or fence, a full path,
          or the exact case of a name that is not an ordinary word.
  silent  the whole description was read and names none of them.
  None    no sentence. A WEAK match only (an ordinary word: lowercase letters, 8 or fewer, or a generic directory
          such as `test` or `docs`, matched outside code); no description; text that may be cut (over MAX_BYTES, or
          the truncated CI variable); an unclosed `<!--`; an HTML attribute that can hide text (`hidden`, `style`);
          or the DEADLINE passed. "Does not mention" is never said unread, and a false "names this" is avoided.

A name appears when, ignoring case, nothing that continues it touches it: no letter, digit or `_`, and no `- . / @ +
~` followed (or preceded) by one, so `leftpad` is not in `leftpad-py2` and `2.0.7` is not in `2.0.7.1`. A base name
also needs no `/` before it. Closed HTML comments outside code, link and image destinations and titles, images,
reference definitions and HTML tags with attributes are dropped first; invisible characters too. A paraphrase or a
look-alike never counts. Names shorter than MIN_LEN after cleaning, or with no letter or digit, never match.
Naming every extra is information, not approval: every extra still needs its answer.
"""
from __future__ import annotations

import bisect
import posixpath
import re
import time

LISTED, NAMED, SILENT, WEAK = "listed", "named", "silent", "weak"     # WEAK: said_detail only, never shown
SENTENCE = {LISTED: 'The description lists this under "Beyond the issue".',
            NAMED: "The description names this.",
            SILENT: "The description does not mention this."}
HEADING = "beyond the issue"
MAX_BYTES = 64 * 1024     # of the description (and of the title) read; past it, a name not found is not "silent"
DEADLINE = 0.5            # seconds for all the extras of one merge request; an extra not reached gets no sentence
MIN_LEN = 3
MAX_NAMES = 1000          # names tried per extra (a group's items); the deadline bounds the rest
ORDINARY = 8              # a lowercase word of this many letters or fewer is an ordinary word (weak outside code)
GENERIC = frozenset({"test", "tests", "testing", "spec", "specs", "src", "source", "docs", "doc", "build", "dist",
                     "lib", "libs", "bin", "out", "output", "tmp", "temp", "scripts", "script", "examples", "example",
                     "assets", "config", "vendor", "packages", "pkg", "app", "apps", "site-packages", "node_modules",
                     "public", "static", "data", "fixtures"})
_JOIN = frozenset("-./@+~")
_DROP = dict.fromkeys([0x00AD, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF, 0x061C,
                       *range(0x202A, 0x202F), *range(0x2066, 0x206A), *range(0xE0000, 0xE0080)])
_BLOCK_TAGS = frozenset("address article aside base basefont blockquote body caption center col colgroup dd details "
                        "dialog dir div dl dt fieldset figcaption figure footer form frame frameset h1 h2 h3 h4 h5 h6 "
                        "head header hr html iframe legend li link main menu menuitem nav noframes ol optgroup option "
                        "p param pre script section source style summary table tbody td textarea tfoot th thead title "
                        "tr track ul".split())
_TAG = re.compile(r"<[A-Za-z][A-Za-z0-9-]{0,30}[ \t/][^<>\n]{0,2000}>")      # a tag with attributes (or a slash)
_REFDEF = re.compile(r" {0,3}\[[^\[\]\n]{1,999}\]:")
_ORDERED = re.compile(r" {0,3}\d{1,9}[.)](?: |$)")


class _Late(Exception):
    pass


def names(name: str, path: str = "", detail=()) -> list[tuple[str, bool]]:
    """(text, is_base) for each string that names one extra: its name; for a path (the name is the path, or a
    directory ending in "/"), also the full path and its base name; for a grouped extra (`detail`), also the base
    name of its file or directory and each listed item's name."""
    out = [(name, False)]
    if name == path or name.endswith("/") or detail:
        full = (path or name).rstrip("/")
        out += [(full, False), (posixpath.basename(full), True)]
    out += [(str(d), False) for d in list(detail)[:MAX_NAMES]]
    return out


def _lower(s: str) -> str:
    """Lower case with every index kept (a character whose lower case is longer stays as it is)."""
    low = s.lower()
    return low if len(low) == len(s) else "".join(c.lower() if len(c.lower()) == 1 else c for c in s)


def _keys(candidates) -> list[tuple[str, str, bool, bool]]:
    """(text, lower case, is_base, ordinary) for each name that can be matched; a name with a control character,
    shorter than MIN_LEN, or without a letter or digit is left out."""
    seen = {}
    for c in list(candidates)[:MAX_NAMES + 3]:
        text, base = (c, False) if isinstance(c, str) else c
        if any(ord(ch) < 32 or 0x7F <= ord(ch) <= 0x9F for ch in text):
            continue
        s = text.translate(_DROP).strip().rstrip("/").strip()
        if len(s) < MIN_LEN or not any(ch.isalnum() for ch in s):
            continue
        seen[s] = seen.get(s, True) and base
    return [(s, _lower(s), base, (s.isalpha() and s.islower() and len(s) <= ORDINARY) or _lower(s) in GENERIC)
            for s, base in seen.items()]


def _cap(text: str) -> tuple[str, bool]:
    """The first MAX_BYTES bytes of `text` (UTF-8), and whether anything was cut."""
    head = text[:MAX_BYTES]
    raw = head.encode("utf-8", "replace")
    return raw[:MAX_BYTES].decode("utf-8", "ignore"), len(text) > len(head) or len(raw) > MAX_BYTES


# ---------------------------------------------------------------- lines and code

def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _fence(line: str):
    """(character, length) when the line opens a code fence or a $$ math block, else None."""
    if _indent(line) > 3:
        return None
    s = line.lstrip(" ")
    if s.rstrip() == "$$":
        return "$", 2
    for ch in "`~":
        n = len(s) - len(s.lstrip(ch))
        if n >= 3 and not (ch == "`" and "`" in s[n:]):
            return ch, n
    return None


def _closes(line: str, fence) -> bool:
    s = line.strip()
    return _indent(line) <= 3 and len(s) >= fence[1] and s == fence[0] * len(s)


def _fenced(lines: list[str]) -> list[bool]:
    """For each line: is it a fence line or inside a fence?"""
    out, fence = [], None
    for line in lines:
        if fence is not None:
            out.append(True)
            if _closes(line, fence):
                fence = None
        else:
            fence = _fence(line)
            out.append(fence is not None)
    return out


def _code_spans(line: str) -> list[tuple[int, int]]:
    """[(start, end)] of the inline code spans of one line, backticks included: a run of backticks up to the next
    run of the same length."""
    runs, i, n = [], 0, len(line)
    while True:
        i = line.find("`", i)
        if i < 0:
            break
        j = i
        while j < n and line[j] == "`":
            j += 1
        runs.append((i, j - i))
        i = j
    after, nxt = [None] * len(runs), {}
    for k in range(len(runs) - 1, -1, -1):
        after[k], nxt[runs[k][1]] = nxt.get(runs[k][1]), k
    spans, k = [], 0
    while k < len(runs):
        m = after[k]
        if m is None:
            k += 1
            continue
        spans.append((runs[k][0], runs[m][0] + runs[m][1]))
        k = m + 1
    return spans


def _in(spans, pos: int) -> bool:
    k = bisect.bisect_right(spans, (pos, float("inf"))) - 1
    return k >= 0 and spans[k][0] <= pos < spans[k][1]


def _uncomment(text: str) -> tuple[str, bool]:
    """`text` without its closed HTML comments outside code (the line breaks inside stay, so no line moves), and
    whether an unclosed `<!--` outside code was left as it is."""
    lines = text.split("\n")
    starts, pos = [], 0
    for line in lines:
        starts.append(pos)
        pos += len(line) + 1
    fenced, spans = _fenced(lines), {}
    out, i, search = [], 0, 0
    while True:
        j = text.find("<!--", search)
        if j < 0:
            break
        ln = bisect.bisect_right(starts, j) - 1
        if ln not in spans:
            spans[ln] = _code_spans(lines[ln])
        if fenced[ln] or _in(spans[ln], j - starts[ln]):
            search = j + 4
            continue
        k = text.find("-->", j + 4)
        if k < 0:
            out.append(text[i:])
            return "".join(out), True
        out += [text[i:j], "\n" * text.count("\n", j, k + 3)]
        i = search = k + 3
    out.append(text[i:])
    return "".join(out), False


def _unlink(line: str, spans) -> str:
    """`line` with each [text](destination "title") outside code reduced to its text and each image dropped."""
    out, i = [], 0
    while True:
        j = line.find("](", i)
        if j < 0:
            out.append(line[i:])
            return "".join(out)
        o = line.rfind("[", max(i, j - 1000), j)
        if o < 0 or _in(spans, j) or "]" in line[o + 1:j]:
            out.append(line[i:j + 2])
            i = j + 2
            continue
        depth, k, end = 1, j + 2, min(len(line), j + 2002)
        while k < end and depth:
            depth += {"(": 1, ")": -1}.get(line[k], 0)
            k += 1
        if depth:
            out.append(line[i:j + 2])
            i = j + 2
            continue
        image = o > i and line[o - 1] == "!"
        out.append(line[i:o - 1] if image else line[i:o] + line[o + 1:j])
        i = k


def _inline(line: str) -> tuple[list[tuple[str, bool]], bool]:
    """[(text, is_code)] for one line: links reduced to their text, tags with attributes dropped outside code; and
    whether a dropped tag carried an attribute that can hide text."""
    line = _unlink(line, _code_spans(line))
    out, hidden, i = [], False, 0
    for a, b in _code_spans(line) + [(len(line), len(line))]:
        plain = line[i:a]
        for m in _TAG.finditer(plain):
            low = m.group(0).lower()
            hidden = hidden or "hidden" in low or "style" in low
        out.append((_TAG.sub("", plain), False))
        if b > a:
            out.append((line[a:b], True))
        i = b
    return out, hidden


# ---------------------------------------------------------------- blocks

def _atx(line: str) -> str | None:
    """The text of an ATX heading line ("## Text ##"), else None."""
    if _indent(line) > 3:
        return None
    s = line.lstrip(" ")
    n = len(s) - len(s.lstrip("#"))
    if not 1 <= n <= 6 or (len(s) > n and s[n] not in " \t"):
        return None
    text = s[n:].strip()
    bare = text.rstrip("#")
    if not bare or bare[-1] in " \t":
        text = bare.strip()
    return text


def _underline(line: str) -> bool:
    s = line.strip()
    return _indent(line) <= 3 and bool(s) and (s == "=" * len(s) or s == "-" * len(s))


def _rule(line: str) -> bool:
    s = line.strip().replace(" ", "").replace("\t", "")
    return _indent(line) <= 3 and len(s) >= 3 and s[0] in "-*_" and s == s[0] * len(s)


def _list_item(line: str) -> bool:
    s = line.lstrip(" ")
    return s.startswith(("- ", "* ", "+ ")) or s in ("-", "*", "+") or bool(_ORDERED.match(line.lstrip(" ")))


def _html_start(line: str) -> bool:
    """A line starting with an HTML block tag (CommonMark's HTML block types 1 and 6)."""
    s = line.strip().lower()
    if _indent(line) > 3 or not s.startswith("<"):
        return False
    name = s[2:] if s.startswith("</") else s[1:]
    k = 0
    while k < len(name) and name[k].isalnum():
        k += 1
    return name[:k] in _BLOCK_TAGS and (k == len(name) or name[k] in " \t>/")


def _bold_only(s: str) -> bool:
    return len(s) > 4 and ((s.startswith("**") and s.endswith("**")) or (s.startswith("__") and s.endswith("__")))


def _label(s: str) -> bool:
    t = s.strip("*_ ").rstrip("*_ ")
    return t.endswith(":") and 1 <= len(t[:-1].split()) <= 3 and len(t) <= 40


def _paragraph(line: str) -> bool:
    s = line.strip()
    return (bool(s) and _indent(line) <= 3 and not s.startswith(">") and not _list_item(line)
            and _fence(line) is None and _atx(line) is None and not _html_start(line))


def _beyond(text: str) -> bool:
    return text.strip().strip("*_").strip().rstrip(":").strip().casefold() == HEADING


def _blocks(lines: list[str]) -> list[tuple[str, bool, bool]]:
    """(line, is_code, listed) for each line of the description. Reference definitions become empty lines, a
    "Beyond the issue" heading line is left out, other heading lines keep only their text."""
    out, fence, html, here, region, blank, k = [], None, False, False, "", True, 0
    while k < len(lines):
        line, s = lines[k], lines[k].strip()
        k += 1
        if fence is not None:
            if _closes(line, fence):
                fence = None
                if region == "first":
                    region = "after"
            out.append((line, True, here and region in ("first", "list")))
            blank = False
            continue
        if html:
            html = bool(s)
            out.append((line, False, False))
            blank = not s
            continue
        if not s:
            if here:
                region = {"para": "after", "first": "after", "list": "gap"}.get(region, region)
            out.append(("", False, False))
            blank = True
            continue
        f = _fence(line)
        if f is not None:
            fence = f
            if here:
                region = ("first" if region == "start" else "list" if region in ("list", "gap") and _indent(line) >= 2
                          else "other")
            out.append((line, True, here and region in ("first", "list")))
            blank = False
            continue
        if _html_start(line):
            html, here = True, False
            out.append((line, False, False))
            blank = False
            continue
        if _REFDEF.match(line):
            out.append(("", False, False))
            continue
        heading = _atx(line)
        if heading is None and blank and _paragraph(line) and k < len(lines) and _underline(lines[k]):
            heading = s
            k += 1                                  # the underline belongs to the heading
        if heading is not None:
            here, region, blank = _beyond(heading), "start", True
            if not here:
                out.append((heading, False, False))
            continue
        if _rule(line) or (_underline(line) and not blank) or (here and (
                _bold_only(s) or (region != "start" and _label(s)))):
            here = False
        listed = False
        if here:
            if _list_item(line):
                region, listed = "list", True
            elif region in ("start", "para"):
                region, listed = "para", True
            elif region == "list" or (region == "gap" and _indent(line) >= 2):
                region, listed = "list", True
            else:
                region = "other"
        out.append((line, False, listed))
        blank = False
    return out


# ---------------------------------------------------------------- matching

class _Text:
    """One searchable text: the original, its lower case, and which characters are code."""

    def __init__(self):
        self.parts, self.code = [], bytearray()

    def add(self, text: str, is_code: bool):
        self.parts.append(text)
        self.code += (b"\x01" if is_code else b"\x00") * len(text)

    def done(self):
        self.text = "".join(self.parts)
        self.low = _lower(self.text)
        return self


def _word(c: str) -> bool:
    return c.isalnum() or c == "_"


def _edge_before(low: str, i: int) -> bool:
    if i == 0:
        return True
    c = low[i - 1]
    return not (_word(c) or (c in _JOIN and i >= 2 and _word(low[i - 2])))


def _edge_after(low: str, j: int) -> bool:
    if j >= len(low):
        return True
    c = low[j]
    return not (_word(c) or (c in _JOIN and j + 1 < len(low) and _word(low[j + 1])))


def _find(key, t: _Text, strong_only: bool, until: float, clock):
    """"strong", "weak" or None: the best occurrence of one name in `t`."""
    text, low_key, base, ordinary = key
    start, n, best = 0, len(low_key), None
    while True:
        if clock() > until:
            raise _Late
        i = t.low.find(low_key, start)
        if i < 0:
            return best
        start = i + 1
        if not _edge_before(t.low, i) or not _edge_after(t.low, i + n) or (base and i and t.low[i - 1] == "/"):
            continue
        if t.code[i] or "/" in text or (not ordinary and t.text[i:i + n] == text):
            return "strong"
        best = WEAK
        if not strong_only:
            return best


def _texts(title: str, description: str) -> tuple[_Text, _Text, bool]:
    """(listed, rest, hidden): the text of the listed lines, the rest (title first), and whether an HTML attribute
    that can hide text was seen."""
    listed, rest, hidden = _Text(), _Text(), False
    lines = [line[:-1] if line.endswith("\r") else line for line in description.split("\n")]
    for line, is_code, in_list in [(title, False, False)] + _blocks(lines):
        into = listed if in_list else rest
        if is_code:
            into.add(line, True)
        else:
            parts, h = _inline(line)
            hidden = hidden or h
            for text, code in parts:
                into.add(text, code)
        into.add("\n", False)
    return listed.done(), rest.done(), hidden


def said_detail(title: str | None, description: str | None, extras: list, *, cut: bool = False,
                clock=time.monotonic, deadline: float = DEADLINE) -> list:
    """LISTED, NAMED, WEAK, SILENT or None for each extra, given as its names() list. `cut`: the description may be
    truncated (a CI variable), so a name not found gives None, never SILENT."""
    if not description or not description.strip():
        return [None] * len(extras)
    until = clock() + deadline
    text, over = _cap(description)
    text, unclosed = _uncomment(text.translate(_DROP))
    listed, rest, hidden = _texts(_cap(title or "")[0].translate(_DROP).replace("\n", " "), text)
    if hidden:
        return [None] * len(extras)
    out = []
    for candidates in extras:
        try:
            if clock() > until:
                raise _Late
            keys = _keys(candidates)
            if any(_find(k, listed, False, until, clock) for k in keys):
                out.append(LISTED)
                continue
            found = None
            for k in keys:
                found = _find(k, rest, True, until, clock) or found
                if found == "strong":
                    break
            out.append(NAMED if found == "strong" else WEAK if found else None if (cut or over or unclosed)
                       else SILENT)
        except _Late:
            out.append(None)
    return out


def said(title: str | None, description: str | None, extras: list, **kw) -> list:
    """One of LISTED, NAMED, SILENT or None (no sentence) for each extra; a weak match gives None."""
    return [None if s == WEAK else s for s in said_detail(title, description, extras, **kw)]
