"""Registry facts for the packages a merge request adds (brief T17).

For a new dependency the approver sees, at the moment they must name it: does the name exist on its public registry,
since when, how many releases, which licence the registry states, and how many advisories OSV knows. Facts only:
no score and no advice. Standard library only.

Package names come from the merge request, so they are hostile: each is checked against its ecosystem's name rules
before any request, only the four hosts in HOSTS are asked, a redirect to any other host is refused, and every
request has a timeout inside a total budget per job. A lookup never fails the job: any failure is
`lookup: "unavailable"` with a short reason code, and no field is guessed.
"""
from __future__ import annotations

import datetime
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from itemator import extras as X
from itemator import installs as INSTALLS
from itemator import sci as SCI
from itemator import setupdeps as SETUP
from itemator import weight as W

# The only hosts the job may ask (brief T17 item 3): three public registries and OSV's advisory database.
HOSTS = frozenset({"pypi.org", "registry.npmjs.org", "crates.io", "api.nuget.org", "proxy.golang.org", "api.osv.dev",
                   "api.deps.dev"})
OSV_URL = "https://api.osv.dev/v1/query"
TIMEOUT = 8               # seconds per request: a registry that has not answered by then is not waited for
BUDGET = 25               # seconds for all lookups of one job, so the facts never hold up the pipeline
MAX_PACKAGES = 10         # packages looked up per job (two requests each), whatever the merge request adds
PER_EXTRA = 5             # packages of a grouped extra looked up; the card names those and gives the count
NAME_MAX = 214            # characters in a name: npm's limit, the longest of the three registries'
# Bytes read from one answer, per host (T21 NOTE 9): npm's documents for big packages run to tens of MB, PyPI's and
# crates.io's to a few, OSV's query answers to a few kB. A larger answer, or a larger Content-Length, is `too_large`.
MAX_BODY = {"api.osv.dev": 2 ** 20, "pypi.org": 16 * 2 ** 20, "crates.io": 16 * 2 ** 20, "registry.npmjs.org": 64 * 2 ** 20,
           "api.nuget.org": 16 * 2 ** 20, "proxy.golang.org": 2 ** 20,
           "api.deps.dev": 4 * 2 ** 20}
MAX_LINE = 2000           # characters of a manifest line read for a pin or a path; a longer line is skipped (T21 NOTE 10)
MAX_COUNT = 10 ** 7       # a release count is kept only below this (T21 FIX 3)
LICENCE_MAX = 100         # characters of a stated licence kept; some packages put the whole licence text there
USER_AGENT = "itemator-ci"  # crates.io refuses requests without a User-Agent (its crawler policy)

_KIND_ECOSYSTEM = {"requirements": "PyPI", "pyproject": "PyPI", "npm": "npm", "cargo": "crates.io",
                   "go": "Go", "gem": "RubyGems", "pom": "Maven", "gradle": "Maven"}
SUPPORTED = ("PyPI", "npm", "crates.io", "NuGet", "Go")
# ASCII classes and no IGNORECASE: with re.I a Unicode pattern lets 'ſ' or the Kelvin sign match [a-z].
_NAME = {
    "PyPI": re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"),               # PEP 508 name
    "npm": re.compile(r"(?:@[a-z0-9~-][a-z0-9._~-]*/)?[a-z0-9~-][a-z0-9._~-]*"),     # npm name, plain or scoped
    "crates.io": re.compile(r"[A-Za-z0-9_-]{1,64}"),
    "Go": re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._~-]|/(?!/))*[A-Za-z0-9]"),           # module path: no empty or dot-only element is checked below
    "NuGet": re.compile(r"[A-Za-z0-9_](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?"),        # package id: letters, digits, . _ -
}
_VER = r"(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)"
_VERSION = re.compile(r"[A-Za-z0-9._+!-]{1,64}")      # a version string kept, shown or sent to OSV (T21 FIX 3)
# A licence is shown as written only when SPDX-shaped (T21 FIX 1): ids joined by AND, OR or WITH, in parentheses or not.
_SPDX = re.compile(r"\(*[A-Za-z0-9][A-Za-z0-9.+-]{0,39}\)*(?: (?:AND|OR|WITH) \(*[A-Za-z0-9][A-Za-z0-9.+-]{0,39}\)*){0,4}")
_STRAY_DOT = re.compile(r"(?<![0-9])\.|\.(?![0-9])")    # SPDX ids put a dot only inside a version; www.x.example is a link
_CLASSIFIER = re.compile(r"[A-Za-z0-9 .+()/,-]{1,80}")  # a PyPI licence classifier's name ("MIT License")
_GROUPS = ("OSI Approved", "DFSG approved")             # classifiers that group licences and name none
_SITE = {"PyPI": "pypi.org", "npm": "npmjs.org", "crates.io": "crates.io", "NuGet": "nuget.org", "Go": "proxy.golang.org"}
DECLARED = " as declared by its publisher"


