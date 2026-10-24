"""Left behind: the change moves a runtime or an image to a new version in one place, and other files still pin the old one.

PHP2Shell (21 October 2026) was fixed by moving PHP to 8.3.36, 8.4.27, 8.5.12 or 8.2.35, and a container that still runs the
old PHP stays open however many other files were moved. A security fix is often written in one file: the production
Dockerfile moves, the CI test image, the staging compose file and `.php-version` do not. Renovate and Dependabot propose
an update file by file, and a diff-only reviewer never sees a file the change did not touch. This reads the change's
moved pins (a line the change adds whose pin is newer than the same image's or runtime's pin in that file before), then
every other pin of that image or runtime in the repository at the head, and names each copy still on the old version.

Where pins are read (fixed rules, no YAML parser, standard library only):
- Dockerfiles (`Dockerfile*`, `*.Dockerfile`, `Containerfile*`): `FROM` (with `--platform`, `AS`; a stage name and `scratch`
  are skipped), `COPY --from=<image>`, and an `ARG NAME=value` default a `FROM` uses (the version then lives on the ARG line).
- GitLab CI files, compose files (`compose*.y?ml`, `docker-compose*.y?ml`) and GitHub workflows: `image:`, `name:` under
  `image:` or `services:`, `container:`, and setup inputs (`php-version:`, `node-version:`, `python-version:` ...). A pin
  under a `matrix:` key, a list, or one with a variable that is not a compose default (`${VAR:-8.3.30}`) is not read; a
  compose service that also has `build:` names the image it builds, so its `image:` is not read either.
- `.tool-versions` (every version on a line), `.php-version`, `.nvmrc`, `.node-version`, `.python-version`, `.ruby-version`.
- Not read: vendored and build directories, documentation, lock files, and any line that carries `itemator: keep` (or
  follows a comment line that does): the way to say a copy is old on purpose.

How versions compare (Renovate's docker versioning shows why each rule): the leading dotted number of a tag is the version
and the text after it is a flavour (`-fpm-alpine3.20` is not a version); numbers compare as numbers (8.3.4 < 8.3.36); a
release candidate, `latest`, an alias (`lts/*`) or no tag is never compared. A copy is left behind when its version is
lower than the one the change moves to and it is on the line the change moved from or to (same major.minor; same major
for a one-number version), or, when the issue lists versions (patch day), it is below the listed version for its own
line. A shorter tag on that line (`php:8.3-fpm` against 8.3.36) floats: it follows each pull, so it is a fact, not a
question. Information for the card; the CI job turns each file with a copy left behind into one thread.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field

KIND = "left_behind"
MAX_FILES = 3000          # files the scan looks at in one repository
MAX_BYTES = 256 * 1024    # a larger file is skipped
MAX_FOUND = 20            # copies named per change
SKIP_DIRS = ("vendor", "node_modules", ".git", "dist", "build", "third_party", "docs", "doc", "testdata", "fixtures")
KEEP_MARK = "itemator: keep"

RUNTIME_FILES = {".php-version": "php", ".nvmrc": "node", ".node-version": "node", ".python-version": "python",
                 ".ruby-version": "ruby"}
TOOL_NAMES = {"nodejs": "node"}                     # .tool-versions spells a few tools differently
SETUP_INPUTS = {"php-version": "php", "node-version": "node", "python-version": "python", "ruby-version": "ruby",
                "go-version": "go", "java-version": "java"}
SAME_IMAGE = {"gitlab/gitlab-ce": "gitlab", "gitlab/gitlab-ee": "gitlab"}

_VERSION = re.compile(r"v?(\d+(?:\.\d+){0,3})(?![\d.])")
_FROM = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?\s*$", re.I)
_COPY_FROM = re.compile(r"^\s*COPY\s+(?:--\S+\s+)*?--from=(\S+)", re.I)
_ARG = re.compile(r"""^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)=(["']?)([^\s"']+)\2\s*$""", re.I)
_VAR = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
_KEY = re.compile(r"""^(\s*)(-\s+)?([A-Za-z0-9_.-]+):(?:\s+["']?([^\s"'#]*)["']?)?\s*(?:#.*)?$""")
_DEFAULT = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?-([^}]*)\}")
_ITEM = re.compile(r"""^(\s*)-\s+["']?([^\s"'#:]+(?:/[^\s"'#:]+)*:[^\s"'#]+)["']?\s*(?:#.*)?$""")
_PROXY = re.compile(r"^\$\{?CI_DEPENDENCY_PROXY_[A-Z_]*\}?/")


