"""What keeping a new dependency costs every fresh install: the packages it brings along and their download size. Standard library
only; no model.

A line in a manifest names one package, but installing it installs that package's own dependencies too, on every CI run without a
cache, every developer machine and every deploy, for as long as it stays. This asks deps.dev (Google's Open Source Insights) for the
resolved dependency graph of the version the change uses, then each package's own registry for the size of the file an install
downloads: the wheel pip would most likely pick on Linux x86_64 with CPython 3.12 (PyPI; the most specific wheel first, our reading of pip's choice), or the tarball (npm). deps.dev gives no
resolved graph for Go or NuGet, and its Cargo graph also holds dev-only dependencies, so those are not weighed. Everything is measured from those answers; nothing is estimated. A size the registry does not give is counted as
unknown, never guessed, and a graph larger than MAX_NODES is sized in its first MAX_NODES packages and said to be at least that.
The graph is deps.dev's resolution today, which can differ from the one an install on another day or with a lockfile makes.
Information only: the extras, the state and the exit code never depend on it.
"""
from __future__ import annotations

import concurrent.futures
import json
import math
import re
import urllib.parse

DEPS_DEV = "https://api.deps.dev/v3/systems/"
SYSTEM = {"PyPI": "pypi", "npm": "npm"}     # deps.dev resolves Cargo too, but with dev-only dependencies in it (fleet 43 R1)
MAX_NODES = 200           # packages sized per dependency; a larger graph is "at least"
WORKERS = 8               # size requests in flight at once
MAX_WEIGHED = 3           # dependencies weighed per job, the first ones the card shows
SHOWN = 2                 # largest packages named in the record
_PY_TAG = re.compile(r"-(?:py3|py2\.py3)-none-any\.whl$")
_CP312 = re.compile(r"-cp312-(?:cp312|abi3)-manylinux[^/]*x86_64[^/]*\.whl$")
_ABI3 = re.compile(r"-cp3\d+-abi3-manylinux[^/]*x86_64[^/]*\.whl$")
_PY_LINUX = re.compile(r"-(?:py3|py2\.py3)-none-manylinux[^/]*x86_64[^/]*\.whl$")     # e.g. NVIDIA's CUDA libraries


def _q(text: str) -> str:
    return urllib.parse.quote(text, safe="")


def graph_url(ecosystem: str, name: str, version: str) -> str:
    return f"{DEPS_DEV}{SYSTEM[ecosystem]}/packages/{_q(name)}/versions/{_q(version)}:dependencies"


def pick_wheel(files: list) -> dict | None:
    """The file pip would most likely download on a Linux x86_64 runner with CPython 3.12, in pip's order of preference (the most
    specific tag first): a cp312 manylinux wheel, else an abi3 one, else a py3 manylinux wheel, else a pure wheel, else the source
    archive; of several in one tier, the smallest. Our reading of pip's choice, not pip itself. None when the version has none."""
    files = [f for f in files if isinstance(f, dict) and isinstance(f.get("filename"), str) and type(f.get("size")) is int]
    for test in (lambda n: _CP312.search(n), lambda n: _ABI3.search(n), lambda n: _PY_LINUX.search(n),
                 lambda n: _PY_TAG.search(n), lambda n: n.endswith((".tar.gz", ".zip"))):
        hit = [f for f in files if test(f["filename"]) and not f.get("yanked")]
        if hit:
            return min(hit, key=lambda f: f["size"])
    return None


def size_request(ecosystem: str, name: str, version: str) -> tuple[str, str]:
    """(method, url) for the size of one package version. "SIZE" is a one-byte ranged GET whose answer carries the file's length."""
    if ecosystem == "PyPI":
        return "GET", f"https://pypi.org/pypi/{_q(name)}/{_q(version)}/json"
    if ecosystem == "npm":
        base = name.rsplit("/", 1)[-1]
        return "SIZE", f"https://registry.npmjs.org/{name}/-/{_q(base)}-{_q(version)}.tgz"
    raise ValueError(ecosystem)


def read_size(ecosystem: str, status: int, body: bytes) -> int | None:
    """The size in bytes from an answer to size_request, or None."""
    if status not in (200, 206):
        return None
    try:
        if ecosystem == "PyPI":
            f = pick_wheel(json.loads(body).get("urls") or [])
            return f["size"] if f else None
        n = int(body.decode("ascii"))
        return n if n >= 0 else None
    except (ValueError, AttributeError, TypeError, UnicodeDecodeError):
        return None