class LookupFailed(Exception):
    """A lookup that gave no facts; `code` is the short reason kept in the record."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# ------------------------------------------------------------------ names

def valid_name(ecosystem: str, name) -> bool:
    ok = (isinstance(name, str) and name.isascii() and 0 < len(name) <= NAME_MAX
          and ecosystem in _NAME and _NAME[ecosystem].fullmatch(name) is not None)
    if ok and ecosystem == "Go":      # a path element of dots only ('..') would climb out of the module's place on the proxy
        ok = all(part.strip(".") for part in name.split("/"))
    return ok


def _go_escape(path: str) -> str:
    """The proxy's spelling of a module path: each capital letter becomes '!' and its lower-case letter."""
    return urllib.parse.quote(re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), path), safe="/!")


def _pep503(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def registry_url(ecosystem: str, name: str) -> str:
    if ecosystem == "PyPI":
        return f"https://pypi.org/pypi/{urllib.parse.quote(_pep503(name), safe='')}/json"
    if ecosystem == "npm":
        return "https://registry.npmjs.org/" + urllib.parse.quote(name, safe="@")
    if ecosystem == "Go":
        return "https://proxy.golang.org/" + _go_escape(name) + "/@v/list"
    if ecosystem == "NuGet":
        return "https://api.nuget.org/v3/registration5-semver1/" + urllib.parse.quote(name.lower(), safe="") + "/index.json"
    return "https://crates.io/api/v1/crates/" + urllib.parse.quote(name, safe="")


def _key(name: str) -> str:
    return r"(?<![A-Za-z0-9_-])[\"']?" + re.escape(name) + r"[\"']?\s*=\s*"


def pinned(ecosystem: str, name: str, line: str) -> str | None:
    """The exact version the added line pins the package to, else None (a range is not a pin)."""
    if len(line) > MAX_LINE:
        return None
    if ecosystem == "PyPI":
        parts = [re.escape(p) for p in re.split(r"[-_.]+", name) if p]
        rx = (r"(?<![A-Za-z0-9._-])" + r"[-_.]+".join(parts) +
              r"\s*(?:\[[^\]]*\])?\s*==\s*([0-9][0-9A-Za-z.+!_-]*)(?![0-9A-Za-z.+!_*=-])")
        m = re.search(rx, line, re.I)
    elif ecosystem == "npm":
        m = re.search('"' + re.escape(name) + r'"\s*:\s*"[=v]?' + _VER + '"', line)
    elif ecosystem == "Go":
        m = re.search(r"(?<![^\s\"(])" + re.escape(name) + r"\s+(v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+incompatible)?)(?![0-9A-Za-z.+-])", line)
    elif ecosystem == "crates.io":
        m = re.search(_key(name) + r'(?:"=\s*' + _VER + r'"|\{[^}]*?\bversion\s*=\s*"=\s*' + _VER + '")', line)
    else:
        return None
    v = next((g for g in m.groups() if g), None) if m else None
    return v if v and _VERSION.fullmatch(v) else None


def _local(ecosystem: str, name: str, line: str) -> bool:
    """A dependency the line takes from the disk or the workspace, not from the registry."""
    if len(line) > MAX_LINE:
        return False
    if ecosystem == "npm":
        return re.search('"' + re.escape(name) + r'"\s*:\s*"(?:workspace|file|link|portal):', line) is not None
    return re.search(_key(name) + r"\{[^}]*\bpath\s*=", line) is not None


def _line(e, by_path: dict) -> str:
    """The added line the extra anchors on (the first one that names the package), or ''."""
    from itemator import ci     # ci imports this module
    anchor, _ = ci.anchor_for(e, by_path)
    f = by_path.get(e.path) or {}
    if not anchor or anchor.get("new_line") is None:
        return ""
    return next((text for sign, _, new, text in ci.diff_lines(f.get("patch"))
                 if sign == "+" and new == anchor["new_line"]), "")


def request_for(e, by_path: dict) -> dict:
    """What to look up for one new-dependency extra, or why nothing is looked up."""
    kind = X._manifest_kind(e.path)
    eco = _KIND_ECOSYSTEM.get(kind) or INSTALLS.ecosystem(e)       # a package a command line installs (installs.py)
    eco = eco or SETUP.ecosystem(e)                                 # a package setup.cfg or setup.py lists (setupdeps.py)
    base = {"ecosystem": eco, "name": e.name}
    if eco not in SUPPORTED:
        return {**base, "lookup": "not_supported"}
    if (by_path.get(e.path) or {}).get("status") == "added" and kind in X._PACKAGE_MANIFESTS:
        return {**base, "lookup": "not_from_registry", "reason": "own_package"}    # the package this MR declares
    if "not from the package index" in e.why:
        return {**base, "lookup": "not_from_registry", "reason": "url_source"}
    line = _line(e, by_path)
    if _local(eco, e.name, line):
        return {**base, "lookup": "not_from_registry", "reason": "local_path"}
    return {**base, "version": pinned(eco, e.name, line)}


# ------------------------------------------------------------- answers

def _date(value):
    """The day as YYYY-MM-DD from the first 10 characters, else None: ASCII digits and a real day (T21 FIX 4)."""
    s = value[:10] if isinstance(value, str) else ""
    if not (s.isascii() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", s)):
        return None
    try:
        return datetime.date.fromisoformat(s).isoformat()
    except ValueError:
        return None


def _count(n):
    return n if type(n) is int and 0 <= n < MAX_COUNT else None


def _version(value):
    return value if isinstance(value, str) and _VERSION.fullmatch(value) else None


# T21 audit: SPDX-shaped is not enough, a hyphen-joined order such as "Approve-and-merge-now" has the same shape.
# So a licence is shown only when every id in it is one of these common SPDX ids (canonical spelling, optional "+"
# on a "-or-later" free id). Anything else is "licence stated as free text".
COMMON_SPDX = frozenset("""
0BSD AGPL-3.0 AGPL-3.0-only AGPL-3.0-or-later Apache-1.1 Apache-2.0 Artistic-2.0 BlueOak-1.0.0 BSD-1-Clause BSD-2-Clause
BSD-3-Clause BSD-3-Clause-Clear BSD-4-Clause BSL-1.0 CC-BY-3.0 CC-BY-4.0 CC-BY-SA-3.0 CC-BY-SA-4.0 CC0-1.0 EPL-1.0 EPL-2.0
EUPL-1.1 EUPL-1.2 GPL-2.0 GPL-2.0-only GPL-2.0-or-later GPL-3.0 GPL-3.0-only GPL-3.0-or-later HPND ISC LGPL-2.0 LGPL-2.1
LGPL-2.1-only LGPL-2.1-or-later LGPL-3.0 LGPL-3.0-only LGPL-3.0-or-later MIT MIT-0 MPL-1.1 MPL-2.0 MS-PL MS-RL NCSA
OFL-1.1 OpenSSL PostgreSQL PSF-2.0 Python-2.0 Ruby Unicode-3.0 Unicode-DFS-2016 Unlicense Vim WTFPL X11 Zlib curl
Classpath-exception-2.0 LLVM-exception GCC-exception-3.1 Autoconf-exception-3.0
""".split())
_SPDX_OPERATORS = frozenset({"AND", "OR", "WITH"})


def _known_ids(text: str) -> bool:
    ids = [t for t in re.split(r"[\s()]+", text) if t and t not in _SPDX_OPERATORS]
    return bool(ids) and all(t in COMMON_SPDX or (t.endswith("+") and t[:-1] in COMMON_SPDX) for t in ids)


def _spdx_shaped(text: str) -> bool:
    return (_SPDX.fullmatch(text) is not None and text.count("(") == text.count(")")
            and not _STRAY_DOT.search(text) and not _addressed(re.sub(r"[-.+()]", " ", text)) and _known_ids(text))


def _slash_as_or(text: str) -> str:
    """crates.io still serves the old form `Apache-2.0 / MIT` (and `MIT/Apache-2.0`): read it as OR."""
    parts = [x.strip() for x in text.split("/")]
    return " OR ".join(parts) if len(parts) > 1 and all(x in COMMON_SPDX for x in parts) else text


def _licence(stated, classifiers=()) -> dict:
    """The licence the publisher declares. `stated`: the registry's licence fields, most precise first; `classifiers`:
    PyPI licence classifier names. Kept as `spdx` or `classifier` (shown as written), else as `free_text` (not shown);
    UNKNOWN or empty is no licence."""
    texts = [_slash_as_or(" ".join(v.split())) for v in stated if isinstance(v, str)]
    texts = [t for t in texts if t and t.upper() != "UNKNOWN"]
    shaped = next((t for t in texts if len(t) <= LICENCE_MAX and _spdx_shaped(t)), None)
    if shaped:
        return {"license": shaped, "license_form": "spdx"}
    named = " / ".join(classifiers)
    if classifiers and all(_CLASSIFIER.fullmatch(c) and not _addressed(c) for c in classifiers):
        return {"license": named, "license_form": "classifier"}
    text = next(iter(texts), named)
    if not text:
        return {"license": None}
    cut = {"license_cut": True} if len(text) > LICENCE_MAX else {}
    return {"license": text[:LICENCE_MAX], "license_form": "free_text", **cut}


def _pypi(doc: dict, name: str, version: str | None = None) -> dict:
    info = doc.get("info") or {}
    if _pep503(str(info.get("name") or "")) != _pep503(name):
        raise LookupFailed("name_differs")
    releases = first = released = None
    yanked = 0
    install = {}
    rel = doc.get("releases")
    if isinstance(rel, dict):
        files = {v: [f for f in fs if isinstance(f, dict)] for v, fs in rel.items() if isinstance(fs, list)}
        files = {v: fs for v, fs in files.items() if fs}           # a version with no file was never released
        live = sum(1 for fs in files.values() if not all(f.get("yanked") is True for f in fs))
        releases, yanked = _count(live), len(files) - live          # a release whose every file is yanked is not counted
        dates = sorted(d for fs in files.values() for f in fs
                       for d in [_date(f.get("upload_time_iso_8601") or f.get("upload_time"))] if d)
        first = dates[0] if dates else None
        mine = sorted(d for f in files.get(version) or () for d in [_date(f.get("upload_time_iso_8601") or f.get("upload_time"))] if d)
        released = mine[0] if mine else None
        own = files.get(version or _version(info.get("version"))) or []
        if own and all(f.get("yanked") is True for f in own):
            install["version_yanked"] = True
        live_files = [f for f in own if f.get("yanked") is not True and isinstance(f.get("filename"), str)]
        if live_files and not any(f["filename"].endswith(".whl") for f in live_files):
            install["install_code"] = "sdist"      # no wheel: pip builds it from source, which runs the package's own build code
    classifiers = [" ".join(c.split("::")[-1].split()) for c in info.get("classifiers") or ()
                   if isinstance(c, str) and c.startswith("License ::")]
    classifiers = [c for c in classifiers if c not in _GROUPS]
    return {"first_release": first, "releases": releases, **({"yanked": yanked} if yanked else {}),
            **({"version_released": released} if released else {}),
            "latest": _version(info.get("version")), **install,
            **_licence([info.get("license_expression"), info.get("license")], classifiers)}


def _npm_licence(meta: dict):
    lic = meta.get("license")
    if isinstance(lic, dict):
        lic = lic.get("type")
    if lic is None and isinstance(meta.get("licenses"), list):         # the legacy form, [{"type": "MIT"}, ...]
        types = [x.get("type") if isinstance(x, dict) else x for x in meta["licenses"]]
        lic = " OR ".join(t for t in types if isinstance(t, str)) or None
    return lic


INSTALL_SCRIPTS = ("preinstall", "install", "postinstall")


def _npm(doc: dict, name: str, version: str | None = None) -> dict:
    if doc.get("name") != name:
        raise LookupFailed("name_differs")
    times = doc.get("time") if isinstance(doc.get("time"), dict) else {}
    if times.get("unpublished"):
        raise LookupFailed("unpublished")         # npm keeps a stub for an unpublished package: no facts to give
    versions = doc.get("versions") if isinstance(doc.get("versions"), dict) else None
    latest = _version((doc.get("dist-tags") or {}).get("latest"))
    lic = _npm_licence(doc)
    if lic is None and versions and isinstance(versions.get(latest), dict):
        lic = _npm_licence(versions[latest])
    released = _date(times.get(version)) if version else None
    meta = (versions or {}).get(version or latest)
    install = {}
    if isinstance(meta, dict):
        if isinstance(meta.get("deprecated"), str) and meta["deprecated"].strip():
            install["deprecated"] = True
        scripts = meta.get("scripts") if isinstance(meta.get("scripts"), dict) else {}
        if meta.get("hasInstallScript") is True or any(k in scripts for k in INSTALL_SCRIPTS):
            install["install_code"] = "npm"        # npm runs these on every install unless told not to
    return {"first_release": _date(times.get("created")), **({"version_released": released} if released else {}), **install,
            "releases": _count(len(versions)) if versions is not None else None, "latest": latest, **_licence([lic])}


def _crates(doc: dict, name: str, version: str | None = None) -> dict:
    crate = doc.get("crate") or {}
    if crate.get("name") != name:
        raise LookupFailed("name_differs")
    versions = doc.get("versions") if isinstance(doc.get("versions"), list) else None
    count = _count(crate.get("num_versions"))
    latest = _version(crate.get("max_stable_version") or crate.get("max_version"))
    lic = next((v.get("license") for v in versions or ()
                if isinstance(v, dict) and latest is not None and v.get("num") == latest), None)
    if count is None and versions is not None:
        count = _count(len(versions))
    released = next((_date(v.get("created_at")) for v in versions or ()
                     if isinstance(v, dict) and version is not None and v.get("num") == version), None)
    return {"first_release": _date(crate.get("created_at")), **({"version_released": released} if released else {}),
            "releases": count, "latest": latest, **_licence([lic])}


def _nuget(doc: dict, name: str, version: str | None = None) -> dict:
    """NuGet's registration index: pages of releases, each with its `published` date and licence expression. `doc` is the
    index with the first and the last page filled in (`Run._nuget_doc` fetches a page the index does not inline)."""
    pages = doc.get("items") if isinstance(doc.get("items"), list) else None
    if not pages or not all(isinstance(p, dict) for p in pages):
        raise LookupFailed("bad_response")
    entries = [[i.get("catalogEntry") for i in (p.get("items") or ()) if isinstance(i, dict)
                and isinstance(i.get("catalogEntry"), dict)] for p in pages]
    first_page, last_page = entries[0], entries[-1]
    if not first_page or not last_page:
        raise LookupFailed("bad_response")
    ids = {str(e.get("id")) for e in first_page + last_page}
    if len(ids) != 1 or next(iter(ids)).lower() != name.lower():
        raise LookupFailed("name_differs")
    total = sum(p["count"] for p in pages if type(p.get("count")) is int)
    dates = sorted(d for e in first_page for d in [_date(e.get("published"))] if d and d >= "2001-01-01")   # 1900-01-01 marks an unlisted release
    stable = [e for e in last_page if isinstance(e.get("version"), str) and "-" not in e["version"]]
    latest = (stable or last_page)[-1]
    released = next((_date(e.get("published")) for e in first_page + last_page if version and e.get("version") == version), None)
    lic = latest.get("licenseExpression") if isinstance(latest.get("licenseExpression"), str) else None
    return {"canonical": next(iter(ids)), "first_release": dates[0] if dates else None,
            **({"version_released": released} if released and released >= "2001-01-01" else {}),
            "releases": _count(total), "latest": _version(latest.get("version")), **_licence([lic])}


_GO_VERSION = re.compile(r"v(\d+)\.(\d+)\.(\d+)(-[0-9A-Za-z.-]{1,40})?(\+incompatible)?")


def _go_key(v: str):
    m = _GO_VERSION.fullmatch(v)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) is None, m.group(4) or "")


