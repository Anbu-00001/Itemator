"""Fixed rules: what a merge request changed beyond its linked issue. Rules version 4.

No model, no network, no randomness: the same issue text, changed files and
repository name always give the same extras, in the same order. Version 1
(commit cf0d762, sample A) is frozen in extras_v1.py, version 2 (commit
12b3d1b, held out on sample B) in extras_v2.py and version 3 (held out on
sample C) in extras_v3.py, byte for byte; analyse(..., version=1, 2 or 3) runs
them. Version 4 was fixed on samples A, B and C together (the development set,
seeds 20261010, 20261011 and 20261012) after the T10 audit and the T13 live
test; it is tested once on sample D.

WHAT V4 CHANGES (the rule texts below are v3's, amended where marked v4)
  - Rule 1: a manifest the change adds (Cargo.toml, package.json,
    pyproject.toml) is one extra, "adds package X", not one per dependency.
    In pyproject.toml, a one-line `dependencies = [...]` or
    `dev-dependencies = [...]` is read even when the hunk shows no section.
  - Rule 1b (new): version_bump.
  - Rule 4: a name still defined at the head (on a context line) or deleted
    with its file while a file of the same stem is added or renamed is not
    removed; story, mock and fixture helpers are not package API.
  - Rule 6: an added file with lines but no patch is large.
  - Rule 8 (new): build_output_added. Rule 9 (new): stray_file.

WHAT V3 CHANGED (the rule texts below are v2's, amended where marked v3)
  - Rule 5 no longer makes extras. Its files are `unplaced` (the card's
    informational state, "N files the rules could not place"), never named.
  - Mass events (rule 7): MASS or more files of one kind, all added or all
    deleted, under one directory become one extra named by that directory.
  - Rule 6 (new): binary_or_large_added.
  - Rule 3c (new): generated_code_removed. Generated or vendored code is never
    a test file (rules 3, 4, 5d).
  - Rule 1: a package the old file already lists is not new; nor is one whose
    name contains an acronym of the issue's title.

INPUT
  issue_text: the linked issue's title and body (several issues: joined).
  files: the changed files, each a dict with `filename`, `status`
  (GitHub's: added | removed | modified | renamed | copied | changed),
  `patch` (unified diff text, or None when the forge omits it) and, for a
  rename, `previous_filename`. A file without a patch is skipped by every rule
  that reads lines (rules 1, 2b, 2c, 3b, 4).
  repo: "owner/name" (optional). The project's own name, compared with '-'
  and '_' removed, never names a file (rule 5).

"THE ISSUE MENTIONS X" means: X occurs in the issue text, case-insensitively,
not glued to another letter or digit on either side; a second try ignores
'-' and '_' on both sides (`my-pkg` matches "my_pkg").

RULES (an extra is kind + path + name + why; `name` is what a human types)
1. new_dependency. In a manifest (requirements*.txt, requirements/*.txt|.in,
   pyproject.toml, package.json, go.mod, Cargo.toml, Gemfile, pom.xml,
   build.gradle, build.gradle.kts), a package on an added line that
   a. comes from the package index, is not also on a removed line of the same
      file (a version bump or a move is not new), and is not mentioned by the
      issue; or
   b. comes from a URL or VCS source (git+https://..., `pkg @ https://...`,
      a bare archive URL, -e git+..., --index-url/--extra-index-url/
      --find-links, npm git+/github:/https:/owner-repo values, Cargo or Gem
      git sources), unless the same source is on a removed line or the issue
      contains the source text. A package switched from the index to a URL
      counts. v1 skipped these lines.
   Only lines the parser can place in a dependency list count; when a diff hunk
   starts inside an unknown section, a line counts only if it carries a version
   (see the _deps_* functions). go.mod `// indirect` lines do not count.
   v3: a package that the old file already lists, on a removed or unchanged
   line the diff shows (go.mod `// indirect` included), is not new (a move from
   indirect to direct, or between sections, is not new). An index package is
   not new either when its name contains an acronym of the issue's title (a
   word of 4 or more capitals with at least 3 letters, such as XMPP): the issue
   names what the package implements.
   v4: a manifest the change adds (status added: Cargo.toml, package.json or
   pyproject.toml) belongs to a new package, so its dependencies are not
   extras one by one: it is one extra named by the package it declares
   ([package] name, the top-level "name", [project] or [tool.poetry] name;
   else its directory), unless the issue mentions that name. A manifest
   that declares no package and lists no dependency (tool settings only)
   gives nothing here. In pyproject.toml, a key named exactly dependencies
   or dev-dependencies whose array is on one line is read as a dependency
   array even when the hunk shows no section header.
   name = the package name (npm: the full `@scope/pkg`; Maven/Gradle: the
   artifact id; go.mod: the module path; a URL line: egg=, the name before
   ' @ ', else the URL's last part; an index option: the URL).
2. ci_or_config.
   a. A changed CI, dependency-update (dependabot, renovate), build, container
      or lint config file (_CONFIG_RULES), when the issue mentions neither its
      file name nor any keyword of its kind ("dependabot" or "renovate" for
      dependency-update config). name = the path.
   b. In package.json, a preinstall, install, postinstall, prepare or
      prepublish script added or changed, unless the issue mentions the
      script's name. name = the script name.
   c. In pyproject.toml, a changed line in a lint tool section
      ([tool.ruff*], flake8, pylint, mypy, pyright, black, isort, bandit, ...),
      or, in a hunk whose section is unknown, a changed ignore-list key
      (ignore, extend-ignore, per-file-ignores, disable, unfixable), unless the
      issue mentions pyproject.toml or a lint keyword. name = the path.
3. tests_removed. In a test file (a code file whose name looks like a test,
   or with a directory test/, tests/, __tests__/, spec/, specs/, testing/,
   e2e/), either
   a. the file was deleted, unless a test file with the same file name was
      added elsewhere (a move), or a non-test code file with the same stem was
      deleted too (the module went with its test), or the other test files of
      the same directory gain, net, at least as many test definitions as the
      deleted files of that directory held (a rewrite); or
   b. its removed lines hold more test definitions, or more assertion lines,
      than its added lines, and the change as a whole also lost that measure
      (tests moved between files are not removals).
   Skipped when the issue mentions the file's name. name = the path.
   v3: generated or vendored files (is_generated: a directory generated,
   __generated__, vendor, vendored, third_party, node_modules, site-packages;
   or a name like x.generated.cs, x_pb2.py, x.pb.go, x.g.dart) are never test
   files.
   c. generated_code_removed (v3). Deleted generated or vendored files, unless
      the issue names the file or the directory it sits in (_names_closely;
      naming an ancestor directory, such as a whole package, is not enough).
      Reported only as a mass event (rule 7); fewer than MASS deletions under
      one directory are regeneration churn and are dropped.
4. public_api_removed. On a removed line of a non-test file: a Python `def`
   or `class` indented 0 or 4 spaces (or one tab) whose name does not start
   with '_', or a JS/TS `export` (declaration or `export { a, b as c }`).
   It counts when no added line anywhere in the change defines or exports the
   same name again (signature changes and moves are not removals), and the
   issue does not mention the name. name = the symbol.
   v4: a name on a context line of any file is still defined at the head; a
   deleted file whose stem equals that of an added or renamed file moved;
   files under a *story*/*stories* name, __mocks__ or fixtures are helpers,
   not package API.
5. unplaced (v3; v2's file_outside_ask, same logic, no longer an extra). Every changed file is first checked
   against the issue:
   a. a path in the issue (a token with '/' or a file extension) equals the
      file's path, ends with it, is a trailing part of it, or is a directory
      that contains it; or
   b. the file's stem (its name up to the first '.', with test affixes such as
      test_, _test, Test, _spec removed) equals an issue token; or
   c. one of its directory names equals an issue token; or
   d. it is a test file whose stem equals the stem of a file matched by a-c.
   In b and c, a stem or directory equal to the project's own name never
   matches (v1: an issue saying "crewai" named every file under crewai/).
   Issue tokens: every word in the issue (and each part of a word joined by
   '-' or '_'), two or three adjacent words written together, each part of a path,
   text in backticks, and each part of a dotted name (`pkg.module`). Tokens
   and names compare lowercased with '-' and '_' removed, singular or plural.
   A forge link (github.com, gitlab.com) counts as a path only through
   /blob/<ref>/<path> or /tree/<ref>/<path>. Generic stems and directory
   names (_GENERIC_STEMS, _GENERIC_DIRS: index, utils, src, ...) and names
   under 3 characters match only through a path (a), never through a token.
   The issue anchors the change only when at least one matched file is not a
   test-support file (a test file, or a file under a test, fixtures, testdata
   or mocks directory): agents name their new tests after the issue, so a
   matched test alone is no anchor. Without an anchor the rule abstains:
   `anchored = False` and every candidate is listed in `unplaced`.
   A file is then unplaced when it is not matched, not a test-support
   file, not in the same directory as a matched file, and that shares fewer
   than two leading directories with every matched file. Never extras on their
   own: docs (README*, CHANGELOG*, CHANGES*, HISTORY*, NEWS*, anything under
   docs/, doc/ or .changeset/), lockfiles, files under __snapshots__/, and
   files that rules 1-3 and 6 cover (manifests, config files, deleted test
   files, deleted generated files, binary or large files reported by rule 6).
6. binary_or_large_added (v3). An added file that is binary (GitHub marks it
   binary, or it has no patch, no added or deleted lines and an extension that
   is not a known text extension, which includes no extension), or larger than
   LARGE bytes when the file list gives its size, unless the issue names the
   file or the directory it sits in (_names_closely). GitHub's file list gives no size, so the reason says when the
   size is missing; a binary and an empty file look the same there.
   name = the path.
   v4: an added file with added or deleted lines but no patch (GitHub shows
   no diff when it is too large to show) is large, unless it is generated or
   vendored, or a lockfile (rule 9a reads those).
7. Mass events (v3). Extras of rules 2a, 3a, 3c and 6 whose files were all
   added, or all deleted, are pooled by kind and by their first two
   directories; a pool of MASS or more becomes one extra whose path and name
   are the pool's deepest common directory ("dir/"), with the files in
   `detail`.
1b. version_bump (v4). A changed package version (package.json's top-level
   "version", Cargo [package] or [workspace.package] version, pyproject
   [project] or [tool.poetry] version, a Python __version__) when the issue
   mentions neither the old nor the new version. One extra per new version;
   name = the version, `detail` = its files when there are several.
8. build_output_added (v4). Added files under a build-output directory
   (_BUILD_DIRS), pooled by the path up to that directory; a pool of MASS or
   more is one extra, "N generated files committed", named by the directory.
   Its files are left out of every other rule.
9. stray_file (v4). Added files the issue does not name that look left
   behind: (a) a lockfile of a package manager the repo does not use (the
   change shows another manager's lockfile of the same ecosystem in that
   directory, or the manifest it locks is not added, so the project had no
   such lockfile), unless the issue mentions the manager or the file;
   (b) a backup or editor copy (*.backup, *.bak, *.orig, *.swp, *~); a
   top-level *.md other than README, CHANGELOG, LICENSE, CONTRIBUTING; a
   new top-level file that is not code and that no other changed file names.
   One extra per change: name = the path for one file, else "stray files"
   with the files in `detail`. `Analysis.stray` lists them; `unplaced` is
   unchanged.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import asdict, dataclass, field

RULES_VERSION = 4       # v1, v2 and v3 are frozen in extras_v1.py, extras_v2.py and extras_v3.py; analyse(..., version=1|2|3) runs them
KINDS = ("new_dependency", "ci_or_config", "tests_removed", "generated_code_removed",
         "public_api_removed", "binary_or_large_added", "version_bump", "build_output_added", "stray_file")
MASS = 10               # files of one kind, added or deleted under one directory: one extra
LARGE = 1_000_000       # bytes


@dataclass(frozen=True)
class Extra:
    kind: str
    path: str
    name: str
    why: str
    detail: tuple = ()      # a mass event's files

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Analysis:
    extras: list[Extra]
    named_paths: list[str] = field(default_factory=list)
    anchored: bool = False
    unplaced: list[str] = field(default_factory=list)   # files the rules could not place (rule 5)
    stray: list[str] = field(default_factory=list)      # files rule 9 reports as stray_file (v4)


# ---------------------------------------------------------------- helpers

def _squash(s: str) -> str:
    return s.lower().replace("-", "").replace("_", "")


def _mentions(issue_text: str, name: str) -> bool:
    """Rule text: 'the issue mentions X' (see module docstring)."""
    if not name:
        return False
    for text, needle in ((issue_text.lower(), name.lower()),
                         (_squash(issue_text), _squash(name))):
        if needle and re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", text):
            return True
    return False


def _lines(patch: str | None):
    """Yield (sign, text) for each diff line; sign is '+', '-', ' ' or '@'."""
    if not patch:
        return
    for raw in patch.splitlines():
        if raw.startswith("@@"):
            yield "@", raw
        elif raw[:1] in ("+", "-", " "):
            yield raw[0], raw[1:]
        # '\ No newline at end of file' and anything else: ignored


def _base(path: str) -> str:
    return posixpath.basename(path)


def _dirs(path: str) -> list[str]:
    d = posixpath.dirname(path)
    return d.split("/") if d else []


# ------------------------------------------------- rule 1: new_dependency

_REQ_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._\-]*)")
_QUOTED_REQ = re.compile(r"""["']([A-Za-z0-9][A-Za-z0-9._\-]*)\s*(\[[^\]]*\])?\s*([<>=!~^;@][^"']*)?["']""")
_HAS_VERSION = re.compile(r"[<>=~^!]|@\s|\d")
_TOML_HEADER = re.compile(r"^\s*\[\[?([^\]]+)\]\]?\s*(#.*)?$")
_TOML_KEY = re.compile(r"""^\s*(?:"([^"]+)"|'([^']+)'|([A-Za-z0-9][\w.\-]*))\s*=(?!=)\s*(.*)$""")