@dataclass
class Pin:
    path: str
    line: int                 # 1-based line that holds the version text
    text: str                 # that line, as in the file
    family: str               # php, node, python, or an image path such as postgres or gitlab
    version: tuple
    shown: str                # the version as written there
    start: int                # where `shown` sits in `text`
    flavour: str = ""
    digest: bool = False
    where: str = "image"      # image, arg, runtime-file, tool-versions, setup-input
    unique: bool = True       # the line, without its indentation, occurs once in its file (set by find)

    @property
    def precision(self) -> int:
        return len(self.version)


@dataclass
class Moved:
    path: str
    line: int
    family: str
    old: tuple
    new: tuple
    shown: str


@dataclass
class Found:
    moved: list = field(default_factory=list)
    left: list = field(default_factory=list)       # (Pin, target version text, Moved)
    floating: list = field(default_factory=list)   # (Pin, Moved)
    capped: bool = False
    single: dict = field(default_factory=dict)     # {path: Moved}: the file's whole change is that one moved pin


# ---------------------------------------------------------------- reading one file

def skipped_path(path: str) -> bool:
    parts = path.split("/")
    return any(p in SKIP_DIRS for p in parts[:-1]) or path.endswith((".md", ".rst", ".txt", ".lock"))


def kind_of(path: str) -> str | None:
    name = posixpath.basename(path)
    low = name.lower()
    if name in RUNTIME_FILES:
        return "runtime"
    if name == ".tool-versions":
        return "tools"
    if low.startswith(("dockerfile", "containerfile")) or low.endswith(".dockerfile"):
        return "dockerfile"
    if not low.endswith((".yml", ".yaml")):
        return None
    if re.fullmatch(r"(docker-)?compose[^/]*\.ya?ml", low):
        return "compose"
    if path.startswith(".github/workflows/") or low.endswith((".gitlab-ci.yml", ".gitlab-ci.yaml")) or \
            path.startswith((".gitlab/", "ci/")):
        return "yaml"
    return None


def parse_version(s: str):
    """(version tuple, the text that was read, flavour) or None: a release candidate, an alias or no number is None."""
    m = _VERSION.match(s)
    if not m:
        return None
    rest = s[m.end():]
    if rest and rest[0] not in "-_":
        return None                    # 8.5.12RC1, 20.0.0rc2, 3.13b1: not a release
    return tuple(int(x) for x in m.group(1).split(".")), m.group(0), rest


def image_family(name: str) -> str:
    name = name.lower()
    first = name.split("/", 1)[0]
    if "/" in name and ("." in first or ":" in first or first == "localhost"):
        name = name.split("/", 1)[1]           # a registry host
    if name.startswith("library/"):
        name = name[len("library/"):]
    return SAME_IMAGE.get(name, name)


def split_image(ref: str):
    """(family, tag, digest) of an image reference, or None for one with no tag, `latest`, or an unresolved variable."""
    ref = _PROXY.sub("", ref.strip().strip("\"'"))
    if "$" in ref or not ref or ref == "scratch":
        return None
    ref, _, digest = ref.partition("@")
    head, _, last = ref.rpartition("/")
    if ":" not in last:
        return None
    last_name, tag = last.rsplit(":", 1)
    name = f"{head}/{last_name}" if head else last_name
    return image_family(name), tag, bool(digest)