def _go(doc: dict, name: str, version: str | None = None) -> dict:
    """The Go proxy gives the tagged versions and, for two of them, a date; it gives no licence, so none is read
    (`license_read` False). `first_release` is the date of the lowest-numbered tagged version."""
    versions = [v for v in doc.get("versions") or () if isinstance(v, str) and _GO_VERSION.fullmatch(v)]
    if not versions:
        raise LookupFailed("no_tagged_versions")
    stable = [v for v in versions if _go_key(v)[3]]
    first = min(versions, key=_go_key)
    dates = doc.get("dates") if isinstance(doc.get("dates"), dict) else {}
    released = _date(dates.get(version)) if version else None
    return {"first_release": _date(dates.get(first)), **({"version_released": released} if released else {}),
            "first_version": first, "releases": _count(len(set(versions))), "latest": _version(max(stable or versions, key=_go_key)),
            "license": None, "license_read": False}


_PARSE = {"PyPI": _pypi, "npm": _npm, "crates.io": _crates, "NuGet": _nuget, "Go": _go}


def _json(body: bytes) -> dict:
    try:
        doc = json.loads(body)
    except ValueError as e:
        raise LookupFailed("bad_response") from e
    if not isinstance(doc, dict):
        raise LookupFailed("bad_response")
    return doc