def _toml_kv(text):
    m = _TOML_KEY.match(text)
    if not m:
        return None
    return (m.group(1) or m.group(2) or m.group(3)), m.group(4).strip()
_JSON_OPEN = re.compile(r'^\s*"([^"]+)"\s*:\s*\{')
_JSON_PAIR = re.compile(r'^\s*"([^"]+)"\s*:\s*"([^"]*)"')
_NPM_DEP_KEYS = {"dependencies", "devDependencies", "peerDependencies", "optionalDependencies"}
_NPM_VERSION = re.compile(r"^(\^|~|>=?|<=?|=|\*|x$|latest|next|canary|beta|workspace:|file:|link:|npm:|git|github:|https?:|catalog:|\d)")
_NPM_NOT_DEPS = {"name", "version", "main", "module", "types", "typings", "node", "npm", "yarn",
                 "pnpm", "bun", "vscode", "packageManager", "license", "description", "homepage",
                 "author", "type", "browser", "bin", "private", "engines", "electron"}
_CARGO_NOT_DEPS = {"name", "version", "edition", "rust-version", "authors", "description", "license",
                   "repository", "homepage", "readme", "keywords", "categories", "documentation",
                   "publish", "build", "resolver", "members", "exclude", "include", "default-run",
                   "opt-level", "lto", "debug", "codegen-units", "panic", "strip"}
_GO_REQ = re.compile(r"^\s*(?:require\s+)?([A-Za-z0-9][\w.\-~/]*\.[\w.\-~/]+)\s+v\d\S*\s*(//.*)?$")
_GEM = re.compile(r"""^\s*gem\s+['"]([^'"]+)['"]""")
_GRADLE = re.compile(
    r"""^\s*(?:implementation|api|compileOnly|runtimeOnly|testImplementation|testRuntimeOnly|"""
    r"""testCompileOnly|androidTestImplementation|debugImplementation|releaseImplementation|kapt|ksp|"""
    r"""annotationProcessor|classpath|compile|testCompile)\s*\(?\s*(?:platform\s*\(\s*)?"""
    r"""(?:['"]([^'"]+)['"]|(libs\.[\w.]+))""")
_POM_TAG = re.compile(r"<(dependency|plugin|parent|exclusion|project|extension)>")
_POM_ARTIFACT = re.compile(r"<artifactId>\s*([^<\s]+)\s*</artifactId>")


