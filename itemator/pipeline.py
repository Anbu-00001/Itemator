"""What a change does to the project's own CI pipeline, for the card: GitLab's CI lint returns the fully merged
configuration (includes, templates and `extends` already resolved) for any commit, so the job reads it at the merge
base and at the head and compares the two, job by job. The merged text is cut at its top-level and second-level keys; no
YAML parser is needed (the checker runs on a bare Python image). Information only. Jobs that a pipeline execution policy
adds are not in GitLab's lint output, so this is the project's pipeline, not everything that runs. Standard library
only; no model."""
from __future__ import annotations

import re
import urllib.parse

CI_NAMES = (".gitlab-ci.yml", ".gitlab-ci.yaml")
CI_DIRS = (".gitlab/", "ci/")
GLOBAL_KEYS = ("variables", "stages", "default", "workflow", "include")
SHOWN_VALUES = ("allow_failure", "when")     # the two parts whose new value says most: a check turned into a warning, a job made manual
SHOWN = 3

# GitLab's own patch notes, read 2026-10-24: an unauthenticated user could run code on the server through a crafted regular
# expression, and CVE-2026-97229 is reached through a CI configuration. The lint read below hands GitLab the change's CI file
# to compile, so on a GitLab in these ranges the job does not ask. (first affected, first fixed) per release line.
# https://docs.gitlab.com/releases/patches/patch-release-gitlab-19-4-2-released/ (CVE-2026-97229)
# https://docs.gitlab.com/releases/patches/patch-release-gitlab-19-5-1-released/ (CVE-2026-110264)
UNSAFE_LINT = {
    "CVE-2026-97229": (((19, 2, 0), (19, 2, 8)), ((19, 3, 0), (19, 3, 5)), ((19, 4, 0), (19, 4, 2))),
    "CVE-2026-110264": (((7, 0, 0), (18, 11, 13)), ((19, 0, 0), (19, 0, 10)), ((19, 1, 0), (19, 1, 9)), ((19, 2, 0), (19, 2, 9)),
                        ((19, 3, 0), (19, 3, 6)), ((19, 4, 0), (19, 4, 3)), ((19, 5, 0), (19, 5, 1))),
}
_SERVER = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)(?![\d.])")

_TOP = re.compile(r'^("(?:[^"\\]|\\.)*"|[^\s#\-"][^:]*?):(?:\s|$)')
_SUB = re.compile(r'^  ("(?:[^"\\]|\\.)*"|[^\s#\-"][^:]*?):(?:\s|$)(.*)$')


def is_ci_path(path: str) -> bool:
    """A file whose change can change the pipeline: the CI file, files in `.gitlab/` or `ci/`, or any `*.gitlab-ci.yml`."""
    name = path.rsplit("/", 1)[-1]
    return (name in CI_NAMES or name.endswith((".gitlab-ci.yml", ".gitlab-ci.yaml"))
            or (path.startswith(CI_DIRS) and name.endswith((".yml", ".yaml"))))


def blocks(merged: str) -> dict[str, dict[str, str]]:
    """GitLab's merged YAML as {top-level key: {second-level key: its text}}. A key with a plain value keeps that value."""
    out: dict[str, dict[str, str]] = {}
    top = sub = None
    for line in merged.splitlines():
        if not line.strip() or line.startswith(("#", "---")):
            continue
        m = _TOP.match(line) if not line[0].isspace() else None
        if m:
            top, sub = m.group(1).strip('"'), None
            out.setdefault(top, {})
            rest = line[m.end():].strip()
            if rest:
                out[top][""] = rest
            continue
        if top is None:
            continue
        s = _SUB.match(line)
        if s:
            sub = s.group(1).strip('"')
            out[top][sub] = s.group(2).strip()
        elif sub is not None:
            out[top][sub] += "\n" + line.rstrip()
        else:
            out[top][""] = (out[top].get("", "") + "\n" + line.rstrip()).strip()
    return out


def _change(name: str, was: dict[str, str], now: dict[str, str]) -> dict | None:
    parts, values = [], {}
    for key in sorted(set(was) | set(now)):
        if was.get(key) != now.get(key):
            parts.append(key or "value")
            if key in SHOWN_VALUES:
                values[key] = (was.get(key, "absent") or "absent", now.get(key, "absent") or "absent")
    return {"job": name, "parts": parts, "values": values} if parts else None