def _image_pin(path, lineno, text, ref, where="image", arg=None) -> Pin | None:
    got = split_image(ref)
    if not got:
        return None
    family, tag, digest = got
    v = parse_version(tag)
    if not v:
        return None
    version, shown, flavour = v
    if arg is not None:                                  # the version came from an ARG default on another line
        aline, atext, avalue = arg
        start = atext.find(shown)
        return Pin(path, aline, atext, family, version, shown, start, flavour, digest, "arg") if start >= 0 else None
    start = text.find(":" + shown)
    if start < 0:
        return None
    return Pin(path, lineno, text, family, version, shown, start + 1, flavour, digest, where)


def _kept(lines: list, i: int) -> bool:
    if KEEP_MARK in lines[i]:
        return True
    prev = lines[i - 1].strip() if i > 0 else ""
    return prev.startswith("#") and KEEP_MARK in prev


def dockerfile_pins(path: str, text: str) -> list[Pin]:
    lines, out, args = text.split("\n"), [], {}
    for i, raw in enumerate(lines):
        line = raw.split(" #", 1)[0] if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        m = _ARG.match(line)
        if m:
            args[m.group(1)] = (i + 1, raw, m.group(3))
            continue
        m = _FROM.match(line)
        ref = None
        if m:
            ref = m.group(1)                         # a stage name (FROM base) has no tag, so split_image drops it
        else:
            c = _COPY_FROM.match(line)
            if c and (":" in c.group(1) or "/" in c.group(1)):
                ref = c.group(1)
        if not ref or _kept(lines, i):
            continue
        used = _VAR.findall(ref)
        arg = None
        if used:
            if len(used) != 1 or used[0] not in args:
                continue                                 # unresolved, or more than one variable: not read
            arg = args[used[0]]
            if _kept(lines, arg[0] - 1):
                continue
            ref = _VAR.sub(arg[2], ref)
        p = _image_pin(path, i + 1, raw, ref, arg=arg)
        if p:
            out.append(p)
    return out


def yaml_pins(path: str, text: str, compose: bool = False) -> list[Pin]:
    """Pins in a CI, compose or workflow file, by indentation and key, without a YAML parser."""
    lines, out = text.split("\n"), []
    keys = []                                  # (indent, key, line index) of every key line, in order
    for i, raw in enumerate(lines):
        m = _KEY.match(raw) if not raw.lstrip().startswith("#") else None
        if m:
            indent = len(m.group(1)) + (len(m.group(2)) if m.group(2) else 0)
            keys.append((indent, m.group(3), i, bool(m.group(2)), m.group(4)))

    def ancestors(k):
        indent, chain = k[0], []
        for j in range(keys.index(k) - 1, -1, -1):
            if keys[j][0] < indent:
                chain.append(keys[j])
                indent = keys[j][0]
        return chain

    for k in keys:
        indent, key, i, item, value = k
        if not value or _kept(lines, i):
            continue
        chain = ancestors(k)
        names = [c[1] for c in chain]
        if "matrix" in names or value.startswith(("[", "{")):
            continue
        parent = names[0] if names else None
        if key in SETUP_INPUTS:
            if "${{" in lines[i] or "$" in value:
                continue
            v = parse_version(value)
            if v and value[len(v[1]):] == "":
                start = lines[i].find(v[1], lines[i].index(key) + len(key))
                out.append(Pin(path, i + 1, lines[i], SETUP_INPUTS[key], v[0], v[1], start, "", False, "setup-input"))
            continue
        is_image = key in ("image", "container") or (key == "name" and (parent == "image" or parent == "services"
                                                                         or (item and parent == "services")))
        if not is_image or (compose and key == "image" and _has_build(keys, k, chain)):
            continue
        ref = value
        if compose:
            d = _DEFAULT.fullmatch(ref) or _DEFAULT.search(ref)
            if d and "$" in ref:
                whole = _DEFAULT.sub(lambda mm: mm.group(1), ref)
                ref = whole if "$" not in whole else ref
            ref = ref.replace("$$", "$")
        p = _image_pin(path, i + 1, lines[i], ref)
        if p:
            out.append(p)
    for i, raw in enumerate(lines):                # `services:` entries written as a bare image (`- mysql:8.0.36`)
        m = _ITEM.match(raw)
        if not m or _kept(lines, i):
            continue
        indent = len(m.group(1))
        parent = next((k for k in reversed(keys) if k[2] < i and k[0] < indent), None)
        if parent and parent[1] == "services" and not any(k[1] == "matrix" for k in _chain(keys, parent)):
            p = _image_pin(path, i + 1, raw, m.group(2))
            if p:
                out.append(p)
    return sorted(out, key=lambda q: q.line)