_URLISH = re.compile(r"://|(?<![\w.\-])(?:git|hg|svn|bzr)\+|(?<![\w.\-])(?:github|gitlab|bitbucket|gist):", re.I)
_URL = re.compile(r"(?:(?:git|hg|svn|bzr)\+)?[a-z][a-z0-9+.\-]*://[^\s\"',;]+|(?:github|gitlab|bitbucket|gist):[^\s\"',;]+", re.I)
_NPM_SHORTHAND = re.compile(r"[\w.\-]+/[\w.\-]+(#\S*)?")   # npm reads "owner/repo" as a GitHub repo


def _url_req_name(s: str) -> str | None:
    """The package a requirements line with a URL installs (egg=, `name @ url`, the URL's last part)."""
    m = re.search(r"[#&]egg=([A-Za-z0-9][\w.\-]*)", s)
    if m:
        return m.group(1)
    m = re.match(r"([A-Za-z0-9][\w.\-]*)\s*(\[[^\]]*\])?\s*@\s*\S", s)
    if m:
        return m.group(1)
    u = _URL.search(s)
    if not u:
        return None
    if s.startswith("-") and not s.startswith(("-e", "--editable")):
        return u.group(0)                      # --index-url, --extra-index-url, --find-links
    last = u.group(0).split("#")[0].split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    return last.removesuffix(".git") or u.group(0)


def _url_source(kind: str, text: str) -> str | None:
    """The URL or VCS source on a dependency line, or None for an index version."""
    if kind == "npm":
        p = _JSON_PAIR.match(text)
        value = p.group(2) if p else ""
        if _URLISH.match(value) or _URL.match(value) or _NPM_SHORTHAND.fullmatch(value):
            return value
        return None
    if not _URLISH.search(text):
        return None
    u = _URL.search(text)
    return u.group(0) if u else text.strip()


def _manifest_kind(path: str) -> str | None:
    b = _base(path)
    if re.fullmatch(r"requirements[\w.\-]*\.(txt|in)", b) or (
            "requirements" in _dirs(path) and b.endswith((".txt", ".in"))):
        return "requirements"
    return {"pyproject.toml": "pyproject", "package.json": "npm", "go.mod": "go",
            "Cargo.toml": "cargo", "Gemfile": "gem", "pom.xml": "pom",
            "build.gradle": "gradle", "build.gradle.kts": "gradle"}.get(b)


def _deps_requirements(patch):
    for sign, text in _lines(patch):
        s = text.strip()
        if sign not in "+-" or not s or s.startswith("#"):
            continue
        if _URLISH.search(s):                 # VCS, URL or index option: v1 skipped these
            name = _url_req_name(s)
            if name:
                yield sign, name, text
            continue
        if s.startswith("-"):
            continue
        m = _REQ_LINE.match(s)
        if m:
            yield sign, m.group(1), text


def _deps_pyproject(patch):
    section = None      # None = unknown (hunk starts mid-file)
    array_key = None
    for sign, text in _lines(patch):
        if sign == "@":
            section, array_key = None, None
            continue
        h = _TOML_HEADER.match(text)
        if h and "=" not in text:
            section, array_key = h.group(1).strip().strip('"'), None
            continue
        kv = _toml_kv(text)
        if kv:
            key, value = kv
            if value.startswith("["):
                array_key = key if "]" not in value else None
            dep_array = _pyproject_dep_array(section, key) or (     # v4: a one-line array, section unknown
                section is None and key in _ONE_LINE_DEP_KEYS and value.startswith("[") and "]" in value)
            if section is not None and re.search(r"(^|\.)(dev-)?dependencies$", section) \
                    and section.startswith("tool.") and not value.startswith("["):
                if sign in "+-" and key.lower() != "python":
                    yield sign, key, text           # poetry style: name = "^1.0"
                continue
            if dep_array and sign in "+-":
                for q in _QUOTED_REQ.finditer(value):
                    yield sign, q.group(1), text
            continue
        if text.strip().startswith("]"):
            array_key = None
            continue
        if sign not in "+-":
            continue
        q = _QUOTED_REQ.search(text)
        if not q:
            continue
        known = section is not None and array_key is not None
        if known and _pyproject_dep_array(section, array_key):
            yield sign, q.group(1), text
        elif not known and q.group(3) and _HAS_VERSION.search(q.group(3)):
            yield sign, q.group(1), text            # unknown place: needs a version


_ONE_LINE_DEP_KEYS = ("dependencies", "dev-dependencies")


def _pyproject_dep_array(section, key) -> bool:
    if section is None or key is None:
        return False
    if section == "project":
        return key == "dependencies"
    if section in ("project.optional-dependencies", "dependency-groups"):
        return True
    if section == "build-system":
        return key == "requires"
    return key in ("dependencies", "dev-dependencies") or section.endswith("dependencies")


def _npm_pairs(patch):
    """Yield (sign, block, key, value, text) for each "key": "value" line of package.json."""
    stack: list[str | None] = []
    for sign, text in _lines(patch):
        if sign == "@":
            stack = []
            continue
        o = _JSON_OPEN.match(text)
        if o:
            if text.count("{") > text.count("}"):
                stack.append(o.group(1))
            continue
        if re.match(r"^\s*\}", text):
            if stack:
                stack.pop()
            else:
                stack = ["<top>"]             # left an unknown block
            continue
        p = _JSON_PAIR.match(text)
        if p and sign in "+-":
            yield sign, (stack[-1] if stack else None), p.group(1), p.group(2), text


def _deps_npm(patch):
    for sign, block, key, value, text in _npm_pairs(patch):
        if block in _NPM_DEP_KEYS:
            yield sign, key, text
        elif block is None and key not in _NPM_NOT_DEPS and _NPM_VERSION.match(value):
            yield sign, key, text                   # unknown block: needs a version


def _deps_go(patch):
    for sign, text in _lines(patch):
        if sign not in "+-" or "=>" in text:
            continue
        m = _GO_REQ.match(text)
        if m and not (m.group(2) or "").replace(" ", "").startswith("//indirect"):
            yield sign, m.group(1), text


def _deps_cargo(patch):
    section = None
    for sign, text in _lines(patch):
        if sign == "@":
            section = None
            continue
        h = _TOML_HEADER.match(text)
        if h and "=" not in text:
            section = h.group(1).strip()
            m = re.fullmatch(r"(?:.*\.)?(?:dev-|build-)?dependencies\.([\w\-]+)", section)
            if m and sign in "+-":
                yield sign, m.group(1), text
            continue
        kv = _toml_kv(text)
        if not kv or sign not in "+-":
            continue
        full_key, value = kv
        key = full_key.split(".")[0]
        if section is not None:
            if re.search(r"(^|\.)(dev-|build-)?dependencies$", section):
                yield sign, key, text
        elif key not in _CARGO_NOT_DEPS and (
                re.match(r"""["'][\^~=<>*]?\d""", value) or
                re.match(r"\{.*\b(version|path|git|workspace)\b", value) or
                full_key.endswith(".workspace")):
            yield sign, key, text                   # unknown section: needs a version


def _deps_gem(patch):
    for sign, text in _lines(patch):
        m = _GEM.match(text)
        if m and sign in "+-":
            yield sign, m.group(1), text


def _deps_pom(patch):
    context = None
    for sign, text in _lines(patch):
        if sign == "@":
            context = None
            continue
        t = _POM_TAG.search(text)
        if t:
            context = t.group(1)
        a = _POM_ARTIFACT.search(text)
        if a and context == "dependency" and sign in "+-":
            yield sign, a.group(1), text


def _deps_gradle(patch):
    for sign, text in _lines(patch):
        m = _GRADLE.match(text)
        if not m or sign not in "+-":
            continue
        if m.group(1):
            parts = m.group(1).split(":")
            if len(parts) >= 2:
                yield sign, parts[1], text
        else:
            yield sign, m.group(2), text


_DEP_PARSERS = {"requirements": _deps_requirements, "pyproject": _deps_pyproject,
                "npm": _deps_npm, "go": _deps_go, "cargo": _deps_cargo, "gem": _deps_gem,
                "pom": _deps_pom, "gradle": _deps_gradle}


