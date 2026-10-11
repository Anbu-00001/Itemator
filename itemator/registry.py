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

# The only hosts the job may ask (brief T17 item 3): three public registries and OSV's advisory database.
HOSTS = frozenset({"pypi.org", "registry.npmjs.org", "crates.io", "api.osv.dev"})
OSV_URL = "https://api.osv.dev/v1/query"
TIMEOUT = 8               # seconds per request: a registry that has not answered by then is not waited for
BUDGET = 25               # seconds for all lookups of one job, so the facts never hold up the pipeline
MAX_PACKAGES = 10         # packages looked up per job (two requests each), whatever the merge request adds
PER_EXTRA = 5             # packages of a grouped extra looked up; the card names those and gives the count
NAME_MAX = 214            # characters in a name: npm's limit, the longest of the three registries'
# Bytes read from one answer, per host (T21 NOTE 9): npm's documents for big packages run to tens of MB, PyPI's and
# crates.io's to a few, OSV's query answers to a few kB. A larger answer, or a larger Content-Length, is `too_large`.
MAX_BODY = {"api.osv.dev": 2 ** 20, "pypi.org": 16 * 2 ** 20, "crates.io": 16 * 2 ** 20, "registry.npmjs.org": 64 * 2 ** 20}
MAX_LINE = 2000           # characters of a manifest line read for a pin or a path; a longer line is skipped (T21 NOTE 10)
MAX_COUNT = 10 ** 7       # a release count is kept only below this (T21 FIX 3)
LICENCE_MAX = 100         # characters of a stated licence kept; some packages put the whole licence text there
USER_AGENT = "itemator-ci"  # crates.io refuses requests without a User-Agent (its crawler policy)

_KIND_ECOSYSTEM = {"requirements": "PyPI", "pyproject": "PyPI", "npm": "npm", "cargo": "crates.io",
                   "go": "Go", "gem": "RubyGems", "pom": "Maven", "gradle": "Maven"}
SUPPORTED = ("PyPI", "npm", "crates.io")
# ASCII classes and no IGNORECASE: with re.I a Unicode pattern lets 'ſ' or the Kelvin sign match [a-z].
_NAME = {
    "PyPI": re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"),               # PEP 508 name
    "npm": re.compile(r"(?:@[a-z0-9~-][a-z0-9._~-]*/)?[a-z0-9~-][a-z0-9._~-]*"),     # npm name, plain or scoped
    "crates.io": re.compile(r"[A-Za-z0-9_-]{1,64}"),
}
_VER = r"(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)"
_VERSION = re.compile(r"[A-Za-z0-9._+!-]{1,64}")      # a version string kept, shown or sent to OSV (T21 FIX 3)
# A licence is shown as written only when SPDX-shaped (T21 FIX 1): ids joined by AND, OR or WITH, in parentheses or not.
_SPDX = re.compile(r"\(*[A-Za-z0-9][A-Za-z0-9.+-]{0,39}\)*(?: (?:AND|OR|WITH) \(*[A-Za-z0-9][A-Za-z0-9.+-]{0,39}\)*){0,4}")
_STRAY_DOT = re.compile(r"(?<![0-9])\.|\.(?![0-9])")    # SPDX ids put a dot only inside a version; www.x.example is a link
_CLASSIFIER = re.compile(r"[A-Za-z0-9 .+()/,-]{1,80}")  # a PyPI licence classifier's name ("MIT License")
_GROUPS = ("OSI Approved", "DFSG approved")             # classifiers that group licences and name none
_SITE = {"PyPI": "pypi.org", "npm": "npmjs.org", "crates.io": "crates.io"}
DECLARED = " as declared by its publisher"