def diff(base_yaml: str, head_yaml: str) -> dict:
    """{"added": [job], "removed": [job], "changed": [{"job", "parts", "values"}], "global": [key]} between two merged
    configurations. A top-level key named in GLOBAL_KEYS is reported under "global", never as a job."""
    was, now = blocks(base_yaml), blocks(head_yaml)
    added = sorted(k for k in now if k not in was and k not in GLOBAL_KEYS)
    removed = sorted(k for k in was if k not in now and k not in GLOBAL_KEYS)
    changed, glob = [], []
    for k in sorted(set(was) & set(now)):
        c = _change(k, was[k], now[k])
        if c and k in GLOBAL_KEYS:
            glob.append(k)
        elif c:
            changed.append(c)
    glob += [k for k in GLOBAL_KEYS if (k in now) != (k in was)]
    return {"added": added, "removed": removed, "changed": changed, "global": sorted(set(glob))}


def empty(d: dict) -> bool:
    return not (d["added"] or d["removed"] or d["changed"] or d["global"])


def unsafe_server(version: str | None) -> dict | None:
    """{version, cves} when `version` (CI_SERVER_VERSION, "19.6.0-pre" on GitLab.com) is in a range of UNSAFE_LINT, or when
    it cannot be read as major.minor.patch (then cves is empty: the job cannot tell, so it does not ask); None when the
    version is outside every range. No version at all (a run outside GitLab CI) is None: there is no server to protect."""
    if version is None or not version.strip():
        return None
    m = _SERVER.match(version)
    if not m:
        return {"version": version.strip()[:40], "cves": []}
    v = tuple(int(x) for x in m.groups())
    cves = [c for c, ranges in UNSAFE_LINT.items() if any(lo <= v < hi for lo, hi in ranges)]
    return {"version": ".".join(m.groups()), "cves": cves} if cves else None


def find(api, pid, base: str, head: str, files: list[dict], warnings: list, server_version: str | None = None) -> dict | None:
    """The diff of the merged pipeline configuration between `base` and `head`, or None when no changed file can change it,
    when nothing in the pipeline changed, or when GitLab could not be asked (a warning says why). On a GitLab that
    unsafe_server() names, nothing is asked and the result is {"skipped": that dict}."""
    if not any(is_ci_path(f.get("filename", "")) or is_ci_path(f.get("previous_filename") or "") for f in files):
        return None
    unsafe = unsafe_server(server_version)
    if unsafe:
        warnings.append(f"no pipeline check: GitLab {unsafe['version']} " + (f"is in the range of {', '.join(unsafe['cves'])}" if unsafe["cves"] else "is not a version the job can read"))
        return {"skipped": unsafe}
    try:
        merged = []
        for sha in (base, head):
            got = api.get(f"/projects/{pid}/ci/lint?content_ref={urllib.parse.quote(sha)}&include_jobs=true")
            if not isinstance(got, dict) or not got.get("valid", True) or not isinstance(got.get("merged_yaml"), str):
                raise ValueError("no merged configuration" if isinstance(got, dict) and got.get("valid", True) else "the configuration is invalid")
            merged.append(got["merged_yaml"])
    except Exception as e:                # noqa: BLE001 -- information only: a lint that cannot be read says nothing
        warnings.append(f"no pipeline check: {type(e).__name__}: {str(e)[:80]}")
        return None
    d = diff(*merged)
    return None if empty(d) else d


def _job_part(c: dict) -> str:
    shown = []
    for p in c["parts"]:
        if p in c["values"]:
            was, now = c["values"][p]
            shown.append(f"{p} ({was} to {now})")
        else:
            shown.append(p)
    return f"`{c['job']}`: {', '.join(shown)}"


def sentence(d: dict) -> str:
    """One sentence for the card. It says what changed in the merged project pipeline and what the view leaves out."""
    if "skipped" in d:
        u = d["skipped"]
        why = (f"GitLab's patch notes list {u['version']} as open to {' and '.join(u['cves'])}, run through a crafted regular expression, and that request hands GitLab this change's CI file to compile"
               if u["cves"] else f"the job cannot read this GitLab's version ({u['version']}) to rule out the regular-expression flaws GitLab patched in October 2026")
        return f"The job did not ask GitLab to merge the pipeline configuration: {why}. Upgrade GitLab to read it."
    parts = []
    for label, names in (("new", d["added"]), ("removed", d["removed"])):
        if names:
            more = f" and {len(names) - SHOWN} more" if len(names) > SHOWN else ""
            parts.append(f"{label} {'job' if len(names) == 1 else 'jobs'} {', '.join('`%s`' % n for n in names[:SHOWN])}{more}")
    if d["changed"]:
        more = f" and {len(d['changed']) - SHOWN} more jobs" if len(d["changed"]) > SHOWN else ""
        parts.append("changed: " + "; ".join(_job_part(c) for c in d["changed"][:SHOWN]) + more)
    if d["global"]:
        parts.append("global settings: " + ", ".join(f"`{k}`" for k in d["global"]))
    return ("The project's pipeline, as GitLab merges it, differs from the target branch: " + "; ".join(parts)
            + ". Jobs that a pipeline execution policy adds are not in this view.")