_ADVISORY_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}")      # GHSA-…, PYSEC-…, RUSTSEC-…, MAL-…


MAX_MALWARE_IDS = 3


def _malware(vulns: list) -> list[str]:
    """The OpenSSF malicious-packages reports among OSV's records (MAL-...), by a record's own id or an alias."""
    out = []
    for v in vulns:
        if not isinstance(v, dict):
            continue
        aliases = v.get("aliases") if isinstance(v.get("aliases"), list) else []
        mal = next((i for i in [v.get("id"), *aliases] if isinstance(i, str) and i.startswith("MAL-")
                    and _ADVISORY_ID.fullmatch(i)), None)
        if mal and mal not in out:
            out.append(mal)
    return out[:MAX_MALWARE_IDS]


def _distinct(vulns: list) -> int:
    """OSV lists one issue once per database (GHSA-…, PYSEC-…), each record naming the others as aliases: count it once."""
    seen, n = set(), 0
    for v in vulns:
        if not isinstance(v, dict) or not isinstance(v.get("id"), str):
            continue                                    # only a record with an id is an advisory (T21 NOTE 7e)
        aliases = v.get("aliases") if isinstance(v.get("aliases"), list) else ()
        ids = {v["id"]} | {a for a in aliases if isinstance(a, str)}
        if not ids & seen:
            n += 1
        seen |= ids
    return n


