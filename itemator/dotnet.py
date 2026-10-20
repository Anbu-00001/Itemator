"""NuGet packages a change adds to .NET project files, with the registry's facts for each. Standard library only; no model.

The extras rules do not read .NET build files (itemator/extras.py, rules v6: measured as config on samples A to E, it was over the limit),
so a `<PackageReference Include="X" Version="1.2.3" />` the change adds raises no extra and no thread. This reads those lines on their own
and sets nuget.org's facts beside them on the card (first release, releases, licence, advisories), through the same lookup the extras'
packages use (itemator/registry.py). A package a removed line already listed is a version change, not a new package. A name or a version
that is not plain text is not looked up. Information only: the state, the extras and the exit code never depend on it."""
from __future__ import annotations

import re

from itemator import registry as RG

PROJECT_FILES = re.compile(r"(?:.*/)?(?:[^/]+\.(?:csproj|fsproj|vbproj)|Directory\.Packages\.props|Directory\.Build\.props|packages\.config)", re.I)
MAX_FOUND = 20            # packages named per job; RG.MAX_PACKAGES of them are looked up
SHOWN = 3
_TAG = re.compile(r"<(?:PackageReference|PackageVersion)\b([^>]*)>", re.I)
_ATTR = re.compile(r"\b(Include|Update|Version|VersionOverride)\s*=\s*\"([^\"]*)\"", re.I)
_CONFIG = re.compile(r"<package\b([^>]*)>", re.I)
_CONFIG_ATTR = re.compile(r"\b(id|version)\s*=\s*\"([^\"]*)\"", re.I)
_PLAIN_VERSION = re.compile(r"\d+(?:\.\d+){1,3}(?:-[0-9A-Za-z.-]{1,40})?(?:\+[0-9A-Za-z.-]{1,40})?")


def _lines(patch: str):
    for raw in (patch or "").split("\n"):
        if raw[:1] in ("+", "-") and not raw.startswith(("+++", "---")):
            yield raw[0], raw[1:]


def _references(path: str, text: str):
    """[(name, version or None)] named on one line."""
    if path.lower().endswith("packages.config"):
        for m in _CONFIG.finditer(text):
            a = {k.lower(): v for k, v in _CONFIG_ATTR.findall(m.group(1))}
            if a.get("id"):
                yield a["id"], a.get("version")
        return
    for m in _TAG.finditer(text):
        a = {k.lower(): v for k, v in _ATTR.findall(m.group(1))}
        name = a.get("include") or a.get("update")
        if name:
            yield name, a.get("version") or a.get("versionoverride")


def find(files: list[dict]) -> list[dict]:
    """[{path, name, version}] for each package an added line names that no removed line of the same file names."""
    out, seen = [], set()
    for f in files:
        path = f.get("filename") or ""
        if f.get("status") == "removed" or not PROJECT_FILES.fullmatch(path) or not f.get("patch"):
            continue
        added, removed = [], set()
        for sign, text in _lines(f["patch"]):
            for name, version in _references(path, text):
                if sign == "+":
                    added.append((name, version))
                else:
                    removed.add(name.lower())
        for name, version in added:
            key = (path, name.lower())
            if name.lower() in removed or key in seen:
                continue
            seen.add(key)
            pin = version if version and _PLAIN_VERSION.fullmatch(version) else None
            out.append({"path": path, "name": name, "version": pin})
            if len(out) >= MAX_FOUND:
                return out
    return out


def look_up(found: list[dict], fetch, now) -> list[dict]:
    """The registry's record for each package found (RG.Run.look), the first RG.MAX_PACKAGES of them."""
    run = RG.Run(fetch, now.strftime("%Y-%m-%d"))
    return [run.look({"ecosystem": "NuGet", "name": p["name"], "version": p["version"]}) for p in found]


def sentence(found: list[dict], records: list[dict]) -> str | None:
    """One sentence for the card, or None when no package was added."""
    if not found:
        return None
    shown = [r for r in records if r.get("lookup") in ("ok", "unavailable")]
    head = f"{len(found)} NuGet {'package' if len(found) == 1 else 'packages'} added in .NET project files (the rules do not count these files as extras)"
    if not shown:
        return head + "."
    ok = [r for r in shown if r["lookup"] == "ok"]
    parts, declared = [], False
    for r in ok[:SHOWN]:
        parts.append(f"`{r['name']}`: {RG._facts(r, not declared)}")
        declared = declared or RG._shows_licence(r)
    if len(shown) > len(ok):
        parts.append(f"facts for {len(shown) - len(ok)} could not be read")
    if len(ok) > SHOWN:
        parts.append(f"{len(ok) - SHOWN} more in `checked` in itemator.json")
    return f"{head} (checked {shown[0]['checked']}): " + "; ".join(parts) + "."
