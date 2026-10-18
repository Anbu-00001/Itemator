"""References that a change adds to the pipeline or an image build and that can change under it. Standard library only;
no model.

GitLab's own advice is to pin images by digest and includes by commit. This looks only at lines the change adds to CI
files and Dockerfiles and names the ones that point at something that moves by design: an image tagged `latest`, an include
or component on a branch (`main`, `master`, `HEAD`, `~latest`), a remote include whose URL is a branch, and a download piped
into a shell. A tag such as `3.12` is not named: it moves too, but naming every tag would name nearly every image. Information
only; a line the change did not add is never read."""
from __future__ import annotations

import re

from itemator import pipeline as PL

MAX_FOUND = 20
SHOWN = 3

_BRANCHES = r"(?:main|master|HEAD|develop|latest|stable|trunk)"
_IMAGE = re.compile(r"""^\s*(?:-\s*)?image:\s*["']?([^\s"'#]+)""")
_FROM = re.compile(r"""^\s*FROM\s+(?:--\S+\s+)?([^\s]+)""", re.I)
_REF = re.compile(rf"""^\s*(?:-\s*)?ref:\s*["']?({_BRANCHES})["']?\s*(?:#.*)?$""")
_REMOTE = re.compile(rf"""^\s*(?:-\s*)?(?:remote|file):\s*["']?(\S*/(?:-/)?(?:raw|blob)/{_BRANCHES}/\S*)""")
_COMPONENT = re.compile(rf"""^\s*(?:-\s*)?component:\s*["']?(\S+@(?:~latest|{_BRANCHES}))["']?""")
_PIPE = re.compile(r"\b(?:curl|wget)\b[^|;&]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b")


def is_build_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return PL.is_ci_path(path) or name.startswith("Dockerfile") or name.endswith(".Dockerfile") or name == "Containerfile"


def _image_kind(ref: str) -> str | None:
    if ref.startswith(("$", "${")) or ref == "scratch":
        return None
    last = ref.rsplit("/", 1)[-1]
    if ":" not in last:
        return "untagged"
    return "latest" if last.rsplit(":", 1)[1] == "latest" else None


def added_lines(patch: str) -> list[str]:
    out, in_hunk = [], False
    for line in (patch or "").split("\n"):
        if line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line.startswith("+"):
            out.append(line[1:])
    return out


def find(files: list[dict]) -> list[dict]:
    """[{path, kind, text}] for each added line that points at something that moves; kind is one of image-latest,
    image-untagged, include-branch, remote-branch, component-branch, pipe-to-shell."""
    found = []
    for f in files:
        path = f.get("filename", "")
        if f.get("status") == "removed" or not is_build_file(path) or not f.get("patch"):
            continue
        dockerfile = not PL.is_ci_path(path)
        for line in added_lines(f["patch"]):
            if line.lstrip().startswith("#"):
                continue
            hit = None
            m = (_FROM if dockerfile else _IMAGE).match(line)
            if m and (k := _image_kind(m.group(1))):
                if not (dockerfile and k == "untagged"):          # an untagged FROM is often a build stage
                    hit = (f"image-{k}", m.group(1))
            if hit is None and not dockerfile:
                for kind, pat in (("include-branch", _REF), ("remote-branch", _REMOTE), ("component-branch", _COMPONENT)):
                    m = pat.match(line)
                    if m:
                        hit = (kind, m.group(1))
                        break
            if hit is None and _PIPE.search(line):
                hit = ("pipe-to-shell", line.strip()[:80])
            if hit:
                found.append({"path": path, "kind": hit[0], "text": hit[1]})
                if len(found) >= MAX_FOUND:
                    return found
    return found


_WHAT = {"image-latest": "an image tagged `latest`", "image-untagged": "an image with no tag", "include-branch": "an include on a branch",
         "remote-branch": "an include from a branch URL", "component-branch": "a component on a moving version",
         "pipe-to-shell": "a download piped into a shell"}


def sentence(found: list[dict]) -> str:
    parts = [f"{_WHAT[d['kind']]} (`{d['text']}`) in `{d['path']}`" for d in found[:SHOWN]]
    more = f" and {len(found) - SHOWN} more" if len(found) > SHOWN else ""
    return "The change adds references that can change under it: " + "; ".join(parts) + more + "."