def _side(patch: str, keep: str) -> str:
    """One side of the diff: '+' keeps the new file's lines, '-' the old file's."""
    return "\n".join(raw for raw in patch.splitlines()
                     if raw.startswith(("@@", " ", keep)) and not raw.startswith(("+++", "---")))


def _deps_go_all(patch):
    """go.mod requirements, `// indirect` included (what the old file already lists)."""
    for sign, text in _lines(patch):
        m = _GO_REQ.match(text) if sign in "+-" and "=>" not in text else None
        if m:
            yield sign, m.group(1), text


def _old_names(kind: str, patch: str) -> set[str]:
    """Packages the old file lists on the lines the diff shows (removed or unchanged)."""
    old = "\n".join(raw if raw.startswith("@@") else "-" + raw[1:] for raw in patch.splitlines()
                    if raw.startswith(("@@", " ", "-")) and not raw.startswith("---"))
    parse = _deps_go_all if kind == "go" else _DEP_PARSERS[kind]
    return {n.lower() for sign, n, _ in parse(old) if sign == "-"}


_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{3,}\b")


def _title_acronyms(issue_text: str) -> set[str]:
    title = issue_text.strip().split("\n", 1)[0]
    return {a.lower() for a in _ACRONYM.findall(title) if sum(c.isalpha() for c in a) >= 3}


_PACKAGE_MANIFESTS = {"cargo", "npm", "pyproject"}     # manifests that declare their own package (v4)
_QUOTED = re.compile(r"""["']([^"']+)["']""")


def _package_name(kind: str, patch: str) -> str | None:
    """The package a manifest declares: Cargo [package] name, package.json's top-level "name", or pyproject
    [project] or [tool.poetry] name."""
    if kind == "npm":
        return next((value for sign, block, key, value, _ in _npm_pairs(patch) if block is None and key == "name"), None)
    section = None
    for sign, text in _lines(patch):
        h = _TOML_HEADER.match(text)
        if h and "=" not in text:
            section = h.group(1).strip().strip('"')
            continue
        kv = _toml_kv(text)
        m = _QUOTED.match(kv[1]) if kv and kv[0] == "name" and section in ("package", "project", "tool.poetry") else None
        if m:
            return m.group(1)
    return None


def _new_package(issue_text, f, kind, parse):
    """v4: a manifest the change adds belongs to a new package; its dependencies come with it."""
    deps = {n.lower() for sign, n, _ in parse(_side(f["patch"], "+")) if sign == "+"}
    name = _package_name(kind, f["patch"])
    if not name and not deps:
        return None                                     # tool settings only (rule 2c reads them)
    name = name or _base(posixpath.dirname(f["filename"])) or f["filename"]
    if _mentions(issue_text, name) or _mentions(issue_text, name.rsplit("/", 1)[-1]):
        return None
    n = len(deps)
    return Extra("new_dependency", f["filename"], name,
                 f"adds package {name} (a new {_base(f['filename'])} with {n} "
                 f"{'dependency' if n == 1 else 'dependencies'}); the issue does not name it")


def _new_dependencies(issue_text, files):
    out = []
    acronyms = _title_acronyms(issue_text)
    for f in files:
        kind = _manifest_kind(f["filename"])
        if not kind or not f.get("patch"):
            continue
        parse = _DEP_PARSERS[kind]
        if f.get("status") == "added" and kind in _PACKAGE_MANIFESTS:
            out += [e for e in [_new_package(issue_text, f, kind, parse)] if e]
            continue
        added = [(n, t) for sign, n, t in parse(_side(f["patch"], "+")) if sign == "+"]
        gone = [(n, t) for sign, n, t in parse(_side(f["patch"], "-")) if sign == "-"]
        removed = {n.lower() for n, _ in gone} | _old_names(kind, f["patch"])
        removed_sources = {_url_source(kind, t) for _, t in gone} - {None}
        seen = set()
        for name, text in added:
            low = name.lower()
            source = _url_source(kind, text)
            if low in seen:
                continue
            if source is None and low in removed:
                continue                       # a version bump or a move
            if source is not None and source in removed_sources:
                continue                       # the same URL, moved
            seen.add(low)
            if source is not None:
                if source.lower() in issue_text.lower():
                    continue
                out.append(Extra("new_dependency", f["filename"], name,
                                 f"installs {name} from {source}, not from the package index; "
                                 "the issue does not name that source"))
                continue
            short = name.rsplit("/", 1)[-1] if kind in ("npm", "go") else name
            if _mentions(issue_text, name) or (short != name and _mentions(issue_text, short)):
                continue
            if any(a in _squash(name) for a in acronyms):
                continue                       # the title names what the package implements
            out.append(Extra("new_dependency", f["filename"], name,
                             f"adds package {name}; the issue does not name it"))
    return out


# --------------------------------------------- rule 1b: version_bump (v4)

_PY_VERSION = re.compile(r"""^\s*__version__\s*=\s*["']([^"']+)["']""")
_VERSION_SECTIONS = {"package", "workspace.package", "project", "tool.poetry"}


def _versions(f: dict, sign: str) -> list[str]:
    """The package versions on one side ('+' or '-') of f's diff."""
    kind, patch = _manifest_kind(f["filename"]), f.get("patch")
    if kind == "npm":
        return [value for s, block, key, value, _ in _npm_pairs(patch) if s == sign and block is None and key == "version"]
    if kind in ("cargo", "pyproject"):
        out, section = [], None
        for s, text in _lines(patch):
            if s == "@":
                section = None
                continue
            h = _TOML_HEADER.match(text)
            if h and "=" not in text:
                section = h.group(1).strip().strip('"')
                continue
            kv = _toml_kv(text)
            m = _QUOTED.match(kv[1]) if s == sign and kv and kv[0] == "version" and section in _VERSION_SECTIONS else None
            if m:
                out.append(m.group(1))
        return out
    if _ext(f["filename"]) in _PY_EXT:
        return [m.group(1) for s, t in _lines(patch) if s == sign for m in [_PY_VERSION.match(t)] if m]
    return []


def _version_bumps(issue_text, files):
    bumps = {}
    for f in files:
        if f.get("status") == "added" or not f.get("patch"):
            continue
        old = _versions(f, "-")
        for v in _versions(f, "+"):
            if old and v not in old:
                bumps.setdefault(v, []).append((f["filename"], old[0]))
    out = []
    for v, hits in sorted(bumps.items()):
        olds = sorted({o for _, o in hits})
        if _mentions(issue_text, v) or any(_mentions(issue_text, o) for o in olds):
            continue
        paths = tuple(sorted(p for p, _ in hits))
        out.append(Extra("version_bump", paths[0], v,
                         f"changes the package version from {', '.join(olds)} to {v}; the issue names neither version",
                         paths if len(paths) > 1 else ()))
    return out


# --------------------------------------------------- rule 2: ci_or_config

_CI_WORDS = ("ci", "workflow", "workflows", "pipeline", "pipelines", "github actions", "gitlab-ci")
_DOCKER_WORDS = ("docker", "dockerfile", "container", "containers", "compose")
_LINT_WORDS = ("lint", "linter", "linting", "eslint", "prettier", "ruff", "flake8", "pylint",
               "mypy", "formatter", "stylelint", "biome", "golangci", "rubocop", "editorconfig",
               "markdownlint")