def _reason(ex: Exception) -> str:
    if isinstance(ex, LookupFailed):
        return ex.code
    if isinstance(ex, TimeoutError):
        return "timeout"
    if isinstance(ex, OSError):
        return "network"
    if isinstance(ex, (ValueError, TypeError, AttributeError, KeyError)):
        return "bad_response"
    return "error"


# ------------------------------------------------------------------ a run

class Run:
    """The lookups of one job: one time budget and one package cap."""

    def __init__(self, fetch, today: str, clock=time.monotonic):
        self.fetch, self.today, self.clock = fetch, today, clock
        self.deadline, self.looked = clock() + BUDGET, 0

    def _ask(self, method: str, url: str, body: bytes | None = None):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in HOSTS:
            raise LookupFailed("host")
        if not _plain_netloc(parts):
            raise LookupFailed("host")
        left = self.deadline - self.clock()
        if left <= 0:
            raise LookupFailed("time_budget")
        return self.fetch(method, url, body, min(TIMEOUT, left))

    def _go_doc(self, name: str, body: bytes, version: str | None) -> dict:
        """The version list with the dates of the lowest-numbered version and of the pinned one (one request each)."""
        versions = [v for v in (line.strip() for line in body.decode("utf-8", "replace").splitlines()[:5000]) if _GO_VERSION.fullmatch(v)]
        if not versions:
            raise LookupFailed("no_tagged_versions")
        wanted = [min(versions, key=_go_key)] + ([version] if version and _GO_VERSION.fullmatch(version) else [])
        dates = {}
        for v in dict.fromkeys(wanted):
            status, info = self._ask("GET", f"https://proxy.golang.org/{_go_escape(name)}/@v/{_go_escape(v)}.info")
            if status == 200:
                dates[v] = _json(info).get("Time")
        return {"versions": versions, "dates": dates}

    def _nuget_doc(self, index: dict) -> dict:
        """The index with its first and last page inline: a package with more than 128 releases lists its pages by link only."""
        pages = index.get("items") if isinstance(index.get("items"), list) else None
        if not pages or not all(isinstance(p, dict) for p in pages):
            raise LookupFailed("bad_response")
        filled = list(pages)
        for i in {0, len(pages) - 1}:
            if "items" in pages[i]:
                continue
            link = pages[i].get("@id")
            if not isinstance(link, str) or not link.startswith("https://api.nuget.org/v3/registration5-semver1/"):
                raise LookupFailed("bad_response")
            status, body = self._ask("GET", link)
            if status != 200:
                raise LookupFailed(f"http_{status}")
            filled[i] = {**pages[i], **_json(body)}
        return {**index, "items": filled}

    def _gone(self, rec: dict, name: str, eco: str) -> dict:
        """A name the registry does not have: a registry takes malware down, and OSV keeps the report (OpenSSF's
        malicious-packages list, ids MAL-...), so OSV is asked about the name, in any version. Only a malware report is
        kept; a failed or odd answer says nothing more than "not found"."""
        query = {"package": {"name": _pep503(name) if eco == "PyPI" else name, "ecosystem": eco}}
        try:
            status, body = self._ask("POST", OSV_URL, json.dumps(query).encode())
            vulns = _json(body).get("vulns") if status == 200 else None
        except Exception:                # noqa: BLE001 -- information only
            vulns = None
        if isinstance(vulns, list) and _malware(vulns):
            rec["malware"] = _malware(vulns)
        return rec

    def look(self, req: dict) -> dict:
        if "lookup" in req:
            return req
        eco, name = req["ecosystem"], req["name"]
        rec = {"ecosystem": eco, "name": name, "version": req.get("version"), "checked": self.today, "source": None}
        if not valid_name(eco, name):
            return {**rec, "lookup": "unavailable", "reason": "invalid_name"}
        rec["source"] = url = registry_url(eco, name)
        if self.looked >= MAX_PACKAGES:
            return {**rec, "lookup": "unavailable", "reason": "package_cap"}
        self.looked += 1
        try:
            status, body = self._ask("GET", url)
            if status == 404:
                return self._gone({**rec, "lookup": "ok", "found": False}, name, eco)
            if status != 200:
                raise LookupFailed(f"http_{status}")
            doc = (self._nuget_doc(_json(body)) if eco == "NuGet" else
                   self._go_doc(name, body, rec["version"]) if eco == "Go" else _json(body))
            found = _PARSE[eco](doc, name, rec['version'])
        except Exception as ex:          # never fail the job because of a lookup
            return {**rec, "lookup": "unavailable", "reason": _reason(ex)}
        canonical = found.pop("canonical", name)      # OSV's NuGet names are case-sensitive; the registry's spelling is the one it keeps
        rec = {**rec, "lookup": "ok", "found": True, **found}
        query = {"package": {"name": _pep503(name) if eco == "PyPI" else canonical, "ecosystem": eco}}
        if rec["version"]:
            query["version"] = rec["version"]
        try:
            status, body = self._ask("POST", OSV_URL, json.dumps(query).encode())
            if status != 200:
                raise LookupFailed(f"http_{status}")
            doc = _json(body)
            vulns = doc.get("vulns") or []
            if not isinstance(vulns, list):
                raise LookupFailed("bad_response")
            rec["advisories"] = _distinct(vulns)
            if _malware(vulns):
                rec["malware"] = _malware(vulns)
            rec["advisory_ids"] = [v["id"] for v in vulns if isinstance(v, dict) and isinstance(v.get("id"), str)
                                   and _ADVISORY_ID.fullmatch(v["id"])][:20]
            if doc.get("next_page_token"):
                rec["advisories_partial"] = True      # OSV has more pages: the count is a lower bound
        except Exception as ex:
            rec["advisories"], rec["advisories_reason"] = None, _reason(ex)
        return rec