def nodes_of(doc: dict) -> list[dict]:
    """[{name, version, relation}] of the packages an install fetches: the graph's nodes less those bundled inside another package."""
    out = []
    for n in doc.get("nodes") or ():
        key = n.get("versionKey") if isinstance(n, dict) else None
        if not isinstance(key, dict) or n.get("bundled"):
            continue
        name, version = key.get("name"), key.get("version")
        if isinstance(name, str) and isinstance(version, str) and name and version:
            out.append({"name": name, "version": version, "relation": n.get("relation")})
    return out


def weigh(ask, ecosystem: str, name: str, version: str) -> dict:
    """`ask(method, url)` -> (status, body), the registry run's own request function (allowed hosts, time budget)."""
    if ecosystem not in SYSTEM or not version:
        return {"weight": "not_supported" if ecosystem not in SYSTEM else "no_version"}
    status, body = ask("GET", graph_url(ecosystem, name, version))
    if status != 200:
        return {"weight": "unavailable", "reason": f"graph_http_{status}"}
    doc = json.loads(body)
    if doc.get("error"):                  # deps.dev answers 200 with an error for a graph it could not resolve
        return {"weight": "unavailable", "reason": "graph_error"}
    nodes = nodes_of(doc)
    if not nodes:
        return {"weight": "unavailable", "reason": "empty_graph"}
    sized = nodes[:MAX_NODES]

    def one(n):
        try:
            method, url = size_request(ecosystem, n["name"], n["version"])
            st, b = ask(method, url)
            return read_size(ecosystem, st, b)
        except Exception:                 # noqa: BLE001 -- an unknown size stays unknown
            return None

    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        sizes = list(pool.map(one, sized))
    known = [(n, s) for n, s in zip(sized, sizes) if s is not None]
    largest = sorted(known, key=lambda x: -x[1])[:SHOWN]
    return {"weight": "ok", "source": "deps.dev", "version": version, "packages": len(nodes),
            "direct": sum(1 for n in nodes if n["relation"] == "DIRECT"), "sized": len(known), "of": len(sized),
            "bytes": sum(s for _, s in known), "capped": len(nodes) > MAX_NODES,
            "largest": [{"name": n["name"], "version": n["version"], "bytes": s} for n, s in largest]}


def _half_up(x: float, digits: int = 0) -> float:
    """Rounding with halves up, the same arithmetic as web/weigh.js (Python's round() sends halves to the even side)."""
    k = 10 ** digits
    return math.floor(x * k + 0.5) / k


def human(n: int) -> str:
    if n < 1000 * 1000:
        return f"{max(1, int(_half_up(n / 1000)))} kB"
    if n < 1000 ** 3:
        mb = n / 1e6
        return f"{_half_up(mb, 1):.1f} MB" if mb < 10 else f"{int(_half_up(mb))} MB"
    gb = n / 1e9
    return f"{_half_up(gb, 1):.1f} GB" if gb < 10 else f"{int(_half_up(gb))} GB"


def part(w: dict | None) -> str | None:
    """The words for the card, or None when there is nothing measured to say."""
    if not w or w.get("weight") != "ok":
        return None
    n = w["packages"]
    which = "for its latest version (the line pins none), " if w.get("of_version") == "latest" else ""
    if n <= 1:
        size = f"about {human(w['bytes'])} to download" if w["sized"] else "its size not given"
        return f"{which}it brings no other package ({size} on a fresh install)"
    more = n - 1
    words = f"{which}with what it brings along, {'at least ' if w['capped'] else ''}{n} packages ({more} more than the line names)"
    if w["sized"]:
        unknown = w["of"] - w["sized"]
        words += (f" and {'at least ' if (w['capped'] or unknown) else 'about '}{human(w['bytes'])} to download on every fresh install"
                  + (f" ({unknown} {'size' if unknown == 1 else 'sizes'} not given)" if unknown else ""))
    return words + monthly(w)


def monthly(w: dict) -> str:
    """The weight times this project's own pipelines in the last days (`pipelines`, set by the CI job), or "" when that
    count was not read. A count, not a forecast: it says what the same number of pipelines would download if each one
    installed the dependency without a cache, which a pipeline with a cache does not."""
    runs = w.get("pipelines")
    if not runs or not w.get("sized") or not runs.get("count"):
        return ""
    least = runs["at_least"] or w["capped"] or w["of"] > w["sized"]
    n = f"{'at least ' if runs['at_least'] else ''}{runs['count']} pipeline{'' if runs['count'] == 1 else 's'}"
    return (f"; this project ran {n} in the last {runs['days']} days, so {'at least' if least else 'about'} "
            f"{human(w['bytes'] * runs['count'])} a month if each one installs it without a cache")