# (description, test on (path, basename), keywords that count as a mention)
_CONFIG_RULES = [
    ("dependency-update config", lambda p, b: p in (".github/dependabot.yml", ".github/dependabot.yaml",
                                                    ".github/renovate.json", ".github/renovate.json5")
     or b in ("renovate.json", "renovate.json5", ".renovaterc", ".renovaterc.json"),
     ("dependabot", "renovate")),
    ("CI config", lambda p, b: b in (".gitlab-ci.yml", ".gitlab-ci.yaml", ".travis.yml",
                                     "azure-pipelines.yml", "Jenkinsfile", "bitbucket-pipelines.yml")
     or p.startswith((".github/workflows/", ".gitlab/ci/", ".circleci/", ".buildkite/")), _CI_WORDS),
    ("container config", lambda p, b: b.startswith("Dockerfile") or b.endswith(".dockerfile")
     or b == ".dockerignore" or re.fullmatch(r"(docker-)?compose[\w.\-]*\.ya?ml", b) is not None,
     _DOCKER_WORDS),
    ("build config", lambda p, b: b in ("Makefile", "GNUmakefile", "makefile", "tox.ini", "setup.cfg",
                                        "noxfile.py", "justfile", "Justfile")
     or re.fullmatch(r"tsconfig[\w.\-]*\.json", b) is not None,
     ("makefile", "build", "tox", "nox", "setup.cfg", "tsconfig", "compile", "compiler")),
    ("lint config", lambda p, b: b in (".pre-commit-config.yaml", ".flake8", ".pylintrc", "pylintrc",
                                       "ruff.toml", ".ruff.toml", "mypy.ini", ".mypy.ini",
                                       ".golangci.yml", ".golangci.yaml", ".rubocop.yml", "biome.json",
                                       "biome.jsonc", ".editorconfig", ".prettierignore",
                                       ".eslintignore")
     or re.fullmatch(r"\.(eslintrc|prettierrc|stylelintrc|markdownlint)[\w.\-]*", b) is not None
     or re.fullmatch(r"(eslint|prettier|stylelint)\.config\.\w+", b) is not None,
     _LINT_WORDS + ("pre-commit",)),
]


def _config_kind(path: str):
    b = _base(path)
    for desc, test, words in _CONFIG_RULES:
        if test(path, b):
            return desc, words
    return None


def _ci_or_config(issue_text, files):
    out = []
    for f in files:
        ck = _config_kind(f["filename"])
        if not ck:
            continue
        desc, words = ck
        if _mentions(issue_text, _base(f["filename"])) or any(_mentions(issue_text, w) for w in words):
            continue
        out.append(Extra("ci_or_config", f["filename"], f["filename"],
                         f"changes {desc}; the issue does not mention it"))
    return out + _npm_lifecycle(issue_text, files) + _pyproject_lint(issue_text, files)


_LIFECYCLE = {"preinstall", "install", "postinstall", "prepare", "prepublish"}   # npm runs these on install


def _npm_lifecycle(issue_text, files):
    out = []
    for f in files:
        if _manifest_kind(f["filename"]) != "npm" or not f.get("patch"):
            continue
        pairs = {"+": set(), "-": set()}
        for sign, block, key, value, _ in _npm_pairs(f["patch"]):
            if block in ("scripts", None) and key in _LIFECYCLE:
                pairs[sign].add((key, value))
        for key, value in sorted(pairs["+"] - pairs["-"]):
            if not _mentions(issue_text, key):
                out.append(Extra("ci_or_config", f["filename"], key,
                                 f"adds or changes the npm {key} script, which runs on install"))
    return out


_LINT_SECTION = re.compile(r"tool\.(ruff|flake8|pylint|mypy|pyright|basedpyright|black|isort|bandit|pydocstyle"
                           r"|codespell|pycodestyle|autopep8|pylama)(\..*)?")
_IGNORE_KEYS = {"ignore", "extend-ignore", "per-file-ignores", "extend-per-file-ignores", "disable",
                "unfixable", "extend-unfixable"}


def _pyproject_lint(issue_text, files):
    """Lint settings changed inside pyproject.toml (a manifest, so rule 2's file list misses them)."""
    out = []
    for f in files:
        if _base(f["filename"]) != "pyproject.toml" or not f.get("patch"):
            continue
        section, array_key, hit = None, None, None
        for sign, text in _lines(f["patch"]):
            if sign == "@":
                ctx = _TOML_HEADER.match(text.split("@@")[-1].strip() or "-")
                section, array_key = (ctx.group(1).strip() if ctx else None), None
                continue
            h = _TOML_HEADER.match(text)
            if h and "=" not in text:
                section, array_key = h.group(1).strip().strip('"'), None
                continue
            kv = _toml_kv(text)
            key = kv[0] if kv else None
            if kv and kv[1].startswith("[") and "]" not in kv[1]:
                array_key = key
            elif text.strip().startswith("]"):
                array_key = None
            if sign not in "+-":
                continue
            lint = section is not None and _LINT_SECTION.fullmatch(section)
            if lint or (section is None and (key in _IGNORE_KEYS or array_key in _IGNORE_KEYS)):
                hit = section or "an ignore list"
                break
        if hit and not (_mentions(issue_text, "pyproject.toml")
                        or any(_mentions(issue_text, w) for w in _LINT_WORDS + ("pre-commit",))):
            out.append(Extra("ci_or_config", f["filename"], f["filename"],
                             f"changes lint settings ({hit}); the issue does not mention them"))
    return out


# -------------------------------------------------- rule 3: tests_removed

_CODE_EXT = {"py", "pyi", "js", "jsx", "ts", "tsx", "mjs", "cjs", "mts", "cts", "go", "java", "kt",
             "kts", "rb", "rs", "cs", "php", "swift", "scala", "c", "cc", "cpp", "h", "hpp", "m",
             "ex", "exs", "dart", "vue", "svelte", "lua", "r", "jl", "clj", "groovy"}
_TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "testing", "e2e", "__test__"}
_TEST_NAME = re.compile(r"(test_.+|.+_test|.+\.test|.+\.spec|.+_spec|.+Tests?|.+Spec|test|tests)\.[A-Za-z0-9]+")
_TEST_DEF = re.compile(
    r"^\s*(async\s+)?def\s+test\w*\s*\("                                # Python, Ruby minitest
    r"|^\s*(it|test|describe|context|specify)(\.(only|skip|each|concurrent|todo|failing))?\s*[(`]"  # JS
    r"|^\s*(it|test|describe|context|specify)\s+['\"]"                  # RSpec, minitest
    r"|^\s*func\s+(Test|Benchmark|Fuzz|Example)\w*\s*\("               # Go
    r"|@Test\b|@ParameterizedTest\b"                                    # JUnit
    r"|#\[(\w+::)?test\]"                                               # Rust
    r"|\[(Fact|Theory|Test|TestMethod|TestCase)\b")                     # C#
_ASSERT = re.compile(
    r"\bassert|\bexpect\s*\(|\.should\b|\bt\.(Error|Errorf|Fatal|Fatalf|Fail|FailNow)\b"
    r"|\brequire\.[A-Z]\w*\(|\bXCTAssert|\bEXPECT_[A-Z]|\bASSERT_[A-Z]|\bself\.fail\(|\bpytest\.raises\b")


def _ext(path: str) -> str:
    b = _base(path)
    return b.rsplit(".", 1)[-1].lower() if "." in b else ""


_GENERATED_DIRS = {"generated", "__generated__", "_generated", "vendor", "vendored", "third_party",
                   "third-party", "node_modules", "site-packages"}
_GENERATED_NAME = re.compile(r".+(?:[._]generated\.\w+|\.g\.\w+|_pb2(?:_grpc)?\.pyi?|\.pb(?:\.gw)?\.(?:go|cc|h))")


def is_generated(path: str) -> bool:
    """Generated or vendored code (rule 3, v3)."""
    return (any(d.lower() in _GENERATED_DIRS for d in _dirs(path))
            or _GENERATED_NAME.fullmatch(_base(path)) is not None)


def is_test_file(path: str) -> bool:
    if _ext(path) not in _CODE_EXT or is_generated(path):
        return False
    return _TEST_NAME.fullmatch(_base(path)) is not None or any(d in _TEST_DIRS for d in _dirs(path))


def _count(patch, sign, pattern):
    return sum(1 for s, t in _lines(patch) if s == sign and pattern.search(t))


