"""Lines a change adds that run what they decode, send the environment out, or write downloaded text over a source file.
Standard library only; no model.

Three shapes carried real supply-chain incidents and look like nothing in a file list: a payload decoded and run (the
tj-actions/changed-files and reviewdog action payloads), the CI environment or a credentials file posted to a server (the Codecov
bash uploader), and a build script that downloads a file and overwrites a source file with it (the Amazon Q extension, version
1.84.0). A fourth is older and common: a download run straight by a shell (`curl ... | sh`, `sh -c "$(curl ...)"`), in a script
or inside source code such as `os.system("curl ... | sh")`; CI files and Dockerfiles are left to itemator.moving, which names it
there. Only lines the change adds are read, in any file but tests, documentation and lock files, and only the named shapes are
matched, so an ordinary `curl` or `base64` is not reported. A shape is a fact about the added text, not a finding that the change
is malicious. Information only."""
from __future__ import annotations

import re

from itemator import fence as FE
from itemator import moving as MV

MAX_FOUND = 20
MAX_RUN = 40              # a download and the write over a source file must lie within this many consecutive added lines
SHOWN = 3
SHELL = r"(?:sudo\s+)?(?:ba|z|da|k)?sh\b"
NET = r"(?:curl|wget|nc|ncat)\b"
SOURCE_EXT = r"(?:ts|tsx|js|jsx|mjs|cjs|py|go|rs|c|cc|cpp|h|java|kt|rb|php|cs)"
WHOLE_ENV = r"(?:process\.env(?![.\[\w])|os\.environ(?![.\[\w])|os\.environ\.copy\(\)|dict\(os\.environ\)|Object\.entries\(process\.env\))"

_DECODE = tuple(re.compile(p, re.I) for p in (
    rf"base64\s+(?:-d|-D|--decode)\b[^\n]*\|\s*{SHELL}",
    r"\b(?:eval|exec)\s*\(\s*(?:atob|base64\.b64decode|Buffer\.from\([^)]*base64|zlib\.decompress|codecs\.decode)",
    r"\beval\s+[\"']?\$\([^)]*base64\s+(?:-d|--decode)",
    r"\bnew\s+Function\(\s*atob\(",
    r"\b(?:python3?|node|perl|ruby)\s+-[ce]\s+[\"'][^\"']*(?:b64decode|atob|base64)",
))
_ENV = tuple(re.compile(p, re.I) for p in (
    rf"\b(?:env|printenv)\b(?:\s+[^|;]*)?\|\s*(?:base64\s*\|\s*)?{NET}",
    rf"\b(?:curl|wget)\b[^\n]*(?:\s-d|--data(?:-binary|-raw|-urlencode)?|\s-F\b|--form|--upload-file|\s-T)\b[^\n]*(?:\$\(\s*(?:env|printenv)\b|`\s*(?:env|printenv)\b)",
    rf"git\s+remote\s+-v[^\n]*\|\s*{NET}",
    rf"{NET}[^\n]*\$\(\s*git\s+remote\s+-v",
    rf"\bcat\s+[^|;\n]*(?:\.ssh/|\.aws/credentials|\.npmrc|\.git-credentials|\.docker/config\.json)[^|;\n]*\|\s*{NET}",
))
_RUN_DOWNLOAD = tuple(re.compile(p, re.I) for p in (
    rf"{NET}[^|;&\n]*\|\s*{SHELL}",
    rf"\b(?:ba|z|da|k)?sh\s+-c\s+[\"']?\$\(\s*{NET}",
    rf"\b(?:ba|z|da|k)?sh\s+<\(\s*{NET}",
))
_SEND = re.compile(r"\b(?:fetch|axios\.(?:post|put)|https?\.request|got\.post|requests\.(?:post|put)|urlopen|\.post)\s*\(", re.I)
_WHOLE_ENV = re.compile(WHOLE_ENV)
_DOWNLOAD = re.compile(r"\b(?:curl|wget)\b|\bfetch\s*\(|requests\.get\s*\(|urllib\.request\.urlopen|https?\.get\s*\(|axios\.get\s*\(|\bdownload\w*\s*\(", re.I)
_WRITE = re.compile(r"\bwriteFile(?:Sync)?\s*\(|\bcopyFile(?:Sync)?\s*\(|\bcreateWriteStream\s*\(|(?:^|\s)(?:-o|-O|--output)\s|[\"'](?:-o|-O|--output)[\"']\s*,|>\s*[\"']?[\w./$-]+\." + SOURCE_EXT + r"\b")
_SOURCE_PATH = re.compile(r"[\"'][^\"'\n]*\." + SOURCE_EXT + r"[\"']")
_REDIRECT = re.compile(r"(?:\s-o|\s-O|--output|>)\s*[\"']?[\w./$-]+\." + SOURCE_EXT + r"\b")
_HUNK = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)")