def look_up(grouped: list, by_path: dict, fetch, now, clock=time.monotonic, weigh: bool = False) -> list:
    """Per (extra, items) of ci.group_extras: None, or {"count", "packages"} for a new dependency (the first
    PER_EXTRA packages of a grouped one). `weigh`: also measure what the first W.MAX_WEIGHED found packages bring along
    (itemator/weight.py); the CI job asks for it."""
    run = Run(fetch, now.strftime("%Y-%m-%d"), clock)
    out = []
    for e, items in grouped:
        if e.kind != "new_dependency":
            out.append(None)
            continue
        members = tuple(items) or (e,)
        packages = []
        for item in members[:PER_EXTRA]:
            try:
                packages.append(run.look(request_for(item, by_path)))
            except Exception as ex:
                packages.append({"ecosystem": None, "name": item.name, "lookup": "unavailable",
                                 "reason": _reason(ex), "checked": run.today, "source": None})
        out.append({"count": len(members), "packages": packages})
    weighed = 0 if weigh else W.MAX_WEIGHED
    for r in out:
        for p in (r or {}).get("packages", ()):
            if weighed >= W.MAX_WEIGHED or p.get("lookup") != "ok" or not p.get("found") or p.get("ecosystem") not in W.SYSTEM:
                continue
            weighed += 1
            _weigh(run, p)
    return out