def _tests_removed(issue_text, files):
    out = []
    tests = [f for f in files if is_test_file(f["filename"])]
    added_names = {_base(f["filename"]) for f in tests if f.get("status") == "added"}
    net = {}
    for label, pat in (("test definitions", _TEST_DEF), ("assertion lines", _ASSERT)):
        net[label] = sum(_count(f.get("patch"), "+", pat) - _count(f.get("patch"), "-", pat) for f in tests)
    gone_sources = {_squash(_stem(f["filename"])) for f in files
                    if f.get("status") == "removed" and _ext(f["filename"]) in _CODE_EXT
                    and not is_test_file(f["filename"])}
    lost, gained = {}, {}             # test definitions per directory: in deleted files, net in the rest
    for f in tests:
        d = posixpath.dirname(f["filename"])
        minus, plus = _count(f.get("patch"), "-", _TEST_DEF), _count(f.get("patch"), "+", _TEST_DEF)
        if f.get("status") == "removed":
            lost[d] = lost.get(d, 0) + minus
        else:
            gained[d] = gained.get(d, 0) + plus - minus
    for f in tests:
        path = f["filename"]
        b, st = _base(path), _stem(path)
        if _mentions(issue_text, b) or _mentions(issue_text, b.split(".")[0]):
            continue
        if f.get("status") == "removed":
            d = posixpath.dirname(path)
            if b in added_names or _squash(st) in gone_sources:
                continue              # moved, or deleted together with its source file
            if lost.get(d, 0) > 0 and gained.get(d, 0) >= lost[d]:
                continue              # rewritten: the directory gains as many test definitions
            out.append(Extra("tests_removed", path, path, "deletes this test file"))
            continue
        for label, pat in (("test definitions", _TEST_DEF), ("assertion lines", _ASSERT)):
            minus, plus = _count(f.get("patch"), "-", pat), _count(f.get("patch"), "+", pat)
            if minus > plus and net[label] < 0:
                out.append(Extra("tests_removed", path, path,
                                 f"removes {minus - plus} more {label} than it adds"))
                break
    return out


# --------------------------------------------- rule 4: public_api_removed

_PY_DEF = re.compile(r"^(?: {0,4}|\t)(?:async\s+def|def|class)\s+([A-Za-z]\w*)")
_JS_EXPORT = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(?:function\s*\*?|class|const|let|var|interface|type|enum|namespace)\s+([A-Za-z_$][\w$]*)")
_JS_EXPORT_LIST = re.compile(r"^\s*export\s+(?:type\s+)?\{([^}]*)\}")
_PY_EXT = {"py", "pyi"}
_JS_EXT = {"js", "jsx", "ts", "tsx", "mjs", "cjs", "mts", "cts"}


def _symbols(text: str, ext: str) -> list[str]:
    if ext in _PY_EXT:
        m = _PY_DEF.match(text)
        return [m.group(1)] if m else []
    if ext in _JS_EXT:
        m = _JS_EXPORT.match(text)
        if m:
            return [m.group(1)]
        m = _JS_EXPORT_LIST.match(text)
        if m:
            names = []
            for part in m.group(1).split(","):
                part = part.strip()
                if part:
                    names.append(part.split(" as ")[-1].strip().removeprefix("type ").strip())
            return [n for n in names if n and n != "default"]
    return []


_STORY = re.compile(r"(?:(?<![A-Za-z])[Ss]|(?<=[a-z])S)tor(?:y|ies)")    # story, Story, stories; not history
_HELPER_DIRS = {"__mocks__", "fixtures", "__fixtures__"}


def _not_api(path: str) -> bool:
    """v4: story, mock and fixture helpers are not package API."""
    return any(_STORY.search(part) for part in path.split("/")) or any(d.lower() in _HELPER_DIRS for d in _dirs(path))


def _public_api_removed(issue_text, files):
    defined_again = set()
    for f in files:
        for s, t in _lines(f.get("patch")):
            if s in ("+", " "):          # v4: a context line is at the head too
                defined_again.update(_symbols(t, _ext(f["filename"])))
    twins = {_squash(_stem(f["filename"])) for f in files if f.get("status") in ("added", "renamed")}
    out = []
    for f in files:
        path, ext = f["filename"], _ext(f["filename"])
        if ext not in _PY_EXT | _JS_EXT or is_test_file(path) or is_generated(path):
            continue
        if _not_api(path):
            continue
        if f.get("status") == "removed" and _squash(_stem(path)) in twins:
            continue                     # v4: moved, a file of the same stem is added or renamed
        seen = set()
        for s, t in _lines(f.get("patch")):
            if s != "-":
                continue
            for name in _symbols(t, ext):
                if name in seen or name in defined_again or _mentions(issue_text, name):
                    continue
                seen.add(name)
                out.append(Extra("public_api_removed", path, name,
                                 f"removes public {'export' if ext in _JS_EXT else 'def/class'} {name}"))
    return out


# ----------------------------------------------- rule 5: file_outside_ask

_LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock",
              "go.sum", "Gemfile.lock", "uv.lock", "composer.lock", "Pipfile.lock", "bun.lockb",
              "bun.lock", "pdm.lock", "npm-shrinkwrap.json", "flake.lock", "mix.lock",
              "pubspec.lock", "Podfile.lock", "gradle.lockfile", "packages.lock.json"}
_DOC_NAME = re.compile(r"(README|CHANGELOG|CHANGES|HISTORY|NEWS)([.\-_].*)?", re.IGNORECASE)
_GENERIC_STEMS = {
    "index", "main", "mod", "lib", "app", "init", "__init__", "__main__", "utils", "util", "helpers",
    "helper", "common", "core", "types", "type", "config", "constants", "const", "setup", "base",
    "test", "tests", "spec", "api", "server", "client", "page", "layout", "style", "styles",
    "global", "globals", "default", "defaults", "model", "models", "schema", "schemas", "data",
    "run", "build", "update", "get", "set", "new", "add", "list", "create", "delete", "remove",
    "fix", "change", "use", "make", "start", "check", "error", "errors", "file", "files", "service",
    "services", "handler", "handlers", "routes", "router", "views", "view", "settings", "options",
    "interface", "interfaces", "default", "version", "readme", "license", "package", "conftest",
}
_GENERIC_DIRS = {
    "src", "lib", "libs", "app", "apps", "packages", "pkg", "internal", "cmd", "components", "utils",
    "util", "common", "core", "test", "tests", "__tests__", "spec", "public", "static", "assets",
    "scripts", "server", "client", "web", "frontend", "backend", "main", "java", "kotlin", "resources",
    "python", "js", "ts", "go", "source", "sources", "include", "crates", "modules", "api", "services",
    "service", "routes", "models", "views", "hooks", "types", "config", "page", "pages", "com", "org",
    "tools", "bin", "build", "dist", "examples", "example", "shared", "features", "feature", "ui",
    "data", "helpers", "github", "gitlab", "workflows", "docs", "doc", "test-utils", "fixtures",
}
_PATH_TOKEN = re.compile(r"[\w.@\-]+(?:/[\w.@\-]+)+/?|[\w@\-]+(?:\.[\w\-]+)*\.[A-Za-z][A-Za-z0-9]{0,5}\b")
_FORGE_URL = re.compile(r"^(?:www\.)?(?:github\.com|gitlab\.com)/(.*)$")
_BACKTICK = re.compile(r"`([^`\n]+)`")
_DOTTED = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[_\-][A-Za-z0-9]+)*")


def _forms(s: str) -> set[str]:
    n = _squash(s)
    forms = {n} if n else set()
    if len(n) > 3 and n.endswith("s"):
        forms.add(n[:-1])
    return forms


@dataclass
class _IssueTokens:
    paths: set[str]
    words: set[str]


def issue_tokens(issue_text: str) -> _IssueTokens:
    """Paths (rule 5a) and tokens (rules 5b, 5c) of the issue text."""
    paths, words = set(), set()
    for m in _PATH_TOKEN.finditer(issue_text):
        t = m.group(0).strip(".").lower().removeprefix("./").rstrip("/")
        forge = _FORGE_URL.match(t)
        if forge:   # a forge link names a file only through /blob/<ref>/<path>
            parts = forge.group(1).split("/")
            if len(parts) > 4 and parts[2] in ("blob", "tree"):
                t = "/".join(parts[4:])
            else:
                continue
        if not t:
            continue
        paths.add(t)
        for part in t.split("/"):
            words |= _forms(part.split(".")[0])
    for m in _BACKTICK.finditer(issue_text):
        for part in re.split(r"[^A-Za-z0-9_\-]+", m.group(1)):
            if len(part) >= 2:
                words |= _forms(part)
    for m in _DOTTED.finditer(issue_text):
        for part in m.group(0).split("."):
            if len(part) >= 3:
                words |= _forms(part)
    seq = []
    for m in _WORD.finditer(issue_text):
        w = m.group(0)
        words |= _forms(w)
        for piece in re.split(r"[_\-]", w):
            if len(piece) >= 3:
                words |= _forms(piece)
        seq.append(w)
    for i in range(len(seq)):
        words |= _forms("".join(seq[i:i + 2])) | _forms("".join(seq[i:i + 3]))
    return _IssueTokens(paths, {w for w in words if len(w) >= 2})