def added(patch: str) -> list[tuple[int, str]]:
    """[(line number in the new file, text)] for each added line of a unified diff."""
    out, n = [], None
    for line in (patch or "").split("\n"):
        m = _HUNK.match(line)
        if m:
            n = int(m.group(1))
        elif n is not None and line.startswith("+"):
            out.append((n, line[1:]))
            n += 1
        elif n is not None and line.startswith(" "):
            n += 1
    return out


def _shape(text: str, build_file: bool = False) -> str | None:
    if any(p.search(text) for p in _DECODE):
        return "decode-and-run"
    if not build_file and any(p.search(text) for p in _RUN_DOWNLOAD):
        return "download-and-run"
    if any(p.search(text) for p in _ENV) or (_SEND.search(text) and _WHOLE_ENV.search(text)):
        return "env-to-network"
    return None


def _runs(lines: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    runs, cur = [], []
    for n, t in lines:
        if cur and n != cur[-1][0] + 1:
            runs.append(cur)
            cur = []
        cur.append((n, t))
    return runs + [cur] if cur else runs


def find(files: list[dict]) -> list[dict]:
    """[{path, line, kind, text}] with kind decode-and-run, download-and-run, env-to-network or download-over-source."""
    found = []
    for f in files:
        path = f.get("filename", "")
        if f.get("status") == "removed" or not f.get("patch") or FE._SKIP_PATH.search(path):
            continue
        lines = [(n, t) for n, t in added(f["patch"]) if not t.lstrip().startswith(("#", "//")) or t.lstrip().startswith("#!")]
        build = MV.is_build_file(path)
        for n, t in lines:
            kind = _shape(t, build)
            if kind:
                found.append({"path": path, "line": n, "kind": kind, "text": t.strip()[:80]})
        for run in _runs(lines):
            for i in range(0, max(1, len(run) - MAX_RUN + 1)):
                window = run[i:i + MAX_RUN]
                joined = "\n".join(t for _, t in window)
                if _DOWNLOAD.search(joined) and ((_WRITE.search(joined) and _SOURCE_PATH.search(joined)) or _REDIRECT.search(joined)):
                    at = next(((n, t) for n, t in window if _DOWNLOAD.search(t)), window[0])
                    found.append({"path": path, "line": at[0], "kind": "download-over-source", "text": at[1].strip()[:80]})
                    break
        if len(found) >= MAX_FOUND:
            return found[:MAX_FOUND]
    return found


_WHAT = {"decode-and-run": "decodes text and runs it", "download-and-run": "downloads a script and runs it", "env-to-network": "sends the environment or credentials to a server",
         "download-over-source": "downloads a file and writes it over a source file"}


def sentence(found: list[dict]) -> str:
    parts = [f"`{d['path']}` line {d['line']} {_WHAT[d['kind']]}" for d in found[:SHOWN]]
    more = f" and {len(found) - SHOWN} more" if len(found) > SHOWN else ""
    return "The change adds lines of a shape that has carried supply-chain attacks: " + "; ".join(parts) + more + "."