def _weigh(run: Run, p: dict) -> None:
    """Adds `weight` (itemator/weight.py) to a found package's record, at the pinned version or else the registry's latest."""
    version = p.get("version") or p.get("latest")
    name = _pep503(p["name"]) if p["ecosystem"] == "PyPI" else p["name"]
    try:
        p["weight"] = {**W.weigh(run._ask, p["ecosystem"], name, version), "of_version": "pinned" if p.get("version") else "latest"}
    except Exception as ex:          # never fail the job because of a lookup
        p["weight"] = {"weight": "unavailable", "reason": _reason(ex)}


def look_up_one(req: dict, fetch, now, clock=time.monotonic) -> dict:
    """One request_for() answer looked up and weighed, with its own time budget (eval/aidev_weight.py)."""
    run = Run(fetch, now.strftime("%Y-%m-%d"), clock)
    p = run.look(req)
    if p.get("lookup") == "ok" and p.get("found") and p.get("ecosystem") in W.SYSTEM:
        _weigh(run, p)
    return p


# ------------------------------------------------------------------ card

def _addressed(text: str) -> bool:
    """Text a package author wrote that the card's injection phrases match (ci._phrases): not shown as written."""
    from itemator import ci
    return bool(ci._phrases(text))


def _shows_licence(p: dict) -> bool:
    return p.get("license") is not None and p.get("license_form") in ("spdx", "classifier")


FRESH_DAYS = 30


def _fresh(p: dict):
    """When the pinned version came out, said only if it is recent: a brand-new version has had little time to be noticed."""
    try:
        days = (datetime.date.fromisoformat(p["checked"]) - datetime.date.fromisoformat(p["version_released"])).days
    except (KeyError, TypeError, ValueError):
        return None
    if not 0 <= days <= FRESH_DAYS:
        return None
    return "released " + ("the day of this check" if days == 0 else f"{days} day{'' if days == 1 else 's'} before this check")


def _malware_part(p: dict) -> str | None:
    ids = p.get("malware") or []
    if not ids:
        return None
    return f"OSV has {'a malware report' if len(ids) == 1 else 'malware reports'} for this package ({', '.join(ids)})"


def _facts(p: dict, declare: bool = True) -> str:
    """`declare`: say once per sentence that a licence shown is the publisher's own statement. A malware report comes
    first: it is the one fact a reader must not miss."""
    mal = _malware_part(p)
    if not p["found"]:
        return f"no package named `{p['name']}` on {_SITE[p['ecosystem']]} was found" + (f"; {mal}" if mal else "")
    first = f"first released {p['first_release']}" if p.get("first_release") else "first release date not stated"
    fresh = _fresh(p)
    if fresh:
        first += f", version {p['version']} {fresh}"
    n = p.get("releases")
    releases = f"{n} release{'' if n == 1 else 's'}" if _count(n) is not None else "release count not stated"
    if p.get("yanked"):
        releases += f" plus {p['yanked']} yanked"
    if p.get("license_read") is False:
        licence = "licence not given by its registry"
    elif p.get("license") is None:
        licence = "no licence stated"
    elif _shows_licence(p):
        licence = f"licence {p['license']}{DECLARED if declare else ''}"
    else:
        licence = "licence stated as free text"
    a = p.get("advisories")
    if a is None:
        advisories = "advisories could not be read"
    else:
        advisories = (f"{'at least ' if p.get('advisories_partial') else ''}{a} known advisor{'y' if a == 1 else 'ies'}"
                      + (f" for {p['version']}" if p.get("version") else " in any version"))
    parts = [*([mal] if mal else []), first, releases, licence, advisories]
    which = f"version {p['version']}" if p.get("version") else "its latest version"
    if p.get("deprecated"):
        parts.append(f"its publisher marked {which} deprecated")
    if p.get("version_yanked"):
        parts.append(f"{which} is yanked")
    if p.get("install_code") == "npm":
        parts.append(f"installing {which} runs the package's own install script")
    elif p.get("install_code") == "sdist":
        parts.append(f"{which} has no wheel, so installing it builds it from source and runs the package's own build code")
    weight = W.part(p.get("weight"))
    if weight:
        parts.append(weight)
    carbon = SCI.part(p.get("weight"))
    if carbon:
        parts.append(carbon)
    return ", ".join(parts)