def _stem(path: str) -> str:
    s = _base(path).split(".")[0]
    s = re.sub(r"^(test_|tests_)", "", s)
    s = re.sub(r"(_test|_tests|_spec|Tests|Test|Spec)$", "", s)
    return s


def _path_named(path: str, toks: _IssueTokens) -> bool:
    p = path.lower()
    for t in toks.paths:
        if p == t or p.endswith("/" + t) or t.endswith("/" + p) or ("/" + p).find("/" + t + "/") >= 0:
            return True
    return False


def _token_named(name: str, toks: _IssueTokens, generic: set[str]) -> bool:
    if name.lower() in generic or len(_squash(name)) < 3:
        return False   # generic or tiny names match only through a path (5a)
    return bool(_forms(name) & toks.words)


def _exempt(path: str) -> bool:
    b = _base(path)
    return (b in _LOCKFILES or _DOC_NAME.fullmatch(b) is not None
            or any(d.lower() in ("docs", "doc", "__snapshots__", ".changeset") for d in _dirs(path)))


def _named_files(issue_text, files, package: str = "") -> set[str]:
    toks = issue_tokens(issue_text)
    named = set()
    for f in files:
        for path in filter(None, (f["filename"], f.get("previous_filename"))):
            own = lambda n: bool(package) and _squash(n) == package   # the project's own name
            if (_path_named(path, toks)
                    or (not own(_stem(path)) and _token_named(_stem(path), toks, _GENERIC_STEMS))
                    or any(_token_named(d, toks, _GENERIC_DIRS) for d in _dirs(path) if not own(d))):
                named.add(f["filename"])
    named_stems = {_squash(_stem(p)) for p in named if not is_test_file(p)}
    for f in files:
        if is_test_file(f["filename"]) and _squash(_stem(f["filename"])) in named_stems:
            named.add(f["filename"])
    return named


_SUPPORT_DIRS = _TEST_DIRS | {"fixtures", "__fixtures__", "testdata", "test-data", "__mocks__", "mocks"}


def _test_support(path: str) -> bool:
    return is_test_file(path) or any(d.lower() in _SUPPORT_DIRS for d in _dirs(path))


def _near(path: str, named: set[str]) -> bool:
    """Same directory as a named file, or at least two leading directories in common with one."""
    a = _dirs(path)
    for q in named:
        b = _dirs(q)
        if a == b:
            return True
        common = 0
        for x, y in zip(a, b):
            if x != y:
                break
            common += 1
        if common >= 2:
            return True
    return False


def _unplaced(issue_text, files, covered: set[str], package: str = ""):
    """Rule 5: (unplaced files, named files, anchored)."""
    candidates = [f["filename"] for f in files
                  if not _exempt(f["filename"]) and f["filename"] not in covered]
    keep = set(candidates)
    named = _named_files(issue_text, [f for f in files if f["filename"] in keep], package)
    if all(_test_support(p) for p in named):
        return sorted(candidates), [], False   # no anchor, or only tests the agent named after the issue
    out = [p for p in candidates
           if p not in named and not _near(p, named) and not _test_support(p)]
    return sorted(out), sorted(named), True


# ------------------------------------- rule 3c: generated_code_removed (v3)

def _names_closely(path: str, toks: _IssueTokens, package: str = "") -> bool:
    """The issue names this file (its path or stem) or the directory it sits in; an ancestor is not enough
    (rules 3c and 6: an issue that names a whole package does not name every file deleted or added in it)."""
    p, parent = path.lower(), posixpath.dirname(path).lower()
    for t in toks.paths:
        if p == t or p.endswith("/" + t) or t.endswith("/" + p) or (parent and (t == parent or parent.endswith("/" + t))):
            return True
    own = lambda n: bool(package) and _squash(n) == package
    d = _dirs(path)
    return ((not own(_stem(path)) and _token_named(_stem(path), toks, _GENERIC_STEMS))
            or (bool(d) and not own(d[-1]) and _token_named(d[-1], toks, _GENERIC_DIRS)))


def _generated_code_removed(issue_text, files, package: str = ""):
    toks = issue_tokens(issue_text)
    return [Extra("generated_code_removed", f["filename"], f["filename"], "deletes this generated or vendored file")
            for f in files if f.get("status") == "removed" and is_generated(f["filename"])
            and not _names_closely(f["filename"], toks, package)]


# -------------------------------------- rule 6: binary_or_large_added (v3)

_TEXT_EXT = _CODE_EXT | {
    "md", "markdown", "mdx", "rst", "txt", "adoc", "asciidoc", "tex", "bib", "json", "jsonc", "json5", "jsonl",
    "yaml", "yml", "toml", "ini", "cfg", "conf", "config", "properties", "env", "example", "sample", "template",
    "tpl", "tmpl", "j2", "jinja", "jinja2", "mustache", "hbs", "ejs", "erb", "xml", "xsd", "xsl", "xaml", "resx",
    "html", "htm", "xhtml", "css", "scss", "sass", "less", "styl", "svg", "csv", "tsv", "sql", "graphql", "gql",
    "proto", "sh", "bash", "zsh", "fish", "ps1", "psm1", "psd1", "bat", "cmd", "tf", "tfvars", "hcl", "bicep",
    "tsp", "csproj", "fsproj", "vbproj", "props", "targets", "sln", "gradle", "pom", "mod", "sum", "lock",
    "pem", "crt", "pub", "patch", "diff", "log", "ipynb", "snap", "http", "razor", "cshtml", "vb", "fs", "fsi",
    "fsx", "ml", "mli", "hs", "erl", "hrl", "nim", "zig", "pl", "pm", "cmake", "mk", "in", "am", "ac", "service",
    "plist", "po", "pot", "vtt", "srt", "rake", "gemspec", "podspec", "nix", "dhall", "cue", "rego", "sol",
    "gitignore", "gitattributes", "gitkeep", "keep", "gitmodules", "nojekyll", "typed", "dockerignore",
    "npmignore", "npmrc", "nvmrc", "editorconfig", "prettierrc", "eslintrc", "babelrc", "browserslistrc",
    "eslintignore", "prettierignore", "flake8", "pylintrc", "coveragerc", "rc",
}


def _binary_or_large_added(issue_text, files, package: str = ""):
    out, toks = [], issue_tokens(issue_text)
    for f in files:
        if f.get("status") != "added":
            continue
        size = f.get("size") if isinstance(f.get("size"), int) else None
        large = size is not None and size > LARGE
        no_lines = not f.get("patch") and not f.get("additions") and not f.get("deletions")
        marked = f.get("binary") is True
        hidden = (not f.get("patch") and not no_lines and not is_generated(f["filename"])   # v4: too large to show
                  and _base(f["filename"]) not in _LOCKFILES)
        if not (large or marked or hidden or (no_lines and _ext(f["filename"]) not in _TEXT_EXT)):
            continue
        if _names_closely(f["filename"], toks, package):
            continue
        if large:
            why = f"adds a file of {size:,} bytes (over 1 MB)"
        elif marked:
            why = "adds a file GitHub marks binary"
        elif hidden:
            why = (f"adds a file GitHub shows no diff for although it counts its lines "
                   f"(+{f.get('additions') or 0} -{f.get('deletions') or 0}): too large to show")
        else:
            why = (f"adds a file GitHub shows no diff for (+0 -0, extension "
                   f"{_ext(f['filename']) or 'none'}): binary or empty")
        if size is None:
            why += "; its size is not in the file list"
        elif not large:
            why += f"; {size:,} bytes"
        out.append(Extra("binary_or_large_added", f["filename"], f["filename"], why))
    return out