def _chain(keys, k) -> list:
    indent, chain = k[0], [k]
    for j in range(keys.index(k) - 1, -1, -1):
        if keys[j][0] < indent:
            chain.append(keys[j])
            indent = keys[j][0]
    return chain


def _has_build(keys, k, chain) -> bool:
    """A compose service whose mapping also has `build:` (its `image:` names what it builds)."""
    if not chain:
        return False
    parent = chain[0]
    start = keys.index(parent)
    for j in range(start + 1, len(keys)):
        if keys[j][0] <= parent[0]:
            break
        if keys[j][0] == k[0] and keys[j][1] == "build":
            return True
    return False


def runtime_pins(path: str, text: str) -> list[Pin]:
    family = RUNTIME_FILES[posixpath.basename(path)]
    for i, raw in enumerate(text.split("\n")):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        v = parse_version(s)
        if not v or s[len(v[1]):]:
            return []
        return [Pin(path, i + 1, raw, family, v[0], v[1], raw.find(v[1]), "", False, "runtime-file")]
    return []


def tool_pins(path: str, text: str) -> list[Pin]:
    out, lines = [], text.split("\n")
    for i, raw in enumerate(lines):
        body = raw.split("#", 1)[0].split()
        if len(body) < 2 or _kept(lines, i):
            continue
        family = TOOL_NAMES.get(body[0], body[0])
        pos = raw.find(body[0]) + len(body[0])
        for tok in body[1:]:
            at = raw.find(tok, pos)
            pos = at + len(tok)
            v = parse_version(tok)
            if v and tok[len(v[1]):] == "":
                out.append(Pin(path, i + 1, raw, family, v[0], v[1], at, "", False, "tool-versions"))
    return out


def pins(path: str, text: str) -> list[Pin]:
    k = kind_of(path)
    if k == "dockerfile":
        return dockerfile_pins(path, text)
    if k in ("yaml", "compose"):
        return yaml_pins(path, text, compose=k == "compose")
    if k == "runtime":
        return runtime_pins(path, text)
    if k == "tools":
        return tool_pins(path, text)
    return []


# ---------------------------------------------------------------- the change and the repository

def moved(files: list[dict], read_base, read_head) -> list[Moved]:
    """Pins at the head whose version no pin of the same image or runtime in that file had at the base, and that are newer
    than one of them at the same precision: what the change moved (a modified file only; a new file moves nothing). A
    version that is new in the file sits on a line the change added, or on the ARG line a FROM reads."""
    out = []
    for f in files:
        path = f.get("filename") or ""
        if f.get("status") != "modified" or not kind_of(path):
            continue
        before, after = read_base(path), read_head(path)
        if before is None or after is None:
            continue
        old = {}
        for p in pins(path, before):
            old.setdefault(p.family, []).append(p.version)
        for p in pins(path, after):
            if p.family not in old:
                continue
            lower = [v for v in old[p.family] if v < p.version and len(v) == p.precision]
            if lower and p.version not in old[p.family]:
                out.append(Moved(path, p.line, p.family, max(lower), p.version, p.shown))
    return out