def sentence(registry) -> str | None:
    """The card's sentence of registry facts, or None when there is nothing to say."""
    if not registry:
        return None
    shown = [p for p in registry["packages"] if p["lookup"] in ("ok", "unavailable")]
    if not shown:
        return None
    if registry["count"] == 1:
        p = shown[0]
        if p["lookup"] == "unavailable":
            return "Registry facts could not be read."
        return f"{p['ecosystem']}: {_facts(p)} (checked {p['checked']})."
    ok = [p for p in shown if p["lookup"] == "ok"]
    n, total = len(registry["packages"]), registry["count"]
    head = f"Registry facts for the first {n} of {total} packages" if total > n else f"Registry facts for the {n} packages"
    parts, declared = [], False
    for p in ok:                                                                # names in `ok` passed valid_name
        parts.append(f"`{p['name']}` on {p['ecosystem']}: {_facts(p, not declared)}")
        declared = declared or _shows_licence(p)
    if len(shown) > len(ok):
        parts.append(f"facts for {len(shown) - len(ok)} could not be read")
    return f"{head} (checked {shown[0]['checked']}): " + "; ".join(parts) + "."


# ---------------------------------------------------------------- network

class _SameHost(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to https on the same host, itself one of HOSTS (PyPI sends a name that is not
    normalised to the normalised URL); any other redirect is refused, so an answer cannot send the job elsewhere."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if new.scheme != "https" or new.hostname != old.hostname or new.hostname not in HOSTS:
            raise LookupFailed("redirect")
        if not _plain_netloc(new):
            raise LookupFailed("redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _plain_netloc(parts) -> bool:
    """Port 443 or none, and no user part or backslash, which urlsplit and the connection could read differently
    (T21 NOTE 6: `https://evil.example\\@pypi.org/x` has the host name pypi.org for urlsplit)."""
    try:
        port = parts.port
    except ValueError:
        return False
    return port in (None, 443) and "@" not in parts.netloc and "\\" not in parts.netloc


_OPENER = urllib.request.build_opener(_SameHost)
_clock = time.monotonic


def _open(req, timeout):
    """The one place that reaches the network."""
    return _OPENER.open(req, timeout=timeout)


def _read(response, deadline: float, cap: int) -> bytes:
    """read1 returns what one packet brings, so the deadline is checked per packet (T21 NOTE 8): a server that sends
    one byte at a time cannot hold the job past it by more than one packet's wait."""
    chunks, size = [], 0
    while True:
        if _clock() > deadline:
            raise LookupFailed("timeout")
        chunk = response.read1(65536)
        if not chunk:
            return b"".join(chunks)
        size += len(chunk)
        if size > cap:
            raise LookupFailed("too_large")
        chunks.append(chunk)


def _size(url: str, headers: dict, timeout: float):
    """(status, the total length as ASCII digits) for a ranged GET of one byte; nothing of the file is kept."""
    req = urllib.request.Request(url, headers={**headers, "Accept": "*/*", "Range": "bytes=0-0"}, method="GET")
    try:
        with _open(req, timeout) as r:
            total = None
            m = re.fullmatch(r"bytes 0-0/(\d{1,15})", (r.headers.get("Content-Range") or "").strip())
            if r.status == 206 and m:
                total = m.group(1)
            elif r.status == 200 and (r.headers.get("Content-Length") or "").isdigit():
                total = r.headers["Content-Length"]          # a server that ignores the range: its length, body left unread
            return (r.status, total.encode()) if total else (r.status, b"")
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LookupFailed("network") from e


def fetch(method: str, url: str, body: bytes | None, timeout: float):
    """One request: (status, body). Raises LookupFailed when no answer arrives."""
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if method == "SIZE":                       # the file's length from a one-byte ranged GET (itemator/weight.py)
        return _size(url, headers, timeout)
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    deadline = _clock() + timeout                          # connecting counts too
    cap = MAX_BODY.get(urllib.parse.urlsplit(url).hostname, 2 ** 20)
    try:
        with _open(req, timeout) as r:
            try:
                declared = int(r.headers.get("Content-Length") or -1)
            except ValueError:
                declared = -1
            if declared > cap:
                raise LookupFailed("too_large")
            return r.status, _read(r, deadline, cap)
    except urllib.error.HTTPError as e:
        return e.code, b""
    except urllib.error.URLError as e:
        raise LookupFailed("timeout" if isinstance(e.reason, TimeoutError) else "network") from e
    except TimeoutError as e:
        raise LookupFailed("timeout") from e
    except OSError as e:
        raise LookupFailed("network") from e