# ------------------------------------------------ rule 7: mass events (v3)

_NOUN = {"ci_or_config": "config files", "tests_removed": "test files",
         "generated_code_removed": "generated or vendored files", "binary_or_large_added": "binary or large files"}


def _mass_events(found, files):
    status = {f["filename"]: f.get("status") for f in files}
    keep, pools = [], {}
    for e in found:
        st, top = status.get(e.path), "/".join(_dirs(e.path)[:2])
        if e.kind in _NOUN and e.name == e.path and st in ("added", "removed") and top:
            pools.setdefault((e.kind, st, top), []).append(e)
        else:
            keep.append(e)
    for (kind, st, _), group in pools.items():
        if len(group) < MASS:
            keep += group
            continue
        paths = tuple(sorted(e.path for e in group))
        d = posixpath.commonpath([posixpath.dirname(p) for p in paths]) + "/"
        verb = "deleted" if st == "removed" else "added"
        keep.append(Extra(kind, d, d, f"{len(paths)} {_NOUN[kind]} {verb} under {d}", paths))
    return keep


# -------------------------------------------- rule 8: build_output_added (v4)

_BUILD_DIRS = {".turbo", "dist", ".tshy-build", "build", "target", "node_modules", ".next", "__pycache__",
               "site-packages"}   # build or install output; site-packages is node_modules' Python counterpart


def _build_output(issue_text, files):
    """(extras, their files): added files pooled by the path up to their first build-output directory."""
    pools, toks = {}, issue_tokens(issue_text)
    for f in files:
        parts = f["filename"].split("/")
        hit = next((i for i, d in enumerate(parts[:-1]) if d.lower() in _BUILD_DIRS), None)
        if f.get("status") == "added" and hit is not None:
            pools.setdefault("/".join(parts[:hit + 1]), []).append(f["filename"])
    out, taken = [], set()
    for d, paths in sorted(pools.items()):
        if len(paths) < MASS or any(t == d.lower() or d.lower().endswith("/" + t) for t in toks.paths):
            continue
        paths = tuple(sorted(paths))
        taken.update(paths)
        out.append(Extra("build_output_added", d + "/", d + "/", f"{len(paths)} generated files committed under {d}/", paths))
    return out, taken


# ----------------------------------------------------- rule 9: stray_file (v4)

_LOCK_MANAGER = {"package-lock.json": ("npm", "package.json"), "npm-shrinkwrap.json": ("npm", "package.json"),
                 "yarn.lock": ("yarn", "package.json"), "pnpm-lock.yaml": ("pnpm", "package.json"),
                 "bun.lock": ("bun", "package.json"), "bun.lockb": ("bun", "package.json"),
                 "poetry.lock": ("poetry", "pyproject.toml"), "uv.lock": ("uv", "pyproject.toml"),
                 "pdm.lock": ("pdm", "pyproject.toml"), "Pipfile.lock": ("pipenv", "Pipfile")}
_LEFTOVER = re.compile(r".+(?:\.(?:backup|bak|orig|swp)|~)")
_KEPT_TOP = re.compile(r"(README|CHANGELOG|LICEN[CS]E|CONTRIBUTING)([.\-_].*)?", re.IGNORECASE)
_HOUSEKEEPING = {".gitkeep", ".keep", ".gitignore", ".gitattributes"}   # read by git, named by no file


def _stray_lockfiles(issue_text, files):
    status = {f["filename"]: f.get("status") for f in files}
    out = []
    for f in files:
        b, d = _base(f["filename"]), posixpath.dirname(f["filename"])
        if f.get("status") != "added" or b not in _LOCK_MANAGER:
            continue
        manager, manifest = _LOCK_MANAGER[b]
        if _mentions(issue_text, manager) or _mentions(issue_text, b):
            continue
        others = sorted(o for o, (_, m) in _LOCK_MANAGER.items() if o != b and m == manifest
                        and status.get(posixpath.join(d, o)) not in (None, "removed"))
        if others:
            out.append((f["filename"], f"a {manager} lockfile beside {others[0]}, the lockfile of the package manager in use"))
        elif status.get(posixpath.join(d, manifest)) != "added":
            out.append((f["filename"], f"a {manager} lockfile in a project that had none (its {manifest} is not new)"))
    return out


def _stray(issue_text, files, named, covered, package):
    toks = issue_tokens(issue_text)
    head = {f["filename"]: "\n".join(t for s, t in _lines(f.get("patch")) if s in ("+", " ")).lower() for f in files}
    out = []
    for f in files:
        p, b = f["filename"], _base(f["filename"])
        if f.get("status") != "added" or p in covered or p in named or _names_closely(p, toks, package):
            continue
        if _LEFTOVER.fullmatch(b):
            out.append((p, "a backup or editor copy"))
        elif "/" in p or _exempt(p) or _KEPT_TOP.fullmatch(b):
            continue
        elif _ext(p) in ("md", "markdown"):
            out.append((p, "a top-level document the issue does not name"))
        elif _ext(p) not in _CODE_EXT and b not in _HOUSEKEEPING and not any(
                b.lower() in text for q, text in head.items() if q != p):
            out.append((p, "a new top-level file no other changed file names"))
    return out


def _stray_extra(found):
    if len(found) == 1:
        p, why = found[0]
        return [Extra("stray_file", p, p, f"adds {why}; the issue does not ask for it")]
    if not found:
        return []
    paths = tuple(p for p, _ in found)
    d = posixpath.commonpath([posixpath.dirname(p) for p in paths])
    return [Extra("stray_file", (d + "/") if d else "./", "stray files",
                  f"{len(paths)} files the issue does not ask for: " + "; ".join(f"{p} ({w})" for p, w in found), paths)]


# ------------------------------------------------------------------- entry

def analyse(issue_text: str, files: list[dict], *, repo: str | None = None,
            version: int = RULES_VERSION) -> Analysis:
    """`repo` ("owner/name") keeps the project's own package directory from naming files (rules 5, 6).
    version=1, 2 or 3 runs the frozen rules (extras_v1.py through extras_v3.py) and returns their own
    objects, so their output is byte for byte what it was."""
    if version in (1, 2, 3):
        from itemator import extras_v3
        return extras_v3.analyse(issue_text, files, repo=repo, version=version)
    if version != RULES_VERSION:
        raise ValueError(f"unknown rules version {version}")
    package = _squash((repo or "").rsplit("/", 1)[-1])
    issue_text = issue_text or ""
    files = [f for f in files if f.get("filename")]
    build, taken = _build_output(issue_text, files)
    rest = [f for f in files if f["filename"] not in taken]     # rule 8's files: no other rule reads them
    found = (_new_dependencies(issue_text, rest) + _ci_or_config(issue_text, rest)
             + _tests_removed(issue_text, rest) + _generated_code_removed(issue_text, rest, package)
             + _public_api_removed(issue_text, rest) + _binary_or_large_added(issue_text, rest, package))
    found = [e for e in _mass_events(found, rest)      # 3c: mass events only
             if e.kind != "generated_code_removed" or e.detail]
    found += build + _version_bumps(issue_text, rest)
    covered = {f["filename"] for f in files
               if _manifest_kind(f["filename"]) or _config_kind(f["filename"])
               or (f.get("status") == "removed" and (is_test_file(f["filename"]) or is_generated(f["filename"])))}
    covered |= {p for e in found if e.kind == "binary_or_large_added" for p in (e.detail or (e.path,))}
    covered |= taken
    unplaced, named, anchored = _unplaced(issue_text, files, covered, package)
    stray = sorted(_stray_lockfiles(issue_text, rest)
                   + _stray(issue_text, rest, _named_files(issue_text, rest, package), covered, package))
    found += _stray_extra(stray)
    unique = sorted(set(found), key=lambda e: (KINDS.index(e.kind), e.path, e.name))
    return Analysis(extras=unique, named_paths=named, anchored=anchored, unplaced=unplaced, stray=[p for p, _ in stray])


def extras(issue_text: str, files: list[dict], *, repo: str | None = None,
           version: int = RULES_VERSION) -> list[Extra]:
    """The extras of a change, in a fixed order (kind, path, name)."""
    return analyse(issue_text, files, repo=repo, version=version).extras