def single(files: list[dict], moves: list[Moved], read_base, read_head) -> dict:
    """{path: Moved} for each file whose whole change is one moved pin: one line differs, and it is the line before with
    only the version text swapped (what `bump` writes). Such a file follows the move another file makes."""
    out = {}
    for f in files:
        path = f.get("filename") or ""
        ms = [m for m in moves if m.path == path]
        if len(ms) != 1:
            continue
        before, after = read_base(path), read_head(path)
        b, a = (before or "").split("\n"), (after or "").split("\n")
        diff = [i for i in range(len(b)) if b[i] != a[i]] if len(b) == len(a) else []
        if before is None or after is None or diff != [ms[0].line - 1]:
            continue
        old = [p for p in pins(path, before) if p.line == ms[0].line and p.family == ms[0].family]
        if any(a[p.line - 1] == p.text[:p.start] + ms[0].shown + p.text[p.start + len(p.shown):] for p in old):
            out[path] = ms[0]
    return out


def _series(v: tuple) -> tuple:
    return v[:2] if len(v) >= 2 else v[:1]


def judge(p: Pin, m: Moved, listed: set) -> tuple | None:
    """("left", target) or ("floating", None) or None for one pin against one moved pin."""
    if p.precision < len(m.new):
        return ("floating", None) if m.new[:p.precision] == p.version else None
    if p.version >= m.new and _series(p.version) == _series(m.new):
        return None
    if _series(p.version) in (_series(m.new), _series(m.old)) and p.version < m.new:
        return "left", m.shown
    fixes = sorted(v[0] for v in map(parse_version, listed) if v)
    for fx in fixes:
        if len(fx) == p.precision and _series(fx) == _series(p.version) and p.version < fx:
            return "left", ".".join(map(str, fx))
    return None


def find(files: list[dict], tracked: list[str], read_base, read_head, listed=frozenset()) -> Found:
    """`tracked`: the repository's files at the head; `read_base(path)` / `read_head(path)`: a file's text or None."""
    got = Found(moved=moved(files, read_base, read_head))
    if not got.moved:
        return got
    got.single = single(files, got.moved, read_base, read_head)
    families = {m.family for m in got.moved}
    scanned = 0
    for path in tracked:
        if skipped_path(path) or not kind_of(path):
            continue
        scanned += 1
        if scanned > MAX_FILES:
            got.capped = True
            break
        text = read_head(path)
        if text is None or len(text.encode("utf-8", "replace")) > MAX_BYTES:
            continue
        for p in pins(path, text):
            if p.family not in families:             # a moved pin is at the new version, so judge() passes it
                continue
            p.unique = text.count(p.text.strip()) == 1
            for m in (m for m in got.moved if m.family == p.family):
                verdict = judge(p, m, listed)
                if verdict and verdict[0] == "left":
                    got.left.append((p, verdict[1], m))
                    break
                if verdict and verdict[0] == "floating":
                    got.floating.append((p, m))
                    break
            if len(got.left) >= MAX_FOUND:
                got.capped = True
                return got
    return got


# ---------------------------------------------------------------- what the card says

def bump_line(p: Pin, target: str) -> tuple | None:
    """(OLD, NEW) for the reaction flow's one-line edit: the line without its indentation, with the version replaced.
    None when the edit cannot be made safely: a digest pin (the digest would stay old), a precision the target does not
    have, a backtick in the line, or text that is not unique in its file (the caller checks that)."""
    if p.digest or not p.unique or "`" in p.text or len(target.split(".")) != p.precision:
        return None
    new = p.text[:p.start] + target + p.text[p.start + len(p.shown):]
    old_s, new_s = p.text.strip(), new.strip()
    return (old_s, new_s) if old_s and old_s != new_s else None


def where(p: Pin) -> str:
    return {"arg": "build argument", "runtime-file": "version file", "tool-versions": "tool versions",
            "setup-input": "setup step"}.get(p.where, "image")