class LookupFailed(Exception):
    """A lookup that gave no facts; `code` is the short reason kept in the record."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# ------------------------------------------------------------------ names

def valid_name(ecosystem: str, name) -> bool:
    return (isinstance(name, str) and name.isascii() and 0 < len(name) <= NAME_MAX
            and ecosystem in _NAME and _NAME[ecosystem].fullmatch(name) is not None)


def _pep503(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def registry_url(ecosystem: str, name: str) -> str:
    if ecosystem == "PyPI":
        return f"https://pypi.org/pypi/{urllib.parse.quote(_pep503(name), safe='')}/json"
    if ecosystem == "npm":
        return "https://registry.npmjs.org/" + urllib.parse.quote(name, safe="@")
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
    eco = _KIND_ECOSYSTEM.get(kind)
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


def _pypi(doc: dict, name: str) -> dict:
    info = doc.get("info") or {}
    if _pep503(str(info.get("name") or "")) != _pep503(name):
        raise LookupFailed("name_differs")
    releases = first = None
    yanked = 0
    rel = doc.get("releases")
    if isinstance(rel, dict):
        files = {v: [f for f in fs if isinstance(f, dict)] for v, fs in rel.items() if isinstance(fs, list)}
        files = {v: fs for v, fs in files.items() if fs}           # a version with no file was never released
        live = sum(1 for fs in files.values() if not all(f.get("yanked") is True for f in fs))
        releases, yanked = _count(live), len(files) - live          # a release whose every file is yanked is not counted
        dates = sorted(d for fs in files.values() for f in fs
                       for d in [_date(f.get("upload_time_iso_8601") or f.get("upload_time"))] if d)
        first = dates[0] if dates else None
    classifiers = [" ".join(c.split("::")[-1].split()) for c in info.get("classifiers") or ()
                   if isinstance(c, str) and c.startswith("License ::")]
    classifiers = [c for c in classifiers if c not in _GROUPS]
    return {"first_release": first, "releases": releases, **({"yanked": yanked} if yanked else {}),
            "latest": _version(info.get("version")),
            **_licence([info.get("license_expression"), info.get("license")], classifiers)}


def _npm_licence(meta: dict):
    lic = meta.get("license")
    if isinstance(lic, dict):
        lic = lic.get("type")
    if lic is None and isinstance(meta.get("licenses"), list):         # the legacy form, [{"type": "MIT"}, ...]
        types = [x.get("type") if isinstance(x, dict) else x for x in meta["licenses"]]
        lic = " OR ".join(t for t in types if isinstance(t, str)) or None
    return lic


def _npm(doc: dict, name: str) -> dict:
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
    return {"first_release": _date(times.get("created")),
            "releases": _count(len(versions)) if versions is not None else None, "latest": latest, **_licence([lic])}


def _crates(doc: dict, name: str) -> dict:
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
    return {"first_release": _date(crate.get("created_at")), "releases": count, "latest": latest, **_licence([lic])}


_PARSE = {"PyPI": _pypi, "npm": _npm, "crates.io": _crates}


def _json(body: bytes) -> dict:
    try:
        doc = json.loads(body)
    except ValueError as e:
        raise LookupFailed("bad_response") from e
    if not isinstance(doc, dict):
        raise LookupFailed("bad_response")
    return doc


_ADVISORY_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}")      # GHSA-…, PYSEC-…, RUSTSEC-…, MAL-…


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
                return {**rec, "lookup": "ok", "found": False}
            if status != 200:
                raise LookupFailed(f"http_{status}")
            found = _PARSE[eco](_json(body), name)
        except Exception as ex:          # never fail the job because of a lookup
            return {**rec, "lookup": "unavailable", "reason": _reason(ex)}
        rec = {**rec, "lookup": "ok", "found": True, **found}
        query = {"package": {"name": _pep503(name) if eco == "PyPI" else name, "ecosystem": eco}}
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
            rec["advisory_ids"] = [v["id"] for v in vulns if isinstance(v, dict) and isinstance(v.get("id"), str)
                                   and _ADVISORY_ID.fullmatch(v["id"])][:20]
            if doc.get("next_page_token"):
                rec["advisories_partial"] = True      # OSV has more pages: the count is a lower bound
        except Exception as ex:
            rec["advisories"], rec["advisories_reason"] = None, _reason(ex)
        return rec


def look_up(grouped: list, by_path: dict, fetch, now, clock=time.monotonic) -> list:
    """Per (extra, items) of ci.group_extras: None, or {"count", "packages"} for a new dependency (the first
    PER_EXTRA packages of a grouped one)."""
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
    return out


# ------------------------------------------------------------------ card

def _addressed(text: str) -> bool:
    """Text a package author wrote that the card's injection phrases match (ci._phrases): not shown as written."""
    from itemator import ci
    return bool(ci._phrases(text))


def _shows_licence(p: dict) -> bool:
    return p.get("license") is not None and p.get("license_form") in ("spdx", "classifier")


def _facts(p: dict, declare: bool = True) -> str:
    """`declare`: say once per sentence that a licence shown is the publisher's own statement."""
    if not p["found"]:
        return f"no package named `{p['name']}` on {_SITE[p['ecosystem']]} was found"
    first = f"first released {p['first_release']}" if p.get("first_release") else "first release date not stated"
    n = p.get("releases")
    releases = f"{n} release{'' if n == 1 else 's'}" if _count(n) is not None else "release count not stated"
    if p.get("yanked"):
        releases += f" plus {p['yanked']} yanked"
    if p.get("license") is None:
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
    return ", ".join((first, releases, licence, advisories))


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


def fetch(method: str, url: str, body: bytes | None, timeout: float):
    """One request: (status, body). Raises LookupFailed when no answer arrives."""
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
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
